"""Procedural ARC task generator — deterministic grid transformations from seeds.

Each seed maps to exactly one task via a pure function chain:
  seed -> RNG -> grid + transform_type -> input_grid + expected_output

Tier 1: 25 single transforms (geometric, color, pooling, gravity).
Tier 2: Compositional transforms (2-3 sequential operations).
Tier 3: Relational/object tasks (connected components, counting, tiling).
Tier 4: Holdout mix (40% T1, 40% T2, 20% T3) with non-overlapping seeds.

All transforms are pure functions: input_grid -> output_grid.
"""
from __future__ import annotations

import random
from collections import Counter, deque
from typing import Any

# ARC color palette: 0=black, 1=blue, 2=red, 3=green, 4=yellow,
#                    5=gray, 6=magenta, 7=orange, 8=cyan, 9=maroon
MAX_COLOR = 9

# Ordered list of all 25 transform types
TRANSFORM_TYPES: list[str] = [
    "mirror_h",
    "mirror_v",
    "rotate_90",
    "rotate_180",
    "rotate_270",
    "transpose",
    "color_swap",
    "invert",
    "fill_zeros",
    "scale_2x",
    "border_add",
    "crop_1",
    "shift_right",
    "shift_down",
    "shift_left",
    "shift_up",
    "gravity_down",
    "gravity_left",
    "flood_fill",
    "pattern_tile_2x2",
    "checkerboard",
    "diagonal_mirror",
    "color_remap",
    "max_pool_2x2",
    "sort_rows",
]

# Transforms that preserve grid dimensions — safe for Tier 2 composition.
# Excluded: scale_2x, border_add, crop_1, max_pool_2x2, pattern_tile_2x2
# (these change grid size, which can break a second transform's assumptions).
# Also excluded: transpose, diagonal_mirror, rotate_90, rotate_270
# (these swap rows/cols on non-square grids — fine individually but
#  only safe in composition on square grids, so we allow them but
#  force square grids when they appear in a composition).
_DIMENSION_CHANGING_TRANSFORMS: set[str] = {
    "scale_2x", "border_add", "crop_1", "max_pool_2x2", "pattern_tile_2x2",
}

_DIMENSION_SWAPPING_TRANSFORMS: set[str] = {
    "transpose", "diagonal_mirror", "rotate_90", "rotate_270",
}

_COMPOSABLE_TRANSFORMS: list[str] = [
    t for t in TRANSFORM_TYPES if t not in _DIMENSION_CHANGING_TRANSFORMS
]

# Transforms that need a minimum grid size to produce valid output
_MIN_SIZE_FOR_TRANSFORM: dict[str, int] = {
    "crop_1": 3,         # need at least 3x3 to crop to 1x1
    "max_pool_2x2": 2,   # need at least 2x2 for pooling
}

# Grid size bucket weights — we pick a "max dimension" bucket first,
# then sample rows and cols uniformly within that bucket.
# Target: 2x2~50, 3x3~200, 4x4~250, 5x5~200, 6x6~150, 7-8~100, 9-10~50
_GRID_BUCKET_WEIGHTS: list[tuple[int, float]] = [
    (2, 50.0),
    (3, 200.0),
    (4, 250.0),
    (5, 200.0),
    (6, 150.0),
    (7, 50.0),
    (8, 50.0),
    (9, 25.0),
    (10, 25.0),
]


Grid = list[list[int]]


# ---------------------------------------------------------------------------
# 25 Transform implementations — each is a pure function
# ---------------------------------------------------------------------------


def _mirror_h(grid: Grid, rng: random.Random) -> Grid:
    """Flip horizontally (reverse each row)."""
    return [row[::-1] for row in grid]


def _mirror_v(grid: Grid, rng: random.Random) -> Grid:
    """Flip vertically (reverse row order)."""
    return grid[::-1]


def _rotate_90(grid: Grid, rng: random.Random) -> Grid:
    """Rotate 90 degrees clockwise."""
    rows, cols = len(grid), len(grid[0])
    return [[grid[rows - 1 - r][c] for r in range(rows)] for c in range(cols)]


def _rotate_180(grid: Grid, rng: random.Random) -> Grid:
    """Rotate 180 degrees."""
    return [row[::-1] for row in grid[::-1]]


def _rotate_270(grid: Grid, rng: random.Random) -> Grid:
    """Rotate 270 degrees clockwise (= 90 counter-clockwise)."""
    rows, cols = len(grid), len(grid[0])
    return [[grid[r][cols - 1 - c] for r in range(rows)] for c in range(cols)]


def _transpose(grid: Grid, rng: random.Random) -> Grid:
    """Swap rows and columns."""
    rows, cols = len(grid), len(grid[0])
    return [[grid[r][c] for r in range(rows)] for c in range(cols)]


def _color_swap(grid: Grid, rng: random.Random) -> Grid:
    """Swap two specific colors determined by the RNG."""
    # Collect all distinct colors in the grid
    colors_present = set()
    for row in grid:
        for v in row:
            colors_present.add(v)

    colors_list = sorted(colors_present)
    if len(colors_list) < 2:
        # Not enough colors — swap color with a new one
        c1 = colors_list[0]
        c2 = (c1 + 1) % (MAX_COLOR + 1)
    else:
        pair = rng.sample(colors_list, 2)
        c1, c2 = pair[0], pair[1]

    return [[c2 if v == c1 else c1 if v == c2 else v for v in row] for row in grid]


def _invert(grid: Grid, rng: random.Random) -> Grid:
    """0 -> 1, nonzero -> 0."""
    return [[1 if v == 0 else 0 for v in row] for row in grid]


def _fill_zeros(grid: Grid, rng: random.Random) -> Grid:
    """Replace all 0s with a seed-derived color (1-9)."""
    fill_color = rng.randint(1, MAX_COLOR)
    return [[fill_color if v == 0 else v for v in row] for row in grid]


