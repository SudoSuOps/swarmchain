#!/usr/bin/env python3
"""SwarmChain Edge Worker — standalone mining node for any machine.

Self-contained single-file worker that can be scp'd to Jetson, Whale, or any
edge device. Connects to a remote SwarmChain API and continuously mines open
blocks using its assigned strategy family.

All strategy functions are inlined for portability.

Usage:
    # On Jetson Orin:
    python worker.py --api-url http://192.168.0.50:8080 --node-id miner-jetson-001 --node-type jetmini

    # On Whale (RTX 3090):
    python worker.py --api-url http://192.168.0.50:8080 --node-id miner-whale-001 --node-type zima

    # Auto-generated node ID:
    python worker.py --api-url http://192.168.0.50:8080 --node-type edge

    # Queen with custom strategies:
    python worker.py --api-url http://192.168.0.50:8080 --node-type queen --strategies random_perturbation
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import logging
import os
import platform
import random
import signal
import sys
import time
from typing import Callable

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(message)s",
)
log = logging.getLogger("worker")


# ===========================================================================
# INLINE STRATEGIES — duplicated from strategies.py for single-file portability
# ===========================================================================

Grid = list[list[int]]
MAX_COLOR = 9


def _grid_dims(grid: Grid) -> tuple[int, int]:
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    return rows, cols


def _colors_in_grid(grid: Grid) -> set[int]:
    colors: set[int] = set()
    for row in grid:
        colors.update(row)
    return colors


def _make_empty(rows: int, cols: int, fill: int = 0) -> Grid:
    return [[fill] * cols for _ in range(rows)]


def _clamp_to_dims(grid: Grid, rows: int, cols: int) -> Grid:
    result: Grid = []
    for r in range(rows):
        if r < len(grid):
            src_row = grid[r]
            new_row = [src_row[c] if c < len(src_row) else 0 for c in range(cols)]
        else:
            new_row = [0] * cols
        result.append(new_row)
    return result


def random_grid(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Generate a completely random grid of the correct dimensions."""
    rows, cols = expected_dims
    colors = list(_colors_in_grid(input_grid) | {0, 1})
    return [[random.choice(colors) for _ in range(cols)] for _ in range(rows)]


