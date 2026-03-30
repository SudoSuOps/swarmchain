# SwarmChain

**The Sovereign AI Validation & Deed Recording System.**

SwarmChain is a vertically integrated stack for validating AI training pairs and recording them as titled deeds on-chain. Every pair is judged, scored, classified, and sealed — with full provenance from raw data to recorded deed.

```
Raw Pairs → Refinery (Judge + Recorder) → Titled Deeds → Hedera Anchor
```

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        SwarmOS CLI                              │
│  profile → flightsheet → calibrate → POJ → run → close         │
├────────────────────────────────────────────────────────────────┤
│                        Refinery                                 │
│  Judge (9B base) → Classify → Recorder (2B base) → Deed        │
├────────────────────────────────────────────────────────────────┤
│                   SwarmChain Backend                             │
│  Blocks → Attempts → Finality → Rewards → Hedera Anchor        │
├────────────────────────────────────────────────────────────────┤
│                     Infrastructure                              │
│  PostgreSQL · llama-server · GGUF models · Hedera HCS           │
└────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install SwarmOS CLI
pip install -e .

# Profile hardware
swarmos profile

# Generate flight sheet
swarmos flightsheet finance --pairs 14366 --lock

# Generate Proof of Job (pre-closing)
swarmos poj generate <job_id> --client "Your Company"

# Authorize
swarmos poj sign <job_id>

# Execute
swarmos run <job_id>

# Generate closing statement
swarmos close <job_id>
```

## The Seven Documents

| # | Document | When | CRE Analogy |
|---|----------|------|-------------|
| 1 | **HardwareProfile** | Before anything | Property survey |
| 2 | **FlightSheet** | Before job | Construction plans |
| 3 | **CalibrationReport** | Before pricing | Appraisal |
| 4 | **POJ (Proof of Job)** | Before launch | Loan Estimate / Pre-Closing |
| 5 | **EpochProgress** | During job | Construction inspections |
| 6 | **ClosingStatement** | After job | Closing Disclosure / HUD-1 |
| 7 | **Hedera Anchor** | After close | Recorded deed at courthouse |

## Project Structure

```
swarmchain/
├── swarmos/              # CLI operating system (Python)
│   ├── cli.py            # Click CLI entry point
│   ├── profiler.py       # Hardware detection
│   ├── flightsheet.py    # Flight sheet generator
│   ├── calibrate.py      # 50-pair calibration test
│   ├── poj.py            # Proof of Job (pre-closing)
│   ├── permit.py         # Build permits
│   ├── epoch.py          # Epoch runner (judge + recorder)
│   ├── closing.py        # Closing statement generator
│   ├── models.py         # Pydantic data models (7 documents)
│   ├── config.py         # Configuration + system prompts
│   ├── state.py          # File-based job persistence
│   ├── algos.py          # Algorithm registry (12 domains)
│   └── hardware/         # GPU/CPU/power detection
│
├── refinery/             # The Intelligence Refinery
│   ├── pipeline.py       # End-to-end validation orchestrator
│   ├── judge.py          # Judge phase (9B base model)
│   ├── recorder.py       # Recorder phase (2B base model)
│   ├── classifier.py     # Score-only 3-tier classification
│   └── domains/          # Domain-specific prompts & config
│       ├── finance.py
│       ├── medical.py
│       ├── aviation.py
│       ├── cre.py
│       ├── legal.py
│       ├── failure.py
│       └── ...           # 18 domain configs
│
├── backend/              # SwarmChain Distributed Reasoning Ledger
│   └── swarmchain/
│       ├── main.py       # FastAPI app
│       ├── config.py     # Backend settings
│       ├── api/          # 14 REST endpoint modules
│       ├── db/           # SQLAlchemy models + engine
│       ├── schemas/      # Pydantic request/response
│       └── services/     # Controller, verifier, finality,
│                         # rewards, lineage, reputation,
│                         # economics, hedera anchor
│
├── verification/         # Chain verification & audit tools
├── fleet/                # Fleet management scripts
├── models/               # Base model manifest + download
├── simulator/            # Node simulation for testing
├── frontend/             # React block explorer
├── infra/                # Docker Compose + nginx
├── docs/                 # Glass Wall architecture docs
└── tests/                # Full test suite
```

## Validation Domains

| Domain | Algo | Status | Pairs |
|--------|------|--------|-------|
| finance | validate-finance | EPOCH COMPLETE | 14,366 → 4,072 honey |
| failure | validate-failure | ACTIVE | 5,278 |
| cre | validate-cre | READY | 45,039 raw |
| medical | validate-medical | READY | — |
| aviation | validate-aviation | READY | — |
| legal | validate-legal | READY | — |
| grants | validate-grants | PLANNED | — |
| marketing | validate-marketing | READY | — |
| signal | validate-signal | READY | — |
| junior | validate-junior | READY | — |
| curator | validate-curator | READY | — |
| router | validate-router | READY | — |

## Base Models (Validation Chain)

| Role | Model | Quant | VRAM |
|------|-------|-------|------|
| Judge | Qwen3.5-9B | Q4_K_M | 6.2 GB |
| Recorder | Qwen3.5-2B | Q4_K_M | 1.5 GB |

**Policy: BASE MODELS ONLY.** No fine-tuned models in the validation chain.

## The Metric: Cost to Mint

```
SwarmChain: cost to mint 1 deed = electricity + silicon + chain fees

The token is the PAIR.
The hash is the VERDICT.
The block reward is the TITLE DEED.
The hashrate is VERDICTS PER MINUTE.
The efficiency is PAIRS PER WATT.

MEASURED BASELINE (Epoch 2):
  Cost to mint:    $0.0008/deed
  System power:    723W
  Recording:       19 deeds/min
  Break-even:      $0.005/deed
```

## Pair Locations

| Dataset | Path | Lines | Status |
|---------|------|-------|--------|
| Finance honey | `/data1/swarm-honey/finance/finance_honey.jsonl` | 14,366 | Input |
| Finance validated | `/data1/swarm-honey/finance/validated/` | 17,700 receipts | Complete |
| Failure intelligence | `/data1/swarm-honey/failure/failure_intelligence.jsonl` | 5,278 | Input |
| CRE capital | `swarm_cooks/cre_capital/swarmcapitalmarkets_train.jsonl` | 45,039 | Raw |
| Bee-Hive agents | `/data2/bee-hive-v1/pairs/` | 112,388 | Training |

## Development

```bash
# Backend
cd backend && pip install -r requirements.txt
make dev  # uvicorn on :8000

# Tests
make test

# Docker (full stack)
make up
```

---

*SwarmChain — Defendable Commercial Compute Intelligence Refinery*

*Swarm & Bee — Caballerz Network LLC*
