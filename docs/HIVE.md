# The Hive — 50 Role-Based Bees on One CPU

**Not 50 miners doing the same thing. 50 bees with jobs.**

A real hive has division of labor. Foragers, nurses, guards, scouts, the queen. They don't all do the same work. The hive converges because each bee has a role.

SwarmChain's hive works the same way.

---

## The Hardware Nobody Thinks About

```
Intel Xeon w9-3475X
  36 cores / 72 threads
  256GB DDR5 (8 channels, ~300+ GB/s bandwidth)
  Intel AMX — hardware INT8/BF16 matrix acceleration
  Intel DL Boost (VNNI) — vector neural network instructions
  Max supported: 4TB RAM
  TDP: 250W for the ENTIRE hive
```

This isn't a GPU host. It's an AI accelerator hiding in plain sight. AMX gives it built-in tensor operations — matrix multiply in hardware, on the CPU, no GPU required.

With AMX-optimized inference, a 3B model runs at ~40-60 tok/s per instance. Standard CPU inference does ~15 tok/s. Same silicon. Same watts. 3-4x faster.

---

## The 50-Bee Hive

```
┌─────────────────────────────────────────────────────┐
│  PROPOSERS (15 bees)                                │
│  Submit raw attempts against the current block      │
│  3B Q4, AMX INT8, ~40 tok/s each                    │
│  Role: generate candidate solutions FAST            │
│  Total RAM: ~45GB                                   │
├─────────────────────────────────────────────────────┤
│  SCORERS (5 bees)                                   │
│  Verify proposer outputs against ground truth       │
│  2B INT8, deterministic scoring                     │
│  Role: honey/jelly/propolis in real-time            │
│  Total RAM: ~12GB                                   │
├─────────────────────────────────────────────────────┤
│  REJECTORS (5 bees)                                 │
│  Pattern-match against known failure modes          │
│  2B INT8, trained on propolis data                  │
│  Role: kill dead-end strategies before they waste   │
│  Total RAM: ~12GB                                   │
├─────────────────────────────────────────────────────┤
│  REPAIRERS (10 bees)                                │
│  Take jelly (0.30-0.95) and try to fix it           │
│  3B Q4, fed the near-miss + the gap analysis        │
│  Role: push 0.750 → 1.000                          │
│  Total RAM: ~30GB                                   │
├─────────────────────────────────────────────────────┤
│  IDLERS (10 bees)                                   │
│  Dormant until a proposer gets promoted             │
│  Spin up on demand for Phase 2/3 escalation         │
│  Role: burst capacity, zero energy when idle        │
│  Total RAM: ~0GB idle, ~30GB when activated         │
├─────────────────────────────────────────────────────┤
│  AUDITORS (5 bees)                                  │
│  SwarmRefinery micro — validate the process         │
│  2B INT8, protocol-knowledge trained                │
│  Role: real-time audit, flag anomalies              │
│  Total RAM: ~12GB                                   │
├─────────────────────────────────────────────────────┤
│  TOTAL: ~125-150GB active / 256GB available         │
│  100GB headroom for OS + orchestration + KV cache   │
└─────────────────────────────────────────────────────┘
```

---

## The Memory Math

```
BitNet 2B at INT8:     ~2.0GB per instance
3B at Q4_K_M:          ~2.5GB per instance
KV cache (2K context): ~0.3GB per instance
Runtime overhead:      ~0.2GB per instance

Per bee:               ~2.5-3.0GB
50 bees:               ~125-150GB
Available RAM:         256GB
Headroom:              100-130GB

VERDICT: Fits. With room to spare.
```

---

## How the Hive Processes a Block

A block opens. The task enters the hive.

```
SECOND 0-5: PROPOSAL WAVE
  15 proposers attack the task simultaneously
  Each one generates a candidate solution
  Throughput: 15 × 40 tok/s = 600 tok/s combined
  In 5 seconds: 15 raw attempts ready for scoring

SECOND 5-8: SCORING WAVE
  5 scorers verify all 15 proposals
  Deterministic grid match — no model opinion
  Results: 3 propolis (< 0.30), 9 jelly (0.30-0.95), 3 honey candidates (> 0.95)

SECOND 8-10: REJECTION WAVE
  5 rejectors analyze the 3 propolis attempts
  Pattern match: "this strategy always fails on color_remap"
  Signal broadcast: all proposers avoid this approach next round

SECOND 10-20: REPAIR WAVE
  10 repairers take the 9 jelly attempts
  Each repairer gets: the jelly output + the gap analysis + the task
  Goal: push 0.750 → 1.000
  Repairers produce 10 refined attempts

SECOND 20-25: SECOND SCORING
  5 scorers verify the 10 repaired attempts
  Results: 2 honey (1.000), 5 improved jelly, 3 still jelly

SECOND 25-30: AUDIT
  5 auditors verify the full cycle
  Lineage traced: proposer → scorer → repairer → scorer
  Cost computed: total energy for this block
  Quality confirmed: honey is real, scores are deterministic

SECOND 30: SEAL
  Block finalized. 2 honey. Full provenance.
  25 attempts processed. 50 bees participated.
  Total CPU time: 30 seconds at 250W.
  Total energy cost: ~$0.002
```

