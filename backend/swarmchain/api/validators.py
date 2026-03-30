"""Validator API — inspect domain validator decisions and available validators."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.engine import get_db
from swarmchain.db.models import Block, ValidatorDecision
from swarmchain.services.domain_validators import list_validators, get_validator

router = APIRouter()


@router.get("/validators")
async def get_validators():
    """List all registered domain validators."""
    return {
        "validators": list_validators(),
        "note": "Deterministic verification remains the source-of-truth anchor. "
                "Domain validators assist convergence but may never override objective checks.",
    }


@router.get("/blocks/{block_id}/validations")
async def get_block_validations(block_id: str, db: AsyncSession = Depends(get_db)):
    """Get all validator decisions for a block.

    Shows domain validator confidence, verdict, critique, flags, and repair suggestions.
    Also shows whether the objective score was preserved (it always must be).
    """
    result = await db.execute(select(Block).where(Block.block_id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(404, f"Block {block_id} not found")

    result = await db.execute(
        select(ValidatorDecision)
        .where(ValidatorDecision.block_id == block_id)
        .order_by(ValidatorDecision.created_at.desc())
    )
    decisions = result.scalars().all()

    return {
        "block_id": block_id,
        "domain": block.domain,
        "has_validator": get_validator(block.domain) is not None,
        "decisions": [
            {
                "validator_name": d.validator_name,
                "domain": d.domain,
                "confidence": d.confidence,
                "verdict": d.verdict,
                "critique": d.critique,
                "flags": d.flags,
                "repair_suggestion": d.repair_suggestion,
                "objective_score": d.objective_score,
                "objective_overridden": d.objective_overridden,
                "raw_output": d.raw_output,
                "created_at": d.created_at.isoformat(),
            }
            for d in decisions
        ],
    }
