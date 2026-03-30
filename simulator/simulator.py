#!/usr/bin/env python3
"""SwarmChain Node Simulator — drives a heterogeneous swarm against ARC blocks.

Registers four node types with different strategy families, opens blocks for
the ARC task catalog, and runs configurable rounds of distributed solving.
Each node picks an open block, generates an attempt via its assigned strategy,
submits it to the API, and logs the score.  After all rounds complete, every
block is finalized.

Usage:
    python simulator.py --api-url http://localhost:8000 --rounds 20 --delay 0.1
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
import time
from dataclasses import dataclass, field

import httpx

from strategies import STRATEGY_REGISTRY, Grid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("swarm-sim")


# ---------------------------------------------------------------------------
# ARC task catalog (must match backend/swarmchain/tasks/arc_tasks.py)
# ---------------------------------------------------------------------------

ARC_TASKS = [
    "arc-001-fill-blue",
    "arc-002-mirror-h",
    "arc-003-rotate-90",
    "arc-004-color-swap",
    "arc-005-border",
    "arc-006-transpose",
    "arc-007-invert",
    "arc-008-scale-2x",
]


# ---------------------------------------------------------------------------
# Node definitions
# ---------------------------------------------------------------------------

@dataclass
class NodeProfile:
    """A simulated compute node with its strategy family."""
    node_id: str
    node_type: str
    hardware_class: str
    strategies: list[str]
    energy_per_attempt: float
    latency_base_ms: int
    can_derive: bool = False          # queen-only: always derive from parent
    registered: bool = False


# The four node types and their strategy families
NODE_PROFILES: list[NodeProfile] = [
    NodeProfile(
        node_id="sim-jetmini-01",
        node_type="jetmini",
        hardware_class="edge-4gb",
        strategies=["random_grid", "copy_input", "random_perturbation"],
        energy_per_attempt=0.2,
        latency_base_ms=15,
    ),
    NodeProfile(
        node_id="sim-zima-lowgpu-01",
        node_type="zima-lowgpu",
        hardware_class="low-gpu-8gb",
        strategies=["mirror_h", "mirror_v", "color_swap", "invert"],
        energy_per_attempt=0.5,
        latency_base_ms=40,
    ),
    NodeProfile(
        node_id="sim-midgpu-01",
        node_type="mid-gpu",
        hardware_class="mid-gpu-24gb",
        strategies=["rotate_90", "rotate_180", "rotate_270", "transpose", "scale_2x", "border_add"],
        energy_per_attempt=1.0,
        latency_base_ms=80,
    ),
    NodeProfile(
        node_id="sim-queen-01",
        node_type="queen",
        hardware_class="high-gpu-48gb",
        strategies=["random_perturbation"],
        energy_per_attempt=2.0,
        latency_base_ms=150,
        can_derive=True,
    ),
]


# ---------------------------------------------------------------------------
# Block tracking
# ---------------------------------------------------------------------------

@dataclass
class BlockState:
    """Tracks per-block simulation state."""
    block_id: str
    task_id: str
    input_grid: Grid
    expected_rows: int
    expected_cols: int
    best_score: float = 0.0
    best_attempt_id: str | None = None
    solved: bool = False
    promoted_attempts: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class SwarmSimulator:
    """Async simulator that drives a swarm of nodes against ARC blocks."""

    def __init__(self, api_url: str, rounds: int, delay: float, api_key: str = ""):
        self.api_url = api_url.rstrip("/")
        self.rounds = rounds
        self.delay = delay
        self.api_key = api_key
        self.blocks: dict[str, BlockState] = {}
        self.nodes = NODE_PROFILES
        self.stats: dict[str, dict] = {}   # node_id -> {attempts, solves, total_score}

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _post(self, client: httpx.AsyncClient, path: str, json: dict) -> dict | None:
        """POST to the API and return JSON response, or None on error."""
        url = f"{self.api_url}{path}"
        try:
            resp = await client.post(url, json=json, timeout=30.0)
            if resp.status_code >= 400:
                log.warning("POST %s -> %s: %s", path, resp.status_code, resp.text[:300])
                return None
            return resp.json()
        except httpx.HTTPError as exc:
            log.error("POST %s failed: %s", path, exc)
            return None

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict | None = None) -> dict | None:
        """GET from the API."""
        url = f"{self.api_url}{path}"
        try:
            resp = await client.get(url, params=params, timeout=30.0)
            if resp.status_code >= 400:
                log.warning("GET %s -> %s: %s", path, resp.status_code, resp.text[:300])
                return None
            return resp.json()
        except httpx.HTTPError as exc:
            log.error("GET %s failed: %s", path, exc)
            return None

    # ------------------------------------------------------------------
    # Setup phase
    # ------------------------------------------------------------------

    async def register_nodes(self, client: httpx.AsyncClient) -> None:
        """Register all simulated nodes with the API."""
        for node in self.nodes:
            result = await self._post(client, "/nodes/register", {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "hardware_class": node.hardware_class,
                "metadata": {
                    "simulator": True,
                    "strategies": node.strategies,
                },
            })
            if result:
                node.registered = True
                self.stats[node.node_id] = {"attempts": 0, "solves": 0, "total_score": 0.0}
                log.info("Registered node %s (%s)", node.node_id, node.node_type)
            else:
                log.error("Failed to register node %s", node.node_id)

    async def open_blocks(self, client: httpx.AsyncClient) -> None:
        """Open a block for each ARC task in the catalog."""
        for task_id in ARC_TASKS:
            result = await self._post(client, "/blocks/open", {
                "task_id": task_id,
                "domain": "arc",
                "reward_pool": 100.0,
                "max_attempts": 500,
                "time_limit_sec": 3600,
                "metadata": {"simulator": True},
            })
            if result:
                block_id = result["block_id"]
                payload = result.get("task_payload", {})
                input_grid = payload.get("input_grid", [])
                expected = payload.get("expected_output", [])
                exp_rows = len(expected)
                exp_cols = len(expected[0]) if exp_rows > 0 else 0

                self.blocks[block_id] = BlockState(
                    block_id=block_id,
                    task_id=task_id,
                    input_grid=input_grid,
                    expected_rows=exp_rows,
                    expected_cols=exp_cols,
                )
                log.info("Opened block %s for task %s (%dx%d output)",
                         block_id, task_id, exp_rows, exp_cols)
            else:
                log.error("Failed to open block for task %s", task_id)

    # ------------------------------------------------------------------
    # Attempt submission
    # ------------------------------------------------------------------

    async def _pick_parent(self, client: httpx.AsyncClient, block: BlockState) -> dict | None:
        """Pick a promoted parent attempt for derivation strategies.

        Returns the top-scoring attempt for the block, or None.
        """
        if not block.promoted_attempts:
            # Fetch top attempts from the API
            data = await self._get(client, f"/attempts/block/{block.block_id}/top", {"limit": 5})
            if data and data.get("attempts"):
                block.promoted_attempts = data["attempts"]

        if block.promoted_attempts:
            # Weighted random by score — favor better parents
            attempts = block.promoted_attempts
            weights = [max(a.get("score", 0.01), 0.01) for a in attempts]
            return random.choices(attempts, weights=weights, k=1)[0]
        return None

    async def submit_attempt(
        self,
        client: httpx.AsyncClient,
        node: NodeProfile,
        block: BlockState,
    ) -> None:
        """Generate and submit a single attempt for a node against a block."""
        # Pick strategy
        strategy_name = random.choice(node.strategies)
        strategy_fn = STRATEGY_REGISTRY[strategy_name]

        # Queen always derives from a parent; other nodes sometimes do
        parent_attempt_id: str | None = None
        parent_grid: Grid | None = None

        if node.can_derive or (strategy_name == "random_perturbation" and random.random() < 0.7):
            parent = await self._pick_parent(client, block)
            if parent:
                parent_attempt_id = parent["attempt_id"]
                parent_grid = parent.get("output_json", {}).get("grid")

        # For the queen, skip if no parent is available (queen only refines)
        if node.can_derive and parent_grid is None:
            # Fall back to perturbing the input
            parent_grid = None

        # Generate the grid
        t0 = time.monotonic()
        grid = strategy_fn(
            input_grid=block.input_grid,
            expected_dims=(block.expected_rows, block.expected_cols),
            parent_grid=parent_grid,
        )
        latency_ms = int((time.monotonic() - t0) * 1000) + node.latency_base_ms + random.randint(0, 20)

        # Submit
        result = await self._post(client, "/attempts", {
            "node_id": node.node_id,
            "block_id": block.block_id,
            "parent_attempt_id": parent_attempt_id,
            "method": f"sim-{strategy_name}",
            "strategy_family": strategy_name,
            "output_json": {"grid": grid},
            "energy_cost": node.energy_per_attempt,
            "latency_ms": latency_ms,
        })

        if result:
            score = result.get("score", 0.0)
            valid = result.get("valid", False)
            attempt_id = result.get("attempt_id", "?")
            node_stats = self.stats[node.node_id]
            node_stats["attempts"] += 1
            node_stats["total_score"] += score

            # Track best
            if score > block.best_score:
                block.best_score = score
                block.best_attempt_id = attempt_id
                # Refresh promoted parents on improvement
                block.promoted_attempts = []

            if score == 1.0:
                block.solved = True
                node_stats["solves"] += 1
                log.info(
                    "SOLVED! Block %s (%s) by %s using %s — score=%.3f",
                    block.block_id, block.task_id, node.node_id, strategy_name, score,
                )
            elif valid:
                log.debug(
                    "Attempt %s: block=%s node=%s strategy=%s score=%.3f",
                    attempt_id, block.block_id, node.node_id, strategy_name, score,
                )

    # ------------------------------------------------------------------
    # Simulation loop
    # ------------------------------------------------------------------

    async def run_round(self, client: httpx.AsyncClient, round_num: int) -> None:
        """Run one round: each node picks an open block and submits an attempt."""
        open_blocks = [b for b in self.blocks.values() if not b.solved]
        if not open_blocks:
            log.info("Round %d: all blocks solved — nothing to do", round_num)
            return

        active_nodes = [n for n in self.nodes if n.registered]
        tasks: list = []

        for node in active_nodes:
            # Each node picks a random open block
            block = random.choice(open_blocks)
            tasks.append(self.submit_attempt(client, node, block))

        # Run all node attempts concurrently within the round
        await asyncio.gather(*tasks, return_exceptions=True)

    async def finalize_blocks(self, client: httpx.AsyncClient) -> None:
        """Finalize all blocks after simulation completes."""
        for block in self.blocks.values():
            result = await self._post(
                client,
                f"/blocks/{block.block_id}/finalize",
                {"force": True, "reason": "simulator-complete"},
            )
            status = result.get("status", "?") if result else "error"
            log.info(
                "Finalized block %s (%s): status=%s best_score=%.3f solved=%s",
                block.block_id, block.task_id, status, block.best_score, block.solved,
            )

    async def run(self) -> None:
        """Execute the full simulation lifecycle."""
        log.info("=" * 60)
        log.info("SwarmChain Node Simulator")
        log.info("API: %s | Rounds: %d | Delay: %.2fs", self.api_url, self.rounds, self.delay)
        log.info("Nodes: %s", ", ".join(f"{n.node_id} ({n.node_type})" for n in self.nodes))
        log.info("=" * 60)

        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        async with httpx.AsyncClient(headers=headers) as client:
            # Phase 1: Register nodes
            log.info("--- Phase 1: Register nodes ---")
            await self.register_nodes(client)

            registered = sum(1 for n in self.nodes if n.registered)
            if registered == 0:
                log.error("No nodes registered — is the API running at %s?", self.api_url)
                return

            # Phase 2: Open blocks
            log.info("--- Phase 2: Open blocks ---")
            await self.open_blocks(client)

            if not self.blocks:
                log.error("No blocks opened — aborting")
                return

            # Phase 3: Run rounds
            log.info("--- Phase 3: Simulation (%d rounds) ---", self.rounds)
            for round_num in range(1, self.rounds + 1):
                await self.run_round(client, round_num)

                # Status summary every 5 rounds
                if round_num % 5 == 0 or round_num == self.rounds:
                    solved = sum(1 for b in self.blocks.values() if b.solved)
                    total = len(self.blocks)
                    best_scores = [f"{b.task_id}={b.best_score:.3f}" for b in self.blocks.values()]
                    log.info(
                        "Round %d/%d — solved %d/%d blocks | %s",
                        round_num, self.rounds, solved, total,
                        " | ".join(best_scores),
                    )

                if self.delay > 0:
                    await asyncio.sleep(self.delay)

            # Phase 4: Finalize
            log.info("--- Phase 4: Finalize blocks ---")
            await self.finalize_blocks(client)

            # Summary
            self._print_summary()

    def _print_summary(self) -> None:
        """Print final simulation summary."""
        log.info("=" * 60)
        log.info("SIMULATION COMPLETE")
        log.info("=" * 60)

        solved = sum(1 for b in self.blocks.values() if b.solved)
        total = len(self.blocks)
        log.info("Blocks solved: %d / %d (%.0f%%)", solved, total, 100 * solved / max(total, 1))

        log.info("")
        log.info("Per-block results:")
        for b in self.blocks.values():
            log.info(
                "  %-25s best=%.3f  solved=%s",
                b.task_id, b.best_score, b.solved,
            )

        log.info("")
        log.info("Per-node stats:")
        for node in self.nodes:
            s = self.stats.get(node.node_id, {})
            attempts = s.get("attempts", 0)
            solves = s.get("solves", 0)
            avg = s.get("total_score", 0) / max(attempts, 1)
            log.info(
                "  %-25s type=%-12s attempts=%-4d solves=%-2d avg_score=%.3f",
                node.node_id, node.node_type, attempts, solves, avg,
            )

        log.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SwarmChain Node Simulator — drive a heterogeneous swarm against ARC blocks",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="SwarmChain API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=20,
        help="Number of simulation rounds (default: 20)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Delay between rounds in seconds (default: 0.1)",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key for authenticated endpoints (X-API-Key header)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sim = SwarmSimulator(
        api_url=args.api_url,
        rounds=args.rounds,
        delay=args.delay,
        api_key=args.api_key,
    )
    asyncio.run(sim.run())


if __name__ == "__main__":
    main()
