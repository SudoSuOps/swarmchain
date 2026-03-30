#!/usr/bin/env bash
# SwarmChain Email Send — uses Resend CLI with HTML templates.
# Usage: send.sh <template> <subject> [--to email] [--var KEY=VAL ...]
#
# Templates use ${VAR} placeholders filled by envsubst.
# All SWARM_* env vars are available in templates.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESEND="${HOME}/.resend/bin/resend"
FROM="${SWARM_FROM:-SwarmChain <chain@swarmandbee.ai>}"
TO="${SWARM_TO:-build@swarmandbee.ai}"

TEMPLATE="$1"; shift
SUBJECT="$1"; shift

# Parse optional args
while [[ $# -gt 0 ]]; do
  case $1 in
    --to) TO="$2"; shift 2 ;;
    --var) export "${2}"; shift 2 ;;
    *) shift ;;
  esac
done

TEMPLATE_FILE="${SCRIPT_DIR}/${TEMPLATE}.html"
if [ ! -f "$TEMPLATE_FILE" ]; then
  echo "Template not found: $TEMPLATE_FILE" >&2
  exit 1
fi

# Fill template and send
HTML=$(envsubst < "$TEMPLATE_FILE")
TMPFILE=$(mktemp /tmp/swarm-email-XXXXXX.html)
echo "$HTML" > "$TMPFILE"

RESULT=$($RESEND emails send \
  --from "$FROM" \
  --to "$TO" \
  --subject "$SUBJECT" \
  --html-file "$TMPFILE" \
  --tags "pipeline=swarmchain" \
  --tags "template=${TEMPLATE}" \
  2>&1)

rm -f "$TMPFILE"
echo "$RESULT"
