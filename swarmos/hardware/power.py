"""Real-time power measurement — GPU via nvidia-smi, CPU via RAPL."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path


def read_gpu_power() -> dict[int, float]:
    """Read current power draw for all GPUs. Returns {gpu_index: watts}."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,power.draw", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}

    power = {}
    for line in result.stdout.strip().split("\n"):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            try:
                power[int(parts[0])] = float(parts[1])
            except ValueError:
                pass
    return power


def read_cpu_power_rapl(duration_sec: float = 3.0) -> float:
    """Measure CPU package power over a duration using RAPL. Returns watts."""
    rapl_path = Path("/sys/class/powercap/intel-rapl:0/energy_uj")
    if not rapl_path.exists():
        return 0.0

    try:
        e1 = int(rapl_path.read_text().strip())
        time.sleep(duration_sec)
        e2 = int(rapl_path.read_text().strip())
        energy_uj = e2 - e1
        return energy_uj / (duration_sec * 1_000_000)  # µJ → W
    except (OSError, ValueError, PermissionError):
        return 0.0


def read_system_power(cpu_duration: float = 3.0) -> dict:
    """Read power from all sources. Returns summary dict."""
    gpu_power = read_gpu_power()
    cpu_power = read_cpu_power_rapl(cpu_duration)

    total_gpu = sum(gpu_power.values())
    overhead = 60.0  # Fans, RAM, NVMe, PSU losses (estimated)

    return {
        "gpu_power": gpu_power,
        "gpu_total_w": round(total_gpu, 1),
        "cpu_power_w": round(cpu_power, 1),
        "overhead_w": overhead,
        "total_system_w": round(total_gpu + cpu_power + overhead, 1),
    }
