"""Verdict classifier — score-only, 3-tier: royal-jelly / honey / propolis.

No verdict gating. No guessing. The score decides the tier.
"""
from __future__ import annotations

import re


def classify_verdict(judge_output: str) -> tuple[str, float, str]:
    """Parse judge output into (verdict, score, classification).

    Returns:
        verdict: "PASS" or "FAIL"
        score: 0.0 to 1.0
        classification: "royal-jelly", "honey", or "propolis"
    """
    score = 0.0
    verdict = "FAIL"

    for line in judge_output.split("\n"):
        ll = line.strip().lower()
        if ll.startswith("verdict:"):
            verdict = "PASS" if "pass" in ll else "FAIL"
        if "total_score:" in ll or "total score:" in ll:
            nums = re.findall(r"\d+", line)
            if nums:
                score = min(int(nums[0]), 100) / 100.0

    # Score-only classification — deterministic
    if score >= 0.75:
        classification = "royal-jelly"
    elif score >= 0.50:
        classification = "honey"
    else:
        classification = "propolis"

    return verdict, score, classification
