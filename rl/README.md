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
    serve_pool.py         # (env/) bring up a persistent pool of challenges + emit the verl parquet
  agent/
    tools.py              # h5i command surface as JSON tool schemas the policy calls
    rollout.py            # run ONE episode -> token-level trajectory + reward
  reward/
    reward.py             # capture-backed terminal reward + shaping + canary/scope penalties
  train/
    h5i_tool.py           # h5i verbs as verl BaseTools (verl 0.9.1); per-rollout isolated session
    h5i_tools.yaml        # tool-config: lists the h5i verbs for verl's ToolAgentLoop
    h5i_reward.py         # verl custom reward: capture-backed flag + canary penalty over the trajectory
    grpo.yaml             # documented reference for the run (run_grpo.sh is the runnable truth)
    run_grpo.sh           # launcher: verl GRPO with the h5i tool/agent/reward wired in
    agent_loop.py         # standalone (non-verl) episode sampler + the curriculum selector
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

# 2. one rollout end-to-end (no training) to eyeball trajectories + reward
MODEL=Qwen/Qwen3-4B ../vault-ctf/scripts/serve-model.sh &   # policy on an OpenAI endpoint
python -m agent.rollout --suite xbow --challenge XBEN-053-24 --max-turns 25

# 3. GRPO training (verl-native: h5i tools + ToolAgentLoop + capture-backed reward)
python -m env.serve_pool --n 8 --out data    # persistent challenge pool + parquet dataset
./train/run_grpo.sh                          # needs verl venv (torch cu124) + free GPUs
python -m env.serve_pool --down              # tear the pool down when finished
```

## Guardrails that are part of the design

- **Scope containment.** In the verl path it is enforced by construction:
  `browser_open` only ever opens the challenge's own base_url, never a URL the
  policy supplies. The standalone reward additionally penalizes any
  agent-initiated request to another host.
- **No reward hacking on a fixed string.** Flags are re-injected per run (a fresh
  random value each time the pool comes up), so the policy cannot memorize a
  literal, and an unguessable flag appearing in the trajectory can only mean it
  was extracted through h5i. Canaries turn "grabbed a decoy" into a negative
  signal.
- **Offline only.** Containers run on an internal Docker network; nothing here is
  pointed at the internet or at anyone else's infrastructure.

## What still needs deciding / doing

- **verl integration: done (verl 0.9.1), import-verified.** h5i is expressed as
  verl `BaseTool`s (`train/h5i_tool.py`, `h5i_tools.yaml`) driven by verl's
  ToolAgentLoop, with `train/h5i_reward.py` as the reward and `env/serve_pool.py`
  producing the pool + dataset. The tool config, tool schemas and reward all load
  and score correctly against an installed verl 0.9.1.
- **Before an actual GPU run** (two environment gates, not code):
  (1) The verl venv's default torch is a **cu130** wheel, but this box's driver is
  **CUDA 12.6** — reinstall torch built for cu124 (or cu121) plus a matching
  `vllm`, or verl will refuse to use the GPUs. (2) The eval vLLM server fills all
  4 cards; **stop it first** so training has memory. Then `env/serve_pool.py` +
  `train/run_grpo.sh`.
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
