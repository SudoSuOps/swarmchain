# SwarmRefinery — The Mining Operations Center

**Who builds refinery models?**

Not domain models. Not chatbots. Not another LLM that answers questions. A model that **runs the refinery.** The brain behind the glass wall. The operations center that makes every block, every epoch, every dataset DEFENDABLE.

---

## What SwarmRefinery IS

SwarmRefinery is the in-house operational intelligence engine for Swarm & Bee.

It doesn't mine blocks — it **certifies** them.
It doesn't solve tasks — it **audits** the solutions.
It doesn't generate data — it makes data **defendable and bankable**.

Think of it as the control room in a mining operation. The miners dig. The control room decides where to dig, tracks what comes out, certifies the yield, and makes sure the books balance.

---

## The 3-Shift Operation

SwarmRefinery runs 24/7 across three operational shifts:

### Shift 1 — Mining (Active Epoch)
```
The swarm is mining. Blocks are opening and sealing.
SwarmRefinery monitors:
  - Cost-per-honey (trending up or down?)
  - Solve rate per model (who's producing?)
  - Energy efficiency (which silicon tier is winning?)
  - Convergence windows (are we improving?)
  - Fleet health (any nodes down?)
```

### Shift 2 — Cooldown / Audit
```
The epoch just sealed. SwarmRefinery goes into audit mode:
  - Underwrite the event (what happened and why)
  - File it, organize it, label it
  - Classify edge cases (that 0.89 jelly — honey or not?)
  - Discovery mode (what patterns emerged in the data?)
  - Write the epoch report
  - Compute final economics
  - Trigger Hedera anchor for the last windows
```

### Shift 3 — Prep
```
Next epoch is coming. SwarmRefinery plans:
  - Adjust escalation policy (Phase timing)
  - Recommend fleet composition (which models, which tiers)
  - Calculate budget allocation
  - Set target block count and deadline
  - Clean gear (retire underperforming models)
  - Prep task generator for next tier
```

**That's a lot for a Python script.** The scripts handle the plumbing — open block, close block, track state. SwarmRefinery handles the **thinking** — analyze, recommend, audit, certify.

---

## The Architecture

```
Layer 1: Deterministic Scripts (0 GPU, always running)
  single_chain.py    — block lifecycle
  supervisor.py      — crash recovery
  cost_calculator    — arithmetic
  convergence        — rolling window math

Layer 2: SwarmRefinery (dedicated GPU, 24/7)
  Epoch analysis     — "what happened and why"
  Fleet optimization — "which model mines which tier"
  Dataset audit      — "is this defendable?"
  Cost projection    — "what will the next epoch cost"
  Client reports     — "here's what you're buying"
  SwarmEval reports  — "here's what your model can do"

Layer 3: Human (the operator)
  Reviews recommendations
  Approves epoch plans
  Signs off on deliveries
```

Scripts do the plumbing. SwarmRefinery does the thinking. The human makes the calls.

---

## The Training Data — What a Refinery Brain Eats

SwarmRefinery was not trained on domain data. No grants. No real estate. No legal docs. Pure operational intelligence:

```
Source                          Pairs     Purpose
──────────────────────────────────────────────────────
Nemotron Instruction Following  47,616    Reasoning backbone
Nemotron Algorithms             17,222    Search, scheduling, optimization
Nemotron MCQ                     9,608    Structured reasoning
Nemotron Formal Logic            7,676    Proofs, truth tables
Nemotron Blockchain              4,792    Consensus, Merkle, Hedera, trust
Nemotron Economics               4,762    Cost analysis, pricing, markets
Nemotron Compute + Silicon       4,760    GPU/CPU, J/token, efficiency
SwarmChain Epoch Ops             3,498    Real honey/jelly/propolis from mining
Protocol Knowledge                  79    The soul — 67 deep operational pairs
──────────────────────────────────────────────────────
Total                          100,013    Zero domain slop
```

### Why This Mix

**47.6% Instruction Following** — the reasoning backbone. SwarmRefinery needs to think clearly, follow complex instructions, and produce structured output.

**17.2% Algorithms** — the refinery is fundamentally an optimization problem. Search strategies, scheduling algorithms, resource allocation. This is the math.

**9.6% MCQ + 7.7% Formal Logic** — structured reasoning and proof construction. When SwarmRefinery says "this dataset is defendable," it needs to build the argument step by step.

**4.8% Blockchain** — SwarmRefinery anchors to Hedera. It needs to understand consensus, Merkle trees, hash functions, trust verification. Not as a crypto bro — as an engineer who uses these tools.

**4.8% Compute + Silicon** — the silicon ladder. J/token. S19 vs S21. RTX 6000 vs DGX Spark. SwarmRefinery makes hardware allocation decisions. It needs to think in watts, tokens, and dollars.

**4.8% Economics** — cost-per-honey, ROI, break-even analysis. The refinery is a business. Every decision has an economic dimension.

**3.5% SwarmChain Ops** — real epoch data. Real honey. Real jelly. Real propolis. 3,498 pairs from actual mining runs, with real scores, real models, real energy costs. This is the ground truth.

