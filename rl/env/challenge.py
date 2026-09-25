"""One uniform interface over the XBOW and Argus benchmark formats.

A `Challenge` stands its vulnerable app up in Docker, tells you the base URL to
point the agent at, hands back the ground-truth flag, and tears it down.

Real layouts (verified against the cloned repos):

  XBOW   benchmarks/xbow/benchmarks/<slug>/
           benchmark.json          name, level, win_condition, tags, canaries
           Makefile -> ../../common.mk   targets: build / run / stop / clean
         common.mk injects the flag at BUILD time and wraps it:
           FLAG_FMT = FLAG{$(FLAG)}   ->  `make build FLAG=<inner>` gives FLAG{<inner>}
         and builds via `docker compose` (v2). All 104 are win_condition=flag.

  Argus  benchmarks/argus/benchmarks/<ID>/src/
           benchmark.json          flags:{strategy:per_run, env:FLAG}, win_condition
           Makefile                targets: build / run / stop, but uses the v1
                                   `docker-compose` binary (needs a shim if only
                                   the v2 plugin is installed -- see up()).
         ../expected_results/vulnerability.json is a code-audit answer key.

Flag granularity is PER RUN, not per episode: XBOW caches the image behind a
build guard, so a fresh flag means a rebuild. We build once per challenge (with
a random flag) and then just run/stop per episode. That matches Argus's own
"per_run" strategy and keeps rollouts fast.
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BENCH = ROOT / "benchmarks"

# Ports we must NOT mistake for the web app when discovering the target URL.
_DB_PORTS = {3306, 5432, 6379, 27017, 1433, 11211, 9200}
_WEB_PORTS = {80, 443, 3000, 3001, 4000, 5000, 8000, 8080, 8888}


def _run(cmd, cwd: Path, timeout: int = 900, env: dict | None = None):
    return subprocess.run(cmd, cwd=cwd, timeout=timeout, text=True,
                          capture_output=True, check=False, env=env)


def _published_base_url(compose_dir: Path) -> str | None:
    """Pick the web app's published host port (never a DB port)."""
    cp = _run(["docker", "compose", "ps", "--format", "json"], compose_dir, timeout=60)
    if cp.returncode != 0 or not cp.stdout.strip():
        return None
    out = cp.stdout.strip()
    rows = json.loads(out) if out.startswith("[") else \
        [json.loads(l) for l in out.splitlines() if l.strip()]
    candidates: list[tuple[int, int]] = []  # (target_port, published_port)
    for row in rows:
        for pub in row.get("Publishers") or []:
            hp, tp = pub.get("PublishedPort"), pub.get("TargetPort")
            if hp:
                candidates.append((tp or 0, hp))
    if not candidates:
        return None
    # prefer a known web target port; else any non-DB target; else first.
    for tp, hp in candidates:
        if tp in _WEB_PORTS:
            return f"http://127.0.0.1:{hp}"
    for tp, hp in candidates:
        if tp not in _DB_PORTS:
            return f"http://127.0.0.1:{hp}"
    return f"http://127.0.0.1:{candidates[0][1]}"


@dataclass
class Challenge:
    suite: str                       # "xbow" | "argus"
    slug: str                        # directory name / id
    path: Path                       # dir holding the Makefile / docker-compose.yml
    level: int = 0                   # 1 easy .. 3 hard (0 = unknown)
    tags: list[str] = field(default_factory=list)
    description: str = ""
    canaries: list[str] = field(default_factory=list)
    _flag: str | None = None

    # ---- lifecycle -------------------------------------------------------
    def up(self) -> str:
        """Build with a fresh per-run flag, then run. Return the base URL.

        XBOW caches the built image behind a guard file (.xben_build_done), so
        `make build FLAG=<new>` is a no-op once built and the OLD flag stays
        baked in -- which would make `flag` lie about what is actually running.
        We drop the guard (`make clean`) first so the new flag takes; the docker
        layer cache keeps this cheap because `ARG FLAG` sits late in the
        Dockerfile (only that layer and the flag-substitution re-run).
        """
        inner = secrets.token_hex(12)
        if self.suite == "xbow":
            self._flag = f"FLAG{{{inner}}}"           # common.mk wraps FLAG{...}
            _run(["make", "clean"], self.path, timeout=60)
            _run(["make", "build", f"FLAG={inner}"], self.path).check_returncode()
            _run(["make", "run", f"FLAG={inner}"], self.path).check_returncode()
        else:  # argus
            self._flag = f"FLAG{{{inner}}}"
            env = {"FLAG": self._flag}
            _run(["make", "build", f"FLAG={self._flag}"], self.path, env=_shell_env(env)).check_returncode()
            _run(["make", "run", f"FLAG={self._flag}"], self.path, env=_shell_env(env)).check_returncode()
        return self._await_base_url()

    def down(self) -> None:
        _run(["make", "stop"], self.path, timeout=120)

    def _await_base_url(self, tries: int = 30, delay: float = 1.5) -> str:
        for _ in range(tries):
            url = _published_base_url(self.path)
            if url:
                return url
            time.sleep(delay)
        raise RuntimeError(f"{self.slug}: no published web port after run")

    @property
    def flag(self) -> str:
        if self._flag is None:
            raise RuntimeError("flag is only known after up()")
        return self._flag


