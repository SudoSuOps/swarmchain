#!/usr/bin/env bash
# SwarmChain Gate Monitor — watches a cook and fires gate emails automatically.
# Usage: gate_monitor.sh <job_id> <domain> <total_pairs> [--interval 30]
#
# Fires at: 5% (internal), 25% (client), 50% (client), 75% (client), 100% (closing)
# Per the permit. Per the chain.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.resend/bin:$HOME/.local/bin:$PATH"
export RESEND_API_KEY="${RESEND_API_KEY:-***SECRET_PURGED_FROM_HISTORY***}"

JOB_ID="$1"
DOMAIN="$2"
TOTAL_PAIRS="$3"
INTERVAL="${4:-30}"
HONEY_DIR="${HONEY_DIR:-/data1/swarm-honey}"
VALIDATED="${HONEY_DIR}/${DOMAIN}/validated"
JUDGED="${VALIDATED}/judged.jsonl"

GATES_FIRED=""

calc_stats() {
  python3 -c "
import json
rj=h=p=0; scores=[]; empty=0
for line in open('${JUDGED}'):
    d=json.loads(line.strip()); s=d.get('score',0); c=d.get('classification',''); ms=d.get('judge_ms',0)
    if ms==0 and s==0: empty+=1; continue
    scores.append(s)
    if c=='royal-jelly': rj+=1
    elif c=='honey': h+=1
    else: p+=1
t=rj+h+p
avg=sum(scores)/len(scores) if scores else 0
print(f'{t}|{rj}|{h}|{p}|{empty}|{avg:.3f}|{rj/max(t,1)*100:.1f}')
"
}

fire_gate() {
  local GATE_PCT="$1"
  local GATE_TYPE="$2"
  local GATE_COLOR="$3"

  STATS=$(calc_stats)
  IFS='|' read -r JUDGED_N RJ_N HONEY_N PROP_N EMPTY_N AVG_SCORE RJ_RATE <<< "$STATS"
  PROGRESS_PCT=$(python3 -c "print(round(${JUDGED_N}/${TOTAL_PAIRS}*100, 1))")

  export JOB_ID DOMAIN GATE_PCT GATE_TYPE GATE_COLOR PROGRESS_PCT
  export JUDGED="$JUDGED_N" TOTAL_PAIRS AVG_SCORE
  export RJ_COUNT="$RJ_N" RJ_RATE HONEY_COUNT="$HONEY_N" PROPOLIS_COUNT="$PROP_N"
  export EMPTY_COUNT="$EMPTY_N"
  export CLEAN_STATUS=$([ "$EMPTY_N" = "0" ] && echo "CLEAN" || echo "CONTAMINATED")
  export FOOTER_NOTE="Glass Wall: http://192.168.0.91:3000"

  bash "${SCRIPT_DIR}/send.sh" gate_report \
    "${GATE_TYPE} ${GATE_PCT}% — ${DOMAIN} — ${RJ_RATE}% Royal Jelly — ${JUDGED_N} / ${TOTAL_PAIRS}"

  echo "[$(date -u +%H:%M:%S)] GATE ${GATE_PCT}% FIRED — ${JUDGED_N} judged, ${RJ_RATE}% RJ, ${EMPTY_N} empty"
}

echo "SwarmChain Gate Monitor"
echo "  Job: ${JOB_ID}"
echo "  Domain: ${DOMAIN}"
echo "  Pairs: ${TOTAL_PAIRS}"
echo "  Interval: ${INTERVAL}s"
echo "  Gates: 5% 25% 50% 75%"
echo "  Watching: ${JUDGED}"
echo ""

while true; do
  [ ! -f "$JUDGED" ] && sleep "$INTERVAL" && continue

  COUNT=$(wc -l < "$JUDGED" 2>/dev/null || echo 0)
  PCT=$(python3 -c "print(round(${COUNT}/${TOTAL_PAIRS}*100, 1))" 2>/dev/null || echo 0)

  # 5% gate — internal
  if [[ "$GATES_FIRED" != *"5"* ]] && (( $(echo "$PCT >= 5" | bc -l) )); then
    fire_gate 5 "GATE" "#4caf50"
    GATES_FIRED="${GATES_FIRED}5,"
  fi

  # 25% gate — client
  if [[ "$GATES_FIRED" != *"25"* ]] && (( $(echo "$PCT >= 25" | bc -l) )); then
    fire_gate 25 "PROGRESS" "#4fc3f7"
    GATES_FIRED="${GATES_FIRED}25,"
  fi

  # 50% gate
  if [[ "$GATES_FIRED" != *"50"* ]] && (( $(echo "$PCT >= 50" | bc -l) )); then
    fire_gate 50 "PROGRESS" "#4fc3f7"
    GATES_FIRED="${GATES_FIRED}50,"
  fi

  # 75% gate
  if [[ "$GATES_FIRED" != *"75"* ]] && (( $(echo "$PCT >= 75" | bc -l) )); then
    fire_gate 75 "GATE" "#f0b000"
    GATES_FIRED="${GATES_FIRED}75,"
  fi

  # 100% — cook done
  if [ "$COUNT" -ge "$TOTAL_PAIRS" ]; then
    echo "[$(date -u +%H:%M:%S)] COOK COMPLETE — ${COUNT} / ${TOTAL_PAIRS}"
    STATS=$(calc_stats)
    IFS='|' read -r JUDGED_N RJ_N HONEY_N PROP_N EMPTY_N AVG_SCORE RJ_RATE <<< "$STATS"
    echo "  Royal Jelly: ${RJ_N} (${RJ_RATE}%)"
    echo "  Honey: ${HONEY_N}"
    echo "  Propolis: ${PROP_N}"
    echo "  Empty: ${EMPTY_N}"
    break
  fi

  echo "[$(date -u +%H:%M:%S)] ${COUNT} / ${TOTAL_PAIRS} (${PCT}%) — gates fired: ${GATES_FIRED:-none}"
  sleep "$INTERVAL"
done

echo "Gate monitor exiting."
