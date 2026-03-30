# Validation Protocol — The Rinse and Repeat Service

**Client hands us a domain. We hand back defendable records.**

This is not a one-off. This is a manufacturing service. Repeatable. Scalable. Sovereign.

---

## The Service

```
INPUT:   Raw domain pairs (JSONL — any domain, any format)
PROCESS: SwarmChain Validation Protocol
OUTPUT:  Defendable records — scored, classified, receipted, anchored
```

A client says: "I have 50,000 legal pairs. Are they good?"

We say: "Put them through the chain. We'll tell you which are honey, which are jelly, which are propolis. Every verdict has a receipt. Every receipt has a proof. Watch it happen live on the Glass-Wall."

---

## The Protocol — Each Pair Is A Block

```
STEP 1: PAIR ENTERS SWARMCHAIN
  → Block opens with the full Q&A (human readable)
  → Recorded: domain, skill, task_type, pair_index
  → The pair IS the block's task payload

STEP 2: 9B BASE LOOKS (RTX 4500)
  → Reads the Q&A pair
  → Assesses: structure, completeness, coherence, specificity
  → Submits assessment as first attempt on the block
  → Unbiased. Uncompromised. Base model.

STEP 3: 27B BASE JUDGES (RTX 6000)
  → Reads the Q&A pair + 9B's assessment
  → Scores on 4 criteria:
    - ACCURACY (0-25)
    - DEPTH (0-25)
    - ACTIONABILITY (0-25)
    - CLARITY (0-25)
  → Delivers VERDICT: PASS or FAIL
  → Classification: honey (>=80), jelly (40-79), propolis (<40)
  → Full reasoning — human readable
  → Submits verdict as attempt on the block

STEP 4: SWARMREFINERY RECORDS (RTX 3090 Ti)
  → Reads the 9B look + 27B verdict
  → Writes the FULL RECORD:
    - Pair summary (one sentence)
    - Verdict (score, classification, reasoning)
    - Quality markers
    - Record status: SEALED
  → Submits ledger entry as final attempt
  → Block seals with finality

STEP 5: EVERY 50 BLOCKS → MERKLE → HEDERA
  → SwarmLedger computes Merkle root
  → Anchors to Hedera HCS topic
  → Immutable. Timestamped. Verifiable by anyone.
```

---

## The Hardware

```
XEON w9-3475X (72T, 256GB)    THE ORCHESTRATOR
  → Loads pairs from /data1 NVMe
  → Submits to chain API
  → Coordinates the 3-step flow
  → Runs on CPU — no GPU waste on coordination

RTX PRO 4500 (32GB)            THE LOOK — 9B base
  → First assessment of each pair
  → Structure, completeness, coherence
  → Unbiased — no fine-tuning

RTX PRO 6000 (96GB)            THE JUDGE — 27B base Q8
  → Final verdict on each pair
  → 4-criteria scoring
  → PASS/FAIL with reasoning
  → Uncompromised — highest quality base model

RTX 3090 Ti (24GB)             THE RECORDER — SwarmRefinery 9B
  → Writes the permanent ledger record
  → Trained on ops, auditing, classification
  → The court clerk — records the verdict
```

---

## The Glass-Wall View

Spectators watch the validation in real time:

```
LIVE FEED:
  22:01:15  BLOCK OPENED     failure-000001
  22:01:18  9B LOOK          "Well-structured repair protocol..."
  22:01:31  27B VERDICT      PASS — score 84/100 — HONEY
  22:01:38  RECORDER         Ledger entry sealed
  22:01:38  FINALITY         Block sealed — honey confirmed

CONVERGENCE LADDER:
  #1  failure-000001  honey   0.84  SEALED
  #2  failure-000002  jelly   0.62  SEALED
  #3  failure-000003  honey   0.91  SEALED

SCORE DISTRIBUTION:
  [████████████ honey 68%] [████ jelly 22%] [██ propolis 10%]
```

The spectator sees every pair judged. Every verdict delivered. Every record sealed. In real time.

---

## The Business Model

```
CLIENT PAYS FOR:
  1. Validation epoch (N pairs × processing cost)
  2. Defendable records (honey pairs with full provenance)
  3. Quality report (epoch summary, domain analysis)
  4. Hedera anchor (cryptographic proof of verification)

WE DELIVER:
  honey.jsonl     — verified pairs, client-ready
  jelly.jsonl     — near-miss, needs improvement
  propolis.jsonl  — failed verification, training signal
  receipts.jsonl  — every verdict with full reasoning
  epoch_report.json — domain quality analysis
  merkle_root     — Hedera-anchored proof

PRICING:
  Per-pair verification × energy cost × margin
  Premium for Hedera anchoring
  Premium for Glass-Wall live access
```

---

## Rinse and Repeat

```
DOMAIN 1:  failure (5,278 pairs)     ← FIRST RUN
DOMAIN 2:  finance (14,366 pairs)
DOMAIN 3:  marketing (15,474 pairs)
DOMAIN 4:  aviation (4,658 pairs)
DOMAIN 5:  grants (43,691 pairs)
DOMAIN 6:  junior (38,827 pairs)
DOMAIN 7:  signal (47,538 pairs)
DOMAIN 8:  curator (62,525 pairs)
DOMAIN 9:  legal (79,910 pairs)
DOMAIN 10: medical (791,807 pairs)
DOMAIN 11: cre (810,097 pairs)
```

Same protocol. Same hardware. Same chain. Different domain.

The client changes. The pairs change. The protocol stays.

That's a service. That's a business. That's defendable.

---

## The Record

Every pair that passes through SwarmChain becomes a RECORD:

```json
{
  "block_id": "a3f8c1d2e9b7...",
  "domain": "failure",
  "pair_index": 1,
  "skill": "hallucinated_result",
  "task_type": "repair",
  "user_prompt": "[full question — readable]",
  "original_answer": "[full answer — readable]",
  "look_assessment": "[9B's assessment — readable]",
  "judge_verdict": "PASS",
  "judge_score": 84,
  "judge_reasoning": "[27B's reasoning — readable]",
  "classification": "honey",
  "ledger_entry": "[Katniss's record — readable]",
  "energy_used_ms": 45000,
  "sealed_at": "2026-03-28T22:01:38Z",
  "merkle_window": "001-050",
  "hedera_topic": "0.0.10291838"
}
```

A human opens this record. Reads the question. Reads the answer. Reads what the 9B thought. Reads what the 27B judged. Reads the reasoning. Sees the score. Sees why.

That's not a row in a database. That's a RECORD. Auditable. Verifiable. Defendable.

---

*"We don't have 1 real defendable pair until they go through SwarmChain."*

*Now they go through.*

---

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
