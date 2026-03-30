#!/usr/bin/env python3
"""SwarmBench Baseline B — Centralized Refinement Loop.

The smart centralized control. Single-process with iterative refinement.
  - First pass:  try all 25 transforms, rank by score
  - Second pass: take top 5, apply random perturbation to each, re-score
  - Third pass:  take top 3, apply perturbation again
  - Up to max_attempts budget

No distribution, no lineage tracking, no economic incentives.
Uses the SwarmChain API for scoring to ensure identical evaluation.

Usage:
    python baseline_b.py --api-url http://localhost:8080/api --tasks 50 --api-key <key>
    python baseline_b.py --api-url http://localhost:8000 --tasks 50 --max-attempts 50
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
from typing import Callable

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [baseline-b] %(message)s",
)
log = logging.getLogger("baseline-b")

# ---------------------------------------------------------------------------
# 25 Transforms — EXACT duplicates from arc_generator.py
# ---------------------------------------------------------------------------
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

assert len(TRANSFORM_FN) == 25


# ---------------------------------------------------------------------------
# Perturbation — the refinement mechanism
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


def perturb_grid(
    grid: Grid,
    input_grid: Grid,
    rng: random.Random,
    num_mutations: int = 3,
) -> Grid:
    """Apply random perturbations to a grid.

    Mutate 1 to num_mutations cells by replacing them with colors
    from the input grid palette. This is the centralized equivalent
    of the queen's refinement strategy.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    if rows == 0 or cols == 0:
        return grid

    result = [list(row) for row in grid]

    # Build color palette from input
    colors = set()
    for row in input_grid:
        colors.update(row)
    colors.update({0, 1, 2, 3})
    palette = list(colors)

    actual_mutations = rng.randint(1, min(num_mutations, rows * cols))
    for _ in range(actual_mutations):
        r = rng.randint(0, rows - 1)
        c = rng.randint(0, cols - 1)
        result[r][c] = rng.choice(palette)

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
    outcome: str
    best_score: float
    attempts: int
    wall_time_sec: float
    cpu_time_sec: float
    total_energy: float
    best_strategy: str
    refinement_passes: int = 0

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
            "refinement_passes": self.refinement_passes,
        }


# ---------------------------------------------------------------------------
# Baseline B solver
# ---------------------------------------------------------------------------

