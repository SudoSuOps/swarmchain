# Finding: Energy Efficiency in the Validation Factory

**Right-size the model. Right-size the silicon. The factory runs on efficiency, not brute force.**

---

## The Evolution — Same Day, Same Chain

```
CONFIG 1: 27B Judge (the coma)
  RTX 4500:  149W  98%  74°C  — 9B inspector hammering alone
  RTX 6000:   24W   0%  42°C  — 27B sitting idle between pairs
  RTX 3090:   29W   0%  43°C  — Katniss sleeping
  Total:     202W
  Output:    0.7 pairs/min
  Per deed:  247 watts
  THE CHAIN WAS IN A COMA.

CONFIG 2: 4× 9B Judges (the heartbeat)
  RTX 4500:   81W  91%  57°C  — balanced, cooler, more models
  RTX 6000:  102W   0%  51°C  — 3 models, wants more work
  RTX 3090:  264W  95%  65°C  — Katniss ALIVE
  Total:     447W
  Output:    7.3 pairs/min
  Per deed:  61 watts
  THE CHAIN HAD A HEARTBEAT.

CONFIG 3: 7× 9B Judges + 3× 4B Inspectors (the sprint)
  RTX 4500:  155W  91%  57°C  — 2 judges + 1 inspector, full load
  RTX 6000:  223W  high  51°C — 5 judges + 1 inspector, happy at 223W
  RTX 3090:  264W  95%  65°C  — Katniss working steady
  Total:     642W
  Output:    8+ pairs/min
  Per deed:  ~80 watts (all 3 rigs combined)
  ALL STATIONS ACTIVE. THE FACTORY RUNS.
```

---

## The Silicon Efficiency Report

### RTX PRO 6000 Blackwell (96GB, 300W cap)

```
At 24W (27B idle):     $10K of silicon doing NOTHING
At 102W (3 models):    underutilized — card wants 200-300W
At 223W (5 models):    happy range — 26GB/96GB, 70GB headroom
At 300W (max):         could run 12+ 9B models simultaneously

This card is built for 24/7 at 300W. We run it at 50%.
That's efficiency — not lazy silicon, but tuned power.
The 6000 is an underclocked powerhouse.
```

### RTX PRO 4500 Blackwell (32GB, 150W cap)

```
At 149W (1 model):     98% util, 74°C — one model maxing it
At 81W (balanced):     91% util, 57°C — multiple small models
At 155W (full load):   5 models balanced, Blackwell efficiency

The 4500 might be the most efficient Blackwell card period.
200W design. 32GB. Hums at 150W. 17 degrees cooler with 10x output
when right-sized models replace one oversized model.
```

### RTX 3090 Ti (24GB, 480W cap)

```
At 29W (idle):         Katniss sleeping — wasted silicon
At 264W (working):     95% util, recording deeds non-stop
At 480W (max):         never needed — 264W is enough for the task

The 3090 wants work. Feed it deeds. It stamps them.
264W out of 480W = 55% power. Efficient, not maxed.
```

---

## The Lesson

```
1 big model at 100% on 1 GPU:
  Hot. Slow. Bottlenecked. Other GPUs idle.

8 right-sized models across 3 GPUs:
  Cool. Fast. Balanced. All stations active.

Energy per deed: 247W → 61W (4x improvement)
Throughput:      0.7 → 8+ pairs/min (11x improvement)
Temperature:     74°C → 57°C (17° cooler on 4500)
```

The factory doesn't need bigger models. It needs MORE right-sized models working in parallel. The assembly line, not the solo genius.

---

## Power Tuning Insight

```
RTX 6000: 300W cap, running at 223W (74%)
  Could handle 600W uncapped. We tune DOWN to 300W.
  That's 50% power reduction by design.
  Efficiency, not performance — same output, half the watts.

RTX 4500: 150W cap, running at 155W (103%)
  The most efficient Blackwell card in the fleet.
  200W design, hums at 150W.
  32GB of GDDR7 on a 150W envelope.

RTX 3090: 480W cap, running at 264W (55%)
  Old gen but still earns its keep.
  264W for Katniss is plenty.
  The recorder doesn't need peak performance.
```

---

## The Doctrine

*Right-size the model to the task.*
*Right-size the silicon to the model.*
*The factory runs on efficiency, not brute force.*
*A 27B at 24W idle is waste. Seven 9Bs at 223W is production.*

---

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
