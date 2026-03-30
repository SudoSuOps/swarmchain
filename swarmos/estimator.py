"""SwarmOS Estimator — throughput and cost estimation from hardware + benchmarks.

Takes a HardwareProfile and algo config, estimates:
- How many model instances fit on each GPU
- Expected hashrate (verdicts/min, deeds/min)
- Expected wall time for N pairs
- Expected cost (electricity + depreciation + chain)
"""
from __future__ import annotations

from . import config
from .models import (
    CPUAssignment,
    EstimatedCost,
    FlightSheet,
    FlightSheetTotals,
    GPUAssignment,
    HardwareProfile,
)


def _gpu_price(name: str) -> float:
    """Lookup GPU purchase price for depreciation."""
    for key, price in config.GPU_PRICES.items():
        if key.lower() in name.lower():
            return price
    return 5000.0  # Default assumption


def _hourly_depreciation(purchase_price: float) -> float:
    """Annual depreciation → hourly rate."""
    return purchase_price / (config.DEPRECIATION_YEARS * 8760)


def estimate_gpu_assignment(
    gpu_index: int,
    gpu_name: str,
    vram_free_gb: float,
    power_limit_w: float,
    role: str,
    model_type: str = "9B-Q4",
    model_gguf: str = "",
) -> GPUAssignment:
    """Estimate optimal model assignment for a single GPU."""
    vram_per = config.MODEL_VRAM_GB.get(model_type, 6.2)
    max_instances = int(vram_free_gb / vram_per)

    # 80/20 rule — use 80% of capacity for efficiency
    optimal_instances = max(1, int(max_instances * 0.80))
    vram_total = optimal_instances * vram_per
    vram_pct = round(vram_total / (vram_free_gb + 0.01) * 100, 1)
    power_target = round(power_limit_w * 0.80, 1)

    # Hashrate from benchmarks
    if role == "judge":
        rate_per = config.BENCHMARK_JUDGE_RATE.get(model_type, 5.0)
    else:
        rate_per = config.BENCHMARK_RECORDER_RATE_GPU.get(model_type, 60.0)
    hashrate = optimal_instances * rate_per

    # Port allocation
    if role == "judge":
        port_start = config.JUDGE_PORT_START
    else:
        port_start = config.RECORDER_GPU_PORT_START
    ports = list(range(port_start, port_start + optimal_instances))

    if not model_gguf:
        model_gguf = config.DEFAULT_JUDGE_GGUF if role == "judge" else config.DEFAULT_RECORDER_GGUF

    return GPUAssignment(
        gpu_index=gpu_index,
        card=gpu_name,
        role=role,
        model_gguf=model_gguf,
        model_type=model_type,
        instance_count=optimal_instances,
        vram_per_instance_gb=vram_per,
        vram_total_gb=round(vram_total, 1),
        vram_percent=vram_pct,
        ports=ports,
        power_target_w=power_target,
        threads_per_instance=4,
        estimated_hashrate=round(hashrate, 1),
    )


def estimate_cpu_assignment(
    cpu_threads: int,
    role: str = "recorder",
    model_type: str = "9B-Q4",
    model_gguf: str = "",
) -> CPUAssignment:
    """Estimate CPU model instances using AMX."""
    threads_per = config.CPU_THREADS_PER_RECORDER
    max_instances = max(1, cpu_threads // threads_per)
    # Leave some threads for orchestrator
    optimal_instances = max(1, max_instances - 1)

    rate_per = config.BENCHMARK_RECORDER_RATE_CPU.get(model_type, 5.0)
    hashrate = optimal_instances * rate_per

    port_start = config.RECORDER_CPU_PORT_START
    ports = list(range(port_start, port_start + optimal_instances))

    if not model_gguf:
        model_gguf = config.DEFAULT_RECORDER_GGUF

    return CPUAssignment(
        role=role,
        model_gguf=model_gguf,
        model_type=model_type,
        instance_count=optimal_instances,
        threads_per_instance=threads_per,
        ports=ports,
        estimated_hashrate=round(hashrate, 1),
    )


def estimate_costs(
    pair_count: int,
    total_power_w: float,
    hashrate_deeds_per_min: float,
    gpu_assignments: list[GPUAssignment],
    cpu_system_price: float = config.CPU_SYSTEM_PRICE,
) -> EstimatedCost:
    """Estimate total production costs for an epoch."""
    if hashrate_deeds_per_min <= 0:
        return EstimatedCost()

    wall_hours = pair_count / (hashrate_deeds_per_min * 60)

    # Electricity
    energy_kwh = total_power_w * wall_hours / 1000
    electricity = energy_kwh * config.ELECTRICITY_RATE

    # Hardware depreciation
    depreciation = 0.0
    for ga in gpu_assignments:
        gpu_price = _gpu_price(ga.card)
        depreciation += _hourly_depreciation(gpu_price) * wall_hours
    depreciation += _hourly_depreciation(cpu_system_price) * wall_hours

    # Chain overhead (PostgreSQL + Hedera)
    chain = pair_count * 0.00001

    total = electricity + depreciation + chain
    per_deed = total / max(pair_count, 1)

    return EstimatedCost(
        electricity=round(electricity, 4),
        hardware_depreciation=round(depreciation, 4),
        chain_overhead=round(chain, 4),
        total_production=round(total, 4),
        per_deed=round(per_deed, 6),
    )


def compute_totals(
    pair_count: int,
    gpu_assignments: list[GPUAssignment],
    cpu_assignments: list[CPUAssignment],
) -> FlightSheetTotals:
    """Compute aggregate totals for a flight sheet."""
    total_models = sum(a.instance_count for a in gpu_assignments) + sum(a.instance_count for a in cpu_assignments)
    total_vram = sum(a.vram_total_gb for a in gpu_assignments)
    total_power = sum(a.power_target_w for a in gpu_assignments)

    # Add CPU power estimate (TDP × 80%)
    if cpu_assignments:
        total_power += 240  # ~80% of 300W TDP

    judge_rate = sum(a.estimated_hashrate for a in gpu_assignments if a.role == "judge")
    recorder_rate = (
        sum(a.estimated_hashrate for a in gpu_assignments if a.role == "recorder")
        + sum(a.estimated_hashrate for a in cpu_assignments if a.role == "recorder")
    )

    # Effective rate is the bottleneck
    effective_rate = min(judge_rate, recorder_rate) if judge_rate > 0 and recorder_rate > 0 else max(judge_rate, recorder_rate)
    wall_hours = pair_count / (effective_rate * 60) if effective_rate > 0 else 0

    costs = estimate_costs(pair_count, total_power, effective_rate, gpu_assignments)

    return FlightSheetTotals(
        total_models=total_models,
        total_vram_used_gb=round(total_vram, 1),
        total_power_w=round(total_power, 1),
        total_estimated_hashrate=round(effective_rate, 1),
        judge_hashrate=round(judge_rate, 1),
        recorder_hashrate=round(recorder_rate, 1),
        estimated_wall_hours=round(wall_hours, 2),
        estimated_cost_to_mint=costs.per_deed,
        estimated_total_cost=costs.total_production,
    )
