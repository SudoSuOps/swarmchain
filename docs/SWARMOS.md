# SwarmOS — HiveOS for AI Mining

**HiveOS manages GPU mining rigs. SwarmOS manages AI validation rigs.**

Same discipline. Different hash. Instead of SHA-256, we hash QUALITY.

---

## The Blueprint: HiveOS → SwarmOS

```
HIVEOS                           SWARMOS
──────────────────────────────────────────────────
Flight sheets                    Flight sheets
  algo + OC + pool                 model + power + chain

Worker management                Fleet management
  GPU rigs, ASICs                  RTX, Xeon, Jetson, Sparks, Zimas

Overclocking                     Power tuning
  core/mem/power/fan               power cap, threads, ctx, parallel

Hashrate monitoring              Throughput monitoring
  MH/s per card per algo           deeds/min per GPU per model

Pool connection                  Chain connection
  stratum://pool                   http://swarmchain:8080

Watchdog                         Watchdog
  restart crashed miners           restart crashed model servers

Dashboard                        Glass-Wall
  power, temp, hash, uptime        power, temp, deeds/min, quality

Multi-rig                        Multi-rig
  manage 100s remotely             Rails, Whale, Jetson, Zimas, Sparks

OS-level                         OS-level
  boots to mine                    boots to validate
```

---

## SwarmOS Components

### 1. Flight Sheet Manager

```
Create flight sheets per domain:
  - Model assignments (which model, which GPU, which port)
  - Power targets (80% capacity)
  - Throughput estimates
  - Quality baselines

Save templates. Clone for new epochs.
Compare actual vs predicted after each run.

flight-sheet-failure-v1.json
flight-sheet-cre-v1.json
flight-sheet-medical-v1.json
```

### 2. Fleet Controller (swarm_ctl.sh → SwarmOS)

```
swarm up              start full stack
swarm down            stop + backup
swarm status          all rigs, all GPUs, all models
swarm epoch 500       fire epoch from Zima-2
swarm flightsheet     load/save/compare flight sheets
swarm power           real-time power per GPU
swarm watchdog        enable auto-restart
```

### 3. Worker Management

```
RAILS:     Xeon + RTX 4500 + RTX 6000
WHALE:     RTX 3090 Ti
JETSON:    Orin Nano 8GB
ZIMA-2:    Controller appliance
ZIMA-LITE: 20× micro-bee nodes
SPARKS:    5× DGX Spark 128GB (arriving)

Each worker:
  - Heartbeat (health check every 30s)
  - Power draw (real-time watts)
  - Throughput (deeds/min or attempts/min)
  - Temperature (throttle warning at 85°C)
  - Model status (loaded, serving, crashed)
```

### 4. Power Tuning

```
Per GPU:
  Power cap (nvidia-smi -pl)
  Target utilization (80%)
  Temperature limit
  Fan curve

Per model:
  Thread count
  Context size
  Batch size
  Parallel instances

The miner's art:
  Find the sweet spot where
  throughput is 95% of max
  at 70% of peak power.
  Lock it. Run it. 24/7.
```

### 5. Watchdog

```
Monitor every model server every 30 seconds:
  curl -s http://host:port/health

If DOWN for 3 consecutive checks:
  1. Log the failure
  2. Kill the process
  3. Restart with same flight sheet config
  4. Alert on Glass-Wall
  5. Resume from last good state

No manual intervention. Self-healing fleet.
```

### 6. Glass-Wall Integration

```
SwarmOS feeds the Glass-Wall:
  - Fleet status (which rigs online)
  - Power draw per GPU (real-time watts)
  - Model throughput (deeds/min per judge)
  - Temperature map
  - Epoch progress
  - Quality metrics (honey rate trending)

The spectator sees the factory running.
SwarmOS is the factory floor manager.
The Glass-Wall is the observation deck.
```

---

## Flight Sheet Schema

