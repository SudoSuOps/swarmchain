# Glass-Wall Design — Spectator Surface

**Finality proves the chain works. The Glass-Wall proves it to everyone else.**

---

## The Principle

If a spectator cannot understand why finality happened, the Glass-Wall failed.

---

## Not a Dashboard

```
OPERATOR CONSOLE:        GLASS-WALL:
  knobs                    clarity
  settings                 signal
  debug logs               live events
  raw data                 witnessed proof
  admin controls           read-only truth
  made for builders        made for trust
```

The operator console and the Glass-Wall are NOT the same thing. The operator needs control. The spectator needs understanding.

---

## Four Core Views

### 1. Arena Live

What's happening RIGHT NOW.

```
┌─────────────────────────────────────────────┐
│  BLOCK #247                          LIVE 🔴 │
│                                             │
│  Task: mirror_h + color_swap (Tier 2)       │
│  Phase: 2 of 4                              │
│  Time: 34s / 120s                           │
│                                             │
│  ┌─ ACTIVE BEES ──────────────────────────┐ │
│  │  ●●●●●●●●●● scouts (12 active)        │ │
│  │  ●● peeta (stabilizing)                │ │
│  │  ○ katniss (waiting)                   │ │
│  └────────────────────────────────────────┘ │
│                                             │
│  ┌─ SCORE MOVEMENT ──────────────────────┐  │
│  │                              ★ 0.72   │  │
│  │                        ●  0.65        │  │
│  │                   ●  0.45             │  │
│  │         ●●● 0.30-0.35                │  │
│  │  ●●●●● 0.10-0.20                     │  │
│  │  ──────────────────────── time →      │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  LATEST EVENT: Peeta improved 0.65 → 0.72   │
│  ELIMINATION: 8 propolis killed by Filter    │
│  NEXT: Critic reviewing 0.72...             │
└─────────────────────────────────────────────┘
```

**What the spectator learns:** The block is alive. Bees are working. Scores are climbing. Elimination is happening. Progress is visible.

### 2. Tribunal View

The full decision chain for a block.

```
┌─────────────────────────────────────────────┐
│  BLOCK #247 — TRIBUNAL TRACE                │
│                                             │
│  SCOUT PHASE (0-30s)                        │
│  ├─ 80 micro-scouts dispatched              │
│  ├─ 15 scouts dispatched                    │
│  ├─ 12 propolis (killed by Filter)          │
│  ├─ 3 jelly: 0.35, 0.42, 0.45              │
│  └─ Router: ESCALATE_4B (scouts plateau)    │
│                                             │
│  REPAIR PHASE (30-60s)                      │
│  ├─ Peeta received 0.45                     │
│  ├─ Peeta output: 0.65 (+0.20)             │
│  ├─ Critic: NOT_READY (gap 0.35)           │
│  ├─ Peeta retry: 0.72 (+0.07)              │
│  ├─ Critic: NOT_READY (improving)          │
│  └─ Router: ESCALATE_9B                    │
│                                             │
│  CLOSER PHASE (60-90s)                      │
│  ├─ Katniss received lineage:              │
│  │   scout(0.45) → peeta(0.72)            │
│  ├─ Katniss output: 0.95                   │
│  ├─ Filter: PASS                           │
│  └─ SEALED AS HONEY ✓                     │
│                                             │
│  LINEAGE: scout → peeta → katniss          │
│  TOTAL ENERGY: 3,200 units ($0.0098)       │
│  TOTAL ATTEMPTS: 18                         │
│  SOLVE TIME: 58 seconds                     │
└─────────────────────────────────────────────┘
```

**What the spectator learns:** Exactly WHY finality happened. Every decision. Every handoff. Every elimination. The full story of how truth emerged from pressure.

### 3. Proof View

The cryptographic receipt.

