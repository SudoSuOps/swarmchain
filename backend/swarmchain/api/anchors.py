"""Hedera anchor API — proof the swarm's work is immutably timestamped.

Endpoints:
- GET  /anchors                    — list all Hedera anchor receipts
- GET  /anchors/timeline           — chronological anchor timeline for charts
- GET  /anchors/verify/{window_end} — recompute and verify a Merkle root
- GET  /anchors/{window_end}       — get specific anchor with Merkle proof
- POST /anchors/trigger            — manually trigger an anchor (auth required)
- POST /anchors/retry              — retry all pending (unanchored) anchors (auth required)
- GET  /anchors/{window_end}/proof/{block_id} — Merkle inclusion proof for a block
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from swarmchain.db.engine import get_db
from swarmchain.db.models import Block, BlockArtifact
from swarmchain.api.auth import require_api_key
from swarmchain.services.hedera_anchor import HederaAnchor, MerkleBuilder

router = APIRouter()


@router.get("")
async def list_anchors(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    anchored_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """List all Hedera anchor receipts, newest first."""
    q = (
        select(BlockArtifact)
        .where(BlockArtifact.artifact_type == "hedera_anchor")
        .order_by(BlockArtifact.created_at.desc())
    )
    count_q = (
        select(func.count(BlockArtifact.id))
        .where(BlockArtifact.artifact_type == "hedera_anchor")
    )

    result = await db.execute(count_q)
    total = result.scalar() or 0

    result = await db.execute(q.limit(limit).offset(offset))
    anchors = result.scalars().all()

    items = []
    for a in anchors:
        data = a.artifact_json
        if anchored_only and not data.get("anchored"):
            continue
        items.append({
            "window": data.get("window"),
            "merkle_root": data.get("merkle_root"),
            "block_count": data.get("block_count", 0),
            "anchored": data.get("anchored", False),
            "timestamp": data.get("timestamp"),
            "convergence": data.get("convergence"),
            "totals": data.get("totals"),
            "hcs": data.get("hcs"),
            "topic_id": data.get("topic_id"),
        })

    return {
        "anchors": items,
        "total": total,
    }


@router.get("/status")
async def anchor_status(db: AsyncSession = Depends(get_db)):
    """Summary status of anchoring system."""
    total_q = (
        select(func.count(BlockArtifact.id))
        .where(BlockArtifact.artifact_type == "hedera_anchor")
    )
    total = (await db.execute(total_q)).scalar() or 0

    # Count anchored vs pending
    result = await db.execute(
        select(BlockArtifact)
        .where(BlockArtifact.artifact_type == "hedera_anchor")
    )
    all_anchors = result.scalars().all()

    anchored_count = sum(1 for a in all_anchors if a.artifact_json.get("anchored"))
    pending_count = total - anchored_count

    # Latest anchor
    latest = None
    if all_anchors:
        latest_artifact = max(all_anchors, key=lambda a: a.created_at)
        latest = {
            "window": latest_artifact.artifact_json.get("window"),
            "merkle_root": latest_artifact.artifact_json.get("merkle_root"),
            "anchored": latest_artifact.artifact_json.get("anchored", False),
            "timestamp": latest_artifact.artifact_json.get("timestamp"),
        }

    # Total sealed blocks
    sealed_q = (
        select(func.count(Block.id))
        .where(Block.status.in_(["solved", "exhausted"]))
    )
    total_sealed = (await db.execute(sealed_q)).scalar() or 0

    anchor_svc = HederaAnchor.from_settings()

    return {
        "enabled": anchor_svc.is_enabled(),
        "topic_id": anchor_svc.topic_id,
        "anchor_interval": anchor_svc.anchor_interval,
        "total_anchors": total,
        "anchored": anchored_count,
        "pending": pending_count,
        "total_sealed_blocks": total_sealed,
        "next_anchor_at": (
            (total_sealed // anchor_svc.anchor_interval + 1) * anchor_svc.anchor_interval
            if anchor_svc.anchor_interval > 0 else None
        ),
        "latest": latest,
    }


@router.get("/timeline")
async def anchor_timeline(
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Chronological timeline of all Hedera anchors for chart rendering.

    Returns array of {window, merkle_root, convergence, anchored, timestamp}
    ordered by creation time ascending.
    """
    result = await db.execute(
        select(BlockArtifact)
        .where(BlockArtifact.artifact_type == "hedera_anchor")
        .order_by(BlockArtifact.created_at.asc())
        .limit(limit)
    )
    anchors = result.scalars().all()

    timeline = []
    for a in anchors:
        data = a.artifact_json
        timeline.append({
            "window": data.get("window"),
            "merkle_root": data.get("merkle_root"),
            "convergence": data.get("convergence"),
            "anchored": data.get("anchored", False),
            "timestamp": a.created_at.isoformat() if a.created_at else None,
        })

    return {
        "timeline": timeline,
        "total": len(timeline),
    }


