"""Domain-routed finality validators — models assist convergence, never override truth.

Architecture:
- Deterministic verification (DomainVerifier) remains the source-of-truth anchor.
- Domain validators run AFTER objective verification, during block finalization.
- They provide: confidence, verdict, critique, flags, repair suggestions.
- A validator may NEVER override a failed objective check.
- A validator may NEVER downgrade a block that passed objective verification.
- Validator outputs are stored in both ValidatorDecision records and block artifacts.

Domain routing:
- CRE       → Atlas validator (commercial real estate analysis)
- Capital   → Swarm Capital 27B validator (grants/funding intelligence)
- Legal     → Resolve validator (legal reasoning review)
- arc       → (none — deterministic verification is sufficient)

To add a new domain validator:
1. Subclass FinalityValidator
2. Implement validate_attempt()
3. Register in VALIDATOR_REGISTRY
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.models import ValidatorDecision, BlockArtifact, Block, Attempt

logger = logging.getLogger("swarmchain.validators")


@dataclass
class ValidationResult:
    """Output of a domain validator — structured decision with full transparency."""
    confidence: float           # 0.0-1.0: how confident the validator is in the attempt
    verdict: str                # "approved", "flagged", "rejected", "needs_review"
    critique: str | None = None # free-text analysis of the attempt quality
    flags: list[str] = field(default_factory=list)  # specific issues found
    repair_suggestion: str | None = None  # guidance for improving the attempt
    raw_output: dict = field(default_factory=dict)   # full validator internals


class FinalityValidator(ABC):
    """Interface for domain-specific finality validators.

    Validators assist convergence — they provide expert judgment on whether
    an attempt truly solves the domain problem, beyond what deterministic
    verification can check. They may NEVER override objective verification.

    Future validators may call actual model endpoints. For MVP, mock
    implementations demonstrate the architecture.
    """
    domain: str = "generic"
    name: str = "generic-validator"

    @abstractmethod
    async def validate_attempt(
        self,
        task_payload: dict,
        attempt_output: dict,
        objective_score: float,
        block_context: dict | None = None,
    ) -> ValidationResult:
        """Validate an attempt with domain expertise.

        Args:
            task_payload: The block's task definition
            attempt_output: The attempt's output_json
            objective_score: Score from the deterministic verifier (source of truth)
            block_context: Optional context (attempt history, lineage, etc.)

        Returns:
            ValidationResult with confidence, verdict, critique, flags, repair guidance
        """
        ...

    async def suggest_repair(
        self,
        task_payload: dict,
        attempt_output: dict,
        objective_score: float,
    ) -> str | None:
        """Optional: suggest specific repair direction for a failing attempt."""
        return None


# ─── CRE Atlas Validator ──────────────────────────────────────────────────────

class CREAtlasValidator(FinalityValidator):
    """CRE domain validator — commercial real estate analysis.

    Validates attempts against CRE-specific quality criteria:
    - Property analysis completeness (zoning, financials, comps)
    - Regulatory compliance flags
    - Market data recency and relevance
    - Risk factor identification

    In production, this would call the Atlas 9B/27B model endpoint.
    For MVP, uses deterministic structural checks as a mock.
    """
    domain = "cre"
    name = "atlas-cre"

    # Required fields for a quality CRE analysis
    REQUIRED_SECTIONS = [
        "property_type", "location", "valuation", "zoning",
    ]
    RECOMMENDED_SECTIONS = [
        "financials", "comparables", "risk_factors", "market_analysis",
        "regulatory_notes", "cap_rate", "noi",
    ]

    async def validate_attempt(
        self,
        task_payload: dict,
        attempt_output: dict,
        objective_score: float,
        block_context: dict | None = None,
    ) -> ValidationResult:
        flags = []
        critique_parts = []
        sections_found = []
        sections_missing = []

        # Check required sections
        for section in self.REQUIRED_SECTIONS:
            if section in attempt_output and attempt_output[section]:
                sections_found.append(section)
            else:
                sections_missing.append(section)
                flags.append(f"missing_required:{section}")

        # Check recommended sections
        recommended_found = 0
        for section in self.RECOMMENDED_SECTIONS:
            if section in attempt_output and attempt_output[section]:
                recommended_found += 1
                sections_found.append(section)

        # Compute confidence
        required_coverage = len(self.REQUIRED_SECTIONS) - len(
            [f for f in flags if f.startswith("missing_required:")]
        )
        required_ratio = required_coverage / max(len(self.REQUIRED_SECTIONS), 1)
        recommended_ratio = recommended_found / max(len(self.RECOMMENDED_SECTIONS), 1)
        confidence = (required_ratio * 0.7) + (recommended_ratio * 0.3)

        # Valuation sanity check
        valuation = attempt_output.get("valuation")
        if isinstance(valuation, (int, float)):
            if valuation <= 0:
                flags.append("invalid_valuation:non_positive")
                confidence *= 0.5
            elif valuation > 1e12:
                flags.append("suspicious_valuation:exceeds_1T")
                confidence *= 0.8

        # Cap rate sanity check
        cap_rate = attempt_output.get("cap_rate")
        if isinstance(cap_rate, (int, float)):
            if cap_rate < 0.01 or cap_rate > 0.50:
                flags.append(f"unusual_cap_rate:{cap_rate}")

        # Risk factors check
        risk_factors = attempt_output.get("risk_factors", [])
        if isinstance(risk_factors, list) and len(risk_factors) == 0:
            flags.append("no_risk_factors_identified")
            critique_parts.append("No risk factors identified — every CRE asset has risks.")

        # Build critique
        if sections_missing:
            critique_parts.insert(0,
                f"Missing required sections: {', '.join(sections_missing)}."
            )
        if recommended_found < len(self.RECOMMENDED_SECTIONS) // 2:
            critique_parts.append(
                f"Only {recommended_found}/{len(self.RECOMMENDED_SECTIONS)} "
                f"recommended sections present. Analysis depth is thin."
            )
        if not critique_parts:
            critique_parts.append("Analysis is structurally complete and well-formed.")

        # Determine verdict
        if required_ratio == 1.0 and confidence >= 0.8:
            verdict = "approved"
        elif required_ratio >= 0.75:
            verdict = "needs_review"
        elif flags:
            verdict = "flagged"
        else:
            verdict = "needs_review"

        # Build repair suggestion
        repair = None
        if sections_missing:
            repair = f"Add the following sections: {', '.join(sections_missing)}."
            if "financials" in sections_missing:
                repair += " Include NOI, operating expenses, and revenue projections."
            if "comparables" in sections_missing:
                repair += " Add at least 3 comparable properties with sale prices and dates."

        return ValidationResult(
            confidence=round(confidence, 4),
            verdict=verdict,
            critique=" ".join(critique_parts),
            flags=flags,
            repair_suggestion=repair,
            raw_output={
                "sections_found": sections_found,
                "sections_missing": sections_missing,
                "required_coverage": required_ratio,
                "recommended_coverage": recommended_ratio,
                "total_flags": len(flags),
            },
        )


# ─── Capital Markets Validator (Scaffold) ─────────────────────────────────────

class CapitalValidator(FinalityValidator):
    """Capital Markets validator — grants/funding intelligence.

    In production: routes to Swarm Capital 27B model endpoint.
    For MVP: scaffold with basic structural checks.
    """
    domain = "capital"
    name = "swarm-capital-27b"

    async def validate_attempt(
        self,
        task_payload: dict,
        attempt_output: dict,
        objective_score: float,
        block_context: dict | None = None,
    ) -> ValidationResult:
        # Scaffold — structural presence check
        flags = []
        expected_keys = task_payload.get("required_fields", [])
        for key in expected_keys:
            if key not in attempt_output:
                flags.append(f"missing_field:{key}")

        confidence = max(0.0, 1.0 - (len(flags) * 0.15))
        verdict = "approved" if not flags else "flagged"

        return ValidationResult(
            confidence=round(confidence, 4),
            verdict=verdict,
            critique=f"Structural check: {len(flags)} missing fields." if flags else "All required fields present.",
            flags=flags,
            raw_output={"checked_fields": expected_keys, "missing": len(flags)},
        )


# ─── Legal Resolve Validator (Scaffold) ───────────────────────────────────────

class LegalResolveValidator(FinalityValidator):
    """Legal domain validator — legal reasoning review.

    In production: routes to Resolve legal model endpoint.
    For MVP: scaffold only.
    """
    domain = "legal"
    name = "resolve-legal"

    async def validate_attempt(
        self,
        task_payload: dict,
        attempt_output: dict,
        objective_score: float,
        block_context: dict | None = None,
    ) -> ValidationResult:
        # Scaffold — check for IRAC structure
        flags = []
        for section in ["issue", "rule", "analysis", "conclusion"]:
            if section not in attempt_output:
                flags.append(f"missing_irac:{section}")

        confidence = max(0.0, 1.0 - (len(flags) * 0.25))
        verdict = "approved" if not flags else "needs_review"

        return ValidationResult(
            confidence=round(confidence, 4),
            verdict=verdict,
            critique=f"IRAC check: {4 - len(flags)}/4 sections present.",
            flags=flags,
            raw_output={"irac_sections_present": 4 - len(flags)},
        )


# ─── Validator Registry ──────────────────────────────────────────────────────

VALIDATOR_REGISTRY: dict[str, type[FinalityValidator]] = {
    "cre": CREAtlasValidator,
    "capital": CapitalValidator,
    "legal": LegalResolveValidator,
}


def get_validator(domain: str) -> FinalityValidator | None:
    """Get the finality validator for a domain. Returns None for domains without one."""
    cls = VALIDATOR_REGISTRY.get(domain)
    return cls() if cls else None


def list_validators() -> list[dict]:
    """List all registered domain validators."""
    return [
        {"domain": v.domain, "name": v.name}
        for v in (cls() for cls in VALIDATOR_REGISTRY.values())
    ]


# ─── Validator Runner ─────────────────────────────────────────────────────────

class ValidatorRunner:
    """Executes domain validators during finalization and stores decisions.

    Enforces the iron rule: validators may NEVER override objective verification.
    """

    @staticmethod
    async def run_validator(
        db: AsyncSession,
        block: Block,
        attempt: Attempt | None,
        objective_score: float,
    ) -> ValidatorDecision | None:
        """Run the domain validator for a block and store the decision.

        Returns None if no validator exists for the domain.
        """
        validator = get_validator(block.domain)
        if validator is None:
            return None

        attempt_output = attempt.output_json if attempt else {}

        # Build block context for the validator
        block_context = {
            "block_id": block.block_id,
            "attempt_count": block.attempt_count,
            "total_energy": block.total_energy,
        }

        # Run validation
        try:
            result = await validator.validate_attempt(
                task_payload=block.task_payload,
                attempt_output=attempt_output,
                objective_score=objective_score,
                block_context=block_context,
            )
        except Exception as e:
            logger.error(f"Validator {validator.name} failed for block {block.block_id}: {e}")
            result = ValidationResult(
                confidence=0.0,
                verdict="error",
                critique=f"Validator error: {str(e)}",
                flags=["validator_error"],
                raw_output={"error": str(e)},
            )

        # IRON RULE: validator cannot override objective verification
        # If objective says solved (1.0), validator cannot downgrade the verdict
        # If objective says failed, validator opinion is recorded but doesn't change score
        objective_overridden = False
        if objective_score >= 1.0 and result.verdict in ("rejected", "flagged", "needs_review"):
            logger.warning(
                f"Validator {validator.name} returned '{result.verdict}' for objectively solved "
                f"block {block.block_id} — overriding to 'approved' (objective verification is truth)"
            )
            result.verdict = "approved"
            result.flags.append("validator_overridden_by_objective")
            objective_overridden = True

        # Store the decision
        decision = ValidatorDecision(
            block_id=block.block_id,
            attempt_id=attempt.attempt_id if attempt else None,
            validator_name=validator.name,
            domain=validator.domain,
            confidence=result.confidence,
            verdict=result.verdict,
            critique=result.critique,
            flags=result.flags,
            repair_suggestion=result.repair_suggestion,
            raw_output=result.raw_output,
            objective_score=objective_score,
            objective_overridden=objective_overridden,
        )
        db.add(decision)

        # Also store as a block artifact for the sealed record
        artifact = BlockArtifact(
            block_id=block.block_id,
            artifact_type="validator_decision",
            artifact_json={
                "validator_name": validator.name,
                "domain": validator.domain,
                "confidence": result.confidence,
                "verdict": result.verdict,
                "critique": result.critique,
                "flags": result.flags,
                "repair_suggestion": result.repair_suggestion,
                "objective_score": objective_score,
                "objective_overridden": objective_overridden,
                "validated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(artifact)

        await db.flush()
        logger.info(
            f"Validator {validator.name}: block={block.block_id} "
            f"verdict={result.verdict} confidence={result.confidence:.3f}"
        )
        return decision
