"""GPU detection via nvidia-smi."""
from __future__ import annotations

import subprocess

from ..models import GPUProfile
from .. import config


def detect_gpus() -> list[GPUProfile]:
    """Detect all NVIDIA GPUs via nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.free,memory.used,power.limit,power.draw,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    gpus = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 8:
            continue

        idx = int(parts[0])
        name = parts[1]
        vram_total = float(parts[2]) / 1024  # MiB → GiB
        vram_free = float(parts[3]) / 1024
        vram_used = float(parts[4]) / 1024
        power_limit = float(parts[5])
        power_draw = float(parts[6])
        compute_cap = parts[7]

        # Calculate model capacity
        slots_9b = int(vram_free / config.MODEL_VRAM_GB.get("9B-Q4", 6.2))
        slots_4b = int(vram_free / config.MODEL_VRAM_GB.get("4B-Q4", 3.5))

        gpus.append(GPUProfile(
            index=idx,
            name=name,
            vram_total_gb=round(vram_total, 1),
            vram_free_gb=round(vram_free, 1),
            vram_used_gb=round(vram_used, 1),
            power_limit_w=power_limit,
            power_draw_w=power_draw,
            compute_capability=compute_cap,
            model_slots_9b=slots_9b,
            model_slots_4b=slots_4b,
        ))
    return gpus
