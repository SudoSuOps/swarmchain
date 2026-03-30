"""ARC-style task definitions for MVP.

Simple deterministic grid transformation tasks — verification is exact.
These seed the system for demo and testing.
"""

# Each task has an input grid and expected output grid.
# Colors: 0=black, 1=blue, 2=red, 3=green, 4=yellow, 5=gray,
#         6=magenta, 7=orange, 8=cyan, 9=maroon

SAMPLE_TASKS = [
    {
        "task_id": "arc-001-fill-blue",
        "description": "Fill all zeros with blue (1)",
        "input_grid": [
            [0, 0, 0],
            [0, 2, 0],
            [0, 0, 0],
        ],
        "expected_output": [
            [1, 1, 1],
            [1, 2, 1],
            [1, 1, 1],
        ],
    },
    {
        "task_id": "arc-002-mirror-h",
        "description": "Mirror the grid horizontally",
        "input_grid": [
            [1, 0, 0],
            [1, 1, 0],
            [1, 1, 1],
        ],
        "expected_output": [
            [0, 0, 1],
            [0, 1, 1],
            [1, 1, 1],
        ],
    },
    {
        "task_id": "arc-003-rotate-90",
        "description": "Rotate the grid 90 degrees clockwise",
        "input_grid": [
            [1, 2],
            [3, 4],
        ],
        "expected_output": [
            [3, 1],
            [4, 2],
        ],
    },
    {
        "task_id": "arc-004-color-swap",
        "description": "Swap colors: 1 becomes 2, 2 becomes 1",
        "input_grid": [
            [1, 1, 2],
            [2, 1, 2],
            [1, 2, 1],
        ],
        "expected_output": [
            [2, 2, 1],
            [1, 2, 1],
            [2, 1, 2],
        ],
    },
    {
        "task_id": "arc-005-border",
        "description": "Add a border of 3s around the pattern",
        "input_grid": [
            [1, 2],
            [2, 1],
        ],
        "expected_output": [
            [3, 3, 3, 3],
            [3, 1, 2, 3],
            [3, 2, 1, 3],
            [3, 3, 3, 3],
        ],
    },
    {
        "task_id": "arc-006-transpose",
        "description": "Transpose the grid (swap rows and columns)",
        "input_grid": [
            [1, 2, 3],
            [4, 5, 6],
        ],
        "expected_output": [
            [1, 4],
            [2, 5],
            [3, 6],
        ],
    },
    {
        "task_id": "arc-007-invert",
        "description": "Invert: 0 becomes 1, anything else becomes 0",
        "input_grid": [
            [0, 3, 0],
            [3, 0, 3],
            [0, 3, 0],
        ],
        "expected_output": [
            [1, 0, 1],
            [0, 1, 0],
            [1, 0, 1],
        ],
    },
    {
        "task_id": "arc-008-scale-2x",
        "description": "Scale the grid 2x (each cell becomes a 2x2 block)",
        "input_grid": [
            [1, 2],
            [3, 4],
        ],
        "expected_output": [
            [1, 1, 2, 2],
            [1, 1, 2, 2],
            [3, 3, 4, 4],
            [3, 3, 4, 4],
        ],
    },
]


def get_task(task_id: str) -> dict | None:
    """Look up a task by ID."""
    for t in SAMPLE_TASKS:
        if t["task_id"] == task_id:
            return t
    return None


def get_task_payload(task_id: str) -> dict:
    """Build the task payload for block creation."""
    task = get_task(task_id)
    if not task:
        return {}
    return {
        "input_grid": task["input_grid"],
        "expected_output": task["expected_output"],
        "description": task["description"],
    }


def list_tasks() -> list[dict]:
    """Return summary of all available tasks."""
    return [
        {"task_id": t["task_id"], "description": t["description"]}
        for t in SAMPLE_TASKS
    ]
