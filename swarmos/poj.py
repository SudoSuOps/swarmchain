"""SwarmOS Proof of Job — the pre-closing statement.

Generated BEFORE the epoch launches. Contains:
- Hardware config (from flight sheet)
- Estimated cost breakdown
- Estimated total closing cost (title premium + fixed fees)
- Estimated timeline and honey rate
- Deliverables list

This is what the client signs off on before launch.
Title companies provide pre-closing statements. Banks provide Loan Estimates.
SwarmOS provides Proof of Job.
"""
from __future__ import annotations

from . import config
from .models import EstimatedCost, FeeSchedule, FlightSheet, POJ, CalibrationReport
from . import state


def generate_poj(
    job_id: str,
    client: str,
    flight_sheet: FlightSheet,
    calibration: CalibrationReport | None = None,
    tier: str = "full",
) -> POJ:
    """Generate a Proof of Job from a locked flight sheet."""
    if not flight_sheet.locked:
        raise ValueError("Flight sheet must be locked before generating POJ")

    # Select fee tier
    tier_rates = {
        "floor": config.FEE_TIER_FLOOR,
        "standard": config.FEE_TIER_STANDARD,
        "full": config.FEE_TIER_FULL,
        "enterprise": config.FEE_TIER_ENTERPRISE,
    }
    premium_rate = tier_rates.get(tier, config.FEE_TIER_FULL)

    fee_schedule = FeeSchedule(
        title_premium_per_deed=premium_rate,
        model_prep_fee=config.FEE_MODEL_PREP,
        doc_prep_fee=config.FEE_DOC_PREP,
        flight_sheet_setup=config.FEE_FLIGHT_SHEET,
        recording_fee=config.FEE_RECORDING,
        inspection_report=config.FEE_INSPECTION,
        cooks_included=2,
    )

    # Estimated title premium
    title_premium = flight_sheet.pair_count * premium_rate
    total_closing = title_premium + fee_schedule.fixed_fees_total

    # Use calibration data if available, otherwise flight sheet estimates
    if calibration and calibration.measured_recorder_hashrate > 0:
        hashrate = calibration.measured_recorder_hashrate
        honey_rate = calibration.sample_honey_rate
    else:
        hashrate = flight_sheet.totals.total_estimated_hashrate
        honey_rate = 0.20  # Conservative default

    timeline_hours = flight_sheet.totals.estimated_wall_hours
    if calibration and hashrate > 0:
        timeline_hours = flight_sheet.pair_count / (hashrate * 60)

    poj = POJ(
        job_id=job_id,
        client=client,
        domain=flight_sheet.domain,
        pair_count=flight_sheet.pair_count,
        flight_sheet_id=flight_sheet.sheet_id,
        flight_sheet_hash=flight_sheet.lock_hash or "",
        fee_schedule=fee_schedule,
        estimated_title_premium=round(title_premium, 2),
        estimated_total_closing=round(total_closing, 2),
        estimated_cost=EstimatedCost(
            electricity=flight_sheet.totals.estimated_total_cost * 0.08,  # ~8% is electricity
            hardware_depreciation=flight_sheet.totals.estimated_total_cost * 0.90,
            chain_overhead=flight_sheet.totals.estimated_total_cost * 0.02,
            total_production=flight_sheet.totals.estimated_total_cost,
            per_deed=flight_sheet.totals.estimated_cost_to_mint,
        ),
        estimated_timeline_hours=round(timeline_hours, 2),
        estimated_honey_rate=round(honey_rate, 4),
        estimated_hashrate=round(hashrate, 1),
    )

    return poj


def format_poj(poj: POJ) -> str:
    """Human-readable POJ output — the pre-closing statement."""
    lines = [
        "┌─────────────────────────────────────────────────┐",
        "│          PROOF OF JOB — PRE-CLOSING              │",
        "└─────────────────────────────────────────────────┘",
        "",
        f"  Job ID:      {poj.job_id}",
        f"  Client:      {poj.client}",
        f"  Domain:      {poj.domain}",
        f"  Pairs:       {poj.pair_count:,}",
        f"  Flight Sheet: {poj.flight_sheet_id} ({poj.flight_sheet_hash[:12]}...)",
        "",
        "  FEE SCHEDULE:",
        f"    Title premium:    {poj.pair_count:,} × ${poj.fee_schedule.title_premium_per_deed:.3f} = ${poj.estimated_title_premium:,.2f}",
        f"    Model prep:       ${poj.fee_schedule.model_prep_fee:.2f}",
        f"    Doc prep:         ${poj.fee_schedule.doc_prep_fee:.2f}",
        f"    Flight sheet:     ${poj.fee_schedule.flight_sheet_setup:.2f}",
        f"    Recording fee:    ${poj.fee_schedule.recording_fee:.2f}",
        f"    Inspection:       ${poj.fee_schedule.inspection_report:.2f}",
        "    ─────────────────────────────────────",
        f"    ESTIMATED TOTAL:  ${poj.estimated_total_closing:,.2f}",
        "",
        "  SCOPE:",
        f"    Cooks included:   {poj.fee_schedule.cooks_included} (Cook 1: discovery · Cook 2: validation)",
        f"    Timeline:         {poj.estimated_timeline_hours:.1f} hours per cook",
        f"    Hashrate:         {poj.estimated_hashrate:.1f} deeds/min",
        "",
        "  DELIVERABLES:",
    ]
    for d in poj.deliverables:
        lines.append(f"    - {d}")

    lines.extend([
        "",
        f"  Terms: {poj.terms_version}",
        "",
    ])

    if poj.signed:
        lines.append(f"  STATUS: SIGNED ({poj.signed_at.isoformat() if poj.signed_at else ''})")
    else:
        lines.append("  STATUS: AWAITING SIGNATURE")
        lines.append("  Run: swarmos poj sign <job_id> to approve")

    return "\n".join(lines)
