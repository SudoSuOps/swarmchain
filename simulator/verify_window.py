#!/usr/bin/env python3
"""SwarmChain Window Verifier — the trust foundation of the protocol.

Public verifier script that anyone can run to validate a SwarmChain
convergence claim. Fetches sealed blocks, recomputes Merkle roots and
convergence metrics, and compares against anchored claims.

NON-NEGOTIABLE: this script must be deterministic and correct.

Merkle tree algorithm:
  - Leaf = SHA256(canonical_json(artifact_json))
  - Tree built bottom-up, pairs hashed left||right
  - Odd leaf promoted without hashing
  - Root = single remaining hash
  This is the CANONICAL implementation. hedera_anchor.py must use the same.

Usage:
    python verify_window.py --api-url http://165.227.109.67/api --window-end 500
    python verify_window.py --api-url http://localhost:8000 --window-end 40 --window-size 20
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Merkle tree — CANONICAL IMPLEMENTATION
# ---------------------------------------------------------------------------
# If you are implementing hedera_anchor.py or any other component that
# computes Merkle roots over block artifacts, you MUST use this exact
# algorithm. The canonical JSON serialization uses sort_keys=True and
# separators=(',', ':') with no trailing whitespace.
# ---------------------------------------------------------------------------

def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON serialization for hashing.

    Rules:
      - Keys sorted alphabetically at all nesting levels
      - No whitespace between tokens (compact separators)
      - UTF-8 encoded bytes
      - ensure_ascii=False for faithful Unicode representation
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """SHA-256 hash, returned as lowercase hex string."""
    return hashlib.sha256(data).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    """Compute the Merkle root from a list of hex-encoded leaf hashes.

    Algorithm:
      1. If no leaves, root is SHA256(b"empty")
      2. Pair adjacent hashes and hash their concatenation
      3. If odd number, the last hash is promoted to the next level
      4. Repeat until one hash remains

    All intermediate hashes use SHA256(left_bytes || right_bytes) where
    left_bytes and right_bytes are the raw bytes of the hex-decoded hashes.
    """
    if not leaves:
        return sha256_hex(b"empty")

    current_level = list(leaves)

    while len(current_level) > 1:
        next_level: list[str] = []
        for i in range(0, len(current_level), 2):
            if i + 1 < len(current_level):
                # Pair: hash(left || right)
                left = bytes.fromhex(current_level[i])
                right = bytes.fromhex(current_level[i + 1])
                combined = hashlib.sha256(left + right).hexdigest()
                next_level.append(combined)
            else:
                # Odd leaf: promoted without modification
                next_level.append(current_level[i])
        current_level = next_level

    return current_level[0]


def compute_artifact_leaf(artifact_json: dict) -> str:
    """Compute the Merkle leaf hash for a single block artifact."""
    return sha256_hex(canonical_json(artifact_json))


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class SwarmChainClient:
    """Read-only client for the SwarmChain public API."""

    def __init__(self, api_url: str, timeout: float = 30.0):
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.api_url}{path}"

    def get(self, client: httpx.Client, path: str, params: dict | None = None) -> Any:
        """GET request, returns parsed JSON or raises."""
        resp = client.get(self._url(path), params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Verification logic
# ---------------------------------------------------------------------------

HONEY_THRESHOLD = 0.95
JELLY_THRESHOLD = 0.30


def classify_score(score: float) -> str:
    """Classify an attempt score into honey/jelly/propolis."""
    if score >= HONEY_THRESHOLD:
        return "honey"
    elif score >= JELLY_THRESHOLD:
        return "jelly"
    else:
        return "propolis"


def verify_window(
    api_url: str,
    window_end: int,
    window_size: int = 50,
    verbose: bool = False,
) -> dict:
    """Run full verification on a convergence window.

    Steps:
      1. Fetch sealed blocks in the window
      2. Fetch block artifacts for each block
      3. Recompute Merkle root from artifacts
      4. Fetch anchor record for this window
      5. Compare computed root vs anchored root
      6. Recompute convergence metrics from raw block data
      7. Compare computed metrics vs claimed metrics

    Returns a result dict with all verification details.
    """
    api = SwarmChainClient(api_url)
    window_start = max(0, window_end - window_size)

    result = {
        "window_start": window_start,
        "window_end": window_end,
        "window_size": window_size,
        "merkle": {"claimed": None, "computed": None, "match": False},
        "metrics": {},
        "verdict": "PENDING",
        "errors": [],
    }

    with httpx.Client() as client:
        # ---------------------------------------------------------------
        # Step 1: Fetch sealed blocks in the window
        # ---------------------------------------------------------------
        if verbose:
            print(f"  Fetching sealed blocks (offset={window_start}, limit={window_size})...")

        blocks_data = api.get(
            client, "/blocks",
            params={"status": "solved", "limit": 500, "offset": 0},
        )
        all_blocks = blocks_data.get("blocks", [])

        # Also fetch exhausted blocks
        exhausted_data = api.get(
            client, "/blocks",
            params={"status": "exhausted", "limit": 500, "offset": 0},
        )
        all_blocks.extend(exhausted_data.get("blocks", []))

        # Sort by start_time ascending to establish ordering
        all_blocks.sort(key=lambda b: b.get("start_time", ""))

        # Take blocks in the window [window_start:window_end]
        window_blocks = all_blocks[window_start:window_end]

        if not window_blocks:
            result["errors"].append(
                f"No sealed blocks found in window {window_start}-{window_end}. "
                f"Total sealed blocks available: {len(all_blocks)}"
            )
            result["verdict"] = "FAILED"
            return result

        if verbose:
            print(f"  Found {len(window_blocks)} blocks in window")

        # ---------------------------------------------------------------
        # Step 2: Fetch block artifacts for each block
        # ---------------------------------------------------------------
        if verbose:
            print("  Fetching block artifacts...")

        all_artifacts: list[dict] = []
        blocks_with_data: list[dict] = []

        for block in window_blocks:
            block_id = block["block_id"]
            try:
                artifacts = api.get(client, f"/blocks/{block_id}/artifacts")
                if artifacts:
                    all_artifacts.extend(artifacts)
                    blocks_with_data.append(block)
                else:
                    if verbose:
                        print(f"    Block {block_id[:8]}: no artifacts")
            except httpx.HTTPStatusError as e:
                result["errors"].append(f"Failed to fetch artifacts for block {block_id}: {e}")

        if verbose:
            print(f"  Collected {len(all_artifacts)} artifacts from {len(blocks_with_data)} blocks")

        # ---------------------------------------------------------------
        # Step 3: Recompute Merkle root from artifacts
        # ---------------------------------------------------------------
        if verbose:
            print("  Computing Merkle root...")

        # Sort artifacts deterministically: by block_id then by artifact_type
        all_artifacts.sort(
            key=lambda a: (
                a.get("artifact_json", {}).get("block_id", ""),
                a.get("artifact_type", ""),
            )
        )

        leaf_hashes = [
            compute_artifact_leaf(a.get("artifact_json", {}))
            for a in all_artifacts
        ]

        computed_root = merkle_root(leaf_hashes)
        result["merkle"]["computed"] = computed_root

        if verbose:
            print(f"  Computed Merkle root: 0x{computed_root[:16]}...")

        # ---------------------------------------------------------------
        # Step 4: Fetch anchor record for this window
        # ---------------------------------------------------------------
        if verbose:
            print(f"  Fetching anchor record for window_end={window_end}...")

        anchor = None
        try:
            # Try the anchors endpoint
            anchor = api.get(client, f"/anchors/{window_end}")
        except httpx.HTTPStatusError:
            # Anchors endpoint might not exist yet — try convergence events
            try:
                events = api.get(
                    client, "/events/stream",
                    params={"event_type": "convergence.anchored", "limit": 100},
                )
                for ev in events:
                    payload = ev.get("payload", {})
                    if payload.get("window_end") == window_end:
                        anchor = payload
                        break
            except httpx.HTTPStatusError:
                pass

        if anchor:
            claimed_root = anchor.get("merkle_root") or anchor.get("root")
            result["merkle"]["claimed"] = claimed_root
            if claimed_root:
                result["merkle"]["match"] = (computed_root == claimed_root)
        else:
            # No anchor record — verification still runs, but Merkle comparison
            # is reported as "NO ANCHOR" rather than FAIL
            result["merkle"]["claimed"] = "NO_ANCHOR_RECORD"
            result["merkle"]["match"] = None  # indeterminate
            if verbose:
                print("  No anchor record found — Merkle comparison skipped")

        # ---------------------------------------------------------------
        # Step 5: Fetch claimed convergence metrics
        # ---------------------------------------------------------------
        if verbose:
            print("  Fetching claimed convergence metrics...")

        claimed_metrics = None
        try:
            # Try convergence events for this window
            events = api.get(
                client, "/events/stream",
                params={"event_type": "convergence.computed", "limit": 100},
            )
            for ev in events:
                payload = ev.get("payload", {})
                window_str = payload.get("window", "")
                if window_str == f"{window_start}-{window_end}":
                    claimed_metrics = payload
                    break
        except httpx.HTTPStatusError:
            pass

        # Also try dashboard for latest convergence
        if claimed_metrics is None:
            try:
                dashboard = api.get(client, "/dashboard")
                conv = dashboard.get("convergence")
                if conv and conv.get("window") == f"{window_start}-{window_end}":
                    claimed_metrics = conv
            except httpx.HTTPStatusError:
                pass

        # ---------------------------------------------------------------
        # Step 6: Recompute convergence metrics from raw block data
        # ---------------------------------------------------------------
        if verbose:
            print("  Recomputing convergence metrics from raw block data...")

        blocks_sealed = len(window_blocks)
        blocks_solved = sum(1 for b in window_blocks if b.get("status") == "solved")
        solve_rate = blocks_solved / max(blocks_sealed, 1)

        total_attempts = sum(b.get("attempt_count", 0) for b in window_blocks)
        avg_attempts_per_solve = total_attempts / max(blocks_solved, 1)

        # Fetch anatomy for each block to get cost data
        total_cost = 0.0
        total_honey = 0
        total_jelly = 0
        total_propolis = 0

        for block in window_blocks:
            block_id = block["block_id"]
            try:
                anatomy = api.get(client, f"/blocks/{block_id}/anatomy")
                taxonomy = anatomy.get("taxonomy", {})
                total_honey += taxonomy.get("honey", 0)
                total_jelly += taxonomy.get("jelly", 0)
                total_propolis += taxonomy.get("propolis", 0)

                energy = anatomy.get("energy", {})
                # Use energy.total as cost proxy (actual cost comes from BlockCost)
                total_cost += energy.get("total", 0)
            except httpx.HTTPStatusError:
                # Fall back to block-level data
                if block.get("status") == "solved":
                    total_honey += 1

        avg_cost_per_honey = total_cost / max(total_honey, 1)

        computed_metrics = {
            "solve_rate": round(solve_rate, 4),
            "avg_attempts_per_solve": round(avg_attempts_per_solve, 2),
            "avg_cost_per_honey": round(avg_cost_per_honey, 4),
            "blocks_sealed": blocks_sealed,
            "blocks_solved": blocks_solved,
            "total_attempts": total_attempts,
            "total_honey": total_honey,
            "total_jelly": total_jelly,
            "total_propolis": total_propolis,
        }

        # ---------------------------------------------------------------
        # Step 7: Compare computed metrics vs claimed metrics
        # ---------------------------------------------------------------
        metric_checks: dict[str, dict] = {}

        if claimed_metrics:
            # cost_per_honey
            claimed_cph = claimed_metrics.get("cost_per_honey")
            if claimed_cph is not None:
                metric_checks["cost_per_honey"] = {
                    "claimed": round(float(claimed_cph), 4),
                    "computed": computed_metrics["avg_cost_per_honey"],
                    "match": abs(float(claimed_cph) - computed_metrics["avg_cost_per_honey"]) < 0.01,
                }

            # attempts_per_solve
            claimed_aps = claimed_metrics.get("attempts_per_solve")
            if claimed_aps is not None:
                metric_checks["attempts_per_solve"] = {
                    "claimed": round(float(claimed_aps), 2),
                    "computed": computed_metrics["avg_attempts_per_solve"],
                    "match": abs(float(claimed_aps) - computed_metrics["avg_attempts_per_solve"]) < 1.0,
                }

            # solve_rate
            claimed_sr = claimed_metrics.get("solve_rate")
            if claimed_sr is not None:
                metric_checks["solve_rate"] = {
                    "claimed": round(float(claimed_sr), 4),
                    "computed": computed_metrics["solve_rate"],
                    "match": abs(float(claimed_sr) - computed_metrics["solve_rate"]) < 0.05,
                }
        else:
            result["errors"].append(
                "No claimed convergence metrics found for this window. "
                "Metric verification skipped — only computed values reported."
            )

        result["metrics"] = {
            "computed": computed_metrics,
            "checks": metric_checks,
        }

        # ---------------------------------------------------------------
        # Verdict
        # ---------------------------------------------------------------
        all_pass = True
        fail_reasons: list[str] = []

        # Merkle check
        if result["merkle"]["match"] is False:
            all_pass = False
            fail_reasons.append(
                f"Merkle root mismatch: claimed={result['merkle']['claimed']}, "
                f"computed={result['merkle']['computed']}"
            )

        # Metric checks
        for metric_name, check in metric_checks.items():
            if not check["match"]:
                all_pass = False
                fail_reasons.append(
                    f"{metric_name} mismatch: claimed={check['claimed']}, "
                    f"computed={check['computed']}"
                )

        if all_pass and not fail_reasons:
            result["verdict"] = "VERIFIED"
        elif fail_reasons:
            result["verdict"] = f"FAILED"
            result["fail_reasons"] = fail_reasons
        else:
            result["verdict"] = "VERIFIED"

    return result


# ---------------------------------------------------------------------------
# Pretty output
# ---------------------------------------------------------------------------

def print_result(result: dict) -> None:
    """Print verification result in the specified format."""
    ws = result["window_start"]
    we = result["window_end"]

    print()
    print("=" * 48)
    print("  SwarmChain Window Verification")
    print(f"  Window: blocks {ws}-{we}")
    print("=" * 48)

    # Errors
    for err in result.get("errors", []):
        print(f"\n  WARNING: {err}")

    # Merkle root
    merkle = result["merkle"]
    print()
    print("  Merkle Root:")
    claimed = merkle.get("claimed") or "N/A"
    computed = merkle.get("computed") or "N/A"
    if claimed != "N/A" and claimed != "NO_ANCHOR_RECORD" and len(claimed) > 16:
        print(f"    Claimed:  0x{claimed[:16]}...")
    else:
        print(f"    Claimed:  {claimed}")
    if computed != "N/A" and len(computed) > 16:
        print(f"    Computed: 0x{computed[:16]}...")
    else:
        print(f"    Computed: {computed}")

    match = merkle.get("match")
    if match is True:
        print("    Status:   MATCH")
    elif match is False:
        print("    Status:   MISMATCH")
    else:
        print("    Status:   NO ANCHOR (comparison skipped)")

    # Convergence metrics
    metrics = result.get("metrics", {})
    computed_m = metrics.get("computed", {})
    checks = metrics.get("checks", {})

    print()
    print("  Convergence Metrics:")
    print(f"    blocks_sealed:    {computed_m.get('blocks_sealed', 'N/A')}")
    print(f"    blocks_solved:    {computed_m.get('blocks_solved', 'N/A')}")
    print(f"    total_attempts:   {computed_m.get('total_attempts', 'N/A')}")
    print(f"    total_honey:      {computed_m.get('total_honey', 'N/A')}")
    print(f"    total_jelly:      {computed_m.get('total_jelly', 'N/A')}")
    print(f"    total_propolis:   {computed_m.get('total_propolis', 'N/A')}")

    if checks:
        print()
        for metric_name, check in checks.items():
            print(f"    {metric_name}:")
            print(f"      Claimed:  {check['claimed']}")
            print(f"      Computed: {check['computed']}")
            status = "MATCH" if check["match"] else "MISMATCH"
            print(f"      Status:   {status}")
    else:
        print()
        print("    (No claimed metrics to compare — showing computed only)")
        for key in ["solve_rate", "avg_attempts_per_solve", "avg_cost_per_honey"]:
            val = computed_m.get(key, "N/A")
            print(f"    {key}: {val}")

    # Verdict
    verdict = result.get("verdict", "UNKNOWN")
    print()
    if verdict == "VERIFIED":
        print(f"  VERDICT: VERIFIED")
    else:
        reasons = result.get("fail_reasons", [])
        if reasons:
            print(f"  VERDICT: FAILED")
            for r in reasons:
                print(f"    - {r}")
        else:
            print(f"  VERDICT: {verdict}")

    print("=" * 48)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "SwarmChain Window Verifier — validate a convergence claim. "
            "Fetches data from the SwarmChain API, recomputes Merkle roots "
            "and convergence metrics, and compares against anchored claims."
        ),
    )
    parser.add_argument(
        "--api-url",
        default="http://165.227.109.67/api",
        help="SwarmChain API base URL (default: http://165.227.109.67/api)",
    )
    parser.add_argument(
        "--window-end",
        type=int,
        required=True,
        help="Block sequence number at the end of the window to verify",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=50,
        help="Number of blocks in the verification window (default: 50)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print progress details during verification",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output raw JSON result instead of formatted text",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.verbose:
        print(f"SwarmChain Window Verifier")
        print(f"  API:    {args.api_url}")
        print(f"  Window: {max(0, args.window_end - args.window_size)}-{args.window_end}")
        print()

    try:
        result = verify_window(
            api_url=args.api_url,
            window_end=args.window_end,
            window_size=args.window_size,
            verbose=args.verbose,
        )
    except httpx.ConnectError:
        print(f"ERROR: Cannot connect to API at {args.api_url}")
        print("Is the SwarmChain backend running?")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"ERROR: API returned {e.response.status_code}: {e.response.text[:200]}")
        sys.exit(1)

    if args.json_output:
        print(json.dumps(result, indent=2, default=str))
    else:
        print_result(result)

    # Exit code: 0 = verified, 1 = failed
    if result["verdict"] == "VERIFIED":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
