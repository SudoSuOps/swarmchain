# Flight Sheet — Epoch 1 Validation

**Algorithm: Validation | Token: 9B Base / 4B Base | Clocks: Blackwell + Ampere**

*Locked before epoch. Do not modify mid-run.*

---

## ALGO: Domain Pair Validation

```
Protocol:    inspect → judge → record → seal
Domain:      failure intelligence
Pairs:       5,278
Session:     epoch-1-validation-failure
```

---

## TOKEN: Model Configuration

```
INSPECTORS (4B base — the quick look):
  Model:    Qwen 3.5 4B Q4_K_M
  VRAM:     2.5GB per instance
  Speed:    1-2 seconds per look
  Role:     structure, completeness, coherence
  Thinking: enabled (Qwen default)
  Instances: 3

JUDGES (9B base — the verdict):
  Model:    Qwen 3.5 9B Q4_K_M
  VRAM:     5.5GB per instance
  Speed:    5-10 seconds per verdict
  Role:     score, classify, reason
  Thinking: enabled (Qwen default)
  Output:   VERDICT / TOTAL_SCORE / CLASSIFICATION / REASONING
  Instances: 7

RECORDER (Katniss 9B — the closing agent):
  Model:    SwarmRefinery 9B v1 Q4_K_M
  VRAM:     5.5GB
  Speed:    7-10 seconds per record
  Role:     write title deed, seal block
  Thinking: enabled
  Instances: 1
```

---

## CLOCKS: GPU Power Configuration

```
┌────────────────────────────────────────────────────────────────┐
│  GPU 0 — RTX PRO 4500 Blackwell (32GB GDDR7)                  │
│                                                                │
│  Power cap:     150W                                           │
│  Target draw:   114W (76% — sweet spot)                        │
│  Temperature:   54°C (cool, no throttle risk)                  │
│  VRAM used:     27GB / 32GB (83%)                              │
│  Utilization:   91% avg (bursts to 98%)                        │
│                                                                │
│  Models loaded:                                                │
│    :8204  9B judge        5.5GB                                │
│    :8211  4B inspector    2.5GB                                │
│    :8212  4B inspector    2.5GB                                │
│    :8205  9B judge        5.5GB (shared from overflow)         │
│                                                                │
│  Efficiency:    most efficient Blackwell card in fleet          │
│  Note:          200W design, runs at 76% — S21 of AI silicon   │
├────────────────────────────────────────────────────────────────┤
│  GPU 1 — RTX PRO 6000 Blackwell (96GB GDDR7)                  │
│                                                                │
│  Power cap:     300W                                           │
│  Target draw:   138W (46% — has massive headroom)              │
│  Temperature:   54°C (cold, barely working)                    │
│  VRAM used:     26GB / 96GB (27%)                              │
│  Utilization:   variable (round-robin across 5 judges)         │
│                                                                │
│  Models loaded:                                                │
│    :8201  9B judge        5.5GB                                │
│    :8202  9B judge        5.5GB                                │
│    :8203  9B judge        5.5GB                                │
│    :8206  9B judge        5.5GB                                │
│    :8207  9B judge        5.5GB                                │
│    :8210  4B inspector    2.5GB                                │
│                                                                │
│  Headroom:      70GB VRAM free, 162W power free                │
│  Note:          could run 12 more 9B judges                    │
│                 card WANTS 200-300W range                       │
├────────────────────────────────────────────────────────────────┤
│  GPU 2 — RTX 3090 Ti Ampere (24GB GDDR6X)    [WHALE RIG]      │
│                                                                │
│  Power cap:     480W                                           │
│  Target draw:   249W (52% — recorder doesn't need peak)        │
│  Temperature:   66°C (warm but stable)                         │
│  VRAM used:     6GB / 24GB (24%)                               │
│  Utilization:   95% (Katniss working steady)                   │
│                                                                │
│  Models loaded:                                                │
│    :8097  Katniss 9B      5.5GB                                │
│                                                                │
│  Note:          old gen, high power, but earns its keep         │
│                 the recorder doesn't need Blackwell             │
└────────────────────────────────────────────────────────────────┘
```

---

## EFFICIENCY METRICS

```
POWER:
  GPU 0:     114W
  GPU 1:     138W
  GPU 2:     249W
  TOTAL:     501W across 3 GPUs

THROUGHPUT:
  Pairs/min:     5.1 (measured at 234 deeds)
  Deeds/hour:    306

ENERGY PER DEED:
  501W ÷ 5.1/min = 98W per deed
  98W × (1/5.1 min) = 1.15 Wh per deed

  At $0.30/kWh: $0.00035 per deed in electricity

COMPARISON TO PREVIOUS CONFIGS:
  27B config:    247W/deed at 0.7/min    GRADE: F
  4× 9B config:  61W/deed at 4.5/min    GRADE: B
  7× 9B config:  98W/deed at 5.1/min    GRADE: A-
  (higher total watts but more deeds — better utilization)
```

---

## QUALITY METRICS (at 234 deeds)

```
  Honey:      49 (20.9%)
  Jelly:       2 (0.9%)
  Propolis:  183 (78.2%)

  Honey rate:    20.9%
  Improvement:   +3.9% vs 27B config (17%)

  Score distribution:
    0.92 — most common honey score
    0.25 — most common propolis score
    0.35 — jelly boundary zone
```

---

## FLEET SUMMARY

```
  11 models across 3 GPUs on 2 rigs

  INSPECTORS:  3× 4B base (ports 8210-8212)
  JUDGES:      7× 9B base (ports 8201-8207)
  RECORDER:    1× Katniss 9B (port 8097, Whale)
  ORCHESTRATOR: Xeon w9-3475X (CPU, Python async)

  Total VRAM:   59GB allocated / 153GB available
  Total power:  501W / 930W capacity (54%)

  Running at 54% total fleet power.
  80% per-card target on active cards.
  The factory hums. It doesn't scream.
```

---

## PRE-FLIGHT CALIBRATION LOG

```
  Test 1 (27B judge):      0.7/min, 247W/deed — REJECTED
  Test 2 (4× 9B judges):   4.5/min, 61W/deed  — IMPROVED
  Test 3 (5× 9B + 3× 4B): 5.1/min, 98W/deed  — ACCEPTED
  Test 4 (7× 9B + 3× 4B): 5.1/min, 98W/deed  — LOCKED

  Finding: 27B overthinks, 9B is decisive
  Finding: 4B inspectors at 1-2s are right-sized
  Finding: 80% GPU capacity is the sweet spot
  Finding: honey rate improved from 17% → 21% with 9B judges
```

---

## LOCK STATUS

```
  ██████████████████████████████████████
  ██                                  ██
  ██    FLIGHT SHEET: LOCKED          ██
  ██    EPOCH 1 VALIDATION            ██
  ██    DO NOT MODIFY MID-RUN         ██
  ██                                  ██
  ██████████████████████████████████████

  Locked at:     2026-03-29 02:00 UTC
  Locked by:     human + AI calibration
  Next review:   after epoch completion

  Changes require: new flight sheet + 50-pair retest
```

---

*The flight sheet is the discipline.*
*Build it before the epoch. Lock it. Learn from it. Improve the next one.*

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
