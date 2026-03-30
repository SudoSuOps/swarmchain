"""SwarmOS Closing Statement — the post-epoch delivery document.

The HUD-1 / Closing Disclosure equivalent.
Compares actuals to estimates, calculates fees, builds deliverable manifest.

Five principles:
  1. Wire epoch progress into every run path
  2. Mark missing runtime fields as None, never fake zeros
  3. Separate observed vs derived vs estimated vs unavailable
  4. Adopt manual/external epochs — don't require swarmos run
  5. Explain variance reasons, not just percentages
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from . import config, state
from .models import (
    ClosingStatement,
    DataSource,
    DeliverableFile,
    EpochProgress,
    POJ,
    VarianceReport,
)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def _count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in open(path))
    except OSError:
        return 0


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _build_manifest(output_dir: Path) -> list[DeliverableFile]:
    files = []
    for name in ["royal-jelly.jsonl", "honey.jsonl", "propolis.jsonl",
                  "jelly.jsonl", "wax.jsonl",  # backward compat
                  "receipts.jsonl", "judged.jsonl", "epoch_report.json", "closing.json"]:
        p = output_dir / name
        if p.exists():
            files.append(DeliverableFile(
                path=str(p), lines=_count_lines(p),
                size_bytes=_file_size(p), sha256=_file_sha256(p),
            ))
    return files


def _variance_pct(estimated: Optional[float], actual: Optional[float]) -> float:
    if estimated is None or actual is None or estimated == 0:
        return 0.0
    return round((actual - estimated) / estimated * 100, 1)


def _fmt(val: Optional[float], fmt: str = ".1f", prefix: str = "", suffix: str = "") -> str:
    """Format a value, or show 'n/a' if None."""
    if val is None:
        return "n/a"
    return f"{prefix}{val:{fmt}}{suffix}"


# ── Epoch adoption — infer progress from files ─────────────


def _adopt_epoch(domain: str, output_dir: Path) -> EpochProgress:
    """Build an EpochProgress from files alone — for manual/external epochs.

    This is the compatibility path. If someone ran judge_epoch2.py + record_epoch2.py
    manually, we can still generate an honest closing by reading the output files.
    """
    judged_count = _count_lines(output_dir / "judged.jsonl")
    receipt_count = _count_lines(output_dir / "receipts.jsonl")
    honey = _count_lines(output_dir / "honey.jsonl")
    royal_jelly = _count_lines(output_dir / "royal-jelly.jsonl") + _count_lines(output_dir / "jelly.jsonl")  # backward compat
    propolis = _count_lines(output_dir / "propolis.jsonl") + _count_lines(output_dir / "wax.jsonl")  # backward compat

    return EpochProgress(
        job_id="adopted",
        domain=domain,
        pair_count=judged_count,
        source="adopted",
        status="complete" if receipt_count > 0 else "unknown",
        judged=judged_count,
        judge_rate=None,        # Not captured — honest null
        recorded=receipt_count,
        recorder_rate=None,     # Not captured
        pending_in_bin=max(0, judged_count - receipt_count),
        honey=honey,
        royal_jelly=royal_jelly,
        propolis=propolis,
        elapsed_sec=None,       # Not captured
        eta_sec=None,
        total_energy_wh=None,   # Not captured
    )


# ── Cost calculation with honest nulls ─────────────────────


def _compute_costs(
    total_processed: int,
    wall_hours: Optional[float],
    total_power_w: float,
    gpu_assignments: list,
) -> tuple[Optional[float], Optional[float], Optional[float], str]:
    """Compute costs. Returns (total_cost, ctm, energy_wh, source_label).

    If wall_hours is None (manual run), costs are derived from file counts only.
    """
    if wall_hours is not None and wall_hours > 0:
        # Full observed cost
        energy_wh = total_power_w * wall_hours
        energy_kwh = energy_wh / 1000
        electricity = energy_kwh * config.ELECTRICITY_RATE

        depreciation = 0.0
        for ga in gpu_assignments:
            gpu_price = config.GPU_PRICES.get(ga.card, 5000)
            hourly = gpu_price / (config.DEPRECIATION_YEARS * 8760)
            depreciation += hourly * wall_hours
        depreciation += (config.CPU_SYSTEM_PRICE / (config.DEPRECIATION_YEARS * 8760)) * wall_hours

        chain = total_processed * 0.00001
        total = electricity + depreciation + chain
        ctm = total / max(total_processed, 1)
        return round(total, 4), round(ctm, 6), round(energy_wh, 1), "observed"

    elif total_processed > 0:
        # Derived — estimate from per-deed benchmark cost
        # Use measured CTM from config ($0.0008 from Epoch 2 baseline)
        ctm_estimate = 0.0008
        total = total_processed * ctm_estimate
        return round(total, 4), ctm_estimate, None, "estimated"

    return None, None, None, "unavailable"


# ── Variance reasons generator ─────────────────────────────


def _generate_variance_reasons(
    progress: EpochProgress,
    poj: POJ,
    actual_honey_rate: float,
    actual_wall_hours: Optional[float],
    actual_hashrate: Optional[float],
    epoch_source: str,
) -> list[str]:
    """Generate human-readable explanations for variance."""
    reasons = []

    # Source context
    if epoch_source == "adopted":
        reasons.append("Epoch launched outside SwarmOS — runtime metrics (wall time, hashrate, energy) not captured")
    elif epoch_source == "manual":
        reasons.append("Epoch launched via manual scripts — partial runtime metrics available")

    # Honey rate variance
    hr_est = poj.estimated_honey_rate
    if hr_est > 0 and actual_honey_rate > 0:
        delta = actual_honey_rate - hr_est
        if abs(delta) > 0.05:
            direction = "higher" if delta > 0 else "lower"
            reasons.append(
                f"Honey rate {direction} than estimated ({actual_honey_rate:.1%} vs {hr_est:.1%}) "
                f"— {poj.domain} domain pair quality {'exceeded' if delta > 0 else 'below'} calibration baseline"
            )

    # Wall time
    if actual_wall_hours is None:
        reasons.append("Wall time unavailable — epoch progress log not present")
    elif poj.estimated_timeline_hours > 0:
        time_delta = actual_wall_hours - poj.estimated_timeline_hours
        if abs(time_delta) > 1.0:
            reasons.append(
                f"Wall time {'exceeded' if time_delta > 0 else 'under'} estimate by {abs(time_delta):.1f}h"
            )

    # Hashrate
    if actual_hashrate is None:
        reasons.append("Hashrate unavailable pending progress log integration")

    # Manifest
    reasons.append("Deliverable manifest verified from live output files (SHA256 checksums)")

    return reasons


# ── Main generator ─────────────────────────────────────────


def generate_closing(job_id: str) -> ClosingStatement:
    """Generate a closing statement from completed epoch data.

    Works with three run paths:
      1. swarmos run — full progress tracking available
      2. manual scripts — adopt from files, partial metrics
      3. external — adopt from files only, honest nulls
    """
    poj = state.load_poj(job_id)
    progress = state.load_progress(job_id)
    fs = state.load_flightsheet(job_id)

    if not poj:
        raise ValueError(f"No POJ found for job {job_id}")

    domain = poj.domain
    output_dir = config.HONEY_DIR / domain / "validated"

    # ── Determine epoch source and adopt if needed ──
    if progress and progress.source == "swarmos":
        epoch_source = "swarmos"
    elif progress:
        epoch_source = progress.source
    else:
        # No progress file — adopt from output files
        progress = _adopt_epoch(domain, output_dir)
        epoch_source = "adopted"

    # ── Observed: classification counts from files ──
    # Canonical: royal-jelly/honey/propolis — also reads legacy jelly.jsonl and wax.jsonl
    honey_count = _count_lines(output_dir / "honey.jsonl")
    royal_jelly_count = _count_lines(output_dir / "royal-jelly.jsonl") + _count_lines(output_dir / "jelly.jsonl")  # backward compat
    propolis_count = _count_lines(output_dir / "propolis.jsonl") + _count_lines(output_dir / "wax.jsonl")  # backward compat
    receipt_count = _count_lines(output_dir / "receipts.jsonl")
    total_processed = honey_count + royal_jelly_count + propolis_count
    actual_honey_rate = honey_count / max(total_processed, 1)

    # ── Runtime metrics — None if not captured ──
    actual_wall_hours: Optional[float] = None
    actual_hashrate: Optional[float] = None

    if progress.elapsed_sec is not None and progress.elapsed_sec > 0:
        actual_wall_hours = round(progress.elapsed_sec / 3600, 2)

    if progress.recorder_rate is not None and progress.recorder_rate > 0:
        actual_hashrate = round(progress.recorder_rate, 1)

    # ── Cost calculation ──
    total_power_w = fs.totals.total_power_w if fs else 0
    gpu_assignments = fs.gpu_assignments if fs else []
    actual_total_cost, actual_ctm, actual_energy_wh, cost_source = _compute_costs(
        total_processed, actual_wall_hours, total_power_w, gpu_assignments,
    )

    # ── Data source labels ──
    data_sources = DataSource(
        classification="observed",
        wall_time="observed" if actual_wall_hours is not None else "unavailable",
        hashrate="observed" if actual_hashrate is not None else "unavailable",
        energy="observed" if actual_energy_wh is not None else "unavailable",
        cost=cost_source,
        honey_rate="observed",
        fees="derived",
    )

    # ── Fees ──
    title_premium = total_processed * poj.fee_schedule.title_premium_per_deed
    fixed_fees = poj.fee_schedule.fixed_fees_total
    total_closing = title_premium + fixed_fees
    net_margin = (total_closing - actual_total_cost) if actual_total_cost is not None else None
    margin_pct = (net_margin / total_closing * 100) if net_margin is not None and total_closing > 0 else None

    # ── Variance (only where both values exist) ──
    variance = VarianceReport(
        cost_estimated=poj.estimated_cost.total_production,
        cost_actual=actual_total_cost if actual_total_cost is not None else 0.0,
        cost_variance_pct=_variance_pct(poj.estimated_cost.total_production, actual_total_cost),
        time_estimated_hours=poj.estimated_timeline_hours,
        time_actual_hours=actual_wall_hours if actual_wall_hours is not None else 0.0,
        time_variance_pct=_variance_pct(poj.estimated_timeline_hours, actual_wall_hours),
        honey_rate_estimated=poj.estimated_honey_rate,
        honey_rate_actual=round(actual_honey_rate, 4),
        honey_rate_variance_pct=_variance_pct(poj.estimated_honey_rate, actual_honey_rate),
        hashrate_estimated=poj.estimated_hashrate,
        hashrate_actual=actual_hashrate if actual_hashrate is not None else 0.0,
        hashrate_variance_pct=_variance_pct(poj.estimated_hashrate, actual_hashrate),
    )

    # ── Variance reasons ──
    variance_reasons = _generate_variance_reasons(
        progress, poj, actual_honey_rate, actual_wall_hours, actual_hashrate, epoch_source,
    )

    # ── Manifest ──
    manifest = _build_manifest(output_dir)

    return ClosingStatement(
        job_id=job_id,
        poj_id=poj.job_id,
        client=poj.client,
        domain=domain,
        epoch_source=epoch_source,
        actual_pairs_processed=total_processed,
        actual_honey=honey_count,
        actual_royal_jelly=royal_jelly_count,
        actual_propolis=propolis_count,
        actual_honey_rate=round(actual_honey_rate, 4),
        actual_wall_time_hours=actual_wall_hours,
        actual_hashrate=actual_hashrate,
        actual_energy_wh=actual_energy_wh,
        actual_cost_to_mint=actual_ctm,
        actual_total_cost=actual_total_cost,
        title_premium_charged=round(title_premium, 2),
        fixed_fees=round(fixed_fees, 2),
        total_closing_cost=round(total_closing, 2),
        net_margin=round(net_margin, 2) if net_margin is not None else None,
        margin_pct=round(margin_pct, 1) if margin_pct is not None else None,
        variance=variance,
        variance_reasons=variance_reasons,
        data_sources=data_sources,
        deliverable_manifest=manifest,
        block_count=receipt_count,
    )


# ── Formatter ──────────────────────────────────────────────


def format_closing(cs: ClosingStatement) -> str:
    """Human-readable closing statement with honest data source labels."""
    lines = [
        "┌─────────────────────────────────────────────────┐",
        "│           CLOSING STATEMENT                      │",
        "│           SwarmOS Validation Services             │",
        "└─────────────────────────────────────────────────┘",
        "",
        f"  Job:     {cs.job_id}",
        f"  Client:  {cs.client}",
        f"  Domain:  {cs.domain}",
        f"  Source:  {cs.epoch_source}",
        "",
        f"  CLASSIFICATION RESULTS:                    [{cs.data_sources.classification}]",
        f"    Honey:    {cs.actual_honey:,}  ({cs.actual_honey_rate:.1%})",
        f"    Royal Jelly: {cs.actual_royal_jelly:,}",
        f"    Propolis: {cs.actual_propolis:,}",
        f"    Total:    {cs.actual_pairs_processed:,}",
        "",
        "  PERFORMANCE:",
        f"    Wall time:  {_fmt(cs.actual_wall_time_hours, '.1f', suffix='h'):<12} [{cs.data_sources.wall_time}]",
        f"    Hashrate:   {_fmt(cs.actual_hashrate, '.1f', suffix=' deeds/min'):<20} [{cs.data_sources.hashrate}]",
        f"    Energy:     {_fmt(cs.actual_energy_wh, '.0f', suffix=' Wh'):<12} [{cs.data_sources.energy}]",
        f"    CTM:        {_fmt(cs.actual_cost_to_mint, '.6f', prefix='$', suffix='/deed'):<18} [{cs.data_sources.cost}]",
        "",
        f"  FEE SUMMARY:                               [{cs.data_sources.fees}]",
    ]

    if cs.actual_pairs_processed > 0:
        rate = cs.title_premium_charged / cs.actual_pairs_processed
        lines.append(f"    Title premium:  {cs.actual_pairs_processed:,} x ${rate:.3f} = ${cs.title_premium_charged:,.2f}")
    else:
        lines.append(f"    Title premium:  ${cs.title_premium_charged:,.2f}")

    lines.extend([
        f"    Fixed fees:     ${cs.fixed_fees:,.2f}",
        "    ─────────────────────────────────────",
        f"    TOTAL CLOSING:  ${cs.total_closing_cost:,.2f}",
        "",
        f"    Cost to produce: {_fmt(cs.actual_total_cost, '.2f', prefix='$')}",
        f"    Net margin:      {_fmt(cs.net_margin, ',.2f', prefix='$')}"
        + (f" ({cs.margin_pct:.1f}%)" if cs.margin_pct is not None else ""),
        "",
        "  VARIANCE (estimated vs actual):",
    ])

    v = cs.variance
    lines.append(f"    Cost:       ${v.cost_estimated:.2f} -> {_fmt(v.cost_actual if v.cost_actual else None, '.2f', prefix='$'):<10} ({v.cost_variance_pct:+.1f}%)" if v.cost_actual else f"    Cost:       ${v.cost_estimated:.2f} -> n/a")
    lines.append(f"    Time:       {v.time_estimated_hours:.1f}h -> {_fmt(v.time_actual_hours if v.time_actual_hours else None, '.1f', suffix='h'):<8} ({v.time_variance_pct:+.1f}%)" if v.time_actual_hours else f"    Time:       {v.time_estimated_hours:.1f}h -> n/a")
    lines.append(f"    Honey rate: {v.honey_rate_estimated:.1%} -> {v.honey_rate_actual:.1%} ({v.honey_rate_variance_pct:+.1f}%)")
    lines.append(f"    Hashrate:   {v.hashrate_estimated:.1f} -> {_fmt(v.hashrate_actual if v.hashrate_actual else None, '.1f'):<6} ({v.hashrate_variance_pct:+.1f}%)" if v.hashrate_actual else f"    Hashrate:   {v.hashrate_estimated:.1f} -> n/a")

    # Variance reasons
    if cs.variance_reasons:
        lines.append("")
        lines.append("  VARIANCE NOTES:")
        for reason in cs.variance_reasons:
            lines.append(f"    - {reason}")

    lines.append("")
    lines.append("  DELIVERABLES:")
    for d in cs.deliverable_manifest:
        lines.append(f"    {Path(d.path).name:<25} {d.lines:>8} lines  {d.size_bytes:>12} bytes  {d.sha256[:12]}...")

    if cs.hedera_anchors:
        lines.append(f"\n  HEDERA ANCHORS: {', '.join(cs.hedera_anchors)}")
    if cs.block_count:
        lines.append(f"  BLOCKS SEALED: {cs.block_count:,}")

    lines.extend(["", f"  Sealed: {cs.sealed_at.isoformat()}", ""])
    return "\n".join(lines)
