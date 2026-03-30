"""Pydantic schemas for Node operations."""
from datetime import datetime
from pydantic import BaseModel


class NodeRegister(BaseModel):
    """Register a new compute node."""
    node_id: str | None = None
    node_type: str = "generic"
    hardware_class: str = "cpu"
    metadata: dict | None = None


class NodeResponse(BaseModel):
    """Full node representation."""
    node_id: str
    node_type: str
    hardware_class: str
    active: bool
    reputation_score: float
    total_energy_used: float
    total_attempts: int
    total_solves: int
    total_rewards: float
    registered_at: datetime
    metadata: dict | None

    model_config = {"from_attributes": True}


class NodeStats(BaseModel):
    """Aggregated node performance stats."""
    node_id: str
    total_attempts: int
    total_solves: int
    total_rewards: float
    total_energy_used: float
    avg_score: float
    efficiency: float
    blocks_participated: int
