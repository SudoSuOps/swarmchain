#!/usr/bin/env bash
# SwarmChain Training Watchdog — monitors long builds, sends status emails.
# Usage: train_watchdog.sh <job_name> <total_steps> <log_file> [--interval 300]
#
# Checks: GPU health, process alive, temperature, step progress, stall detection.
# Sends email at: 10%, 25%, 50%, 75%, 100%, and on FAILURE.

set -euo pipefail

export PATH="$HOME/.resend/bin:$HOME/.local/bin:$PATH"
export RESEND_API_KEY="${RESEND_API_KEY:-re_2hEw15wp_6uhiqCTwDFF4E5X4VocBB19c}"

JOB_NAME="$1"
TOTAL_STEPS="$2"
LOG_FILE="$3"
INTERVAL="${4:-300}"  # 5 min default
GPU_INDEX="${GPU_INDEX:-1}"
TO="${SWARM_TO:-build@swarmandbee.ai}"
FROM="${SWARM_FROM:-SwarmChain <chain@swarmandbee.ai>}"
RESEND="$HOME/.resend/bin/resend"
MAX_TEMP="${MAX_TEMP:-92}"
STALL_THRESHOLD="${STALL_THRESHOLD:-3}"  # alert after N checks with no progress

GATES_FIRED=""
LAST_STEP=0
STALL_COUNT=0
START_TIME=$(date +%s)

get_step() {
  grep -oP '\| \K\d+(?=/'"$TOTAL_STEPS"')' "$LOG_FILE" 2>/dev/null | tail -1 || \
  grep -oP '^\s*\d+%.*\| \K\d+(?=/)' "$LOG_FILE" 2>/dev/null | tail -1 || \
  echo "0"
}

get_gpu() {
  nvidia-smi --query-gpu=memory.used,power.draw,temperature.gpu,utilization.gpu --format=csv,noheader -i "$GPU_INDEX" 2>/dev/null || echo "?,?,?,?"
}

