"""Standalone (non-verl) rollout sampler, and the curriculum selector.

The verl integration does NOT go through this file. It is verl-native (verl
0.9.1): h5i verbs are `BaseTool`s in train/h5i_tool.py (listed in h5i_tools.yaml),
so verl's built-in ToolAgentLoop owns generation, tool-call parsing, multi-turn
tokenization and the response mask -- no custom AgentLoopBase to maintain. The
container lifecycle lives in env/serve_pool.py; the reward in train/h5i_reward.py;
the wiring in run_grpo.sh.

This module stays useful as a harness-light way to eyeball a full episode
(policy <-> h5i <-> reward) against any OpenAI-compatible endpoint, and it owns
`train_challenges()`, the sweep-verified curriculum both paths draw from.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env.challenge import buildable             # noqa: E402
from agent.rollout import run_episode           # noqa: E402


def sample_episode(challenge, model: str | None = None) -> dict:
    """One challenge -> a full h5i-driving episode dict (messages + scalar reward),
    via the standalone loop in agent/rollout.py. For debugging, not for verl."""
    model = model or os.environ.get("MODEL", "Qwen/Qwen3-4B")
    return run_episode(challenge, model=model,
                       max_turns=int(os.environ.get("MAX_TURNS", "25")))


def train_challenges(seed: int = 0):
    # xbow is the clean flag-capture path (argus needs a docker-compose v1 shim);
    # restrict to the sweep-verified buildable subset so rollouts never stall on
    # a challenge that cannot come up.
    cs = buildable("xbow")
    # curriculum: start on the easiest tier; widen once solve-rate is stable.
    level1 = [c for c in cs if c.level == 1]
    return level1 or cs


if __name__ == "__main__":
    # Smoke: sample one episode from the current curriculum with a served policy.
    chs = train_challenges()
    if not chs:
        raise SystemExit("no challenges found; run env/fetch_benchmarks.sh first")
    ep = sample_episode(chs[0])
    print({k: ep[k] for k in ("suite", "slug", "reward", "turns", "solved")})
