"""SwarmOS state management — file-based job persistence.

Each job gets a directory under /data2/swarmchain/jobs/{job_id}/ with:
  flightsheet.json, calibration.json, poj.json, epoch_progress.json, closing.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import config
from .models import (
    CalibrationReport,
    ClosingStatement,
    EpochProgress,
    FlightSheet,
    Permit,
    POJ,
)


def _jobs_dir() -> Path:
    d = config.JOBS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def job_dir(job_id: str) -> Path:
    d = _jobs_dir() / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_jobs() -> list[dict]:
    """List all jobs with basic status info."""
    jobs = []
    jdir = _jobs_dir()
    if not jdir.exists():
        return jobs
    for d in sorted(jdir.iterdir()):
        if not d.is_dir():
            continue
        info = {"job_id": d.name, "status": "created"}
        if (d / "closing.json").exists():
            info["status"] = "closed"
        elif (d / "epoch_progress.json").exists():
            info["status"] = "running"
        elif (d / "permit.json").exists():
            info["status"] = "permitted"
        elif (d / "poj.json").exists():
            poj = load_poj(d.name)
            info["status"] = "signed" if poj and poj.signed else "poj_ready"
        elif (d / "flightsheet.json").exists():
            fs = load_flightsheet(d.name)
            info["status"] = "locked" if fs and fs.locked else "drafted"
        # Add domain if available
        if (d / "poj.json").exists():
            poj = load_poj(d.name)
            if poj:
                info["domain"] = poj.domain
                info["pairs"] = poj.pair_count
                info["client"] = poj.client
        jobs.append(info)
    return jobs


# ── Save/Load helpers ──────────────────────────────────────

def _save(job_id: str, filename: str, model) -> Path:
    p = job_dir(job_id) / filename
    p.write_text(model.model_dump_json(indent=2))
    return p


def _load(job_id: str, filename: str, cls):
    p = job_dir(job_id) / filename
    if not p.exists():
        return None
    return cls.model_validate_json(p.read_text())


# Flight Sheet
def save_flightsheet(job_id: str, fs: FlightSheet) -> Path:
    return _save(job_id, "flightsheet.json", fs)

def load_flightsheet(job_id: str) -> Optional[FlightSheet]:
    return _load(job_id, "flightsheet.json", FlightSheet)


# Calibration
def save_calibration(job_id: str, report: CalibrationReport) -> Path:
    return _save(job_id, "calibration.json", report)

def load_calibration(job_id: str) -> Optional[CalibrationReport]:
    return _load(job_id, "calibration.json", CalibrationReport)


# POJ
def save_poj(job_id: str, poj: POJ) -> Path:
    return _save(job_id, "poj.json", poj)

def load_poj(job_id: str) -> Optional[POJ]:
    return _load(job_id, "poj.json", POJ)


# Epoch Progress
def save_progress(job_id: str, progress: EpochProgress) -> Path:
    return _save(job_id, "epoch_progress.json", progress)

def load_progress(job_id: str) -> Optional[EpochProgress]:
    return _load(job_id, "epoch_progress.json", EpochProgress)


# Permit
def save_permit(job_id: str, permit: Permit) -> Path:
    return _save(job_id, "permit.json", permit)

def load_permit(job_id: str) -> Optional[Permit]:
    return _load(job_id, "permit.json", Permit)


# Closing Statement
def save_closing(job_id: str, closing: ClosingStatement) -> Path:
    return _save(job_id, "closing.json", closing)

def load_closing(job_id: str) -> Optional[ClosingStatement]:
    return _load(job_id, "closing.json", ClosingStatement)