def _scale_2x(grid: Grid, rng: random.Random) -> Grid:
    """Each cell becomes a 2x2 block — output is 2x the dimensions."""
    result = []
    for row in grid:
        expanded_row = []
        for v in row:
            expanded_row.extend([v, v])
        result.append(expanded_row)
        result.append(list(expanded_row))  # duplicate row
    return result


def _border_add(grid: Grid, rng: random.Random) -> Grid:
    """Add a 1-cell border of a seed-derived color."""
    border_color = rng.randint(1, MAX_COLOR)
    rows, cols = len(grid), len(grid[0])
    new_cols = cols + 2
    result = [[border_color] * new_cols]  # top border
    for row in grid:
        result.append([border_color] + row + [border_color])
    result.append([border_color] * new_cols)  # bottom border
    return result


def _crop_1(grid: Grid, rng: random.Random) -> Grid:
    """Remove outermost row/col on all sides."""
    rows, cols = len(grid), len(grid[0])
    # Guaranteed rows >= 3 and cols >= 3 by min-size enforcement
    return [row[1:-1] for row in grid[1:-1]]


def _shift_right(grid: Grid, rng: random.Random) -> Grid:
    """Shift all cells right by 1, wrapping."""
    return [row[-1:] + row[:-1] for row in grid]


def _shift_down(grid: Grid, rng: random.Random) -> Grid:
    """Shift all rows down by 1, wrapping."""
    return grid[-1:] + grid[:-1]


def _shift_left(grid: Grid, rng: random.Random) -> Grid:
    """Shift all cells left by 1, wrapping."""
    return [row[1:] + row[:1] for row in grid]


def _shift_up(grid: Grid, rng: random.Random) -> Grid:
    """Shift all rows up by 1, wrapping."""
    return grid[1:] + grid[:1]


def _gravity_down(grid: Grid, rng: random.Random) -> Grid:
    """Non-zero cells fall to the bottom of each column."""
    rows, cols = len(grid), len(grid[0])
    result = [[0] * cols for _ in range(rows)]
    for c in range(cols):
        non_zero = [grid[r][c] for r in range(rows) if grid[r][c] != 0]
        # Pack non-zero values to the bottom
        start = rows - len(non_zero)
        for i, v in enumerate(non_zero):
            result[start + i][c] = v
    return result


def _gravity_left(grid: Grid, rng: random.Random) -> Grid:
    """Non-zero cells fall to the left of each row."""
    result = []
    for row in grid:
        non_zero = [v for v in row if v != 0]
        padded = non_zero + [0] * (len(row) - len(non_zero))
        result.append(padded)
    return result


def _flood_fill(grid: Grid, rng: random.Random) -> Grid:
    """BFS flood fill from the top-left 0-region with a seed-derived color."""
    fill_color = rng.randint(1, MAX_COLOR)
    rows, cols = len(grid), len(grid[0])
    result = [list(row) for row in grid]

    # Find target color at (0, 0)
    target = result[0][0]
    if target == fill_color:
        # If top-left already matches fill color, pick a different one
        fill_color = (fill_color % MAX_COLOR) + 1

    if target != 0:
        # Only flood fill if the origin is 0
        # If origin is nonzero, find the first 0-cell via BFS and start there
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
            # No zeros in grid — just return as-is
            return result
    else:
        start_r, start_c = 0, 0

    # BFS fill
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
    """Tile the grid into a 2x larger grid (2x2 copies)."""
    rows, cols = len(grid), len(grid[0])
    result = []
    for _ in range(2):
        for row in grid:
            result.append(row + row)
    return result


def _checkerboard(grid: Grid, rng: random.Random) -> Grid:
    """Replace grid with checkerboard using the two most common colors."""
    # Count colors
    counter: Counter[int] = Counter()
    for row in grid:
        for v in row:
            counter[v] += 1

    most_common = counter.most_common()
    c1 = most_common[0][0]
    c2 = most_common[1][0] if len(most_common) > 1 else (c1 + 1) % (MAX_COLOR + 1)

    rows, cols = len(grid), len(grid[0])
    return [[(c1 if (r + c) % 2 == 0 else c2) for c in range(cols)] for r in range(rows)]


def _diagonal_mirror(grid: Grid, rng: random.Random) -> Grid:
    """Mirror across main diagonal (same as transpose)."""
    rows, cols = len(grid), len(grid[0])
    return [[grid[r][c] for r in range(rows)] for c in range(cols)]


def _color_remap(grid: Grid, rng: random.Random) -> Grid:
    """Remap colors based on a seed-derived permutation."""
    # Build a mapping from each present color to another
    colors_present = set()
    for row in grid:
        for v in row:
            colors_present.add(v)

    colors_list = sorted(colors_present)
    shuffled = list(colors_list)
    rng.shuffle(shuffled)

    # Ensure at least one color actually changes (avoid identity map)
    if shuffled == colors_list and len(colors_list) > 1:
        shuffled[0], shuffled[1] = shuffled[1], shuffled[0]

    mapping = dict(zip(colors_list, shuffled))
    return [[mapping[v] for v in row] for row in grid]


def _max_pool_2x2(grid: Grid, rng: random.Random) -> Grid:
    """2x2 max pooling — reduce grid by half, take max in each 2x2 block."""
    rows, cols = len(grid), len(grid[0])
    # Truncate to even dimensions
    pool_rows = rows // 2
    pool_cols = cols // 2
    result = []
    for r in range(pool_rows):
        result_row = []
        for c in range(pool_cols):
            block = [
                grid[2 * r][2 * c],
                grid[2 * r][2 * c + 1],
                grid[2 * r + 1][2 * c],
                grid[2 * r + 1][2 * c + 1],
            ]
            result_row.append(max(block))
        result.append(result_row)
    return result


