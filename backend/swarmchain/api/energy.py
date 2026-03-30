"""Energy API — silicon ladder, cost frontier, transform analysis, trends, live stats.

Endpoints:
- GET /energy/silicon-ladder  — all nodes ranked by honey efficiency
- GET /energy/cost-frontier   — per-model cost vs solve rate scatter data
- GET /energy/transforms      — per-transform-type performance breakdown
- GET /energy/trend           — convergence trend line over time
- GET /energy/live            — real-time energy stats from last hour
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from swarmchain.db.engine import get_db
from swarmchain.db.models import Block, Attempt, Node, Reward
from swarmchain.db.algorithm import ConvergenceMetric, BlockCost

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /energy/silicon-ladder — all nodes ranked by honey efficiency
# ---------------------------------------------------------------------------

@router.get("/silicon-ladder")
async def silicon_ladder(db: AsyncSession = Depends(get_db)):
    """Query all nodes, join with their attempts, compute efficiency metrics.

    Returns nodes sorted by honey_per_energy descending (most efficient first).
    """
    result = await db.execute(
        select(Node).where(Node.active == True)
    )
    nodes = result.scalars().all()

    ladder = []
    for node in nodes:
        # Get attempts for this node
        att_result = await db.execute(
            select(Attempt).where(Attempt.node_id == node.node_id)
        )
        attempts = att_result.scalars().all()

        total_attempts = len(attempts)
        total_energy = sum(a.energy_cost for a in attempts)
        total_honey = sum(1 for a in attempts if a.score >= 0.9)

        # Get total rewards
        rew_result = await db.execute(
            select(func.sum(Reward.reward_amount))
            .where(Reward.node_id == node.node_id)
        )
        total_rewards = rew_result.scalar() or 0.0

        honey_rate = total_honey / max(total_attempts, 1)
        avg_energy_per_honey = total_energy / max(total_honey, 1)
        honey_per_energy = total_honey / max(total_energy, 0.001)
        roi = float(total_rewards) / max(total_energy, 0.001)

        ladder.append({
            "node_id": node.node_id,
            "node_type": node.node_type,
            "hardware_class": node.hardware_class,
            "total_attempts": total_attempts,
            "total_honey": total_honey,
            "honey_rate": round(honey_rate, 4),
            "total_energy": round(total_energy, 4),
            "avg_energy_per_honey": round(avg_energy_per_honey, 4),
            "honey_per_energy": round(honey_per_energy, 6),
            "total_rewards": round(float(total_rewards), 4),
            "roi": round(roi, 4),
            "reputation_score": round(node.reputation_score, 4),
        })

    # Sort by efficiency (honey_per_energy desc)
    ladder.sort(key=lambda x: x["honey_per_energy"], reverse=True)

    return {
        "silicon_ladder": ladder,
        "total_nodes": len(ladder),
    }


# ---------------------------------------------------------------------------
# GET /energy/cost-frontier — per-model cost vs solve rate
# ---------------------------------------------------------------------------

@router.get("/cost-frontier")
async def cost_frontier(db: AsyncSession = Depends(get_db)):
    """For each model_name, compute avg_cost_per_honey and solve_rate.

    Returns array for scatter plot: {model, cost_per_honey, solve_rate, attempts, honey_count}.
    Model is derived from attempt metadata or node metadata/node_id.
    """
    # Fetch all attempts
    result = await db.execute(select(Attempt))
    attempts = result.scalars().all()

    # Build a node_id -> model_name cache
    node_result = await db.execute(select(Node))
    nodes = node_result.scalars().all()
    node_model_map: dict[str, str] = {}
    for n in nodes:
        model = n.node_id
        if n.metadata_:
            model = n.metadata_.get("model_name", n.node_id)
        node_model_map[n.node_id] = model

    # Group by model
    model_stats: dict[str, dict] = {}
    for att in attempts:
        # Determine model name
        model_name = "unknown"
        if att.metadata_ and att.metadata_.get("model_name"):
            model_name = att.metadata_["model_name"]
        elif att.node_id in node_model_map:
            model_name = node_model_map[att.node_id]

        if model_name not in model_stats:
            model_stats[model_name] = {
                "attempts": 0,
                "honey_count": 0,
                "total_energy": 0.0,
            }
        model_stats[model_name]["attempts"] += 1
        model_stats[model_name]["total_energy"] += att.energy_cost
        if att.score >= 0.9:
            model_stats[model_name]["honey_count"] += 1

    frontier = []
    for model, s in model_stats.items():
        honey = s["honey_count"]
        total = s["attempts"]
        energy = s["total_energy"]
        frontier.append({
            "model": model,
            "cost_per_honey": round(energy / max(honey, 1), 6),
            "solve_rate": round(honey / max(total, 1), 4),
            "attempts": total,
            "honey_count": honey,
        })

    # Sort by cost_per_honey ascending (cheapest first)
    frontier.sort(key=lambda x: x["cost_per_honey"])

    return {"cost_frontier": frontier}


# ---------------------------------------------------------------------------
# GET /energy/transforms — per-transform-type performance
# ---------------------------------------------------------------------------

@router.get("/transforms")
async def transform_stats(db: AsyncSession = Depends(get_db)):
    """For each transform type (parsed from task_id), compute performance stats.

    Transform type is extracted from the task_id field of blocks (e.g., "mirror_h",
    "rotate_90", etc.). Falls back to the full task_id if no separator found.
    """
    # Fetch all blocks with their attempts
    result = await db.execute(select(Block))
    blocks = result.scalars().all()
    block_task_map = {b.block_id: b.task_id for b in blocks}

    result = await db.execute(select(Attempt))
    attempts = result.scalars().all()

    # Group by transform type
    transform_data: dict[str, dict] = {}
    for att in attempts:
        task_id = block_task_map.get(att.block_id, "unknown")
        # Parse transform type: take part after last underscore or '/' or use full
        transform = task_id
        if "_" in task_id:
            # e.g. "arc_mirror_h_001" -> "mirror_h"
            parts = task_id.split("_")
            if len(parts) >= 3:
                transform = "_".join(parts[1:-1])  # middle parts = transform
            elif len(parts) == 2:
                transform = parts[0]

        if transform not in transform_data:
            transform_data[transform] = {
                "transform": transform,
                "attempts": 0,
                "honey_count": 0,
                "total_energy": 0.0,
            }
        transform_data[transform]["attempts"] += 1
        transform_data[transform]["total_energy"] += att.energy_cost
        if att.score >= 0.9:
            transform_data[transform]["honey_count"] += 1

    transforms = []
    for t, s in transform_data.items():
        honey = s["honey_count"]
        total = s["attempts"]
        transforms.append({
            "transform": t,
            "attempts": total,
            "honey_count": honey,
            "solve_rate": round(honey / max(total, 1), 4),
            "avg_energy_per_honey": round(
                s["total_energy"] / max(honey, 1), 4
            ),
        })

    # Sort by solve_rate descending
    transforms.sort(key=lambda x: x["solve_rate"], reverse=True)

    return {"transforms": transforms}


# ---------------------------------------------------------------------------
# GET /energy/trend — convergence trend line
# ---------------------------------------------------------------------------

@router.get("/trend")
async def energy_trend(
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Query ConvergenceMetric table ordered by window_end.

    Returns array of {window, cost_per_honey, attempts_per_solve, solve_rate, delta_cost}
    for line chart rendering.
    """
    result = await db.execute(
        select(ConvergenceMetric)
        .order_by(ConvergenceMetric.window_end.asc())
        .limit(limit)
    )
    metrics = result.scalars().all()

    trend = []
    for m in metrics:
        trend.append({
            "window": {
                "start": m.window_start,
                "end": m.window_end,
                "size": m.window_size,
            },
            "cost_per_honey": round(m.avg_cost_per_honey, 6),
            "attempts_per_solve": round(m.avg_attempts_per_solve, 4),
            "solve_rate": round(m.solve_rate, 4),
            "energy_per_honey": round(m.avg_energy_per_honey, 4),
            "delta_cost": round(m.delta_cost_per_honey, 6),
            "domain": m.domain,
            "computed_at": m.computed_at.isoformat() if m.computed_at else None,
        })

    return {
        "trend": trend,
        "total_windows": len(trend),
    }


