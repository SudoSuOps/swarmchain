"""Cost calculator — every block has a cost-to-mint.

Cost = electricity + API + depreciation + validation + orchestration.
Revenue = dataset sale price. Margin = revenue - cost.
Cost-per-honey is the metric. Track it. Trend it. Prove the algorithm works.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.models import Block, Attempt, Node
from swarmchain.db.algorithm import BlockCost, NodeCostProfile, SwarmEvent
from swarmchain.config import get_settings

logger = logging.getLogger("swarmchain.cost")

HONEY_THRESHOLD = 0.95
JELLY_THRESHOLD = 0.30


class CostCalculator:
    """Computes the real cost-to-mint for a sealed block."""

    @staticmethod
    async def compute(db: AsyncSession, block: Block) -> BlockCost:
        """Calculate full cost breakdown for a block.

        Called during finalization, alongside reward computation.
        """
        s = get_settings()

        # Get all attempts
        result = await db.execute(
            select(Attempt).where(Attempt.block_id == block.block_id)
        )
        attempts = list(result.scalars().all())

        # Classify yield
        honey = sum(1 for a in attempts if a.valid and a.score >= HONEY_THRESHOLD)
        jelly = sum(1 for a in attempts if a.valid and JELLY_THRESHOLD <= a.score < HONEY_THRESHOLD)
        propolis = sum(1 for a in attempts if a.valid and a.score < JELLY_THRESHOLD)

        # Sum energy costs
        total_energy = sum(a.energy_cost for a in attempts)
        total_latency_ms = sum(a.latency_ms for a in attempts)
        total_compute_sec = total_latency_ms / 1000.0

        # Electricity cost: energy_cost is in abstract units from the worker
        # real_worker.py reports: CPU-seconds × 0.1 or GPU watt-seconds
        # Convert to dollars using node electricity rates
        electricity_cost = 0.0
        for a in attempts:
            node_profile = await _get_node_profile(db, a.node_id)
            if node_profile:
                # energy_cost from real_worker = CPU-sec × 0.1 or GPU watt-sec
                # Convert watt-seconds to kWh: ws / 3600000
                kwh = a.energy_cost / 3600.0  # approximate: energy units → kWh
                electricity_cost += kwh * node_profile.electricity_rate
            else:
                # Default rate
                kwh = a.energy_cost / 3600.0
                electricity_cost += kwh * s.electricity_rate_per_kwh

        # API cost: sum from attempt metadata (if real_worker tracked it)
        api_cost = 0.0
        for a in attempts:
            if a.metadata_ and isinstance(a.metadata_, dict):
                api_cost += a.metadata_.get("api_cost", 0.0)

        # GPU depreciation: proportional to compute time used
        depreciation_cost = 0.0
        node_ids = set(a.node_id for a in attempts)
        for nid in node_ids:
            profile = await _get_node_profile(db, nid)
            if profile and profile.hourly_depreciation > 0:
                # Sum compute time for this node's attempts
                node_compute_ms = sum(a.latency_ms for a in attempts if a.node_id == nid)
                hours = node_compute_ms / 3_600_000.0
                depreciation_cost += hours * profile.hourly_depreciation

        # Orchestration overhead (fixed per block)
        orchestration_cost = s.orchestration_cost_per_block

        # Total
        total_cost = electricity_cost + api_cost + depreciation_cost + orchestration_cost

        # Cost per honey
        cost_per_honey = total_cost / max(honey, 1)
        cost_per_attempt = total_cost / max(len(attempts), 1)

        # Wall time (handle both naive and aware datetimes for SQLite compat)
        wall_time = 0.0
        if block.start_time and block.end_time:
            start = block.start_time
            end = block.end_time
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            wall_time = (end - start).total_seconds()

        # Revenue (from dataset sales, if any)
        from swarmchain.db.models import DatasetSale
        result = await db.execute(
            select(func.sum(DatasetSale.sale_price))
            .where(DatasetSale.block_id == block.block_id)
            .where(DatasetSale.status == "completed")
        )
        revenue = float(result.scalar() or 0)
        margin = revenue - total_cost
        roi_pct = (margin / total_cost * 100) if total_cost > 0 else 0

        # Create or update BlockCost
        result = await db.execute(
            select(BlockCost).where(BlockCost.block_id == block.block_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            cost_record = existing
        else:
            cost_record = BlockCost(block_id=block.block_id)
            db.add(cost_record)

        cost_record.electricity_cost = round(electricity_cost, 6)
        cost_record.api_cost = round(api_cost, 6)
        cost_record.depreciation_cost = round(depreciation_cost, 6)
        cost_record.orchestration_cost = round(orchestration_cost, 6)
        cost_record.total_cost = round(total_cost, 6)
        cost_record.honey_count = honey
        cost_record.jelly_count = jelly
        cost_record.propolis_count = propolis
        cost_record.cost_per_honey = round(cost_per_honey, 6)
        cost_record.cost_per_attempt = round(cost_per_attempt, 6)
        cost_record.revenue = round(revenue, 4)
        cost_record.margin = round(margin, 4)
        cost_record.roi_pct = round(roi_pct, 2)
        cost_record.wall_time_sec = round(wall_time, 2)
        cost_record.compute_time_sec = round(total_compute_sec, 2)

        await db.flush()

        # Emit cost event
        event = SwarmEvent(
            event_type="block.costed",
            source_node="cost_calculator",
            block_id=block.block_id,
            domain=block.domain,
            energy_cost=total_energy,
            payload={
                "total_cost": cost_record.total_cost,
                "cost_per_honey": cost_record.cost_per_honey,
                "honey": honey, "jelly": jelly, "propolis": propolis,
                "electricity": cost_record.electricity_cost,
                "api": cost_record.api_cost,
                "depreciation": cost_record.depreciation_cost,
            },
        )
        db.add(event)
        await db.flush()

        logger.info(
            f"Block {block.block_id} cost: ${total_cost:.4f} "
            f"(elec=${electricity_cost:.4f} api=${api_cost:.4f} depr=${depreciation_cost:.4f}) "
            f"honey={honey} cost/honey=${cost_per_honey:.4f}"
        )
        return cost_record


async def _get_node_profile(db: AsyncSession, node_id: str) -> NodeCostProfile | None:
    """Get the cost profile for a node, or None if not configured."""
    result = await db.execute(
        select(NodeCostProfile).where(NodeCostProfile.node_id == node_id)
    )
    return result.scalar_one_or_none()
