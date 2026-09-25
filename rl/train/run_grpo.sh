#!/usr/bin/env bash
# GRPO training: policy learns to drive h5i at the challenge pool.
#
# Prereqs (see README "What still needs doing"):
#   1. verl venv with the driver-compatible stack (see requirements.txt):
#      verl 0.8.0 + vllm 0.8.5.post1 + torch 2.6.0+cu124 + transformers 4.51.3.
#      (verl 0.9.1 needs vllm>=0.18 -> CUDA 13.0, too new for this 12.6 driver.)
#      Set VERL_PY to that venv's python.
#   2. The GPUs must be free -- stop the eval vLLM server first (it fills all 4):
#      docker stop vllm-cyber   # restart later with vault-ctf/scripts/serve-model.sh
#   3. A challenge pool + dataset:  python -m env.serve_pool --n 8 --out data
# If the FSDP model demands flash-attn (not installed by --no-deps), add:
#   actor_rollout_ref.model.attn_implementation=sdpa
#
# verl's idiom is CLI overrides on top of its ppo_trainer defaults (this is the
# runnable source of truth; train/grpo.yaml documents the same settings + why).
set -euo pipefail
cd "$(dirname "$0")/.."                      # -> rl/
RL="$PWD"
VERL_PY="${VERL_PY:-/home/ht2673/Dev/verl-venv/bin/python}"
MODEL="${MODEL:-Qwen/Qwen3-4B}"

[ -f data/train.parquet ] || { echo "no dataset; run: $VERL_PY -m env.serve_pool --n 8 --out data"; exit 1; }
command -v h5i >/dev/null || { echo "h5i not on PATH"; exit 1; }

# train/ on PYTHONPATH so verl's importlib loader finds h5i_tool; rl/ so it can
# import agent.tools / reward.reward. H5I_RL_STATE_ROOT isolates per-rollout h5i.
export PYTHONPATH="$RL:$RL/train:${PYTHONPATH:-}"
export H5I_RL_STATE_ROOT="${H5I_RL_STATE_ROOT:-/tmp/h5i-rl-sessions}"

exec "$VERL_PY" -m verl.trainer.main_ppo \
  algorithm.adv_estimator=grpo \
  data.train_files="$RL/data/train.parquet" \
  data.val_files="$RL/data/val.parquet" \
  data.return_raw_chat=True \
  data.train_batch_size=8 \
  data.max_prompt_length=4096 \
  data.max_response_length=8192 \
  actor_rollout_ref.model.path="$MODEL" \
  actor_rollout_ref.model.lora_rank=32 \
  actor_rollout_ref.model.lora_alpha=64 \
  actor_rollout_ref.model.target_modules=all-linear \
  actor_rollout_ref.actor.optim.lr=1e-6 \
  actor_rollout_ref.actor.ppo_mini_batch_size=8 \
  actor_rollout_ref.actor.use_kl_loss=True \
  actor_rollout_ref.actor.fsdp_config.param_offload=True \
  actor_rollout_ref.actor.fsdp_config.optimizer_offload=True \
  actor_rollout_ref.rollout.name=vllm \
  actor_rollout_ref.rollout.mode=async \
  actor_rollout_ref.rollout.n=8 \
  actor_rollout_ref.rollout.temperature=0.9 \
  actor_rollout_ref.rollout.tensor_model_parallel_size=2 \
  actor_rollout_ref.rollout.gpu_memory_utilization=0.5 \
  actor_rollout_ref.rollout.multi_turn.enable=True \
  actor_rollout_ref.rollout.multi_turn.format=hermes \
  actor_rollout_ref.rollout.multi_turn.tool_config_path="$RL/train/h5i_tools.yaml" \
  actor_rollout_ref.rollout.multi_turn.max_assistant_turns=25 \
  actor_rollout_ref.rollout.multi_turn.max_tool_response_length=4096 \
  custom_reward_function.path="$RL/train/h5i_reward.py" \
  custom_reward_function.name=compute_score \
  trainer.n_gpus_per_node=4 \
  trainer.nnodes=1 \
  trainer.total_epochs=30 \
  trainer.save_freq=25 \
  trainer.test_freq=25 \
  trainer.project_name=h5i-rl \
  trainer.experiment_name=qwen3-4b-grpo-lora \
  trainer.logger=[console] \
  "$@"
