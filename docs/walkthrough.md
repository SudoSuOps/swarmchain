# SwarmChain Walkthrough: Solving a Block

This document walks through a complete block lifecycle — from task creation to sealed artifact.

## Task: ARC-002 Mirror Horizontal

**Input grid:**
```
1 0 0
1 1 0
1 1 1
```

**Expected output:**
```
0 0 1
0 1 1
1 1 1
```

## Step 1: Open the Block

```bash
curl -X POST http://localhost:8000/blocks/open \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "arc-002-mirror-h",
    "domain": "arc",
    "reward_pool": 100.0,
    "max_attempts": 200,
    "time_limit_sec": 3600
  }'
```

Response: block created with status "open", block_id assigned.

## Step 2: Nodes Submit Attempts

### Attempt 1: jetmini submits random grid (score: 0.22)
```json
{
  "node_id": "jetmini-001",
  "block_id": "<block_id>",
  "method": "random_grid",
  "strategy_family": "random",
  "output_json": {"grid": [[3,1,0],[0,2,1],[1,0,3]]},
  "energy_cost": 0.2
}
```
Verifier scores: 2/9 cells correct = 0.222. Valid but low.

### Attempt 2: zima submits mirror_h (score: 1.0!)
```json
{
  "node_id": "zima-001",
  "block_id": "<block_id>",
  "method": "mirror_h",
  "strategy_family": "structured",
  "output_json": {"grid": [[0,0,1],[0,1,1],[1,1,1]]},
  "energy_cost": 0.5
}
```
Verifier scores: 9/9 cells correct = 1.0. **Exact match!**

## Step 3: Controller Detects Solution

The controller loop (runs every 5 seconds):
1. Finds the open block
2. Checks for solved → finds attempt with score 1.0
3. Marks block as **solved**
4. Sets winning_attempt_id and winning_node_id

## Step 4: Finalization

The controller triggers finalization:

### Reward computation:
- **Solver (40%)**: zima-001 gets 40.0 for producing the solution
- **Lineage (30%)**: No ancestors in this case (direct solve)
- **Exploration (20%)**: jetmini-001 gets 20.0 for its valid attempt
- **Efficiency (10%)**: Split based on score/energy ratio
  - zima: 1.0/0.5 = 2.0 efficiency
  - jetmini: 0.222/0.2 = 1.11 efficiency
  - zima gets ~6.4, jetmini gets ~3.6

### Elimination summary:
```json
{
  "total_attempts": 2,
  "total_energy": 0.7,
  "avg_score": 0.611,
  "max_score": 1.0,
  "pruned_count": 0,
  "promoted_count": 2
}
```

## Step 5: Sealed Artifact

The block artifact captures the complete record:
```json
{
  "block_id": "abc123",
  "task_id": "arc-002-mirror-h",
  "domain": "arc",
  "status": "solved",
  "final_score": 1.0,
  "winning_attempt_id": "attempt-002",
  "winning_node_id": "zima-001",
  "elimination_summary": { ... },
  "winning_lineage": [
    {"attempt_id": "attempt-002", "node_id": "zima-001", "score": 1.0}
  ],
  "contributing_nodes": ["jetmini-001", "zima-001"],
  "sealed_at": "2026-03-26T..."
}
```

## Key Observations

1. **Search became data**: Both the failed and successful attempts are recorded
2. **Elimination became integrity**: The random attempt was valid but low-scoring — it proved what doesn't work
3. **Finality created value**: The sealed block is a verified, reproducible dataset artifact
4. **Impact was rewarded**: The solver got the most, but the explorer also earned for contributing
5. **Efficiency mattered**: The solver's better score-per-energy ratio earned an efficiency bonus

## Running the Full Simulation

```bash
# Start services
make up

# Run the simulator (20 rounds of 4 nodes across 8 ARC tasks)
python simulator/simulator.py --rounds 20

# View results in the block explorer
open http://localhost:3000
```