def _sort_rows(grid: Grid, rng: random.Random) -> Grid:
    """Sort each row in ascending order."""
    return [sorted(row) for row in grid]


# ---------------------------------------------------------------------------
# Transform dispatch table
# ---------------------------------------------------------------------------

_TRANSFORM_FN: dict[str, Any] = {
    "mirror_h": _mirror_h,
    "mirror_v": _mirror_v,
    "rotate_90": _rotate_90,
    "rotate_180": _rotate_180,
    "rotate_270": _rotate_270,
    "transpose": _transpose,
    "color_swap": _color_swap,
    "invert": _invert,
    "fill_zeros": _fill_zeros,
    "scale_2x": _scale_2x,
    "border_add": _border_add,
    "crop_1": _crop_1,
    "shift_right": _shift_right,
    "shift_down": _shift_down,
    "shift_left": _shift_left,
    "shift_up": _shift_up,
    "gravity_down": _gravity_down,
    "gravity_left": _gravity_left,
    "flood_fill": _flood_fill,
    "pattern_tile_2x2": _pattern_tile_2x2,
    "checkerboard": _checkerboard,
    "diagonal_mirror": _diagonal_mirror,
    "color_remap": _color_remap,
    "max_pool_2x2": _max_pool_2x2,
    "sort_rows": _sort_rows,
}

# Verify all 25 transforms are registered
assert len(_TRANSFORM_FN) == 25, f"Expected 25 transforms, got {len(_TRANSFORM_FN)}"
assert set(_TRANSFORM_FN.keys()) == set(TRANSFORM_TYPES)

# Human-readable descriptions for each transform
_TRANSFORM_DESCRIPTIONS: dict[str, str] = {
    "mirror_h": "Flip the grid horizontally (reverse each row)",
    "mirror_v": "Flip the grid vertically (reverse row order)",
    "rotate_90": "Rotate the grid 90 degrees clockwise",
    "rotate_180": "Rotate the grid 180 degrees",
    "rotate_270": "Rotate the grid 270 degrees clockwise",
    "transpose": "Transpose the grid (swap rows and columns)",
    "color_swap": "Swap two specific colors in the grid",
    "invert": "Invert the grid: 0 becomes 1, nonzero becomes 0",
    "fill_zeros": "Replace all zeros with a specific color",
    "scale_2x": "Scale the grid 2x (each cell becomes a 2x2 block)",
    "border_add": "Add a 1-cell border around the grid",
    "crop_1": "Remove the outermost row and column on all sides",
    "shift_right": "Shift all cells right by 1, wrapping around",
    "shift_down": "Shift all rows down by 1, wrapping around",
    "shift_left": "Shift all cells left by 1, wrapping around",
    "shift_up": "Shift all rows up by 1, wrapping around",
    "gravity_down": "Non-zero cells fall to the bottom of each column",
    "gravity_left": "Non-zero cells fall to the left of each row",
    "flood_fill": "BFS flood fill from the first 0-region with a color",
    "pattern_tile_2x2": "Tile the grid into a 2x larger grid (2x2 copies)",
    "checkerboard": "Replace with checkerboard using the two most common colors",
    "diagonal_mirror": "Mirror across the main diagonal",
    "color_remap": "Remap all colors based on a seed-derived permutation",
    "max_pool_2x2": "2x2 max pooling (reduce grid by half, take max in each block)",
    "sort_rows": "Sort each row in ascending order",
}


# ---------------------------------------------------------------------------
# Grid generation helpers
# ---------------------------------------------------------------------------


def _pick_grid_size(rng: random.Random, transform_type: str) -> tuple[int, int]:
    """Pick (rows, cols) with a bucket-first strategy for correct distribution.

    Strategy: pick a max-dimension bucket, then sample rows and cols so that
    max(rows, cols) == bucket value. This gives precise control over the
    grid-size distribution as perceived by the caller.
    """
    min_size = _MIN_SIZE_FOR_TRANSFORM.get(transform_type, 2)

    # Filter buckets by min size
    valid = [(s, w) for s, w in _GRID_BUCKET_WEIGHTS if s >= min_size]
    if not valid:
        valid = [(min_size, 1.0)]

    # For max_pool_2x2, restrict to even bucket sizes
    if transform_type == "max_pool_2x2":
        even_valid = [(s, w) for s, w in valid if s % 2 == 0]
        if even_valid:
            valid = even_valid
        else:
            valid = [(2, 1.0)]

    bucket_sizes = [s for s, _ in valid]
    bucket_weights = [w for _, w in valid]

    max_dim = rng.choices(bucket_sizes, weights=bucket_weights, k=1)[0]

    # Sample rows and cols such that max(rows, cols) == max_dim
    # One axis gets max_dim, the other gets a random value in [min_size, max_dim]
    lo = max(min_size, 2)
    other_dim = rng.randint(lo, max_dim)

    if transform_type == "max_pool_2x2":
        # Force both even
        other_dim = other_dim if other_dim % 2 == 0 else other_dim + 1
        if other_dim > max_dim:
            other_dim = max_dim

    # Randomly assign which axis gets the max
    if rng.random() < 0.5:
        rows, cols = max_dim, other_dim
    else:
        rows, cols = other_dim, max_dim

    return rows, cols


def _pick_grid_size_range(
    rng: random.Random, min_dim: int, max_dim: int, force_square: bool = False
) -> tuple[int, int]:
    """Pick (rows, cols) uniformly in [min_dim, max_dim].

    If force_square is True, rows == cols.
    """
    rows = rng.randint(min_dim, max_dim)
    if force_square:
        cols = rows
    else:
        cols = rng.randint(min_dim, max_dim)
    return rows, cols


