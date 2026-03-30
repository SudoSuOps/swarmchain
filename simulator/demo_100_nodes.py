#!/usr/bin/env python3
"""SwarmChain 100-Node Demo — a single ARC block solved by a heterogeneous swarm.

Registers 100 nodes across 5 tiers (jetmini/zima/mid-gpu/heavy-gpu/queen),
opens one block for arc-002-mirror-h, runs 10 rounds of attempts with
realistic delays and failure modes, then finalizes and triggers a dataset sale.

Includes anti-spam and duplicate nodes to exercise the economics penalties.

Usage:
    python demo_100_nodes.py
    python demo_100_nodes.py --api-url http://192.168.0.50:8000
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import httpx

from strategies import (
    STRATEGY_REGISTRY,
    Grid,
    random_grid,
    random_perturbation,
    copy_input,
    mirror_h,
    mirror_v,
    color_swap,
    rotate_90,
    transpose,
    scale_2x,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("demo-100")

# ──────────────────────────────────────────────────────────────────────────────
# ARC task definition (embedded so the demo is fully self-contained)
# ──────────────────────────────────────────────────────────────────────────────

TASK_ID = "arc-002-mirror-h"
INPUT_GRID: Grid = [[1, 0, 0], [1, 1, 0], [1, 1, 1]]
EXPECTED_OUTPUT: Grid = [[0, 0, 1], [0, 1, 1], [1, 1, 1]]
EXPECTED_DIMS = (3, 3)

# Fixed spam grid — identical every time (deliberately wrong)
SPAM_GRID: Grid = [[9, 9, 9], [9, 9, 9], [9, 9, 9]]

# Fixed duplicate grid — always the same slightly-wrong output
DUPLICATE_GRID: Grid = [[0, 0, 0], [0, 1, 1], [1, 1, 1]]


# ──────────────────────────────────────────────────────────────────────────────
# Node definitions
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SimNode:
    """A simulated compute node."""
    node_id: str
    node_type: str
    hardware_class: str
    tier: str  # jetmini | zima | mid-gpu | heavy-gpu | queen
    strategies: list[str]
    energy_range: tuple[float, float]
    delay_range: tuple[float, float]
    is_spam: bool = False      # always submits SPAM_GRID
    is_duplicate: bool = False  # always submits DUPLICATE_GRID
    registered: bool = False


def _build_fleet() -> list[SimNode]:
    """Create 100 nodes across 5 tiers."""
    fleet: list[SimNode] = []

    # ── Tier 1: 40 jetmini (edge, cheap) ──────────────────────────────────
    for i in range(40):
        is_spam = i < 10        # first 10 are spam nodes
        is_dup = 10 <= i < 15   # next 5 are duplicate nodes
        fleet.append(SimNode(
            node_id=f"jet-{i:03d}",
            node_type="jetmini",
            hardware_class="edge-4gb",
            tier="jetmini",
            strategies=["random_grid", "copy_input", "random_perturbation"],
            energy_range=(0.1, 0.3),
            delay_range=(0.01, 0.05),
            is_spam=is_spam,
            is_duplicate=is_dup,
        ))

    # ── Tier 2: 25 zima-lowgpu (structured — these can solve it) ─────────
    for i in range(25):
        fleet.append(SimNode(
            node_id=f"zima-{i:03d}",
            node_type="zima-lowgpu",
            hardware_class="low-gpu-8gb",
            tier="zima",
            strategies=["mirror_h", "mirror_v", "color_swap"],
            energy_range=(0.3, 0.7),
            delay_range=(0.02, 0.06),
        ))

    # ── Tier 3: 20 mid-gpu ────────────────────────────────────────────────
    for i in range(20):
        fleet.append(SimNode(
            node_id=f"mid-{i:03d}",
            node_type="mid-gpu",
            hardware_class="mid-gpu-24gb",
            tier="mid-gpu",
            strategies=["rotate_90", "transpose", "scale_2x"],
            energy_range=(0.7, 1.5),
            delay_range=(0.03, 0.08),
        ))

    # ── Tier 4: 10 heavy-gpu (derives from promoted parents) ─────────────
    for i in range(10):
        fleet.append(SimNode(
            node_id=f"heavy-{i:03d}",
            node_type="heavy-gpu",
            hardware_class="high-gpu-48gb",
            tier="heavy-gpu",
            strategies=["random_perturbation"],
            energy_range=(1.5, 3.0),
            delay_range=(0.04, 0.10),
        ))

    # ── Tier 5: 5 queen (refines top parent only) ────────────────────────
    for i in range(5):
        fleet.append(SimNode(
            node_id=f"queen-{i:03d}",
            node_type="queen",
            hardware_class="high-gpu-96gb",
            tier="queen",
            strategies=["random_perturbation"],
            energy_range=(2.0, 5.0),
            delay_range=(0.05, 0.10),
        ))

    return fleet


# ──────────────────────────────────────────────────────────────────────────────
# Statistics tracking
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class NodeStats:
    """Per-node running stats."""
    attempts: int = 0
    scores: list[float] = field(default_factory=list)
    solved: bool = False
    strategies_used: list[str] = field(default_factory=list)
    errors: int = 0


# ──────────────────────────────────────────────────────────────────────────────
# Demo driver
# ──────────────────────────────────────────────────────────────────────────────

class Demo100Nodes:
    """Orchestrates the full 100-node demo lifecycle."""

    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        self.fleet = _build_fleet()
        self.block_id: str | None = None
        self.stats: dict[str, NodeStats] = {n.node_id: NodeStats() for n in self.fleet}
        self.promoted_cache: list[dict] = []
        self.promoted_cache_round: int = -1

    # ── HTTP helpers ──────────────────────────────────────────────────────

    async def _post(self, client: httpx.AsyncClient, path: str, body: dict) -> dict | None:
        url = f"{self.api_url}{path}"
        try:
            resp = await client.post(url, json=body, timeout=30.0)
            if resp.status_code >= 400:
                log.warning("POST %s -> %d: %s", path, resp.status_code, resp.text[:200])
                return None
            return resp.json()
        except httpx.HTTPError as exc:
            log.error("POST %s error: %s", path, exc)
            return None

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict | None = None) -> dict | None:
        url = f"{self.api_url}{path}"
        try:
            resp = await client.get(url, params=params, timeout=30.0)
            if resp.status_code >= 400:
                log.warning("GET %s -> %d: %s", path, resp.status_code, resp.text[:200])
                return None
            return resp.json()
        except httpx.HTTPError as exc:
            log.error("GET %s error: %s", path, exc)
            return None

    # ── Phase 1: Register all 100 nodes ──────────────────────────────────

    async def register_nodes(self, client: httpx.AsyncClient) -> int:
        """Register every node in the fleet. Returns count registered."""
        log.info("Phase 1: Registering %d nodes ...", len(self.fleet))

        sem = asyncio.Semaphore(20)  # limit concurrency

        async def _register(node: SimNode) -> bool:
            async with sem:
                result = await self._post(client, "/nodes/register", {
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "hardware_class": node.hardware_class,
                    "metadata": {
                        "simulator": True,
                        "demo": "100-nodes",
                        "tier": node.tier,
                        "is_spam": node.is_spam,
                        "is_duplicate": node.is_duplicate,
                    },
                })
                if result:
                    node.registered = True
                    return True
                return False

        results = await asyncio.gather(*[_register(n) for n in self.fleet])
        registered = sum(1 for r in results if r)
        log.info("  -> %d / %d nodes registered", registered, len(self.fleet))
        return registered

    # ── Phase 2: Open ONE block ──────────────────────────────────────────

    async def open_block(self, client: httpx.AsyncClient) -> bool:
        """Open a single block for arc-002-mirror-h."""
        log.info("Phase 2: Opening block for %s ...", TASK_ID)
        result = await self._post(client, "/blocks/open", {
            "task_id": TASK_ID,
            "domain": "arc",
            "reward_pool": 100.0,
            "max_attempts": 2000,
            "time_limit_sec": 7200,
            "metadata": {"demo": "100-nodes", "nodes": 100, "rounds": 10},
        })
        if not result:
            log.error("  -> Failed to open block")
            return False

        self.block_id = result["block_id"]
        log.info("  -> Block %s opened", self.block_id)
        return True

    # ── Phase 3: Fetch promoted parents ──────────────────────────────────

    async def _refresh_promoted(self, client: httpx.AsyncClient, current_round: int) -> None:
        """Refresh the promoted-attempts cache (once per round max)."""
        if current_round == self.promoted_cache_round:
            return
        data = await self._get(client, f"/attempts/block/{self.block_id}/top", {"limit": 10})
        if data and data.get("attempts"):
            self.promoted_cache = data["attempts"]
        self.promoted_cache_round = current_round

    def _pick_parent(self, top_only: bool = False) -> tuple[str | None, Grid | None]:
        """Pick a promoted parent from cache.

        top_only=True picks the #1 parent (queen behavior).
        Otherwise weighted random by score (heavy-gpu behavior).
        """
        if not self.promoted_cache:
            return None, None

        if top_only:
            parent = self.promoted_cache[0]
        else:
            weights = [max(a.get("score", 0.01), 0.01) for a in self.promoted_cache]
            parent = random.choices(self.promoted_cache, weights=weights, k=1)[0]

        parent_id = parent.get("attempt_id")
        parent_grid = parent.get("output_json", {}).get("grid")
        return parent_id, parent_grid

    # ── Phase 3: Submit one attempt ──────────────────────────────────────

    async def _submit_one(
        self,
        client: httpx.AsyncClient,
        node: SimNode,
        current_round: int,
    ) -> None:
        """Generate and submit a single attempt for a node."""
        if not node.registered or not self.block_id:
            return

        ns = self.stats[node.node_id]

        # Simulate random delay (different speeds)
        delay = random.uniform(*node.delay_range)
        await asyncio.sleep(delay)

        # Simulate occasional failures (5% chance for non-spam, non-dup)
        if not node.is_spam and not node.is_duplicate and random.random() < 0.05:
            ns.errors += 1
            return

        # ── Determine output grid and strategy ───────────────────────────
        parent_attempt_id: str | None = None
        parent_grid: Grid | None = None

        if node.is_spam:
            # Spam nodes: always the same garbage grid
            grid = [row[:] for row in SPAM_GRID]
            strategy_name = "random_grid"

        elif node.is_duplicate:
            # Duplicate nodes: always the same slightly-wrong grid
            grid = [row[:] for row in DUPLICATE_GRID]
            strategy_name = "copy_input"

        elif node.tier == "heavy-gpu":
            # Heavy-gpu: derive from any promoted parent
            strategy_name = "random_perturbation"
            parent_attempt_id, parent_grid = self._pick_parent(top_only=False)
            strategy_fn = STRATEGY_REGISTRY[strategy_name]
            grid = strategy_fn(INPUT_GRID, EXPECTED_DIMS, parent_grid=parent_grid)

        elif node.tier == "queen":
            # Queen: derive from the TOP promoted parent only
            strategy_name = "random_perturbation"
            parent_attempt_id, parent_grid = self._pick_parent(top_only=True)
            strategy_fn = STRATEGY_REGISTRY[strategy_name]
            grid = strategy_fn(INPUT_GRID, EXPECTED_DIMS, parent_grid=parent_grid)

        else:
            # Normal nodes: pick a random strategy from their family
            strategy_name = random.choice(node.strategies)
            strategy_fn = STRATEGY_REGISTRY[strategy_name]
            grid = strategy_fn(INPUT_GRID, EXPECTED_DIMS, parent_grid=None)

        # ── Energy cost (random within tier range) ───────────────────────
        energy = round(random.uniform(*node.energy_range), 3)

        # ── Latency (based on delay + jitter) ────────────────────────────
        latency_ms = int(delay * 1000) + random.randint(5, 50)

        # ── Submit ───────────────────────────────────────────────────────
        result = await self._post(client, "/attempts", {
            "node_id": node.node_id,
            "block_id": self.block_id,
            "parent_attempt_id": parent_attempt_id,
            "method": f"demo-{strategy_name}",
            "strategy_family": strategy_name,
            "output_json": {"grid": grid},
            "energy_cost": energy,
            "latency_ms": latency_ms,
        })

        if result:
            score = result.get("score", 0.0)
            ns.attempts += 1
            ns.scores.append(score)
            ns.strategies_used.append(strategy_name)

            if score == 1.0:
                ns.solved = True
                log.info(
                    "  SOLVED by %s (%s) using %s in round %d!",
                    node.node_id, node.tier, strategy_name, current_round,
                )
        else:
            ns.errors += 1

    # ── Phase 3: Run all rounds ──────────────────────────────────────────

    async def run_rounds(self, client: httpx.AsyncClient, num_rounds: int = 10) -> None:
        """Run num_rounds rounds, each with all 100 nodes submitting."""
        log.info("Phase 3: Running %d rounds with %d nodes ...", num_rounds, len(self.fleet))
        sem = asyncio.Semaphore(30)  # limit concurrent API calls

        for rnd in range(1, num_rounds + 1):
            t0 = time.monotonic()

            # Refresh promoted cache for derivation tiers
            await self._refresh_promoted(client, rnd)

            async def _bounded_submit(node: SimNode) -> None:
                async with sem:
                    await self._submit_one(client, node, rnd)

            active = [n for n in self.fleet if n.registered]
            await asyncio.gather(*[_bounded_submit(n) for n in active], return_exceptions=True)

            elapsed = time.monotonic() - t0
            total_attempts = sum(s.attempts for s in self.stats.values())
            solvers = [nid for nid, s in self.stats.items() if s.solved]
            log.info(
                "  Round %2d/%d: %d total attempts, %d solvers, %.1fs",
                rnd, num_rounds, total_attempts, len(solvers), elapsed,
            )

    # ── Phase 4: Finalize ────────────────────────────────────────────────

    async def finalize_block(self, client: httpx.AsyncClient) -> dict | None:
        """Finalize the block with force=true."""
        log.info("Phase 4: Finalizing block %s ...", self.block_id)
        result = await self._post(client, f"/blocks/{self.block_id}/finalize", {
            "force": True,
            "reason": "demo-100-nodes-complete",
        })
        if result:
            log.info(
                "  -> status=%s winner=%s final_score=%s",
                result.get("status"),
                result.get("winning_node_id"),
                result.get("final_score"),
            )
        else:
            log.error("  -> Finalization failed")
        return result

    # ── Phase 5: Dataset sale ────────────────────────────────────────────

    async def dataset_sale(self, client: httpx.AsyncClient) -> dict | None:
        """Trigger a dataset sale."""
        log.info("Phase 5: Dataset sale — buyer=ARC Research Labs, price=$10,000 ...")
        result = await self._post(client, "/economics/dataset-sale", {
            "block_id": self.block_id,
            "buyer": "ARC Research Labs",
            "sale_price": 10000.0,
            "platform_fee_pct": 0.10,
        })
        if result:
            log.info(
                "  -> sale_id=%s distributable=%.2f payouts=%d status=%s",
                result.get("sale_id"),
                result.get("distributable", 0),
                result.get("payout_count", 0),
                result.get("status"),
            )
        else:
            log.error("  -> Dataset sale failed")
        return result

    # ── Phase 6: Fetch rewards and print comprehensive results ───────────

    async def fetch_and_print_results(
        self,
        client: httpx.AsyncClient,
        block_result: dict | None,
        sale_result: dict | None,
    ) -> None:
        """Fetch rewards from the API and print comprehensive results."""
        print("\n" + "=" * 80)
        print("  SWARMCHAIN 100-NODE DEMO — COMPREHENSIVE RESULTS")
        print("=" * 80)

        # ── Block status ─────────────────────────────────────────────────
        print("\n--- BLOCK STATUS ---")
        if block_result:
            print(f"  Block ID:          {block_result.get('block_id')}")
            print(f"  Task:              {block_result.get('task_id')}")
            print(f"  Status:            {block_result.get('status')}")
            print(f"  Total attempts:    {block_result.get('attempt_count')}")
            print(f"  Total energy:      {block_result.get('total_energy', 0):.2f}")
            print(f"  Winner node:       {block_result.get('winning_node_id', 'none')}")
            print(f"  Final score:       {block_result.get('final_score', 0)}")
        else:
            print("  (block finalization result unavailable)")

        # ── Attempt distribution by node type ────────────────────────────
        print("\n--- ATTEMPT DISTRIBUTION BY NODE TYPE ---")
        tier_stats: dict[str, dict] = defaultdict(lambda: {
            "count": 0, "attempts": 0, "solvers": 0, "avg_score": 0.0,
            "total_score": 0.0, "errors": 0,
        })

        for node in self.fleet:
            ns = self.stats[node.node_id]
            ts = tier_stats[node.tier]
            ts["count"] += 1
            ts["attempts"] += ns.attempts
            ts["total_score"] += sum(ns.scores)
            ts["errors"] += ns.errors
            if ns.solved:
                ts["solvers"] += 1

        print(f"  {'Tier':<14} {'Nodes':>6} {'Attempts':>9} {'Avg Score':>10} {'Solvers':>8} {'Errors':>7}")
        print(f"  {'-'*12}   {'-'*5}  {'-'*8}  {'-'*9}  {'-'*7}  {'-'*6}")
        for tier in ["jetmini", "zima", "mid-gpu", "heavy-gpu", "queen"]:
            ts = tier_stats[tier]
            avg = ts["total_score"] / max(ts["attempts"], 1)
            print(
                f"  {tier:<14} {ts['count']:>6} {ts['attempts']:>9} {avg:>10.4f} {ts['solvers']:>8} {ts['errors']:>7}"
            )

        total_attempts = sum(ts["attempts"] for ts in tier_stats.values())
        total_errors = sum(ts["errors"] for ts in tier_stats.values())
        print(f"  {'TOTAL':<14} {len(self.fleet):>6} {total_attempts:>9} {'':>10} "
              f"{sum(ts['solvers'] for ts in tier_stats.values()):>8} {total_errors:>7}")

        # ── Fetch reward breakdown from API ──────────────────────────────
        rewards_data = await self._get(client, f"/blocks/{self.block_id}/rewards")

        print("\n--- REWARD DISTRIBUTION ---")
        if rewards_data:
            print(f"  Total pool:        {rewards_data.get('total_pool', 0):.2f}")
            print(f"  Solver pool:       {rewards_data.get('solver_pool', 0):.2f}")
            print(f"  Lineage pool:      {rewards_data.get('lineage_pool', 0):.2f}")
            print(f"  Exploration pool:  {rewards_data.get('exploration_pool', 0):.2f}")
            print(f"  Efficiency pool:   {rewards_data.get('efficiency_pool', 0):.2f}")

            # Aggregate rewards by type
            reward_by_type: dict[str, float] = defaultdict(float)
            reward_by_node: dict[str, float] = defaultdict(float)
            reward_detail_by_node: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

            for r in rewards_data.get("rewards", []):
                rtype = r.get("reward_type", "unknown")
                amt = r.get("reward_amount", 0)
                nid = r.get("node_id", "?")
                reward_by_type[rtype] += amt
                reward_by_node[nid] += amt
                reward_detail_by_node[nid][rtype] += amt

            print("\n  Rewards by type:")
            for rtype, amt in sorted(reward_by_type.items(), key=lambda x: -x[1]):
                print(f"    {rtype:<20} {amt:>10.4f}")

            # ── Top 20 nodes by total rewards ────────────────────────────
            print("\n--- TOP 20 NODES BY TOTAL REWARDS ---")
            sorted_nodes = sorted(reward_by_node.items(), key=lambda x: -x[1])[:20]
            print(f"  {'Rank':<5} {'Node ID':<14} {'Type':<12} {'Total Reward':>13} {'Solver':>9} {'Lineage':>9} {'Explore':>9} {'Effic.':>9} {'Sale':>9}")
            print(f"  {'-'*4}  {'-'*13} {'-'*11}  {'-'*12} {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")

            # Build a node_id -> tier lookup
            nid_to_tier = {n.node_id: n.tier for n in self.fleet}

            for rank, (nid, total) in enumerate(sorted_nodes, 1):
                det = reward_detail_by_node[nid]
                tier = nid_to_tier.get(nid, "?")
                print(
                    f"  {rank:<5} {nid:<14} {tier:<12} {total:>13.4f} "
                    f"{det.get('solver', 0):>9.4f} "
                    f"{det.get('lineage', 0):>9.4f} "
                    f"{det.get('exploration', 0):>9.4f} "
                    f"{det.get('efficiency', 0):>9.4f} "
                    f"{det.get('dataset_sale', 0):>9.4f}"
                )
        else:
            print("  (reward data unavailable — block may not have been finalized)")

        # ── Anti-spam node analysis ──────────────────────────────────────
        print("\n--- ANTI-SPAM / DUPLICATE NODE ANALYSIS ---")
        spam_nodes = [n for n in self.fleet if n.is_spam]
        dup_nodes = [n for n in self.fleet if n.is_duplicate]

        print(f"  Spam nodes ({len(spam_nodes)}):")
        for node in spam_nodes:
            ns = self.stats[node.node_id]
            avg = sum(ns.scores) / max(len(ns.scores), 1)
            reward = 0.0
            if rewards_data:
                for r in rewards_data.get("rewards", []):
                    if r.get("node_id") == node.node_id:
                        reward += r.get("reward_amount", 0)
            print(f"    {node.node_id}: attempts={ns.attempts}, avg_score={avg:.4f}, reward={reward:.4f}")

        print(f"\n  Duplicate nodes ({len(dup_nodes)}):")
        for node in dup_nodes:
            ns = self.stats[node.node_id]
            avg = sum(ns.scores) / max(len(ns.scores), 1)
            reward = 0.0
            if rewards_data:
                for r in rewards_data.get("rewards", []):
                    if r.get("node_id") == node.node_id:
                        reward += r.get("reward_amount", 0)
            print(f"    {node.node_id}: attempts={ns.attempts}, avg_score={avg:.4f}, reward={reward:.4f}")

        # ── Dataset sale economics ───────────────────────────────────────
        print("\n--- ECONOMIC SUMMARY (DATASET SALE) ---")
        if sale_result:
            sale_price = sale_result.get("sale_price", 0)
            platform_fee = sale_result.get("platform_fee", 0)
            distributable = sale_result.get("distributable", 0)

            summary = sale_result.get("payout_summary", {})
            total_distributed = summary.get("total_distributed", 0)
            undistributed = summary.get("undistributed", 0)
            payouts = summary.get("payouts", [])

            print(f"  Sale price:          ${sale_price:,.2f}")
            print(f"  Platform fee (10%):  ${platform_fee:,.2f}")
            print(f"  Distributable:       ${distributable:,.2f}")
            print(f"  Total distributed:   ${total_distributed:,.2f}")
            print(f"  Undistributed:       ${undistributed:,.2f}")
            print(f"  Payout count:        {sale_result.get('payout_count', 0)}")

            # Show penalized payouts
            penalized = [p for p in payouts if p.get("penalty_reason")]
            if penalized:
                print(f"\n  Penalized payouts ({len(penalized)}):")
                for p in sorted(penalized, key=lambda x: x.get("final_payout", 0)):
                    print(
                        f"    {p['node_id']:<14} base=${p.get('base_payout', 0):>8.2f} "
                        f"final=${p.get('final_payout', 0):>8.2f} "
                        f"penalty_mult={p.get('penalty_multiplier', 1):.4f} "
                        f"reason={p.get('penalty_reason')}"
                    )
            else:
                print("  (no penalized payouts)")

            # Top sale payouts
            top_payouts = sorted(payouts, key=lambda x: -x.get("final_payout", 0))[:10]
            if top_payouts:
                print(f"\n  Top 10 sale payouts:")
                for p in top_payouts:
                    tier = nid_to_tier.get(p["node_id"], "?")
                    print(
                        f"    {p['node_id']:<14} ({tier:<10}) "
                        f"${p.get('final_payout', 0):>8.2f}  "
                        f"rep={p.get('reputation', 0):.4f}"
                    )
        else:
            print("  (dataset sale result unavailable)")

        # ── Fetch overall economics stats ────────────────────────────────
        econ_stats = await self._get(client, "/economics/stats")
        if econ_stats:
            print("\n--- SYSTEM-WIDE ECONOMICS ---")
            print(f"  Total rewards distributed:  {econ_stats.get('total_rewards_distributed', 0):.4f}")
            rbt = econ_stats.get("rewards_by_type", {})
            for rtype, amt in sorted(rbt.items(), key=lambda x: -x[1]):
                print(f"    {rtype:<20} {amt:>10.4f}")
            ds = econ_stats.get("dataset_sales", {})
            print(f"  Dataset sales total:        {ds.get('total_sales', 0)}")
            print(f"  Dataset revenue total:      ${ds.get('total_revenue', 0):,.2f}")
            print(f"  Platform fees total:        ${ds.get('total_platform_fees', 0):,.2f}")
            nd = econ_stats.get("nodes", {})
            print(f"  Active nodes:               {nd.get('active', 0)}")
            print(f"  Avg reputation:             {nd.get('avg_reputation', 0):.4f}")

        print("\n" + "=" * 80)
        print("  Demo complete.")
        print("=" * 80 + "\n")

    # ── Main orchestration ───────────────────────────────────────────────

    async def run(self) -> None:
        """Execute the full demo lifecycle."""
        log.info("=" * 60)
        log.info("SwarmChain 100-Node Demo")
        log.info("API: %s", self.api_url)
        log.info("Fleet: %d nodes across 5 tiers", len(self.fleet))
        log.info("Task: %s (mirror horizontal)", TASK_ID)
        log.info("=" * 60)

        async with httpx.AsyncClient() as client:
            # Smoke check: is the API alive?
            root = await self._get(client, "/")
            if not root:
                log.error("Cannot reach API at %s — is the server running?", self.api_url)
                sys.exit(1)
            log.info("API alive: %s v%s", root.get("service"), root.get("version"))

            # Phase 1
            registered = await self.register_nodes(client)
            if registered == 0:
                log.error("No nodes registered — aborting")
                sys.exit(1)

            # Phase 2
            ok = await self.open_block(client)
            if not ok:
                sys.exit(1)

            # Phase 3
            await self.run_rounds(client, num_rounds=10)

            # Phase 4
            block_result = await self.finalize_block(client)

            # Phase 5
            sale_result = await self.dataset_sale(client)

            # Phase 6
            await self.fetch_and_print_results(client, block_result, sale_result)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SwarmChain 100-Node Demo — heterogeneous swarm solves arc-002-mirror-h",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="SwarmChain API base URL (default: http://localhost:8000)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    demo = Demo100Nodes(api_url=args.api_url)
    asyncio.run(demo.run())


if __name__ == "__main__":
    main()
