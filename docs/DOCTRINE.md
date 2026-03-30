# The Doctrine — Six Roles, One Tribunal

**Scout finds. Router decides. Repair saves. Filter kills. Critic judges. Katniss closes.**

Six tributes cooked in one session. 40 minutes of bee training. 21 hours for the closer. The arena is designed.

---

## The Caste

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  SCOUT (0.5B + 1.5B)          "Find paths"                 │
│  Cook time: 1.9 min + 32 min                                │
│  80 micro-bees spray the search space                       │
│  15 scouts propose rough candidates                         │
│  Output: raw attempts, weak signals, candidate branches     │
│                                                             │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│                                                             │
│  ROUTER (1.5B)                "Decide where it goes"        │
│  Cook time: 1.9 min                                         │
│  Routes: REQUEST_MORE_SCOUTS | LOCAL_RETRY | SEND_TO_REPAIR │
│          SEND_TO_FILTER | ESCALATE_4B | ESCALATE_9B         │
│          KILL_PATH                                          │
│  Output: JSON routing decision with confidence + energy tier│
│                                                             │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│                                                             │
│  FILTER (1.5B)                "Kill the junk"               │
│  Cook time: 1.8 min                                         │
│  PASS or KILL. Schema validation. Contradiction detection.  │
│  Threshold: >= 0.60 passes, < 0.60 dies                     │
│  Output: one word + brief reason                            │
│                                                             │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│                                                             │
│  REPAIR (1.5B)                "Fix what's broken"           │
│  Cook time: 1.4 min                                         │
│  Takes jelly + gap analysis → produces targeted fix         │
│  Doesn't start from scratch — builds on what exists         │
│  Threshold: gap <= 0.40 is repairable, > 0.50 send back    │
│  Output: surgical fix, not full redo                        │
│                                                             │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│                                                             │
│  CRITIC (1.5B)                "Pressure survivors"          │
│  Cook time: 1.4 min                                         │
│  READY | NOT_READY | SEND_BACK                              │
│  Reviews repaired attempts, judges lineage trajectory       │
│  Checks energy ROI, identifies remaining weaknesses         │
│  Last gate before expensive compute                         │
│  Output: judgment + weakness + confidence                   │
│                                                             │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│                                                             │
│  KATNISS (9B)                 "Close the deal"              │
│  Cook time: 21 hours                                        │
│  SwarmRefinery — the ops brain                              │
│  Reads full lineage, synthesizes all attempts               │
│  Produces the final answer                                  │
│  Output: honey (or best jelly for seal)                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## The Flow

```
         ┌──────────┐
         │  TASK     │
         └────┬─────┘
              │
         ┌────▼─────┐
         │  SCOUT   │ ← 80 micro-bees + 15 scouts
         └────┬─────┘
              │ raw attempts
         ┌────▼─────┐
         │  ROUTER  │ ← where does each attempt go?
         └────┬─────┘
              │
    ┌─────────┼─────────┬──────────┐
    │         │         │          │
    ▼         ▼         ▼          ▼
 KILL_PATH  FILTER   REPAIR    ESCALATE
    │         │         │          │
    ×     ┌───▼───┐ ┌───▼───┐     │
        │ PASS/ │ │ FIX   │     │
        │ KILL  │ │ GAP   │     │
        └───┬───┘ └───┬───┘     │
            │         │          │
            └────┬────┘          │
                 │               │
            ┌────▼─────┐         │
            │  CRITIC  │ ←───────┘
            └────┬─────┘
                 │
         ┌───────┼───────┐
         │       │       │
      READY  NOT_READY  SEND_BACK
         │       │       │
         ▼       ▼       ▼
      KATNISS  REPAIR   ROUTER
      (close)  (again)  (re-route)
```

---

## The Training Data

Each bee was trained on role-specific data. No bee learns another bee's job.

| Bee | Pairs | Avg Response | Training Focus |
|-----|-------|-------------|----------------|
| Micro-Scout | 1,190 | ~10 tokens | MCQ, algorithm sketches, jelly/propolis signals |
| Scout | 4,879 | ~50 tokens | Algorithms, pattern recognition, scout protocol |
| Router | 1,621 | ~80 tokens (JSON) | Score routing, complexity gating, search continuation |
| Filter | 2,183 | ~15 tokens | Propolis recognition, schema validation, pass/fail |
| Repair | 1,199 | ~40 tokens | Gap analysis, before/after fixes, repair strategies |
| Critic | 1,316 | ~60 tokens | Quality judgment, lineage review, energy ROI |
| Katniss | 100,000 | ~800 tokens | Full ops intelligence, epoch analysis, defendable audit |

**Total bee data: 11,388 pairs across 6 role bees**
**Total closer data: 100,000 pairs for Katniss**
**Total cook time for bees: 40.4 minutes on RTX 3090 Ti**

---

## The Personality Rules

Each bee has hard behavioral boundaries. These are enforced through training data design:

### Scout
```
DO:    spray, explore, propose, die fast
DON'T: explain, analyze, polish, solve
TONE:  "Try mirror_h. Try rotate_90. Try color_swap. Move."
```

### Router
```
DO:    route, dispatch, decide, cost-optimize
DON'T: solve, explain, debate, second-guess
TONE:  {"route": "ESCALATE_4B", "reason": "Scouts exhausted.", "confidence": "high"}
```

### Filter
```
DO:    PASS or KILL, schema check, duplicate detect
DON'T: analyze, repair, solve, philosophize
TONE:  "KILL. Score 0.25. Dead end."
```

### Repair
```
DO:    fix the gap, targeted patch, build on what exists
DON'T: start from scratch, write essays, solve the whole task
TONE:  "Gap 0.25. Edge cells wrong. Fix boundary region."
```

### Critic
```
DO:    judge, pressure, review trajectory, check ROI
DON'T: solve, repair, explore, filter
TONE:  "NOT_READY. +0.01 improvement. Stalling. SEND_BACK."
```

### Katniss
```
DO:    synthesize lineage, close the deal, write reports, audit
DON'T: waste energy on easy tasks, skip the lineage, rush
TONE:  Full analysis. Structured. Decisive. The final word.
```

---

## Cook Summary — One Session

```
HARDWARE: RTX 3090 Ti (Whale) + RTX PRO 6000 (Rails)

WHALE (3090 Ti, 24GB):
  10:30  Rue Scout 1.5B        32.0 min
  11:02  Rue Micro-Scout 0.5B   1.9 min
  11:04  Filter Bee 1.5B        1.8 min
  11:06  Router Bee 1.5B        1.9 min
  11:08  Repair Bee 1.5B        1.4 min
  11:10  Critic Bee 1.5B        1.4 min
  ─────────────────────────────────────
  Total: 6 bees in 40.4 minutes

RAILS (RTX PRO 6000, 96GB):
  07:00  Katniss 9B             ~21 hours (solo cook, clean rig)
  ─────────────────────────────────────
  Status: 71% complete, ~5hr remaining
```

---

## What Happens Next

When Katniss lands:
1. Merge + quantize all 7 adapters → GGUF
2. Deploy bees to Xeon AMX (CPU fleet)
3. Deploy Katniss to DGX Spark #1
4. Run first tribunal epoch
5. Watch the glass wall

The arena is designed. The tributes are trained. The tribunal awaits.

---

## The One-Liner

**Scout finds. Router decides. Repair saves. Filter kills. Critic judges. Katniss closes.**

*Six roles. One tribunal. Convergence through elimination.*

---

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
