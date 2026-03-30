# The Arena — Convergence Through Elimination

**The bees are tributes. Each one designed with strengths and weaknesses. They don't converge by being the same. They converge by being different.**

---

## The Tributes

Every node in the swarm has a character — a designed personality built for a specific role in the arena.

```
SwarmRue (4B)          The youngest tribute
                       Fast, cheap, dies early — but leaves signal
                       Scores 0.450 on a task nobody else has touched
                       That 0.450 is not failure. It's the first data point.
                       Rue narrows the search space for everyone.

Katniss (9B)           The volunteer
                       Gets the job done. Reliable. Survives everything.
                       Reads the lineage from Rue and Johanna.
                       Builds on their failures. Drops the 1.000.
                       The closer.

Haymitch (27B)         The drunk mentor
                       Knows the game deeply. Sees patterns others miss.
                       Expensive to keep around. Burns energy like whiskey.
                       But when the task is hard enough — only Haymitch solves it.
                       Use sparingly. Deploy when the arena demands it.

Finnick (7B-Whale)     The specialist
                       Strong in specific domains. Elegant solutions.
                       Runs on the RTX 3090 — mid-tier silicon, mid-tier cost.
                       Doesn't win often, but when he wins, it's clean.

Johanna (SwarmJelly-4B) No filter
                       Trained on failure. Fed on propolis and jelly.
                       The self-healing model — learned from what went wrong.
                       Scores 0.750 where base models score 0.300.
                       Cuts through noise. Knows what DOESN'T work.

Peeta (Capital-9B)     The domain specialist
                       Strong when prompted right. Deep domain knowledge.
                       24% honey rate — but 34x more expensive than base.
                       The right tribute for the right task. Wrong arena = waste.

Rue's Bees (0.8B)      The micro-tributes
                       25 of them. Swarm tactics. Volume play.
                       Each one weak. Together, they cover ground.
                       3% honey rate but 50% jelly — half their work is signal.
                       The cheapest intelligence in the pool.
```

---

## The Design Principle

**The tributes are not built to be the best. They're built to be DIFFERENT.**

```
Traditional ML:   Train the best model. Deploy it. Done.
SwarmChain:       Train DIFFERENT models. Deploy them ALL. Let them compete.
```

A fleet of identical models produces identical failures. A fleet of diverse models produces **complementary failures** — each one failing in a different way, each failure narrowing the search space for the next attempt.

**Weakness is signal.** Rue's 0.450 tells Katniss where NOT to look. Johanna's 0.750 tells Katniss where TO look. The elimination of bad approaches IS the reasoning process.

---

## The Arena — How Convergence Works

A block opens. The task enters the arena.

```
Block: "Flip grid horizontally + apply color remap" (Tier 2 compositional)

Phase 1 — The Volunteer Tributes (0-30s)
  Rue's bees swarm the task. 15 micro-tributes, 3B each.
  Most score 0.1-0.3 (propolis). Two score 0.45 (jelly).
  SIGNAL: the task has horizontal symmetry. Color remap is the hard part.

Phase 2 — The Specialists Enter (30-60s)
  Johanna (SwarmJelly-4B) reads the bee attempts.
  She was TRAINED on failures like this. She knows what 0.45 means.
  Johanna scores 0.750. She got the flip right, color remap partial.
  Finnick (7B) scores 0.600. Different approach, same weak spot.
  SIGNAL: color remap is the bottleneck. Flip is solved.

Phase 3 — The Closer (60-90s)
  Katniss (9B) reads the lineage:
    Rue → 0.450 (flip wrong, colors wrong)
    Johanna → 0.750 (flip right, colors partial)
    Finnick → 0.600 (flip right, colors different-wrong)
  Katniss knows: the flip is solved. Focus on color remap.
  She doesn't start from zero. She starts from 0.750.
  Katniss scores 1.000. Honey.

Phase 4 — Seal
  Block sealed. 58 seconds. 8 attempts.
  Winner: Katniss (solver reward: 40%)
  Lineage: Johanna → Katniss (+0.250 improvement, lineage reward: 30%)
  Exploration: Rue's bees + Finnick (spread across exploration pool)
  Everyone earned. Nobody wasted.
```

