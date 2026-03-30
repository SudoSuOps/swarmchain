#!/usr/bin/env python3
"""SwarmChain Production Mining Script — mines 1,000 blocks with a 38-node fleet.

Registers a heterogeneous fleet of 38 nodes (20 jetmini, 10 zima, 5 mid-gpu,
3 queen), generates a full 1,000-task catalog from the ARCTaskGenerator, and
runs batched mining rounds until all blocks are sealed (solved or exhausted).

Supports resumption via --resume, reading/writing mining_state.json.

Usage:
    python mine_1000.py --api-url http://localhost:8080
    python mine_1000.py --api-url http://localhost:8080 --resume
    python mine_1000.py --target 500 --batch-size 4 --rounds-per-block 30
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import signal
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# Import ARCTaskGenerator from the backend
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from swarmchain.tasks.arc_generator import ARCTaskGenerator

from strategies import STRATEGY_REGISTRY, Grid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("mine-1000")

STATE_FILE = "mining_state.json"


# ---------------------------------------------------------------------------
# Fleet definitions
# ---------------------------------------------------------------------------

@dataclass
class MinerNode:
    """A fleet miner node with its strategy family."""
    node_id: str
    node_type: str
    hardware_class: str
    strategies: list[str]
    energy_per_attempt: float
    can_derive: bool = False
    registered: bool = False


@dataclass
class BlockMining:
    """Tracks per-block mining state."""
    block_id: str
    task_id: str
    input_grid: Grid
    expected_rows: int
    expected_cols: int
    best_score: float = 0.0
    best_attempt_id: str | None = None
    solved: bool = False
    attempt_count: int = 0
    promoted_cache: list[dict] = field(default_factory=list)


def build_fleet() -> list[MinerNode]:
    """Create the 38-node mining fleet."""
    fleet: list[MinerNode] = []

    # 20 jetmini nodes — cheap edge exploration
    for i in range(1, 21):
        fleet.append(MinerNode(
            node_id=f"miner-jetmini-{i:03d}",
            node_type="jetmini",
            hardware_class="edge-4gb",
            strategies=["random_grid", "copy_input", "random_perturbation"],
            energy_per_attempt=0.2,
        ))

    # 10 zima nodes — structured transforms
    for i in range(1, 11):
        fleet.append(MinerNode(
            node_id=f"miner-zima-{i:03d}",
            node_type="zima",
            hardware_class="low-gpu-8gb",
            strategies=["mirror_h", "mirror_v", "color_swap", "invert"],
            energy_per_attempt=0.5,
        ))

    # 5 mid-gpu nodes — geometric transforms
    for i in range(1, 6):
        fleet.append(MinerNode(
            node_id=f"miner-midgpu-{i:03d}",
            node_type="mid-gpu",
            hardware_class="mid-gpu-24gb",
            strategies=["rotate_90", "rotate_180", "rotate_270", "transpose", "scale_2x", "border_add"],
            energy_per_attempt=1.0,
        ))

    # 3 queen nodes — refinement from promoted parents
    for i in range(1, 4):
        fleet.append(MinerNode(
            node_id=f"miner-queen-{i:03d}",
            node_type="queen",
            hardware_class="high-gpu-48gb",
            strategies=["random_perturbation"],
            energy_per_attempt=2.0,
            can_derive=True,
        ))

    return fleet


# ---------------------------------------------------------------------------
# Stats tracking
# ---------------------------------------------------------------------------

@dataclass
class MiningStats:
    """Aggregate mining statistics."""
    blocks_sealed: int = 0
    blocks_solved: int = 0
    blocks_exhausted: int = 0
    total_attempts: int = 0
    total_energy: float = 0.0
    started_at: float = 0.0
    mined_task_ids: list[str] = field(default_factory=list)
    strategy_stats: dict[str, dict] = field(default_factory=lambda: defaultdict(
        lambda: {"attempts": 0, "solves": 0, "total_score": 0.0, "best_score": 0.0}
    ))
    node_stats: dict[str, dict] = field(default_factory=lambda: defaultdict(
        lambda: {"attempts": 0, "solves": 0, "total_score": 0.0, "total_rewards": 0.0}
    ))

    def save_state(self, path: str) -> None:
        """Persist mining state for resumption."""
        state = {
            "mined_task_ids": self.mined_task_ids,
            "blocks_sealed": self.blocks_sealed,
            "blocks_solved": self.blocks_solved,
            "blocks_exhausted": self.blocks_exhausted,
            "total_attempts": self.total_attempts,
            "total_energy": self.total_energy,
            "started_at": self.started_at,
        }
        with open(path, "w") as f:
            json.dump(state, f, indent=2)

    @classmethod
    def load_state(cls, path: str) -> "MiningStats":
        """Load mining state from file."""
        with open(path, "r") as f:
            state = json.load(f)
        stats = cls()
        stats.mined_task_ids = state.get("mined_task_ids", [])
        stats.blocks_sealed = state.get("blocks_sealed", 0)
        stats.blocks_solved = state.get("blocks_solved", 0)
        stats.blocks_exhausted = state.get("blocks_exhausted", 0)
        stats.total_attempts = state.get("total_attempts", 0)
        stats.total_energy = state.get("total_energy", 0.0)
        stats.started_at = state.get("started_at", time.time())
        return stats


# ---------------------------------------------------------------------------
# Mining engine
# ---------------------------------------------------------------------------

class MiningEngine:
    """Async mining engine — drives a fleet against the ARC task catalog."""

    def __init__(
        self,
        api_url: str,
        target: int,
        batch_size: int,
        rounds_per_block: int,
        api_key: str | None,
        resume: bool,
    ):
        self.api_url = api_url.rstrip("/")
        self.target = target
        self.batch_size = batch_size
        self.rounds_per_block = rounds_per_block
        self.api_key = api_key
        self.resume = resume
        self.fleet = build_fleet()
        self.stats = MiningStats()
        self.shutdown_requested = False
        self._task_catalog: list[dict] = []

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Build request headers, including API key if provided."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def _post(self, client: httpx.AsyncClient, path: str, body: dict) -> dict | None:
        url = f"{self.api_url}{path}"
        try:
            resp = await client.post(url, json=body, headers=self._headers(), timeout=30.0)
            if resp.status_code >= 400:
                log.warning("POST %s -> %d: %s", path, resp.status_code, resp.text[:300])
                return None
            return resp.json()
        except httpx.HTTPError as exc:
            log.error("POST %s error: %s", path, exc)
            return None

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict | None = None) -> dict | None:
        url = f"{self.api_url}{path}"
        try:
            resp = await client.get(url, params=params, headers=self._headers(), timeout=30.0)
            if resp.status_code >= 400:
                log.warning("GET %s -> %d: %s", path, resp.status_code, resp.text[:300])
                return None
            return resp.json()
        except httpx.HTTPError as exc:
            log.error("GET %s error: %s", path, exc)
            return None

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    async def check_api(self, client: httpx.AsyncClient) -> bool:
        """Verify the API is reachable."""
        data = await self._get(client, "/")
        if not data:
            log.error("Cannot reach API at %s", self.api_url)
            return False
        log.info("API alive: %s v%s", data.get("service"), data.get("version"))
        return True

    async def register_fleet(self, client: httpx.AsyncClient) -> int:
        """Register all fleet nodes. Returns count registered."""
        log.info("Registering %d fleet nodes...", len(self.fleet))
        sem = asyncio.Semaphore(20)

        async def _register(node: MinerNode) -> bool:
            async with sem:
                result = await self._post(client, "/nodes/register", {
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "hardware_class": node.hardware_class,
                    "metadata": {
                        "miner": True,
                        "strategies": node.strategies,
                        "can_derive": node.can_derive,
                    },
                })
                if result:
                    node.registered = True
                    return True
                return False

        results = await asyncio.gather(*[_register(n) for n in self.fleet])
        registered = sum(1 for r in results if r)
        log.info("Fleet registered: %d/%d nodes", registered, len(self.fleet))
        return registered

    def generate_catalog(self) -> list[dict]:
        """Generate the full task catalog using ARCTaskGenerator."""
        log.info("Generating %d-task catalog...", self.target)
        gen = ARCTaskGenerator()
        self._task_catalog = gen.generate_catalog(count=self.target, base_seed=42)
        log.info("Catalog ready: %d tasks across %d transform types",
                 len(self._task_catalog),
                 len(set(t["transform_type"] for t in self._task_catalog)))
        return self._task_catalog

    # ------------------------------------------------------------------
    # Block lifecycle
    # ------------------------------------------------------------------

    async def open_block(self, client: httpx.AsyncClient, task: dict) -> BlockMining | None:
        """Open a single block for a task from the catalog."""
        task_payload = {
            "input_grid": task["input_grid"],
            "expected_output": task["expected_output"],
            "description": task["description"],
        }
        result = await self._post(client, "/blocks/open", {
            "task_id": task["task_id"],
            "domain": "arc",
            "reward_pool": 100.0,
            "max_attempts": 2000,
            "time_limit_sec": 7200,
            "task_payload": task_payload,
            "metadata": {
                "miner": True,
                "transform_type": task["transform_type"],
                "seed": task.get("seed"),
                "grid_size": task.get("grid_size"),
            },
        })
        if not result:
            log.error("Failed to open block for %s", task["task_id"])
            return None

        block_id = result["block_id"]
        payload = result.get("task_payload", {})
        input_grid = payload.get("input_grid", task["input_grid"])
        expected = payload.get("expected_output", task["expected_output"])
        exp_rows = len(expected)
        exp_cols = len(expected[0]) if exp_rows > 0 else 0

        return BlockMining(
            block_id=block_id,
            task_id=task["task_id"],
            input_grid=input_grid,
            expected_rows=exp_rows,
            expected_cols=exp_cols,
        )

    async def finalize_block(self, client: httpx.AsyncClient, block: BlockMining) -> str:
        """Finalize a block, returning its final status."""
        result = await self._post(client, f"/blocks/{block.block_id}/finalize", {
            "force": True,
            "reason": "mine-1000-batch-complete",
        })
        if result:
            return result.get("status", "unknown")
        return "error"

    # ------------------------------------------------------------------
    # Attempt generation and submission
    # ------------------------------------------------------------------

    async def _fetch_promoted(self, client: httpx.AsyncClient, block: BlockMining) -> list[dict]:
        """Fetch top-scoring attempts for parent derivation."""
        if block.promoted_cache:
            return block.promoted_cache
        data = await self._get(client, f"/attempts/block/{block.block_id}/top", {"limit": 5})
        if data and data.get("attempts"):
            block.promoted_cache = data["attempts"]
        return block.promoted_cache

    def _pick_parent(self, promoted: list[dict]) -> tuple[str | None, Grid | None]:
        """Pick a promoted parent for derivation strategies."""
        if not promoted:
            return None, None
        weights = [max(a.get("score", 0.01), 0.01) for a in promoted]
        parent = random.choices(promoted, weights=weights, k=1)[0]
        parent_id = parent.get("attempt_id")
        parent_grid = parent.get("output_json", {}).get("grid")
        return parent_id, parent_grid

    async def submit_attempt(
        self,
        client: httpx.AsyncClient,
        node: MinerNode,
        block: BlockMining,
    ) -> float | None:
        """Generate and submit a single attempt. Returns score or None on error."""
        strategy_name = random.choice(node.strategies)
        strategy_fn = STRATEGY_REGISTRY.get(strategy_name)
        if not strategy_fn:
            return None

        parent_attempt_id: str | None = None
        parent_grid: Grid | None = None

        # Queen and random_perturbation derive from parents
        if node.can_derive or (strategy_name == "random_perturbation" and random.random() < 0.7):
            promoted = await self._fetch_promoted(client, block)
            parent_attempt_id, parent_grid = self._pick_parent(promoted)

        # Generate the grid
        t0 = time.monotonic()
        grid = strategy_fn(
            input_grid=block.input_grid,
            expected_dims=(block.expected_rows, block.expected_cols),
            parent_grid=parent_grid,
        )
        latency_ms = int((time.monotonic() - t0) * 1000) + random.randint(5, 50)

        result = await self._post(client, "/attempts", {
            "node_id": node.node_id,
            "block_id": block.block_id,
            "parent_attempt_id": parent_attempt_id,
            "method": f"mine-{strategy_name}",
            "strategy_family": strategy_name,
            "output_json": {"grid": grid},
            "energy_cost": node.energy_per_attempt,
            "latency_ms": latency_ms,
        })

        if not result:
            return None

        score = result.get("score", 0.0)
        block.attempt_count += 1
        self.stats.total_attempts += 1
        self.stats.total_energy += node.energy_per_attempt

        # Update strategy stats
        ss = self.stats.strategy_stats[strategy_name]
        ss["attempts"] += 1
        ss["total_score"] += score
        if score > ss["best_score"]:
            ss["best_score"] = score

        # Update node stats
        ns = self.stats.node_stats[node.node_id]
        ns["attempts"] += 1
        ns["total_score"] += score

        if score > block.best_score:
            block.best_score = score
            block.best_attempt_id = result.get("attempt_id")
            block.promoted_cache = []  # refresh on improvement

        if score == 1.0:
            block.solved = True
            ss["solves"] += 1
            ns["solves"] += 1

        return score

    # ------------------------------------------------------------------
    # Mining loop for a single batch of blocks
    # ------------------------------------------------------------------

    async def mine_batch(
        self,
        client: httpx.AsyncClient,
        blocks: list[BlockMining],
    ) -> None:
        """Mine a batch of blocks through rounds_per_block rounds."""
        active_nodes = [n for n in self.fleet if n.registered]
        sem = asyncio.Semaphore(30)

        for round_num in range(1, self.rounds_per_block + 1):
            if self.shutdown_requested:
                break

            # Filter to unsolved blocks
            open_blocks = [b for b in blocks if not b.solved]
            if not open_blocks:
                break

            # Each node picks an open block and submits
            async def _node_attempt(node: MinerNode) -> None:
                async with sem:
                    block = random.choice(open_blocks)
                    await self.submit_attempt(client, node, block)

            await asyncio.gather(
                *[_node_attempt(n) for n in active_nodes],
                return_exceptions=True,
            )

            # Check if any blocks got solved this round
            newly_solved = [b for b in open_blocks if b.solved]
            for b in newly_solved:
                log.info("SOLVED block %s (%s) at score=%.3f in round %d",
                         b.block_id[:8], b.task_id, b.best_score, round_num)

        # Finalize all blocks in this batch
        for block in blocks:
            status = await self.finalize_block(client, block)
            if block.solved:
                self.stats.blocks_solved += 1
            else:
                self.stats.blocks_exhausted += 1
            self.stats.blocks_sealed += 1
            self.stats.mined_task_ids.append(block.task_id)

    # ------------------------------------------------------------------
    # Main mining loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Execute the full mining pipeline."""
        self.stats.started_at = time.time()

        # Handle resume
        if self.resume and Path(STATE_FILE).exists():
            self.stats = MiningStats.load_state(STATE_FILE)
            log.info("Resumed from state: %d blocks already mined", self.stats.blocks_sealed)
        else:
            self.stats.started_at = time.time()

        # Generate task catalog
        catalog = self.generate_catalog()

        # Filter out already-mined tasks
        mined_set = set(self.stats.mined_task_ids)
        remaining = [t for t in catalog if t["task_id"] not in mined_set]
        log.info("Tasks remaining: %d / %d", len(remaining), len(catalog))

        if not remaining:
            log.info("All tasks already mined. Nothing to do.")
            self._print_summary()
            return

        async with httpx.AsyncClient() as client:
            # Check API
            if not await self.check_api(client):
                return

            # Register fleet
            registered = await self.register_fleet(client)
            if registered == 0:
                log.error("No fleet nodes registered. Aborting.")
                return

            # Install signal handlers
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_shutdown)

            # Mine in batches
            batch_num = 0
            while remaining and not self.shutdown_requested:
                batch_tasks = remaining[:self.batch_size]
                remaining = remaining[self.batch_size:]
                batch_num += 1

                log.info("--- Batch %d: opening %d blocks ---", batch_num, len(batch_tasks))

                # Open blocks for this batch
                open_coros = [self.open_block(client, t) for t in batch_tasks]
                block_results = await asyncio.gather(*open_coros, return_exceptions=True)
                blocks = [b for b in block_results if isinstance(b, BlockMining) and b is not None]

                if not blocks:
                    log.error("Failed to open any blocks in batch %d", batch_num)
                    continue

                # Mine the batch
                await self.mine_batch(client, blocks)

                # Save state after each batch
                self.stats.save_state(STATE_FILE)

                # Progress log every 10 sealed blocks (or every batch)
                if self.stats.blocks_sealed % 10 <= self.batch_size or not remaining:
                    self._log_progress()

            # Fetch reward data for summary
            await self._fetch_node_rewards(client)

        self._print_summary()

    async def _fetch_node_rewards(self, client: httpx.AsyncClient) -> None:
        """Fetch reward totals for each node from the API."""
        for node in self.fleet:
            if not node.registered:
                continue
            data = await self._get(client, f"/nodes/{node.node_id}/stats")
            if data:
                self.stats.node_stats[node.node_id]["total_rewards"] = data.get("total_rewards", 0.0)

    def _handle_shutdown(self) -> None:
        """Handle graceful shutdown on SIGINT/SIGTERM."""
        log.info("Shutdown requested. Finishing current batch...")
        self.shutdown_requested = True

    # ------------------------------------------------------------------
    # Progress and summary output
    # ------------------------------------------------------------------

    def _log_progress(self) -> None:
        """Print progress line."""
        elapsed = time.time() - self.stats.started_at
        rate = self.stats.blocks_sealed / max(elapsed / 3600, 0.001)
        remaining = self.target - self.stats.blocks_sealed
        eta_hours = remaining / max(rate, 0.001)
        solve_pct = 100 * self.stats.blocks_solved / max(self.stats.blocks_sealed, 1)

        print(
            f"[Mining] {self.stats.blocks_sealed}/{self.target} sealed | "
            f"{self.stats.blocks_solved} solved ({solve_pct:.0f}%) | "
            f"{self.stats.blocks_exhausted} exhausted | "
            f"{self.stats.total_attempts:,} attempts | "
            f"{rate:.1f} blk/hr | "
            f"ETA: {eta_hours:.0f}h",
            flush=True,
        )

    def _print_summary(self) -> None:
        """Print the final mining summary."""
        elapsed = time.time() - self.stats.started_at
        elapsed_hours = elapsed / 3600
        solve_pct = 100 * self.stats.blocks_solved / max(self.stats.blocks_sealed, 1)
        exhaust_pct = 100 * self.stats.blocks_exhausted / max(self.stats.blocks_sealed, 1)

        print("\n" + "=" * 60)
        print(f"  MINING COMPLETE -- {self.stats.blocks_sealed:,} BLOCKS SEALED")
        print("=" * 60)
        print(f"  Solved:    {self.stats.blocks_solved} ({solve_pct:.1f}%)")
        print(f"  Exhausted: {self.stats.blocks_exhausted} ({exhaust_pct:.1f}%)")
        print(f"  Total attempts: {self.stats.total_attempts:,}")
        print(f"  Total energy: {self.stats.total_energy:,.1f}")
        print(f"  Runtime: {elapsed_hours:.1f} hours")
        print()

        # Top strategies by solve rate
        print("  Top strategies by solve rate:")
        strat_items = []
        for name, ss in self.stats.strategy_stats.items():
            if isinstance(ss, dict) and ss.get("attempts", 0) > 0:
                strat_items.append((name, ss))
        strat_items.sort(key=lambda x: x[1].get("solves", 0) / max(x[1].get("attempts", 1), 1), reverse=True)

        for name, ss in strat_items[:15]:
            attempts = ss.get("attempts", 0)
            solves = ss.get("solves", 0)
            pct = 100 * solves / max(attempts, 1)
            print(f"    {name:<22} {solves:>5}/{attempts:<5} ({pct:.0f}%)")

        print()

        # Top nodes by rewards
        print("  Top nodes by rewards:")
        node_items = []
        for nid, ns in self.stats.node_stats.items():
            if isinstance(ns, dict):
                node_items.append((nid, ns))
        node_items.sort(key=lambda x: x[1].get("total_rewards", 0), reverse=True)

        for nid, ns in node_items[:15]:
            rewards = ns.get("total_rewards", 0.0)
            attempts = ns.get("attempts", 0)
            solves = ns.get("solves", 0)
            print(f"    {nid:<25} ${rewards:>10,.2f}  ({solves} solves, {attempts} attempts)")

        print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SwarmChain Production Mining -- mine 1,000 blocks with a 38-node fleet",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8080",
        help="SwarmChain API base URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=1000,
        help="Number of blocks to mine (default: 1000)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Number of blocks to open per batch (default: 8)",
    )
    parser.add_argument(
        "--rounds-per-block",
        type=int,
        default=50,
        help="Maximum rounds per block before force-finalize (default: 50)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional API key for authenticated endpoints",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from mining_state.json if it exists",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    engine = MiningEngine(
        api_url=args.api_url,
        target=args.target,
        batch_size=args.batch_size,
        rounds_per_block=args.rounds_per_block,
        api_key=args.api_key,
        resume=args.resume,
    )
    asyncio.run(engine.run())


if __name__ == "__main__":
    main()
