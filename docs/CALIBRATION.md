# Calibration — Evaluate the Evaluators

**Before you run the chain, tune the chain. Math over energy = capacity.**

---

## The Lesson

We ran the same 5,278 pairs through three configurations:

```
Config 1:  27B judge           → 17% honey, 0.7/min, 247W/deed
Config 2:  4× 9B judges        → 18% honey, 4.5/min, 61W/deed
Config 3:  7× 9B + 3× 4B      → 20.5% honey, 5.1/min, tuned

The 27B OVER-REJECTED good pairs. Overthinking = over-cautious.
The 9B found MORE honey. Decisive = accurate.
```

We discovered this MID-EPOCH. We should have discovered it BEFORE.

---

## The Protocol: Pre-Flight Calibration

Before ANY epoch or validation run, the chain must:

### 1. Model Sizing Test
```
Take 50 sample pairs from the domain.
Run through candidate model sizes: 4B, 7B, 9B, 14B, 27B
Compare:
  - Verdict agreement (do they agree on honey/propolis?)
  - Time per verdict
  - Watts per verdict
  - Honey rate per model

FIND: the smallest model that agrees with the largest model
      90%+ of the time. That's your judge.
```

### 2. Energy Calibration
```
For the chosen model, test fleet configurations:
  1 judge:   baseline watts/deed
  2 judges:  does throughput double? watts per deed?
  4 judges:  diminishing returns?
  7 judges:  where's the sweet spot?

FIND: the configuration where adding more judges
      stops improving throughput proportionally.
      That's your capacity ceiling.
```

### 3. Power Tuning
```
Target: 80% GPU capacity (the miner's sweet spot)

  100% = hot, unstable, marginal gains
   80% = stable, efficient, sustainable 24/7
   60% = underutilized, silicon wasted

Tune power caps per GPU:
  RTX 6000: cap at 240W (80% of 300W)
  RTX 4500: cap at 160W (80% of 200W)
  RTX 3090: cap at 385W (80% of 480W)

Measure: throughput at 80% vs 100%.
         If within 5%, stay at 80%.
```

### 4. Quality Baseline
```
Run 100 pairs through the calibrated fleet.
Measure:
  - Honey rate
  - Score distribution
  - False positive rate (honey that shouldn't be)
  - False negative rate (propolis that should be honey)

ACCEPT: if honey rate is stable and distribution is consistent.
REJECT: if results are erratic — model is wrong for this domain.
```

---

## The Formula

```
MATH ÷ ENERGY = CAPACITY

Math:     model size × verdict quality × agreement rate
Energy:   watts per deed × time per deed
Capacity: pairs per minute at 80% GPU utilization

OPTIMIZE: maximize Capacity
          by minimizing Energy
          without sacrificing Math

The answer is almost never the biggest model.
The answer is the RIGHT-SIZED model at 80% power.
```

---

## What We Proved

```
27B at 100% on 1 GPU:
  Math:     good (but over-cautious)
  Energy:   247W per deed
  Capacity: 0.7/min
  GRADE:    F (factory in a coma)

9B × 7 at 80% across 3 GPUs:
  Math:     better (decisive, higher honey rate)
  Energy:   ~80W per deed
  Capacity: 5+ pairs/min
  GRADE:    A (factory running)
```

---

## Pre-Flight Checklist

Before every epoch:

```
□ Model sizing test (50 sample pairs)
□ Energy calibration (1/2/4/7 judge comparison)
□ Power tuning (target 80% capacity)
□ Quality baseline (100 pair test run)
□ Fleet configuration locked
□ THEN fire the epoch

Never run 5,278 pairs on an untested configuration.
Calibrate first. 50 pairs. Then scale.
```

---

## The Doctrine

*Evaluate the evaluators before they evaluate the data.*

*The 27B taught us that bigger is not better.*
*The energy data taught us that 80% is the sweet spot.*
*The honey rate taught us that decisive beats cautious.*

*Math over energy = capacity.*
*Calibrate before you run.*
*Fine-tune the silicon, not just the models.*

---

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
