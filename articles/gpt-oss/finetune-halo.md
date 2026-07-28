# Fine-tune gpt-oss with Halo

Teach [openai/gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) to solve math step by step and give a checkable final answer. A full fine-tune across 8 GPUs with Expert Parallelism, then a single-GPU LoRA variant and an online reinforcement-learning pass that rewards correct answers directly.

## A framework built for post-training

[Halo](https://github.com/whitecircle/halo) is the post-training framework we build at White Circle. It does one thing differently: your model stays a plain HuggingFace model the whole way through.

Most frameworks that can train a big Moe model make you convert it first. You port it to their model definition. You learn their checkpoint format. You hope it converts back. Halo skips all of that. We add Expert, Context, Tensor and Expert-Tensor Parallelism as thin wrappers around the modules you already have. Nothing gets rewritten. The model stays a `transformers` module, and the checkpoint loads with `from_pretrained`. It is the same line you always use.

It is also fast. On gpt-oss-20b we hit about 3× the tokens per second per GPU of the stock TRL `SFTTrainer`, and we use less memory doing it. We beat NeMo AutoModel, Axolotl, ms-swift and Megatron-LM in the same benchmarks. Full numbers are in our release blogpost.

And it is one tool, not three. SFT, LoRA and RL all read the same config. Moving between the sections below is a config change, not a new codebase.

---

## What this cookbook builds

gpt-oss reasons before it answers. That makes it a strong base for mathematics, because the chain of thought is where the work happens and the final answer can be checked. In this cookbook we fine-tune [openai/gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) to solve problems step by step and put its final answer in `\boxed{...}`. A single regex can grade that format.

The main path is a full fine-tune. Every weight is updated rather than an adapter, because stronger reasoning changes what the model computes and not how it phrases things. gpt-oss-20b trains on a single B300. Distributing its 32 experts across an 8-GPU node with Expert Parallelism trains it several times faster at a fraction of the per-GPU memory. Two shorter sections follow. One covers a single-GPU [LoRA](https://arxiv.org/abs/2106.09685) variant for quick iteration. The other covers an online reinforcement-learning pass that rewards correct answers directly.

> 🖥️ **8×B300.** The full fine-tune uses one 8-GPU B300 node, and every figure in this cookbook is measured on B300. The LoRA section runs on a single GPU. The RL section needs one extra GPU to serve rollouts.

## Build and start the training image

We run everything inside a Docker image that pins the full stack. PyTorch 2.11 on CUDA 13, [Transformers](https://github.com/huggingface/transformers), [TRL](https://github.com/huggingface/trl), [PEFT](https://github.com/huggingface/peft), [Liger](https://github.com/linkedin/Liger-Kernel), [DeepEP](https://github.com/deepseek-ai/DeepEP) and [Flash Attention](https://github.com/Dao-AILab/flash-attention). There is nothing to `pip install`. Build the image for your GPU architecture once.

```bash
git clone --recurse-submodules https://github.com/whitecircle/halo
cd halo
make build-blackwell     # B200 / B300  -> halo:blackwell
make build-hopper        # H100 / H200  -> halo:hopper
```

Put `HF_TOKEN` and `WANDB_API_KEY` in a `.env` file at the repository root, then start the container.

```bash
docker run --rm -it --gpus all \
  --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 --shm-size=128g \
  --env-file .env \
  -e HF_HOME=/mnt/hf -e HF_DATASETS_CACHE=/mnt/hf/datasets \
  -e TMPDIR=/mnt/tmp -e PYTHONPATH=/workspace \
  -e CUDA_DEVICE_MAX_CONNECTIONS=1 \
  -v $(pwd):/workspace -v /mnt:/mnt -w /workspace \
  halo:blackwell
```

Everything below runs inside this container. The `-v /mnt:/mnt` mount points the model cache and checkpoints at a large volume. Adjust it to your disk layout.

## Shape the training data

The supervised stage teaches the format. The model reads a problem, reasons through it, then states the final answer in `\boxed{...}`. Each record is a short conversation with a system prompt, the problem, and a worked solution that ends in the boxed answer.

```json
{
  "prompt": [
    {"role": "system", "content": "You are a math tutor. Solve the problem step\nby step, then give the final answer on the last line as \\boxed{...}."},
    {"role": "user", "content": "A right triangle has legs 6 and 8. Find the hypotenuse."},
    {"role": "assistant", "content": "By the Pythagorean theorem,\nh = sqrt(6^2 + 8^2) = sqrt(100) = 10.\n\nThe answer is \\boxed{10}."}
  ]
}
```

The final answer is wrapped in `\boxed{...}` so one regex can extract it, and the reinforcement-learning stage rewards that same signal. `train_only_on_completions: true` masks the loss to the solution turn, so the model learns to *produce* the reasoning and answer instead of echoing the problem. Point `dataset` at a Hub id, a local JSON or JSONL path, or an `s3://` URI.

## Train all weights with Expert Parallelism

The run is one YAML file. gpt-oss-20b holds 32 experts per MoE layer. We place 4 experts on each of 8 GPUs and route tokens to them with [DeepEP](https://github.com/deepseek-ai/DeepEP) all-to-all, while every GPU keeps its own batch. The effective batch is the per-device batch times the accumulation steps times all 8 data-parallel ranks.

```yaml
# training_configs/sft/gptoss/oss-20b-math-reasoner.yaml
model_name_or_path: openai/gpt-oss-20b
trust_remote_code: true
model_init_kwargs:
  output_router_logits: true        # enable the MoE router auxiliary loss
  router_aux_loss_coef: 0.001

# --- Dataset ---
dataset:
  - whitecircle/math-reasoning-sft@train   # {"prompt": [system, user, assistant]}
test_size: 0.02
conversation_field: prompt
train_only_on_completions: true      # train on the solution turn only
assistant_message_template: "<|start|>assistant"

# --- Parallelism: distribute the 32 experts across 8 GPUs ---
expert_parallel_size: 8
ep_scope: node                       # one NVLink domain
use_grouped_gemm: true
save_sharded_ep: false               # gather to a standard HF checkpoint

# --- Kernels & precision ---
attn_implementation: flash_attention_4
use_liger_kernel: true
bf16: true
packing: true
max_length: 4096

# --- Schedule ---
per_device_train_batch_size: 2
gradient_accumulation_steps: 8       # effective batch = 2 x 8 x dp_size(8) = 128
num_train_epochs: 3.0
gradient_checkpointing: true
optim: adamw_torch_fused
learning_rate: 5.0e-06               # full fine-tuning band
lr_scheduler_type: cosine
warmup_ratio: 0.03
max_grad_norm: 1.0

# --- Checkpoint & eval ---
output_dir: checkpoints/oss-20b-math-reasoner
save_strategy: steps
save_steps: 500
eval_strategy: steps
eval_steps: 200
save_total_limit: 2
logging_steps: 5
report_to: wandb
```

`halo launch` resolves the method to its training script. With `--nproc 8` it launches under `torchrun`, which Expert Parallelism requires.

```bash
halo launch sft training_configs/sft/gptoss/oss-20b-math-reasoner.yaml --nproc 8
```

We apply some defaults for you. `bf16` and Liger fused kernels are on unless disabled. The bf16 optimizer holds weights and both Adam moments at 6 bytes per parameter, half of fp32 Adam. Peak memory per GPU falls as the expert degree rises.

| expert_parallel_size | Experts per GPU | Peak memory per GPU |
| --- | --- | --- |
| 2 | 16 | over 139 GB |
| 4 | 8 | ~75 GB |
| 8 | 4 | ~48 GB |

Figures for gpt-oss-20b on 8×B300 at this sequence length. They grow with `max_length`. If your solutions run long, raise `max_length` or add `--context_parallel_size 2` to split the sequence across GPU pairs, which composes with Expert Parallelism.

On save, we gather the distributed experts into a standard HuggingFace checkpoint. We write sharded safetensors with an index that `from_pretrained` can load, which takes about a minute for the 20B model. The result is an ordinary gpt-oss model, so inference is stock Transformers. Extract the boxed answer and compare it to held-out gold.

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
import re

path = "checkpoints/oss-20b-math-reasoner"
tok = AutoTokenizer.from_pretrained(path)
model = AutoModelForCausalLM.from_pretrained(
    path, torch_dtype="bfloat16", device_map="cuda"
)

SYSTEM = ("You are a math tutor. Solve the problem step by step, then give the "
          "final answer on the last line as \\boxed{...}.")

def solve(problem):
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": problem}]
    inputs = tok.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt"
    ).to(model.device)
    out = model.generate(inputs, max_new_tokens=512)
    reply = tok.decode(out[0][inputs.shape[-1]:], skip_special_tokens=True)
    boxed = re.findall(r"\\boxed\{(.+?)\}", reply)
    return (boxed[-1] if boxed else "unparsed"), reply

answer, work = solve("If 3(x - 2) = 2x + 1, find x.")
print(answer)   # -> "7"
```

## LoRA variant, a single-GPU adapter for fast iteration

For quick iteration a LoRA adapter trains on one GPU in a fraction of the time and disk. It updates small rank-decomposed matrices while the base stays frozen. Replace the parallelism block with the PEFT block. The dataset and prompt format do not change.

```yaml
# swap the parallelism/precision block above for a single-GPU LoRA run
# (remove expert_parallel_size / ep_scope / use_grouped_gemm / save_sharded_ep)
use_peft: true
lora_r: 16
lora_alpha: 32
lora_target_modules: [q_proj, k_proj, v_proj, o_proj, experts]
merge_expert_lora_on_save: true      # fold expert adapters into the base at save
learning_rate: 1.0e-04               # LoRA band, about 10x the full-FT rate
```

gpt-oss stores its experts as fused 3D tensors rather than `nn.Linear` modules, so PEFT's usual `all-linear` target cannot reach them. Listing `experts` in `lora_target_modules` routes those projections to the grouped LoRA adapters we build inside the MoE wrapper. They adapt every layer's experts and train in the same grouped-GEMM kernel as the base. `merge_expert_lora_on_save: true` folds the deltas into the base at save time. LoRA trains far fewer parameters and wants roughly 10× the full fine-tuning rate. 1e-4 is a good start.

```bash
halo launch sft training_configs/sft/gptoss/oss-20b-math-reasoner-lora.yaml
```

If you train an attention-only adapter instead, with no `experts` entry and no merge flag, fold it into the base afterward with the merge tool.

```bash
halo run merge-peft-adapters -- \
    --adapter_dir checkpoints/oss-20b-math-reasoner \
    --output_dir  checkpoints/oss-20b-math-reasoner-merged
```

Use LoRA to explore, then re-run the full fine-tune for the checkpoint you ship. A reasoning gain across many problem types benefits from updating every weight.

## Reinforcement-learning variant, reward correct answers directly

Supervised fine-tuning imitates worked solutions. It does not directly reward getting the answer right. Online [GRPO](https://arxiv.org/abs/2402.03300) does. For each problem the policy samples a group of solutions and grades each one. The policy then moves toward the solutions that scored above the group average. The reward is verifiable, with no reward model and no human in the loop, because the final answer can be checked against the gold answer.

The reward has two parts. The accuracy reward extracts the `\boxed{...}` answer and returns 1.0 when it matches the gold answer and 0.0 otherwise. A small format reward pays for emitting a well-formed boxed answer at all, which stops early and badly formatted samples from starving the accuracy signal. This stage needs only problems and answers. The reasoning is generated and graded rather than supervised.

```yaml
# training_configs/grpo/online/oss-20b-math-rlvr.yaml
model_name_or_path: checkpoints/oss-20b-math-reasoner   # start from the SFT model
attn_implementation: flash_attention_4

# --- Dataset: problem + gold answer, no worked solution needed ---
dataset: whitecircle/math-reasoning-sft:labeled@train   # {"question": ..., "answer": ...}
prompt_field: question
answer_field: answer                 # the gold final answer

# --- Reward: verifiable match on the \boxed{} answer ---
use_accuracy_reward: true            # 1.0 if boxed answer == gold, else 0.0
accuracy_reward_weight: 1.0
use_format_reward: true              # reward emitting a well-formed boxed answer
format_pattern: "\\\\boxed\\{.+?\\}"
format_reward_weight: 0.2

# --- GRPO ---
num_generations: 8                   # samples per problem (the "group")
beta: 0.0                            # no KL penalty
epsilon: 0.15
temperature: 1.0
loss_type: grpo
max_prompt_length: 1024
max_completion_length: 1024

# --- Training ---
expert_parallel_size: 4              # 4 training GPUs; vLLM holds the rest
per_device_train_batch_size: 2
gradient_accumulation_steps: 8
learning_rate: 1.0e-06               # RL band, below SFT
lr_scheduler_type: cosine
warmup_steps: 20
bf16: true
output_dir: checkpoints/oss-20b-math-reasoner-rl
```

Online GRPO generates from a [vLLM](https://github.com/vllm-project/vllm) server that runs in a separate container. vLLM's dependency set is incompatible with the training image, so we keep them apart and sync weights over NCCL. Start the server on a spare GPU, then launch Expert-Parallel training on four.

```bash
# GPU 4: serve the current policy for rollouts (built from Dockerfile.vllm)
docker run --gpus '"device=4"' --network=host --ipc=host \
    vllm-server:0.20 checkpoints/oss-20b-math-reasoner --port 8000 \
    --weight-transfer-config '{"backend": "nccl"}'
```

```bash
# GPUs 0-3: Expert-Parallel training, weights synced to the vLLM server over NCCL
halo launch rlvr training_configs/grpo/online/oss-20b-math-rlvr.yaml --nproc 4
```

After each optimizer step we push the updated weights to the vLLM server over NCCL, so rollouts always come from the current policy. `num_generations: 8` sets the group size. Larger groups give a lower-variance advantage estimate at higher rollout cost. Keep the learning rate below the SFT rate, 1e-6 here, because RL updates are noisier and the policy should move slowly. Start RL from the SFT checkpoint rather than the base. The model must already emit the boxed format for the accuracy reward to have signal.

Online GRPO is one of several reinforcement-learning paths we support. **Offline GRPO** trains from completions you have already scored, so it needs no live generation. **Environmental GRPO** runs multi-turn rollouts against a tool-using environment with Ray actors driving the episodes, which suits code contests, search and other agentic tasks. On the preference side, **DPO**, **SMPO** and **KTO** optimize against pairs or labels instead of a reward function. All of them share the config surface used above.

> ✅ **Verifiable reward.** A math answer can be checked, so the reward is an exact-match grade rather than a learned reward model. That removes the usual reward-hacking surface and optimizes the policy against ground truth.

## Where to go from here

The YAML blocks used here cover the model, dataset, parallelism, PEFT, schedule and reward. They are shared across our trainers, so moving to another method is a config change rather than new code. For harder benchmarks, scale the dataset and raise `max_completion_length` so the model has room to reason. The recipe index in the [documentation](https://github.com/whitecircle/halo/tree/main/docs) lists a ready config for each method.
