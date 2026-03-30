"""SwarmOS Algorithm Registry — validation algo definitions.

Each algo specifies: model requirements, system prompts, scoring thresholds.
Algo + Hardware = Flight Sheet.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config


@dataclass
class AlgoConfig:
    name: str
    domain: str
    description: str
    judge_model: str = "9B-Q4"          # Base 9B — does the thinking
    recorder_model: str = "2B-Q4"       # Base 2B — writes the deed (no fine-tune needed)
    judge_gguf: str = ""                # Override GGUF path
    recorder_gguf: str = ""             # Override GGUF path
    judge_system_prompt: str = ""
    recorder_system_prompt: str = ""
    judge_max_tokens: int = 4096
    recorder_max_tokens: int = 512
    honey_threshold: float = 0.80
    jelly_threshold: float = 0.40
    judge_temperature: float = 0.1

    def __post_init__(self):
        if not self.judge_system_prompt:
            self.judge_system_prompt = config.JUDGE_SYSTEM_PROMPT
        if not self.recorder_system_prompt:
            self.recorder_system_prompt = config.RECORDER_SYSTEM_PROMPT
        if not self.judge_gguf:
            self.judge_gguf = config.DEFAULT_JUDGE_GGUF
        if not self.recorder_gguf:
            self.recorder_gguf = config.DEFAULT_RECORDER_GGUF


# ── Built-in Algorithms ────────────────────────────────────

_REGISTRY: dict[str, AlgoConfig] = {}


def register(algo: AlgoConfig):
    _REGISTRY[algo.name] = algo


def get(name: str) -> AlgoConfig | None:
    return _REGISTRY.get(name)


def list_algos() -> list[AlgoConfig]:
    return list(_REGISTRY.values())


# Register built-in algos
for _domain in [
    "failure", "finance", "cre", "legal", "medical",
    "aviation", "marketing", "signal", "grants", "junior",
    "curator", "router",
]:
    register(AlgoConfig(
        name=f"validate-{_domain}",
        domain=_domain,
        description=f"Validate {_domain} domain pairs (9B base judge → 2B base recorder)",
    ))

# ARC benchmark algo (different scoring)
register(AlgoConfig(
    name="benchmark-arc",
    domain="arc",
    description="ARC procedural task benchmark (deterministic scoring)",
    honey_threshold=0.95,
    jelly_threshold=0.30,
))
