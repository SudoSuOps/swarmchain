"""Event stream API — every action in the swarm produces a receipt."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.engine import get_db
from swarmchain.db.algorithm import SwarmEvent, BlockCost, ConvergenceMetric, CookJob, TrainingRun
from swarmchain.api.auth import require_api_key

router = APIRouter()


class EventSubmit(BaseModel):
    event_type: str
    source_node: str | None = None
    block_id: str | None = None
    domain: str | None = None
    energy_cost: float = 0.0
    payload: dict = {}


@router.post("/events", dependencies=[Depends(require_api_key)])
async def log_event(req: EventSubmit, db: AsyncSession = Depends(get_db)):
    """Log a swarm event — anything that happens produces a receipt."""
    event = SwarmEvent(
        event_type=req.event_type,
        source_node=req.source_node,
        block_id=req.block_id,
        domain=req.domain,
        energy_cost=req.energy_cost,
        payload=req.payload,
    )
    db.add(event)
    await db.flush()
    return {"event_id": event.event_id, "event_type": event.event_type}


@router.get("/events/stream")
async def event_stream(
    limit: int = 50,
    event_type: str | None = None,
    source_node: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Live event stream — the swarm's pulse."""
    q = select(SwarmEvent).order_by(SwarmEvent.timestamp.desc()).limit(limit)
    if event_type:
        q = q.where(SwarmEvent.event_type == event_type)
    if source_node:
        q = q.where(SwarmEvent.source_node == source_node)

    result = await db.execute(q)
    events = result.scalars().all()
    return [
        {
            "event_id": e.event_id,
            "event_type": e.event_type,
            "source_node": e.source_node,
            "block_id": e.block_id,
            "domain": e.domain,
            "energy_cost": e.energy_cost,
            "payload": e.payload,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in events
    ]


@router.get("/events/summary")
async def event_summary(db: AsyncSession = Depends(get_db)):
    """Event type counts — what's the swarm doing?"""
    result = await db.execute(
        select(SwarmEvent.event_type, func.count(SwarmEvent.id))
        .group_by(SwarmEvent.event_type)
    )
    return {row[0]: row[1] for row in result.all()}


@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db)):
    """The unified swarm status — everything in one view."""
    from swarmchain.db.models import Block, Node, Attempt
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Blocks today
    blocks_today = (await db.execute(
        select(func.count(Block.id)).where(Block.start_time >= today_start)
    )).scalar() or 0
    solved_today = (await db.execute(
        select(func.count(Block.id))
        .where(Block.status == "solved")
        .where(Block.end_time >= today_start)
    )).scalar() or 0

    # Attempts today
    attempts_today = (await db.execute(
        select(func.count(Attempt.id)).where(Attempt.created_at >= today_start)
    )).scalar() or 0

    # Energy today
    energy_today = (await db.execute(
        select(func.sum(Attempt.energy_cost)).where(Attempt.created_at >= today_start)
    )).scalar() or 0

    # Nodes active (any attempt in last hour)
    one_hour_ago = now - timedelta(hours=1)
    active_nodes = (await db.execute(
        select(func.count(func.distinct(Attempt.node_id)))
        .where(Attempt.created_at >= one_hour_ago)
    )).scalar() or 0

    # Total nodes
    total_nodes = (await db.execute(select(func.count(Node.id)))).scalar() or 0

    # All-time totals
    total_blocks = (await db.execute(select(func.count(Block.id)))).scalar() or 0
    total_solved = (await db.execute(
        select(func.count(Block.id)).where(Block.status == "solved")
    )).scalar() or 0
    total_energy = (await db.execute(
        select(func.sum(Attempt.energy_cost))
    )).scalar() or 0

    # Latest convergence metric
    result = await db.execute(
        select(ConvergenceMetric).order_by(ConvergenceMetric.computed_at.desc()).limit(1)
    )
    latest_convergence = result.scalar_one_or_none()

    convergence = None
    if latest_convergence:
        convergence = {
            "window": f"{latest_convergence.window_start}-{latest_convergence.window_end}",
            "solve_rate": latest_convergence.solve_rate,
            "attempts_per_solve": latest_convergence.avg_attempts_per_solve,
            "cost_per_honey": latest_convergence.avg_cost_per_honey,
            "delta_attempts": latest_convergence.delta_attempts_per_solve,
            "delta_cost": latest_convergence.delta_cost_per_honey,
            "improving": latest_convergence.delta_cost_per_honey <= 0,
        }

    # Recent events (last 20)
    result = await db.execute(
        select(SwarmEvent).order_by(SwarmEvent.timestamp.desc()).limit(20)
    )
    recent_events = [
        {
            "event_type": e.event_type,
            "source_node": e.source_node,
            "block_id": e.block_id,
            "energy_cost": e.energy_cost,
            "timestamp": e.timestamp.isoformat(),
            "summary": _event_summary(e),
        }
        for e in result.scalars().all()
    ]

    return {
        "today": {
            "blocks_opened": blocks_today,
            "blocks_solved": solved_today,
            "attempts": attempts_today,
            "energy": round(float(energy_today), 4),
        },
        "all_time": {
            "blocks_total": total_blocks,
            "blocks_solved": total_solved,
            "total_energy": round(float(total_energy), 4),
        },
        "nodes": {
            "total": total_nodes,
            "active_last_hour": active_nodes,
        },
        "convergence": convergence,
        "recent_events": recent_events,
    }


def _event_summary(e: SwarmEvent) -> str:
    """One-line summary of an event for the dashboard feed."""
    p = e.payload or {}
    if e.event_type == "block.costed":
        return f"${p.get('total_cost', 0):.4f} cost, {p.get('honey', 0)} honey"
    elif e.event_type == "convergence.computed":
        return f"solve={p.get('solve_rate', 0):.0%} cost/honey=${p.get('cost_per_honey', 0):.4f}"
    elif "block" in e.event_type:
        return f"block {(e.block_id or '')[:8]}"
    elif "model" in e.event_type:
        return p.get("model_name", "")
    elif "cook" in e.event_type:
        return f"{p.get('pairs', 0)} pairs, {p.get('domain', '')}"
    return ""