---

## Division of Labor vs Brute Force

```
BRUTE FORCE (traditional):
  50 identical miners
  50 identical attempts
  Same strategies, same failures
  High redundancy, low signal
  50 × same wrong answer = waste

DIVISION OF LABOR (the hive):
  15 propose (generate)
  5 score (verify)
  5 reject (eliminate)
  10 repair (improve)
  10 idle (reserve)
  5 audit (certify)
  Each role feeds the next
  Failures become signal
  Signal becomes repair
  Repair becomes honey
```

The brute force swarm throws bodies at the problem.
The hive **processes** the problem through stages.

---

## The Block Lifecycle Through the Hive

```
    ┌──────────┐
    │  TASK    │ ← block opens
    └────┬─────┘
         │
    ┌────▼─────┐
    │ PROPOSE  │ ← 15 bees generate candidates
    └────┬─────┘
         │ 15 raw attempts
    ┌────▼─────┐
    │  SCORE   │ ← 5 bees verify deterministically
    └────┬─────┘
         │ honey / jelly / propolis
    ┌────▼─────┐     ┌──────────┐
    │  REJECT  │────→│ DEAD END │ ← 5 bees kill bad strategies
    └────┬─────┘     └──────────┘
         │ surviving jelly
    ┌────▼─────┐
    │  REPAIR  │ ← 10 bees fix near-misses
    └────┬─────┘
         │ refined attempts
    ┌────▼─────┐
    │  SCORE   │ ← 5 bees verify repairs
    └────┬─────┘
         │ honey confirmed
    ┌────▼─────┐
    │  AUDIT   │ ← 5 bees certify the process
    └────┬─────┘
         │
    ┌────▼─────┐
    │  SEAL    │ ← block finalized with full provenance
    └──────────┘
```

---

## Why This Works

**Nature already solved this.**

In a real bee colony:
- Scout bees find flower patches (PROPOSERS)
- Guard bees check returning foragers (SCORERS)
- Undertaker bees remove dead bees (REJECTORS)
- Nurse bees feed and repair larvae (REPAIRERS)
- Reserve bees wait for the waggle dance (IDLERS)
- The queen inspects cells (AUDITORS)

No bee does everything. The hive works because each bee does ONE thing well. The colony-level intelligence emerges from the division of labor.

SwarmChain's hive is the same architecture, running on silicon instead of biology.

---

## The Economics

```
50 bees on Xeon AMX:
  Power: 250W total (the CPU TDP)
  Cost:  $0.075/hr at $0.30/kWh
  Throughput: 600+ tok/s combined (proposers alone)

  Blocks per hour: ~120 (30s per block)
  Honey per hour: ~165 (1.38/block × 120)
  Cost per honey: $0.075 / 165 = $0.00045

  ZERO GPU COST. All CPU. All AMX.

For comparison:
  1× RTX 6000 running 9B:
  Power: 350W
  Cost:  $0.105/hr
  Honey per hour: ~90 (1.38/block × 65 blocks)
  Cost per honey: $0.105 / 90 = $0.00117

  The CPU hive produces 2x more honey at 0.4x the cost.
```

**Efficiency is king. The hive is the most efficient miner in the fleet.**

---

## The Full Fleet

```
XEON HIVE (256GB, AMX):        50 role-bees — the factory floor
RTX PRO 4500 (32GB):           Johanna (SwarmJelly 4B) — the failure expert
RTX PRO 6000 (96GB):           Katniss (9B) — the closer (or cooking)
5× DGX Spark (128GB each):     Specialists + SwarmRefinery ops brain
RTX 3090 Ti (24GB):            Finnick (7B) — domain specialist
Jetson Orin (8GB):             Rue — the edge scout

The hive runs the volume. The GPUs run the closers.
The Sparks run the specialists. The Jetson runs the edge.
SwarmRefinery runs the operation.

Total fleet: 50+ CPU bees + 8 GPU/Spark nodes + edge
Total power: ~1,200W for the entire operation
```

---

## The One-Liner

**50 bees. Not 50 miners. A hive with division of labor — proposers, scorers, rejectors, repairers, reserves, auditors. All on one CPU. 250 watts. $0.00045 per honey.**

*Nature designed the swarm. We built it in silicon.*
