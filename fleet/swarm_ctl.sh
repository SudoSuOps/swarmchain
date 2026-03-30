#!/bin/bash
# SwarmChain Sovereign Control — master startup/shutdown/status
# "Our data. Our pairs. Our eval system. Our datacenter."

BACKEND_DIR="/data2/swarmchain/backend"
GLASSWALL_DIR="/data2/swarmchain/glass-wall"
FLEET_SCRIPT="/data2/swarmchain/fleet/swarm_fleet.sh"
ZIMA2="${SWARMCHAIN_ZIMA2_HOST:-dev@192.168.0.70}"
API_KEY="${SWARMCHAIN_API_KEY:-}"

case "${1}" in

up)
    echo "═══════════════════════════════════════"
    echo "  SWARMCHAIN SOVEREIGN — STARTING"
    echo "═══════════════════════════════════════"
    echo ""

    # 1. Infrastructure
    echo "1. Infrastructure..."
    docker start swarmchain-pg swarmchain-redis 2>/dev/null
    sleep 3
    docker exec swarmchain-pg pg_isready -U swarmchain > /dev/null 2>&1 && echo "   PostgreSQL ✅" || echo "   PostgreSQL ❌"
    docker exec swarmchain-redis redis-cli ping > /dev/null 2>&1 && echo "   Redis ✅" || echo "   Redis ❌"

    # 2. Backend API
    echo "2. Backend API..."
    cd "$BACKEND_DIR"
    nohup python3 -m uvicorn swarmchain.main:app --host 0.0.0.0 --port 8080 --log-level info > /tmp/swarmchain-backend.log 2>&1 &
    sleep 3
    curl -sf http://localhost:8080/health > /dev/null && echo "   API :8080 ✅" || echo "   API :8080 ❌"

    # 3. Glass-Wall
    echo "3. Glass-Wall..."
    cd "$GLASSWALL_DIR"
    nohup python3 server.py > /tmp/glasswall.log 2>&1 &
    sleep 1
    curl -sf http://localhost:3000/ > /dev/null && echo "   Glass-Wall :3000 ✅" || echo "   Glass-Wall :3000 ❌"

    # 4. Fleet
    echo "4. Model Fleet..."
    bash "$FLEET_SCRIPT" start

    echo ""
    echo "═══════════════════════════════════════"
    echo "  SOVEREIGN STACK ONLINE"
    echo "  Glass-Wall: http://192.168.0.91:3000"
    echo "═══════════════════════════════════════"
    ;;

down)
    echo "═══════════════════════════════════════"
    echo "  SWARMCHAIN SOVEREIGN — STOPPING"
    echo "═══════════════════════════════════════"

    # 1. Stop controller on Zima-2
    echo "1. Stopping Zima-2 controller..."
    sshpass -p "$ZIMA2_PASS" ssh -o StrictHostKeyChecking=no $ZIMA2 "pkill -f single_chain; pkill -f supervisor" 2>/dev/null
    echo "   Done"

    # 2. Stop fleet
    echo "2. Stopping fleet..."
    bash "$FLEET_SCRIPT" stop

    # 3. Stop Glass-Wall
    echo "3. Stopping Glass-Wall..."
    fuser -k 3000/tcp 2>/dev/null
    echo "   Done"

    # 4. Stop backend
    echo "4. Stopping backend..."
    pkill -f "uvicorn.*swarmchain" 2>/dev/null
    echo "   Done"

    # 5. Backup before full stop
    echo "5. Database backup..."
    docker exec swarmchain-pg pg_dump -U swarmchain swarmchain 2>/dev/null | gzip > /mnt/swarm/swarmchain-datasets/backups/shutdown_$(date +%Y%m%d_%H%M).sql.gz 2>/dev/null
    echo "   Backed up to NAS"

    echo ""
    echo "  SOVEREIGN STACK OFFLINE"
    ;;

