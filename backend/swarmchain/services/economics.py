"""Economics engine — dataset sale events and contribution-weighted payouts.

When a sealed block's dataset is sold, the sale proceeds are distributed
to all contributors proportional to their reward share from the original
block. This creates the incentive loop: useful search → sealed data →
dataset sale → contributor payouts.

Anti-spam and diminishing returns are applied here as final modifiers
before payout calculation.
"""
import logging
from datetime import datetime, timezone
from collections import Counter
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.models import (
    Block, Attempt, Node, Reward, DatasetSale, BlockArtifact,
)
from swarmchain.config import get_settings

logger = logging.getLogger("swarmchain.economics")


class EconomicsEngine:
    """Handles dataset sales and contribution-weighted payout distribution."""

    def __init__(self):
        s = get_settings()
        self.spam_threshold = s.spam_score_threshold
        self.spam_penalty_mult = s.spam_penalty_multiplier
        self.duplicate_decay = s.duplicate_decay_rate
        self.min_reputation = s.min_reputation_for_rewards

    async def execute_dataset_sale(
        self,
        db: AsyncSession,
        block_id: str,
        buyer: str,
        sale_price: float,
        platform_fee_pct: float = 0.10,
    ) -> DatasetSale:
        """Execute a dataset sale and distribute payouts to contributors.

        Payout flow:
        1. Platform takes fee (default 10%)
        2. Remaining distributed proportional to original block rewards
        3. Anti-spam nodes get penalized share
        4. Diminishing returns applied for repeated identical patterns
        5. Reputation gate: below min reputation gets zero payout
        """
        # Validate block exists and is finalized
        result = await db.execute(select(Block).where(Block.block_id == block_id))
        block = result.scalar_one_or_none()
        if not block:
            raise ValueError(f"Block {block_id} not found")
        if block.status not in ("solved", "exhausted"):
            raise ValueError(f"Block {block_id} not finalized (status: {block.status})")

        # Calculate fees
        platform_fee = sale_price * platform_fee_pct
        distributable = sale_price - platform_fee

        # Get original block rewards to determine contribution shares
        result = await db.execute(
            select(Reward).where(Reward.block_id == block_id)
        )
        original_rewards = list(result.scalars().all())

        if not original_rewards:
            # No rewards = no distribution, but record the sale
            sale = DatasetSale(
                block_id=block_id,
                buyer=buyer,
                sale_price=sale_price,
                platform_fee_pct=platform_fee_pct,
                platform_fee=platform_fee,
                distributable=distributable,
                payout_count=0,
                status="completed",
                completed_at=datetime.now(timezone.utc),
                payout_summary={"note": "no original rewards to distribute"},
            )
            db.add(sale)
            await db.flush()
            return sale

        # Aggregate original rewards per node
        node_original_totals: dict[str, float] = {}
        for r in original_rewards:
            node_original_totals[r.node_id] = node_original_totals.get(r.node_id, 0.0) + r.reward_amount

        total_original = sum(node_original_totals.values()) or 1.0

        # Fetch node data for reputation + spam checks
        node_ids = list(node_original_totals.keys())
        result = await db.execute(select(Node).where(Node.node_id.in_(node_ids)))
        nodes = {n.node_id: n for n in result.scalars().all()}

        # Compute spam and duplicate penalties per node
        result = await db.execute(
            select(Attempt).where(Attempt.block_id == block_id)
        )
        all_attempts = list(result.scalars().all())

        node_penalties = self._compute_penalties(all_attempts, nodes)

        # Calculate payouts with penalties applied
        payouts: list[dict] = []
        payout_rewards: list[Reward] = []
        total_distributed = 0.0

        for node_id, original_share in node_original_totals.items():
            node = nodes.get(node_id)
            if not node:
                continue

            # Base share proportional to original rewards
            base_payout = (original_share / total_original) * distributable

            # Reputation gate
            if node.reputation_score < self.min_reputation:
                base_payout = 0.0
                penalty_reason = "below_min_reputation"
            else:
                penalty_reason = None

            # Apply penalties
            penalty_info = node_penalties.get(node_id, {})
            penalty_mult = penalty_info.get("multiplier", 1.0)
            final_payout = base_payout * penalty_mult

            if penalty_mult < 1.0:
                penalty_reason = penalty_info.get("reason", "penalty_applied")

            # Reputation bonus: high rep gets a small bonus
            if node.reputation_score > 1.2 and final_payout > 0:
                rep_bonus = final_payout * (node.reputation_score - 1.0) * 0.1
                final_payout += rep_bonus

            total_distributed += final_payout

            payouts.append({
                "node_id": node_id,
                "original_share": round(original_share, 4),
                "base_payout": round(base_payout, 4),
                "final_payout": round(final_payout, 4),
                "penalty_multiplier": round(penalty_mult, 4),
                "penalty_reason": penalty_reason,
                "reputation": round(node.reputation_score, 4),
            })

            # Create reward record for sale payout
            if final_payout > 0:
                r = Reward(
                    block_id=block_id,
                    node_id=node_id,
                    reward_type="dataset_sale",
                    reward_amount=final_payout,
                    score_basis=original_share / total_original,
                )
                db.add(r)
                payout_rewards.append(r)

                # Update node totals
                node.total_rewards += final_payout

        # Normalize if over-distributed (due to rep bonuses)
        if total_distributed > distributable and total_distributed > 0:
            scale = distributable / total_distributed
            for r in payout_rewards:
                r.reward_amount *= scale
            for p in payouts:
                p["final_payout"] *= scale
            total_distributed = distributable

        # Create the sale record
        sale = DatasetSale(
            block_id=block_id,
            buyer=buyer,
            sale_price=sale_price,
            platform_fee_pct=platform_fee_pct,
            platform_fee=round(platform_fee, 4),
            distributable=round(distributable, 4),
            payout_count=len([p for p in payouts if p["final_payout"] > 0]),
            status="completed",
            completed_at=datetime.now(timezone.utc),
            payout_summary={
                "total_distributed": round(total_distributed, 4),
                "undistributed": round(distributable - total_distributed, 4),
                "payouts": payouts,
            },
        )
        db.add(sale)

        # Store as block artifact
        artifact = BlockArtifact(
            block_id=block_id,
            artifact_type="dataset_sale",
            artifact_json={
                "sale_id": sale.sale_id,
                "buyer": buyer,
                "sale_price": sale_price,
                "platform_fee": round(platform_fee, 4),
                "distributable": round(distributable, 4),
                "total_distributed": round(total_distributed, 4),
                "payout_count": sale.payout_count,
                "payouts": payouts,
                "sold_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(artifact)

        await db.flush()
        logger.info(
            f"Dataset sale: block={block_id} buyer={buyer} price={sale_price} "
            f"distributed={total_distributed:.2f} to {sale.payout_count} nodes"
        )
        return sale

    def _compute_penalties(
        self,
        attempts: list[Attempt],
        nodes: dict[str, Node],
    ) -> dict[str, dict]:
        """Compute anti-spam and diminishing returns penalties per node."""
        penalties: dict[str, dict] = {}

        # Group attempts by node
        node_attempts: dict[str, list[Attempt]] = {}
        for a in attempts:
            node_attempts.setdefault(a.node_id, []).append(a)

        for node_id, nattempts in node_attempts.items():
            multiplier = 1.0
            reasons = []

            # Anti-spam: penalize nodes with many below-threshold attempts
            spam_count = sum(1 for a in nattempts if a.score < self.spam_threshold)
            total = len(nattempts)
            spam_ratio = spam_count / max(total, 1)

            if spam_ratio > 0.5:
                multiplier *= self.spam_penalty_mult
                reasons.append(f"spam_ratio:{spam_ratio:.2f}")
            elif spam_ratio > 0.2:
                multiplier *= (1.0 - spam_ratio)
                reasons.append(f"partial_spam:{spam_ratio:.2f}")

            # Diminishing returns: repeated identical outputs
            output_hashes = []
            for a in nattempts:
                h = hash(str(sorted(a.output_json.items()) if isinstance(a.output_json, dict) else str(a.output_json)))
                output_hashes.append(h)

            hash_counts = Counter(output_hashes)
            max_repeats = max(hash_counts.values()) if hash_counts else 1
            if max_repeats > 3:
                decay = self.duplicate_decay ** (max_repeats - 3)
                multiplier *= decay
                reasons.append(f"duplicate_repeats:{max_repeats}")

            # Strategy monotony: using same strategy family for >80% of attempts
            strategies = [a.strategy_family for a in nattempts]
            strategy_counts = Counter(strategies)
            dominant_strategy = strategy_counts.most_common(1)[0] if strategy_counts else ("", 0)
            if total > 5 and dominant_strategy[1] / total > 0.8:
                multiplier *= 0.8
                reasons.append(f"strategy_monotony:{dominant_strategy[0]}")

            penalties[node_id] = {
                "multiplier": max(0.0, min(1.0, multiplier)),
                "reason": "; ".join(reasons) if reasons else None,
                "spam_count": spam_count,
                "duplicate_max": max_repeats,
            }

        return penalties

    async def get_sale_history(self, db: AsyncSession, limit: int = 50) -> list[dict]:
        """Get dataset sale history."""
        result = await db.execute(
            select(DatasetSale)
            .order_by(DatasetSale.created_at.desc())
            .limit(limit)
        )
        sales = result.scalars().all()
        return [
            {
                "sale_id": s.sale_id,
                "block_id": s.block_id,
                "buyer": s.buyer,
                "sale_price": s.sale_price,
                "platform_fee": s.platform_fee,
                "distributable": s.distributable,
                "payout_count": s.payout_count,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
            }
            for s in sales
        ]