send_status() {
  local SUBJECT="$1"
  local STATUS="$2"
  local COLOR="$3"
  local STEP=$(get_step)
  local PCT=$(python3 -c "print(round(${STEP}/${TOTAL_STEPS}*100, 1))" 2>/dev/null || echo "?")
  local GPU_INFO=$(get_gpu)
  local ELAPSED=$(( ($(date +%s) - START_TIME) / 60 ))
  local ETA="?"
  if [ "$STEP" -gt 0 ] 2>/dev/null; then
    ETA=$(python3 -c "
s=${STEP}; t=${TOTAL_STEPS}; e=${ELAPSED}
if s>0: print(f'{((t-s)/s*e)/60:.1f}h')
else: print('?')
" 2>/dev/null || echo "?")
  fi

  local HTML="<div style=\"font-family:'Courier New',monospace;background:#0a0a0a;color:#e0e0e0;padding:40px;max-width:600px;margin:0 auto;\">
<div style=\"border-bottom:1px solid #222;padding-bottom:12px;margin-bottom:20px;\">
<span style=\"color:#f0b000;font-size:14px;letter-spacing:4px;\">SWARMCHAIN</span>
<span style=\"color:${COLOR};font-size:14px;letter-spacing:4px;\"> BUILD WATCHDOG</span></div>
<div style=\"background:#111;border:1px solid #222;border-radius:8px;padding:20px;margin-bottom:20px;text-align:center;\">
<div style=\"color:${COLOR};font-size:24px;letter-spacing:4px;\">${STATUS}</div>
<div style=\"color:#555;font-size:12px;margin-top:8px;\">${JOB_NAME}</div></div>
<div style=\"background:#222;height:8px;border-radius:4px;margin:12px 0;overflow:hidden;\">
<div style=\"background:#f0b000;height:100%;width:${PCT}%;border-radius:4px;\"></div></div>
<table style=\"width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px;\">
<tr><td style=\"color:#555;padding:6px 0;\">Step</td><td style=\"text-align:right;color:#f0b000;\">${STEP} / ${TOTAL_STEPS} (${PCT}%)</td></tr>
<tr><td style=\"color:#555;padding:6px 0;\">Elapsed</td><td style=\"text-align:right;\">${ELAPSED} min</td></tr>
<tr><td style=\"color:#555;padding:6px 0;\">ETA</td><td style=\"text-align:right;\">${ETA}</td></tr>
<tr><td style=\"color:#555;padding:6px 0;\">GPU</td><td style=\"text-align:right;\">${GPU_INFO}</td></tr></table>
<div style=\"border-top:1px solid #222;padding-top:12px;text-align:center;color:#555;font-size:10px;letter-spacing:2px;\">
DEFENDABLE AI INTELLIGENCE REFINERY — <span style=\"color:#f0b000;\">SWARM &amp; BEE</span></div></div>"

  local TMPFILE=$(mktemp /tmp/watchdog-XXXXXX.html)
  echo "$HTML" > "$TMPFILE"
  $RESEND emails send --from "$FROM" --to "$TO" --subject "$SUBJECT" --html-file "$TMPFILE" --tags "pipeline=build" --tags "job=${JOB_NAME}" 2>/dev/null || true
  rm -f "$TMPFILE"
}

echo "SwarmChain Training Watchdog"
echo "  Job: ${JOB_NAME}"
echo "  Steps: ${TOTAL_STEPS}"
echo "  Log: ${LOG_FILE}"
echo "  GPU: ${GPU_INDEX}"
echo "  Interval: ${INTERVAL}s"
echo "  Max temp: ${MAX_TEMP}C"
echo ""

while true; do
  # Check process alive
  if ! pgrep -f "train.py" > /dev/null 2>&1; then
    # Check if it finished successfully
    if grep -q "BUILD COMPLETE\|training complete\|Saving model" "$LOG_FILE" 2>/dev/null; then
      send_status "BUILD COMPLETE — ${JOB_NAME}" "COMPLETE" "#4caf50"
      echo "[$(date -u +%H:%M:%S)] BUILD COMPLETE"
      break
    else
      send_status "BUILD FAILED — ${JOB_NAME}" "FAILED" "#f04040"
      echo "[$(date -u +%H:%M:%S)] BUILD FAILED — process died"
      break
    fi
  fi

  STEP=$(get_step)
  PCT=$(python3 -c "print(round(${STEP}/${TOTAL_STEPS}*100, 1))" 2>/dev/null || echo "0")
  GPU_INFO=$(get_gpu)
  TEMP=$(echo "$GPU_INFO" | cut -d',' -f3 | tr -d ' ')

  # Temperature check
  if [ "${TEMP:-0}" -gt "$MAX_TEMP" ] 2>/dev/null; then
    send_status "THERMAL WARNING — ${JOB_NAME} — ${TEMP}C" "THERMAL" "#f04040"
    echo "[$(date -u +%H:%M:%S)] THERMAL WARNING: ${TEMP}C > ${MAX_TEMP}C"
  fi

  # Stall detection
  if [ "$STEP" = "$LAST_STEP" ] 2>/dev/null; then
    STALL_COUNT=$((STALL_COUNT + 1))
    if [ "$STALL_COUNT" -ge "$STALL_THRESHOLD" ]; then
      send_status "STALL DETECTED — ${JOB_NAME} — stuck at step ${STEP}" "STALLED" "#f04040"
      echo "[$(date -u +%H:%M:%S)] STALL: no progress for $((STALL_COUNT * INTERVAL))s"
      STALL_COUNT=0
    fi
  else
    STALL_COUNT=0
    LAST_STEP="$STEP"
  fi

  # Gate emails
  if [[ "$GATES_FIRED" != *"10"* ]] && (( $(echo "$PCT >= 10" | bc -l 2>/dev/null || echo 0) )); then
    send_status "BUILD 10% — ${JOB_NAME}" "10%" "#4fc3f7"
    GATES_FIRED="${GATES_FIRED}10,"
    echo "[$(date -u +%H:%M:%S)] GATE 10% fired"
  fi
  if [[ "$GATES_FIRED" != *"25,"* ]] && (( $(echo "$PCT >= 25" | bc -l 2>/dev/null || echo 0) )); then
    send_status "BUILD 25% — ${JOB_NAME}" "25%" "#4fc3f7"
    GATES_FIRED="${GATES_FIRED}25,"
    echo "[$(date -u +%H:%M:%S)] GATE 25% fired"
  fi
  if [[ "$GATES_FIRED" != *"50,"* ]] && (( $(echo "$PCT >= 50" | bc -l 2>/dev/null || echo 0) )); then
    send_status "BUILD 50% — ${JOB_NAME}" "50%" "#f0b000"
    GATES_FIRED="${GATES_FIRED}50,"
    echo "[$(date -u +%H:%M:%S)] GATE 50% fired"
  fi
  if [[ "$GATES_FIRED" != *"75,"* ]] && (( $(echo "$PCT >= 75" | bc -l 2>/dev/null || echo 0) )); then
    send_status "BUILD 75% — ${JOB_NAME}" "75%" "#f0b000"
    GATES_FIRED="${GATES_FIRED}75,"
    echo "[$(date -u +%H:%M:%S)] GATE 75% fired"
  fi

  echo "[$(date -u +%H:%M:%S)] step ${STEP}/${TOTAL_STEPS} (${PCT}%) | GPU: ${GPU_INFO} | gates: ${GATES_FIRED:-none}"
  sleep "$INTERVAL"
done

echo "Watchdog exiting."
