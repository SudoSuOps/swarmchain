"""SwarmOS Flight Sheet Generator — assign silicon to algorithms.

Takes hardware profile + algo config → produces a locked flight sheet
with GPU/CPU assignments, port allocations, power targets, and cost estimates.
"""
from __future__ import annotations

from pathlib import Path

from . import config
from .algos import AlgoConfig, get as get_algo
from .estimator import compute_totals, estimate_cpu_assignment, estimate_gpu_assignment
from .models import FlightSheet, HardwareProfile
from .profiler import profile as detect_hardware


def generate(
    domain: str,
    pair_count: int,
    algo_name: str | None = None,
    hw: HardwareProfile | None = None,
    input_path: str = "",
) -> FlightSheet:
    """Generate a flight sheet for a validation job.

    Automatically assigns:
    - Largest GPU → judges (highest hashrate need)
    - Remaining GPU(s) → recorder
    - CPU (if AMX) → additional recorders
    """
    if hw is None:
        hw = detect_hardware()

    if algo_name is None:
        algo_name = f"validate-{domain}"
    algo = get_algo(algo_name)
    if algo is None:
        algo = AlgoConfig(name=algo_name, domain=domain, description=f"Custom: {domain}")

    gpu_assignments = []
    cpu_assignments = []

    if not hw.gpus:
        # CPU-only mode
        if hw.cpu.threads > 0:
            cpu_assignments.append(estimate_cpu_assignment(
                hw.cpu.threads,
                role="judge",
                model_type=algo.judge_model,
                model_gguf=algo.judge_gguf,
            ))
    else:
        # Sort GPUs by VRAM (largest first)
        gpus_sorted = sorted(hw.gpus, key=lambda g: g.vram_free_gb, reverse=True)

        # Largest GPU → judges
        primary = gpus_sorted[0]
        gpu_assignments.append(estimate_gpu_assignment(
            primary.index, primary.name, primary.vram_free_gb,
            primary.power_limit_w, role="judge",
            model_type=algo.judge_model, model_gguf=algo.judge_gguf,
        ))

        # Remaining GPUs → recorders
        for gpu in gpus_sorted[1:]:
            gpu_assignments.append(estimate_gpu_assignment(
                gpu.index, gpu.name, gpu.vram_free_gb,
                gpu.power_limit_w, role="recorder",
                model_type=algo.recorder_model, model_gguf=algo.recorder_gguf,
            ))

        # If only 1 GPU, split: use most for judges, 1 instance for recorder
        if len(gpus_sorted) == 1:
            # Add a single GPU recorder instance on the same GPU
            # (reduces judge count by 1 to make room)
            judge_assign = gpu_assignments[0]
            if judge_assign.instance_count > 2:
                # Steal 1 slot for recorder
                judge_assign.instance_count -= 1
                judge_assign.ports = judge_assign.ports[:-1]
                judge_assign.estimated_hashrate = round(
                    judge_assign.instance_count * config.BENCHMARK_JUDGE_RATE.get(algo.judge_model, 5.0), 1
                )
                rec_port = config.RECORDER_GPU_PORT_START
                rate = config.BENCHMARK_RECORDER_RATE_GPU.get(algo.recorder_model, 15.0)
                from .models import GPUAssignment
                gpu_assignments.append(GPUAssignment(
                    gpu_index=primary.index, card=primary.name,
                    role="recorder", model_gguf=algo.recorder_gguf,
                    model_type=algo.recorder_model,
                    instance_count=1,
                    vram_per_instance_gb=config.MODEL_VRAM_GB.get(algo.recorder_model, 6.2),
                    vram_total_gb=config.MODEL_VRAM_GB.get(algo.recorder_model, 6.2),
                    vram_percent=0, ports=[rec_port],
                    power_target_w=0, estimated_hashrate=rate,
                ))

        # CPU → additional recorders (if AMX capable)
        if hw.cpu.amx_int8 and hw.cpu.threads >= 12:
            cpu_assignments.append(estimate_cpu_assignment(
                hw.cpu.threads,
                role="recorder",
                model_type=algo.recorder_model,
                model_gguf=algo.recorder_gguf,
            ))

    # Compute totals
    totals = compute_totals(pair_count, gpu_assignments, cpu_assignments)

    # Resolve input path
    if not input_path:
        domain_dir = config.HONEY_DIR / domain
        if domain_dir.exists():
            jsonl_files = sorted(domain_dir.glob("*.jsonl"))
            jsonl_files = [f for f in jsonl_files if "validated" not in str(f)]
            if jsonl_files:
                input_path = str(jsonl_files[0])

    return FlightSheet(
        algo=algo_name,
        domain=domain,
        pair_count=pair_count,
        input_path=input_path,
        gpu_assignments=gpu_assignments,
        cpu_assignments=cpu_assignments,
        totals=totals,
    )


def format_flightsheet(fs: FlightSheet) -> str:
    """Human-readable flight sheet output."""
    lines = [
        f"═══ FLIGHT SHEET — {fs.algo} ═══",
        f"Domain:  {fs.domain}",
        f"Pairs:   {fs.pair_count:,}",
        f"Sheet:   {fs.sheet_id}",
        f"Status:  {'LOCKED' if fs.locked else 'DRAFT'}",
        "",
    ]

    for ga in fs.gpu_assignments:
        lines.append(f"GPU {ga.gpu_index} ({ga.card}) — {ga.role.upper()}")
        lines.append(f"  Model:     {ga.model_type} × {ga.instance_count}")
        lines.append(f"  VRAM:      {ga.vram_total_gb}GB ({ga.vram_percent}%)")
        lines.append(f"  Power:     {ga.power_target_w}W target")
        lines.append(f"  Ports:     {ga.ports[0]}-{ga.ports[-1]}" if ga.ports else "  Ports: none")
        lines.append(f"  Hashrate:  {ga.estimated_hashrate} {'verdicts' if ga.role == 'judge' else 'deeds'}/min")
        lines.append("")

    for ca in fs.cpu_assignments:
        lines.append(f"CPU — {ca.role.upper()} (AMX)")
        lines.append(f"  Model:     {ca.model_type} × {ca.instance_count}")
        lines.append(f"  Threads:   {ca.threads_per_instance}/instance")
        lines.append(f"  Ports:     {ca.ports[0]}-{ca.ports[-1]}" if ca.ports else "  Ports: none")
        lines.append(f"  Hashrate:  {ca.estimated_hashrate} deeds/min")
        lines.append("")

    t = fs.totals
    lines.append("TOTALS:")
    lines.append(f"  Models:    {t.total_models}")
    lines.append(f"  VRAM:      {t.total_vram_used_gb}GB")
    lines.append(f"  Power:     {t.total_power_w}W")
    lines.append(f"  Hashrate:  {t.total_estimated_hashrate} deeds/min (bottleneck)")
    lines.append(f"  Judge:     {t.judge_hashrate} verdicts/min")
    lines.append(f"  Recorder:  {t.recorder_hashrate} deeds/min")
    lines.append(f"  Wall time: {t.estimated_wall_hours:.1f}h")
    lines.append(f"  CTM:       ${t.estimated_cost_to_mint:.6f}/deed")
    lines.append(f"  Total:     ${t.estimated_total_cost:.2f}")

    if fs.locked:
        lines.append(f"\nLOCKED: {fs.lock_hash}")
    return "\n".join(lines)
