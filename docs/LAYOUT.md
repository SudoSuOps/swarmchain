# Glass-Wall Layout — Browser Architecture

**If the arena is real, the browser must make survival visible.**
**If finality is real, the browser must make proof legible.**

---

## Page Stack

```
┌─────────────────────────────────────────────────────────┐
│  1. LIVE FINALITY HEADER          what is happening now │
├────────────┬──────────────────┬─────────────────────────┤
│ 2. ARENA   │ 3. TRIBUNAL      │ 4. CONVERGENCE          │
│    FEED    │    BOARD          │    LADDER               │
│            │                  │                         │
│ what just  │ who is acting    │ what is surviving       │
│ happened   │                  │                         │
├────────────┴──────────────────┴─────────────────────────┤
│  5. SCORE & PRESSURE PANEL        why it survived       │
├─────────────────────────────────────────────────────────┤
│  6. FINALITY PANEL                what was sealed       │
├─────────────────────────────────────────────────────────┤
│  7. PROOF DRAWER                  how to verify it      │
├─────────────────────────────────────────────────────────┤
│  8. BLOCK HISTORY RAIL            prove it's repeatable │
└─────────────────────────────────────────────────────────┘
```

---

## 1. Live Finality Header

The first thing a spectator sees. Mission control ribbon.

```
┌─────────────────────────────────────────────────────────┐
│  ● LIVE    Block #247    Task: rotate_180               │
│            State: Tribunal Review    Anchor: Pending     │
└─────────────────────────────────────────────────────────┘
```

**Contents:**
- Chain status: `LIVE` / `IDLE` / `FINALIZING`
- Current block number
- Current task name + domain
- Finality state: `Searching` → `Converging` → `Tribunal Review` → `Finalized`
- Hedera anchor: `Pending` → `Anchored` → `Confirmed`

---

## 2. Arena Live Feed

The heartbeat. Live broadcast ticker, not a debug log.

```
21:04:11  Scout      Candidate 03 proposed mirror transform
21:04:13  Filter     Candidate 03 eliminated (schema fail)
21:04:15  Scout      Candidate 07 proposed rotate + remap
21:04:19  Peeta      Candidate 07 repaired (0.45 → 0.72)
21:04:22  Critic     Candidate 07 NOT_READY (gap 0.28)
21:04:31  Router     ESCALATE_9B — candidate 07 earned closer
21:04:44  Katniss    Candidate 07 closed (0.72 → 1.000)
21:04:45  Filter     PASS — honey confirmed
21:04:46  ■ SEALED   Block #247 finalized
```

**Each event shows:**
- Timestamp
- Bee class
- Action
- Target candidate
- Score change (if relevant)

**Design rule:** This should feel like watching a live broadcast. Time-ordered. Clean. Relentless.

---

## 3. Tribunal Board

The core visual. Large card tiles for each caste.

```
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  RUE SCOUT   │ │   FILTER     │ │   ROUTER     │
│  ● ACTIVE    │ │  ● ACTIVE    │ │  ● ACTIVE    │
│              │ │              │ │              │
│  Attempts: 15│ │  Kills: 12   │ │  Routes: 8   │
│  Best: 0.45  │ │  Passes: 3   │ │  Escalations:│
│              │ │              │ │  2           │
│  Generating  │ │  Last: #09   │ │  Last:       │
│  candidates  │ │  rejected    │ │  ESCALATE_9B │
└──────────────┘ └──────────────┘ └──────────────┘

┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   PEETA      │ │   CRITIC     │ │  KATNISS     │
│  ✓ COMPLETE  │ │  ✓ COMPLETE  │ │  ● CLOSING   │
│              │ │              │ │              │
│  Repairs: 2  │ │  Reviews: 3  │ │  Attempts: 1 │
│  Best: +0.27 │ │  READY: 1    │ │  Score: 1.00 │
│              │ │  NOT_READY: 2│ │              │
│  Stabilized  │ │  Cleared #07 │ │  Honey       │
│  Candidate 07│ │  for closer  │ │  confirmed   │
└──────────────┘ └──────────────┘ └──────────────┘
```

**Each card shows:**
- Active / idle / completed
- Attempts or actions taken
- Key metric (kills, repairs, routes, score)
- Current status sentence

Makes the tribunal feel alive and legible.

---

## 4. Convergence Ladder

Where spectators see survival happen. Ranked ladder of candidates.

```
 #  Candidate   Origin                    Score    State
 ─────────────────────────────────────────────────────────
 1  Cand-07     Scout → Peeta → Katniss   1.000   ★ FINALIZED
 2  Cand-04     Scout → Peeta             0.72    ○ Repaired
 3  Cand-12     Scout                     0.45    ○ Jelly
 4  Cand-09     Scout                     0.35    ✕ Eliminated
 5  Cand-03     Scout                     0.18    ✕ Eliminated
 6  Cand-01     Scout                     0.12    ✕ Eliminated
 ·  (12 more eliminated)
```

**This visually explains: what survived pressure.**

The lineage column is the story. `Scout → Peeta → Katniss` shows the handoff chain. The spectator sees that the winner wasn't born perfect — it was MADE through collaboration under pressure.

---

## 5. Score & Pressure Panel

