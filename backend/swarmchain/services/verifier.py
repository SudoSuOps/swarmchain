"""Verification engine — deterministic scoring is the anchor of integrity.

Objective verification first. Domain models assist convergence, never override.
"""
from abc import ABC, abstractmethod
from typing import Any


class DomainVerifier(ABC):
    """Interface for pluggable domain verifiers.

    Future domains (CRE, Legal, Capital Markets) implement this interface.
    Objective verifiers remain the anchor — domain models are validators, not truth.
    """
    domain: str = "generic"

    @abstractmethod
    def verify(self, task_payload: dict, attempt_output: dict) -> dict:
        """Score an attempt against the task.

        Returns:
            dict with keys: score (float 0-1), valid (bool), details (dict)
        """
        ...

    def suggest_repair(self, task_payload: dict, attempt_output: dict) -> dict | None:
        """Optional: suggest a repair direction for a failed attempt."""
        return None


class ARCVerifier(DomainVerifier):
    """Deterministic verifier for ARC-style grid tasks.

    Scoring:
    - exact match = 1.0
    - partial match = proportion of cells correct
    - invalid output = 0.0

    Elimination becomes integrity: every scored attempt refines the search space.
    """
    domain = "arc"

    def verify(self, task_payload: dict, attempt_output: dict) -> dict:
        expected = task_payload.get("expected_output")
        submitted = attempt_output.get("grid")

        if expected is None:
            return {"score": 0.0, "valid": False, "details": {"error": "no expected_output in task"}}

        if submitted is None:
            return {"score": 0.0, "valid": False, "details": {"error": "no grid in attempt output"}}

        if not isinstance(submitted, list) or not isinstance(expected, list):
            return {"score": 0.0, "valid": False, "details": {"error": "grid must be a 2D list"}}

        # Dimension check
        expected_rows = len(expected)
        expected_cols = len(expected[0]) if expected_rows > 0 else 0
        submitted_rows = len(submitted)
        submitted_cols = len(submitted[0]) if submitted_rows > 0 else 0

        if expected_rows != submitted_rows or expected_cols != submitted_cols:
            return {
                "score": 0.0,
                "valid": False,
                "details": {
                    "error": "dimension mismatch",
                    "expected": f"{expected_rows}x{expected_cols}",
                    "submitted": f"{submitted_rows}x{submitted_cols}",
                },
            }

        # Cell-by-cell comparison
        total_cells = expected_rows * expected_cols
        if total_cells == 0:
            return {"score": 0.0, "valid": False, "details": {"error": "empty grid"}}

        correct = 0
        wrong_cells = []
        for r in range(expected_rows):
            for c in range(expected_cols):
                if r < len(submitted) and c < len(submitted[r]) and submitted[r][c] == expected[r][c]:
                    correct += 1
                else:
                    wrong_cells.append({"row": r, "col": c})

        score = correct / total_cells
        exact = score == 1.0

        return {
            "score": score,
            "valid": True,
            "details": {
                "total_cells": total_cells,
                "correct_cells": correct,
                "wrong_cells_count": len(wrong_cells),
                "exact_match": exact,
                "wrong_cells": wrong_cells[:20],  # cap for large grids
            },
        }


# Registry of domain verifiers — scaffold for future domains
VERIFIER_REGISTRY: dict[str, type[DomainVerifier]] = {
    "arc": ARCVerifier,
}


def get_verifier(domain: str) -> DomainVerifier:
    """Get the verifier for a domain. Falls back to ARC."""
    cls = VERIFIER_REGISTRY.get(domain, ARCVerifier)
    return cls()
