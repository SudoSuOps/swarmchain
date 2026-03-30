"""SwarmOS data models — the seven documents.

Every job flows through: Profile → FlightSheet → Calibration → POJ → Progress → Closing → Anchor.
These Pydantic models define the schema for each document. Once locked, they don't change.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, computed_field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    import uuid
    return uuid.uuid4().hex[:16]


# ── Hardware Profile (Document 1) ──────────────────────────


class GPUProfile(BaseModel):
    index: int
    name: str                           # "NVIDIA RTX PRO 6000"
    vram_total_gb: float
    vram_free_gb: float
    vram_used_gb: float
    power_limit_w: float
    power_draw_w: float                 # Current draw (idle or load)
    compute_capability: str = ""
    # Derived capacity
    model_slots_9b: int = 0             # How many 9B Q4 fit (6.2GB each)
    model_slots_4b: int = 0             # How many 4B Q4 fit (3.5GB each)


class CPUProfile(BaseModel):
    model: str                          # "Intel Xeon w9-3475X"
    cores: int
    threads: int
    amx_bf16: bool = False
    amx_int8: bool = False
    avx512: bool = False
    tdp_w: float = 0.0
    rapl_available: bool = False


class RemoteNode(BaseModel):
    hostname: str
    ip: str
    port: int
    status: str = "unknown"             # "healthy" | "unreachable" | "unknown"
    model: str = ""
    latency_ms: float = 0.0


class HardwareProfile(BaseModel):
    hostname: str = ""
    gpus: list[GPUProfile] = []
    cpu: CPUProfile = CPUProfile(model="unknown", cores=0, threads=0)
    ram_total_gb: float = 0.0
    ram_free_gb: float = 0.0
    storage_free_gb: float = 0.0
    remote_nodes: list[RemoteNode] = []
    profiled_at: datetime = Field(default_factory=_now)


# ── Flight Sheet (Document 2) ─────────────────────────────


class GPUAssignment(BaseModel):
    gpu_index: int
    card: str                           # "RTX PRO 6000"
    role: str                           # "judge" | "recorder"
    model_gguf: str                     # Path to GGUF
    model_type: str                     # "Qwen3.5-9B-Q4"
    instance_count: int
    vram_per_instance_gb: float
    vram_total_gb: float                # instance_count × vram_per_instance
    vram_percent: float                 # vram_total / gpu vram
    ports: list[int]                    # Allocated ports
    power_target_w: float               # 80% of TDP
    threads_per_instance: int = 4
    estimated_hashrate: float = 0.0     # verdicts/min or deeds/min


class CPUAssignment(BaseModel):
    role: str                           # "recorder" | "judge"
    model_gguf: str
    model_type: str
    instance_count: int
    threads_per_instance: int
    ports: list[int]
    estimated_hashrate: float = 0.0


class FlightSheetTotals(BaseModel):
    total_models: int = 0
    total_vram_used_gb: float = 0.0
    total_power_w: float = 0.0
    total_estimated_hashrate: float = 0.0  # deeds/min (bottleneck rate)
    judge_hashrate: float = 0.0
    recorder_hashrate: float = 0.0
    estimated_wall_hours: float = 0.0
    estimated_cost_to_mint: float = 0.0    # per deed
    estimated_total_cost: float = 0.0      # full epoch


class FlightSheet(BaseModel):
    sheet_id: str = Field(default_factory=_uuid)
    algo: str                           # "validate-finance"
    domain: str
    pair_count: int
    input_path: str = ""                # Path to input JSONL
    gpu_assignments: list[GPUAssignment] = []
    cpu_assignments: list[CPUAssignment] = []
    totals: FlightSheetTotals = FlightSheetTotals()
    locked: bool = False
    lock_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    locked_at: Optional[datetime] = None

    def lock(self) -> str:
        """Lock the flight sheet. Returns the SHA256 hash."""
        self.locked = True
        self.locked_at = _now()
        content = self.model_dump_json(exclude={"locked", "lock_hash", "locked_at"})
        self.lock_hash = hashlib.sha256(content.encode()).hexdigest()
        return self.lock_hash

    def verify(self) -> bool:
        """Verify the lock hash matches current content."""
        if not self.lock_hash:
            return False
        content = self.model_dump_json(exclude={"locked", "lock_hash", "locked_at"})
        return hashlib.sha256(content.encode()).hexdigest() == self.lock_hash


# ── Calibration Report (Document 3) ───────────────────────


class CalibrationReport(BaseModel):
    job_id: str
    flight_sheet_id: str
    sample_size: int = 50
    # Measured throughput
    judge_latency_mean_ms: float = 0.0
    judge_latency_p95_ms: float = 0.0
    recorder_latency_mean_ms: float = 0.0
    recorder_latency_p95_ms: float = 0.0
    measured_judge_hashrate: float = 0.0    # verdicts/min
    measured_recorder_hashrate: float = 0.0 # deeds/min
    # Measured power
    gpu_power_mean_w: dict[int, float] = {}  # gpu_index → watts
    cpu_load_mean: float = 0.0
    # Measured quality
    sample_honey_rate: float = 0.0
    sample_honey: int = 0
    sample_jelly: int = 0
    sample_propolis: int = 0
    # Comparison to flight sheet estimates
    hashrate_variance_pct: float = 0.0
    power_variance_pct: float = 0.0
    # Warnings
    warnings: list[str] = []
    calibrated_at: datetime = Field(default_factory=_now)


# ── POJ — Proof of Job (Document 4) ───────────────────────


class FeeSchedule(BaseModel):
    title_premium_per_deed: float = 0.05    # $/deed (Full Title + Hedera tier)
    doc_prep_fee: float = 50.0
    flight_sheet_setup: float = 100.0
    recording_fee: float = 25.0
    inspection_report: float = 25.0

    @computed_field
    @property
    def fixed_fees_total(self) -> float:
        return self.doc_prep_fee + self.flight_sheet_setup + self.recording_fee + self.inspection_report


class EstimatedCost(BaseModel):
    electricity: float = 0.0
    hardware_depreciation: float = 0.0
    chain_overhead: float = 0.0
    total_production: float = 0.0       # Sum of above
    per_deed: float = 0.0


class POJ(BaseModel):
    """Proof of Job — the pre-closing statement. Must be signed before epoch launches."""
    job_id: str = Field(default_factory=_uuid)
    client: str = ""
    domain: str = ""
    pair_count: int = 0
    flight_sheet_id: str = ""
    flight_sheet_hash: str = ""         # Tamper-evident link to locked sheet

    # Fee schedule
    fee_schedule: FeeSchedule = FeeSchedule()
    estimated_title_premium: float = 0.0    # pair_count × rate
    estimated_total_closing: float = 0.0    # premium + fixed fees

    # Estimates
    estimated_cost: EstimatedCost = EstimatedCost()
    estimated_timeline_hours: float = 0.0
    estimated_honey_rate: float = 0.0
    estimated_hashrate: float = 0.0

    # Deliverables
    deliverables: list[str] = Field(default_factory=lambda: [
        "honey.jsonl", "jelly.jsonl", "propolis.jsonl",
        "receipts.jsonl", "epoch_report.json", "closing.json",
    ])
    terms_version: str = "v1.0"

    # Sign-off
    signed: bool = False
    signed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_now)

    def sign(self):
        self.signed = True
        self.signed_at = _now()


# ── Epoch Progress (Document 5) ───────────────────────────


class EpochProgress(BaseModel):
    job_id: str
    domain: str = ""
    pair_count: int = 0
    source: str = "swarmos"             # "swarmos" | "manual" | "adopted"
    started_at: Optional[datetime] = None
    status: str = "pending"             # "pending" | "judging" | "recording" | "complete" | "interrupted"
    # Judge phase
    judged: int = 0
    judge_rate: Optional[float] = None  # verdicts/min — None = not captured
    # Record phase
    recorded: int = 0
    recorder_rate: Optional[float] = None  # deeds/min — None = not captured
    pending_in_bin: int = 0
    # Classification
    honey: int = 0
    jelly: int = 0
    propolis: int = 0
    skipped: int = 0
    # Timing
    elapsed_sec: Optional[float] = None  # None = not captured (manual run)
    eta_sec: Optional[float] = None
    # Power
    gpu_power: dict[int, float] = {}    # gpu_index → watts
    cpu_load: Optional[float] = None
    total_energy_wh: Optional[float] = None
    updated_at: datetime = Field(default_factory=_now)


# ── Closing Statement (Document 6) ────────────────────────


class DeliverableFile(BaseModel):
    path: str
    lines: int = 0
    size_bytes: int = 0
    sha256: str = ""


class VarianceReport(BaseModel):
    cost_estimated: float = 0.0
    cost_actual: float = 0.0
    cost_variance_pct: float = 0.0
    time_estimated_hours: float = 0.0
    time_actual_hours: float = 0.0
    time_variance_pct: float = 0.0
    honey_rate_estimated: float = 0.0
    honey_rate_actual: float = 0.0
    honey_rate_variance_pct: float = 0.0
    hashrate_estimated: float = 0.0
    hashrate_actual: float = 0.0
    hashrate_variance_pct: float = 0.0


class DataSource(BaseModel):
    """Tracks where each field's value came from — honest provenance."""
    classification: str = "observed"    # "observed" = from output files
    wall_time: str = "unavailable"      # "observed" | "derived" | "estimated" | "unavailable"
    hashrate: str = "unavailable"
    energy: str = "unavailable"
    cost: str = "derived"               # "derived" = calculated from available data
    honey_rate: str = "observed"
    fees: str = "derived"


