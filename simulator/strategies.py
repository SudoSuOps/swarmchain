"""Strategy implementations for SwarmChain node types.

Each strategy takes an input grid, expected output dimensions, and an optional
parent grid (for derivation/perturbation).  Returns a candidate output grid.

Strategies are intentionally simple transforms — some will produce the correct
answer for the matching ARC task, giving blocks a realistic chance of solving.
"""
from __future__ import annotations

import copy
import random
from typing import Callable

Grid = list[list[int]]

# Maximum color value used across all ARC tasks
MAX_COLOR = 9


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grid_dims(grid: Grid) -> tuple[int, int]:
    """Return (rows, cols) for a grid."""
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    return rows, cols


def _colors_in_grid(grid: Grid) -> set[int]:
    """Return the set of distinct color values in a grid."""
    colors: set[int] = set()
    for row in grid:
        colors.update(row)
    return colors


def _make_empty(rows: int, cols: int, fill: int = 0) -> Grid:
    """Create a grid of the given size filled with a constant."""
    return [[fill] * cols for _ in range(rows)]


def _clamp_to_dims(grid: Grid, rows: int, cols: int) -> Grid:
    """Trim or pad a grid so it is exactly (rows x cols)."""
    result: Grid = []
    for r in range(rows):
        if r < len(grid):
            src_row = grid[r]
            new_row = [src_row[c] if c < len(src_row) else 0 for c in range(cols)]
        else:
            new_row = [0] * cols
        result.append(new_row)
    return result


# ---------------------------------------------------------------------------
# Strategy functions
# ---------------------------------------------------------------------------

def random_grid(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Generate a completely random grid of the correct dimensions.

    Cheap, wide exploration — rarely correct but validates scoring pipeline.
    """
    rows, cols = expected_dims
    colors = list(_colors_in_grid(input_grid) | {0, 1})
    return [[random.choice(colors) for _ in range(cols)] for _ in range(rows)]


def random_perturbation(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Take a parent grid and randomly mutate 1-3 cells.

    If no parent is provided, perturbs the input grid instead.
    This is the queen's refinement strategy — small directed changes.
    """
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
    """Horizontal mirror — reverse each row.

    Solves arc-002-mirror-h exactly.
    """
    mirrored = [list(reversed(row)) for row in input_grid]
    return _clamp_to_dims(mirrored, *expected_dims)


def mirror_v(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Vertical mirror — reverse the row order."""
    mirrored = list(reversed([list(row) for row in input_grid]))
    return _clamp_to_dims(mirrored, *expected_dims)


def rotate_90(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Rotate grid 90 degrees clockwise.

    Solves arc-003-rotate-90 exactly.
    """
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
    """Rotate grid 270 degrees clockwise (= 90 counter-clockwise)."""
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
    """Swap two non-zero colors in the grid.

    Picks the two most frequent non-zero colors and swaps them.
    Solves arc-004-color-swap for the 1<->2 case.
    """
    freq: dict[int, int] = {}
    for row in input_grid:
        for val in row:
            if val != 0:
                freq[val] = freq.get(val, 0) + 1

    # Sort by frequency descending, pick top two
    sorted_colors = sorted(freq.keys(), key=lambda c: freq[c], reverse=True)
    if len(sorted_colors) < 2:
        # Not enough colors to swap — return as-is
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


def transpose(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Transpose the grid — swap rows and columns.

    Solves arc-006-transpose exactly.
    """
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
    """Submit the input grid as-is — naive baseline.

    Produces a partial score whenever the input and output share cells.
    """
    return _clamp_to_dims([list(row) for row in input_grid], *expected_dims)


def scale_2x(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Scale the grid 2x — each cell becomes a 2x2 block.

    Solves arc-008-scale-2x exactly.
    """
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
    """Add a border of 3s around the grid.

    Solves arc-005-border exactly (which uses color 3 as border).
    """
    rows, cols = _grid_dims(input_grid)
    new_rows = rows + 2
    new_cols = cols + 2
    bordered: Grid = []
    bordered.append([3] * new_cols)
    for r in range(rows):
        bordered.append([3] + list(input_grid[r]) + [3])
    bordered.append([3] * new_cols)

    return _clamp_to_dims(bordered, *expected_dims)


def invert(
    input_grid: Grid,
    expected_dims: tuple[int, int],
    parent_grid: Grid | None = None,
) -> Grid:
    """Invert: 0 becomes 1, non-zero becomes 0.

    Solves arc-007-invert exactly.
    """
    inverted = [
        [1 if val == 0 else 0 for val in row]
        for row in input_grid
    ]
    return _clamp_to_dims(inverted, *expected_dims)


# ---------------------------------------------------------------------------
# Strategy registry — maps name to callable
# ---------------------------------------------------------------------------

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
