# Finding: 27B Is Not Production Grade for SwarmChain

**The 27B overthinks. The 9B decides. The factory needs decisions.**

---

## The Evidence

### In the Arena (Mining)
```
27B (Atlas):     0% honey rate, 108K energy per attempt
9B (base):      24% honey rate, 354 energy per attempt
4B (GPU):        8% honey rate, cheapest correct answers

27B contribution to mining: ZERO
```

### As Judge (Validation)
```
27B Q8 judge:    60-96 seconds per verdict
9B Q4 judge:     5-10 seconds per verdict
Quality:         SAME structured output (VERDICT/SCORE/CLASS)

27B was the bottleneck: 0.7 pairs/min
After switching to 9B: 4.5 pairs/min — 6.4x faster
```

### The Pattern

The 27B overthinks in EVERY role:
- Mining: overthinks the grid transform, produces wrong answers
- Judging: overthinks a PASS/FAIL classification, wastes 60-96 seconds
- Both cases: the 9B produces equal or better results in a fraction of the time

---

## Why This Happens

The 27B has MORE parameters, which means:
- More reasoning paths explored before committing
- Longer thinking chains (Qwen 3.5 think mode amplifies this)
- More hedging, more nuance, more qualification
- All of which HURTS decisive tasks like scoring and classification

For tasks that need JUDGMENT (yes/no, score, classify), the 9B is:
- Decisive: commits to an answer faster
- Structured: follows output format more reliably
- Efficient: 6x less compute for the same quality output

---

## Where 27B Might Still Fit

The 27B's strength is DEPTH — long-form analysis, nuanced reasoning, complex multi-step problems. Potential uses:

- Epoch analysis reports (Shift 2 cooldown — reading 500 blocks of data)
- Complex client reports (not per-pair, but per-domain analysis)
- Edge case arbitration (when the 9B judge is uncertain)
- Protocol design (thinking about the system, not executing in it)

But for the FACTORY FLOOR — mining, judging, validating — the 27B is the wrong tool.

---

## The Doctrine Update

```
MINING:      4B bees + 9B closers (no 27B)
VALIDATION:  4B inspectors + 9B judges (no 27B)
RECORDING:   9B Katniss (no 27B)
ANALYSIS:    27B (offline, batch, strategic — not real-time)

The 27B is the consultant, not the worker.
Call it when you need a report.
Don't put it on the assembly line.
```

---

## The Numbers

```
BEFORE (27B judge):
  0.7 pairs/min
  130+ hours for 5,278 pairs
  96GB VRAM consumed
  60-96s per verdict

AFTER (9B judge):
  4.5 pairs/min
  ~19 hours for 5,278 pairs
  5.5GB VRAM per judge (4 judges = 22GB)
  5-10s per verdict

  6.4x faster
  77% less VRAM
  Same quality
```

Efficiency is king. Right-size the silicon. The 27B taught us that bigger is not better for production.

---

*"The 27B is a scholar in a factory. Brilliant but slow. The factory needs workers who decide, not contemplate."*

---

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
