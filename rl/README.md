# RL fine-tuning for agentic h5i use

This directory closes the loop on the `vault-ctf/` eval harness: instead of only
*measuring* how a local model drives [h5i](../../h5i) against web CTFs, it
*trains* the model to do it better — recovering flags with fewer turns and
better tool discipline — with reinforcement learning.

It is a research setup for **authorized, offline** security testing. Every
target is a deliberately-vulnerable app we host ourselves in a container, so
rollouts never touch a third-party server. That is a hard requirement, not a
nicety: RL needs thousands of episodes.

## The idea in one paragraph

An episode is one CTF attempt. We stand up a vulnerable app in Docker with a
freshly-injected flag, hand the policy model the h5i skill and the task, and let
it drive h5i turn by turn until it declares a flag or runs out of turns. The
**reward** is mostly terminal — did the declared flag match the injected one,
*and* is it backed by bytes h5i actually captured — with small shaping for tool
discipline and efficiency. We sample a group of episodes per challenge and
update the policy with **GRPO** (group-relative, no value network), using LoRA
so rollout and training co-exist on the 4×3090 box. Repeat.

```
challenge pool ──► reset (docker up, inject flag) ──► agent loop (policy ⇄ h5i)
      ▲                                                        │
      │                                              trajectory + reward
   train/val split                                             │
      │                                                        ▼
   GRPO update (verl, LoRA)  ◄──────────────  group of N episodes / challenge
```

## Why the pieces are what they are

- **Environment = self-hosted benchmarks, not live sites.** We use two suites of
  Dockerized web CTFs: [xbow-engineering/validation-benchmarks][xbow] (104
  challenges; flag injected at build time via `--build-arg flag=`, MAPS
  *canaries* planted to catch flag-leak / reward hacking) and
  [pensar-x/argus-validation-benchmarks][argus] (71 challenges, each shipping a
  gold `solve.py` we use for env smoke-tests and — optionally — an SFT
  warm-start). `env/fetch_benchmarks.sh` clones both; `env/challenge.py` gives
  one uniform interface over the two formats.
- **Policy = small model + LoRA + GRPO.** 4×24 GB cannot train a 27B model *and*
  serve it for rollouts. The trainable policy is a 4–8B model (default
  `Qwen/Qwen3-4B`) with LoRA adapters; the 27B cyber models stay as eval
  baselines (`eval/`). GRPO drops PPO's value network, which is what makes this
  fit in memory at all.
- **Reward is capture-backed.** `vault-ctf/scripts/ab-vault.sh` already refused
  to count a flag that only appeared in `SOLUTION.md`; we keep that rule. A flag
  scores only if it matches the injected value **and** appears in an h5i-captured
  response body/header. A planted canary in the declared answer is a penalty, not
  a reward — see `reward/reward.py`.
- **Agent loop is scriptable, not codex.** `codex exec` is great for the eval
  harness but is a heavy black box for RL: we need temperature sampling, per-turn
  token masking, and logprobs. `agent/rollout.py` is a thin loop that speaks the
  same h5i CLI but is fully controllable and returns a token-level trajectory.

## Layout

```
rl/
  env/
    fetch_benchmarks.sh   # clone xbow + argus suites into env/benchmarks/ (gitignored)
    challenge.py          # uniform Challenge interface: build, up, base_url, flag, canaries, down
  agent/
    tools.py              # h5i command surface as JSON tool schemas the policy calls
    rollout.py            # run ONE episode -> token-level trajectory + reward
  reward/
    reward.py             # capture-backed terminal reward + shaping + canary/scope penalties
  train/
    grpo.yaml             # verl config: Qwen3-4B, LoRA, GRPO, vLLM rollout
    run_grpo.sh           # launcher
    agent_loop.py         # verl <-> rollout.py adapter  (version-specific glue: see TODOs)
  eval/
    smoke.sh              # sanity: can one challenge stand up and be reached?
    build_sweep.py        # which challenges build+run today -> build_sweep.csv (the trainable pool)
    confirm_solve.py      # drive a known SSTI to a real flag capture; assert the +1.0 reward fires
    build_sweep.csv       # (generated) per-challenge builds/runs/reachable + failure note
  requirements.txt
```

## Runbook

```bash
# 0. one-time: benchmarks + python deps
./env/fetch_benchmarks.sh
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

# 1. lock down the trainable pool: which challenges build+run here today?
python -m eval.build_sweep xbow          # writes eval/build_sweep.csv
python -m eval.confirm_solve             # assert the capture-backed +1.0 reward fires

# 1b. quick single-challenge sanity
./eval/smoke.sh xbow XBEN-053-24

# 2. serve the policy for rollouts (small model; leaves cards for LoRA training)
MODEL=Qwen/Qwen3-4B ../vault-ctf/scripts/serve-model.sh   # or verl's own rollout engine

# 3. one rollout end-to-end (no training) to eyeball trajectories + reward
python -m agent.rollout --suite xbow --challenge XBEN-001-24 --max-turns 25

# 4. GRPO training
./train/run_grpo.sh
```

## Guardrails that are part of the design

- **Scope containment.** The reward penalizes any request whose host is not the
  challenge's own container. This is the same discipline h5i's skill preaches,
  and it keeps a trained policy from learning to wander off-target.
- **No reward hacking on a fixed string.** Flags are re-injected per episode
  (XBOW) or read from the challenge's answer key (Argus); the policy cannot
  memorize one literal. Canaries turn "grabbed a decoy" into a negative signal.
- **Offline only.** Containers run on an internal Docker network; nothing here is
  pointed at the internet or at anyone else's infrastructure.

## What still needs deciding / doing

- **verl version glue** (`train/agent_loop.py`): verl's multi-turn/agent-loop API
  moves between releases. The adapter is written against the async server-mode
  rollout; pin it to the verl commit you install and fill the marked TODOs.
- **h5i-side changes (the `h5i` `rl-env` branch).** Two would materially help and
  belong in h5i, not here: (1) a `--json` flag on every read verb so observations
  are structured for *all* commands, not just `websec requests`; (2) a clean
  per-episode reset (drop captured session state) so rollouts don't leak between
  episodes. Tracked separately from this Python harness.
- **Curriculum.** Start on `level: 1` challenges only; widen to 2–3 once solve
  rate on level 1 is stable. `env/challenge.py` exposes `level` for this, and
  `train_challenges()` already filters to `buildable("xbow")` level-1 first.
- **Benchmark bit-rot.** Many 2024 XBOW challenges pin EOL base images whose apt
  repos now 404, so only a subset builds today. `eval/build_sweep.py` records the
  usable set in `build_sweep.csv`; `challenge.buildable()` reads it so the
  trainer never picks a challenge that cannot come up.

[xbow]: https://github.com/xbow-engineering/validation-benchmarks
[argus]: https://github.com/pensar-x/argus-validation-benchmarks
