#!/usr/bin/env python3
"""Find which challenges actually build and run on this machine today.

Many 2024 XBOW challenges pin EOL base images (python:2.7 / Debian buster) whose
apt repos now 404, so the trainable pool is the subset that survives this sweep.
For each challenge: `make build` with a fresh flag, then `make run`, then probe
the discovered web port, then `make stop`. Results (and a short failure note) go
to eval/build_sweep.csv.

    python -m eval.build_sweep [xbow|argus]     # default: all suites
"""
from __future__ import annotations

import csv
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env.challenge import pool, _published_base_url   # noqa: E402


def _run(cmd, cwd, timeout):
    try:
        cp = subprocess.run(cmd, cwd=cwd, timeout=timeout, text=True, capture_output=True)
        return cp.returncode, cp.stdout + cp.stderr
    except subprocess.TimeoutExpired:
        return 124, "__timeout__"


def _note(out: str) -> str:
    low = out.lower()
    if out == "__timeout__":
        return "timeout"
    if "release file" in low or "404  not found" in low or "not have a release" in low:
        return "apt-eol-404"
    if "already allocated" in low or "address already in use" in low or "port is already" in low:
        return "port-conflict"
    if "no space left" in low:
        return "no-space"
    if "docker-compose: command not found" in low or "docker-compose: not found" in low:
        return "needs-compose-v1"
    tail = [l for l in out.strip().splitlines() if l.strip()]
    return tail[-1][:80] if tail else ""


def main() -> None:
    challenges = pool()
    if len(sys.argv) > 1:
        challenges = [c for c in challenges if c.suite == sys.argv[1]]
    out_p = Path(__file__).resolve().parent / "build_sweep.csv"
    with open(out_p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["suite", "slug", "level", "builds", "runs", "reachable", "secs", "note"])
        ok = 0
        for i, c in enumerate(challenges, 1):
            t0 = time.time()
            builds = runs = reach = False
            note = ""
            flag = f"sw{secrets.token_hex(4)}"
            rc, out = _run(["make", "build", f"FLAG={flag}"], c.path, 300)
            builds = rc == 0
            if not builds:
                note = _note(out)
            else:
                rc, out = _run(["make", "run", f"FLAG={flag}"], c.path, 150)
                runs = rc == 0
                if not runs:
                    note = _note(out)
                else:
                    try:
                        base = _published_base_url(c.path)
                        if base:
                            reach = 200 <= urllib.request.urlopen(base, timeout=8).getcode() < 500
                        else:
                            note = "no-port"
                    except Exception as e:  # noqa: BLE001 - a 4xx/5xx still means "reachable"
                        reach = "HTTPError" in type(e).__name__
                        note = note or f"probe:{type(e).__name__}"
                _run(["make", "stop"], c.path, 120)
            secs = round(time.time() - t0, 1)
            ok += int(reach)
            w.writerow([c.suite, c.slug, c.level, int(builds), int(runs), int(reach), secs, note])
            f.flush()
            print(f"[{i}/{len(challenges)}] {c.slug:16} build={int(builds)} run={int(runs)} "
                  f"reach={int(reach)} {secs:5.0f}s {note}", flush=True)
        print(f"\nusable (reachable): {ok}/{len(challenges)} -> {out_p}")


if __name__ == "__main__":
    main()