Why this candidate survived. One of the most important panels.

```
┌─────────────────────────────────────────────────────────┐
│  CANDIDATE 07 — SURVIVAL TRACE                          │
│                                                         │
│  Initial:              0.31  (Scout phase)              │
│  After Repair:         0.72  (Peeta stabilized)         │
│  Critic Verdict:       READY (after 2 reviews)          │
│  Final Score:          1.000 (Katniss closed)           │
│                                                         │
│  Eliminations Survived: 4                               │
│  Tribunal Passes:       3                               │
│  Total Energy:          2,847 units                     │
│  Lineage Depth:         3 bees                          │
│                                                         │
│  ┌─ SCORE JOURNEY ─────────────────────────────┐        │
│  │  1.0  ·····························★        │        │
│  │  0.8  ··················●                   │        │
│  │  0.6  ·········●                            │        │
│  │  0.4  ···●                                  │        │
│  │  0.2  ●                                     │        │
│  │  0.0  ─────────────────────────── step →    │        │
│  │       scout  peeta  critic katniss          │        │
│  └─────────────────────────────────────────────┘        │
│                                                         │
│  This candidate survived because:                       │
│  Scout found the structure. Peeta stabilized it.        │
│  Critic verified the repair. Katniss closed the gap.    │
└─────────────────────────────────────────────────────────┘
```

**Answers: why did this win?**

---

## 6. Finality Panel

Ceremonial. Marks the transition from activity to truth.

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│                 ■ FINALITY GRANTED                       │
│                                                         │
│  Block #247                                             │
│  Candidate 07                                           │
│  Final Score: 1.000                                     │
│                                                         │
│  Winning Path: Scout → Peeta → Katniss                  │
│  Solve Time: 58 seconds                                 │
│  Total Energy: $0.0098                                  │
│                                                         │
│  Rewards:                                               │
│    Katniss    40.00  (solver)                           │
│    Scout      30.00  (lineage)                          │
│    Peeta      20.00  (repair)                           │
│    Others      10.00  (exploration + efficiency)        │
│                                                         │
│  Anchored: Hedera topic 0.0.10291838 / seq 47           │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**This should feel ceremonial.** The moment the block seals is the moment truth is committed.

---

## 7. Proof Drawer

Collapsible. Clean. Technical. Where spectators validate the validators.

```
┌─ PROOF ─────────────────────────────────────────────────┐
│                                                         │
│  Score Hash:     a3f8c1d2e9b7...                        │
│  Merkle Root:    e7b2f9d4a1c8...                        │
│  Lineage Hash:   7d4e2f8a9b1c...                        │
│  Trace ID:       blk-247-att-18                         │
│  Scoring v:      deterministic_grid_match_v2            │
│                                                         │
│  Hedera:                                                │
│    Topic:     0.0.10291838                              │
│    Sequence:  47                                        │
│    Window:    blocks 201-250                            │
│                                                         │
│  [▶ Replay Score]  [▶ Verify Merkle]  [▶ Check Anchor]  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Three buttons. That's the trust interface.

---

## 8. Block History Rail

Prove this isn't a one-off. Failure is visible too.

```
← #245  mirror_row   ✕ EXHAUSTED  best: 0.68  no anchor
   #246  left_fall    ✓ FINALIZED  Scout → Katniss     anchor: seq 46
   #247  rotate_180   ✓ FINALIZED  Scout → Peeta → K.  anchor: seq 47
   #248  color_swap   ● MINING     Phase 1...
→
```

**Failure should be visible. That builds trust.** A Glass-Wall that only shows wins is a marketing page, not a witness.

---

## Deep Views (Modals)

### Candidate Detail
Click any candidate to see its full life:
- Origin bee
- Every score update
- Every elimination pressure survived
- Repair history
- Critic notes
- Final outcome

### Bee Activity
Click any bee class to see its contribution:
- Attempts made
- Actions taken
- Average score lift
- Kill count
- Escalations caused

---

## Visual Design Language

```
FEEL:     Observatory, not casino
          Industrial witness layer
          Dark, high contrast, precise

MOTION:   Only for:
          - Block opening
          - Candidate promotion
          - Elimination
          - Finality seal
          - Anchor confirmation

COLORS:   Blue/white  — neutral live activity
          Amber       — under review / converging
          Red         — eliminated
          Green       — finalized / verified

TYPOGRAPHY: Strong. Monospace for data. Clean sans for labels.
```

---

## Information Hierarchy

A spectator answers these in order:

```
1. What block is open?
2. Is the chain live?
3. What is the current state?
4. What candidates are alive?
5. Which bees are acting?
6. Why did the winner survive?
7. Can I verify the proof?
```

If the page doesn't answer these in 10 seconds, redesign.

---

## The Doctrine

```
Live Header      — what is happening now
Arena Feed       — what just happened
Tribunal Board   — who is acting
Convergence Ladder — what is surviving
Pressure Panel   — why it survived
Finality Panel   — what was sealed
Proof Drawer     — how to verify it
Block History    — prove this is repeatable
```

**If the arena is real, the browser must make survival visible.**
**If finality is real, the browser must make proof legible.**

---

*What the arena cannot kill, it promotes.*
*What the spectators cannot dispute, they buy.*

---

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
