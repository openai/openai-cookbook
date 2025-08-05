# How to run gpt-oss with Hugging Face Transformers

The [Transformers](https://huggingface.co/docs/transformers/en/index) library by [Hugging Face](https://huggingface.co/) provides a flexible way to load and run large language models locally or on a server. This guide will walk you through running [OpenAI gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) or [OpenAI gpt-oss-120b](https://huggingface.co/openai/gpt-oss-120b) using Transformers, either with a high-level pipeline or via low-level `generate` calls with raw token IDs.

Transformers allows you to run inference in two modes:  
1\. Transformers Serve (Responses \+ Chat Completions API server)  
2\. Directly via Python code.

In this guide we’ll run through various optimised ways to run the **gpt-oss models via Transformers.**

Bonus: You can also fine-tune models via transformers, [check out our fine-tuning guide here](https://cookbook.openai.com/articles/gpt-oss/fine-tune-transformers).

## Pick your model

Both [**gpt-oss** models are available on Hugging Face](https://huggingface.co/collections/openai/gpt-oss-68911959590a1634ba11c7a4):

- [**`openai/gpt-oss-20b`**](https://huggingface.co/openai/gpt-oss-20b)
  - \~16GB VRAM requirement
  - Great for single higher-end consumer GPUs
- [**`openai/gpt-oss-120b`**](https://huggingface.co/openai/gpt-oss-120b)
  - Requires ≥60GB VRAM or multi-GPU setup
  - Ideal for H100/A100-class hardware

Both are **MXFP4 quantized** by default.

## Quick setup

1. **Install dependencies**  
   It’s recommended to create a fresh Python environment. Install Transformers and Accelerate:

```bash
pip install -U transformers accelerate torch triton kernelspip install git+https://github.com/triton-lang/triton.git@main#subdirectory=python/triton_kernels
```

2. **(Optional) Enable multi-GPU**  
   If you’re running large models, use Accelerate to handle device mapping automatically.

## Create an Open AI Responses / Chat Completions endpoint

To launch a server, simply use the transformers serve CLI command:

```bash
transformers serve
```

The simplest way to interact with the server is through our transformers chat CLI

```bash
transformers chat localhost:8000 --model-name-or-path openai/gpt-oss-20b
```

or by sending an HTTP request with cURL, e.g.

```bash
curl -X POST http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{"messages": [{"role": "system", "content": "hello"}], "temperature": 0.9, "max_tokens": 1000, "stream": true, "model": "openai/gpt-oss-20b"}'
```

## Quick inference with pipeline

The easiest way to run gpt-oss is with the Transformers `pipeline` API:

```py
from transformers import pipeline

generator = pipeline(
    "text-generation",
    model="openai/gpt-oss-20b",
    torch_dtype="auto",
    device_map="auto"  # Automatically place on available GPUs
)

messages = [
    {"role": "user", "content": "Explain what MXFP4 quantization is."},
]

result = generator(
    messages,
    max_new_tokens=200,
    temperature=1.0,
)

print(result[0]["generated_text"])
```

## Advanced inference with `.generate()`

If you want more control over sampling, you can load the model and tokenizer manually:

```py
from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "openai/gpt-oss-20b"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype="auto",
    device_map="auto"
)

inputs = tokenizer(
    "Explain what MXFP4 quantization is.",
    return_tensors="pt"
).to(model.device)

outputs = model.generate(
    **inputs,
    max_new_tokens=200,
    temperature=0.7
)

print(tokenizer.decode(outputs[0], skip_special_tokens=True))
```

## Chat template and tool calling

gpt-oss models use the [harmony response format](https://cookbook.openai.com/article/harmony) for structuring messages, incl. reasoning and tool calls.

To construct prompts you can use the built-in chat template of Transformers or alternatively for more control you can use the [openai-harmony library](https://github.com/openai/harmony).

To use the chat template:

```py
from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "openai/gpt-oss-20b"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    device_map="auto",
    torch_dtype="auto",
)

messages = [
    {"role": "user", "content": "Who are you?"},
]

inputs = tokenizer.apply_chat_template(
    messages,
    add_generation_prompt=True,
    tokenize=True,
    return_tensors="pt",
    return_dict=True,
).to(model.device)

generated = model.generate(**inputs, max_new_tokens=100)
print(tokenizer.decode(generated[0][inputs["input_ids"].shape[-1] :]))
```

To integrate the [`openai-harmony`](https://github.com/openai/harmony) library to prepare prompts and parse responses first install the library:

```bash
pip install openai-harmony
```

Here’s an example of how to then use the library to construct your prompts and encode them to tokens:

```py
import json
from openai_harmony import (
    HarmonyEncodingName,
    load_harmony_encoding,
    Conversation,
    Message,
    Role,
    SystemContent,
    DeveloperContent
)
from transformers import AutoModelForCausalLM, AutoTokenizer

encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)

# Build conversation
convo = Conversation.from_messages([
    Message.from_role_and_content(Role.SYSTEM, SystemContent.new()),
    Message.from_role_and_content(
        Role.DEVELOPER,
        DeveloperContent.new().with_instructions("Always respond in riddles")
    ),
    Message.from_role_and_content(Role.USER, "What is the weather like in SF?")
])

# Render prompt
prefill_ids = encoding.render_conversation_for_completion(convo, Role.ASSISTANT)
stop_token_ids = encoding.stop_tokens_for_assistant_action()

# Load model
model_name = "openai/gpt-oss-20b"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype="auto", device_map="auto")

# Generate
outputs = model.generate(
    input_ids=[prefill_ids],
    max_new_tokens=128,
    eos_token_id=stop_token_ids
)

# Parse completion tokens
completion_ids = outputs[0][len(prefill_ids):]
entries = encoding.parse_messages_from_completion_tokens(completion_ids, Role.ASSISTANT)

for message in entries:
    print(json.dumps(message.to_dict(), indent=2))
```

## Multi-GPU & distributed inference

For large models like gpt-oss-120b, you can:

- Use `tp_plan="auto"` for automatic placement and tensor parallelism
- Launch with `accelerate launch or torchrun` for distributed setups
- Leverage Expert Parallelism and specialised Flash attention kernels for faster inference

```py
from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig
import torch
from transformers.distributed import DistributedConfig

model_path = ""
tokenizer = AutoTokenizer.from_pretrained(model_path, padding_side="left")

# Set up chat template
messages = [
     {"role": "user", "content": "Explain how expert parallelism works in large language models."}
]
chat_prompt = tokenizer.apply_chat_template(messages, tokenize=False)

generation_config = GenerationConfig(
    max_new_tokens=1024,
    do_sample=True,
)

device_map = {
    "distributed_config": DistributedConfig(enable_expert_parallel=1),  # Enable Expert Parallelism
    "tp_plan": "auto",  # Enables Tensor Parallelism
}

model = AutoModelForCausalLM.from_pretrained(
    model_path,
    torch_dtype="auto",
    attn_implementation="vllm-flash-attn3:flash_attn_varlen_func",
    **device_map,
)

model.eval()

# Tokenize and generate
inputs = tokenizer(chat_prompt, return_tensors="pt").to("cuda")
outputs = model.generate(**inputs, generation_config=generation_config)

# Decode and print
response = tokenizer.decode(outputs[0], skip_special_tokens=True)
print("Model response:", response.split("assistant\n")[-1].strip())

```

You can then run this generation via

```bash
torchrun --nproc_per_node=2 generate.py
```
