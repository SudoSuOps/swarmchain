"""Convergence tracker — the proof the swarm is getting smarter.

Computes rolling window metrics after each sealed block.
If cost-per-honey trends DOWN, the algorithm works.
If flat, models aren't improving. If UP, something broke.

The convergence curve IS the SwarmAlgorithm.
"""
import logging
from datetime import timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.models import Block, Attempt
from swarmchain.db.algorithm import BlockCost, ConvergenceMetric, SwarmEvent
from swarmchain.services.discord_notify import DiscordNotifier

logger = logging.getLogger("swarmchain.convergence")

DEFAULT_WINDOW_SIZE = 20  # compute metrics every 20 blocks


class ConvergenceTracker:
    """Tracks the convergence curve — the core metric of the SwarmAlgorithm."""

    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE):
        self.window_size = window_size
        self.discord = DiscordNotifier()
        self._hedera_anchor = None  # lazy-init to avoid circular imports

    def _get_hedera_anchor(self):
        """Lazy-load the HederaAnchor service."""
        if self._hedera_anchor is None:
            from swarmchain.services.hedera_anchor import HederaAnchor
            self._hedera_anchor = HederaAnchor.from_settings()
        return self._hedera_anchor

    async def update(self, db: AsyncSession, block_id: str) -> ConvergenceMetric | None:
        """Called after each block seal. Computes window if enough blocks."""

        # Count total sealed blocks
        result = await db.execute(
            select(func.count(Block.id))
            .where(Block.status.in_(["solved", "exhausted"]))
        )
        total_sealed = result.scalar() or 0

        # Only compute window at window_size intervals
        if total_sealed % self.window_size != 0 or total_sealed == 0:
            return None

        window_end = total_sealed
        window_start = max(0, total_sealed - self.window_size)

        # Get the blocks in this window (by seal order)
        result = await db.execute(
            select(Block)
            .where(Block.status.in_(["solved", "exhausted"]))
            .order_by(Block.end_time.desc())
            .limit(self.window_size)
        )
        window_blocks = list(result.scalars().all())

        if not window_blocks:
            return None

        # Compute metrics
        solved = [b for b in window_blocks if b.status == "solved"]
        blocks_sealed = len(window_blocks)
        blocks_solved = len(solved)
        solve_rate = blocks_solved / max(blocks_sealed, 1)

        # Attempts per solve
        total_attempts = sum(b.attempt_count for b in window_blocks)
        avg_attempts_per_solve = total_attempts / max(blocks_solved, 1)

        # Cost per honey (from BlockCost records)
        block_ids = [b.block_id for b in window_blocks]
        result = await db.execute(
            select(func.avg(BlockCost.cost_per_honey), func.avg(BlockCost.total_cost))
            .where(BlockCost.block_id.in_(block_ids))
        )
        cost_row = result.one()
        avg_cost_per_honey = float(cost_row[0] or 0)

        # Time to solve
        solve_times = []
        for b in solved:
            if b.start_time and b.end_time:
                start = b.start_time.replace(tzinfo=timezone.utc) if b.start_time.tzinfo is None else b.start_time
                end = b.end_time.replace(tzinfo=timezone.utc) if b.end_time.tzinfo is None else b.end_time
                solve_times.append((end - start).total_seconds())
        avg_time_to_solve = sum(solve_times) / max(len(solve_times), 1)

        # Energy per honey
        total_energy = sum(b.total_energy for b in window_blocks)
        total_honey = sum(1 for b in solved)  # simplification: 1 honey per solved block
        avg_energy_per_honey = total_energy / max(total_honey, 1)

        # Propolis ratio
        result = await db.execute(
            select(func.count(Attempt.id))
            .where(Attempt.block_id.in_(block_ids))
            .where(Attempt.valid == True)
            .where(Attempt.score < 0.30)
        )
        propolis_total = result.scalar() or 0
        propolis_ratio = propolis_total / max(total_attempts, 1)

        # Get previous window for delta
        result = await db.execute(
            select(ConvergenceMetric)
            .order_by(ConvergenceMetric.computed_at.desc())
            .limit(1)
        )
        previous = result.scalar_one_or_none()

        delta_attempts = 0.0
        delta_cost = 0.0
        if previous:
            delta_attempts = avg_attempts_per_solve - previous.avg_attempts_per_solve
            delta_cost = avg_cost_per_honey - previous.avg_cost_per_honey

        # Store
        metric = ConvergenceMetric(
            window_start=window_start,
            window_end=window_end,
            window_size=self.window_size,
            blocks_sealed=blocks_sealed,
            blocks_solved=blocks_solved,
            solve_rate=round(solve_rate, 4),
            avg_attempts_per_solve=round(avg_attempts_per_solve, 2),
            avg_cost_per_honey=round(avg_cost_per_honey, 6),
            avg_time_to_solve_sec=round(avg_time_to_solve, 2),
            avg_energy_per_honey=round(avg_energy_per_honey, 4),
            propolis_ratio=round(propolis_ratio, 4),
            delta_attempts_per_solve=round(delta_attempts, 2),
            delta_cost_per_honey=round(delta_cost, 6),
        )
        db.add(metric)

        # Emit convergence event
        event = SwarmEvent(
            event_type="convergence.computed",
            source_node="convergence_tracker",
            energy_cost=0,
            payload={
                "window": f"{window_start}-{window_end}",
                "solve_rate": metric.solve_rate,
                "attempts_per_solve": metric.avg_attempts_per_solve,
                "cost_per_honey": metric.avg_cost_per_honey,
                "delta_attempts": metric.delta_attempts_per_solve,
                "delta_cost": metric.delta_cost_per_honey,
                "improving": delta_cost < 0 and delta_attempts < 0,
            },
        )
        db.add(event)
        await db.flush()

        # Hedera HCS anchoring — check if this convergence window triggers an anchor
        try:
            anchor = self._get_hedera_anchor()
            anchor_receipt = await anchor.maybe_anchor(db, total_sealed)
            if anchor_receipt and anchor_receipt.get("merkle_root"):
                anchored = anchor_receipt.get("anchored", False)
                status = "ANCHORED" if anchored else "PENDING"
                logger.info(
                    f"Hedera anchor {status} at block {total_sealed}: "
                    f"root={anchor_receipt['merkle_root'][:18]}..."
                )
        except Exception as e:
            logger.error(f"Hedera anchoring failed (non-fatal): {e}")

        # Discord alert
        direction = "DOWN" if delta_cost <= 0 else "UP"
        await self.discord.custom(
            title=f"CONVERGENCE: blocks {window_start}-{window_end}",
            message=(
                f"Solve rate: {solve_rate:.0%} | "
                f"Attempts/solve: {avg_attempts_per_solve:.1f} ({delta_attempts:+.1f})\n"
                f"Cost/honey: ${avg_cost_per_honey:.4f} ({delta_cost:+.4f}) {direction}\n"
                f"Propolis ratio: {propolis_ratio:.1%}"
            ),
            color=0x00FF88 if delta_cost <= 0 else 0xFF4444,
        )

        logger.info(
            f"Convergence window {window_start}-{window_end}: "
            f"solve={solve_rate:.0%} attempts/solve={avg_attempts_per_solve:.1f} "
            f"cost/honey=${avg_cost_per_honey:.4f} delta={delta_cost:+.4f}"
        )
        return metric
