"""Attempt API — submit, score, and inspect reasoning attempts."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.engine import get_db
from swarmchain.db.models import Block, Attempt, Node
from swarmchain.schemas.attempts import AttemptSubmit, AttemptResponse, AttemptListResponse
from swarmchain.services.verifier import get_verifier
from swarmchain.services.lineage import LineageService
from swarmchain.api.auth import require_api_key

router = APIRouter()


@router.post("", response_model=AttemptResponse, dependencies=[Depends(require_api_key)])
async def submit_attempt(req: AttemptSubmit, db: AsyncSession = Depends(get_db)):
    """Submit a reasoning attempt against a block.

    The attempt is immediately scored by the domain verifier.
    Lineage is recorded if parent_attempt_id is provided.
    """
    # Validate block exists and is open
    result = await db.execute(select(Block).where(Block.block_id == req.block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(404, f"Block {req.block_id} not found")
    if block.status != "open":
        raise HTTPException(400, f"Block is {block.status}, not accepting attempts")

    # Validate node exists
    result = await db.execute(select(Node).where(Node.node_id == req.node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(404, f"Node {req.node_id} not found")

    # Score the attempt — objective verification first
    verifier = get_verifier(block.domain)
    verification = verifier.verify(block.task_payload, req.output_json)

    # Create attempt
    attempt = Attempt(
        block_id=req.block_id,
        node_id=req.node_id,
        parent_attempt_id=req.parent_attempt_id,
        method=req.method,
        strategy_family=req.strategy_family,
        output_json=req.output_json,
        score=verification["score"],
        valid=verification["valid"],
        energy_cost=req.energy_cost,
        latency_ms=req.latency_ms,
        metadata_=verification.get("details"),
    )
    db.add(attempt)

    # Update block counters
    block.attempt_count += 1
    block.total_energy += req.energy_cost

    # Update node counters
    node.total_attempts += 1
    node.total_energy_used += req.energy_cost

    # Record lineage if parent exists
    if req.parent_attempt_id:
        # Get parent score for delta
        parent_result = await db.execute(
            select(Attempt.score)
            .where(Attempt.attempt_id == req.parent_attempt_id)
        )
        parent_score = parent_result.scalar_one_or_none() or 0.0
        delta = verification["score"] - parent_score

        await LineageService.record_edge(
            db, req.block_id, req.parent_attempt_id, attempt.attempt_id, delta
        )

    await db.flush()
    return _to_response(attempt)


@router.get("/{attempt_id}", response_model=AttemptResponse)
async def get_attempt(attempt_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single attempt by ID."""
    result = await db.execute(select(Attempt).where(Attempt.attempt_id == attempt_id))
    attempt = result.scalar_one_or_none()
    if not attempt:
        raise HTTPException(404, f"Attempt {attempt_id} not found")
    return _to_response(attempt)


@router.get("/block/{block_id}", response_model=AttemptListResponse)
async def list_block_attempts(
    block_id: str,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all attempts for a block."""
    count_q = select(func.count(Attempt.id)).where(Attempt.block_id == block_id)
    total = (await db.execute(count_q)).scalar() or 0

    result = await db.execute(
        select(Attempt)
        .where(Attempt.block_id == block_id)
        .order_by(Attempt.created_at.desc())
        .limit(limit).offset(offset)
    )
    attempts = result.scalars().all()
    return AttemptListResponse(
        attempts=[_to_response(a) for a in attempts],
        total=total,
    )


@router.get("/block/{block_id}/top", response_model=AttemptListResponse)
async def top_attempts(
    block_id: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Get top-scoring attempts for a block."""
    result = await db.execute(
        select(Attempt)
        .where(Attempt.block_id == block_id)
        .where(Attempt.valid == True)
        .order_by(Attempt.score.desc())
        .limit(limit)
    )
    attempts = result.scalars().all()
    count_q = select(func.count(Attempt.id)).where(Attempt.block_id == block_id)
    total = (await db.execute(count_q)).scalar() or 0

    return AttemptListResponse(
        attempts=[_to_response(a) for a in attempts],
        total=total,
    )


@router.get("/block/{block_id}/lineage")
async def get_lineage(block_id: str, db: AsyncSession = Depends(get_db)):
    """Get the full lineage graph for a block."""
    edges = await LineageService.get_block_edges(db, block_id)
    return {"block_id": block_id, "edges": edges}


def _to_response(attempt: Attempt) -> AttemptResponse:
    return AttemptResponse(
        attempt_id=attempt.attempt_id,
        block_id=attempt.block_id,
        node_id=attempt.node_id,
        parent_attempt_id=attempt.parent_attempt_id,
        method=attempt.method,
        strategy_family=attempt.strategy_family,
        output_json=attempt.output_json,
        score=attempt.score,
        valid=attempt.valid,
        energy_cost=attempt.energy_cost,
        latency_ms=attempt.latency_ms,
        promoted=attempt.promoted,
        pruned=attempt.pruned,
        created_at=attempt.created_at,
        metadata=attempt.metadata_,
    )
