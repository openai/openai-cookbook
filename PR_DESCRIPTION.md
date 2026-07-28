## Summary

Adds `articles/gpt-oss/finetune-halo.md`, a guide to post-training `openai/gpt-oss-20b` with [Halo](https://github.com/whitecircle/halo). Halo shards the MoE model for training without ever leaving HuggingFace — Expert/Context/Tensor Parallelism attach as wrappers, so the model stays a `transformers` module and reloads with `from_pretrained`, no checkpoint conversion. One config surface drives three recipes: a full fine-tune with Expert Parallelism on an 8×B300 node, a single-GPU LoRA variant, and an online GRPO (RLVR) pass with verifiable rewards. The guide runs all three end to end on a math task, where the model reasons step by step and boxes a final answer a single regex can grade.

## Motivation

The Cookbook has guides for running and fine-tuning gpt-oss (Transformers, Colab), but none that cover distributed post-training of the MoE model — Expert/Context/Tensor Parallelism, grouped-GEMM expert compute, or verifiable-reward RL — while keeping the model in native HuggingFace form (`from_pretrained`-loadable, no checkpoint conversion). This fills that gap and shows SFT, LoRA, and RL as config changes rather than separate codebases.

---

## For new content

When contributing new content, read through our [contribution guidelines](https://github.com/openai/openai-cookbook/blob/main/CONTRIBUTING.md), and mark the following action items as completed:

- [ ] I have added a new entry in [registry.yaml](https://github.com/openai/openai-cookbook/blob/main/registry.yaml) (and, optionally, in [authors.yaml](https://github.com/openai/openai-cookbook/blob/main/authors.yaml)) so that my content renders on the cookbook website.
- [ ] I have conducted a self-review of my content based on the [contribution guidelines](https://github.com/openai/openai-cookbook/blob/main/CONTRIBUTING.md#rubric):
  - [x] Relevance: This content is related to building with OpenAI technologies and is useful to others.
  - [x] Uniqueness: I have searched for related examples in the OpenAI Cookbook, and verified that my content offers new insights or unique information compared to existing documentation.
  - [x] Spelling and Grammar: I have checked for spelling or grammatical mistakes.
  - [x] Clarity: I have done a final read-through and verified that my submission is well-organized and easy to understand.
  - [ ] Correctness: The information I include is correct and all of my code executes successfully.
  - [x] Completeness: I have explained everything fully, including all necessary references and citations.

We will rate each of these areas on a scale from 1 to 4, and will only accept contributions that score 3 or higher on all areas. Refer to our [contribution guidelines](https://github.com/openai/openai-cookbook/blob/main/CONTRIBUTING.md) for more details.
