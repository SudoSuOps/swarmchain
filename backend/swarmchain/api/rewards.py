"""Reward API — inspect reward distributions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.engine import get_db
from swarmchain.db.models import Block, Reward
from swarmchain.schemas.rewards import RewardResponse, RewardSummary
from swarmchain.config import get_settings

router = APIRouter()


@router.get("/blocks/{block_id}/rewards", response_model=RewardSummary)
async def get_block_rewards(block_id: str, db: AsyncSession = Depends(get_db)):
    """Get the full reward breakdown for a finalized block."""
    result = await db.execute(select(Block).where(Block.block_id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(404, f"Block {block_id} not found")

    result = await db.execute(
        select(Reward)
        .where(Reward.block_id == block_id)
        .order_by(Reward.reward_amount.desc())
    )
    rewards = result.scalars().all()

    s = get_settings()
    pool = block.reward_pool

    return RewardSummary(
        block_id=block_id,
        total_pool=pool,
        solver_pool=pool * s.solver_reward_pct,
        lineage_pool=pool * s.lineage_reward_pct,
        exploration_pool=pool * s.exploration_reward_pct,
        efficiency_pool=pool * s.efficiency_reward_pct,
        rewards=[
            RewardResponse(
                block_id=r.block_id,
                node_id=r.node_id,
                reward_type=r.reward_type,
                reward_amount=r.reward_amount,
                score_basis=r.score_basis,
                created_at=r.created_at,
            )
            for r in rewards
        ],
    )
