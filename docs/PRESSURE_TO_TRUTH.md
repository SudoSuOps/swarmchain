# Pressure to Truth

**The simplicity of elimination is survival.**

---

## The Question Nobody Else Asks

Benchmarks ask: *"Did it work?"*

SwarmChain asks: *"How much swarm pressure was required before truth survived?"*

---

## The 10 Metrics

| # | Metric | What It Measures |
|---|--------|-----------------|
| 1 | **Solve rate** | Blocks solved / blocks mined |
| 2 | **Energy per solve** | Total energy / honey count |
| 3 | **Closure rate by bee class** | Which tier actually closes |
| 4 | **Repair dependency** | % of solves that needed Peeta |
| 5 | **Escalation frequency** | How often bees need GPU backup |
| 6 | **Dead-path ratio** | % of attempts that were propolis |
| 7 | **Useful near-miss rate** | % of jelly that led to honey via lineage |
| 8 | **Latency to viable candidate** | Seconds until first jelly >= 0.60 |
| 9 | **Cost-adjusted correctness** | Solve rate weighted by energy |
| 10 | **Convergence efficiency** | How fast cost-per-honey descends |

Metric 10 is the killer. Not "did it work" but "is the system learning?"

---

## Ideal Trajectory

Every block has a shortest path to truth.

```
IDEAL (easy):
  scout → honey → seal
  1 bee touched. 5 seconds. $0.0001.

IDEAL (medium):
  scout → peeta → katniss → honey → seal
  3 bees. 30 seconds. $0.005.

IDEAL (hard):
  scout → escalate → peeta → critic → katniss → retry → honey → seal
  5 bees. 90 seconds. $0.012.
```

The deviation from ideal tells you everything:

```
Too many scouts?           → search is unfocused
Router escalated too late? → policy is too conservative
Peeta didn't improve?      → repair strategy is stale
Critic passed too early?   → quality bar is too low
Katniss needed 3 tries?    → lineage wasn't read properly
```

Every deviation is a signal. Every signal feeds the next epoch.

---

## Elimination IS the Eval

The tribunal doesn't evaluate after the fact. It evaluates IN THE ACT.

```
Step 1: Scout proposes 0.35
        → Router evaluates: "weak but structured"
        → Decision: SEND_TO_REPAIR

Step 2: Peeta repairs to 0.68
        → Critic evaluates: "NOT_READY, gap 0.32"
        → Decision: ESCALATE_9B

Step 3: Katniss closes to 1.0
        → Filter evaluates: "PASS, honey confirmed"
        → Decision: SEAL

Every step is an evaluation.
Every evaluation is a decision.
Every decision applies pressure.
The pressure produces truth.
```

There is no separate eval pipeline. The tribunal IS the eval.

---

## What the Metrics Reveal

### A healthy block looks like:
```
Solve: YES
Attempts: 6
Lineage depth: 3 (scout → peeta → katniss)
Dead paths: 2 (eliminated early by filter)
Phase solved: 3
Cost: $0.008
Verdict: efficient, clean escalation
```

### A sick block looks like:
```
Solve: NO
Attempts: 24 (max)
Lineage depth: 1 (everything isolated, no building)
Dead paths: 18 (75% wasted)
Phase solved: never
Cost: $0.025
Verdict: scouts redundant, router too slow, no repair signal
```

### A converging system looks like:
```
Epoch 1: CPH $0.12, solve rate 7.7%
Epoch 2: CPH $0.08, solve rate 11.2%
Epoch 3: CPH $0.06, solve rate 14.8%

Pressure-to-truth is DECREASING.
The system needs less elimination to find survival.
The bees are getting smarter.
```

### A diverging system looks like:
```
Epoch 1: CPH $0.06, solve rate 14.8%
Epoch 2: CPH $0.09, solve rate 11.0%
Epoch 3: CPH $0.11, solve rate 9.2%

Pressure-to-truth is INCREASING.
Something is wrong. More effort for less result.
Investigate: wrong tier? stale bees? scheduler issue?
```

---

## Evals Shape Behavior

This is the deepest insight:

The tribunal doesn't just MEASURE behavior — it SHAPES it.

When the filter kills a 0.55, that becomes the quality floor. Every future bee knows: below 0.60, you die. That pressure reshapes how scouts generate, how repairers fix, how routers dispatch.

When the critic says "NOT_READY" on a 0.78, that becomes the readiness bar. Katniss is only called when the bar is met. That pressure means Peeta works harder. Repair pushes further before handoff.

When the router kills a path at score 0.20 after 6 attempts, that becomes the exploration budget. Scouts learn to diversify faster because the window is finite.

**The bees don't read a rulebook. They evolve under pressure.**

```
TRADITIONAL:
  Human writes rules → model follows rules

SWARMCHAIN:
  Tribunal applies pressure → behavior emerges from survival
  What survives is what "good" means
  What dies is what "bad" means
  The definition sharpens every epoch
```

---

## Natural Selection for AI

The bee colony doesn't have a manager who tells each bee what to do. The colony has PRESSURE — food scarcity, predators, temperature, disease. The bees that respond well to pressure survive. The colony adapts.

SwarmChain is the same architecture:

```
PRESSURE:     Economic (energy cost), Temporal (phase windows),
              Quality (score thresholds), Competitive (other bees)

SURVIVAL:     Honey (score >= 0.95)

ELIMINATION:  Propolis (score < 0.30), timeout, duplicate,
              filter kill, critic rejection

ADAPTATION:   Convergence over epochs — cost down, solve rate up,
              lineage getting shorter, efficiency improving
```

The tribunal is not designed to find the right answer. It's designed to create the CONDITIONS under which the right answer SURVIVES.

That's the simplicity.

Elimination is survival.

---

## The Line

**Benchmarks measure the answer.**
**SwarmChain measures the pressure required to reach the answer.**

Lower pressure = smarter system.
Decreasing pressure over time = convergence.
Convergence = the system is learning.

The tribunal is not an eval framework. It's an evolutionary pressure chamber.

*The simplicity of elimination is survival.*

---

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
