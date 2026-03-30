"""Epoch API — sealed manufacturing epochs with full receipts.

Endpoints:
- GET  /epochs                         — list all epochs
- GET  /epochs/{epoch_id}              — full epoch detail
- GET  /epochs/{epoch_id}/yield        — paginated artifacts from an epoch
- GET  /epochs/{epoch_id}/silicon-ladder — per-model performance breakdown
- GET  /epochs/{epoch_id}/story        — findings + recommendations narrative
- POST /epochs/seal                    — seal an epoch (auth required)
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from swarmchain.db.engine import get_db
from swarmchain.db.models import Block, Attempt, Node, Reward
from swarmchain.db.algorithm import (
    Epoch, EpochArtifact, BlockCost, ConvergenceMetric,
)
from swarmchain.api.auth import require_api_key

router = APIRouter()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class SealEpochRequest(BaseModel):
    epoch_id: str
    tier: str = "Tier 1 Deterministic"
    block_range_start: int
    block_range_end: int
    findings: list[str] = []
    recommendations: list[str] = []


# ---------------------------------------------------------------------------
# GET /epochs — list all epochs
# ---------------------------------------------------------------------------

@router.get("")
async def list_epochs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all epochs ordered by epoch_id descending."""
    count_q = select(func.count(Epoch.id))
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Epoch)
        .order_by(Epoch.epoch_id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(q)
    epochs = result.scalars().all()

    return {
        "epochs": [
            {
                "epoch_id": e.epoch_id,
                "tier": e.tier,
                "status": e.status,
                "honey_count": e.honey_count,
                "jelly_count": e.jelly_count,
                "propolis_count": e.propolis_count,
                "total_attempts": e.total_attempts,
                "total_blocks": e.total_blocks,
                "cost_per_honey": round(e.cost_per_honey, 6),
                "sealed_at": e.sealed_at.isoformat() if e.sealed_at else None,
            }
            for e in epochs
        ],
        "total": total,
    }


# ---------------------------------------------------------------------------
# GET /epochs/{epoch_id} — full epoch detail
# ---------------------------------------------------------------------------

@router.get("/{epoch_id}")
async def get_epoch(epoch_id: str, db: AsyncSession = Depends(get_db)):
    """Full epoch detail including silicon_ladder, findings, and recommendations."""
    result = await db.execute(
        select(Epoch).where(Epoch.epoch_id == epoch_id)
    )
    epoch = result.scalar_one_or_none()
    if not epoch:
        raise HTTPException(404, f"Epoch {epoch_id} not found")

    return {
        "epoch_id": epoch.epoch_id,
        "tier": epoch.tier,
        "status": epoch.status,
        "block_range_start": epoch.block_range_start,
        "block_range_end": epoch.block_range_end,
        "started_at": epoch.started_at.isoformat() if epoch.started_at else None,
        "sealed_at": epoch.sealed_at.isoformat() if epoch.sealed_at else None,
        "honey_count": epoch.honey_count,
        "jelly_count": epoch.jelly_count,
        "propolis_count": epoch.propolis_count,
        "total_attempts": epoch.total_attempts,
        "total_energy": round(epoch.total_energy, 4),
        "total_blocks": epoch.total_blocks,
        "cost_per_honey": round(epoch.cost_per_honey, 6),
        "attempts_per_honey": round(epoch.attempts_per_honey, 4),
        "energy_per_honey": round(epoch.energy_per_honey, 4),
        "convergence_delta": round(epoch.convergence_delta, 6),
        "manifest_hash": epoch.manifest_hash,
        "findings": epoch.findings or [],
        "recommendations": epoch.recommendations or [],
        "silicon_ladder": epoch.silicon_ladder,
        "metadata": epoch.metadata_,
    }


# ---------------------------------------------------------------------------
# GET /epochs/{epoch_id}/yield — paginated artifacts
# ---------------------------------------------------------------------------

@router.get("/{epoch_id}/yield")
async def get_epoch_yield(
    epoch_id: str,
    type: Optional[str] = Query(default=None, description="honey|jelly|propolis"),
    model: Optional[str] = Query(default=None, description="Filter by model_name"),
    transform: Optional[str] = Query(default=None, description="Filter by transform_type"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Query EpochArtifact table with optional filters."""
    # Verify epoch exists
    epoch_check = await db.execute(
        select(Epoch.id).where(Epoch.epoch_id == epoch_id)
    )
    if not epoch_check.scalar_one_or_none():
        raise HTTPException(404, f"Epoch {epoch_id} not found")

    # Build base query
    base = select(EpochArtifact).where(EpochArtifact.epoch_id == epoch_id)
    count_base = (
        select(func.count(EpochArtifact.id))
        .where(EpochArtifact.epoch_id == epoch_id)
    )

    if type:
        base = base.where(EpochArtifact.artifact_type == type)
        count_base = count_base.where(EpochArtifact.artifact_type == type)
    if model:
        base = base.where(EpochArtifact.model_name == model)
        count_base = count_base.where(EpochArtifact.model_name == model)
    if transform:
        base = base.where(EpochArtifact.transform_type == transform)
        count_base = count_base.where(EpochArtifact.transform_type == transform)

    total = (await db.execute(count_base)).scalar() or 0
    result = await db.execute(
        base.order_by(EpochArtifact.created_at.desc()).limit(limit).offset(offset)
    )
    artifacts = result.scalars().all()

    return {
        "epoch_id": epoch_id,
        "artifacts": [
            {
                "artifact_id": a.artifact_id,
                "artifact_type": a.artifact_type,
                "task_id": a.task_id,
                "transform_type": a.transform_type,
                "model_name": a.model_name,
                "node_id": a.node_id,
                "score": round(a.score, 4),
                "energy_cost": round(a.energy_cost, 4),
                "block_id": a.block_id,
                "attempt_id": a.attempt_id,
                "storage_url": a.storage_url,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in artifacts
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# GET /epochs/{epoch_id}/silicon-ladder — per-model performance
# ---------------------------------------------------------------------------

@router.get("/{epoch_id}/silicon-ladder")
async def get_silicon_ladder(epoch_id: str, db: AsyncSession = Depends(get_db)):
    """Return the silicon ladder for this epoch.

    If pre-computed silicon_ladder is stored on the Epoch record, return it.
    Otherwise, compute from EpochArtifact: group by model_name, compute
    honey count, honey rate, avg energy per honey, total attempts.
    """
    result = await db.execute(
        select(Epoch).where(Epoch.epoch_id == epoch_id)
    )
    epoch = result.scalar_one_or_none()
    if not epoch:
        raise HTTPException(404, f"Epoch {epoch_id} not found")

    # If pre-computed, return it
    if epoch.silicon_ladder:
        return {
            "epoch_id": epoch_id,
            "silicon_ladder": epoch.silicon_ladder,
            "source": "stored",
        }

    # Compute from EpochArtifact
    result = await db.execute(
        select(EpochArtifact).where(EpochArtifact.epoch_id == epoch_id)
    )
    artifacts = result.scalars().all()

    if not artifacts:
        return {
            "epoch_id": epoch_id,
            "silicon_ladder": [],
            "source": "computed",
        }

    # Group by model_name
    model_stats: dict[str, dict] = {}
    for a in artifacts:
        m = a.model_name
        if m not in model_stats:
            model_stats[m] = {
                "model": m,
                "honey_count": 0,
                "jelly_count": 0,
                "propolis_count": 0,
                "total_attempts": 0,
                "total_energy": 0.0,
            }
        model_stats[m]["total_attempts"] += 1
        model_stats[m]["total_energy"] += a.energy_cost
        if a.artifact_type == "honey":
            model_stats[m]["honey_count"] += 1
        elif a.artifact_type == "jelly":
            model_stats[m]["jelly_count"] += 1
        elif a.artifact_type == "propolis":
            model_stats[m]["propolis_count"] += 1

    ladder = []
    for m, s in model_stats.items():
        total = s["total_attempts"]
        honey = s["honey_count"]
        ladder.append({
            "model": m,
            "honey_count": honey,
            "jelly_count": s["jelly_count"],
            "propolis_count": s["propolis_count"],
            "total_attempts": total,
            "honey_rate": round(honey / max(total, 1), 4),
            "avg_energy_per_honey": round(
                s["total_energy"] / max(honey, 1), 4
            ),
            "total_energy": round(s["total_energy"], 4),
        })

    # Sort by honey_rate descending
    ladder.sort(key=lambda x: x["honey_rate"], reverse=True)

    return {
        "epoch_id": epoch_id,
        "silicon_ladder": ladder,
        "source": "computed",
    }


# ---------------------------------------------------------------------------
# GET /epochs/{epoch_id}/story — narrative from findings + recommendations
# ---------------------------------------------------------------------------

@router.get("/{epoch_id}/story")
async def get_epoch_story(epoch_id: str, db: AsyncSession = Depends(get_db)):
    """Return findings + recommendations as a structured narrative object."""
    result = await db.execute(
        select(Epoch).where(Epoch.epoch_id == epoch_id)
    )
    epoch = result.scalar_one_or_none()
    if not epoch:
        raise HTTPException(404, f"Epoch {epoch_id} not found")

    findings = epoch.findings or []
    recommendations = epoch.recommendations or []

    return {
        "epoch_id": epoch_id,
        "tier": epoch.tier,
        "status": epoch.status,
        "narrative": {
            "title": f"Epoch {epoch_id} — {epoch.tier}",
            "summary": (
                f"Sealed with {epoch.honey_count} honey, "
                f"{epoch.jelly_count} jelly, {epoch.propolis_count} propolis "
                f"across {epoch.total_blocks} blocks. "
                f"Cost per honey: ${epoch.cost_per_honey:.6f}."
            ),
            "findings": [
                {"index": i + 1, "insight": f}
                for i, f in enumerate(findings)
            ],
            "recommendations": [
                {"index": i + 1, "action": r}
                for i, r in enumerate(recommendations)
            ],
            "convergence_delta": round(epoch.convergence_delta, 6),
        },
        "sealed_at": epoch.sealed_at.isoformat() if epoch.sealed_at else None,
    }


# ---------------------------------------------------------------------------
# POST /epochs/seal — seal an epoch (auth required)
# ---------------------------------------------------------------------------

@router.post("/seal", dependencies=[Depends(require_api_key)])
async def seal_epoch(req: SealEpochRequest, db: AsyncSession = Depends(get_db)):
    """Seal an epoch by computing real stats from blocks in range.

    Computes yield counts, economics, silicon ladder, and convergence delta
    from actual block data in the specified range.
    """
    # Check if epoch already exists
    existing = await db.execute(
        select(Epoch).where(Epoch.epoch_id == req.epoch_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Epoch {req.epoch_id} already exists")

    # Fetch blocks in range (by sequence id)
    result = await db.execute(
        select(Block)
        .where(Block.id >= req.block_range_start)
        .where(Block.id <= req.block_range_end)
        .order_by(Block.id)
    )
    blocks = result.scalars().all()
    block_ids = [b.block_id for b in blocks]
    total_blocks = len(blocks)

    if total_blocks == 0:
        raise HTTPException(400, "No blocks found in specified range")

    # Fetch all attempts for blocks in range
    result = await db.execute(
        select(Attempt).where(Attempt.block_id.in_(block_ids))
    )
    attempts = result.scalars().all()
    total_attempts = len(attempts)

    # Compute yield counts from attempts
    honey_count = 0
    jelly_count = 0
    propolis_count = 0
    total_energy = 0.0

    # Per-model stats for silicon ladder
    model_stats: dict[str, dict] = {}

    for att in attempts:
        total_energy += att.energy_cost

        # Classify by score: honey >= 0.9, jelly >= 0.5, propolis < 0.5
        if att.score >= 0.9:
            grade = "honey"
            honey_count += 1
        elif att.score >= 0.5:
            grade = "jelly"
            jelly_count += 1
        else:
            grade = "propolis"
            propolis_count += 1

        # Build silicon ladder from node metadata (model_name)
        model_name = "unknown"
        if att.metadata_:
            model_name = att.metadata_.get("model_name", "unknown")
        elif att.node:
            pass  # lazy load not available in async

        # Look up node for model info
        if model_name == "unknown":
            node_result = await db.execute(
                select(Node).where(Node.node_id == att.node_id)
            )
            node = node_result.scalar_one_or_none()
            if node and node.metadata_:
                model_name = node.metadata_.get("model_name", att.node_id)
            else:
                model_name = att.node_id

        if model_name not in model_stats:
            model_stats[model_name] = {
                "model": model_name,
                "honey_count": 0,
                "jelly_count": 0,
                "propolis_count": 0,
                "total_attempts": 0,
                "total_energy": 0.0,
            }
        model_stats[model_name]["total_attempts"] += 1
        model_stats[model_name]["total_energy"] += att.energy_cost
        if grade == "honey":
            model_stats[model_name]["honey_count"] += 1
        elif grade == "jelly":
            model_stats[model_name]["jelly_count"] += 1
        else:
            model_stats[model_name]["propolis_count"] += 1

    # Compute economics
    cost_per_honey = total_energy / max(honey_count, 1)
    attempts_per_honey = total_attempts / max(honey_count, 1)
    energy_per_honey = total_energy / max(honey_count, 1)

    # Compute convergence delta from the most recent ConvergenceMetric
    convergence_delta = 0.0
    result = await db.execute(
        select(ConvergenceMetric)
        .order_by(ConvergenceMetric.window_end.desc())
        .limit(2)
    )
    conv_metrics = result.scalars().all()
    if len(conv_metrics) >= 2:
        convergence_delta = (
            conv_metrics[0].avg_cost_per_honey - conv_metrics[1].avg_cost_per_honey
        )

    # Build silicon ladder
    silicon_ladder = []
    for m, s in model_stats.items():
        total = s["total_attempts"]
        honey = s["honey_count"]
        silicon_ladder.append({
            "model": m,
            "honey_count": honey,
            "jelly_count": s["jelly_count"],
            "propolis_count": s["propolis_count"],
            "total_attempts": total,
            "honey_rate": round(honey / max(total, 1), 4),
            "avg_energy_per_honey": round(
                s["total_energy"] / max(honey, 1), 4
            ),
            "total_energy": round(s["total_energy"], 4),
        })
    silicon_ladder.sort(key=lambda x: x["honey_rate"], reverse=True)

    # Compute manifest hash (SHA256 over epoch data)
    manifest_data = {
        "epoch_id": req.epoch_id,
        "tier": req.tier,
        "block_range": [req.block_range_start, req.block_range_end],
        "total_blocks": total_blocks,
        "honey_count": honey_count,
        "jelly_count": jelly_count,
        "propolis_count": propolis_count,
        "total_attempts": total_attempts,
        "total_energy": total_energy,
        "silicon_ladder": silicon_ladder,
        "findings": req.findings,
        "recommendations": req.recommendations,
    }
    manifest_json = json.dumps(manifest_data, sort_keys=True, separators=(",", ":"), default=str)
    manifest_hash = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()

    now = datetime.now(timezone.utc)

    # Create and persist the sealed epoch
    epoch = Epoch(
        epoch_id=req.epoch_id,
        tier=req.tier,
        status="sealed",
        block_range_start=req.block_range_start,
        block_range_end=req.block_range_end,
        started_at=blocks[0].start_time if blocks else now,
        sealed_at=now,
        honey_count=honey_count,
        jelly_count=jelly_count,
        propolis_count=propolis_count,
        total_attempts=total_attempts,
        total_energy=total_energy,
        total_blocks=total_blocks,
        cost_per_honey=cost_per_honey,
        attempts_per_honey=attempts_per_honey,
        energy_per_honey=energy_per_honey,
        convergence_delta=convergence_delta,
        manifest_hash=manifest_hash,
        findings=req.findings,
        recommendations=req.recommendations,
        silicon_ladder=silicon_ladder,
    )
    db.add(epoch)
    await db.flush()

    return {
        "epoch_id": epoch.epoch_id,
        "tier": epoch.tier,
        "status": epoch.status,
        "total_blocks": epoch.total_blocks,
        "honey_count": epoch.honey_count,
        "jelly_count": epoch.jelly_count,
        "propolis_count": epoch.propolis_count,
        "total_attempts": epoch.total_attempts,
        "total_energy": round(epoch.total_energy, 4),
        "cost_per_honey": round(epoch.cost_per_honey, 6),
        "attempts_per_honey": round(epoch.attempts_per_honey, 4),
        "energy_per_honey": round(epoch.energy_per_honey, 4),
        "convergence_delta": round(epoch.convergence_delta, 6),
        "manifest_hash": epoch.manifest_hash,
        "silicon_ladder": epoch.silicon_ladder,
        "findings": epoch.findings,
        "recommendations": epoch.recommendations,
        "sealed_at": epoch.sealed_at.isoformat() if epoch.sealed_at else None,
    }
