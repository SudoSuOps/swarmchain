#!/bin/bash
# SwarmChain Fleet Manager — start/stop/status all model servers
# Sovereign deployment — everything on owned hardware

LLAMA="/home/swarm/llama.cpp/build/bin/llama-server"
RAILS="192.168.0.91"

# Model definitions
KATNISS_GGUF="/data2/swarm-models/katniss/katniss-9b-v1-q4_k_m.gguf"
GPU4B_GGUF="/data2/openalex/qwen35-4b-base-q4_k_m.gguf"
BEE_GGUF="/data2/swarmrouter-3b-q4.gguf"

BEE_COUNT=10
BEE_PORT_START=9100
BEE_THREADS=3

case "${1}" in

start)
    echo "═══════════════════════════════════════"
    echo "  STARTING SWARMCHAIN FLEET"
    echo "═══════════════════════════════════════"

    # Katniss 9B on GPU 1 (RTX PRO 6000)
    echo "Katniss 9B (RTX 6000, :8090)..."
    CUDA_VISIBLE_DEVICES=1 nohup $LLAMA \
        -m "$KATNISS_GGUF" --host 0.0.0.0 --port 8090 \
        --ctx-size 4096 --n-gpu-layers 99 --parallel 2 --threads 4 \
        > /tmp/fleet-katniss.log 2>&1 &
    sleep 2
    curl -sf http://localhost:8090/health > /dev/null && echo "  ✅" || echo "  ⏳ loading..."

    # GPU-4B on GPU 0 (RTX PRO 4500)
    echo "GPU-4B (RTX 4500, :8094)..."
    CUDA_VISIBLE_DEVICES=0 nohup $LLAMA \
        -m "$GPU4B_GGUF" --host 0.0.0.0 --port 8094 \
        --ctx-size 4096 --n-gpu-layers 99 --parallel 2 --threads 4 \
        > /tmp/fleet-gpu4b.log 2>&1 &
    sleep 2
    curl -sf http://localhost:8094/health > /dev/null && echo "  ✅" || echo "  ⏳ loading..."

    # CPU Bees on Xeon
    echo "${BEE_COUNT}x Bee-3B (Xeon CPU, :${BEE_PORT_START}-$((BEE_PORT_START + BEE_COUNT - 1)))..."
    for i in $(seq 0 $((BEE_COUNT - 1))); do
        PORT=$((BEE_PORT_START + i))
        nohup $LLAMA \
            -m "$BEE_GGUF" --host 0.0.0.0 --port $PORT \
            --ctx-size 1024 --n-gpu-layers 0 --parallel 1 \
            --threads $BEE_THREADS --batch-size 128 \
            > /dev/null 2>&1 &
    done
    sleep 2
    BEES=0
    for i in $(seq 0 $((BEE_COUNT - 1))); do
        PORT=$((BEE_PORT_START + i))
        curl -sf http://localhost:$PORT/health > /dev/null 2>&1 && BEES=$((BEES + 1))
    done
    echo "  $BEES/$BEE_COUNT ✅"

    echo ""
    echo "Fleet deployed. Run '$0 status' to verify."
    ;;

stop)
    echo "Stopping all llama-server processes..."
    pkill -f "llama-server" 2>/dev/null
    sleep 2
    REMAINING=$(pgrep -f "llama-server" | wc -l)
    echo "Remaining: $REMAINING (should be 0)"
    ;;

status)
    echo "═══════════════════════════════════════"
    echo "  SWARMCHAIN FLEET STATUS"
    echo "═══════════════════════════════════════"

    # Local models
    for name_port in "Katniss-9B:8090" "GPU-4B:8094"; do
        NAME=$(echo $name_port | cut -d: -f1)
        PORT=$(echo $name_port | cut -d: -f2)
        STATUS=$(curl -sf http://localhost:$PORT/health > /dev/null 2>&1 && echo "✅ UP" || echo "❌ DOWN")
        echo "  $NAME (:$PORT)    $STATUS"
    done

    # Bees
    BEES=0
    for i in $(seq 0 $((BEE_COUNT - 1))); do
        PORT=$((BEE_PORT_START + i))
        curl -sf http://localhost:$PORT/health > /dev/null 2>&1 && BEES=$((BEES + 1))
    done
    echo "  Bees (:${BEE_PORT_START}-$((BEE_PORT_START + BEE_COUNT - 1)))  $BEES/$BEE_COUNT"

    # Remote
    echo ""
    echo "  REMOTE:"
    WHALE=$(curl -sf http://192.168.0.99:8092/health > /dev/null 2>&1 && echo "✅ UP" || echo "❌ DOWN")
    JETSON=$(curl -sf http://192.168.0.79:8085/health > /dev/null 2>&1 && echo "✅ UP" || echo "❌ DOWN")
    echo "  Whale-7B (192.168.0.99:8092)   $WHALE"
    echo "  Jetson (192.168.0.79:8085)      $JETSON"

    # GPU memory
    echo ""
    echo "  GPU:"
    nvidia-smi --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader 2>/dev/null
    echo "═══════════════════════════════════════"
    ;;

restart)
    $0 stop
    sleep 3
    $0 start
    ;;

*)
    echo "Usage: $0 {start|stop|status|restart}"
    exit 1
    ;;
esac
