"""verl custom reward function for the h5i tool-agent loop.

Signature matches verl's reward manager:
    compute_score(data_source, solution_str, ground_truth, extra_info=None)

`solution_str` is the decoded rollout response -- the model's turns AND the h5i
tool observations, concatenated. Because each episode's flag is a fresh random
value (see env/serve_pool.py), the flag can only appear in `solution_str` if the
policy actually extracted it through h5i; guessing an unseen 24-hex flag is not a
path. That is what makes "flag in trajectory" a capture-backed signal, so we do
not need the declared-vs-captured split the standalone reward.py uses.

`ground_truth` is the flag (a plain string, or a JSON object also carrying
canaries/target). `extra_info` carries canaries + num_turns (verl injects
num_turns). Shaping stays small so it cannot be farmed instead of solving.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reward.reward import R_SOLVE, R_EFFICIENCY, R_TESTED, P_CANARY  # noqa: E402

DEFAULT_MAX_TURNS = 25


def _unpack(ground_truth, extra_info):
    """Accept ground_truth as a flag string or a JSON {flag, canaries, ...}."""
    flag, canaries = None, []
    if isinstance(ground_truth, str) and ground_truth.strip().startswith("{"):
        try:
            gt = json.loads(ground_truth)
            flag, canaries = gt.get("flag"), gt.get("canaries", []) or []
        except json.JSONDecodeError:
            flag = ground_truth
    else:
        flag = ground_truth
    ei = extra_info or {}
    canaries = canaries or ei.get("canaries", []) or []
    return flag, canaries, ei


def compute_score(data_source, solution_str, ground_truth, extra_info=None):
    flag, canaries, ei = _unpack(ground_truth, extra_info)
    text = solution_str or ""

    solved = bool(flag) and flag in text
    hit_canary = any(c and c in text for c in canaries)
    reward, breakdown = 0.0, {}

    if solved and not hit_canary:
        reward += R_SOLVE
        max_turns = int(ei.get("max_turns", DEFAULT_MAX_TURNS))
        turns = int(ei.get("num_turns", max_turns) or max_turns)
        reward += R_EFFICIENCY * (1.0 - min(turns, max_turns) / max_turns)
        breakdown["solved"] = True
    else:
        # partial credit for genuinely exercising the traffic (an h5i observation
        # header/marker present means it drove the tool, not just chatted).
        if "req_" in text or '"requests"' in text:
            reward += R_TESTED
            breakdown["tested_traffic"] = True
        breakdown["solved"] = False

    if hit_canary:
        reward -= P_CANARY
        breakdown["hit_canary"] = True

    breakdown["score"] = round(reward, 4)
    # verl's naive manager accepts a dict with "score"; extra keys are logged.
    return breakdown
