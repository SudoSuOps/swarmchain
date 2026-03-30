# SwarmEval — Defendable Model Evaluation

**Drop your model in the chain. Hunger games. Winner take all.**

SwarmEval is not a benchmark. It's a **live combat evaluation** where models compete on procedural tasks, scored deterministically, receipted on-chain, anchored to Hedera. Can't be gamed. Can't be faked. Can't be memorized.

---

## The Problem

Every AI company has the same question: **"Is my model good?"**

Current answers are broken:

```
MMLU:           contaminated — models train on the test set
HumanEval:      leaked — solutions are in the training data
Chatbot Arena:  vibes — crowdsourced preference, not truth
Leaderboards:   gamed — companies cherry-pick what they win
Internal eval:  unverifiable — "trust us, it's good"
```

Nobody trusts anyone else's eval numbers. Because they shouldn't.

---

## The SwarmEval Answer

Drop your model in the chain. The chain evaluates it.

```
1. INGEST    → Client submits model as a SwarmChain node
2. EXECUTE   → Chain throws procedural tasks at it (fresh, never seen before)
3. SCORE     → Deterministic verification (grid match, schema check, proof)
4. COMPETE   → Client model vs the entire silicon ladder, same tasks
5. RECEIPT   → Every attempt logged: score, energy, strategy, latency
6. VERDICT   → Full evaluation report, Hedera-anchored
```

**The evaluation is not a score. It's an X-ray.**

---

## Multi-Node Eval — Who Validates the Validator?

SwarmEval doesn't use one judge. It uses the **entire swarm**.

```
Traditional eval:
  Model → Single benchmark → Score
  Problem: who validates the benchmark?

SwarmEval:
  Model → Competes against N other models → Same tasks → Same scoring
  The FLEET is the validator. Consensus across silicon tiers.
```

If your model scores 0.95 on a task and three other models independently score 1.0 on the same task — your model has a gap. Not because a judge said so. Because the math shows it.

**Lineage of evaluation:** Every score has a provenance chain. Which task, which input, which model, what attempt, what score, who else attempted it, what they scored. The evaluation is as defendable as the data.

---

## Hunger Games — Winner Take All

Models don't just get scored. They **compete**.

```
Block opens: "Flip grid horizontally + apply color remap"

  Model A (client):     0.750  — jelly, almost there
  Model B (base-9b):    1.000  — honey, solved it
  Model C (swarmjelly): 0.900  — jelly, close
  Model D (bee-3b):     0.450  — propolis, wrong approach

  Winner: Model B
  Reward: 40% solver fee

  But Model A ALSO learns:
  - It scored 0.750 vs the winner's 1.000
  - It was competitive with swarmjelly (0.900)
  - It beat bee-3b (0.450)
  - The gap is 0.250 — specifically on color remap
  - Lineage: if Model A's attempt helped Model B → lineage reward
```

**The client doesn't just learn "my model scored 75%."**
They learn: "my model breaks on color remap in compositional tasks, it's competitive with 4B fine-tuned models but loses to 9B on multi-step reasoning, and it's energy-efficient when it works."

That's not a benchmark. That's a diagnostic.

---

## Failure Intelligence

SwarmEval doesn't just tell you what your model gets RIGHT. It maps what it gets WRONG.

```
Model Pain Point Analysis:

  Transform          Solve Rate    Vs Fleet Avg    Diagnosis
  ─────────────────────────────────────────────────────────
  mirror_h           89%           vs 92%          On par
  rotate_90          71%           vs 85%          Below average
  color_swap         45%           vs 78%          WEAK SPOT
  border_add         12%           vs 34%          CRITICAL GAP
  mirror_h+rotate    3%            vs 41%          BREAKS on composition
  flood_fill         0%            vs 8%           No capability

  Failure Mode: Model handles single transforms but CANNOT compose.
  Root cause: Likely missing multi-step reasoning in training data.
  Recommendation: Add compositional examples to fine-tuning mix.
```

**The chain doesn't just score. It DIAGNOSES.** It identifies exactly where the model breaks, maps it against the fleet for context, and provides actionable intelligence.

This is what SwarmRefinery reads. This is the audit. This is the glass wall into model capability.

---

## Reproducibility — Run It Again

Every SwarmEval result is reproducible:

```
task_id + model + seed = same input → same output → same score
```

A client can challenge any result:
- "Re-run task arc-gen-10042 against my model"
- Same input grid, same scoring function, same result
- Hedera anchor proves the original result existed at timestamp T
- If the re-run matches → evaluation is CONFIRMED
- If it doesn't → something changed (model version, quantization, etc.)

**Reproducibility IS the trust layer.** Not "we ran it once and here's the number." But "run it yourself, you'll get the same answer."

---

## The Eval Stack

```
┌─────────────────────────────────────────────┐
│  TASK INGESTION                             │
│  Procedural generator → fresh tasks         │
│  25 transform types × 4 difficulty tiers    │
│  Can't be memorized. Can't be pre-trained.  │
├─────────────────────────────────────────────┤
│  EXECUTION                                  │
│  Client model joins as SwarmChain node      │
│  Competes against silicon ladder fleet      │
│  Same tasks, same time, same rules          │
├─────────────────────────────────────────────┤
│  CHAIN RECORD                               │
│  Every attempt: score, energy, latency      │
│  Every lineage edge: who improved on who    │
│  Every block: sealed with full provenance   │
├─────────────────────────────────────────────┤
│  VERDICT                                    │
│  Honey/jelly/propolis classification        │
│  Pain point analysis                        │
│  Fleet comparison (your model vs the swarm) │
│  Failure intelligence (where it breaks)     │
│  Hedera-anchored proof of results           │
├─────────────────────────────────────────────┤
│  DEFENDABLE AUDIT                           │
│  SwarmRefinery 9B reviews the evaluation    │
│  Generates client-ready report              │
│  Recommendations for model improvement      │
│  Reproducibility guarantee                  │
└─────────────────────────────────────────────┘
```

---

## SwarmEval vs Everything Else

| Feature | LMSYS Arena | HuggingFace LB | SwarmEval |
|---------|-------------|----------------|-----------|
| Tasks | Static prompts | Static benchmarks | **Procedural, fresh** |
| Scoring | Human preference | Auto metrics | **Deterministic verification** |
| Gameable | Yes (prompt engineering) | Yes (train on test) | **No (tasks are new)** |
| Proof | None | None | **Hedera-anchored** |
| Multi-model | Pairwise only | Independent | **Fleet competition** |
| Failure analysis | No | No | **Yes — pain point mapping** |
| Energy tracking | No | No | **Yes — cost per score** |
| Reproducible | Partially | Yes | **Yes + cryptographic proof** |
| Live visual | No | No | **Glass wall — watch it happen** |

---

## The Business Model

```
Client pays for:
  1. Evaluation epoch (N blocks of eval tasks)
  2. SwarmRefinery audit report
  3. Pain point analysis + recommendations

Swarm & Bee receives:
  1. Evaluation fee
  2. Data from client model's attempts (honey/jelly/propolis)
  3. Fleet comparison data (improves the silicon ladder)

Double value: client pays for eval, we get data. Same block.
```

---

## The One-Liner

**SwarmEval: Drop your model in the chain. Watch it compete. Get the X-ray. Hedera-anchored. Defendable.**

*"We don't grade your model. The chain does. And the chain has receipts."*

---

*Sleep on it. The seeds keep planting themselves.*
