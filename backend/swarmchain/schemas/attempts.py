"""Pydantic schemas for Attempt operations."""
from datetime import datetime
from pydantic import BaseModel, Field


class AttemptSubmit(BaseModel):
    """Node submits an attempt against a block."""
    node_id: str
    block_id: str
    parent_attempt_id: str | None = None
    method: str = "unknown"
    strategy_family: str = "random"
    output_json: dict = Field(default_factory=dict)
    energy_cost: float = Field(default=1.0, ge=0.0, le=1_000_000)
    latency_ms: int = Field(default=0, ge=0)


class AttemptResponse(BaseModel):
    """Full attempt representation."""
    attempt_id: str
    block_id: str
    node_id: str
    parent_attempt_id: str | None
    method: str
    strategy_family: str
    output_json: dict
    score: float
    valid: bool
    energy_cost: float
    latency_ms: int
    promoted: bool
    pruned: bool
    created_at: datetime
    metadata: dict | None

    model_config = {"from_attributes": True}


class AttemptListResponse(BaseModel):
    attempts: list[AttemptResponse]
    total: int
