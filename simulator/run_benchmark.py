#!/usr/bin/env python3
"""SwarmBench Orchestrator — run all 3 systems on the same task set, compare.

Generates a deterministic task set, runs Baseline A, Baseline B, and the
SwarmChain simulator, then collects results and produces comparison tables.

All systems use the SwarmChain API for scoring, ensuring identical evaluation.

Usage:
    python run_benchmark.py --api-url http://localhost:8000 --tasks-per-tier 50 --api-key <key>
    python run_benchmark.py --api-url http://localhost:8080/api --tasks-per-tier 25 --base-seed 42
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import httpx

# Add backend to path for task generator
sys.path.insert(0, "/data2/swarmchain/backend")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [swarm-bench] %(message)s",
)
log = logging.getLogger("swarm-bench")

# Import components
from baseline_a import BaselineA, TaskResult as TaskResultA
from baseline_b import BaselineB, TaskResult as TaskResultB

HONEY_THRESHOLD = 0.95
JELLY_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# SwarmChain simulator runner
# ---------------------------------------------------------------------------

def run_swarmchain_simulator(
    api_url: str,
    tasks: list[dict],
    api_key: str = "",
    rounds: int = 20,
) -> list[dict]:
    """Run the SwarmChain simulator on a set of tasks and collect results.

    Opens blocks for each task, runs the distributed simulator, then
    collects per-block results from the API after finalization.
    """
    from simulator import SwarmSimulator, ARC_TASKS, NodeProfile, NODE_PROFILES

    # Register custom node_id prefix so we can identify SwarmChain blocks
    api_url_clean = api_url.rstrip("/")
    headers = {"X-API-Key": api_key} if api_key else {}

    # We need to open blocks for OUR specific tasks, then run the simulator
    # The simulator normally opens its own blocks for ARC_TASKS, but we
    # want it to work on our specific task set.
    # Strategy: open blocks via API, then run simulator rounds against them.

    results: list[dict] = []

    with httpx.Client(headers=headers) as client:
        # Phase 1: Open blocks for each task
        block_ids: list[str] = []
        task_map: dict[str, dict] = {}

        for task in tasks:
            task_id = task["task_id"]
            resp = client.post(
                f"{api_url_clean}/blocks/open",
                json={
                    "task_id": task_id,
                    "domain": "arc",
                    "reward_pool": 100.0,
                    "max_attempts": 500,
                    "time_limit_sec": 3600,
                    "task_payload": task,
                    "metadata": {"benchmark": "swarmchain"},
                },
                timeout=30.0,
            )
            if resp.status_code >= 400:
                log.warning("Failed to open block for %s: %s", task_id, resp.text[:200])
                continue

            data = resp.json()
            block_id = data["block_id"]
            block_ids.append(block_id)
            task_map[block_id] = task

        log.info("SwarmChain: opened %d blocks", len(block_ids))

        # Phase 2: Register simulator nodes
        from strategies import STRATEGY_REGISTRY

        node_configs = [
            {
                "node_id": "swarm-bench-edge-01",
                "node_type": "jetmini",
                "hardware_class": "edge-4gb",
                "strategies": ["random_grid", "copy_input", "random_perturbation"],
                "energy": 0.2,
            },
            {
                "node_id": "swarm-bench-zima-01",
                "node_type": "zima-lowgpu",
                "hardware_class": "low-gpu-8gb",
                "strategies": ["mirror_h", "mirror_v", "color_swap", "invert"],
                "energy": 0.5,
            },
            {
                "node_id": "swarm-bench-mid-01",
                "node_type": "mid-gpu",
                "hardware_class": "mid-gpu-24gb",
                "strategies": [
                    "rotate_90", "rotate_180", "rotate_270",
                    "transpose", "scale_2x", "border_add",
                ],
                "energy": 1.0,
            },
            {
                "node_id": "swarm-bench-queen-01",
                "node_type": "queen",
                "hardware_class": "high-gpu-48gb",
                "strategies": ["random_perturbation"],
                "energy": 2.0,
            },
        ]

        registered_nodes: list[dict] = []
        for nc in node_configs:
            resp = client.post(
                f"{api_url_clean}/nodes/register",
                json={
                    "node_id": nc["node_id"],
                    "node_type": nc["node_type"],
                    "hardware_class": nc["hardware_class"],
                    "metadata": {
                        "benchmark": True,
                        "strategies": nc["strategies"],
                    },
                },
                timeout=30.0,
            )
            if resp.status_code < 400:
                registered_nodes.append(nc)

        log.info("SwarmChain: registered %d nodes", len(registered_nodes))

        if not registered_nodes:
            log.error("No nodes registered for SwarmChain simulation")
            return results

        # Phase 3: Run distributed simulation rounds
        import random

        total_attempts = 0
        total_energy = 0.0
        wall_start = time.monotonic()

        for round_num in range(1, rounds + 1):
            # Get open blocks from our set
            open_blocks = []
            for bid in block_ids:
                resp = client.get(f"{api_url_clean}/blocks/{bid}", timeout=30.0)
                if resp.status_code == 200:
                    bdata = resp.json()
                    if bdata.get("status") == "open":
                        open_blocks.append(bdata)

            if not open_blocks:
                log.info("SwarmChain round %d: all blocks resolved", round_num)
                break

            # Each node picks a random open block and submits
            for nc in registered_nodes:
                if not open_blocks:
                    break

                block = random.choice(open_blocks)
                block_id = block["block_id"]
                payload = block.get("task_payload", {})
                input_grid = payload.get("input_grid", [])
                expected = payload.get("expected_output", [])
                exp_rows = len(expected)
                exp_cols = len(expected[0]) if exp_rows else 0

                strategy_name = random.choice(nc["strategies"])

                # Check if strategy exists in registry
                strategy_fn = STRATEGY_REGISTRY.get(strategy_name)
                if not strategy_fn:
                    continue

                # Get parent for queen/perturbation
                parent_grid = None
                if nc["node_type"] == "queen" or (
                    strategy_name == "random_perturbation" and random.random() < 0.7
                ):
                    top_resp = client.get(
                        f"{api_url_clean}/attempts/block/{block_id}/top",
                        params={"limit": 5}, timeout=30.0,
                    )
                    if top_resp.status_code == 200:
                        top_data = top_resp.json()
                        top_attempts = top_data.get("attempts", [])
                        if top_attempts:
                            weights = [max(a.get("score", 0.01), 0.01) for a in top_attempts]
                            parent = random.choices(top_attempts, weights=weights, k=1)[0]
                            parent_grid = parent.get("output_json", {}).get("grid")

                # Generate grid
                grid = strategy_fn(
                    input_grid=input_grid,
                    expected_dims=(exp_rows, exp_cols),
                    parent_grid=parent_grid,
                )

                # Submit
                resp = client.post(
                    f"{api_url_clean}/attempts",
                    json={
                        "node_id": nc["node_id"],
                        "block_id": block_id,
                        "method": f"swarm-bench-{strategy_name}",
                        "strategy_family": strategy_name,
                        "output_json": {"grid": grid},
                        "energy_cost": nc["energy"],
                        "latency_ms": random.randint(10, 200),
                    },
                    timeout=30.0,
                )

                if resp.status_code < 400:
                    total_attempts += 1
                    total_energy += nc["energy"]

            if round_num % 5 == 0:
                solved = sum(
                    1 for bid in block_ids
                    if client.get(
                        f"{api_url_clean}/blocks/{bid}", timeout=10.0
                    ).json().get("status") == "solved"
                )
                log.info(
                    "SwarmChain round %d/%d: %d/%d solved, %d attempts",
                    round_num, rounds, solved, len(block_ids), total_attempts,
                )

        swarm_wall_time = time.monotonic() - wall_start

        # Phase 4: Finalize all blocks and collect results
        for block_id in block_ids:
            # Finalize
            client.post(
                f"{api_url_clean}/blocks/{block_id}/finalize",
                json={"force": True, "reason": "benchmark-complete"},
                timeout=30.0,
            )

            # Get block status
            resp = client.get(f"{api_url_clean}/blocks/{block_id}", timeout=30.0)
            if resp.status_code != 200:
                continue

            bdata = resp.json()
            status = bdata.get("status", "unknown")
            score = bdata.get("final_score") or 0.0
            attempts = bdata.get("attempt_count", 0)
            energy = bdata.get("total_energy", 0.0)
            task_id = bdata.get("task_id", "unknown")

            if score >= HONEY_THRESHOLD:
                outcome = "honey"
            elif score >= JELLY_THRESHOLD:
                outcome = "jelly"
            else:
                outcome = "propolis"

            results.append({
                "task_id": task_id,
                "block_id": block_id,
                "outcome": outcome,
                "best_score": score,
                "attempts": attempts,
                "total_energy": energy,
                "wall_time_sec": swarm_wall_time / max(len(block_ids), 1),
            })

    return results


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------

def compute_aggregates(results: list[dict], system_name: str) -> dict:
    """Compute aggregate metrics for a set of results."""
    total = len(results) or 1
    honey = sum(1 for r in results if r.get("outcome") == "honey")
    jelly = sum(1 for r in results if r.get("outcome") == "jelly")
    propolis = sum(1 for r in results if r.get("outcome") == "propolis")

    total_attempts = sum(r.get("attempts", 0) for r in results)
    total_energy = sum(r.get("total_energy", 0) for r in results)
    total_wall = sum(r.get("wall_time_sec", 0) for r in results)

    solved_count = max(honey, 1)

    return {
        "system": system_name,
        "tasks": len(results),
        "honey": honey,
        "honey_pct": round(100 * honey / total, 1),
        "jelly": jelly,
        "jelly_pct": round(100 * jelly / total, 1),
        "propolis": propolis,
        "propolis_pct": round(100 * propolis / total, 1),
        "total_attempts": total_attempts,
        "att_per_solve": round(total_attempts / solved_count, 1),
        "total_energy": round(total_energy, 2),
        "energy_per_honey": round(total_energy / solved_count, 4),
        "cost_per_honey": round(total_energy * 0.0001 / solved_count, 4),
        "wall_time": round(total_wall, 2),
    }


def print_comparison(aggregates: list[dict], task_count: int) -> None:
    """Print the benchmark comparison table."""
    print()
    print("=" * 88)
    print(f"  SwarmBench v0.1 Results (Tier 1, {task_count} tasks)")
    print("=" * 88)
    print()

    # Header
    header = (
        f"{'System':<16s} "
        f"{'Honey%':>7s} "
        f"{'Jelly%':>7s} "
        f"{'Propolis%':>10s} "
        f"{'Att/Solve':>10s} "
        f"{'Cost/Honey':>11s} "
        f"{'Energy/Honey':>13s}"
    )
    print(header)
    print("-" * 88)

    for agg in aggregates:
        line = (
            f"{agg['system']:<16s} "
            f"{agg['honey_pct']:>6.0f}% "
            f"{agg['jelly_pct']:>6.0f}% "
            f"{agg['propolis_pct']:>9.0f}% "
            f"{agg['att_per_solve']:>10.1f} "
            f"${agg['cost_per_honey']:>10.4f} "
            f"{agg['energy_per_honey']:>10.4f} eu"
        )
        print(line)

    print()
    print("=" * 88)

    # Legend
    print()
    print("  Honey  = score >= 0.95 (solved)")
    print("  Jelly  = score 0.30-0.95 (partial)")
    print("  Propolis = score < 0.30 (failed)")
    print("  Att/Solve = total attempts / honey count")
    print("  Cost/Honey = energy * $0.0001 / honey count (abstract)")
    print("  Energy/Honey = total energy units / honey count")
    print()


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_benchmark(
    api_url: str,
    tasks_per_tier: int,
    api_key: str = "",
    base_seed: int = 42,
    swarm_rounds: int = 20,
    baseline_b_max_attempts: int = 75,
) -> dict:
    """Run the full benchmark: generate tasks, run all 3 systems, compare."""

    log.info("=" * 60)
    log.info("SwarmBench v0.1 — Benchmark Orchestrator")
    log.info("  API:        %s", api_url)
    log.info("  Tasks:      %d per tier", tasks_per_tier)
    log.info("  Base seed:  %d", base_seed)
    log.info("=" * 60)

    # ---------------------------------------------------------------
    # Step 1: Generate task set
    # ---------------------------------------------------------------
    log.info("Step 1: Generating %d Tier 1 tasks...", tasks_per_tier)

    try:
        from swarmchain.tasks.arc_generator import ARCTaskGenerator
    except ImportError:
        log.error("Cannot import ARCTaskGenerator — is backend on PYTHONPATH?")
        sys.exit(1)

    generator = ARCTaskGenerator()
    tasks = generator.generate_catalog(count=tasks_per_tier, base_seed=base_seed)
    log.info("  Generated %d tasks", len(tasks))

    # Verify API is reachable
    try:
        resp = httpx.get(f"{api_url.rstrip('/')}/health", timeout=10.0)
        if resp.status_code != 200:
            log.error("API health check failed: %s", resp.text[:200])
            sys.exit(1)
        log.info("  API health: OK")
    except httpx.ConnectError:
        log.error("Cannot reach API at %s", api_url)
        sys.exit(1)

    all_results: dict[str, list] = {}
    all_aggregates: list[dict] = []

    # ---------------------------------------------------------------
    # Step 2: Run Baseline A
    # ---------------------------------------------------------------
    log.info("")
    log.info("Step 2: Running Baseline A (deterministic single-engine)...")
    t0 = time.monotonic()

    baseline_a = BaselineA(api_url=api_url, api_key=api_key)
    with httpx.Client() as client:
        results_a = baseline_a.run(tasks, client)

    elapsed_a = time.monotonic() - t0
    results_a_dicts = [r.to_dict() for r in results_a]
    all_results["baseline_a"] = results_a_dicts
    agg_a = compute_aggregates(results_a_dicts, "Baseline A")
    all_aggregates.append(agg_a)
    log.info("  Baseline A complete: %d/%d honey in %.1fs", agg_a["honey"], len(results_a), elapsed_a)

    # ---------------------------------------------------------------
    # Step 3: Run Baseline B
    # ---------------------------------------------------------------
    log.info("")
    log.info("Step 3: Running Baseline B (centralized refinement)...")
    t0 = time.monotonic()

    baseline_b = BaselineB(
        api_url=api_url,
        api_key=api_key,
        max_attempts=baseline_b_max_attempts,
    )
    with httpx.Client() as client:
        results_b = baseline_b.run(tasks, client)

    elapsed_b = time.monotonic() - t0
    results_b_dicts = [r.to_dict() for r in results_b]
    all_results["baseline_b"] = results_b_dicts
    agg_b = compute_aggregates(results_b_dicts, "Baseline B")
    all_aggregates.append(agg_b)
    log.info("  Baseline B complete: %d/%d honey in %.1fs", agg_b["honey"], len(results_b), elapsed_b)

    # ---------------------------------------------------------------
    # Step 4: Run SwarmChain simulator
    # ---------------------------------------------------------------
    log.info("")
    log.info("Step 4: Running SwarmChain (distributed swarm, %d rounds)...", swarm_rounds)
    t0 = time.monotonic()

    results_swarm = run_swarmchain_simulator(
        api_url=api_url,
        tasks=tasks,
        api_key=api_key,
        rounds=swarm_rounds,
    )

    elapsed_swarm = time.monotonic() - t0
    all_results["swarmchain"] = results_swarm
    agg_swarm = compute_aggregates(results_swarm, "SwarmChain")
    all_aggregates.append(agg_swarm)
    log.info(
        "  SwarmChain complete: %d/%d honey in %.1fs",
        agg_swarm["honey"], len(results_swarm), elapsed_swarm,
    )

    # ---------------------------------------------------------------
    # Step 5: Comparison table
    # ---------------------------------------------------------------
    print_comparison(all_aggregates, tasks_per_tier)

    # ---------------------------------------------------------------
    # Build full results payload
    # ---------------------------------------------------------------
    benchmark_results = {
        "benchmark": "SwarmBench v0.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "api_url": api_url,
            "tasks_per_tier": tasks_per_tier,
            "base_seed": base_seed,
            "swarm_rounds": swarm_rounds,
            "baseline_b_max_attempts": baseline_b_max_attempts,
        },
        "aggregates": all_aggregates,
        "per_task": all_results,
        "timing": {
            "baseline_a_sec": round(elapsed_a, 2),
            "baseline_b_sec": round(elapsed_b, 2),
            "swarmchain_sec": round(elapsed_swarm, 2),
        },
    }

    return benchmark_results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SwarmBench — run all 3 systems on the same task set, compare results",
    )
    parser.add_argument(
        "--api-url", default="http://localhost:8000",
        help="SwarmChain API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--tasks-per-tier", type=int, default=50,
        help="Number of tasks per tier (default: 50)",
    )
    parser.add_argument(
        "--base-seed", type=int, default=42,
        help="Base seed for task generation (default: 42)",
    )
    parser.add_argument(
        "--api-key", default="",
        help="API key for authenticated endpoints",
    )
    parser.add_argument(
        "--swarm-rounds", type=int, default=20,
        help="Number of simulation rounds for SwarmChain (default: 20)",
    )
    parser.add_argument(
        "--baseline-b-max-attempts", type=int, default=75,
        help="Max attempts per task for Baseline B (default: 75)",
    )
    parser.add_argument(
        "--output", default="benchmark_results.json",
        help="Output JSON file for full results (default: benchmark_results.json)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    results = run_benchmark(
        api_url=args.api_url,
        tasks_per_tier=args.tasks_per_tier,
        api_key=args.api_key,
        base_seed=args.base_seed,
        swarm_rounds=args.swarm_rounds,
        baseline_b_max_attempts=args.baseline_b_max_attempts,
    )

    # Save results
    output_path = args.output
    if not os.path.isabs(output_path):
        output_path = os.path.join(os.path.dirname(__file__), output_path)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    log.info("Full results saved to %s", output_path)
    log.info("Benchmark complete.")


if __name__ == "__main__":
    main()
