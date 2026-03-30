"""SwarmChain ORM models — the data layer for the reasoning ledger."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Float, Integer, Boolean, DateTime, Text, ForeignKey, JSON, Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex[:16]


class Base(DeclarativeBase):
    pass


class Block(Base):
    """A reasoning task block — opened, worked, sealed."""
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=new_id)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, default="arc")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    reward_pool: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    time_limit_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_energy: Mapped[float] = mapped_column(Float, default=0.0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    winning_attempt_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    winning_node_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    elimination_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    task_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    attempts: Mapped[list["Attempt"]] = relationship(back_populates="block", cascade="all, delete-orphan")
    rewards: Mapped[list["Reward"]] = relationship(back_populates="block", cascade="all, delete-orphan")
    artifacts: Mapped[list["BlockArtifact"]] = relationship(back_populates="block", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_blocks_status", "status"),
        Index("ix_blocks_domain", "domain"),
    )


class Attempt(Base):
    """A single reasoning attempt submitted by a node."""
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=new_id)
    block_id: Mapped[str] = mapped_column(String(32), ForeignKey("blocks.block_id"), nullable=False)
    node_id: Mapped[str] = mapped_column(String(32), ForeignKey("nodes.node_id"), nullable=False)
    parent_attempt_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    method: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    strategy_family: Mapped[str] = mapped_column(String(64), nullable=False, default="random")
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    energy_cost: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    promoted: Mapped[bool] = mapped_column(Boolean, default=False)
    pruned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    block: Mapped["Block"] = relationship(back_populates="attempts")
    node: Mapped["Node"] = relationship(back_populates="attempts")

    __table_args__ = (
        Index("ix_attempts_block_id", "block_id"),
        Index("ix_attempts_node_id", "node_id"),
        Index("ix_attempts_score", "score"),
        Index("ix_attempts_block_score", "block_id", "score"),
    )


class Node(Base):
    """A compute node that participates in the swarm."""
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=new_id)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False, default="generic")
    hardware_class: Mapped[str] = mapped_column(String(32), nullable=False, default="cpu")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    reputation_score: Mapped[float] = mapped_column(Float, default=1.0)
    total_energy_used: Mapped[float] = mapped_column(Float, default=0.0)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0)
    total_solves: Mapped[int] = mapped_column(Integer, default=0)
    total_rewards: Mapped[float] = mapped_column(Float, default=0.0)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    attempts: Mapped[list["Attempt"]] = relationship(back_populates="node")

    __table_args__ = (
        Index("ix_nodes_node_type", "node_type"),
    )


class Reward(Base):
    """A reward payout for a node's contribution to a block."""
    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_id: Mapped[str] = mapped_column(String(32), ForeignKey("blocks.block_id"), nullable=False)
    node_id: Mapped[str] = mapped_column(String(32), ForeignKey("nodes.node_id"), nullable=False)
    reward_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reward_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_basis: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    block: Mapped["Block"] = relationship(back_populates="rewards")

    __table_args__ = (
        Index("ix_rewards_block_id", "block_id"),
        Index("ix_rewards_node_id", "node_id"),
    )


class LineageEdge(Base):
    """Parent-child link between attempts — traces the search tree."""
    __tablename__ = "lineage_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_id: Mapped[str] = mapped_column(String(32), ForeignKey("blocks.block_id"), nullable=False)
    parent_attempt_id: Mapped[str] = mapped_column(String(32), nullable=False)
    child_attempt_id: Mapped[str] = mapped_column(String(32), nullable=False)
    delta_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_lineage_block_id", "block_id"),
        Index("ix_lineage_parent", "parent_attempt_id"),
        Index("ix_lineage_child", "child_attempt_id"),
    )


class ValidatorDecision(Base):
    """Domain validator output — validators assist convergence, never override truth."""
    __tablename__ = "validator_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_id: Mapped[str] = mapped_column(String(32), ForeignKey("blocks.block_id"), nullable=False)
    attempt_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    validator_name: Mapped[str] = mapped_column(String(64), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    critique: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    repair_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    objective_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    objective_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_valdec_block_id", "block_id"),
        Index("ix_valdec_validator", "validator_name"),
    )


class DatasetSale(Base):
    """A dataset sale event — triggers payout distribution to contributors."""
    __tablename__ = "dataset_sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=new_id)
    block_id: Mapped[str] = mapped_column(String(32), ForeignKey("blocks.block_id"), nullable=False)
    buyer: Mapped[str] = mapped_column(String(128), nullable=False)
    sale_price: Mapped[float] = mapped_column(Float, nullable=False)
    platform_fee_pct: Mapped[float] = mapped_column(Float, default=0.10)
    platform_fee: Mapped[float] = mapped_column(Float, default=0.0)
    distributable: Mapped[float] = mapped_column(Float, default=0.0)
    payout_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payout_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_sales_block_id", "block_id"),
        Index("ix_sales_status", "status"),
    )


class BlockArtifact(Base):
    """Sealed artifact generated when a block reaches finality."""
    __tablename__ = "block_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_id: Mapped[str] = mapped_column(String(32), ForeignKey("blocks.block_id"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    block: Mapped["Block"] = relationship(back_populates="artifacts")

    __table_args__ = (
        Index("ix_artifacts_block_id", "block_id"),
    )