class ClosingStatement(BaseModel):
    """The post-epoch delivery document. The HUD-1 / Closing Disclosure."""
    job_id: str
    poj_id: str = ""
    client: str = ""
    domain: str = ""
    epoch_source: str = "swarmos"       # "swarmos" | "manual" | "adopted"

    # Actuals — None means "not captured", distinct from 0
    actual_pairs_processed: int = 0
    actual_honey: int = 0
    actual_jelly: int = 0
    actual_propolis: int = 0
    actual_honey_rate: float = 0.0
    actual_wall_time_hours: Optional[float] = None
    actual_hashrate: Optional[float] = None     # deeds/min
    actual_energy_wh: Optional[float] = None
    actual_cost_to_mint: Optional[float] = None # per deed
    actual_total_cost: Optional[float] = None

    # Fees charged
    title_premium_charged: float = 0.0
    fixed_fees: float = 0.0
    total_closing_cost: float = 0.0
    net_margin: Optional[float] = None
    margin_pct: Optional[float] = None

    # Variance
    variance: VarianceReport = VarianceReport()
    variance_reasons: list[str] = []    # Human-readable explanations

    # Data source labels — what's observed vs derived vs unavailable
    data_sources: DataSource = DataSource()

    # Deliverables
    deliverable_manifest: list[DeliverableFile] = []

    # Proof
    block_count: int = 0
    hedera_anchors: list[str] = []
    merkle_root: str = ""

    sealed_at: datetime = Field(default_factory=_now)


# ── Permit (Document 7) ──────────────────────────────────


class Permit(BaseModel):
    """Build permit — frozen authorization to run an epoch.

    CRE pattern: no permit, no build. The permit freezes all critical
    settings at approval time. If the flight sheet changes after permit
    issuance, the hash won't match and the permit is invalid.
    """
    permit_id: str
    job_id: str
    flight_sheet_id: str
    flight_sheet_hash: str

    # Approved judge settings (frozen at permit time)
    judge_model: str
    judge_gguf: str
    judge_input_window_question: int
    judge_input_window_answer: int
    judge_max_tokens: int
    judge_temperature: float

    # Approved recorder settings (frozen at permit time)
    recorder_model: str
    recorder_gguf: str
    recorder_max_tokens: int
    recorder_no_think: bool

    # Scoring thresholds (frozen at permit time)
    scoring_thresholds: dict  # {"royal-jelly": 0.75, "honey": 0.50, "propolis": 0.0}
    model_policy: str         # "base_only"

    status: str = "issued"
    issued_at: datetime = Field(default_factory=_now)