def _generate_grid(rng: random.Random, rows: int, cols: int, num_colors: int) -> Grid:
    """Generate a random grid with the given dimensions and color count."""
    # Pick which colors to use (always include 0 as one of them for variety)
    if num_colors <= 1:
        palette = [0]
    else:
        # Always include 0, pick the rest from 1-9
        other_colors = rng.sample(range(1, MAX_COLOR + 1), min(num_colors - 1, MAX_COLOR))
        palette = [0] + other_colors

    return [[rng.choice(palette) for _ in range(cols)] for _ in range(rows)]


def _deep_copy_grid(grid: Grid) -> Grid:
    """Deep copy a 2D grid."""
    return [list(row) for row in grid]


# ---------------------------------------------------------------------------
# Tier 2: Compositional transforms
# ---------------------------------------------------------------------------

# 15 curated compositions (dimension-safe combinations)
TIER2_CURATED_COMPOSITIONS: list[tuple[str, ...]] = [
    ("mirror_h", "color_swap"),
    ("mirror_v", "invert"),
    ("rotate_90", "mirror_h"),
    ("rotate_180", "color_swap"),
    ("transpose", "invert"),
    ("fill_zeros", "mirror_h"),
    ("invert", "rotate_90"),
    ("color_swap", "transpose"),
    ("mirror_h", "rotate_90"),
    ("shift_right", "invert"),
    ("shift_down", "mirror_v"),
    ("gravity_down", "color_swap"),
    ("sort_rows", "mirror_v"),
    ("rotate_270", "fill_zeros"),
    ("mirror_h", "mirror_v"),  # equivalent to rotate_180
]


def _needs_square_grid(transforms: tuple[str, ...] | list[str]) -> bool:
    """Return True if any transform in the chain swaps dimensions.

    Transforms like transpose, rotate_90, rotate_270, diagonal_mirror swap
    rows and cols. If the grid is not square, the intermediate grid dimensions
    change, which can cause issues with subsequent transforms that assume
    stable dimensions. Force square grids when any swapping transform appears.
    """
    return any(t in _DIMENSION_SWAPPING_TRANSFORMS for t in transforms)


def _apply_transform_chain(
    grid: Grid, transforms: tuple[str, ...] | list[str], rng: random.Random
) -> Grid:
    """Apply a sequence of transforms to a grid, forking the RNG for each step.

    Example:
        >>> rng = random.Random(42)
        >>> grid = [[1, 0], [0, 2]]
        >>> result = _apply_transform_chain(grid, ("mirror_h", "invert"), rng)
        >>> # Step 1: mirror_h -> [[0, 1], [2, 0]]
        >>> # Step 2: invert  -> [[1, 0], [0, 1]]
    """
    current = _deep_copy_grid(grid)
    for t_name in transforms:
        fn = _TRANSFORM_FN[t_name]
        step_rng = random.Random(rng.randint(0, 2**32 - 1))
        current = fn(current, step_rng)
    return current


# ---------------------------------------------------------------------------
# Tier 3: Relational/object transform implementations
# ---------------------------------------------------------------------------

TIER3_TASK_TYPES: list[str] = [
    "largest_object_moves",
    "count_colors",
    "fill_enclosed",
    "duplicate_pattern",
    "extract_border",
    "max_color_fill",
]


def _bfs_component(grid: Grid, start_r: int, start_c: int, visited: set) -> list[tuple[int, int]]:
    """BFS flood-fill to find a connected component of same-color cells.

    Returns list of (row, col) coordinates belonging to this component.
    Only considers 4-connected neighbors (up/down/left/right).
    """
    rows, cols = len(grid), len(grid[0])
    color = grid[start_r][start_c]
    component = []
    queue = deque([(start_r, start_c)])
    visited.add((start_r, start_c))

    while queue:
        r, c = queue.popleft()
        component.append((r, c))
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if (
                0 <= nr < rows
                and 0 <= nc < cols
                and (nr, nc) not in visited
                and grid[nr][nc] == color
            ):
                visited.add((nr, nc))
                queue.append((nr, nc))

    return component


def _find_all_components(grid: Grid, ignore_zero: bool = True) -> list[tuple[int, list[tuple[int, int]]]]:
    """Find all connected components in the grid.

    Returns list of (color, [(r, c), ...]) sorted by component size descending.
    If ignore_zero is True, skips cells with value 0.
    """
    rows, cols = len(grid), len(grid[0])
    visited: set[tuple[int, int]] = set()
    components: list[tuple[int, list[tuple[int, int]]]] = []

    for r in range(rows):
        for c in range(cols):
            if (r, c) not in visited:
                if ignore_zero and grid[r][c] == 0:
                    visited.add((r, c))
                    continue
                comp = _bfs_component(grid, r, c, visited)
                components.append((grid[r][c], comp))

    # Sort by size descending, then by color for determinism
    components.sort(key=lambda x: (-len(x[1]), x[0]))
    return components


def _t3_largest_object_moves(grid: Grid, rng: random.Random) -> Grid:
    """Identify the largest connected non-zero region and shift it by 1 cell.

    Direction is chosen by the RNG: 0=up, 1=down, 2=left, 3=right.
    If the shift would push cells out of bounds, they wrap around.

    Example (4x4 grid, largest object is 3 cells of color 2, shift=right):
        Input:                Output:
        [[0, 2, 2, 0],       [[0, 0, 2, 2],
         [0, 2, 0, 0],        [0, 0, 2, 0],
         [0, 0, 1, 0],        [0, 0, 1, 0],
         [0, 0, 0, 0]]        [0, 0, 0, 0]]
    """
    rows, cols = len(grid), len(grid[0])
    components = _find_all_components(grid, ignore_zero=True)

    if not components:
        return _deep_copy_grid(grid)

    # Largest component
    _, largest_cells = components[0]
    largest_set = set(largest_cells)

    direction = rng.randint(0, 3)  # 0=up, 1=down, 2=left, 3=right
    dr, dc = [(-1, 0), (1, 0), (0, -1), (0, 1)][direction]

    # Build output: start with grid minus the object cells
    result = _deep_copy_grid(grid)
    for r, c in largest_cells:
        result[r][c] = 0

    # Place shifted cells (wrapping)
    for r, c in largest_cells:
        nr = (r + dr) % rows
        nc = (c + dc) % cols
        result[nr][nc] = grid[r][c]

    return result


