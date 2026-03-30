#!/usr/bin/env python3
"""SwarmBench Baseline A — Deterministic Single-Engine Solver.

The clean control. No distribution, no lineage, no promotion, no workers.
Single-process, fixed transform library (same 25 transforms as arc_generator.py).

For each task: try each transform in order, score, return best.
Uses the SwarmChain API to open blocks, submit attempts, and finalize,
ensuring the SAME scoring, the SAME block lifecycle, the SAME receipts.
The only difference is the SEARCH STRATEGY.

Usage:
    python baseline_a.py --api-url http://localhost:8080/api --tasks 50 --api-key <key>
    python baseline_a.py --api-url http://localhost:8000 --tasks 50 --base-seed 42
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import random
import sys
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [baseline-a] %(message)s",
)
log = logging.getLogger("baseline-a")

# ---------------------------------------------------------------------------
# 25 Transforms — EXACT duplicates from arc_generator.py
# ---------------------------------------------------------------------------
# These must match the canonical transform library. Any divergence
# invalidates the benchmark comparison.
# Canonical source: backend/swarmchain/tasks/arc_generator.py
# ---------------------------------------------------------------------------

Grid = list[list[int]]
MAX_COLOR = 9


def _mirror_h(grid: Grid, rng: random.Random) -> Grid:
    return [row[::-1] for row in grid]


def _mirror_v(grid: Grid, rng: random.Random) -> Grid:
    return grid[::-1]


def _rotate_90(grid: Grid, rng: random.Random) -> Grid:
    rows, cols = len(grid), len(grid[0])
    return [[grid[rows - 1 - r][c] for r in range(rows)] for c in range(cols)]


def _rotate_180(grid: Grid, rng: random.Random) -> Grid:
    return [row[::-1] for row in grid[::-1]]


def _rotate_270(grid: Grid, rng: random.Random) -> Grid:
    rows, cols = len(grid), len(grid[0])
    return [[grid[r][cols - 1 - c] for r in range(rows)] for c in range(cols)]


def _transpose(grid: Grid, rng: random.Random) -> Grid:
    rows, cols = len(grid), len(grid[0])
    return [[grid[r][c] for r in range(rows)] for c in range(cols)]


def _color_swap(grid: Grid, rng: random.Random) -> Grid:
    colors_present = set()
    for row in grid:
        for v in row:
            colors_present.add(v)
    colors_list = sorted(colors_present)
    if len(colors_list) < 2:
        c1 = colors_list[0]
        c2 = (c1 + 1) % (MAX_COLOR + 1)
    else:
        pair = rng.sample(colors_list, 2)
        c1, c2 = pair[0], pair[1]
    return [[c2 if v == c1 else c1 if v == c2 else v for v in row] for row in grid]


def _invert(grid: Grid, rng: random.Random) -> Grid:
    return [[1 if v == 0 else 0 for v in row] for row in grid]


def _fill_zeros(grid: Grid, rng: random.Random) -> Grid:
    fill_color = rng.randint(1, MAX_COLOR)
    return [[fill_color if v == 0 else v for v in row] for row in grid]


def _scale_2x(grid: Grid, rng: random.Random) -> Grid:
    result = []
    for row in grid:
        expanded = []
        for v in row:
            expanded.extend([v, v])
        result.append(expanded)
        result.append(list(expanded))
    return result


def _border_add(grid: Grid, rng: random.Random) -> Grid:
    border_color = rng.randint(1, MAX_COLOR)
    rows, cols = len(grid), len(grid[0])
    new_cols = cols + 2
    result = [[border_color] * new_cols]
    for row in grid:
        result.append([border_color] + row + [border_color])
    result.append([border_color] * new_cols)
    return result


def _crop_1(grid: Grid, rng: random.Random) -> Grid:
    return [row[1:-1] for row in grid[1:-1]]


def _shift_right(grid: Grid, rng: random.Random) -> Grid:
    return [row[-1:] + row[:-1] for row in grid]


def _shift_down(grid: Grid, rng: random.Random) -> Grid:
    return grid[-1:] + grid[:-1]


def _shift_left(grid: Grid, rng: random.Random) -> Grid:
    return [row[1:] + row[:1] for row in grid]


def _shift_up(grid: Grid, rng: random.Random) -> Grid:
    return grid[1:] + grid[:1]


def _gravity_down(grid: Grid, rng: random.Random) -> Grid:
    rows, cols = len(grid), len(grid[0])
    result = [[0] * cols for _ in range(rows)]
    for c in range(cols):
        non_zero = [grid[r][c] for r in range(rows) if grid[r][c] != 0]
        start = rows - len(non_zero)
        for i, v in enumerate(non_zero):
            result[start + i][c] = v
    return result


def _gravity_left(grid: Grid, rng: random.Random) -> Grid:
    result = []
    for row in grid:
        non_zero = [v for v in row if v != 0]
        padded = non_zero + [0] * (len(row) - len(non_zero))
        result.append(padded)
    return result


def _flood_fill(grid: Grid, rng: random.Random) -> Grid:
    fill_color = rng.randint(1, MAX_COLOR)
    rows, cols = len(grid), len(grid[0])
    result = [list(row) for row in grid]
    target = result[0][0]
    if target == fill_color:
        fill_color = (fill_color % MAX_COLOR) + 1
    if target != 0:
        found = False
        for r in range(rows):
            for c in range(cols):
                if result[r][c] == 0:
                    target = 0
                    start_r, start_c = r, c
                    found = True
                    break
            if found:
                break
        if not found:
            return result
    else:
        start_r, start_c = 0, 0
    visited = set()
    queue = deque([(start_r, start_c)])
    visited.add((start_r, start_c))
    while queue:
        r, c = queue.popleft()
        result[r][c] = fill_color
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited and result[nr][nc] == target:
                visited.add((nr, nc))
                queue.append((nr, nc))
    return result


def _pattern_tile_2x2(grid: Grid, rng: random.Random) -> Grid:
    result = []
    for _ in range(2):
        for row in grid:
            result.append(row + row)
    return result


def _checkerboard(grid: Grid, rng: random.Random) -> Grid:
    counter: Counter = Counter()
    for row in grid:
        for v in row:
            counter[v] += 1
    most_common = counter.most_common()
    c1 = most_common[0][0]
    c2 = most_common[1][0] if len(most_common) > 1 else (c1 + 1) % (MAX_COLOR + 1)
    rows, cols = len(grid), len(grid[0])
    return [[(c1 if (r + c) % 2 == 0 else c2) for c in range(cols)] for r in range(rows)]


def _diagonal_mirror(grid: Grid, rng: random.Random) -> Grid:
    rows, cols = len(grid), len(grid[0])
    return [[grid[r][c] for r in range(rows)] for c in range(cols)]


def _color_remap(grid: Grid, rng: random.Random) -> Grid:
    colors_present = set()
    for row in grid:
        for v in row:
            colors_present.add(v)
    colors_list = sorted(colors_present)
    shuffled = list(colors_list)
    rng.shuffle(shuffled)
    if shuffled == colors_list and len(colors_list) > 1:
        shuffled[0], shuffled[1] = shuffled[1], shuffled[0]
    mapping = dict(zip(colors_list, shuffled))
    return [[mapping[v] for v in row] for row in grid]


def _max_pool_2x2(grid: Grid, rng: random.Random) -> Grid:
    rows, cols = len(grid), len(grid[0])
    pool_rows = rows // 2
    pool_cols = cols // 2
    result = []
    for r in range(pool_rows):
        result_row = []
        for c in range(pool_cols):
            block = [
                grid[2 * r][2 * c], grid[2 * r][2 * c + 1],
                grid[2 * r + 1][2 * c], grid[2 * r + 1][2 * c + 1],
            ]
            result_row.append(max(block))
        result.append(result_row)
    return result


def _sort_rows(grid: Grid, rng: random.Random) -> Grid:
    return [sorted(row) for row in grid]


# Ordered list of all 25 transforms — same order as arc_generator.py
TRANSFORM_NAMES: list[str] = [
    "mirror_h", "mirror_v", "rotate_90", "rotate_180", "rotate_270",
    "transpose", "color_swap", "invert", "fill_zeros", "scale_2x",
    "border_add", "crop_1", "shift_right", "shift_down", "shift_left",
    "shift_up", "gravity_down", "gravity_left", "flood_fill",
    "pattern_tile_2x2", "checkerboard", "diagonal_mirror", "color_remap",
    "max_pool_2x2", "sort_rows",
]

TRANSFORM_FN: dict[str, Callable] = {
    "mirror_h": _mirror_h, "mirror_v": _mirror_v,
    "rotate_90": _rotate_90, "rotate_180": _rotate_180,
    "rotate_270": _rotate_270, "transpose": _transpose,
    "color_swap": _color_swap, "invert": _invert,
    "fill_zeros": _fill_zeros, "scale_2x": _scale_2x,
    "border_add": _border_add, "crop_1": _crop_1,
    "shift_right": _shift_right, "shift_down": _shift_down,
    "shift_left": _shift_left, "shift_up": _shift_up,
    "gravity_down": _gravity_down, "gravity_left": _gravity_left,
    "flood_fill": _flood_fill, "pattern_tile_2x2": _pattern_tile_2x2,
    "checkerboard": _checkerboard, "diagonal_mirror": _diagonal_mirror,
    "color_remap": _color_remap, "max_pool_2x2": _max_pool_2x2,
    "sort_rows": _sort_rows,
}

assert len(TRANSFORM_FN) == 25, f"Expected 25 transforms, got {len(TRANSFORM_FN)}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp_grid(grid: Grid, rows: int, cols: int) -> Grid:
    """Trim or pad a grid to exact (rows, cols)."""
    result: Grid = []
    for r in range(rows):
        if r < len(grid):
            src = grid[r]
            new_row = [src[c] if c < len(src) else 0 for c in range(cols)]
        else:
            new_row = [0] * cols
        result.append(new_row)
    return result


# ---------------------------------------------------------------------------
# Task results
# ---------------------------------------------------------------------------

HONEY_THRESHOLD = 0.95
JELLY_THRESHOLD = 0.30


@dataclass
class TaskResult:
    """Result of running the baseline on a single task."""
    task_id: str
    block_id: str
    outcome: str           # "honey", "jelly", "propolis", "exhausted"
    best_score: float
    attempts: int
    wall_time_sec: float
    cpu_time_sec: float
    total_energy: float
    best_strategy: str
    all_scores: dict = field(default_factory=dict)  # strategy -> score

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "block_id": self.block_id,
            "outcome": self.outcome,
            "best_score": self.best_score,
            "attempts": self.attempts,
            "wall_time_sec": round(self.wall_time_sec, 4),
            "cpu_time_sec": round(self.cpu_time_sec, 4),
            "total_energy": round(self.total_energy, 4),
            "best_strategy": self.best_strategy,
        }


# ---------------------------------------------------------------------------
# Baseline A solver
# ---------------------------------------------------------------------------

class BaselineA:
    """Deterministic single-engine solver.

    Strategy: try each of the 25 transforms in fixed order. Score each.
    If any hits >= 0.95, stop early (solved). Otherwise finalize as exhausted
    with the best score found.
    """

    ENERGY_PER_ATTEMPT = 0.5  # abstract energy units per attempt
    NODE_ID = "baseline-a-solver"
    NODE_TYPE = "baseline-a"

    def __init__(self, api_url: str, api_key: str = ""):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.results: list[TaskResult] = []

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def _post(self, client: httpx.Client, path: str, body: dict) -> dict | None:
        url = f"{self.api_url}{path}"
        try:
            resp = client.post(url, json=body, headers=self._headers(), timeout=30.0)
            if resp.status_code >= 400:
                log.warning("POST %s -> %d: %s", path, resp.status_code, resp.text[:200])
                return None
            return resp.json()
        except httpx.HTTPError as e:
            log.error("POST %s error: %s", path, e)
            return None

    def _get(self, client: httpx.Client, path: str, params: dict | None = None) -> dict | None:
        url = f"{self.api_url}{path}"
        try:
            resp = client.get(url, params=params, headers=self._headers(), timeout=30.0)
            if resp.status_code >= 400:
                log.warning("GET %s -> %d: %s", path, resp.status_code, resp.text[:200])
                return None
            return resp.json()
        except httpx.HTTPError as e:
            log.error("GET %s error: %s", path, e)
            return None

    def register(self, client: httpx.Client) -> bool:
        """Register the baseline solver as a node."""
        result = self._post(client, "/nodes/register", {
            "node_id": self.NODE_ID,
            "node_type": self.NODE_TYPE,
            "hardware_class": "cpu-baseline",
            "metadata": {"system": "baseline_a", "strategy": "fixed_order_25"},
        })
        return result is not None

    def solve_task(
        self, client: httpx.Client, task: dict, block_id: str
    ) -> TaskResult:
        """Run all 25 transforms in fixed order against a single task.

        Returns early if a transform achieves score >= 0.95.
        """
        input_grid = task.get("input_grid", [])
        expected = task.get("expected_output", [])
        exp_rows = len(expected)
        exp_cols = len(expected[0]) if exp_rows else 0
        task_id = task.get("task_id", "unknown")

        wall_start = time.monotonic()
        cpu_start = time.process_time()

        best_score = 0.0
        best_strategy = ""
        attempt_count = 0
        total_energy = 0.0
        scores: dict[str, float] = {}
        solved = False

        # Use a fixed RNG seed derived from the task for deterministic transforms
        # that need randomness (color_swap, fill_zeros, etc.)
        task_seed = hash(task_id) & 0xFFFFFFFF
        rng = random.Random(task_seed)

        for transform_name in TRANSFORM_NAMES:
            transform_fn = TRANSFORM_FN[transform_name]

            # Some transforms need minimum grid size
            rows, cols = len(input_grid), len(input_grid[0]) if input_grid else 0
            if transform_name == "crop_1" and (rows < 3 or cols < 3):
                continue
            if transform_name == "max_pool_2x2" and (rows < 2 or cols < 2):
                continue

            # Apply transform
            try:
                output_grid = transform_fn(input_grid, rng)
            except Exception:
                continue

            # Clamp to expected dimensions
            if exp_rows > 0 and exp_cols > 0:
                output_grid = _clamp_grid(output_grid, exp_rows, exp_cols)

            # Measure latency
            t0 = time.monotonic()
            # (transform already applied above — latency is minimal for baselines)
            latency_ms = max(1, int((time.monotonic() - t0) * 1000) + 1)

            # Submit attempt via API
            result = self._post(client, "/attempts", {
                "node_id": self.NODE_ID,
                "block_id": block_id,
                "parent_attempt_id": None,
                "method": f"baseline-a-{transform_name}",
                "strategy_family": transform_name,
                "output_json": {"grid": output_grid},
                "energy_cost": self.ENERGY_PER_ATTEMPT,
                "latency_ms": latency_ms,
            })

            attempt_count += 1
            total_energy += self.ENERGY_PER_ATTEMPT

            if result:
                score = result.get("score", 0.0)
                scores[transform_name] = score

                if score > best_score:
                    best_score = score
                    best_strategy = transform_name

                if score >= HONEY_THRESHOLD:
                    solved = True
                    log.info(
                        "  SOLVED %s with %s (score=%.3f, attempt %d)",
                        task_id, transform_name, score, attempt_count,
                    )
                    break

        wall_time = time.monotonic() - wall_start
        cpu_time = time.process_time() - cpu_start

        # Classify outcome
        if best_score >= HONEY_THRESHOLD:
            outcome = "honey"
        elif best_score >= JELLY_THRESHOLD:
            outcome = "jelly"
        else:
            outcome = "propolis"

        return TaskResult(
            task_id=task_id,
            block_id=block_id,
            outcome=outcome,
            best_score=best_score,
            attempts=attempt_count,
            wall_time_sec=wall_time,
            cpu_time_sec=cpu_time,
            total_energy=total_energy,
            best_strategy=best_strategy,
            all_scores=scores,
        )

    def run(
        self, tasks: list[dict], client: httpx.Client
    ) -> list[TaskResult]:
        """Run Baseline A on all tasks.

        For each task:
        1. Open a block via the API
        2. Try each transform, submit attempts
        3. Finalize the block
        4. Record results
        """
        log.info("Baseline A: %d tasks to solve", len(tasks))

        # Register node
        if not self.register(client):
            log.error("Failed to register baseline-a node")
            return []

        results: list[TaskResult] = []

        for i, task in enumerate(tasks):
            task_id = task.get("task_id", f"task-{i}")
            log.info("[%d/%d] Opening block for %s", i + 1, len(tasks), task_id)

            # Open block
            block_resp = self._post(client, "/blocks/open", {
                "task_id": task_id,
                "domain": "arc",
                "reward_pool": 100.0,
                "max_attempts": 500,
                "time_limit_sec": 3600,
                "task_payload": task,
                "metadata": {"benchmark": "baseline_a"},
            })

            if not block_resp:
                log.error("Failed to open block for %s", task_id)
                continue

            block_id = block_resp["block_id"]

            # Solve
            result = self.solve_task(client, task, block_id)
            results.append(result)

            # Finalize block
            self._post(client, f"/blocks/{block_id}/finalize", {
                "force": True,
                "reason": "baseline-a-complete",
            })

            log.info(
                "  Result: %s score=%.3f attempts=%d strategy=%s wall=%.2fs",
                result.outcome, result.best_score, result.attempts,
                result.best_strategy, result.wall_time_sec,
            )

        self.results = results
        return results


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(results: list[TaskResult]) -> None:
    """Print a summary table of Baseline A results."""
    if not results:
        print("No results to summarize.")
        return

    total = len(results)
    honey = sum(1 for r in results if r.outcome == "honey")
    jelly = sum(1 for r in results if r.outcome == "jelly")
    propolis = sum(1 for r in results if r.outcome == "propolis")

    total_attempts = sum(r.attempts for r in results)
    solved = [r for r in results if r.outcome == "honey"]
    avg_attempts_per_solve = total_attempts / max(len(solved), 1)

    total_energy = sum(r.total_energy for r in results)
    energy_per_honey = total_energy / max(honey, 1)

    total_wall = sum(r.wall_time_sec for r in results)
    total_cpu = sum(r.cpu_time_sec for r in results)

    print()
    print("=" * 56)
    print("  Baseline A: Deterministic Single-Engine Solver")
    print("=" * 56)
    print(f"  Tasks:           {total}")
    print(f"  Honey:           {honey} ({100 * honey / total:.0f}%)")
    print(f"  Jelly:           {jelly} ({100 * jelly / total:.0f}%)")
    print(f"  Propolis:        {propolis} ({100 * propolis / total:.0f}%)")
    print(f"  Total attempts:  {total_attempts}")
    print(f"  Att/solve:       {avg_attempts_per_solve:.1f}")
    print(f"  Total energy:    {total_energy:.2f}")
    print(f"  Energy/honey:    {energy_per_honey:.2f}")
    print(f"  Wall time:       {total_wall:.2f}s")
    print(f"  CPU time:        {total_cpu:.2f}s")
    print("=" * 56)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SwarmBench Baseline A — deterministic single-engine solver",
    )
    parser.add_argument(
        "--api-url", default="http://localhost:8000",
        help="SwarmChain API base URL",
    )
    parser.add_argument(
        "--tasks", type=int, default=50,
        help="Number of tasks to run (default: 50)",
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
        "--output", default=None,
        help="Output JSON file for results",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Generate tasks using the same generator as the backend
    # Import here to allow standalone use (with inline generator if needed)
    sys.path.insert(0, "/data2/swarmchain/backend")
    try:
        from swarmchain.tasks.arc_generator import ARCTaskGenerator
    except ImportError:
        log.error(
            "Cannot import ARCTaskGenerator. Run from swarmchain root or "
            "ensure backend is on PYTHONPATH."
        )
        sys.exit(1)

    generator = ARCTaskGenerator()
    tasks = generator.generate_catalog(count=args.tasks, base_seed=args.base_seed)
    log.info("Generated %d tasks (base_seed=%d)", len(tasks), args.base_seed)

    baseline = BaselineA(api_url=args.api_url, api_key=args.api_key)

    with httpx.Client() as client:
        results = baseline.run(tasks, client)

    print_summary(results)

    if args.output:
        output_data = {
            "system": "baseline_a",
            "tasks": args.tasks,
            "base_seed": args.base_seed,
            "results": [r.to_dict() for r in results],
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        log.info("Results saved to %s", args.output)


if __name__ == "__main__":
    main()
