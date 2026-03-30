"""Pydantic schemas for Reward operations."""
from datetime import datetime
from pydantic import BaseModel


class RewardResponse(BaseModel):
    """Individual reward payout."""
    block_id: str
    node_id: str
    reward_type: str
    reward_amount: float
    score_basis: float
    created_at: datetime

    model_config = {"from_attributes": True}


class RewardSummary(BaseModel):
    """Reward breakdown for a block."""
    block_id: str
    total_pool: float
    solver_pool: float
    lineage_pool: float
    exploration_pool: float
    efficiency_pool: float
    rewards: list[RewardResponse]
