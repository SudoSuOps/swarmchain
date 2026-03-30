"""SwarmOS configuration — fee schedules, paths, benchmark defaults.

All values configurable via environment variables with SWARMOS_ prefix.
"""
import os
from pathlib import Path


def _env(key: str, default: str) -> str:
    return os.environ.get(f"SWARMOS_{key}", os.environ.get(key, default))


# ── Paths ──────────────────────────────────────────────────

SWARMCHAIN_DIR = Path(_env("SWARMCHAIN_DIR", "/data2/swarmchain"))
JOBS_DIR = SWARMCHAIN_DIR / "jobs"
HONEY_DIR = Path(_env("HONEY_DIR", "/data1/swarm-honey"))
MODELS_DIR = Path(_env("MODELS_DIR", "/data2/models"))
SWARM_MODELS_DIR = Path(_env("SWARM_MODELS_DIR", "/data2/swarm-models"))
LLAMA_SERVER = Path(_env("LLAMA_SERVER", "/home/swarm/llama.cpp/build/bin/llama-server"))

# ── SwarmChain API ─────────────────────────────────────────

API_HOST = _env("SWARM_RAILS_HOST", "localhost")
API_PORT = int(_env("API_PORT", "8080"))
API_URL = _env("SWARM_API_URL", f"http://{API_HOST}:{API_PORT}")
API_KEY = _env("SWARM_API_KEY", "") or _env(
    "API_KEY_FALLBACK",
    "354131b4c036349ae89ebd0a2d73be7cfe665eb1d2b642cc62dd4262e54ce953",
)

# ── Fee Schedule (configurable per tier) ───────────────────

# Title premium tiers (per deed)
FEE_TIER_FLOOR = float(_env("FEE_TIER_FLOOR", "0.008"))       # 10× CTM
FEE_TIER_STANDARD = float(_env("FEE_TIER_STANDARD", "0.02"))  # 25× CTM
FEE_TIER_FULL = float(_env("FEE_TIER_FULL", "0.05"))          # 62× CTM — Full Title + Hedera
FEE_TIER_ENTERPRISE = float(_env("FEE_TIER_ENTERPRISE", "0.10"))  # 125× CTM

# Fixed fees (per epoch / job)
FEE_DOC_PREP = float(_env("FEE_DOC_PREP", "50.0"))
FEE_FLIGHT_SHEET = float(_env("FEE_FLIGHT_SHEET", "100.0"))
FEE_RECORDING = float(_env("FEE_RECORDING", "25.0"))
FEE_INSPECTION = float(_env("FEE_INSPECTION", "25.0"))

# ── Cost Inputs ────────────────────────────────────────────

ELECTRICITY_RATE = float(_env("ELECTRICITY_RATE", "0.10"))     # $/kWh
DEPRECIATION_YEARS = float(_env("DEPRECIATION_YEARS", "3.0"))

# Hardware costs (for depreciation calculation)
GPU_PRICES = {
    "RTX PRO 6000": 10000.0,
    "RTX PRO 4500": 4000.0,
    "RTX 3090": 1500.0,
    "RTX 3090 Ti": 1500.0,
}
CPU_SYSTEM_PRICE = float(_env("CPU_SYSTEM_PRICE", "8000.0"))   # Xeon + mobo + RAM

# ── Model Specs (VRAM per instance) ───────────────────────

MODEL_VRAM_GB = {
    "9B-Q4": 6.2,
    "4B-Q4": 3.5,
    "27B-Q4": 16.0,
    "1.5B-Q4": 1.5,
}

# ── Benchmark Defaults (measured from Epoch 2) ────────────

# Verdicts per minute per instance (GPU) — 9B base judge
BENCHMARK_JUDGE_RATE = {
    "9B-Q4": 7.2,      # ~86/min ÷ 12 instances
}

# Deeds per minute per instance — 2B base recorder
BENCHMARK_RECORDER_RATE_GPU = {
    "2B-Q4": 60.0,     # ~0.3s/deed on GPU with /no_think
    "9B-Q4": 21.0,     # Legacy (Legacy-9B) — do not use in production
}
BENCHMARK_RECORDER_RATE_CPU = {
    "2B-Q4": 5.0,      # ~12s/deed on Xeon AMX with /no_think
    "9B-Q4": 1.7,      # Legacy (Legacy-9B) — do not use in production
}

# CPU threads per instance for recording
CPU_THREADS_PER_RECORDER = 12

# ── Ports ──────────────────────────────────────────────────

JUDGE_PORT_START = int(_env("JUDGE_PORT_START", "8201"))
RECORDER_GPU_PORT_START = int(_env("RECORDER_GPU_PORT_START", "8097"))
RECORDER_CPU_PORT_START = int(_env("RECORDER_CPU_PORT_START", "9001"))

# ── Model Policy ───────────────────────────────────────────
#
# SwarmOS runs on BASE MODELS ONLY in the validation chain.
# No fine-tuned models. No custom builds. No compromised weights.
# Base models are unbiased, auditable, and reproducible.
#
# The judge thinks (9B base). The recorder writes (2B base).
# You don't hire a lawyer to fill out the deed at the courthouse.
#

# ── System Prompts ─────────────────────────────────────────

JUDGE_SYSTEM_PROMPT = """You are the final quality judge for AI training pairs.
Output EXACTLY this format — nothing else:

VERDICT: PASS or FAIL
TOTAL_SCORE: <number 0-100>
CLASSIFICATION: royal-jelly or honey or propolis
REASONING: <1-2 sentences max>

Scoring guide:
  royal-jelly (75-100): High quality, accurate, actionable, well-structured
  honey (50-74): Partial quality, some gaps, usable with improvement
  propolis (0-49): Low quality, inaccurate, or too generic

Be decisive. Be brief. No extra commentary."""

RECORDER_SYSTEM_PROMPT = """/no_think
You are the SwarmChain Deed Recorder.
Write EXACTLY this format — nothing else:

PAIR_ID: <id>
DOMAIN: <domain>
PAIR_SUMMARY: <one sentence>
VERDICT: <PASS/FAIL>
SCORE: <0-100>
CLASSIFICATION: <royal-jelly/honey/propolis>
WHY_SEALED: <2 sentences>
RECORD_STATUS: SEALED"""

# ── Default GGUFs — BASE MODELS ONLY ──────────────────────

DEFAULT_JUDGE_GGUF = str(MODELS_DIR / "Qwen3.5-9B-Q4_K_M.gguf")
DEFAULT_RECORDER_GGUF = str(MODELS_DIR / "Qwen3.5-2B-Q4_K_M.gguf")
