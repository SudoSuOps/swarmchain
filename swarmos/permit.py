"""SwarmOS Permit Gate — the build authorization system.

CRE pattern: Builder submits plans (flight sheet) -> Plan review (HTML inspection)
-> Permit issued -> Build authorized -> Title company can close.

No permit, no epoch. The permit freezes all critical settings at approval time.
If the flight sheet changes after permit issuance, the permit is invalid.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config, state
from .algos import get as get_algo, AlgoConfig
from .models import FlightSheet, Permit, _uuid, _now


def _compute_flight_sheet_hash(fs: FlightSheet) -> str:
    """Compute the canonical hash of a flight sheet for permit binding."""
    content = fs.model_dump_json(exclude={"locked", "lock_hash", "locked_at"})
    return hashlib.sha256(content.encode()).hexdigest()


def issue_permit(job_id: str) -> Permit:
    """Issue a build permit for a job after the operator has reviewed the flight sheet.

    Reads the flight sheet and algo config, freezes all critical judge/recorder
    settings into the permit, and saves to jobs/{job_id}/permit.json.

    Raises ValueError if preconditions are not met.
    """
    fs = state.load_flightsheet(job_id)
    if not fs:
        raise ValueError(f"No flight sheet found for job {job_id}")
    if not fs.locked:
        raise ValueError(
            f"Flight sheet not locked for job {job_id}. "
            "Lock it first: swarmos lock <job_id>"
        )

    # Load algo config for the frozen settings
    algo = get_algo(fs.algo)
    if algo is None:
        algo = AlgoConfig(name=fs.algo, domain=fs.domain, description=f"Custom: {fs.domain}")

    # Compute the flight sheet hash for tamper detection
    fs_hash = _compute_flight_sheet_hash(fs)

    # Input windows — must match judge_epoch2.py settings
    judge_input_window_question = 2000   # chars — covers 100% of grants prompts
    judge_input_window_answer = 14000    # chars — covers p95 of grants answers (13,473)

    permit = Permit(
        permit_id=_uuid(),
        job_id=job_id,
        flight_sheet_id=fs.sheet_id,
        flight_sheet_hash=fs_hash,
        # Judge settings frozen at permit time
        judge_model=algo.judge_model,
        judge_gguf=algo.judge_gguf,
        judge_input_window_question=judge_input_window_question,
        judge_input_window_answer=judge_input_window_answer,
        judge_max_tokens=algo.judge_max_tokens,
        judge_temperature=algo.judge_temperature,
        # Recorder settings frozen at permit time
        recorder_model=algo.recorder_model,
        recorder_gguf=algo.recorder_gguf,
        recorder_max_tokens=algo.recorder_max_tokens,
        recorder_no_think=True,   # /no_think is always enabled for recorder
        # Scoring thresholds frozen at permit time
        scoring_thresholds={
            "royal-jelly": 0.75,
            "honey": 0.50,
            "propolis": 0.0,
        },
        model_policy="base_only",
        status="issued",
        issued_at=_now(),
    )

    state.save_permit(job_id, permit)
    return permit


def verify_permit(job_id: str) -> tuple[bool, str]:
    """Verify that a permit exists and its flight sheet hash still matches.

    Returns (is_valid, reason).
    """
    permit = state.load_permit(job_id)
    if not permit:
        return False, "No permit issued. Review the flight sheet and issue a permit first."

    fs = state.load_flightsheet(job_id)
    if not fs:
        return False, "Flight sheet missing. Cannot verify permit."

    if not fs.locked:
        return False, "Flight sheet is no longer locked. Permit is invalid."

    current_hash = _compute_flight_sheet_hash(fs)
    if current_hash != permit.flight_sheet_hash:
        return False, (
            "Flight sheet has changed since permit was issued. "
            f"Permit hash: {permit.flight_sheet_hash[:16]}... "
            f"Current hash: {current_hash[:16]}... "
            "Issue a new permit after reviewing the updated flight sheet."
        )

    if permit.status != "issued":
        return False, f"Permit status is '{permit.status}', not 'issued'."

    return True, "Permit valid. Build authorized."


def format_permit(permit: Permit) -> str:
    """Human-readable permit output."""
    lines = [
        "=" * 60,
        "BUILD PERMIT",
        "=" * 60,
        "",
        f"  Permit ID:           {permit.permit_id}",
        f"  Job ID:              {permit.job_id}",
        f"  Status:              {permit.status.upper()}",
        f"  Issued:              {permit.issued_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        f"  Flight Sheet ID:     {permit.flight_sheet_id}",
        f"  Flight Sheet Hash:   {permit.flight_sheet_hash[:32]}...",
        "",
        "  FROZEN JUDGE SETTINGS:",
        f"    Model:             {permit.judge_model}",
        f"    GGUF:              {permit.judge_gguf}",
        f"    Temperature:       {permit.judge_temperature}",
        f"    Max Tokens:        {permit.judge_max_tokens}",
        f"    Input Window (Q):  {permit.judge_input_window_question} chars",
        f"    Input Window (A):  {permit.judge_input_window_answer} chars",
        "",
        "  FROZEN RECORDER SETTINGS:",
        f"    Model:             {permit.recorder_model}",
        f"    GGUF:              {permit.recorder_gguf}",
        f"    Max Tokens:        {permit.recorder_max_tokens}",
        f"    /no_think:         {'ENABLED' if permit.recorder_no_think else 'DISABLED'}",
        "",
        "  SCORING THRESHOLDS:",
        f"    Royal Jelly:       >= {permit.scoring_thresholds.get('royal-jelly', 0.75)}",
        f"    Honey:             >= {permit.scoring_thresholds.get('honey', 0.50)}",
        f"    Wax:               < {permit.scoring_thresholds.get('honey', 0.50)}",
        "",
        f"  Model Policy:        {permit.model_policy.upper().replace('_', ' ')}",
        "",
        "=" * 60,
    ]
    return "\n".join(lines)
