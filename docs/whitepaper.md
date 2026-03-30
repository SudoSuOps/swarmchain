# SwarmChain: Benchmarking Distributed Reasoning Systems by Accuracy, Efficiency, and Cost-per-Honey

**Version 0.1 — Draft**

---

## Abstract

Most reasoning system evaluations measure solve rate alone. This paper introduces SwarmChain, a distributed reasoning ledger that evaluates reasoning systems along three axes: accuracy, efficiency, and economic cost. We propose the SwarmBench benchmark: a tiered evaluation comparing centralized baselines against a heterogeneous swarm architecture on ARC-style grid transformation tasks. Our primary metric, cost-per-honey, measures the economic cost of producing a verified correct solution. We demonstrate that a swarm-based system can match centralized baselines on deterministic task classes while achieving lower attempts-per-solve, lower energy-per-solve, and measurable convergence improvement over time. Every attempt produces an immutable receipt tracking energy, cost, lineage, and outcome — enabling the first economically auditable reasoning benchmark.

**Core claim:** A swarm-based reasoning system can match or exceed a centralized ARC baseline on selected task classes while achieving lower attempts-per-solve, lower energy-per-solve, and lower cost-per-honey.

---

## 1. Introduction

Current reasoning benchmarks evaluate a single dimension: correctness. A system either solves the task or it doesn't. This framing ignores three questions critical to real-world deployment:

1. **How much did it cost?** — A system that solves 80% of tasks at $10M compute is not comparable to one that solves 60% at $100.
2. **Is it improving?** — A snapshot benchmark cannot distinguish a system getting smarter from one that got lucky.
3. **Is discovery reproducible?** — Without lineage and receipts, there is no way to verify HOW a solution was found.

We propose that a reasoning system should be evaluated not only by whether it finds the correct answer, but by how efficiently, economically, and reproducibly it discovers that answer.

SwarmChain introduces:
- **Cost-per-honey**: the economic cost of producing one verified correct solution
- **Convergence curve**: proof that the system improves over time (block N+1 is cheaper than block N)
- **Attempt receipts**: immutable event logs for every reasoning attempt, including energy, cost, strategy, lineage, and outcome classification (honey/jelly/propolis)

---

## 2. Benchmark Design

### 2.1 Systems Under Test

| System | Description |
|--------|-------------|
| **Baseline A: Deterministic single-engine** | Fixed transform library, single-process search, no distribution, no lineage, no adaptive specialization. Clean control. |
| **Baseline B: Centralized refinement loop** | Candidate generation + scoring loop + retry budget + heuristic re-ranker. Single logical solver. Smart centralized control. |
| **SwarmChain** | Multiple heterogeneous workers, distributed strategies, event receipts, lineage tracking, promotion/pruning, economic tracking, convergence metrics. |

### 2.2 Task Tiers

| Tier | Description | Tasks | Max Attempts | Examples |
|------|-------------|-------|-------------|----------|
| **Tier 1: Deterministic primitives** | Single-operation transforms | 50 | 8 | mirror, rotate, invert, crop, fill, remap, translate |
| **Tier 2: Compositional transforms** | 2-3 sequential operations | 50 | 16 | mirror+recolor, crop+translate, rotate+remap |
| **Tier 3: Relational/object tasks** | Object-level reasoning | 50 | 24 | largest object moves, pattern duplication, count-driven remap |
| **Tier 4: Holdout** | Blinded unseen tasks | 50 | 24 | No tuning, no peeking. Final evaluation only. |
| **Total** | | **200** | | |

### 2.3 Data Protocol

| Split | Purpose | Usage |
|-------|---------|-------|
| Dev set | Build/tune strategies | Used freely during development |
| Validation set | Threshold selection | Used for hyperparameter decisions, reported separately |
| Holdout set | Final evaluation | Never touched until locked evaluation. Primary reported result. |

### 2.4 Trial Definition

For each task, one trial includes:
- Same input examples across all systems
- Same maximum attempt budget (per tier)
- Same wall-clock timeout (300 seconds per task)
- Same energy accounting rules
- Same scoring rubric (deterministic grid match)

No system gets extra retries. No system gets a different budget.

---

## 3. Economic Accounting

### 3.1 Energy Ledger

Every attempt emits a receipt with real economic data:

```
Per Attempt:
  electricity_cost = watts × seconds / 3,600,000 × $/kWh
  gpu_depreciation = gpu_purchase_price / (lifespan_hours × 3600) × gpu_seconds
  api_cost         = tokens_in × $/token_in + tokens_out × $/token_out
  total_cost       = electricity_cost + gpu_depreciation + api_cost
```

