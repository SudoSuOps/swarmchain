"""Health and metrics endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.engine import get_db
from swarmchain.db.models import Block, Attempt, Node

router = APIRouter()


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Health check — confirms DB connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "service": "swarmchain"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/metrics")
async def metrics(db: AsyncSession = Depends(get_db)):
    """System-wide metrics snapshot."""
    blocks_total = (await db.execute(select(func.count(Block.id)))).scalar() or 0
    blocks_open = (await db.execute(
        select(func.count(Block.id)).where(Block.status == "open")
    )).scalar() or 0
    blocks_solved = (await db.execute(
        select(func.count(Block.id)).where(Block.status == "solved")
    )).scalar() or 0
    blocks_exhausted = (await db.execute(
        select(func.count(Block.id)).where(Block.status == "exhausted")
    )).scalar() or 0

    attempts_total = (await db.execute(select(func.count(Attempt.id)))).scalar() or 0
    nodes_total = (await db.execute(select(func.count(Node.id)))).scalar() or 0
    nodes_active = (await db.execute(
        select(func.count(Node.id)).where(Node.active == True)
    )).scalar() or 0

    total_energy = (await db.execute(
        select(func.sum(Attempt.energy_cost))
    )).scalar() or 0

    return {
        "blocks": {
            "total": blocks_total,
            "open": blocks_open,
            "solved": blocks_solved,
            "exhausted": blocks_exhausted,
        },
        "attempts": {"total": attempts_total},
        "nodes": {"total": nodes_total, "active": nodes_active},
        "total_energy": float(total_energy),
    }