**0.1% Protocol Knowledge** — 67 deep pairs that teach the model WHO IT IS. What is cost-per-honey? What makes data defendable? How does the escalation ladder work? What is finality? These are concentrated, high-signal pairs that define the refinery's identity.

### What's NOT in the data

- No CRE real estate
- No Capital grants
- No legal documents
- No domain-specific knowledge

SwarmRefinery is an ops engine, not a domain model. It runs the refinery. It doesn't do the domain work.

---

## The Cook — Parallel Blackwell

Two SwarmRefinery models cooking simultaneously on one rig:

```
┌──────────────────────────────────────────────────┐
│  GPU 0: RTX PRO 4500 Blackwell (32GB)            │
│  SwarmRefinery 4B — Micro-Class                  │
│  Qwen 3.5 4B, LoRA r=32 alpha=16, LR 2e-5       │
│  100K pairs, ~15s/step, ~13hr total              │
│  VRAM: 24GB / 32GB                               │
│  Power: ~150W                                    │
│  Purpose: edge deployment, Jetson/Spark, mining   │
├──────────────────────────────────────────────────┤
│  GPU 1: RTX PRO 6000 Blackwell (96GB)            │
│  SwarmRefinery 9B — Edge-Class                   │
│  Qwen 3.5 9B, LoRA r=64 alpha=32, LR 1e-5       │
│  100K pairs, ~24s/step, ~18hr total              │
│  VRAM: 66GB / 96GB                               │
│  Power: ~350W                                    │
│  Purpose: primary ops brain, DGX Spark            │
└──────────────────────────────────────────────────┘
  Total rig power: ~500W for TWO simultaneous cooks
  A single 4090 Ti does ONE cook at 450W.
  Blackwell efficiency.
```

### Why Two Sizes?

Same data. Same soul. Different bodies.

**SwarmRefinery 9B** — the primary brain. Runs on DGX Spark (128GB). Deeper reasoning, longer reports, better edge-case judgment. The ops center.

**SwarmRefinery 4B** — the micro brain. Runs on Jetson (8GB) or any GPU. Faster inference, lighter footprint. Deploys as a mining node that ALSO audits. The scout.

**The plan:** Eval both on the same 5-point checklist. If the 4B scores within 90% of the 9B — run the 4B everywhere and save the 9B for complex audits. Efficiency is king.

---

## The 5-Point Eval

Both models evaluated against:

```
1. AUDIT        — Can it assess a dataset for defendability?
                  Input: dataset metadata with missing proofs
                  Expected: identify gaps, recommend fixes

2. CALCULATE    — Can it compute cost-per-honey and explain trends?
                  Input: epoch economics data
                  Expected: correct math + interpretation

3. REPORT       — Can it write an epoch report?
                  Input: epoch yield + fleet stats
                  Expected: structured analysis + recommendations

4. ESCALATE     — Can it design an escalation policy?
                  Input: fleet composition + task tier
                  Expected: phase timing + model assignment

5. CLASSIFY     — Can it handle honey/jelly/propolis edge cases?
                  Input: attempt with score 0.89-0.95
                  Expected: classification with reasoning
```

Pass = the model understands the refinery.
Fail = needs more training data or bigger model.

---

## The Decision Tree

```
4B passes 5/5 → Deploy 4B everywhere. Efficiency wins.
4B passes 3/5 → Deploy 9B for ops, 4B for mining only.
4B fails      → 9B is the brain. 4B stays base.
9B passes 5/5 → Ship it. DGX Spark #1 gets the brain.
9B fails      → Cook the 27B. Sometimes you need the big model.
```

No ego. No "we built a 27B so we must use it." Right-size the silicon. The cheapest model that passes the eval wins.

**Efficiency is king. That's miner rule #1.**

---

## Deployment — The Fleet

```
DGX Spark #1  →  SwarmRefinery 9B (24/7 ops brain)
DGX Spark #2  →  Mining: 27B Q4 specialist
DGX Spark #3  →  Mining: 9B FP16 workhorse
DGX Spark #4  →  Mining: 9B FP16 workhorse
DGX Spark #5  →  Training / hot spare / burst
RTX PRO 6000  →  Cooking (the foundry — heavy LoRA runs)
RTX PRO 4500  →  Mining: 4B GPU tier
RTX 3090 Ti   →  Mining: 7B Whale tier
Jetson Orin   →  Edge: SwarmRefinery 4B or SwarmBuddy
Xeon 3475     →  Bee swarm: 25× 3B CPU miners
```

10 nodes. 6 silicon tiers. The mining operations center has its own dedicated hardware. SwarmProtocol.

---

## Why This Matters

Nobody builds refinery models. Everyone builds domain models — legal AI, medical AI, finance AI. Those models answer questions. SwarmRefinery doesn't answer questions. It **runs the operation**.

It's the difference between a miner and the mining foreman. Between a trader and the trading floor. Between a model and the system that makes models trustworthy.

**SwarmRefinery makes the swarm's output DEFENDABLE and BANKABLE.**

It doesn't mine blocks — it certifies them.

---

*"Anyone can sell rows. We sell defendable inventory."*

*SwarmRefinery is the model that makes inventory defendable.*
