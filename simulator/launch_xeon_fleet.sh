#!/bin/bash
# SwarmChain Xeon Fleet Launcher
# Spawns N llama-server instances + N real_worker.py miners
# Designed for Xeon 3475 Sapphire Rapids (72 threads, 256GB RAM)
#
# Usage: ./launch_xeon_fleet.sh <num_miners> <api_key>
# Example: ./launch_xeon_fleet.sh 20 d8b26bc8...

set -euo pipefail

NUM_MINERS="${1:-20}"
API_KEY="${2:?Usage: launch_xeon_fleet.sh <num_miners> <api_key>}"
API_URL="${3:-http://165.227.109.67/api}"
MODEL="/data2/swarmrouter-3b-q4.gguf"
BASE_PORT=9100
THREADS_PER_MINER=3  # 20 miners × 3 threads = 60 of 72 threads

echo "============================================"
echo "  SwarmChain Xeon Fleet Launcher"
echo "============================================"
echo "  Miners:    ${NUM_MINERS}"
echo "  Model:     ${MODEL}"
echo "  Threads:   ${THREADS_PER_MINER} per miner (${NUM_MINERS}×${THREADS_PER_MINER}=$((NUM_MINERS * THREADS_PER_MINER)) total)"
echo "  API:       ${API_URL}"
echo "  Ports:     ${BASE_PORT}-$((BASE_PORT + NUM_MINERS - 1))"
echo "============================================"

# Kill any existing fleet
echo "Cleaning up old instances..."
pkill -f "llama-server.*swarmbuddy-1.5b" 2>/dev/null || true
pkill -f "real_worker.py.*xeon-miner" 2>/dev/null || true
sleep 2

# Launch llama-server instances
echo ""
echo "--- Launching ${NUM_MINERS} model servers ---"
for i in $(seq 0 $((NUM_MINERS - 1))); do
    PORT=$((BASE_PORT + i))
    CUDA_VISIBLE_DEVICES="" nohup /home/swarm/llama.cpp/build/bin/llama-server \
        -m "$MODEL" \
        --host 127.0.0.1 --port "$PORT" \
        --ctx-size 1024 --n-gpu-layers 0 \
        --parallel 1 --threads "$THREADS_PER_MINER" --batch-size 128 \
        > "/tmp/xeon-miner-${i}.log" 2>&1 &
    echo "  Server $i on port $PORT (PID $!)"
done

# Wait for all servers to load
echo ""
echo "Waiting for model loading (15s)..."
sleep 15

# Check health
HEALTHY=0
for i in $(seq 0 $((NUM_MINERS - 1))); do
    PORT=$((BASE_PORT + i))
    if curl -sf "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1; then
        HEALTHY=$((HEALTHY + 1))
    fi
done
echo "Healthy servers: ${HEALTHY}/${NUM_MINERS}"

if [ "$HEALTHY" -eq 0 ]; then
    echo "ERROR: No servers started. Check /tmp/xeon-miner-0.log"
    exit 1
fi

# Launch real workers
echo ""
echo "--- Launching ${HEALTHY} miners ---"
WORKER_DIR="$(dirname "$0")"
for i in $(seq 0 $((HEALTHY - 1))); do
    PORT=$((BASE_PORT + i))
    NODE_ID="xeon-miner-$(printf '%03d' $i)"

    nohup python3 "${WORKER_DIR}/real_worker.py" \
        --api-url "$API_URL" \
        --model-url "http://127.0.0.1:${PORT}/v1/chat/completions" \
        --node-id "$NODE_ID" \
        --node-type "cpu-xeon" \
        --hardware-class "xeon-3475-72t" \
        --model-name "swarmbuddy-1.5b" \
        --api-key "$API_KEY" \
        > "/tmp/xeon-worker-${i}.log" 2>&1 &

    echo "  Worker $NODE_ID → port $PORT (PID $!)"
done

echo ""
echo "============================================"
echo "  FLEET LAUNCHED: ${HEALTHY} miners active"
echo "============================================"
echo "  Monitor: tail -f /tmp/xeon-worker-0.log"
echo "  Stop:    pkill -f 'swarmbuddy-1.5b'"
echo "  Status:  pgrep -c -f real_worker"
echo "============================================"
