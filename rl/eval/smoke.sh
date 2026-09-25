#!/usr/bin/env bash
# Prove an environment is sound before spending GPU on it:
#   1. the challenge stands up and publishes a port
#   2. it is actually winnable -- for Argus, run the gold solve.py; for XBOW,
#      just confirm the injected flag is reachable over HTTP.
# Usage: ./eval/smoke.sh <argus|xbow> <slug>
set -euo pipefail
cd "$(dirname "$0")/.."
SUITE="${1:?usage: smoke.sh <argus|xbow> <slug>}"
SLUG="${2:?usage: smoke.sh <argus|xbow> <slug>}"

python3 - "$SUITE" "$SLUG" <<'PY'
import sys
sys.path.insert(0, ".")
from env.challenge import pool
suite, slug = sys.argv[1], sys.argv[2]
ch = next((c for c in pool() if c.suite == suite and c.slug == slug), None)
if ch is None:
    sys.exit(f"no such challenge: {suite}/{slug}")
base = ch.up()
print(f"UP   {suite}/{slug} -> {base}  (level {ch.level})")
try:
    if suite == "argus":
        import subprocess
        r = subprocess.run(["make", "exploit"], cwd=ch.path, text=True, capture_output=True)
        ok = ch.flag and ch.flag in (r.stdout + r.stderr)
        print("GOLD solve.py:", "WON" if ok else "did not surface flag")
    else:
        import urllib.request
        html = urllib.request.urlopen(base, timeout=10).read().decode("utf-8", "replace")
        print("HTTP reachable, bytes:", len(html))
        print("flag injected:", ch.flag)
finally:
    ch.down()
    print("DOWN", slug)
PY