```json
{
  "name": "failure-validation-v3",
  "algo": "domain_pair_validation",
  "domain": "failure",
  "created": "2026-03-29",

  "workers": [
    {
      "rig": "rails",
      "gpu": "RTX PRO 4500",
      "gpu_index": 0,
      "power_cap_w": 150,
      "power_target_pct": 80,
      "models": [
        {"role": "judge", "model": "Qwen3.5-9B-Q4", "port": 8204, "vram_gb": 5.5},
        {"role": "judge", "model": "Qwen3.5-9B-Q4", "port": 8205, "vram_gb": 5.5},
        {"role": "inspector", "model": "Qwen3.5-4B-Q4", "port": 8211, "vram_gb": 2.5},
        {"role": "inspector", "model": "Qwen3.5-4B-Q4", "port": 8212, "vram_gb": 2.5}
      ]
    },
    {
      "rig": "rails",
      "gpu": "RTX PRO 6000",
      "gpu_index": 1,
      "power_cap_w": 300,
      "power_target_pct": 80,
      "models": [
        {"role": "judge", "model": "Qwen3.5-9B-Q4", "port": 8201, "vram_gb": 5.5},
        {"role": "judge", "model": "Qwen3.5-9B-Q4", "port": 8202, "vram_gb": 5.5},
        {"role": "judge", "model": "Qwen3.5-9B-Q4", "port": 8203, "vram_gb": 5.5},
        {"role": "judge", "model": "Qwen3.5-9B-Q4", "port": 8206, "vram_gb": 5.5},
        {"role": "judge", "model": "Qwen3.5-9B-Q4", "port": 8207, "vram_gb": 5.5},
        {"role": "inspector", "model": "Qwen3.5-4B-Q4", "port": 8210, "vram_gb": 2.5}
      ]
    },
    {
      "rig": "whale",
      "gpu": "RTX 3090 Ti",
      "gpu_index": 0,
      "power_cap_w": 480,
      "power_target_pct": 55,
      "models": [
        {"role": "recorder", "model": "Katniss-9B-Q4", "port": 8097, "vram_gb": 5.5}
      ]
    }
  ],

  "orchestrator": {
    "rig": "rails",
    "cpu": "Xeon w9-3475X",
    "script": "orchestrate_v2.py"
  },

  "targets": {
    "pairs_per_min": 5.0,
    "watts_per_deed": 100,
    "honey_rate_baseline": 0.20,
    "gpu_util_target": 0.80
  },

  "calibration": {
    "test_pairs": 50,
    "27b_rejected": true,
    "9b_accepted": true,
    "notes": "27B overthinks, 9B decisive. 4B inspectors at 1-2s. 80% sweet spot."
  }
}
```

---

## The Product Roadmap

```
v0.1 (NOW):      swarm_ctl.sh + swarm_fleet.sh
                  Manual flight sheets. Manual power tuning.

v0.2:            SwarmOS CLI
                  swarm flightsheet load/save
                  swarm power tune <gpu> <watts>
                  swarm watchdog enable

v0.3:            SwarmOS Dashboard (Glass-Wall integration)
                  Real-time power/temp/throughput
                  Fleet map (all rigs)
                  Flight sheet comparison

v1.0:            SwarmOS Full
                  Remote rig management (like HiveOS)
                  Auto-calibration (run 50 pairs, recommend config)
                  Flight sheet templates per domain
                  Watchdog + self-healing
                  Multi-epoch scheduling
```

---

## The Parallel

```
HiveOS built the operating system for crypto mining.
  1M+ rigs managed worldwide.
  Flight sheets. Overclocking. Watchdog. Dashboard.

SwarmOS builds the operating system for AI validation.
  Same discipline. Same efficiency.
  Flight sheets. Power tuning. Watchdog. Glass-Wall.

The difference:
  HiveOS produces hashes.
  SwarmOS produces title deeds.

  Hashes have no meaning.
  Title deeds have value.
```

---

*SwarmOS: the operating system that makes AI validation a factory operation.*

*Swarm & Bee — Defendable Commercial Compute Intelligence Refinery*
