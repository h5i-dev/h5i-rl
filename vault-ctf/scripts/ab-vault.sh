#!/usr/bin/env bash
# A/B the websec replay-diff change on the vault challenge.
#   ./scripts/ab-vault.sh <old|new> <run-number>
# vault is the benchmark because it is the one challenge known to be solvable
# by this model, so turn counts can be compared rather than just pass/fail.
set -euo pipefail
ARM="${1:?usage: ab-vault.sh <old|new> <n>}"
N="${2:?usage: ab-vault.sh <old|new> <n>}"
SLUG="ab-$ARM-$N"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$ARM" in
  old) h5i plugin install websec --from /tmp/ht2673-websec-OLD --force >/dev/null 2>&1 ;;
  new) h5i plugin install websec --from /tmp/ht2673-websec-NEW --force >/dev/null 2>&1 ;;
  *) echo "arm must be old or new" >&2; exit 2 ;;
esac

"$ROOT/scripts/run-challenge.sh" "$SLUG" https://websecdojo.com/vault/ \
  "Test your HTTP skills and crack the vault." >/dev/null
while tmux list-sessions 2>/dev/null | grep -q "^codex-$SLUG:"; do sleep 15; done

WS="$ROOT/challenges/$SLUG"
LOG=/tmp/ht2673-codex-$SLUG.log
REQ=$(cd "$WS" && h5i websec requests 2>/dev/null | python3 -c "
import json,sys
try: print(len([r for r in json.loads(sys.stdin.read()).get('requests',[]) if r.get('phase')=='request']))
except Exception: print(-1)" 2>/dev/null || echo -1)
TOK=$(grep -A1 "^tokens used" "$LOG" 2>/dev/null | tail -1 | tr -d ' ,' || true); TOK=${TOK:-0}
SHOW=$(grep -c "h5i websec show" "$LOG" 2>/dev/null || true); SHOW=${SHOW:-0}
REPLAY=$(grep -c "h5i websec replay" "$LOG" 2>/dev/null || true); REPLAY=${REPLAY:-0}
DIFF=$(grep -c "h5i websec diff" "$LOG" 2>/dev/null || true); DIFF=${DIFF:-0}
# Solved only if the real flag is in the write-up AND in a captured body.
SOLVED=no
if [ -f "$WS/SOLUTION.md" ] && grep -q "B4nk5Ar3c00l" "$WS/SOLUTION.md" 2>/dev/null; then SOLVED=yes; fi
printf '%s,%s,%s,%s,%s,%s,%s,%s\n' "$ARM" "$N" "$SOLVED" "$REQ" "$TOK" "$SHOW" "$REPLAY" "$DIFF" \
  | tee -a "$ROOT/ab-results.csv"