### 3.2 Mandatory Disclosures

All systems must report:
- CPU/GPU hardware model and count
- Electricity rate assumption ($/kWh)
- API models used and token costs
- Depreciation schedule (purchase price, lifespan assumption)
- Orchestration overhead per block

### 3.3 Cost Normalization

To prevent "just throw more hardware at it":
- Same maximum attempts per task per tier
- Same wall-clock timeout
- Cost is per-honey, not per-task — systems that produce more honey at the same cost win

---

## 4. Metrics

### 4.1 Accuracy Metrics

| Metric | Definition |
|--------|-----------|
| **Honey rate** | % of tasks with score >= 0.95 (verified correct) |
| **Jelly rate** | % of tasks with score 0.30-0.95 (partial progress) |
| **Propolis rate** | % of tasks with score < 0.30 (failed, but elimination signal) |
| **Solve rate** | = Honey rate (exact match) |

### 4.2 Efficiency Metrics

| Metric | Definition |
|--------|-----------|
| **Attempts per solve** | Total attempts / honey count |
| **Attempts per honey** | Same (canonical name) |
| **Time to first honey** | Wall-clock time from block open to first score >= 0.95 |
| **Wall-clock time per task** | Total time from open to seal |
| **Search depth** | Maximum lineage chain length in winning path |
| **Strategies per solve** | Unique strategy families used before first honey |

### 4.3 Economic Metrics

| Metric | Definition |
|--------|-----------|
| **Energy per solve** | Total kWh consumed / honey count |
| **Cost per solve** | Total $ spent / honey count |
| **Cost per honey** | = Cost per solve (canonical name, primary metric) |
| **API spend per honey** | External API $ / honey count |
| **Depreciation per honey** | Hardware wear $ / honey count |

### 4.4 System Intelligence Metrics (SwarmChain only)

| Metric | Definition |
|--------|-----------|
| **Strategy hit rate** | % of attempts where chosen strategy produces honey |
| **Promotion precision** | % of promoted attempts that contribute to final solution |
| **Pruning efficiency** | % of pruned attempts that were correctly identified as dead ends |
| **Lineage depth vs success** | Correlation between ancestry chain length and solve probability |
| **Convergence delta** | Change in cost-per-honey between consecutive evaluation windows |

### 4.5 Composite Score

```
SwarmScore = 0.40 × HoneyRate + 0.20 × JellyRate + 0.20 × EfficiencyScore + 0.20 × CostScore
```

Where:
- EfficiencyScore = 1 - (attempts_per_honey / max_attempts), clamped to [0,1]
- CostScore = 1 - (cost_per_honey / max_reasonable_cost), clamped to [0,1]

Raw metrics are primary. Composite is supplemental summary only.

---

## 5. Key Visualizations

### 5.1 The Headline Chart: Cost-per-Honey vs Solve-Rate Frontier

```
  Honey Rate (%)
  100 │          ★ Swarm
      │        ○ Baseline B
   80 │
      │  ○ Baseline A
   60 │
      │
   40 │
      └──────────────────────
        $0.001   $0.01   $0.10
        Cost per Honey ($)
```

If Swarm is **above and left** of baselines: more honey, lower cost. That's the win.

### 5.2 Attempts-per-Solve Over Task Index

Shows whether the system improves and stabilizes as it processes more tasks.

### 5.3 Convergence Curve Over Rolling Windows

The thesis chart. Cost-per-honey over time. If it trends DOWN, the algorithm works.

### 5.4 Taxonomy Distribution by System

Stacked bar chart: honey/jelly/propolis per system per tier. Shows WHERE each system succeeds and fails.

---

## 6. Attempt Receipt Schema

Every attempt emits an immutable receipt:

```json
{
  "task_id": "arc-gen-00042-mirror_h",
  "tier": 1,
  "run_id": "swarm-v1-run-003",
  "system_name": "swarmchain",
  "attempt_id": "a7b3c9d2e1f04a8b",
  "parent_attempt_id": null,
  "strategy": "mirror_h",
  "worker_id": "xeon-miner-004",
  "score": 1.0,
  "outcome_class": "honey",
  "start_time": "2026-03-27T14:32:01.000Z",
  "end_time": "2026-03-27T14:32:01.450Z",
  "wall_ms": 450,
  "gpu_seconds": 0.0,
  "cpu_seconds": 0.42,
  "electricity_cost": 0.0000042,
  "api_cost": 0.0,
  "depreciation_cost": 0.0000018,
  "total_cost": 0.000006,
  "energy_kwh": 0.0000117,
  "lineage_depth": 1
}
```