status)
    echo "═══════════════════════════════════════"
    echo "  SWARMCHAIN SOVEREIGN STATUS"
    echo "═══════════════════════════════════════"
    echo ""
    echo "INFRA:"
    echo "  PostgreSQL: $(docker exec swarmchain-pg pg_isready -U swarmchain > /dev/null 2>&1 && echo '✅' || echo '❌')"
    echo "  Redis:      $(docker exec swarmchain-redis redis-cli ping > /dev/null 2>&1 && echo '✅' || echo '❌')"
    echo ""
    echo "API:"
    echo "  Backend:    $(curl -sf http://localhost:8080/health > /dev/null && echo '✅ :8080' || echo '❌')"
    echo "  Glass-Wall: $(curl -sf http://localhost:3000/ > /dev/null && echo '✅ :3000' || echo '❌')"
    echo ""

    bash "$FLEET_SCRIPT" status

    echo ""
    echo "CONTROLLER (Zima-2):"
    ZIMA_CHAIN=$(sshpass -p "$ZIMA2_PASS" ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no $ZIMA2 "pgrep -f single_chain | wc -l" 2>/dev/null)
    echo "  single_chain: ${ZIMA_CHAIN:-0} process(es)"
    echo ""

    echo "EPOCH:"
    curl -sf http://localhost:8080/dashboard 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
t=d.get('today',{})
print(f'  Blocks today: {t.get(\"blocks_opened\",0)}')
print(f'  Solved today: {t.get(\"blocks_solved\",0)}')
print(f'  Attempts:     {t.get(\"attempts\",0)}')
print(f'  Energy:       {t.get(\"energy\",0):.0f}')
" 2>/dev/null
    echo ""
    echo "STORAGE:"
    echo "  /data1 (datasets): $(df -h /data1 | tail -1 | awk '{print $3 " used / " $4 " free"}')"
    echo "  /data2 (ops+models): $(df -h /data2 | tail -1 | awk '{print $3 " used / " $4 " free"}')"
    echo "  NAS: $(df -h /mnt/swarm 2>/dev/null | tail -1 | awk '{print $3 " used / " $4 " free"}')"
    echo "═══════════════════════════════════════"
    ;;

epoch)
    BLOCKS=${2:-100}
    SESSION=${3:-"epoch-sovereign"}
    echo "Firing $BLOCKS blocks from Zima-2 (session: $SESSION)..."
    sshpass -p "$ZIMA2_PASS" ssh -o StrictHostKeyChecking=no $ZIMA2 "
        cd /data/swarmchain/controller
        export SWARM_RAILS_HOST=192.168.0.91
        nohup python3 -u single_chain.py \
            --api-url http://192.168.0.91:8080 \
            --api-key $API_KEY \
            --session-id $SESSION \
            --blocks $BLOCKS \
            > epoch.log 2>&1 &
        echo 'Epoch fired. PID: '\$!
    "
    echo "Monitor: ssh dev@192.168.0.70 'tail -f /data/swarmchain/controller/epoch.log'"
    ;;

backup)
    echo "Manual database backup..."
    mkdir -p /mnt/swarm/swarmchain-datasets/backups
    docker exec swarmchain-pg pg_dump -U swarmchain swarmchain | gzip > /mnt/swarm/swarmchain-datasets/backups/manual_$(date +%Y%m%d_%H%M).sql.gz
    ls -lh /mnt/swarm/swarmchain-datasets/backups/ | tail -3
    echo "Done."
    ;;

*)
    echo "SwarmChain Sovereign Control"
    echo ""
    echo "Usage: $0 {up|down|status|epoch [blocks] [session]|backup}"
    echo ""
    echo "  up              Start full sovereign stack"
    echo "  down            Stop everything + backup"
    echo "  status          Health check all components"
    echo "  epoch 500       Fire 500-block epoch from Zima-2"
    echo "  backup          Manual database backup to NAS"
    ;;
esac
