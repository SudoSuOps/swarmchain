# SwarmChain Base Models

**Policy: BASE MODELS ONLY in the validation chain.**

No fine-tuned models. No custom builds. No compromised weights.
Base models are unbiased, auditable, and reproducible.

## Active Models

| Role | Model | Quant | VRAM | Location |
|------|-------|-------|------|----------|
| **Judge** | Qwen3.5-9B | Q4_K_M | 6.2 GB | `/data2/models/Qwen3.5-9B-Q4_K_M.gguf` |
| **Recorder** | Qwen3.5-2B | Q4_K_M | 1.5 GB | `/data2/models/Qwen3.5-2B-Q4_K_M.gguf` |
| **Inspector** | Qwen3.5-0.8B | Q4_K_M | 0.8 GB | `/data2/models/Qwen3.5-0.8B-Q4_K_M.gguf` |

## Available (not in validation chain)

| Model | Quant | VRAM | Location |
|-------|-------|------|----------|
| Gemma-3-12B-IT | Q4_K_M | ~8 GB | `/data2/models/gemma-3-12b-it-Q4_K_M.gguf` |
| Gemma-2-2B-IT | Q4_K_M | ~1.5 GB | `/data2/models/gemma-2-2b-it-Q4_K_M.gguf` |
| Qwen2.5-7B-Instruct | Q4_K_M | ~5 GB | `/data2/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf` |

## Why Base Models

The judge thinks (9B base). The recorder writes (2B base).
You don't hire a lawyer to fill out the deed at the courthouse.

Fine-tuned models introduce bias into the validation chain.
The refinery must be neutral ground — the pairs are what get trained, not the judges.
