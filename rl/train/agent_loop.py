"""verl <-> our environment adapter.

verl (async/server rollout mode) serves the current policy and asks an "agent
loop" to produce a trajectory + reward for a given prompt. Our prompt is a
challenge id; our trajectory is a full h5i-driving episode from agent/rollout.py.

verl's exact hook name and signature depend on the release you install, so the
integration point is isolated here. Fill the two TODOs against your verl commit:

  1. Subclass / register verl's agent-loop base so verl discovers this class
     (in recent verl: `verl.experimental.agent_loop.AgentLoopBase`, registered
     via the rollout config's agent-loop path).
  2. Map verl's served-policy handle onto an OpenAI-compatible base_url so
     agent/rollout.py can call it unchanged (verl exposes the rollout server's
     address at loop-construction time; set OPENAI_BASE_URL from it).

Until then this module is runnable standalone as a rollout *sampler*: it turns a
challenge into an episode dict, which is exactly what verl needs, minus the
tokenization/masking verl does internally on the returned messages.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env.challenge import buildable             # noqa: E402
from agent.rollout import run_episode           # noqa: E402


def sample_episode(challenge, model: str | None = None) -> dict:
    """One (state_0 = challenge) -> full trajectory + scalar reward.

    verl consumes: the message list (it tokenizes and masks tool/observation
    tokens so only assistant tokens get gradient) and `reward`. GRPO then
    normalizes reward within each group of `rollout.n` episodes on the same
    challenge — which is why the group must share one challenge."""
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


# ---- TODO(verl-version): register with verl's agent-loop machinery ----------
# from verl.experimental.agent_loop import AgentLoopBase, register
#
# @register("h5i")
# class H5iAgentLoop(AgentLoopBase):
#     async def run(self, prompt, sampling_params):
#         os.environ["OPENAI_BASE_URL"] = self.server_address  # verl-provided
#         ep = sample_episode(prompt["challenge"], model=self.model_name)
#         return self.to_verl_output(ep["messages"], reward=ep["reward"])


if __name__ == "__main__":
    # Smoke: sample one episode from the current curriculum with a served policy.
    chs = train_challenges()
    if not chs:
        raise SystemExit("no challenges found; run env/fetch_benchmarks.sh first")
    ep = sample_episode(chs[0])
    print({k: ep[k] for k in ("suite", "slug", "reward", "turns", "solved")})