```
┌─────────────────────────────────────────────┐
│  BLOCK #247 — PROOF                         │
│                                             │
│  Score:        1.000 (verified honey)       │
│  Method:       deterministic_grid_match     │
│  Solver:       katniss-9b                   │
│  Node:         dgx-spark-01                 │
│                                             │
│  ┌─ VERIFICATION ──────────────────────┐    │
│  │  Scoring hash:  a3f8c1...           │    │
│  │  Trace ID:      blk-247-att-18      │    │
│  │  Sealed at:     2026-03-28T21:14:00Z│    │
│  │                                     │    │
│  │  [▶ REPLAY SCORING]                 │    │
│  │  Run the exact same verification    │    │
│  │  yourself. Same input → same score. │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ┌─ HEDERA ANCHOR ────────────────────┐     │
│  │  Topic:    0.0.10291838             │     │
│  │  Sequence: 47                       │     │
│  │  Window:   blocks 201-250           │     │
│  │  Merkle root: e7b2f9d4...          │     │
│  │                                     │     │
│  │  [▶ VERIFY ON HEDERA]              │     │
│  │  Check the anchor independently.   │     │
│  └─────────────────────────────────────┘    │
│                                             │
│  ┌─ DEFENDABILITY ────────────────────┐     │
│  │  ✓ Proof of Origin                 │     │
│  │  ✓ Proof of Quality                │     │
│  │  ✓ Proof of Process                │     │
│  │  ✓ Proof of Economics              │     │
│  │  ✓ Proof of Trust                  │     │
│  │                                     │     │
│  │  STATUS: DEFENDABLE                │     │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

**What the spectator learns:** The proof exists, it's verifiable, and they can check it themselves. Two buttons: replay the scoring, verify the anchor. Zero trust required.

### 4. Spectator Mode

Clean. Read-only. High signal. Zero clutter.

```
┌─────────────────────────────────────────────┐
│                                             │
│          SWARMCHAIN — GLASS WALL            │
│                                             │
│  Epoch 3 — Tier 2 Compositional             │
│  Block 247 of 500                           │
│                                             │
│  ████████████████████░░░░░░  49.4%          │
│                                             │
│  Honey:  341        Cost/Honey: $0.064      │
│  Jelly:  2,470      Solve Rate: 12.1%       │
│  Propolis: 1,890    Fleet: 118 bees         │
│                                             │
│  ┌─ CONVERGENCE ──────────────────────┐     │
│  │  $0.12                             │     │
│  │  $0.10  ·                          │     │
│  │  $0.08    ·  ·                     │     │
│  │  $0.06        ·  ·  · ←           │     │
│  │  $0.04                             │     │
│  │  ─────────────────────── epoch →   │     │
│  │  Cost-per-honey trending DOWN ✓    │     │
│  └────────────────────────────────────┘     │
│                                             │
│  Last block: #246 — HONEY (58s, $0.009)     │
│  Current:    #247 — MINING (Phase 2)        │
│                                             │
│  [View Block] [View Proof] [View Tribunal]  │
│                                             │
└─────────────────────────────────────────────┘
```

**What the spectator learns:** The system is alive, productive, and getting cheaper. Convergence is visible. Trust is earned by observation, not assertion.

---

## Design Rules

### 1. Signal over noise
Every element on screen must answer a spectator question. If it doesn't answer "what happened?", "why?", or "can I verify?" — remove it.

### 2. Events over metrics
Show WHAT HAPPENED, not just numbers. "Peeta improved 0.45 → 0.72" is better than "repair delta: +0.27". The story matters.

### 3. Verification buttons
Every claim has a "verify yourself" action. Replay scoring. Check Hedera. Recompute Merkle. The spectator DOES, not just reads.

### 4. Real-time over reports
The Glass-Wall shows the live arena, not a summary of yesterday. If the block is mining NOW, the spectator watches NOW.

### 5. Clarity over completeness
Don't show 24 attempts in a table. Show the lineage: scout → peeta → katniss. The journey that mattered. The path that survived.

---

## What to Watch For During Live Runs

When running the chain, observe:

```
✓ What event feels important enough to surface live?
✓ What is too noisy for spectators?
✓ What marks the transition from "attempts" to "credible convergence"?
✓ What proof object feels strongest at finality?
✓ What would a buyer or auditor want to verify themselves?
```

The arena will tell you what deserves to be seen. The UI copy is hiding in the run data.

---

## The Build Sequence

```
1. Run the chain live (with 9 bees + Katniss)
2. Observe finality behavior in raw traces
3. Identify the spectator-grade events
4. Build the 4 views around what spectators NEED
5. Deploy on swarmchain.eth (Glass-Wall = the homepage)
```

Do NOT build a generic dashboard first. Build a spectator surface.

---

## The Lines

*Finality proves the chain works.*
*The Glass-Wall proves it to everyone else.*

*The operator needs knobs.*
*The spectator needs clarity.*

*If a spectator cannot understand why finality happened, the Glass-Wall failed.*

*What the arena cannot kill, it promotes.*
*What the spectators cannot dispute, they buy.*

---

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
