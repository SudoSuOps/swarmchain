# Behavioral Evaluation — The Chain IS the Eval

**Benchmarks tell you if the answer was right. SwarmChain tells you what behavior got you there, what it cost, and where weaker paths died.**

---

## The Problem with Benchmarks

```
Traditional eval:
  Input → Model → Output → Score

  What you learn: "73% accuracy on MMLU"
  What you DON'T learn:
    - Why it got the wrong ones wrong
    - What strategies it tried
    - How much it cost per correct answer
    - Whether it improved over time
    - What other models tried on the same tasks
    - Where in its reasoning it broke
```

A score is a number. A number is not a diagnosis.

---

## What SwarmChain Captures That Benchmarks Don't

Every block in the chain produces a **behavioral trace** — not just a score, but the full story of how that score was reached.

```
BENCHMARK OUTPUT:
  Task: mirror_h+color_swap
  Model: base-9b
  Score: 0.82
  Result: FAIL (below 0.95 honey threshold)

SWARMCHAIN OUTPUT:
  Task: mirror_h+color_swap
  Block: #247

  Attempt 1: scout-0.5b    → 0.15  (propolis, 2 seconds, $0.00002)
  Attempt 2: scout-0.5b    → 0.20  (propolis, 2 seconds, $0.00002)
  Attempt 3: scout-1.5b    → 0.45  (jelly, 4 seconds, $0.0001)
  Attempt 4: scout-1.5b    → 0.42  (jelly, 4 seconds, $0.0001)
  → Router: ESCALATE_4B (scouts plateauing at 0.4x)
  Attempt 5: peeta-3b      → 0.65  (jelly, 12 seconds, $0.001)
  → Router: SEND_TO_REPAIR (gap 0.35, worth fixing)
  Attempt 6: peeta-3b      → 0.72  (jelly, 15 seconds, $0.001)
  → Critic: NOT_READY (+0.07, improving but not there)
  → Router: ESCALATE_9B
  Attempt 7: katniss-9b    → 0.82  (jelly, 25 seconds, $0.004)
  → Critic: NOT_READY (0.82, close but not honey)
  Attempt 8: katniss-9b    → 0.95  (honey candidate, 28 seconds, $0.004)
  → Filter: PASS
  → SEALED as honey

  Lineage: scout(0.45) → peeta(0.72) → katniss(0.95)
  Total cost: $0.0102
  Total time: 58 seconds
  Solve phase: Phase 3 (required 9B escalation)
  Behavioral insight: compositional tasks need GPU tier,
    scouts useful for initial search but plateau at 0.4x
```

**Same task. Same final score. But SwarmChain tells you the STORY.**

---

## Behavioral Pressure, Elimination, Convergence

SwarmChain doesn't just evaluate outputs. It evaluates **behavior under pressure**.

### Behavioral Pressure
Each bee is under economic pressure. Every token costs energy. Every second costs time. The bees that produce the most signal per dollar survive. The bees that waste energy get deprioritized.

### Elimination
Wrong paths don't just fail — they get KILLED and BROADCAST. When scout-0.5b scores 0.15, that's not just a failed attempt. It's a signal: "mirror_h alone doesn't work on this task." Every subsequent bee knows not to try that path. Elimination IS reasoning.

### Convergence
Over blocks, over epochs, the system learns. Cost-per-honey trends down. Solve rate trends up. The behavioral patterns that work get reinforced. The patterns that fail get eliminated. The chain doesn't just evaluate — it EVOLVES.

```
Benchmark:    static snapshot
SwarmChain:   dynamic convergence
```

---

## Eval Categories — Behavioral, Not Topical

Traditional benchmarks categorize by topic: math, code, language, reasoning.
SwarmChain categorizes by behavior:

| Behavior | What It Measures | How the Chain Captures It |
|----------|-----------------|--------------------------|
| Search coverage | Did scouts explore diverse paths? | Number of unique strategies per block |
| Escalation efficiency | Did the router escalate at the right time? | Phase where honey was found vs budget spent |
| Repair effectiveness | Did Peeta improve the score? | Delta between pre-repair and post-repair |
| Filter accuracy | Did filter correctly kill junk and pass viable? | False kill rate (killed something that was viable) |
| Convergence rate | Is the system getting better? | Cost-per-honey trend over 20-block windows |
| Lineage depth | How many bees contributed to the solve? | Length of the lineage chain |
| Energy ROI | Was the honey worth the energy? | Total block energy ÷ honey value |

**Each metric is automatically computed from the chain record. No separate eval framework needed.**

---

## The Ideal Trajectory

Every block has an ideal trajectory — the cheapest path to honey.

```
IDEAL (simple Tier 1 task):
  scout(0.95) → filter(PASS) → seal
  Cost: $0.0001 | Time: 5s | Phases: 1

IDEAL (medium Tier 1 task):
  scout(0.60) → peeta(0.85) → katniss(1.0) → seal
  Cost: $0.005 | Time: 30s | Phases: 3

IDEAL (hard Tier 2 task):
  scout(0.30) → escalate → peeta(0.65) → katniss(0.90) → retry → katniss(1.0) → seal
  Cost: $0.012 | Time: 90s | Phases: 4

WASTEFUL (any task):
  scout(0.10) → scout(0.12) → scout(0.11) → scout(0.13) → escalate too late →
  katniss(0.70) → katniss(0.75) → katniss(0.78) → exhausted
  Cost: $0.025 | Time: 120s | No honey
```

**The deviation from ideal trajectory IS the eval.** Every block that takes more steps, more energy, or more time than the ideal — that's a behavioral issue. Was the router too slow to escalate? Did scouts waste cycles on redundant strategies? Did Peeta fail to stabilize?

The chain answers all of these automatically. From the trace. With receipts.

---

## Self-Evaluating System

The key insight from behavioral eval research:

> "Every failure becomes an eval."

In SwarmChain, every failed block IS an eval:
- What was the task?
- What did each bee try?
- Where did the trajectory deviate?
- What was the cost of the deviation?
- How should the policy change?

SwarmRefinery reads these traces during Shift 2 (cooldown/audit) and generates recommendations for Shift 3 (prep). The system evaluates itself. Every epoch.

```
TRADITIONAL EVAL LOOP:
  Build agent → Run benchmark → Read score → Fix agent → Repeat

SWARMCHAIN EVAL LOOP:
  Mine epoch → Chain records everything → SwarmRefinery audits traces →
  Adjusts bee policy → Mine next epoch → Compare convergence →
  The system improves itself
```

No separate eval framework. No benchmark suite. No LLM-as-judge.
The chain IS the eval. The convergence IS the score.

---

## The Competitive Position

```
LangChain Deep Agents:   Behavioral evals in LangSmith (private traces)
LMSYS Arena:             Preference evals via crowdsource (subjective)
HuggingFace:             Static benchmarks (contaminated)

SwarmChain:              Behavioral evals ON-CHAIN (public, immutable, receipted)
                         Deterministic scoring (no judge)
                         Multi-model competition (not single-model)
                         Economic pressure (cost-aware)
                         Convergence tracking (improves over time)
                         Hedera-anchored (can't be faked)
```

They're building behavioral eval as a TOOL.
We're building behavioral eval as an ARCHITECTURE.

The chain doesn't evaluate behavior — the chain IS behavior, recorded, scored, receipted, and anchored.

---

## The Line

**Benchmarks tell you if the answer was right.**
**SwarmChain tells you what behavior got you there, what it cost, and where weaker paths died.**

*That's not an eval system. That's a behavioral intelligence engine.*

---

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