def random_perturbation(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Take a parent grid and randomly mutate 1-3 cells."""
    base = copy.deepcopy(parent_grid if parent_grid is not None else input_grid)
    base = _clamp_to_dims(base, *expected_dims)
    rows, cols = expected_dims
    if rows == 0 or cols == 0:
        return base
    colors = list(_colors_in_grid(input_grid) | {0, 1, 2, 3})
    num_mutations = random.randint(1, min(3, rows * cols))
    for _ in range(num_mutations):
        r = random.randint(0, rows - 1)
        c = random.randint(0, cols - 1)
        base[r][c] = random.choice(colors)
    return base


def mirror_h(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Horizontal mirror -- reverse each row."""
    mirrored = [list(reversed(row)) for row in input_grid]
    return _clamp_to_dims(mirrored, *expected_dims)


def mirror_v(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Vertical mirror -- reverse the row order."""
    mirrored = list(reversed([list(row) for row in input_grid]))
    return _clamp_to_dims(mirrored, *expected_dims)


def rotate_90(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Rotate grid 90 degrees clockwise."""
    rows, cols = _grid_dims(input_grid)
    if rows == 0 or cols == 0:
        return _make_empty(*expected_dims)
    rotated = [
        [input_grid[rows - 1 - r][c] for r in range(rows)]
        for c in range(cols)
    ]
    return _clamp_to_dims(rotated, *expected_dims)


def rotate_180(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Rotate grid 180 degrees."""
    rotated = [list(reversed(row)) for row in reversed(input_grid)]
    return _clamp_to_dims(rotated, *expected_dims)


def rotate_270(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Rotate grid 270 degrees clockwise."""
    rows, cols = _grid_dims(input_grid)
    if rows == 0 or cols == 0:
        return _make_empty(*expected_dims)
    rotated = [
        [input_grid[r][cols - 1 - c] for r in range(rows)]
        for c in range(cols)
    ]
    return _clamp_to_dims(rotated, *expected_dims)


def color_swap(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Swap two non-zero colors in the grid."""
    freq: dict[int, int] = {}
    for row in input_grid:
        for val in row:
            if val != 0:
                freq[val] = freq.get(val, 0) + 1
    sorted_colors = sorted(freq.keys(), key=lambda c: freq[c], reverse=True)
    if len(sorted_colors) < 2:
        return _clamp_to_dims([list(row) for row in input_grid], *expected_dims)
    a, b = sorted_colors[0], sorted_colors[1]
    swapped = []
    for row in input_grid:
        new_row = []
        for val in row:
            if val == a:
                new_row.append(b)
            elif val == b:
                new_row.append(a)
            else:
                new_row.append(val)
        swapped.append(new_row)
    return _clamp_to_dims(swapped, *expected_dims)


def invert(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Invert: 0 becomes 1, non-zero becomes 0."""
    inverted = [
        [1 if val == 0 else 0 for val in row]
        for row in input_grid
    ]
    return _clamp_to_dims(inverted, *expected_dims)


def transpose(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Transpose the grid -- swap rows and columns."""
    rows, cols = _grid_dims(input_grid)
    if rows == 0 or cols == 0:
        return _make_empty(*expected_dims)
    transposed = [
        [input_grid[r][c] for r in range(rows)]
        for c in range(cols)
    ]
    return _clamp_to_dims(transposed, *expected_dims)


def copy_input(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Submit the input grid as-is."""
    return _clamp_to_dims([list(row) for row in input_grid], *expected_dims)


def scale_2x(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Scale the grid 2x -- each cell becomes a 2x2 block."""
    rows, cols = _grid_dims(input_grid)
    scaled: Grid = []
    for r in range(rows):
        row_a: list[int] = []
        row_b: list[int] = []
        for c in range(cols):
            val = input_grid[r][c]
            row_a.extend([val, val])
            row_b.extend([val, val])
        scaled.append(row_a)
        scaled.append(row_b)
    return _clamp_to_dims(scaled, *expected_dims)


def border_add(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Add a border of 3s around the grid."""
    rows, cols = _grid_dims(input_grid)
    new_rows = rows + 2
    new_cols = cols + 2
    bordered: Grid = []
    bordered.append([3] * new_cols)
    for r in range(rows):
        bordered.append([3] + list(input_grid[r]) + [3])
    bordered.append([3] * new_cols)
    return _clamp_to_dims(bordered, *expected_dims)


# Strategy registry
STRATEGY_REGISTRY: dict[str, Callable[..., Grid]] = {
    "random_grid": random_grid,
    "random_perturbation": random_perturbation,
    "mirror_h": mirror_h,
    "mirror_v": mirror_v,
    "rotate_90": rotate_90,
    "rotate_180": rotate_180,
    "rotate_270": rotate_270,
    "color_swap": color_swap,
    "transpose": transpose,
    "copy_input": copy_input,
    "scale_2x": scale_2x,
    "border_add": border_add,
    "invert": invert,
}

# Default strategies per node type
DEFAULT_STRATEGIES: dict[str, list[str]] = {
    "jetmini": ["random_grid", "random_perturbation"],
    "edge": ["random_grid", "random_perturbation"],
    "zima": ["mirror_h", "mirror_v", "color_swap", "invert"],
    "mid-gpu": ["rotate_90", "transpose", "scale_2x", "border_add"],
    "queen": ["random_perturbation"],
}

# Energy costs per node type
ENERGY_COSTS: dict[str, float] = {
    "jetmini": 0.2,
    "edge": 0.2,
    "zima": 0.5,
    "mid-gpu": 1.0,
    "queen": 2.0,
}


# ===========================================================================
# Worker
# ===========================================================================

class EdgeWorker:
    """Standalone edge mining worker."""

    def __init__(
        self,
        api_url: str,
        node_id: str,
        node_type: str,
        hardware_class: str,
        strategies: list[str],
        api_key: str | None,
    ):
        self.api_url = api_url.rstrip("/")
        self.node_id = node_id
        self.node_type = node_type
        self.hardware_class = hardware_class
        self.strategies = strategies
        self.api_key = api_key
        self.energy_cost = ENERGY_COSTS.get(node_type, 0.5)
        self.is_queen = node_type == "queen"
        self.running = True

        # Stats
        self.total_attempts = 0
        self.total_solves = 0
        self.total_score = 0.0

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _post(self, client: httpx.Client, path: str, body: dict) -> dict | None:
        url = f"{self.api_url}{path}"
        try:
            resp = client.post(url, json=body, headers=self._headers(), timeout=30.0)
            if resp.status_code >= 400:
                log.warning("POST %s -> %d: %s", path, resp.status_code, resp.text[:200])
                return None
            return resp.json()
        except httpx.HTTPError as exc:
            log.error("POST %s error: %s", path, exc)
            return None

    def _get(self, client: httpx.Client, path: str, params: dict | None = None) -> dict | None:
        url = f"{self.api_url}{path}"
        try:
            resp = client.get(url, params=params, headers=self._headers(), timeout=30.0)
            if resp.status_code >= 400:
                log.warning("GET %s -> %d: %s", path, resp.status_code, resp.text[:200])
                return None
            return resp.json()
        except httpx.HTTPError as exc:
            log.error("GET %s error: %s", path, exc)
            return None

    def register(self, client: httpx.Client) -> bool:
        """Register this node with the API."""
        result = self._post(client, "/nodes/register", {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "hardware_class": self.hardware_class,
            "metadata": {
                "worker": True,
                "hostname": platform.node(),
                "platform": platform.platform(),
                "strategies": self.strategies,
            },
        })
        if result:
            log.info("Registered as %s (%s/%s)", self.node_id, self.node_type, self.hardware_class)
            return True
        log.error("Failed to register as %s", self.node_id)
        return False

    def find_open_blocks(self, client: httpx.Client) -> list[dict]:
        """Fetch open blocks from the API."""
        data = self._get(client, "/blocks", {"status": "open", "limit": 50})
        if data and data.get("blocks"):
            return data["blocks"]
        return []

    def fetch_top_attempts(self, client: httpx.Client, block_id: str) -> list[dict]:
        """Fetch top-scoring attempts for parent derivation."""
        data = self._get(client, f"/attempts/block/{block_id}/top", {"limit": 5})
        if data and data.get("attempts"):
            return data["attempts"]
        return []

    def generate_and_submit(self, client: httpx.Client, block: dict) -> float | None:
        """Generate an attempt for a block and submit it."""
        block_id = block["block_id"]
        task_payload = block.get("task_payload", {})
        input_grid = task_payload.get("input_grid", [])
        expected_output = task_payload.get("expected_output", [])

        if not input_grid or not expected_output:
            return None

        exp_rows = len(expected_output)
        exp_cols = len(expected_output[0]) if exp_rows > 0 else 0
        expected_dims = (exp_rows, exp_cols)

        # Pick strategy
        strategy_name = random.choice(self.strategies)
        strategy_fn = STRATEGY_REGISTRY.get(strategy_name)
        if not strategy_fn:
            log.warning("Unknown strategy: %s", strategy_name)
            return None

        # Parent derivation for queen / random_perturbation
        parent_attempt_id: str | None = None
        parent_grid: Grid | None = None

        if self.is_queen or (strategy_name == "random_perturbation" and random.random() < 0.7):
            top_attempts = self.fetch_top_attempts(client, block_id)
            if top_attempts:
                weights = [max(a.get("score", 0.01), 0.01) for a in top_attempts]
                parent = random.choices(top_attempts, weights=weights, k=1)[0]
                parent_attempt_id = parent.get("attempt_id")
                parent_grid = parent.get("output_json", {}).get("grid")

        # Generate grid
        t0 = time.monotonic()
        grid = strategy_fn(
            input_grid=input_grid,
            expected_dims=expected_dims,
            parent_grid=parent_grid,
        )
        latency_ms = int((time.monotonic() - t0) * 1000) + random.randint(5, 30)

        # Submit
        result = self._post(client, "/attempts", {
            "node_id": self.node_id,
            "block_id": block_id,
            "parent_attempt_id": parent_attempt_id,
            "method": f"worker-{strategy_name}",
            "strategy_family": strategy_name,
            "output_json": {"grid": grid},
            "energy_cost": self.energy_cost,
            "latency_ms": latency_ms,
        })

        if not result:
            return None

        score = result.get("score", 0.0)
        self.total_attempts += 1
        self.total_score += score

        if score == 1.0:
            self.total_solves += 1
            log.info("-> block %s: %s -> score=%.3f SOLVED!",
                     block_id[:8], strategy_name, score)
        else:
            log.info("-> block %s: %s -> score=%.3f",
                     block_id[:8], strategy_name, score)

        return score

    def run(self) -> None:
        """Main worker loop -- runs until shutdown signal."""
        with httpx.Client() as client:
            # Check API
            root = self._get(client, "/")
            if not root:
                log.error("Cannot reach API at %s", self.api_url)
                return
            log.info("API alive: %s v%s", root.get("service"), root.get("version"))

            # Register
            if not self.register(client):
                return

            log.info("Starting mining loop (strategies: %s)", ", ".join(self.strategies))
            consecutive_empty = 0

            while self.running:
                try:
                    # Find open blocks
                    open_blocks = self.find_open_blocks(client)

                    if not open_blocks:
                        consecutive_empty += 1
                        if consecutive_empty == 1 or consecutive_empty % 12 == 0:
                            log.info("No open blocks. Waiting... (%d checks)", consecutive_empty)
                        time.sleep(5.0)
                        continue

                    consecutive_empty = 0
                    log.info("Found %d open blocks", len(open_blocks))

                    # Pick a random open block and submit
                    block = random.choice(open_blocks)
                    self.generate_and_submit(client, block)

                    # Small delay between attempts
                    time.sleep(0.1)

                except KeyboardInterrupt:
                    break
                except Exception as exc:
                    log.error("Error in mining loop: %s", exc)
                    time.sleep(2.0)

        self._print_stats()

    def _print_stats(self) -> None:
        """Print final worker stats."""
        avg = self.total_score / max(self.total_attempts, 1)
        print(f"\n[worker] Shutting down {self.node_id}")
        print(f"[worker] Total attempts: {self.total_attempts}")
        print(f"[worker] Total solves:   {self.total_solves}")
        print(f"[worker] Avg score:      {avg:.4f}")

    def stop(self) -> None:
        """Signal the worker to stop."""
        self.running = False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _generate_node_id(node_type: str) -> str:
    """Generate a unique node ID based on hostname and random suffix."""
    hostname = platform.node() or "unknown"
    suffix = hashlib.md5(f"{hostname}-{time.time()}-{os.getpid()}".encode()).hexdigest()[:6]
    return f"miner-{node_type}-{suffix}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SwarmChain Edge Worker -- standalone mining node for any machine",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8080",
        help="SwarmChain API base URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--node-id",
        default=None,
        help="Node ID (auto-generated if not provided)",
    )
    parser.add_argument(
        "--node-type",
        default="edge",
        choices=["jetmini", "edge", "zima", "mid-gpu", "queen"],
        help="Node type (default: edge)",
    )
    parser.add_argument(
        "--hardware-class",
        default="cpu",
        help="Hardware class descriptor (default: cpu)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional API key for authenticated endpoints",
    )
    parser.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated list of strategies (default: based on node-type)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve node ID
    node_id = args.node_id or _generate_node_id(args.node_type)

    # Resolve strategies
    if args.strategies:
        strategies = [s.strip() for s in args.strategies.split(",")]
        # Validate
        for s in strategies:
            if s not in STRATEGY_REGISTRY:
                print(f"[worker] ERROR: Unknown strategy '{s}'. Available: {', '.join(STRATEGY_REGISTRY.keys())}")
                sys.exit(1)
    else:
        strategies = DEFAULT_STRATEGIES.get(args.node_type, ["random_grid", "random_perturbation"])

    worker = EdgeWorker(
        api_url=args.api_url,
        node_id=node_id,
        node_type=args.node_type,
        hardware_class=args.hardware_class,
        strategies=strategies,
        api_key=args.api_key,
    )

    # Install signal handlers for graceful shutdown
    def _shutdown(sig, frame):
        log.info("Received signal %s, shutting down...", sig)
        worker.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    worker.run()


if __name__ == "__main__":
    main()