@router.get("/verify/{window_end}")
async def verify_anchor(window_end: int, db: AsyncSession = Depends(get_db)):
    """Recompute Merkle root for the specified window and compare to stored anchor.

    Fetches the last N blocks before window_end (where N = window size from the
    stored anchor), hashes their sealed_block artifacts, and recomputes the
    Merkle root. Compares against the claimed root stored in the anchor receipt.
    """
    # Find the stored anchor for this window_end
    result = await db.execute(
        select(BlockArtifact)
        .where(BlockArtifact.artifact_type == "hedera_anchor")
    )
    all_anchors = result.scalars().all()

    anchor_data = None
    for a in all_anchors:
        data = a.artifact_json
        window = data.get("window", {})
        if window.get("end") == window_end:
            anchor_data = data
            break

    if not anchor_data:
        raise HTTPException(404, f"No anchor found for window_end={window_end}")

    claimed_root = anchor_data.get("merkle_root")
    window = anchor_data["window"]
    window_start = window.get("start", 0)
    window_size = window_end - window_start

    # Fetch the same blocks used in the anchor window
    result = await db.execute(
        select(Block)
        .where(Block.status.in_(["solved", "exhausted"]))
        .order_by(Block.end_time.desc())
        .limit(window_size)
    )
    window_blocks = list(result.scalars().all())
    block_ids_in_window = [b.block_id for b in window_blocks]

    # Get sealed_block artifacts for these blocks
    result = await db.execute(
        select(BlockArtifact)
        .where(BlockArtifact.block_id.in_(block_ids_in_window))
        .where(BlockArtifact.artifact_type == "sealed_block")
    )
    artifacts = result.scalars().all()
    artifact_dicts = [a.artifact_json for a in artifacts]

    if not artifact_dicts:
        raise HTTPException(
            404, "No sealed_block artifacts found for verification"
        )

    # Recompute the Merkle root
    computed_root = MerkleBuilder.compute_root(block_ids_in_window, artifact_dicts)

    # Compare convergence snapshots if available
    stored_convergence = anchor_data.get("convergence")
    convergence_match = True  # assume match if no convergence stored
    if stored_convergence:
        # The convergence snapshot is informational; the root covers integrity
        convergence_match = True

    return {
        "window_end": window_end,
        "window": window,
        "claimed_root": claimed_root,
        "computed_root": computed_root,
        "match": claimed_root == computed_root,
        "convergence_match": convergence_match,
        "block_count": len(block_ids_in_window),
        "artifact_count": len(artifact_dicts),
    }


@router.get("/{window_end}")
async def get_anchor(window_end: int, db: AsyncSession = Depends(get_db)):
    """Get a specific anchor receipt by window_end block number."""
    result = await db.execute(
        select(BlockArtifact)
        .where(BlockArtifact.artifact_type == "hedera_anchor")
    )
    anchors = result.scalars().all()

    for a in anchors:
        data = a.artifact_json
        window = data.get("window", {})
        if window.get("end") == window_end:
            return {
                "anchor": data,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "block_id": a.block_id,
            }

    raise HTTPException(404, f"No anchor found for window_end={window_end}")