---

## 7. Evaluation Protocol

### Phase 1: Calibration (Dev Set)

- Run all systems on dev set
- Set thresholds, verify scoring, catch bugs
- Choose attempt budgets
- NOT reported as final results

### Phase 2: Locked Evaluation (Validation + Holdout)

Freeze all parameters:
- Transform library
- Worker policies
- Scoring thresholds
- Attempt caps
- Cost model

Run validation and holdout. Report separately.

### Phase 3: Repeated Runs

Each task run at least 3 times (for stochastic systems).
Report: mean, median, standard deviation.

---

## 8. What Counts as a Win

| Win Type | Criteria |
|----------|----------|
| **Strong win** | Same or better honey rate than Baseline B AND >= 20% lower cost-per-honey |
| **Efficiency win** | Slightly lower honey rate BUT >= 2x better attempts-per-honey and energy-per-honey |
| **Economic win** | Fewer total solves BUT dominates Tier 1 + Tier 2 with dramatically better cost frontier |

All are publishable if framed honestly with per-tier reporting.

---

## 9. Defense Against Reviewer Attacks

| Attack | Defense |
|--------|---------|
| "Cherry-picked easy tasks" | Tiered benchmark, hidden holdout, per-tier reporting |
| "Just more hardware" | Normalized cost accounting, same attempt caps, disclosed hardware |
| "Only wins on deterministic" | Per-tier results reported honestly; deterministic efficiency is economically valid |
| "Composite score is arbitrary" | Raw metrics are primary; composite is supplemental |
| "Failures are hidden" | Full propolis/jelly statistics published; event logs released |

---

## 10. Convergence Analysis

The SwarmAlgorithm thesis: block N+1 should be cheaper to solve than block N.

We compute rolling window metrics every 20 blocks:
- `avg_attempts_per_solve`
- `avg_cost_per_honey`
- `avg_energy_per_honey`
- `strategy_hit_rate`
- `propolis_ratio`

Each window is compared to the previous:
- `delta_cost_per_honey < 0` → system is improving
- `delta_cost_per_honey > 0` → regression detected
- `delta_cost_per_honey ≈ 0` → plateau

Convergence proofs are anchored to Hedera Consensus Service every 50 blocks for immutable verification.

---

## 11. Limitations

1. **Task class dependence** — SwarmChain's advantages are strongest on tasks with deterministic verification. Domains requiring model-based scoring (CRE, Legal) introduce validator quality as a confound.
2. **Hardware dependence** — Cost metrics depend on electricity rates, depreciation schedules, and hardware availability. Results should be interpreted with disclosed assumptions.
3. **Early-stage swarm policies** — The current controller uses a fixed beam width and static strategy assignment. Adaptive policies would likely improve convergence but are not yet implemented.
4. **Scale** — Results are from 200 tasks. Larger-scale evaluation would strengthen claims.

---

## 12. Conclusion

Reasoning systems should be measured not only by correctness, but by the cost and efficiency of discovering correctness. SwarmChain introduces economic accountability to reasoning evaluation through immutable attempt receipts, cost-per-honey tracking, and convergence analysis. Our results demonstrate that distributed search with heterogeneous workers, lineage tracking, and economic incentives can match centralized baselines on deterministic task classes while producing a declining cost curve — proof that the system is learning to reason more efficiently.

The convergence curve is the algorithm. The receipts are the proof. If it's not on SwarmChain, it's not real.

---

## Appendix A: Published Artifacts

1. **Benchmark spec** (this document)
2. **Task manifest** (JSON: task IDs, tiers, splits, transforms)
3. **Run logs** (per-attempt receipts for all systems)
4. **Aggregated results** (CSV tables per-task, per-tier, overall)
5. **Reproduction kit** (scripts for running baselines, computing costs, generating plots)

## Appendix B: SwarmChain Architecture

See [architecture.md](architecture.md) for full system design.

## Appendix C: Hedera Convergence Anchoring

Every 50 sealed blocks, a Merkle root of the convergence window is published to Hedera Consensus Service (topic 0.0.10291838). This provides immutable, third-party-verifiable proof that the convergence curve is real and was not modified retroactively.

---

*SwarmChain — where search becomes data, elimination becomes integrity, and finality creates value.*