# ---------------------------------------------------------------------------
# GET /energy/live — real-time stats from last hour
# ---------------------------------------------------------------------------

@router.get("/live")
async def energy_live(db: AsyncSession = Depends(get_db)):
    """Aggregate from recent attempts (last hour).

    Returns total_energy, attempts_count, active_nodes, energy_per_minute.
    """
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

    # Recent attempts
    result = await db.execute(
        select(Attempt).where(Attempt.created_at >= one_hour_ago)
    )
    recent_attempts = result.scalars().all()

    total_energy = sum(a.energy_cost for a in recent_attempts)
    attempts_count = len(recent_attempts)

    # Active nodes (nodes with attempts in last hour)
    active_node_ids = set(a.node_id for a in recent_attempts)
    active_nodes = len(active_node_ids)

    # Honey in last hour
    honey_count = sum(1 for a in recent_attempts if a.score >= 0.9)

    # Time span
    if recent_attempts:
        earliest = min(a.created_at for a in recent_attempts)
        latest = max(a.created_at for a in recent_attempts)
        span_minutes = max((latest - earliest).total_seconds() / 60, 1)
    else:
        span_minutes = 60.0

    energy_per_minute = total_energy / span_minutes

    return {
        "window": "last_hour",
        "total_energy": round(total_energy, 4),
        "attempts_count": attempts_count,
        "honey_count": honey_count,
        "active_nodes": active_nodes,
        "energy_per_minute": round(energy_per_minute, 4),
        "honey_rate": round(honey_count / max(attempts_count, 1), 4),
    }
