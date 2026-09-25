#!/usr/bin/env bash
# Serve GPT-OSS-Cybersecurity-20B on the 4x RTX 3090s for the codex harness.
#
# TP=4 rather than 2: the weights are ~42GB bf16, so two cards (48GB) leave
# almost nothing for KV cache. Across four there is ~50GB left, which is what
# a long agent session actually needs.
#
# Tool parser: gpt-oss speaks harmony, which /v1/responses parses natively --
# for THAT model passing --tool-call-parser made vLLM leak the channel token
# into the tool name and codex saw
#   unsupported call: exec_command<|channel|>commentary
# Qwen is not harmony, so it does need an explicit parser. Set TOOL_FLAGS=""
# when serving gpt-oss again.
#
# --reasoning-parser qwen3 matters as much as the tool parser: without it
# Qwen's <think> block is returned as the assistant message body, so codex
# sees a long text answer instead of a tool call and ends the turn. That
# looked exactly like the model refusing to act.
#
# --override-generation-config caps a single turn's generation. Qwen3.5 ran
# ~25k tokens of uninterrupted thinking on the pebble GraphQL challenge and
# never emitted a tool call, so the turn never ended. 8k is enough for a think
# plus a tool call, and forces the turn to close either way.
#
# gpt-oss uses attention sinks; on Ampere vLLM picks the TRITON_ATTN backend
# for that automatically, so no backend env var is needed.
#
# --tmpfs /usr/local/cuda/compat: the image ships CUDA forward-compat libs
# (libcuda 575.57.08) and the container runtime prefers them over the host's
# real 560.35.03 driver. Forward compat is a datacenter-GPU feature; on GeForce
# it fails with "Error 804: forward compatibility was attempted on non
# supported HW". Masking the directory makes the loader fall back to the host
# driver, which is what we want.
set -euo pipefail

MODEL="${MODEL:-Qwen/Qwen3.5-27B}"
CACHE="/tmp/ht2673-hf-cache"   # local NVMe; /local0 is not writable and NFS is slow

mkdir -p "$CACHE"

exec docker run --rm --name vllm-cyber \
  --gpus all \
  --ipc=host \
  --tmpfs /usr/local/cuda/compat \
  -p 8000:8000 \
  -v "$CACHE:/root/.cache/huggingface" \
  vllm/vllm-openai:v0.29.0-cu129 \
    --model "$MODEL" \
    --served-model-name "$MODEL" \
    --tensor-parallel-size 4 \
    --max-model-len 131072 \
    --override-generation-config '{"max_new_tokens": 8000}' \
    --gpu-memory-utilization 0.92 \
    ${TOOL_FLAGS:---enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3} \
    --api-key dummy \
    --host 0.0.0.0 --port 8000
