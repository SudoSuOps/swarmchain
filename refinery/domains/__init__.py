"""
cook-domain-prompts — Royal Jelly–aligned prompt library.

Usage:
    from domains import get_prompts, list_domains

    system, instruction = get_prompts("aviation")
    system, instruction = get_prompts("cre")

    # All available domains
    print(list_domains())
"""

from domains.base import (
    RJ_TRAJECTORY,
    RJ_SYSTEM_SUFFIX,
    TRAJECTORY_KW,
    CAUSAL_KW,
    CONDITIONAL_KW,
    QUANT_MARKERS,
    get_prompts,
    get_system_prompt,
    get_instruction,
    get_concept_terms,
    list_domains,
    DOMAIN_REGISTRY,
)

__all__ = [
    "RJ_TRAJECTORY",
    "RJ_SYSTEM_SUFFIX",
    "TRAJECTORY_KW",
    "CAUSAL_KW",
    "CONDITIONAL_KW",
    "QUANT_MARKERS",
    "get_prompts",
    "get_system_prompt",
    "get_instruction",
    "get_concept_terms",
    "list_domains",
    "DOMAIN_REGISTRY",
]