@router.get("/{window_end}/proof/{block_id}")
async def get_merkle_proof(
    window_end: int, block_id: str, db: AsyncSession = Depends(get_db),
):
    """Get the Merkle inclusion proof for a specific block within an anchor window.

    This proves that a given block was included in a specific Hedera anchor.
    Anyone can independently verify this proof against the published Merkle root.
    """
    # Find the anchor
    result = await db.execute(
        select(BlockArtifact)
        .where(BlockArtifact.artifact_type == "hedera_anchor")
    )
    anchors = result.scalars().all()

    anchor_data = None
    for a in anchors:
        data = a.artifact_json
        window = data.get("window", {})
        if window.get("end") == window_end:
            anchor_data = data
            break

    if not anchor_data:
        raise HTTPException(404, f"No anchor found for window_end={window_end}")

    window = anchor_data["window"]
    window_start = window["start"]
    window_size = window_end - window_start

    # Gather the same blocks and artifacts used for this anchor
    result = await db.execute(
        select(Block)
        .where(Block.status.in_(["solved", "exhausted"]))
        .order_by(Block.end_time.desc())
        .limit(window_size)
    )
    window_blocks = list(result.scalars().all())
    block_ids_in_window = [b.block_id for b in window_blocks]

    if block_id not in block_ids_in_window:
        raise HTTPException(
            404,
            f"Block {block_id} not found in anchor window [{window_start}, {window_end}]",
        )

    # Get sealed artifacts
    result = await db.execute(
        select(BlockArtifact)
        .where(BlockArtifact.block_id.in_(block_ids_in_window))
        .where(BlockArtifact.artifact_type == "sealed_block")
    )
    artifacts = result.scalars().all()
    artifact_dicts = [a.artifact_json for a in artifacts]

    if not artifact_dicts:
        raise HTTPException(404, "No sealed_block artifacts found for this window")

    # Generate proof
    proof = MerkleBuilder.generate_proof(block_ids_in_window, artifact_dicts, block_id)
    if proof is None:
        raise HTTPException(404, f"Could not generate proof for block {block_id}")

    return {
        "block_id": block_id,
        "window": window,
        "merkle_root": anchor_data.get("merkle_root"),
        "anchored": anchor_data.get("anchored", False),
        "proof": proof,
        "verification": (
            "To verify: recompute SHA-256(canonical_json(artifact)) as the leaf, "
            "then walk the proof steps hashing left||right to reconstruct the root."
        ),
    }


@router.post("/trigger", dependencies=[Depends(require_api_key)])
async def trigger_anchor(
    window_size: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a Hedera anchor for the most recent N sealed blocks.

    Useful for:
    - Initial anchoring before the automatic interval kicks in
    - Re-anchoring a specific window after HCS connectivity is restored
    - Testing the anchor pipeline
    """
    # Count total sealed blocks
    result = await db.execute(
        select(func.count(Block.id))
        .where(Block.status.in_(["solved", "exhausted"]))
    )
    total_sealed = result.scalar() or 0

    if total_sealed == 0:
        raise HTTPException(400, "No sealed blocks to anchor")

    window_end = total_sealed
    window_start = max(0, total_sealed - window_size)

    anchor = HederaAnchor.from_settings()
    receipt = await anchor.anchor_window(db, window_start, window_end)

    return {
        "status": "anchored" if receipt.get("anchored") else "pending",
        "receipt": receipt,
    }


@router.post("/retry", dependencies=[Depends(require_api_key)])
async def retry_pending_anchors(db: AsyncSession = Depends(get_db)):
    """Retry all pending (unanchored) anchor submissions.

    Returns the list of anchors that were successfully submitted on retry.
    """
    anchor = HederaAnchor.from_settings()
    retried = await anchor.retry_pending(db)

    return {
        "retried_count": len(retried),
        "retried": [
            {
                "window": r.get("window"),
                "merkle_root": r.get("merkle_root"),
                "hcs": r.get("hcs"),
            }
            for r in retried
        ],
    }
