# h5i-rl

Reinforcement-learning research on [h5i](https://github.com/h5i-dev/h5i): training
a local LLM to red-team web applications through h5i — recovering flags with
fewer turns and better tool discipline — on self-hosted, deliberately-vulnerable
targets. Every target runs in a container we host ourselves; nothing here is
pointed at a third-party server.

## Two parts

- **[`rl/`](rl/)** — the training loop. A self-hosted CTF *environment* over the
  [XBOW][xbow] (104) and [Argus][argus] (71) benchmark suites, a scriptable h5i
  *agent rollout* with per-episode session isolation, a capture-backed GRPO
  *reward* (canary / scope / fabrication penalties), and a
  [verl](https://github.com/volcengine/verl) LoRA *training* scaffold. Start at
  [`rl/README.md`](rl/README.md).
- **[`vault-ctf/`](vault-ctf/)** — the eval harness this grew from: drive a local
  vLLM-served model (via the codex CLI) at WebSecDojo challenges through h5i, and
  A/B h5i changes by turn count. This is *measurement*; `rl/` closes the loop to
  *training*.

## Status

The environment, rollout, and reward have been exercised end-to-end on this
hardware (4× RTX 3090): a challenge builds with a freshly-injected flag, the
policy drives h5i in an isolated session, and a scalar reward comes back. The
verl training step is the remaining unvalidated piece (it needs verl installed
and its version-specific agent-loop glue filled in — see the TODOs in
[`rl/train/agent_loop.py`](rl/train/agent_loop.py)).

## Quickstart

```bash
cd rl
./env/fetch_benchmarks.sh                      # clone the XBOW + Argus suites
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
./eval/smoke.sh xbow XBEN-053-24               # env stands up + is reachable?
MODEL=Qwen/Qwen3-4B python -m agent.rollout --suite xbow --challenge XBEN-053-24
```

Scripts resolve their own location, so both `rl/` and `vault-ctf/` run from
wherever this repo is checked out.

[xbow]: https://github.com/xbow-engineering/validation-benchmarks
[argus]: https://github.com/pensar-x/argus-validation-benchmarks
