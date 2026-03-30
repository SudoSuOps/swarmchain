# SwarmChain Base Models

**Policy: BASE MODELS ONLY in the validation chain.**

No fine-tuned models. No custom builds. No compromised weights.
The judge thinks. The recorder writes. Separation of concerns.

## Validation Chain (Active)

| Role | Model | Quant | VRAM | Hardware | Path |
|------|-------|-------|------|----------|------|
| **Judge** | Gemma-3 12B IT | Q4_K_M | 8.0 GB | **GPUs** | `gemma-3-12b-it-Q4_K_M.gguf` |
| **Recorder** | Gemma-2 2B IT | Q4_K_M | 1.6 GB | **CPUs / Edge** | `gemma-2-2b-it-Q4_K_M.gguf` |

## Hardware Assignment

```
GPUs     → Judge (Gemma-3 12B)   — deep reasoning, quality verdicts
CPUs     → Recorder (Gemma-2 2B) — fast deed writing, /no_think
Edge     → Recorder (Gemma-2 2B) — distributed recording at the edge
```

## Classification Tiers

```
royal-jelly   >= 0.75   The king. Production-grade training data.
honey         >= 0.50   Usable. Improvement candidate.
propolis      <  0.50   Low quality. Rejected from training.
```

## Why These Models

**Gemma-3 12B** — Google's best open-weight reasoning model at the 12B scale.
Deeper than 9B Qwen, better at nuanced quality assessment. Fits on RTX PRO 4500 (32GB).
Two instances on RTX PRO 6000 (96GB) with room to spare.

**Gemma-2 2B** — Smallest model that writes clean, structured output.
Recording a deed doesn't require intelligence — it requires format compliance.
Runs on CPU with AMX acceleration. Runs on edge devices. Runs everywhere.

## Available (on disk, not in chain)

| Model | Quant | Path |
|-------|-------|------|
| Qwen3.5-9B | Q4_K_M | `Qwen3.5-9B-Q4_K_M.gguf` (legacy judge) |
| Qwen3.5-2B | Q4_K_M | `Qwen3.5-2B-Q4_K_M.gguf` (legacy recorder) |
| Qwen3.5-0.8B | Q4_K_M | `Qwen3.5-0.8B-Q4_K_M.gguf` (inspector) |
| Qwen2.5-7B | Q4_K_M | `Qwen2.5-7B-Instruct-Q4_K_M.gguf` |
