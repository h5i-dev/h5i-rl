#!/usr/bin/env bash
# Launch GRPO training. Assumes verl is installed in the active venv and the
# benchmarks are fetched. The policy is served by verl's own async rollout
# engine (mode: async in grpo.yaml), so do NOT also run vault-ctf/serve-model.sh
# here -- that one is for eval/standalone rollouts.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v verl >/dev/null 2>&1 || { echo "verl not on PATH; pip install verl (pin your commit)"; exit 1; }
[ -d env/benchmarks/xbow ] || { echo "run env/fetch_benchmarks.sh first"; exit 1; }

# verl reads hydra-style overrides; the config path is train/grpo.yaml.
# The agent-loop class is registered in train/agent_loop.py (see its TODOs).
exec python -m verl.trainer.main_ppo \
  --config-path "$PWD/train" \
  --config-name grpo \
  "$@"
