# How to run gpt-oss with vLLM

[vLLM](https://docs.vllm.ai/en/latest/) is an open-source, high-throughput inference engine designed to efficiently serve large language models (LLMs) by optimizing memory usage and processing speed. This guide will walk you through how to use vLLM to set up **gpt-oss-20b** or **gpt-oss-120b** on a server to serve gpt-oss as an API for your applications, and even connect it to the Agents SDK.

Note that this guide is meant for server applications with dedicated GPUs like NVIDIA’s H100s. For local inference on consumer GPUs, check out our [Ollama](https://cookbook.openai.com/articles/gpt-oss/run-locally-ollama) or [LM Studio](https://cookbook.openai.com/articles/gpt-oss/run-locally-lmstudio) guides.

## Pick your model

vLLM supports both model sizes of gpt-oss:

- [**`openai/gpt-oss-20b`**](https://huggingface.co/openai/gpt-oss-20b)
  - The smaller model
  - Only requires about **16GB of VRAM**
- [**`openai/gpt-oss-120b`**](https://huggingface.co/openai/gpt-oss-120b)
  - Our larger full-sized model
  - Best with **≥60GB VRAM**
  - Can fit on a single H100 or multi-GPU setups

Both models are **MXFP4 quantized** out of the box.

## Quick Setup

1. **Install vLLM**  
   vLLM recommends using [uv](https://docs.astral.sh/uv/) to manage your Python environment. This will help with picking the right implementation based on your environment. [Learn more in their quickstart](https://docs.vllm.ai/en/latest/getting_started/quickstart.html#installation). To create a new virtual environment and install vLLM run:

```shell
uv venv --python 3.12 --seed
source .venv/bin/activate
uv pip install --pre vllm==0.10.1+gptoss \
    --extra-index-url https://wheels.vllm.ai/gpt-oss/ \
    --extra-index-url https://download.pytorch.org/whl/nightly/cu128 \
    --index-strategy unsafe-best-match
```

2. **Start up a server and download the model**  
   vLLM provides a `serve` command that will automatically download the model from HuggingFace and spin up an OpenAI-compatible server on `localhost:8000`. Run the following command depending on your desired model size in a terminal session on your server.

```shell
# For 20B
vllm serve openai/gpt-oss-20b

# For 120B
vllm serve openai/gpt-oss-120b
```

## Use the API

vLLM exposes a **Chat Completions-compatible API** and a **Responses-compatible API** so you can use the OpenAI SDK without changing much. Here’s a Python example:

```py
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="EMPTY"
)

result = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain what MXFP4 quantization is."}
    ]
)

print(result.choices[0].message.content)

response = client.responses.create(
    model="openai/gpt-oss-120b",
    instructions="You are a helfpul assistant.",
    input="Explain what MXFP4 quantization is."
)

print(response.output_text)
```

If you’ve used the OpenAI SDK before, this will feel instantly familiar and your existing code should work by changing the base URL.

## Using tools (function calling)

vLLM supports function calling and giving the model browsing capabilities.

Function calling works through both the Responses and Chat Completions APIs.

Example of invoking a function via Chat Completions:

```py
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather in a given city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"]
            },
        },
    }
]

response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[{"role": "user", "content": "What's the weather in Berlin right now?"}],
    tools=tools
)

print(response.choices[0].message)
```

Since the models can perform tool calling as part of the chain-of-thought (CoT) it’s important for you to return the reasoning returned by the API back into a subsequent call to a tool call where you provide the answer until the model reaches a final answer.

## Agents SDK Integration

Want to use gpt-oss with OpenAI’s **Agents SDK**?

Both Agents SDK enable you to override the OpenAI base client to point to vLLM for your self-hosted models. Alternatively, for the Python SDK you can also use the [LiteLLM integration](https://openai.github.io/openai-agents-python/models/litellm/) to proxy to vLLM.

Here’s a Python Agents SDK example:

```
uv pip install openai-agents
```

```py
import asyncio
from openai import AsyncOpenAI
from agents import Agent, Runner, function_tool, OpenAIResponsesModel, set_tracing_disabled

set_tracing_disabled(True)

@function_tool
def get_weather(city: str):
    print(f"[debug] getting weather for {city}")
    return f"The weather in {city} is sunny."


async def main(model: str, api_key: str):
    agent = Agent(
        name="Assistant",
        instructions="You only respond in haikus.",
        model=OpenAIResponsesModel(
            model="openai/gpt-oss-120b",
            openai_client=AsyncOpenAI(
                base_url="http://localhost:8000/v1",
                api_key="EMPTY",
            ),
        )
        tools=[get_weather],
    )

    result = await Runner.run(agent, "What's the weather in Tokyo?")
    print(result.final_output)

if __name__ == "__main__":
    asyncio.run(main())
```

## Using vLLM for direct sampling

Aside from running vLLM using `vllm serve` as an API server, you can use the vLLM Python library to control inference directly.

If you are using vLLM for sampling directly it’s important to ensure that your input prompts follow the [harmony response format](https://cookbook.openai.com/article/harmony) as the model will not function correctly otherwise. You can use the [`openai-harmony` SDK](https://github.com/openai/harmony) for this.

```
uv pip install openai-harmony
```

Afterwards you can use harmony to encode and parse the tokens generated by vLLM’s generate function.

```py
import json
from openai_harmony import (
    HarmonyEncodingName,
    load_harmony_encoding,
    Conversation,
    Message,
    Role,
    SystemContent,
    DeveloperContent,
)

from vllm import LLM, SamplingParams

# --- 1) Render the prefill with Harmony ---
encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)

convo = Conversation.from_messages(
    [
        Message.from_role_and_content(Role.SYSTEM, SystemContent.new()),
        Message.from_role_and_content(
            Role.DEVELOPER,
            DeveloperContent.new().with_instructions("Always respond in riddles"),
        ),
        Message.from_role_and_content(Role.USER, "What is the weather like in SF?"),
    ]
)

prefill_ids = encoding.render_conversation_for_completion(convo, Role.ASSISTANT)

# Harmony stop tokens (pass to sampler so they won't be included in output)
stop_token_ids = encoding.stop_tokens_for_assistant_actions()

# --- 2) Run vLLM with prefill ---
llm = LLM(
    model="openai/gpt-oss-120b",
    trust_remote_code=True,
)

sampling = SamplingParams(
    max_tokens=128,
    temperature=1,
    stop_token_ids=stop_token_ids,
)

outputs = llm.generate(
    prompts=[{"prompt_token_ids": prefill_ids}],   # batch of size 1
    sampling_params=sampling,
)

# vLLM gives you both text and token IDs
gen = outputs[0].outputs[0]
text = gen.text
output_tokens = gen.token_ids  # <-- these are the completion token IDs (no prefill)

# --- 3) Parse the completion token IDs back into structured Harmony messages ---
entries = encoding.parse_messages_from_completion_tokens(output_tokens, Role.ASSISTANT)

# 'entries' is a sequence of structured conversation entries (assistant messages, tool calls, etc.).
for message in entries:
    print(f"{json.dumps(message.to_dict())}")
```
