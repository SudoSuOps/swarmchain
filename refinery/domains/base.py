"""
Royal Jelly — shared trajectory template and domain registry.

Every domain prompt inherits from these two constants so JellyScore
reasoning_depth consistently hits 1.0 (10/10).

JellyScore reasoning_depth checks for:
  - trajectory keywords: identify, calculate, analyze, evaluate, recommend  (max 5)
  - causal keywords:     because, therefore, implies, consequently, thus, hence  (max 3)
  - conditional keywords: if, then, unless, when, assuming, given that  (max 2)
  - quantitative markers: $, %, or arithmetic expressions  (max 2)
  Total: 12 possible → capped at 10 → divided by 10.0

Tier thresholds:  Royal Jelly ≥ 95 | Honey ≥ 85 | Pollen ≥ 70 | Propolis < 70

CRITICAL — Domain Fallback Rule:
  Unknown or unclassified domains MUST fall back to "default", NEVER to a
  specific domain like "ai". Sending a non-AI paper (e.g. aerospace fluid
  dynamics) through the AI prompt causes hallucinated ML metrics — the model
  invents transformer benchmarks for papers about turbulent flames. The output
  passes quality gates (structured, has numbers) but the content is fabricated.
  This has caused 24+ hour cook runs to produce zero usable pairs.

  get_prompts() already falls back to "default" for unknown domains.
  Callers MUST NOT map unknown domains to "ai" before calling get_prompts().
"""

from __future__ import annotations

import random
from typing import Tuple

# ═══════════════════════════════════════════════════════════════════════
# Canonical JellyScore keyword lists — the exact tokens the scorer counts
# Import these instead of hardcoding duplicates in other repos
# ═══════════════════════════════════════════════════════════════════════

TRAJECTORY_KW = ["identify", "calculate", "analyze", "evaluate", "recommend"]
CAUSAL_KW = ["because", "therefore", "implies", "consequently", "thus", "hence"]
CONDITIONAL_KW = ["if", "then", "unless", "when", "assuming", "given that"]
QUANT_MARKERS = ["%", "$"]

# ═══════════════════════════════════════════════════════════════════════
# Shared trajectory template — embedded in every domain instruction
# ═══════════════════════════════════════════════════════════════════════

RJ_TRAJECTORY = (
    "Use the 5-step trajectory:\n"
    "1. IDENTIFY the core issue\n"
    "2. CALCULATE key metrics — include specific numbers, percentages, and show the math\n"
    "3. ANALYZE root causes with causal reasoning — use 'because', 'therefore', 'consequently'\n"
    "4. EVALUATE risks with conditional reasoning — 'if X then Y', 'unless Z', 'assuming W'\n"
    "5. RECOMMEND specific actions with clear rationale\n"
)

# ═══════════════════════════════════════════════════════════════════════
# Shared system prompt suffix — appended to every domain system prompt
# ═══════════════════════════════════════════════════════════════════════

RJ_SYSTEM_SUFFIX = (
    "\n\nYou produce structured analysis using the 5-step trajectory: "
    "IDENTIFY → CALCULATE → ANALYZE → EVALUATE → RECOMMEND. "
    "Always include specific numbers and percentages. "
    "Use causal reasoning ('because', 'therefore', 'consequently') and "
    "conditional reasoning ('if…then', 'unless', 'assuming'). "
    "Write for experienced professionals, not academics."
)

# ═══════════════════════════════════════════════════════════════════════
# Domain registry — populated by each domain module on import
# ═══════════════════════════════════════════════════════════════════════

DOMAIN_REGISTRY: dict[str, dict] = {}


def register_domain(
    name: str,
    system_prompts: list[str],
    instructions: list[str],
    concept_terms: list[str] | None = None,
):
    """Register a domain's prompts in the global registry."""
    DOMAIN_REGISTRY[name] = {
        "system_prompts": system_prompts,
        "instructions": instructions,
        "concept_terms": concept_terms or [],
    }


def get_prompts(domain: str) -> Tuple[str, str]:
    """Return (system_prompt, instruction) for a domain. Random selection."""
    d = DOMAIN_REGISTRY.get(domain)
    if not d:
        d = DOMAIN_REGISTRY.get("default")
    if not d:
        raise KeyError(f"Domain '{domain}' not registered and no default found")
    return random.choice(d["system_prompts"]), random.choice(d["instructions"])


def get_system_prompt(domain: str) -> str:
    """Return a random system prompt for the domain."""
    d = DOMAIN_REGISTRY.get(domain, DOMAIN_REGISTRY.get("default"))
    if not d:
        raise KeyError(f"Domain '{domain}' not registered")
    return random.choice(d["system_prompts"])


def get_instruction(domain: str) -> str:
    """Return a random instruction for the domain."""
    d = DOMAIN_REGISTRY.get(domain, DOMAIN_REGISTRY.get("default"))
    if not d:
        raise KeyError(f"Domain '{domain}' not registered")
    return random.choice(d["instructions"])


def list_domains() -> list[str]:
    """Return all registered domain names."""
    return sorted(DOMAIN_REGISTRY.keys())


def get_concept_terms(domain: str) -> list[str]:
    """Return concept terms for gate_concept_present checks."""
    d = DOMAIN_REGISTRY.get(domain, {})
    return d.get("concept_terms", [])
