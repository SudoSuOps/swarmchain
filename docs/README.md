# Glass Wall

**The process IS the product.**

Open-door inspection of the Swarm & Bee intelligence refinery. See it. Feel it. Touch it. On the browser.

The market message is not words — it's the visual. The ability to watch the algorithm work.

---

## The Story of Block `0d63d78e`

```
8 miners competed. 3 tiers of silicon.
58 seconds from open to seal.
```

A task enters the refinery: *"Flip the grid horizontally (4x5 → 4x5)"*

**What happens next is visible to everyone:**

| Time | Event | Score |
|------|-------|-------|
| 0s | Block opens. 8 miners start working. | — |
| 12s | Xeon bee submits first attempt | 0.450 |
| 18s | Same bee improves | 0.600 → PROMOTED |
| 24s | Three more bees converge | 0.750, 0.750, 0.750 |
| 31s | Jetson edge (sigedge) — a $200 board at 15 watts | 0.700 |
| 44s | GPU-4B drops the hammer | **1.000** — HONEY |
| 58s | Block sealed. Rewards distributed. Next block opens. | ✓ |

**The lineage tells the collaboration story:**

```
xeon-miner (0.750) ──improves──→ gpu-4b (1.000)
                     +0.250
```

The bee's work **led** to the solve. The GPU didn't start from zero — it built on what the bee found. That's why the bee earns the second-highest reward.

**The reward split tells the economic story:**

```
gpu-4b:       40.00  (solver — found the answer)
xeon-bee:     30.00  (lineage — its work led to the solve)
5 bees:       16.50  (exploration — tried different angles)
sigedge:       6.27  (exploration + efficiency — cheapest per score)
everyone:      7.22  (efficiency — proportional to energy)
```

Nobody got nothing. Even the 0.450 attempt earned exploration reward. Every miner contributed. Every contribution is receipted.

**The client sees ALL of this.** Every attempt. Every score. Every node. Every strategy. The lineage graph. The reward split. The energy cost. The seal timestamp.

---

## The Vision

Five glass walls into the refinery:

```
swarmchain.eth     →  watch blocks mine live
swarmepoch.eth     →  watch the harvest accumulate
swarmledger.eth    →  watch proofs anchor to Hedera
swarmenergy.eth    →  watch the economics work
defendable.eth     →  verify any pair yourself
```

You don't explain defendable. You **show** it.

---

## What Makes It Defendable

Every block carries 5 proofs:

1. **Proof of Origin** — which model, which node, which hardware, which strategy
2. **Proof of Quality** — deterministic verification score, not model opinion
3. **Proof of Process** — full lineage: what was tried, what failed, what survived
4. **Proof of Economics** — energy cost per attempt, cost-per-honey trend
5. **Proof of Trust** — Hedera HCS anchor, Merkle root, verifiable by anyone

**Without these proofs, it's just a JSONL file. With them, it's a data asset.**

*"Anyone can sell rows. We sell defendable inventory."*

---

## Who Validates the Validator?

The algorithm is deterministic and public.

```
Attack: "Your scores are wrong"
Defense: Run the scoring function yourself. Same inputs → same output.

Attack: "Your data was tampered"
Defense: Recompute the Merkle tree. Compare to Hedera anchor.

Attack: "Your timestamp is fake"
Defense: Hedera aBFT consensus. Immutable. Public.

Attack: "Your Hedera operator is compromised"
Defense: The topic is public. Messages are append-only.

Attack: "Your scoring function has a bug"
Defense: Open-source the verifier. Multiple implementations must agree.
```

The seal isn't Swarm & Bee's signature. The seal is the cryptographic proof that the data is what we say it is — verifiable by anyone, anchored on Hedera, forever.

**defendable.eth IS the algorithm.**

---

## The Refinery Stack

```
SwarmChain          the mining pool
SwarmEpoch          the harvest viewer
SwarmLedger         the proof layer
SwarmEnergy         the economics engine
SwarmProtocol       the specification
SwarmRefinery       the operations brain (in-house, 9B trained model)
Defendable          the algorithm — the proof system itself
```

---

## Genesis

This repo was born from a conversation about what makes data trustworthy. The answer wasn't a better model or a bigger dataset. The answer was: **show the work.**

A live refinery. Glass walls. Open-door inspection. The process visible to everyone.

The seed is planted. Nature takes care of the rest.

---

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