---

## Elimination IS Reasoning

In the Hunger Games, elimination is violence. In SwarmChain, elimination is **intelligence**.

```
Attempt scores 0.300 → PROPOLIS
  This approach doesn't work.
  That information is VALUABLE.
  Every future attempt knows: don't go there.

Attempt scores 0.750 → JELLY
  This approach ALMOST works.
  What's the gap between 0.750 and 1.000?
  That gap is the signal. That gap is what the next miner targets.

Attempt scores 1.000 → HONEY
  Built on the failures. Built on the near-misses.
  The 1.000 didn't come from genius. It came from CONVERGENCE.
  From elimination narrowing the search space.
  From different failures pointing at the same truth.
```

**No single tribute solves alone.** The solve is the CONVERGENCE of different intelligences, each contributing what they're designed to contribute:
- Rue contributes **speed** (cheap, fast, first signal)
- Johanna contributes **resilience** (trained on failure, knows what doesn't work)
- Finnick contributes **diversity** (different approach, different failure mode)
- Katniss contributes **synthesis** (reads the lineage, builds the final answer)

---

## The Lineage Graph

Every solve has a story. The lineage graph tells it.

```
    Rue-bee-003 (0.300)
         ↓ elimination signal
    Rue-bee-007 (0.450)
         ↓ partial improvement
    Johanna (0.750) ──────────┐
         ↓ near-miss signal   │
    Finnick (0.600)           │ lineage
         ↓ diversity signal   │
    Katniss (1.000) ←─────────┘
         ↑
    Built on 4 failures + 1 near-miss
    5 tributes contributed. 1 solved.
    The solve REQUIRED the failures.
```

This is visible on the glass wall. The client sees the lineage. The client sees that the answer didn't appear from nothing — it was **manufactured through convergence**.

---

## Designing Tributes

Each tribute is designed with intention:

| Tribute | Strength | Weakness | Role in Arena |
|---------|----------|----------|---------------|
| Rue (0.8B) | Speed, cost | Accuracy | First signal, search space reduction |
| Johanna (SwarmJelly-4B) | Failure knowledge | Novel tasks | Near-miss generation, gap identification |
| Finnick (7B) | Domain depth | Narrow range | Alternative approaches, diversity |
| Katniss (9B) | Synthesis, closing | Cost | Final solve, lineage reader |
| Haymitch (27B) | Deep reasoning | Energy burn | Last resort, hardest tasks only |
| Peeta (Capital-9B) | Domain expertise | Wrong arena = waste | Specialized tasks, prompted right |

**The fleet is designed like a team, not a tournament.** Each tribute has a role. The escalation ladder IS the game design. Phase 1 sends the scouts. Phase 2 sends the specialists. Phase 3 sends the closer. Phase 4 is all-in.

---

## The Economics of Convergence

```
If Katniss solved alone (no lineage):
  1 attempt × $0.004 = $0.004/honey
  But Katniss would need 13 attempts on average to solve
  Real cost: 13 × $0.004 = $0.052/honey

With the arena (tributes + lineage):
  5 Rue attempts × $0.0005 = $0.0025
  1 Johanna attempt × $0.001 = $0.001
  1 Finnick attempt × $0.002 = $0.002
  1 Katniss attempt × $0.004 = $0.004
  Total: $0.0095/honey

  5.5x cheaper. Because elimination is free intelligence.
```

**The tributes who "lost" made the solve cheaper.** Their failures were not waste — they were investment. The cost of Rue's propolis is the cost of narrowing the search. The cost of Johanna's jelly is the cost of identifying the gap.

Every failure has a receipt. Every receipt has value. Nothing is wasted.

---

## The Rule

**The tributes don't converge by being the same. They converge by being different.**

Different models. Different sizes. Different training data. Different silicon. Different failure modes. Different strengths.

That's the arena. That's the design. That's convergence through elimination.

*"May the odds be ever in your favor."*
*In SwarmChain, they are. Because the odds are designed.*

---

*This is not a metaphor. This is the architecture.*
