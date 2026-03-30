"""Node API — register and inspect compute nodes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.engine import get_db
from swarmchain.db.models import Node, Attempt
from swarmchain.schemas.nodes import NodeRegister, NodeResponse, NodeStats
from swarmchain.api.auth import require_api_key

router = APIRouter()


@router.post("/register", response_model=NodeResponse, dependencies=[Depends(require_api_key)])
async def register_node(req: NodeRegister, db: AsyncSession = Depends(get_db)):
    """Register a new compute node in the swarm."""
    # Check for duplicate
    if req.node_id:
        result = await db.execute(select(Node).where(Node.node_id == req.node_id))
        existing = result.scalar_one_or_none()
        if existing:
            return _to_response(existing)

    node = Node(
        node_type=req.node_type,
        hardware_class=req.hardware_class,
        metadata_=req.metadata,
    )
    if req.node_id:
        node.node_id = req.node_id
    db.add(node)
    await db.flush()
    return _to_response(node)


@router.get("", response_model=list[NodeResponse])
async def list_nodes(active: bool | None = None, db: AsyncSession = Depends(get_db)):
    """List all registered nodes."""
    q = select(Node).order_by(Node.registered_at.desc())
    if active is not None:
        q = q.where(Node.active == active)
    result = await db.execute(q)
    return [_to_response(n) for n in result.scalars().all()]


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(node_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single node by ID."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")
    return _to_response(node)


@router.get("/{node_id}/stats", response_model=NodeStats)
async def get_node_stats(node_id: str, db: AsyncSession = Depends(get_db)):
    """Get aggregated performance stats for a node."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")

    # Compute aggregated stats
    result = await db.execute(
        select(
            func.avg(Attempt.score).label("avg_score"),
            func.count(func.distinct(Attempt.block_id)).label("blocks"),
        )
        .where(Attempt.node_id == node_id)
    )
    stats = result.one()
    avg_score = float(stats.avg_score or 0)
    efficiency = avg_score / max(node.total_energy_used, 0.001)

    return NodeStats(
        node_id=node.node_id,
        total_attempts=node.total_attempts,
        total_solves=node.total_solves,
        total_rewards=node.total_rewards,
        total_energy_used=node.total_energy_used,
        avg_score=avg_score,
        efficiency=efficiency,
        blocks_participated=stats.blocks or 0,
    )


def _to_response(node: Node) -> NodeResponse:
    return NodeResponse(
        node_id=node.node_id,
        node_type=node.node_type,
        hardware_class=node.hardware_class,
        active=node.active,
        reputation_score=node.reputation_score,
        total_energy_used=node.total_energy_used,
        total_attempts=node.total_attempts,
        total_solves=node.total_solves,
        total_rewards=node.total_rewards,
        registered_at=node.registered_at,
        metadata=node.metadata_,
    )
