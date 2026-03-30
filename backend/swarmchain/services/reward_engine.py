"""Reward engine — reward impact, not participation.

Rewards are computed based on actual contribution to convergence:
- Solver: produced the verified solution
- Lineage: ancestors in the winning path
- Exploration: high-scoring non-winning attempts that refined the search
- Efficiency: best score-per-energy ratio

Failed attempts with useful elimination signal are not discarded.
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.models import Attempt, Reward, Node, Block
from swarmchain.services.lineage import LineageService
from swarmchain.config import get_settings


class RewardEngine:
    """Computes and distributes rewards for a finalized block."""

    def __init__(self):
        s = get_settings()
        self.solver_pct = s.solver_reward_pct
        self.lineage_pct = s.lineage_reward_pct
        self.exploration_pct = s.exploration_reward_pct
        self.efficiency_pct = s.efficiency_reward_pct
        self.min_contribution = s.min_contribution_score

    async def compute_rewards(self, db: AsyncSession, block: Block) -> list[Reward]:
        """Compute all reward allocations for a finalized block.

        Returns list of Reward objects (already persisted).
        """
        pool = block.reward_pool
        rewards: list[Reward] = []

        # Fetch all valid attempts above minimum threshold
        result = await db.execute(
            select(Attempt)
            .where(Attempt.block_id == block.block_id)
            .where(Attempt.valid == True)
            .where(Attempt.score >= self.min_contribution)
            .order_by(Attempt.score.desc())
        )
        attempts = list(result.scalars().all())

        if not attempts:
            return rewards

        # ── 1. Solver reward (40%) ──────────────────────────
        solver_pool = pool * self.solver_pct
        if block.winning_attempt_id:
            winner = next((a for a in attempts if a.attempt_id == block.winning_attempt_id), None)
            if winner:
                r = Reward(
                    block_id=block.block_id,
                    node_id=winner.node_id,
                    reward_type="solver",
                    reward_amount=solver_pool,
                    score_basis=winner.score,
                )
                db.add(r)
                rewards.append(r)

        # ── 2. Lineage reward (30%) ─────────────────────────
        lineage_pool = pool * self.lineage_pct
        if block.winning_attempt_id:
            ancestry = await LineageService.get_ancestry(db, block.block_id, block.winning_attempt_id)
            # Exclude the winner itself (already got solver reward)
            ancestors = [aid for aid in ancestry if aid != block.winning_attempt_id]

            if ancestors:
                ancestor_attempts = [a for a in attempts if a.attempt_id in ancestors]
                total_ancestor_score = sum(a.score for a in ancestor_attempts) or 1.0

                for a in ancestor_attempts:
                    share = (a.score / total_ancestor_score) * lineage_pool
                    if share > 0:
                        r = Reward(
                            block_id=block.block_id,
                            node_id=a.node_id,
                            reward_type="lineage",
                            reward_amount=share,
                            score_basis=a.score,
                        )
                        db.add(r)
                        rewards.append(r)

        # ── 3. Exploration reward (20%) ─────────────────────
        exploration_pool = pool * self.exploration_pct
        # Non-winning, non-lineage attempts with good scores
        lineage_ids = set()
        if block.winning_attempt_id:
            lineage_ids = set(await LineageService.get_ancestry(db, block.block_id, block.winning_attempt_id))

        explorers = [a for a in attempts if a.attempt_id not in lineage_ids and a.score >= self.min_contribution]

        if explorers:
            total_explorer_score = sum(a.score for a in explorers) or 1.0
            for a in explorers:
                share = (a.score / total_explorer_score) * exploration_pool
                if share > 0:
                    r = Reward(
                        block_id=block.block_id,
                        node_id=a.node_id,
                        reward_type="exploration",
                        reward_amount=share,
                        score_basis=a.score,
                    )
                    db.add(r)
                    rewards.append(r)

        # ── 4. Efficiency reward (10%) ──────────────────────
        efficiency_pool = pool * self.efficiency_pct
        # Score-per-energy ratio — reward nodes that achieve more with less
        scored_attempts = [a for a in attempts if a.energy_cost > 0 and a.score >= self.min_contribution]

        if scored_attempts:
            efficiencies = [(a, a.score / a.energy_cost) for a in scored_attempts]
            total_efficiency = sum(e for _, e in efficiencies) or 1.0

            for a, eff in efficiencies:
                share = (eff / total_efficiency) * efficiency_pool
                if share > 0:
                    r = Reward(
                        block_id=block.block_id,
                        node_id=a.node_id,
                        reward_type="efficiency",
                        reward_amount=share,
                        score_basis=eff,
                    )
                    db.add(r)
                    rewards.append(r)

        await db.flush()

        # Update node total_rewards
        node_totals: dict[str, float] = {}
        for r in rewards:
            node_totals[r.node_id] = node_totals.get(r.node_id, 0.0) + r.reward_amount

        for nid, total in node_totals.items():
            result = await db.execute(select(Node).where(Node.node_id == nid))
            node = result.scalar_one_or_none()
            if node:
                node.total_rewards += total

        await db.flush()
        return rewards
