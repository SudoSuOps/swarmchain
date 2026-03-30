"""SwarmAlgorithm data models — the unified operating layer.

If it's not on SwarmChain, it's not real.
Every action produces a receipt. Every receipt feeds the algorithm.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    String, Float, Integer, Boolean, DateTime, Text, ForeignKey, JSON, Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from swarmchain.db.models import Base, utcnow, new_id


class SwarmEvent(Base):
    """Universal event log — every action in the swarm produces an immutable receipt.

    Event types:
    - model.online / model.offline / model.inference
    - cook.started / cook.pair / cook.completed
    - block.opened / block.attempt / block.solved / block.sealed
    - sale.completed
    - node.registered / node.heartbeat
    - signal.received
    - training.started / training.completed
    """
    __tablename__ = "swarm_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=new_id)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    block_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    energy_cost: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_events_type", "event_type"),
        Index("ix_events_source", "source_node"),
        Index("ix_events_block", "block_id"),
        Index("ix_events_timestamp", "timestamp"),
        Index("ix_events_domain", "domain"),
    )


class BlockCost(Base):
    """Unified P&L per block — the cost-to-mint receipt.

    Every sealed block has a cost. Cost = electricity + API + depreciation + overhead.
    Revenue = dataset sale price (if sold). Margin = revenue - cost.
    """
    __tablename__ = "block_costs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_id: Mapped[str] = mapped_column(String(32), ForeignKey("blocks.block_id"), unique=True, nullable=False)

    # Cost side
    electricity_cost: Mapped[float] = mapped_column(Float, default=0.0)
    api_cost: Mapped[float] = mapped_column(Float, default=0.0)
    depreciation_cost: Mapped[float] = mapped_column(Float, default=0.0)
    validation_cost: Mapped[float] = mapped_column(Float, default=0.0)
    orchestration_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)

    # Yield side
    honey_count: Mapped[int] = mapped_column(Integer, default=0)
    jelly_count: Mapped[int] = mapped_column(Integer, default=0)
    propolis_count: Mapped[int] = mapped_column(Integer, default=0)
    cost_per_honey: Mapped[float] = mapped_column(Float, default=0.0)
    cost_per_attempt: Mapped[float] = mapped_column(Float, default=0.0)

    # Revenue side
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    margin: Mapped[float] = mapped_column(Float, default=0.0)
    roi_pct: Mapped[float] = mapped_column(Float, default=0.0)

    # Time metrics
    wall_time_sec: Mapped[float] = mapped_column(Float, default=0.0)
    compute_time_sec: Mapped[float] = mapped_column(Float, default=0.0)

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_blockcost_block", "block_id"),
    )


class NodeCostProfile(Base):
    """Per-node operating costs — the economics of running a swarm node.

    Tracks the real cost of operating hardware so we can compute
    cost-to-mint accurately and determine node profitability.
    """
    __tablename__ = "node_cost_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(32), ForeignKey("nodes.node_id"), unique=True, nullable=False)

    # Hardware
    gpu_model: Mapped[str] = mapped_column(String(64), default="none")
    gpu_vram_gb: Mapped[int] = mapped_column(Integer, default=0)
    gpu_purchase_price: Mapped[float] = mapped_column(Float, default=0.0)
    gpu_depreciation_years: Mapped[int] = mapped_column(Integer, default=5)

    # Operating costs
    electricity_rate: Mapped[float] = mapped_column(Float, default=0.10)  # $/kWh
    power_draw_watts: Mapped[float] = mapped_column(Float, default=100.0)
    monthly_electricity: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_internet: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_other: Mapped[float] = mapped_column(Float, default=0.0)

    # Computed
    hourly_depreciation: Mapped[float] = mapped_column(Float, default=0.0)
    hourly_opex: Mapped[float] = mapped_column(Float, default=0.0)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CookJob(Base):
    """Tracks cooking jobs outside of blocks — OpenRouter cooks, batch cooks, etc.

    If it's not on SwarmChain, it's not real. Cooks produce pairs.
    Pairs have quality (honey/jelly/propolis). Quality has cost.
    """
    __tablename__ = "cook_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=new_id)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(128), default="local")  # openrouter, local, etc.

    # Yield
    pairs_total: Mapped[int] = mapped_column(Integer, default=0)
    pairs_honey: Mapped[int] = mapped_column(Integer, default=0)
    pairs_jelly: Mapped[int] = mapped_column(Integer, default=0)
    pairs_propolis: Mapped[int] = mapped_column(Integer, default=0)

    # Cost
    cost_api: Mapped[float] = mapped_column(Float, default=0.0)
    cost_electricity: Mapped[float] = mapped_column(Float, default=0.0)
    cost_total: Mapped[float] = mapped_column(Float, default=0.0)
    cost_per_honey: Mapped[float] = mapped_column(Float, default=0.0)

    # Time
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    __table_args__ = (
        Index("ix_cookjobs_domain", "domain"),
        Index("ix_cookjobs_source", "source"),
    )


class TrainingRun(Base):
    """Tracks model training — the recycling loop.

    Sealed blocks produce training data. Training produces models.
    Models join the swarm. The swarm gets smarter. Track the proof.
    """
    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=new_id)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_model: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    # Input
    input_block_ids: Mapped[list] = mapped_column(JSON, default=list)
    input_pair_count: Mapped[int] = mapped_column(Integer, default=0)
    input_honey_count: Mapped[int] = mapped_column(Integer, default=0)
    input_propolis_count: Mapped[int] = mapped_column(Integer, default=0)

    # Cost
    gpu_hours: Mapped[float] = mapped_column(Float, default=0.0)
    cost_electricity: Mapped[float] = mapped_column(Float, default=0.0)
    cost_total: Mapped[float] = mapped_column(Float, default=0.0)

    # Results
    eval_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    eval_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Deployment
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deployed_to_nodes: Mapped[list] = mapped_column(JSON, default=list)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_training_model", "model_name"),
    )


class ConvergenceMetric(Base):
    """Rolling window convergence stats — the proof the swarm is getting smarter.

    Computed after each sealed block. If cost-per-honey trends DOWN,
    the SwarmAlgorithm is working. That curve is the defensible moat.
    """
    __tablename__ = "convergence_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    window_start: Mapped[int] = mapped_column(Integer, nullable=False)  # block sequence number
    window_end: Mapped[int] = mapped_column(Integer, nullable=False)
    window_size: Mapped[int] = mapped_column(Integer, nullable=False)
    domain: Mapped[str] = mapped_column(String(64), default="all")

    # The metrics
    blocks_sealed: Mapped[int] = mapped_column(Integer, default=0)
    blocks_solved: Mapped[int] = mapped_column(Integer, default=0)
    solve_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_attempts_per_solve: Mapped[float] = mapped_column(Float, default=0.0)
    avg_cost_per_honey: Mapped[float] = mapped_column(Float, default=0.0)
    avg_time_to_solve_sec: Mapped[float] = mapped_column(Float, default=0.0)
    avg_energy_per_honey: Mapped[float] = mapped_column(Float, default=0.0)
    strategy_hit_rate: Mapped[float] = mapped_column(Float, default=0.0)
    propolis_ratio: Mapped[float] = mapped_column(Float, default=0.0)

    # Delta from previous window (the improvement signal)
    delta_attempts_per_solve: Mapped[float] = mapped_column(Float, default=0.0)
    delta_cost_per_honey: Mapped[float] = mapped_column(Float, default=0.0)

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_convergence_window", "window_end"),
        Index("ix_convergence_domain", "domain"),
    )


class Epoch(Base):
    """A sealed manufacturing epoch — a complete mining shift with full receipts."""
    __tablename__ = "epochs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    epoch_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(64), nullable=False, default="Tier 1 Deterministic")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    block_range_start: Mapped[int] = mapped_column(Integer, nullable=False)
    block_range_end: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Yield counts
    honey_count: Mapped[int] = mapped_column(Integer, default=0)
    jelly_count: Mapped[int] = mapped_column(Integer, default=0)
    propolis_count: Mapped[int] = mapped_column(Integer, default=0)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0)
    total_energy: Mapped[float] = mapped_column(Float, default=0.0)
    total_blocks: Mapped[int] = mapped_column(Integer, default=0)

    # Economics
    cost_per_honey: Mapped[float] = mapped_column(Float, default=0.0)
    attempts_per_honey: Mapped[float] = mapped_column(Float, default=0.0)
    energy_per_honey: Mapped[float] = mapped_column(Float, default=0.0)
    convergence_delta: Mapped[float] = mapped_column(Float, default=0.0)

    # Receipts
    manifest_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    silicon_ladder: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    __table_args__ = (
        Index("ix_epochs_epoch_id", "epoch_id"),
        Index("ix_epochs_status", "status"),
    )


class EpochArtifact(Base):
    """Individual yield item from an epoch — honey, jelly, or propolis."""
    __tablename__ = "epoch_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    epoch_id: Mapped[str] = mapped_column(String(32), ForeignKey("epochs.epoch_id"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)  # honey | jelly | propolis
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    transform_type: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    node_id: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    energy_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    block_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempt_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    storage_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_epochart_epoch_id", "epoch_id"),
        Index("ix_epochart_type", "artifact_type"),
        Index("ix_epochart_model", "model_name"),
    )
