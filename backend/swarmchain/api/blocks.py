"""Block API — open, inspect, and finalize reasoning blocks."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.engine import get_db
from swarmchain.db.models import Block, BlockArtifact
from swarmchain.schemas.blocks import BlockOpen, BlockResponse, BlockListResponse, BlockFinalize
from swarmchain.services.controller import BlockController
from swarmchain.tasks.arc_tasks import get_task_payload
from swarmchain.api.auth import require_api_key

router = APIRouter()
controller = BlockController()


@router.post("/open", response_model=BlockResponse, dependencies=[Depends(require_api_key)])
async def open_block(req: BlockOpen, db: AsyncSession = Depends(get_db)):
    """Open a new reasoning block for distributed solving."""
    # If ARC domain and no task_payload, load from task catalog
    payload = req.task_payload
    if not payload and req.domain == "arc":
        payload = get_task_payload(req.task_id)
        if not payload:
            raise HTTPException(404, f"Task {req.task_id} not found in ARC catalog")

    block = Block(
        task_id=req.task_id,
        domain=req.domain,
        reward_pool=req.reward_pool,
        max_attempts=req.max_attempts,
        time_limit_sec=req.time_limit_sec,
        task_payload=payload,
        metadata_=req.metadata,
    )
    db.add(block)
    await db.flush()
    return _to_response(block)


@router.get("", response_model=BlockListResponse)
async def list_blocks(
    status: str | None = None,
    domain: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List blocks with optional status/domain filters."""
    q = select(Block).order_by(Block.start_time.desc())
    count_q = select(func.count(Block.id))

    if status:
        q = q.where(Block.status == status)
        count_q = count_q.where(Block.status == status)
    if domain:
        q = q.where(Block.domain == domain)
        count_q = count_q.where(Block.domain == domain)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(q.limit(limit).offset(offset))
    blocks = result.scalars().all()

    return BlockListResponse(
        blocks=[_to_response(b) for b in blocks],
        total=total,
    )


@router.get("/{block_id}", response_model=BlockResponse)
async def get_block(block_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single block by ID."""
    block = await _get_block_or_404(block_id, db)
    return _to_response(block)


@router.post("/{block_id}/finalize", response_model=BlockResponse, dependencies=[Depends(require_api_key)])
async def finalize_block(block_id: str, req: BlockFinalize, db: AsyncSession = Depends(get_db)):
    """Manually trigger finalization for a block."""
    block = await _get_block_or_404(block_id, db)

    if block.status != "open":
        raise HTTPException(400, f"Block already in status: {block.status}")

    new_status = await controller.process_block(db, block)
    if not new_status and req.force:
        # Force exhausted
        block.status = "exhausted"
        await controller._finalize_block(db, block)

    return _to_response(block)


@router.get("/{block_id}/artifacts")
async def get_block_artifacts(block_id: str, db: AsyncSession = Depends(get_db)):
    """Get sealed artifacts for a finalized block."""
    await _get_block_or_404(block_id, db)
    result = await db.execute(
        select(BlockArtifact).where(BlockArtifact.block_id == block_id)
    )
    artifacts = result.scalars().all()
    return [
        {
            "artifact_type": a.artifact_type,
            "artifact_json": a.artifact_json,
            "created_at": a.created_at.isoformat(),
        }
        for a in artifacts
    ]


@router.get("/{block_id}/anatomy")
async def get_block_anatomy(block_id: str, db: AsyncSession = Depends(get_db)):
    """Get the full anatomy of a sealed block — honey, jelly, propolis, convergence math."""
    from swarmchain.services.block_anatomy import BlockAnatomyService
    try:
        anatomy = await BlockAnatomyService.analyze(db, block_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return anatomy.to_dict()


async def _get_block_or_404(block_id: str, db: AsyncSession) -> Block:
    result = await db.execute(select(Block).where(Block.block_id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(404, f"Block {block_id} not found")
    return block


def _to_response(block: Block) -> BlockResponse:
    return BlockResponse(
        block_id=block.block_id,
        task_id=block.task_id,
        domain=block.domain,
        status=block.status,
        reward_pool=block.reward_pool,
        max_attempts=block.max_attempts,
        time_limit_sec=block.time_limit_sec,
        start_time=block.start_time,
        end_time=block.end_time,
        total_energy=block.total_energy,
        attempt_count=block.attempt_count,
        winning_attempt_id=block.winning_attempt_id,
        winning_node_id=block.winning_node_id,
        final_score=block.final_score,
        elimination_summary=block.elimination_summary,
        task_payload=block.task_payload,
        metadata=block.metadata_,
    )