def _shell_env(extra: dict) -> dict:
    import os
    e = dict(os.environ)
    e.update({k: str(v) for k, v in extra.items()})
    return e


# ---- discovery -----------------------------------------------------------
def _as_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _load_xbow() -> list[Challenge]:
    root = BENCH / "xbow" / "benchmarks"
    out = []
    for d in (sorted(p for p in root.glob("*") if p.is_dir()) if root.exists() else []):
        cfg_p = d / "benchmark.json"
        if not cfg_p.exists():
            continue
        cfg = json.loads(cfg_p.read_text())
        out.append(Challenge(
            suite="xbow", slug=d.name, path=d,
            level=_as_int(cfg.get("level")),
            tags=cfg.get("tags", []) or [],
            description=cfg.get("description", "") or "",
            canaries=cfg.get("canaries", []) or [],
        ))
    return out


def _load_argus() -> list[Challenge]:
    root = BENCH / "argus" / "benchmarks"
    out = []
    for d in (sorted(p for p in root.glob("*") if (p / "src").is_dir()) if root.exists() else []):
        src = d / "src"
        cfg_p = src / "benchmark.json"
        cfg = json.loads(cfg_p.read_text()) if cfg_p.exists() else {}
        out.append(Challenge(
            suite="argus", slug=d.name, path=src,
            level=_as_int(cfg.get("level") or cfg.get("difficulty")),
            tags=cfg.get("tags", cfg.get("categories", [])) or [],
            description=cfg.get("description", "") or "",
            canaries=cfg.get("canaries", []) or [],
        ))
    return out


def pool() -> list[Challenge]:
    return _load_xbow() + _load_argus()


def buildable(suite: str | None = None) -> list[Challenge]:
    """The subset a prior `eval/build_sweep.py` run found actually reachable on
    this machine (many 2024 challenges bit-rotted on EOL base images). Falls
    back to the full pool if no sweep has run yet."""
    import csv as _csv
    csv_p = ROOT.parent / "eval" / "build_sweep.csv"
    cs = pool() if suite is None else [c for c in pool() if c.suite == suite]
    if not csv_p.exists():
        return cs
    with open(csv_p) as f:
        ok = {(r["suite"], r["slug"]) for r in _csv.DictReader(f) if r["reachable"] == "1"}
    return [c for c in cs if (c.suite, c.slug) in ok]


def split(seed: int = 0, val_frac: float = 0.15):
    """Deterministic train/val split, stratified by (suite, level)."""
    import random
    rng = random.Random(seed)
    by_stratum: dict[tuple, list] = {}
    for c in pool():
        by_stratum.setdefault((c.suite, c.level), []).append(c)
    train, val = [], []
    for group in by_stratum.values():
        rng.shuffle(group)
        n_val = max(1, int(len(group) * val_frac))
        val.extend(group[:n_val])
        train.extend(group[n_val:])
    return train, val


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--counts", action="store_true")
    args = ap.parse_args()
    cs = pool()
    if args.counts or not args.list:
        import collections
        by = collections.Counter((c.suite, c.level) for c in cs)
        print(f"total {len(cs)} challenges")
        for k in sorted(by):
            print(f"  {k[0]:6} level {k[1]}: {by[k]}")
    if args.list:
        for c in cs:
            print(f"{c.suite:6} {c.slug:16} L{c.level} {','.join(c.tags[:4])}")
