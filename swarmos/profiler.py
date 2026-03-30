"""SwarmOS Hardware Profiler — detect and assess all compute resources.

Produces a HardwareProfile document with GPU capacity, CPU AMX status,
RAM, and remote fleet health.
"""
from __future__ import annotations

import platform
import shutil
import subprocess

import httpx

from . import config
from .models import HardwareProfile, RemoteNode
from .hardware.gpu import detect_gpus
from .hardware.cpu import detect_cpu


def _get_ram() -> tuple[float, float]:
    """Return (total_gb, free_gb) from /proc/meminfo."""
    total = free = 0.0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) / (1024 * 1024)  # kB → GB
                elif line.startswith("MemAvailable:"):
                    free = int(line.split()[1]) / (1024 * 1024)
    except OSError:
        pass
    return round(total, 1), round(free, 1)


def _get_storage_free() -> float:
    """Return free disk space in GB on the primary data partition."""
    for path in ["/data2", "/data1", "/"]:
        try:
            usage = shutil.disk_usage(path)
            return round(usage.free / (1024**3), 1)
        except OSError:
            continue
    return 0.0


def _probe_remote(host: str, port: int, timeout: float = 3.0) -> RemoteNode:
    """Probe a remote model endpoint for health."""
    node = RemoteNode(hostname=host, ip=host, port=port)
    try:
        resp = httpx.get(f"http://{host}:{port}/health", timeout=timeout)
        if resp.status_code == 200:
            node.status = "healthy"
        else:
            node.status = "unhealthy"
    except Exception:
        node.status = "unreachable"
    return node


# Known fleet endpoints (from swarm_fleet.sh)
FLEET_ENDPOINTS = [
    ("192.168.0.99", 8092, "whale-7b"),      # Whale (RTX 3090)
    ("192.168.0.79", 8085, "jetson-4b"),      # Jetson Orin
    ("192.168.0.70", 8085, "zima-4b"),        # Zima (N150)
]


def profile(include_remote: bool = False) -> HardwareProfile:
    """Detect all local hardware and optionally probe remote fleet."""
    gpus = detect_gpus()
    cpu = detect_cpu()
    ram_total, ram_free = _get_ram()
    storage_free = _get_storage_free()

    remote_nodes = []
    if include_remote:
        for host, port, model_name in FLEET_ENDPOINTS:
            node = _probe_remote(host, port)
            node.model = model_name
            remote_nodes.append(node)

    hostname = platform.node()

    return HardwareProfile(
        hostname=hostname,
        gpus=gpus,
        cpu=cpu,
        ram_total_gb=ram_total,
        ram_free_gb=ram_free,
        storage_free_gb=storage_free,
        remote_nodes=remote_nodes,
    )


def format_profile(hp: HardwareProfile) -> str:
    """Human-readable profile output."""
    lines = [
        f"═══ HARDWARE PROFILE — {hp.hostname} ═══",
        "",
    ]

    # GPUs
    lines.append("GPUs:")
    for g in hp.gpus:
        lines.append(
            f"  [{g.index}] {g.name}: {g.vram_total_gb}GB "
            f"({g.vram_free_gb}GB free) | {g.power_limit_w}W cap | "
            f"Slots: {g.model_slots_9b}×9B or {g.model_slots_4b}×4B"
        )
    if not hp.gpus:
        lines.append("  (none detected)")

    # CPU
    lines.append(f"\nCPU: {hp.cpu.model}")
    lines.append(f"  Cores: {hp.cpu.cores} | Threads: {hp.cpu.threads}")
    flags = []
    if hp.cpu.amx_int8:
        flags.append("AMX-INT8")
    if hp.cpu.amx_bf16:
        flags.append("AMX-BF16")
    if hp.cpu.avx512:
        flags.append("AVX-512")
    lines.append(f"  ISA: {', '.join(flags) if flags else 'none'}")
    if hp.cpu.tdp_w:
        lines.append(f"  TDP: {hp.cpu.tdp_w}W | RAPL: {'yes' if hp.cpu.rapl_available else 'no'}")

    # RAM & Storage
    lines.append(f"\nRAM: {hp.ram_total_gb}GB total / {hp.ram_free_gb}GB free")
    lines.append(f"Storage: {hp.storage_free_gb}GB free")

    # Remote fleet
    if hp.remote_nodes:
        lines.append("\nFleet:")
        for n in hp.remote_nodes:
            lines.append(f"  {n.hostname}:{n.port} ({n.model}) — {n.status}")

    lines.append("")
    lines.append(f"Profiled: {hp.profiled_at.isoformat()}")
    return "\n".join(lines)