def _t3_count_colors(grid: Grid, rng: random.Random) -> Grid:
    """Output a 1xN grid where cell i = count of color i in the input.

    N = max color value present + 1 (so indices 0..max_color_present).

    Example (3x3 grid with colors 0,1,2):
        Input:                Output:
        [[0, 1, 2],          [[4, 3, 2]]
         [0, 1, 0],
         [0, 0, 1]]
    """
    counter: Counter[int] = Counter()
    for row in grid:
        for v in row:
            counter[v] += 1

    if not counter:
        return [[0]]

    max_color_present = max(counter.keys())
    result_row = [counter.get(i, 0) for i in range(max_color_present + 1)]
    return [result_row]


def _t3_fill_enclosed(grid: Grid, rng: random.Random) -> Grid:
    """Fill regions of 0 that are fully enclosed by non-zero cells.

    A region of 0s is "enclosed" if no cell in it touches the grid border
    (directly or via connected 0-cells that reach the border).
    Enclosed regions are filled with the most common non-zero color
    among their 4-connected neighbors.

    Example (5x5):
        Input:                Output:
        [[1, 1, 1, 0, 0],    [[1, 1, 1, 0, 0],
         [1, 0, 1, 0, 0],     [1, 1, 1, 0, 0],
         [1, 1, 1, 0, 0],     [1, 1, 1, 0, 0],
         [0, 0, 0, 0, 0],     [0, 0, 0, 0, 0],
         [0, 0, 0, 0, 0]]     [0, 0, 0, 0, 0]]
    The center 0 at (1,1) is enclosed by 1s, so it becomes 1.
    The border-touching 0s remain 0.
    """
    rows, cols = len(grid), len(grid[0])
    result = _deep_copy_grid(grid)

    # Find all 0-regions via BFS
    visited: set[tuple[int, int]] = set()
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != 0:
                visited.add((r, c))

    zero_regions: list[list[tuple[int, int]]] = []
    for r in range(rows):
        for c in range(cols):
            if (r, c) not in visited:
                region = _bfs_component(grid, r, c, visited)
                zero_regions.append(region)

    # For each zero region, check if any cell touches the border
    for region in zero_regions:
        touches_border = any(
            r == 0 or r == rows - 1 or c == 0 or c == cols - 1
            for r, c in region
        )
        if touches_border:
            continue  # Not enclosed

        # Find the most common non-zero neighbor color
        neighbor_colors: Counter[int] = Counter()
        for r, c in region:
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] != 0:
                    neighbor_colors[grid[nr][nc]] += 1

        if neighbor_colors:
            fill_color = neighbor_colors.most_common(1)[0][0]
        else:
            fill_color = 1  # fallback

        for r, c in region:
            result[r][c] = fill_color

    return result


def _t3_duplicate_pattern(grid: Grid, rng: random.Random) -> Grid:
    """Tile the input grid 2x1 (horizontal) or 1x2 (vertical).

    Direction chosen by RNG: 0 = horizontal (side by side), 1 = vertical (stacked).

    Example (horizontal, 2x3 input):
        Input:           Output:
        [[1, 2, 3],     [[1, 2, 3, 1, 2, 3],
         [4, 5, 6]]      [4, 5, 6, 4, 5, 6]]

    Example (vertical, 2x3 input):
        Input:           Output:
        [[1, 2, 3],     [[1, 2, 3],
         [4, 5, 6]]      [4, 5, 6],
                          [1, 2, 3],
                          [4, 5, 6]]
    """
    direction = rng.randint(0, 1)
    if direction == 0:
        # Horizontal: side by side
        return [row + list(row) for row in grid]
    else:
        # Vertical: stacked
        return _deep_copy_grid(grid) + _deep_copy_grid(grid)


def _t3_extract_border(grid: Grid, rng: random.Random) -> Grid:
    """Output only the border cells; interior cells become 0.

    Example (4x4):
        Input:               Output:
        [[1, 2, 3, 4],      [[1, 2, 3, 4],
         [5, 6, 7, 8],       [5, 0, 0, 8],
         [9, 1, 2, 3],       [9, 0, 0, 3],
         [4, 5, 6, 7]]       [4, 5, 6, 7]]
    """
    rows, cols = len(grid), len(grid[0])
    result = [[0] * cols for _ in range(rows)]

    for r in range(rows):
        for c in range(cols):
            if r == 0 or r == rows - 1 or c == 0 or c == cols - 1:
                result[r][c] = grid[r][c]

    return result


def _t3_max_color_fill(grid: Grid, rng: random.Random) -> Grid:
    """Replace all cells with the most common non-zero color.

    If there are no non-zero cells, fill with 1.

    Example (3x3):
        Input:              Output:
        [[0, 1, 2],        [[1, 1, 1],
         [1, 1, 0],         [1, 1, 1],
         [0, 2, 0]]         [1, 1, 1]]
    (color 1 appears 3 times, color 2 appears 2 times)
    """
    counter: Counter[int] = Counter()
    rows, cols = len(grid), len(grid[0])
    for row in grid:
        for v in row:
            if v != 0:
                counter[v] += 1

    if not counter:
        fill = 1
    else:
        fill = counter.most_common(1)[0][0]

    return [[fill] * cols for _ in range(rows)]


