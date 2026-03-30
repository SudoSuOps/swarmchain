# SwarmChain Architecture

## Core Mission

SwarmChain is a distributed reasoning ledger where nodes submit **attempts**, not answers. Attempts are scored, pruned, traced, and promoted. When a solution reaches finality, the block is sealed.

The asset is not just the answer — it is the solved set, the search lineage, the elimination history, the compute quality, the efficiency of convergence, and the contributor reward allocation.

## Design Principles

1. **Deterministic verification beats model opinion** whenever possible
2. **Models may assist finality**, but never override failed objective verification
3. **Nodes are rewarded for useful search**, not mere participation
4. **Failed attempts are not discarded** if they contain useful elimination signal
5. **Finality must be explicit**: solved, exhausted, or inconclusive
6. **Every attempt is traceable**
7. **Every sealed block is reproducible** from its stored data

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                  SwarmChain Backend                   │
│                   (FastAPI + Async)                   │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │  Block    │  │ Attempt  │  │   Node           │   │
│  │  API      │  │ Gateway  │  │   Registry       │   │
│  └────┬─────┘  └────┬─────┘  └──────────────────┘   │
│       │              │                                │
│  ┌────▼──────────────▼───────────────────────────┐   │
│  │              Controller Loop                   │   │
│  │  prune → promote → finality check → seal      │   │
│  └────┬──────────────┬───────────────────────────┘   │
│       │              │                                │
│  ┌────▼─────┐  ┌─────▼──────┐  ┌────────────────┐   │
│  │ Verifier │  │  Reward    │  │   Lineage      │   │
│  │ (ARC)    │  │  Engine    │  │   Store        │   │
│  └──────────┘  └────────────┘  └────────────────┘   │
│                                                       │
│  ┌───────────────────────────────────────────────┐   │
│  │           PostgreSQL + SQLAlchemy              │   │
│  │  blocks | attempts | nodes | rewards | lineage │   │
│  └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Node       │     │   Node       │     │   Node       │
│   Simulator  │────▶│   Simulator  │────▶│   Simulator  │
│   (jetmini)  │     │   (mid-gpu)  │     │   (queen)    │
└──────────────┘     └──────────────┘     └──────────────┘

┌─────────────────────────────────────────────────────┐
│              Block Explorer (React)                   │
│  Block List → Block Detail → Lineage → Rewards       │
└─────────────────────────────────────────────────────┘
```

## Component Details

### Controller
The orchestrator. Runs a background loop that processes all open blocks:
- Ranks attempts by score
- Promotes top N (beam width) candidates
- Prunes below-threshold attempts
- Checks finality conditions (solved at score 1.0, exhausted at limits)
- Triggers reward computation and block sealing

### Attempt Gateway
Accepts node submissions via POST /attempts. Each attempt is immediately scored by the domain verifier. Lineage edges are recorded if the attempt derives from a parent.

### Verifier
Deterministic scoring engine. For ARC MVP: exact cell-by-cell comparison.
- Score 1.0 = exact match (solved)
- Score 0.0-0.99 = partial match (proportion of correct cells)
- Invalid = dimension mismatch or malformed output

Pluggable interface (`DomainVerifier`) for future domains.

### Lineage Store
Tracks the parent-child attempt graph. Supports:
- Forward traversal (descendants)
- Backward traversal (ancestry to root)
- Full graph retrieval for visualization
- Winning lineage extraction

### Reward Engine
Weighted distribution based on contribution impact:
- **40% Solver**: node that produced the verified solution
- **30% Lineage**: ancestors in the winning path, weighted by score
- **20% Exploration**: high-scoring non-winning attempts
- **10% Efficiency**: best score-per-energy ratio

No reward for junk below minimum contribution threshold.

### Finality Service
Determines when a block is done:
- **Solved**: verified attempt reaches score 1.0
- **Exhausted**: max attempts or time limit reached
- Seals the block with artifacts, elimination summary, and reward distribution

## Data Model

Six core entities: `blocks`, `attempts`, `nodes`, `rewards`, `lineage_edges`, `block_artifacts`.

See `backend/swarmchain/db/models.py` for full schema.

## Block Lifecycle

```
OPEN → [attempts submitted] → [controller prunes/promotes]
     → SOLVED (score 1.0 verified)
     → EXHAUSTED (limits reached)
     → [rewards computed] → [artifact sealed]
```

## Future Domain Routing

The `DomainVerifier` interface supports pluggable domain validators:

```python
class DomainVerifier(ABC):
    def verify(self, task_payload, attempt_output) -> dict: ...
    def suggest_repair(self, task_payload, attempt_output) -> dict | None: ...
```

Planned domains:
- **CRE** → Atlas validator
- **Capital Markets** → Swarm Capital 27B validator
- **Legal** → Resolve validator

Domain models assist convergence but never override objective verification.
