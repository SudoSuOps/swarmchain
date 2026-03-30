"""Hedera HCS anchoring — immutable proof the swarm converged.

Every 50 sealed blocks, we:
1. Compute a Merkle root over all block artifact hashes in the window
2. Snapshot convergence metrics (cost/honey, solve rate, energy)
3. Publish the root + snapshot to a Hedera Consensus Service topic
4. Store the anchor receipt as a BlockArtifact + SwarmEvent

The Merkle root is deterministic: same artifacts, same root, always.
The HCS timestamp is consensus-ordered: you cannot backdate or reorder.
Together they prove WHAT the swarm produced and WHEN.

HCS transport is pluggable — works without the Hedera SDK installed.
If the SDK or REST endpoint is unreachable, anchors are stored locally
with anchored=false and can be submitted later via POST /anchors/trigger.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from swarmchain.db.models import Block, BlockArtifact
from swarmchain.db.algorithm import SwarmEvent, BlockCost, ConvergenceMetric
from swarmchain.config import get_settings

logger = logging.getLogger("swarmchain.hedera_anchor")


# ---------------------------------------------------------------------------
# Merkle tree
# ---------------------------------------------------------------------------

class MerkleBuilder:
    """Builds a SHA-256 Merkle tree from block artifact hashes.

    The tree is deterministic:
    - Leaves are SHA-256 hashes of the canonical JSON serialisation of each
      artifact, sorted by block_id to guarantee ordering.
    - Odd-length layers are padded by duplicating the last element.
    - Internal nodes are SHA-256(left || right) where || is concatenation.

    Example (doctest-friendly)::

        >>> MerkleBuilder.compute_root(
        ...     ["blk_001", "blk_002"],
        ...     [{"block_id": "blk_001", "score": 1.0},
        ...      {"block_id": "blk_002", "score": 0.8}],
        ... )  # doctest: +SKIP
        # Returns a deterministic 64-char hex string.

    Worked example with two leaves::

        leaf_0 = sha256(canonical_json(artifact_0))  # e.g. 'a1b2...'
        leaf_1 = sha256(canonical_json(artifact_1))  # e.g. 'c3d4...'
        root   = sha256(leaf_0 + leaf_1)             # e.g. 'e5f6...'

    Verification: anyone with the artifacts can recompute the same root.
    """

    @staticmethod
    def _sha256(data: str) -> str:
        """SHA-256 hex digest of a UTF-8 string."""
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_json(obj: Any) -> str:
        """Deterministic JSON — sorted keys, no whitespace, no trailing floats."""
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)

    @classmethod
    def compute_root(cls, block_ids: list[str], artifacts: list[dict]) -> str:
        """Compute the SHA-256 Merkle root of the given artifacts.

        Args:
            block_ids: ordered list of block IDs in the window (used for
                       sorting artifacts into deterministic order).
            artifacts: list of artifact dicts — one per block.

        Returns:
            64-character hex Merkle root string prefixed with '0x'.

        Raises:
            ValueError: if artifacts list is empty.
        """
        if not artifacts:
            raise ValueError("Cannot compute Merkle root of empty artifact list")

        # Sort artifacts by block_id for deterministic ordering
        id_order = {bid: idx for idx, bid in enumerate(block_ids)}
        sorted_artifacts = sorted(
            artifacts,
            key=lambda a: id_order.get(a.get("block_id", ""), 0),
        )

        # Build leaf hashes
        leaves = [cls._sha256(cls._canonical_json(a)) for a in sorted_artifacts]

        # Single leaf — root is the hash of that leaf
        if len(leaves) == 1:
            return f"0x{leaves[0]}"

        # Pad odd-length layer
        if len(leaves) % 2 != 0:
            leaves.append(leaves[-1])

        # Reduce to root
        while len(leaves) > 1:
            next_level: list[str] = []
            for i in range(0, len(leaves), 2):
                combined = leaves[i] + leaves[i + 1]
                next_level.append(cls._sha256(combined))
            leaves = next_level
            if len(leaves) > 1 and len(leaves) % 2 != 0:
                leaves.append(leaves[-1])

        return f"0x{leaves[0]}"

    @classmethod
    def generate_proof(cls, block_ids: list[str], artifacts: list[dict],
                       target_block_id: str) -> dict | None:
        """Generate a Merkle inclusion proof for a specific block.

        Returns a dict with:
            leaf_hash: the hash of the target artifact
            proof: list of {hash, position} steps
            root: the Merkle root

        Returns None if the target block is not in the artifact list.
        """
        if not artifacts:
            return None

        id_order = {bid: idx for idx, bid in enumerate(block_ids)}
        sorted_artifacts = sorted(
            artifacts,
            key=lambda a: id_order.get(a.get("block_id", ""), 0),
        )

        # Find target index
        target_idx = None
        for i, a in enumerate(sorted_artifacts):
            if a.get("block_id") == target_block_id:
                target_idx = i
                break
        if target_idx is None:
            return None

        # Build leaf hashes
        leaves = [cls._sha256(cls._canonical_json(a)) for a in sorted_artifacts]
        target_leaf = leaves[target_idx]

        if len(leaves) == 1:
            return {
                "leaf_hash": target_leaf,
                "proof": [],
                "root": f"0x{target_leaf}",
            }

        # Pad odd-length layer
        if len(leaves) % 2 != 0:
            leaves.append(leaves[-1])

        proof_steps: list[dict] = []
        idx = target_idx

        while len(leaves) > 1:
            if idx % 2 == 0:
                sibling = leaves[idx + 1] if idx + 1 < len(leaves) else leaves[idx]
                proof_steps.append({"hash": sibling, "position": "right"})
            else:
                sibling = leaves[idx - 1]
                proof_steps.append({"hash": sibling, "position": "left"})

            next_level: list[str] = []
            for i in range(0, len(leaves), 2):
                combined = leaves[i] + leaves[i + 1]
                next_level.append(cls._sha256(combined))
            leaves = next_level
            idx = idx // 2

            if len(leaves) > 1 and len(leaves) % 2 != 0:
                leaves.append(leaves[-1])

        return {
            "leaf_hash": target_leaf,
            "proof": proof_steps,
            "root": f"0x{leaves[0]}",
        }

    @classmethod
    def verify_proof(cls, leaf_hash: str, proof: list[dict], expected_root: str) -> bool:
        """Verify a Merkle inclusion proof.

        Args:
            leaf_hash: the SHA-256 hash of the leaf artifact
            proof: list of {hash, position} steps from generate_proof
            expected_root: the expected Merkle root (with or without '0x' prefix)

        Returns:
            True if the proof is valid.
        """
        current = leaf_hash
        for step in proof:
            if step["position"] == "left":
                current = cls._sha256(step["hash"] + current)
            else:
                current = cls._sha256(current + step["hash"])

        expected = expected_root.removeprefix("0x")
        return current == expected


# ---------------------------------------------------------------------------
# HCS transport (pluggable)
# ---------------------------------------------------------------------------

class HCSTransport:
    """Pluggable transport for Hedera Consensus Service submission.

    Primary: HTTP POST to the Hedera REST API / mirror node.
    Fallback: local storage with anchored=false for later retry.
    """

    @staticmethod
    async def submit(topic_id: str, message: str,
                     operator_id: str, operator_key: str) -> dict:
        """Submit a message to an HCS topic.

        Returns a dict with at minimum:
            success: bool
            sequence_number: int | None
            consensus_timestamp: str | None
            transaction_id: str | None
            error: str | None
        """
        if not operator_id or not operator_key:
            logger.warning("Hedera credentials not configured — storing anchor locally")
            return {
                "success": False,
                "sequence_number": None,
                "consensus_timestamp": None,
                "transaction_id": None,
                "error": "hedera_credentials_not_configured",
            }

        # Attempt submission via Hedera REST API (testnet/mainnet)
        # The Hedera REST API for submitting consensus messages requires
        # a signed transaction. Without the SDK, we use the hashgraph
        # REST proxy if available, or fall back gracefully.
        try:
            result = await HCSTransport._submit_via_rest(
                topic_id, message, operator_id, operator_key,
            )
            return result
        except Exception as e:
            logger.warning(f"HCS REST submission failed: {e} — storing locally")
            return {
                "success": False,
                "sequence_number": None,
                "consensus_timestamp": None,
                "transaction_id": None,
                "error": str(e),
            }

    @staticmethod
    async def _submit_via_rest(topic_id: str, message: str,
                               operator_id: str, operator_key: str) -> dict:
        """Submit via Hedera mirror node REST API.

        NOTE: Direct HCS message submission requires a signed transaction,
        which needs the Hedera SDK. This method attempts to use a local
        proxy or the Hedera SDK REST wrapper if available. If neither is
        present, it returns a failure result that triggers local storage.
        """
        # Try local Hedera relay proxy (common pattern in SwarmChain infra)
        relay_url = f"http://localhost:5551/api/v1/topics/{topic_id}/messages"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    relay_url,
                    json={
                        "message": message,
                        "operator_id": operator_id,
                    },
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "success": True,
                        "sequence_number": data.get("sequenceNumber"),
                        "consensus_timestamp": data.get("consensusTimestamp"),
                        "transaction_id": data.get("transactionId"),
                        "error": None,
                    }
            except httpx.ConnectError:
                pass  # Relay not running — fall through

        # Try Hedera mirror node query to verify topic exists
        # (submission requires SDK — record the intent)
        mirror_url = f"https://mainnet.mirrornode.hedera.com/api/v1/topics/{topic_id}/messages"
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(mirror_url, params={"limit": 1, "order": "desc"})
                if resp.status_code == 200:
                    logger.info(
                        f"HCS topic {topic_id} verified on mirror node — "
                        f"submission requires SDK or relay proxy"
                    )
            except Exception:
                pass

        # Cannot submit without SDK or relay — return failure for local storage
        raise ConnectionError(
            "No Hedera SDK or relay proxy available. "
            "Install hedera-sdk-py or run the HCS relay proxy on :5551."
        )


# ---------------------------------------------------------------------------
# Anchor service
# ---------------------------------------------------------------------------

class HederaAnchor:
    """Anchors convergence proofs to Hedera Consensus Service.

    Every anchor_interval sealed blocks, we:
    1. Gather all sealed block artifacts in the window
    2. Compute a Merkle root over those artifacts
    3. Gather convergence metrics for the window
    4. Build the anchor payload
    5. Submit to HCS (or store locally if HCS unavailable)
    6. Store the anchor receipt as a SwarmEvent + BlockArtifact
    """

    def __init__(self, operator_id: str = "", operator_key: str = "",
                 topic_id: str = "0.0.10291838", anchor_interval: int = 50):
        self.operator_id = operator_id
        self.operator_key = operator_key
        self.topic_id = topic_id
        self.anchor_interval = anchor_interval

    @classmethod
    def from_settings(cls) -> "HederaAnchor":
        """Create from application settings."""
        s = get_settings()
        return cls(
            operator_id=s.hedera_operator_id,
            operator_key=s.hedera_operator_key,
            topic_id=s.hedera_topic_id,
            anchor_interval=s.hedera_anchor_interval,
        )

    def is_enabled(self) -> bool:
        """Anchoring is enabled if operator_id is configured."""
        return bool(self.operator_id)

    async def maybe_anchor(self, db: AsyncSession, total_sealed: int) -> dict | None:
        """Check if we should anchor at this block count, and do it if so.

        Called after each block seal. Returns the anchor receipt if an anchor
        was performed, None otherwise.
        """
        if self.anchor_interval <= 0:
            return None

        if total_sealed % self.anchor_interval != 0 or total_sealed == 0:
            return None

        window_end = total_sealed
        window_start = max(0, total_sealed - self.anchor_interval)

        logger.info(
            f"Hedera anchor triggered: window [{window_start}, {window_end}]"
        )

        return await self.anchor_window(db, window_start, window_end)

    async def anchor_window(self, db: AsyncSession,
                            window_start: int, window_end: int) -> dict:
        """Anchor a window of sealed blocks to Hedera HCS.

        Steps:
        1. Gather all sealed block artifacts in [window_start, window_end]
        2. Compute Merkle root of artifacts
        3. Gather convergence metrics for this window
        4. Build anchor payload (merkle_root + convergence + energy + cost)
        5. Submit to Hedera HCS topic
        6. Store anchor receipt as SwarmEvent + BlockArtifact
        7. Return anchor receipt
        """
        # 1. Gather sealed blocks in the window (by seal order)
        window_size = window_end - window_start
        result = await db.execute(
            select(Block)
            .where(Block.status.in_(["solved", "exhausted"]))
            .order_by(Block.end_time.desc())
            .limit(window_size)
        )
        window_blocks = list(result.scalars().all())

        if not window_blocks:
            logger.warning(f"No sealed blocks found for window [{window_start}, {window_end}]")
            return self._empty_receipt(window_start, window_end, "no_sealed_blocks")

        block_ids = [b.block_id for b in window_blocks]

        # Gather artifacts (sealed_block type) for these blocks
        result = await db.execute(
            select(BlockArtifact)
            .where(BlockArtifact.block_id.in_(block_ids))
            .where(BlockArtifact.artifact_type == "sealed_block")
        )
        artifacts = result.scalars().all()
        artifact_dicts = [a.artifact_json for a in artifacts]

        if not artifact_dicts:
            logger.warning(f"No sealed_block artifacts for window [{window_start}, {window_end}]")
            return self._empty_receipt(window_start, window_end, "no_artifacts")

        # 2. Compute Merkle root
        merkle_root = MerkleBuilder.compute_root(block_ids, artifact_dicts)

        # 3. Gather convergence metrics for this window
        convergence_data = await self._gather_convergence(db, window_start, window_end)

        # 4. Gather cost/energy totals
        totals = await self._gather_totals(db, block_ids, window_blocks)

        # 5. Build anchor payload
        now = datetime.now(timezone.utc)
        payload = {
            "protocol": "swarmchain-v1",
            "window": {
                "start": window_start,
                "end": window_end,
            },
            "merkle_root": merkle_root,
            "block_count": len(artifact_dicts),
            "convergence": convergence_data,
            "totals": totals,
            "timestamp": now.isoformat(),
            "topic_id": self.topic_id,
        }

        # 6. Submit to HCS
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        hcs_result = await HCSTransport.submit(
            self.topic_id, payload_json, self.operator_id, self.operator_key,
        )

        anchored = hcs_result["success"]

        # 7. Build receipt
        receipt = {
            **payload,
            "anchored": anchored,
            "hcs": {
                "sequence_number": hcs_result.get("sequence_number"),
                "consensus_timestamp": hcs_result.get("consensus_timestamp"),
                "transaction_id": hcs_result.get("transaction_id"),
                "error": hcs_result.get("error"),
            },
        }

        # Store as SwarmEvent
        event = SwarmEvent(
            event_type="hedera.anchored" if anchored else "hedera.anchor_pending",
            source_node="hedera_anchor",
            energy_cost=0,
            payload=receipt,
        )
        db.add(event)

        # Store as BlockArtifact (anchored to the last block in the window)
        anchor_artifact = BlockArtifact(
            block_id=block_ids[0],  # most recent block
            artifact_type="hedera_anchor",
            artifact_json=receipt,
        )
        db.add(anchor_artifact)
        await db.flush()

        status_str = "ANCHORED" if anchored else "PENDING (stored locally)"
        logger.info(
            f"Hedera anchor {status_str}: window [{window_start}, {window_end}] "
            f"merkle_root={merkle_root[:18]}... blocks={len(artifact_dicts)}"
        )

        return receipt

    async def retry_pending(self, db: AsyncSession) -> list[dict]:
        """Retry all pending (unanchored) anchor records.

        Returns list of receipts that were successfully submitted.
        """
        result = await db.execute(
            select(BlockArtifact)
            .where(BlockArtifact.artifact_type == "hedera_anchor")
            .order_by(BlockArtifact.created_at.asc())
        )
        anchors = result.scalars().all()

        retried: list[dict] = []
        for anchor in anchors:
            data = anchor.artifact_json
            if data.get("anchored"):
                continue

            payload_json = json.dumps(
                {k: v for k, v in data.items() if k not in ("anchored", "hcs")},
                sort_keys=True, separators=(",", ":"), default=str,
            )

            hcs_result = await HCSTransport.submit(
                self.topic_id, payload_json, self.operator_id, self.operator_key,
            )

            if hcs_result["success"]:
                data["anchored"] = True
                data["hcs"] = {
                    "sequence_number": hcs_result.get("sequence_number"),
                    "consensus_timestamp": hcs_result.get("consensus_timestamp"),
                    "transaction_id": hcs_result.get("transaction_id"),
                    "error": None,
                }
                # Update the artifact in place
                anchor.artifact_json = data
                # Flag dirty for SQLAlchemy JSON mutation detection
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(anchor, "artifact_json")

                # Update the corresponding event
                evt_result = await db.execute(
                    select(SwarmEvent)
                    .where(SwarmEvent.event_type == "hedera.anchor_pending")
                    .where(
                        SwarmEvent.payload["window"]["start"].as_integer()
                        == data["window"]["start"]
                    )
                    .limit(1)
                )
                evt = evt_result.scalar_one_or_none()
                if evt:
                    evt.event_type = "hedera.anchored"
                    evt.payload = data
                    flag_modified(evt, "payload")

                retried.append(data)
                logger.info(
                    f"Retried anchor window [{data['window']['start']}-"
                    f"{data['window']['end']}] — now anchored"
                )

        if retried:
            await db.flush()

        return retried

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    async def _gather_convergence(self, db: AsyncSession,
                                  window_start: int, window_end: int) -> dict:
        """Get the latest convergence metrics covering this window."""
        result = await db.execute(
            select(ConvergenceMetric)
            .where(ConvergenceMetric.window_end <= window_end)
            .order_by(ConvergenceMetric.computed_at.desc())
            .limit(1)
        )
        metric = result.scalar_one_or_none()

        if not metric:
            return {
                "cost_per_honey": 0.0,
                "attempts_per_solve": 0.0,
                "solve_rate": 0.0,
                "delta_cost": 0.0,
                "energy_per_honey": 0.0,
            }

        return {
            "cost_per_honey": metric.avg_cost_per_honey,
            "attempts_per_solve": metric.avg_attempts_per_solve,
            "solve_rate": metric.solve_rate,
            "delta_cost": metric.delta_cost_per_honey,
            "energy_per_honey": metric.avg_energy_per_honey,
        }

    async def _gather_totals(self, db: AsyncSession,
                             block_ids: list[str],
                             window_blocks: list[Block]) -> dict:
        """Aggregate totals across the anchor window."""
        blocks_sealed = len(window_blocks)
        blocks_solved = sum(1 for b in window_blocks if b.status == "solved")
        total_attempts = sum(b.attempt_count for b in window_blocks)
        total_energy = sum(b.total_energy for b in window_blocks)

        # Total cost from BlockCost records
        result = await db.execute(
            select(func.sum(BlockCost.total_cost))
            .where(BlockCost.block_id.in_(block_ids))
        )
        total_cost = float(result.scalar() or 0)

        return {
            "blocks_sealed": blocks_sealed,
            "blocks_solved": blocks_solved,
            "total_attempts": total_attempts,
            "total_energy_kwh": round(total_energy, 4),
            "total_cost_usd": round(total_cost, 4),
        }

    def _empty_receipt(self, window_start: int, window_end: int, reason: str) -> dict:
        """Return an empty receipt when anchoring cannot proceed."""
        return {
            "protocol": "swarmchain-v1",
            "window": {"start": window_start, "end": window_end},
            "merkle_root": None,
            "block_count": 0,
            "convergence": {},
            "totals": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "topic_id": self.topic_id,
            "anchored": False,
            "hcs": {"error": reason},
        }