_TIER3_TRANSFORM_FN: dict[str, Any] = {
    "largest_object_moves": _t3_largest_object_moves,
    "count_colors": _t3_count_colors,
    "fill_enclosed": _t3_fill_enclosed,
    "duplicate_pattern": _t3_duplicate_pattern,
    "extract_border": _t3_extract_border,
    "max_color_fill": _t3_max_color_fill,
}

_TIER3_DESCRIPTIONS: dict[str, str] = {
    "largest_object_moves": "Shift the largest connected non-zero region by 1 cell",
    "count_colors": "Output a 1xN row counting occurrences of each color 0..max",
    "fill_enclosed": "Fill enclosed zero-regions with the neighboring non-zero color",
    "duplicate_pattern": "Tile the grid 2x1 (horizontal) or 1x2 (vertical)",
    "extract_border": "Keep only border cells; set interior to 0",
    "max_color_fill": "Replace all cells with the most common non-zero color",
}


# ---------------------------------------------------------------------------
# Main generator class
# ---------------------------------------------------------------------------


class ARCTaskGenerator:
    """Deterministic procedural ARC task generator.

    Each seed maps to exactly one task. The same seed always produces the same
    task. The catalog of 1000 tasks is a fixed, reproducible dataset.

    Supports four tiers:
      - Tier 1: Single transforms (25 types)
      - Tier 2: Compositional transforms (2-3 sequential operations)
      - Tier 3: Relational/object tasks (connected components, counting, etc.)
      - Tier 4 (Holdout): Mixed tier sampling with non-overlapping seeds
    """

    # -----------------------------------------------------------------------
    # Tier 1 — Single transforms (original)
    # -----------------------------------------------------------------------

    def generate(self, seed: int) -> dict:
        """Generate one Tier 1 ARC task deterministically from a seed.

        Returns:
            dict with keys: task_id, description, input_grid, expected_output,
                            transform_type, grid_size, seed, tier
        """
        rng = random.Random(seed)

        # 1. Pick transform type (uniform across all 25)
        transform_type = TRANSFORM_TYPES[seed % len(TRANSFORM_TYPES)]

        # 2. Pick grid size
        rows, cols = _pick_grid_size(rng, transform_type)

        # 3. Pick number of colors (2-5)
        num_colors = rng.randint(2, 5)

        # 4. Generate input grid
        input_grid = _generate_grid(rng, rows, cols, num_colors)

        # 5. Apply transform to get expected output
        # Create a fresh RNG fork for the transform (so transform params are deterministic)
        transform_rng = random.Random(rng.randint(0, 2**32 - 1))
        transform_fn = _TRANSFORM_FN[transform_type]
        expected_output = transform_fn(input_grid, transform_rng)

        # 6. Compute output grid size
        out_rows = len(expected_output)
        out_cols = len(expected_output[0]) if out_rows > 0 else 0

        # 7. Build task ID
        task_id = f"arc-gen-{seed:05d}-{transform_type}"

        # 8. Build description
        base_desc = _TRANSFORM_DESCRIPTIONS[transform_type]
        description = f"{base_desc} ({rows}x{cols} -> {out_rows}x{out_cols})"

        return {
            "task_id": task_id,
            "description": description,
            "input_grid": input_grid,
            "expected_output": expected_output,
            "transform_type": transform_type,
            "grid_size": {"rows": rows, "cols": cols},
            "seed": seed,
            "tier": 1,
        }

    def generate_catalog(self, count: int = 1000, base_seed: int = 42) -> list[dict]:
        """Generate a catalog of `count` Tier 1 tasks starting from `base_seed`.

        Seeds used: base_seed, base_seed+1, ..., base_seed+count-1
        """
        return [self.generate(base_seed + i) for i in range(count)]

    # -----------------------------------------------------------------------
    # Tier 2 — Compositional transforms (2-3 sequential operations)
    # -----------------------------------------------------------------------

    def generate_tier2(self, seed: int) -> dict:
        """Generate one Tier 2 (compositional) ARC task from a seed.

        Picks 2-3 transforms from the composable set, generates a grid,
        and applies them sequentially.

        Grid sizes: 3x3 to 6x6.
        Task ID format: arc-t2-{seed:05d}-{transform1}+{transform2}[+{transform3}]

        Example (seed=2000):
            Picks mirror_h + color_swap from curated list.
            Generates a 4x4 grid, applies mirror_h then color_swap.
            The expected_output is the result of both transforms.

        Returns:
            dict with keys: task_id, description, input_grid, expected_output,
                            transform_type, transforms, grid_size, seed, tier
        """
        rng = random.Random(seed)

        # Decide: use curated composition or random
        num_curated = len(TIER2_CURATED_COMPOSITIONS)
        # First `num_curated` seeds map to curated, rest are random
        curated_idx = seed % (num_curated + 10)  # +10 gives room for random picks

        if curated_idx < num_curated:
            transforms = list(TIER2_CURATED_COMPOSITIONS[curated_idx])
        else:
            # Random composition: 2 or 3 transforms
            num_transforms = rng.choice([2, 2, 2, 3])  # 75% two, 25% three
            transforms = [rng.choice(_COMPOSABLE_TRANSFORMS) for _ in range(num_transforms)]

        # Determine if we need a square grid
        force_square = _needs_square_grid(transforms)

        # Pick grid size: 3x3 to 6x6
        rows, cols = _pick_grid_size_range(rng, 3, 6, force_square=force_square)

        # Pick number of colors (2-5)
        num_colors = rng.randint(2, 5)

        # Generate input grid
        input_grid = _generate_grid(rng, rows, cols, num_colors)

        # Apply transform chain
        chain_rng = random.Random(rng.randint(0, 2**32 - 1))
        expected_output = _apply_transform_chain(input_grid, transforms, chain_rng)

        # Output grid size
        out_rows = len(expected_output)
        out_cols = len(expected_output[0]) if out_rows > 0 else 0

        # Build IDs and description
        chain_label = "+".join(transforms)
        task_id = f"arc-t2-{seed:05d}-{chain_label}"

        descs = [_TRANSFORM_DESCRIPTIONS.get(t, t) for t in transforms]
        description = (
            f"Compositional: {' then '.join(descs)} "
            f"({rows}x{cols} -> {out_rows}x{out_cols})"
        )

        return {
            "task_id": task_id,
            "description": description,
            "input_grid": input_grid,
            "expected_output": expected_output,
            "transform_type": chain_label,
            "transforms": transforms,
            "grid_size": {"rows": rows, "cols": cols},
            "seed": seed,
            "tier": 2,
        }

    def generate_tier2_catalog(self, count: int = 50, base_seed: int = 2000) -> list[dict]:
        """Generate a catalog of Tier 2 compositional tasks.

        Seeds used: base_seed, base_seed+1, ..., base_seed+count-1
        """
        return [self.generate_tier2(base_seed + i) for i in range(count)]

    # -----------------------------------------------------------------------
    # Tier 3 — Relational/object tasks
    # -----------------------------------------------------------------------

    def generate_tier3(self, seed: int) -> dict:
        """Generate one Tier 3 (relational/object) ARC task from a seed.

        Creates tasks requiring object-level reasoning: connected components,
        color counting, enclosed region filling, pattern duplication, border
        extraction, and majority color filling.

        Grid sizes: 4x4 to 8x8.
        Task ID format: arc-t3-{seed:05d}-{transform_type}

        Example (seed=5000, task_type=extract_border):
            Generates a 5x5 grid, keeps only border cells and zeros the interior.

        Returns:
            dict with keys: task_id, description, input_grid, expected_output,
                            transform_type, grid_size, seed, tier
        """
        rng = random.Random(seed)

        # Pick task type
        task_type = TIER3_TASK_TYPES[seed % len(TIER3_TASK_TYPES)]

        # Pick grid size: 4x4 to 8x8 (5x5 to 8x8 for fill_enclosed)
        min_dim = 5 if task_type == "fill_enclosed" else 4
        rows, cols = _pick_grid_size_range(rng, min_dim, 8)

        # Pick number of colors (2-5 for most, ensure at least 2 non-zero)
        num_colors = rng.randint(3, 5)

        # Generate input grid
        input_grid = _generate_grid(rng, rows, cols, num_colors)

        # For fill_enclosed, we need to engineer a grid with an enclosed region
        if task_type == "fill_enclosed":
            input_grid = self._make_enclosure_grid(rng, rows, cols)

        # For largest_object_moves, ensure there are distinct objects
        if task_type == "largest_object_moves":
            input_grid = self._make_objects_grid(rng, rows, cols)

        # Apply the tier 3 transform
        transform_rng = random.Random(rng.randint(0, 2**32 - 1))
        transform_fn = _TIER3_TRANSFORM_FN[task_type]
        expected_output = transform_fn(input_grid, transform_rng)

        # Output grid size
        out_rows = len(expected_output)
        out_cols = len(expected_output[0]) if out_rows > 0 else 0

        # Build IDs and description
        task_id = f"arc-t3-{seed:05d}-{task_type}"
        base_desc = _TIER3_DESCRIPTIONS[task_type]
        description = f"{base_desc} ({rows}x{cols} -> {out_rows}x{out_cols})"

        return {
            "task_id": task_id,
            "description": description,
            "input_grid": input_grid,
            "expected_output": expected_output,
            "transform_type": task_type,
            "grid_size": {"rows": rows, "cols": cols},
            "seed": seed,
            "tier": 3,
        }

    @staticmethod
    def _make_enclosure_grid(rng: random.Random, rows: int, cols: int) -> Grid:
        """Generate a grid guaranteed to have at least one enclosed zero region.

        Strategy: fill a rectangular ring of non-zero cells with zeros inside,
        and leave the outer region as zeros (border-touching, not enclosed).

        Requires rows >= 5 and cols >= 5 so a 3x3 ring (with 1x1 interior)
        can be placed at least 1 cell away from every border.

        Example (6x6):
            [[0, 0, 0, 0, 0, 0],
             [0, 2, 2, 2, 2, 0],
             [0, 2, 0, 0, 2, 0],   <- enclosed 0s at (2,2), (2,3), (3,2), (3,3)
             [0, 2, 0, 0, 2, 0],
             [0, 2, 2, 2, 2, 0],
             [0, 0, 0, 0, 0, 0]]
        """
        # Enforce minimum size for enclosure viability
        rows = max(rows, 5)
        cols = max(cols, 5)

        grid: Grid = [[0] * cols for _ in range(rows)]
        wall_color = rng.randint(1, MAX_COLOR)

        # Ring top-left: (r1, c1), bottom-right: (r2, c2)
        # Constraints:
        #   r1 >= 1       (1 cell from top border)
        #   r2 <= rows-2  (1 cell from bottom border)
        #   r2 >= r1 + 2  (at least 1 interior row)
        #   c1 >= 1, c2 <= cols-2, c2 >= c1 + 2 (same for cols)
        #
        # Valid r1 range: [1, rows - 4]  (because r2 >= r1+2 and r2 <= rows-2)
        # Valid c1 range: [1, cols - 4]
        r1 = rng.randint(1, rows - 4)
        c1 = rng.randint(1, cols - 4)

        # r2 in [r1+2, rows-2], c2 in [c1+2, cols-2]
        r2 = rng.randint(r1 + 2, rows - 2)
        c2 = rng.randint(c1 + 2, cols - 2)

        # Draw the ring
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if r == r1 or r == r2 or c == c1 or c == c2:
                    grid[r][c] = wall_color

        # Scatter some non-zero cells outside the ring for variety
        for _ in range(rows * cols // 4):
            sr, sc = rng.randint(0, rows - 1), rng.randint(0, cols - 1)
            # Only place outside the ring interior
            if not (r1 < sr < r2 and c1 < sc < c2):
                if grid[sr][sc] == 0 and rng.random() < 0.3:
                    grid[sr][sc] = rng.randint(1, MAX_COLOR)

        return grid

    @staticmethod
    def _make_objects_grid(rng: random.Random, rows: int, cols: int) -> Grid:
        """Generate a grid with distinct colored objects (connected components).

        Places 2-4 rectangular blobs of different colors on a zero background.

        Example (5x5):
            [[0, 0, 0, 0, 0],
             [0, 2, 2, 0, 0],
             [0, 2, 0, 0, 0],
             [0, 0, 0, 3, 3],
             [0, 0, 0, 3, 0]]
        """
        grid: Grid = [[0] * cols for _ in range(rows)]
        num_objects = rng.randint(2, min(4, (rows * cols) // 4))
        used_colors: set[int] = set()

        for _ in range(num_objects):
            # Pick a unique non-zero color
            color = rng.randint(1, MAX_COLOR)
            attempts = 0
            while color in used_colors and attempts < 20:
                color = rng.randint(1, MAX_COLOR)
                attempts += 1
            used_colors.add(color)

            # Random rectangle placement
            obj_h = rng.randint(1, max(1, rows // 3))
            obj_w = rng.randint(1, max(1, cols // 3))
            start_r = rng.randint(0, rows - obj_h)
            start_c = rng.randint(0, cols - obj_w)

            for r in range(start_r, start_r + obj_h):
                for c in range(start_c, start_c + obj_w):
                    grid[r][c] = color

        return grid

    def generate_tier3_catalog(self, count: int = 50, base_seed: int = 5000) -> list[dict]:
        """Generate a catalog of Tier 3 relational/object tasks.

        Seeds used: base_seed, base_seed+1, ..., base_seed+count-1
        """
        return [self.generate_tier3(base_seed + i) for i in range(count)]

    # -----------------------------------------------------------------------
    # Tier 4 — Holdout (mixed tiers, non-overlapping seed range)
    # -----------------------------------------------------------------------

    def generate_holdout(self, seed: int) -> dict:
        """Generate one holdout task from a mixed distribution.

        Distribution: 40% Tier 1, 40% Tier 2, 20% Tier 3.
        Uses seed range base_seed=10000+ to avoid overlap with dev/validation.

        Task ID format: arc-holdout-{seed:05d}-{type}

        Returns:
            dict with keys matching the selected tier, plus tier and holdout flag.
        """
        rng = random.Random(seed)
        roll = rng.random()

        if roll < 0.4:
            # Tier 1
            task = self.generate(seed)
            tier_label = "t1"
        elif roll < 0.8:
            # Tier 2
            task = self.generate_tier2(seed)
            tier_label = "t2"
        else:
            # Tier 3
            task = self.generate_tier3(seed)
            tier_label = "t3"

        # Override task_id to holdout format
        original_type = task.get("transform_type", "unknown")
        task["task_id"] = f"arc-holdout-{seed:05d}-{tier_label}-{original_type}"
        task["holdout"] = True

        return task

    def generate_holdout_catalog(self, count: int = 50, base_seed: int = 10000) -> list[dict]:
        """Generate a catalog of holdout tasks (mixed tiers).

        Seeds used: base_seed, base_seed+1, ..., base_seed+count-1
        These seeds MUST NOT overlap with Tier 1/2/3 dev seeds.
        """
        return [self.generate_holdout(base_seed + i) for i in range(count)]

    # -----------------------------------------------------------------------
    # Full benchmark and verification
    # -----------------------------------------------------------------------

    def generate_full_benchmark(self) -> dict:
        """Generate the complete 200-task benchmark set grouped by tier.

        Returns:
            {"tier1": [...50 tasks], "tier2": [...50], "tier3": [...50], "holdout": [...50]}
        """
        return {
            "tier1": self.generate_catalog(count=50, base_seed=42),
            "tier2": self.generate_tier2_catalog(count=50, base_seed=2000),
            "tier3": self.generate_tier3_catalog(count=50, base_seed=5000),
            "holdout": self.generate_holdout_catalog(count=50, base_seed=10000),
        }

    @staticmethod
    def verify_task(task: dict) -> dict:
        """Verify a single task: feeding expected_output through the verifier must score 1.0.

        Returns:
            {"task_id": str, "passed": bool, "score": float, "error": str | None}
        """
        from swarmchain.services.verifier import ARCVerifier

        verifier = ARCVerifier()
        result = verifier.verify(
            task_payload={"expected_output": task["expected_output"]},
            attempt_output={"grid": task["expected_output"]},
        )
        return {
            "task_id": task["task_id"],
            "passed": result["score"] == 1.0,
            "score": result["score"],
            "error": result["details"].get("error") if not result["valid"] else None,
        }

    def verify_catalog(self, catalog: list[dict]) -> dict:
        """Verify every task in a catalog passes self-verification.

        Every generated task MUST score 1.0 when its expected_output is submitted
        as the attempt. This catches grid corruption, empty grids, and dimension
        mismatches.

        Returns:
            {
                "total": int,
                "passed": int,
                "failed": int,
                "failures": [{"task_id": ..., "score": ..., "error": ...}, ...]
            }
        """
        results = [self.verify_task(task) for task in catalog]
        failures = [r for r in results if not r["passed"]]
        return {
            "total": len(results),
            "passed": len(results) - len(failures),
            "failed": len(failures),
            "failures": failures,
        }