class BaselineB:
    """Centralized refinement loop.

    Strategy:
      Pass 1: try all 25 transforms, rank by score
      Pass 2: take top 5 candidates, perturb each 3 times, re-score
      Pass 3: take top 3 from pass 2, perturb each 3 times
      Continue until max_attempts budget or score >= 0.95

    This represents the best a centralized system can do with
    the same transform library — systematic exploration + iterative
    refinement, but no distribution.
    """

    ENERGY_PER_ATTEMPT = 0.5
    NODE_ID = "baseline-b-solver"
    NODE_TYPE = "baseline-b"

    # Refinement parameters
    PASS_2_TOP_K = 5
    PASS_2_PERTURBATIONS = 3
    PASS_3_TOP_K = 3
    PASS_3_PERTURBATIONS = 3
    EXTRA_PASSES = 2       # additional refinement passes after pass 3
    EXTRA_TOP_K = 3
    EXTRA_PERTURBATIONS = 3

    def __init__(self, api_url: str, api_key: str = "", max_attempts: int = 75):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.max_attempts = max_attempts
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
                return None
            return resp.json()
        except httpx.HTTPError:
            return None

    def register(self, client: httpx.Client) -> bool:
        """Register the baseline solver as a node."""
        result = self._post(client, "/nodes/register", {
            "node_id": self.NODE_ID,
            "node_type": self.NODE_TYPE,
            "hardware_class": "cpu-baseline",
            "metadata": {
                "system": "baseline_b",
                "strategy": "centralized_refinement",
                "max_attempts": self.max_attempts,
            },
        })
        return result is not None

    def _submit_attempt(
        self,
        client: httpx.Client,
        block_id: str,
        grid: Grid,
        method: str,
        strategy: str,
    ) -> tuple[float, bool]:
        """Submit a grid attempt and return (score, is_solved)."""
        result = self._post(client, "/attempts", {
            "node_id": self.NODE_ID,
            "block_id": block_id,
            "parent_attempt_id": None,
            "method": method,
            "strategy_family": strategy,
            "output_json": {"grid": grid},
            "energy_cost": self.ENERGY_PER_ATTEMPT,
            "latency_ms": 1,
        })
        if result:
            score = result.get("score", 0.0)
            return score, score >= HONEY_THRESHOLD
        return 0.0, False

    def solve_task(
        self, client: httpx.Client, task: dict, block_id: str
    ) -> TaskResult:
        """Run the centralized refinement loop on a single task."""
        input_grid = task.get("input_grid", [])
        expected = task.get("expected_output", [])
        exp_rows = len(expected)
        exp_cols = len(expected[0]) if exp_rows else 0
        task_id = task.get("task_id", "unknown")

        wall_start = time.monotonic()
        cpu_start = time.process_time()

        task_seed = hash(task_id) & 0xFFFFFFFF
        rng = random.Random(task_seed)

        attempt_count = 0
        total_energy = 0.0
        best_score = 0.0
        best_strategy = ""
        solved = False
        refinement_passes = 0

        # candidates: list of (score, grid, strategy_name)
        candidates: list[tuple[float, Grid, str]] = []

        # ---------------------------------------------------------------
        # Pass 1: Try all 25 transforms
        # ---------------------------------------------------------------
        for transform_name in TRANSFORM_NAMES:
            if attempt_count >= self.max_attempts:
                break

            transform_fn = TRANSFORM_FN[transform_name]

            rows = len(input_grid)
            cols = len(input_grid[0]) if input_grid else 0
            if transform_name == "crop_1" and (rows < 3 or cols < 3):
                continue
            if transform_name == "max_pool_2x2" and (rows < 2 or cols < 2):
                continue

            try:
                output_grid = transform_fn(input_grid, rng)
            except Exception:
                continue

            if exp_rows > 0 and exp_cols > 0:
                output_grid = _clamp_grid(output_grid, exp_rows, exp_cols)

            score, is_solved = self._submit_attempt(
                client, block_id, output_grid,
                f"baseline-b-p1-{transform_name}", transform_name,
            )
            attempt_count += 1
            total_energy += self.ENERGY_PER_ATTEMPT

            candidates.append((score, output_grid, transform_name))

            if score > best_score:
                best_score = score
                best_strategy = transform_name

            if is_solved:
                solved = True
                log.info(
                    "  SOLVED %s in pass 1 with %s (score=%.3f, attempt %d)",
                    task_id, transform_name, score, attempt_count,
                )
                break

        if solved:
            wall_time = time.monotonic() - wall_start
            cpu_time = time.process_time() - cpu_start
            return TaskResult(
                task_id=task_id, block_id=block_id,
                outcome="honey", best_score=best_score,
                attempts=attempt_count, wall_time_sec=wall_time,
                cpu_time_sec=cpu_time, total_energy=total_energy,
                best_strategy=best_strategy, refinement_passes=0,
            )

        # ---------------------------------------------------------------
        # Pass 2: Refine top 5 with perturbations
        # ---------------------------------------------------------------
        candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = candidates[:self.PASS_2_TOP_K]
        new_candidates: list[tuple[float, Grid, str]] = []

        for _, parent_grid, parent_strategy in top_candidates:
            for p in range(self.PASS_2_PERTURBATIONS):
                if attempt_count >= self.max_attempts:
                    break

                perturbed = perturb_grid(parent_grid, input_grid, rng)
                if exp_rows > 0 and exp_cols > 0:
                    perturbed = _clamp_grid(perturbed, exp_rows, exp_cols)

                strategy_name = f"{parent_strategy}+perturb"
                score, is_solved = self._submit_attempt(
                    client, block_id, perturbed,
                    f"baseline-b-p2-{parent_strategy}-{p}", strategy_name,
                )
                attempt_count += 1
                total_energy += self.ENERGY_PER_ATTEMPT

                new_candidates.append((score, perturbed, strategy_name))

                if score > best_score:
                    best_score = score
                    best_strategy = strategy_name

                if is_solved:
                    solved = True
                    break

            if solved:
                break

        refinement_passes = 1

        if solved:
            wall_time = time.monotonic() - wall_start
            cpu_time = time.process_time() - cpu_start
            return TaskResult(
                task_id=task_id, block_id=block_id,
                outcome="honey", best_score=best_score,
                attempts=attempt_count, wall_time_sec=wall_time,
                cpu_time_sec=cpu_time, total_energy=total_energy,
                best_strategy=best_strategy,
                refinement_passes=refinement_passes,
            )

        # ---------------------------------------------------------------
        # Pass 3: Refine top 3 from pass 2
        # ---------------------------------------------------------------
        all_candidates = candidates + new_candidates
        all_candidates.sort(key=lambda x: x[0], reverse=True)
        top_3 = all_candidates[:self.PASS_3_TOP_K]
        newer_candidates: list[tuple[float, Grid, str]] = []

        for _, parent_grid, parent_strategy in top_3:
            for p in range(self.PASS_3_PERTURBATIONS):
                if attempt_count >= self.max_attempts:
                    break

                perturbed = perturb_grid(parent_grid, input_grid, rng)
                if exp_rows > 0 and exp_cols > 0:
                    perturbed = _clamp_grid(perturbed, exp_rows, exp_cols)

                strategy_name = f"{parent_strategy}+refine"
                score, is_solved = self._submit_attempt(
                    client, block_id, perturbed,
                    f"baseline-b-p3-{p}", strategy_name,
                )
                attempt_count += 1
                total_energy += self.ENERGY_PER_ATTEMPT

                newer_candidates.append((score, perturbed, strategy_name))

                if score > best_score:
                    best_score = score
                    best_strategy = strategy_name

                if is_solved:
                    solved = True
                    break

            if solved:
                break

        refinement_passes = 2

        # ---------------------------------------------------------------
        # Extra passes: keep refining until budget exhausted
        # ---------------------------------------------------------------
        if not solved:
            all_cands = candidates + new_candidates + newer_candidates
            all_cands.sort(key=lambda x: x[0], reverse=True)

            for extra_pass in range(self.EXTRA_PASSES):
                if solved or attempt_count >= self.max_attempts:
                    break

                top_k = all_cands[:self.EXTRA_TOP_K]
                extra_results: list[tuple[float, Grid, str]] = []

                for _, parent_grid, parent_strategy in top_k:
                    for p in range(self.EXTRA_PERTURBATIONS):
                        if attempt_count >= self.max_attempts:
                            break

                        perturbed = perturb_grid(parent_grid, input_grid, rng, num_mutations=2)
                        if exp_rows > 0 and exp_cols > 0:
                            perturbed = _clamp_grid(perturbed, exp_rows, exp_cols)

                        strategy_name = f"{parent_strategy}+extra{extra_pass}"
                        score, is_solved = self._submit_attempt(
                            client, block_id, perturbed,
                            f"baseline-b-p{4 + extra_pass}-{p}", strategy_name,
                        )
                        attempt_count += 1
                        total_energy += self.ENERGY_PER_ATTEMPT

                        extra_results.append((score, perturbed, strategy_name))

                        if score > best_score:
                            best_score = score
                            best_strategy = strategy_name

                        if is_solved:
                            solved = True
                            break

                    if solved:
                        break

                all_cands = sorted(
                    all_cands + extra_results, key=lambda x: x[0], reverse=True
                )
                refinement_passes += 1

        wall_time = time.monotonic() - wall_start
        cpu_time = time.process_time() - cpu_start

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
            refinement_passes=refinement_passes,
        )

    def run(
        self, tasks: list[dict], client: httpx.Client
    ) -> list[TaskResult]:
        """Run Baseline B on all tasks."""
        log.info("Baseline B: %d tasks, max_attempts=%d per task", len(tasks), self.max_attempts)

        if not self.register(client):
            log.error("Failed to register baseline-b node")
            return []

        results: list[TaskResult] = []

        for i, task in enumerate(tasks):
            task_id = task.get("task_id", f"task-{i}")
            log.info("[%d/%d] Opening block for %s", i + 1, len(tasks), task_id)

            block_resp = self._post(client, "/blocks/open", {
                "task_id": task_id,
                "domain": "arc",
                "reward_pool": 100.0,
                "max_attempts": 500,
                "time_limit_sec": 3600,
                "task_payload": task,
                "metadata": {"benchmark": "baseline_b"},
            })

            if not block_resp:
                log.error("Failed to open block for %s", task_id)
                continue

            block_id = block_resp["block_id"]

            result = self.solve_task(client, task, block_id)
            results.append(result)

            self._post(client, f"/blocks/{block_id}/finalize", {
                "force": True,
                "reason": "baseline-b-complete",
            })

            log.info(
                "  Result: %s score=%.3f attempts=%d passes=%d strategy=%s wall=%.2fs",
                result.outcome, result.best_score, result.attempts,
                result.refinement_passes, result.best_strategy, result.wall_time_sec,
            )

        self.results = results
        return results


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(results: list[TaskResult]) -> None:
    """Print a summary table of Baseline B results."""
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
    avg_refinement = sum(r.refinement_passes for r in results) / max(total, 1)

    total_energy = sum(r.total_energy for r in results)
    energy_per_honey = total_energy / max(honey, 1)

    total_wall = sum(r.wall_time_sec for r in results)
    total_cpu = sum(r.cpu_time_sec for r in results)

    print()
    print("=" * 56)
    print("  Baseline B: Centralized Refinement Loop")
    print("=" * 56)
    print(f"  Tasks:           {total}")
    print(f"  Honey:           {honey} ({100 * honey / total:.0f}%)")
    print(f"  Jelly:           {jelly} ({100 * jelly / total:.0f}%)")
    print(f"  Propolis:        {propolis} ({100 * propolis / total:.0f}%)")
    print(f"  Total attempts:  {total_attempts}")
    print(f"  Att/solve:       {avg_attempts_per_solve:.1f}")
    print(f"  Avg refinements: {avg_refinement:.1f}")
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
        description="SwarmBench Baseline B — centralized refinement loop",
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
        "--max-attempts", type=int, default=75,
        help="Maximum attempts per task (default: 75)",
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

    baseline = BaselineB(
        api_url=args.api_url,
        api_key=args.api_key,
        max_attempts=args.max_attempts,
    )

    with httpx.Client() as client:
        results = baseline.run(tasks, client)

    print_summary(results)

    if args.output:
        output_data = {
            "system": "baseline_b",
            "tasks": args.tasks,
            "base_seed": args.base_seed,
            "max_attempts": args.max_attempts,
            "results": [r.to_dict() for r in results],
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        log.info("Results saved to %s", args.output)


if __name__ == "__main__":
    main()
