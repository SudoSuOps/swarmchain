#!/usr/bin/env bash
# Download base models for SwarmChain validation chain.
# Target: /data2/models/ on swarmrails

set -euo pipefail

MODELS_DIR="${SWARMOS_MODELS_DIR:-/data2/models}"
mkdir -p "$MODELS_DIR"

echo "Downloading base models to $MODELS_DIR..."

# Judge — Qwen3.5-9B-Q4_K_M
if [ ! -f "$MODELS_DIR/Qwen3.5-9B-Q4_K_M.gguf" ]; then
    echo "Downloading Qwen3.5-9B (judge)..."
    huggingface-cli download Qwen/Qwen3.5-9B-GGUF Qwen3.5-9B-Q4_K_M.gguf \
        --local-dir "$MODELS_DIR" --local-dir-use-symlinks False
fi

# Recorder — Qwen3.5-2B-Q4_K_M
if [ ! -f "$MODELS_DIR/Qwen3.5-2B-Q4_K_M.gguf" ]; then
    echo "Downloading Qwen3.5-2B (recorder)..."
    huggingface-cli download Qwen/Qwen3.5-2B-GGUF Qwen3.5-2B-Q4_K_M.gguf \
        --local-dir "$MODELS_DIR" --local-dir-use-symlinks False
fi

echo "Done. Models in $MODELS_DIR:"
ls -lh "$MODELS_DIR"/*.gguf
