"""Reputation system — trust is earned through useful contribution.

Reputation governs:
- Reward multiplier (high rep nodes earn more per contribution)
- Spam gate (below min threshold = no rewards)
- Priority in controller beam selection

Reputation changes:
- Solve a block: +boost
- Lineage contribution to a solve: +small boost
- Spam attempts (below threshold, repeated patterns): -penalty
- Natural decay over time toward 1.0 (mean reversion)

Reputation is bounded [0.0, 2.0]. Starting value is 1.0.
"""
import logging
from collections import Counter
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.models import Node, Attempt, Reward
from swarmchain.config import get_settings

logger = logging.getLogger("swarmchain.reputation")

REPUTATION_MIN = 0.0
REPUTATION_MAX = 2.0
REPUTATION_DEFAULT = 1.0


class ReputationService:
    """Computes and updates node reputation scores."""

    def __init__(self):
        s = get_settings()
        self.solve_boost = s.reputation_solve_boost
        self.spam_penalty = s.reputation_spam_penalty
        self.decay_rate = s.reputation_decay_rate
        self.spam_threshold = s.spam_score_threshold

    @staticmethod
    def clamp(value: float) -> float:
        return max(REPUTATION_MIN, min(REPUTATION_MAX, value))

    async def update_after_block(self, db: AsyncSession, block_id: str) -> dict[str, float]:
        """Update reputation for all nodes that participated in a block.

        Returns dict of {node_id: new_reputation}.
        """
        # Get all attempts for this block
        result = await db.execute(
            select(Attempt).where(Attempt.block_id == block_id)
        )
        attempts = list(result.scalars().all())

        if not attempts:
            return {}

        # Group by node
        node_attempts: dict[str, list[Attempt]] = {}
        for a in attempts:
            node_attempts.setdefault(a.node_id, []).append(a)

        updates: dict[str, float] = {}

        for node_id, nattempts in node_attempts.items():
            result = await db.execute(select(Node).where(Node.node_id == node_id))
            node = result.scalar_one_or_none()
            if not node:
                continue

            rep = node.reputation_score
            scores = [a.score for a in nattempts]

            # Spam detection: low-score repeated attempts
            spam_count = sum(1 for s in scores if s < self.spam_threshold)
            if spam_count > 0:
                penalty = self.spam_penalty * spam_count
                rep -= penalty
                logger.debug(f"Node {node_id}: spam penalty -{penalty:.3f} ({spam_count} spam attempts)")

            # Duplicate pattern detection: repeated identical scores suggest same output
            score_counts = Counter(round(s, 4) for s in scores)
            for score_val, count in score_counts.items():
                if count > 3:  # more than 3 identical scores = suspicious
                    dup_penalty = self.spam_penalty * 0.5 * (count - 3)
                    rep -= dup_penalty
                    logger.debug(f"Node {node_id}: duplicate penalty -{dup_penalty:.3f} (score {score_val} x{count})")

            # Solve boost
            if any(a.score >= 1.0 and a.valid for a in nattempts):
                rep += self.solve_boost
                logger.debug(f"Node {node_id}: solve boost +{self.solve_boost:.3f}")

            # Lineage contribution boost (small)
            if any(a.promoted for a in nattempts):
                rep += self.solve_boost * 0.2
                logger.debug(f"Node {node_id}: promotion boost +{self.solve_boost * 0.2:.3f}")

            # Mean reversion toward 1.0
            rep += (REPUTATION_DEFAULT - rep) * self.decay_rate

            rep = self.clamp(rep)
            node.reputation_score = rep
            updates[node_id] = rep

        await db.flush()
        return updates

    async def get_leaderboard(self, db: AsyncSession, limit: int = 50) -> list[dict]:
        """Get nodes ranked by reputation."""
        result = await db.execute(
            select(Node)
            .where(Node.active == True)
            .order_by(Node.reputation_score.desc())
            .limit(limit)
        )
        nodes = result.scalars().all()
        return [
            {
                "node_id": n.node_id,
                "node_type": n.node_type,
                "reputation_score": n.reputation_score,
                "total_attempts": n.total_attempts,
                "total_solves": n.total_solves,
                "total_rewards": n.total_rewards,
                "efficiency": n.total_rewards / max(n.total_energy_used, 0.001),
            }
            for n in nodes
        ]

    @staticmethod
    async def detect_spam_attempts(db: AsyncSession, block_id: str) -> list[dict]:
        """Identify spam attempts in a block for transparency."""
        s = get_settings()
        result = await db.execute(
            select(Attempt)
            .where(Attempt.block_id == block_id)
            .where(Attempt.score < s.spam_score_threshold)
            .order_by(Attempt.created_at)
        )
        spam = result.scalars().all()
        return [
            {
                "attempt_id": a.attempt_id,
                "node_id": a.node_id,
                "score": a.score,
                "method": a.method,
                "energy_cost": a.energy_cost,
            }
            for a in spam
        ]
