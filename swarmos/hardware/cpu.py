"""CPU detection — model, cores, AMX/AVX capabilities."""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..models import CPUProfile


def detect_cpu() -> CPUProfile:
    """Detect CPU model, core count, and instruction set capabilities."""
    model = "unknown"
    cores = 0
    threads = 0
    flags_str = ""

    try:
        result = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split("\n"):
            low = line.lower()
            if "model name:" in low:
                model = line.split(":", 1)[1].strip()
            elif low.startswith("cpu(s):") and "on-line" not in low and "numa" not in low:
                try:
                    threads = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif "core(s) per socket:" in low:
                try:
                    cores = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif "flags:" in low:
                flags_str = line.split(":", 1)[1].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # If flags not found via lscpu, try /proc/cpuinfo
    if not flags_str:
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text()
            for line in cpuinfo.split("\n"):
                if line.lower().startswith("flags"):
                    flags_str = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass

    flags = set(flags_str.split())

    # TDP from RAPL max power constraint
    tdp = 0.0
    rapl_available = False
    rapl_path = Path("/sys/class/powercap/intel-rapl:0/constraint_0_max_power_uw")
    if rapl_path.exists():
        try:
            tdp = int(rapl_path.read_text().strip()) / 1_000_000  # µW → W
            rapl_available = True
        except (OSError, ValueError):
            pass

    return CPUProfile(
        model=model,
        cores=cores,
        threads=threads,
        amx_bf16="amx_bf16" in flags,
        amx_int8="amx_int8" in flags,
        avx512="avx512f" in flags,
        tdp_w=tdp,
        rapl_available=rapl_available,
    )
