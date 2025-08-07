# How to run gpt-oss locally with LM Studio

[LM Studio](https://lmstudio.ai) is a performant and friendly desktop application for running large language models (LLMs) on local hardware. This guide will walk you through how to set up and run **gpt-oss-20b** or **gpt-oss-120b** models using LM Studio, including how to chat with them, use MCP servers, or interact with the models through LM Studio's local development API.

Note that this guide is meant for consumer hardware, like running gpt-oss on a PC or Mac. For server applications with dedicated GPUs like NVIDIA's H100s, [check out our vLLM guide](https://cookbook.openai.com/articles/gpt-oss/run-vllm).

## Pick your model

LM Studio supports both model sizes of gpt-oss:

- [**`openai/gpt-oss-20b`**](https://lmstudio.ai/models/openai/gpt-oss-20b)
  - The smaller model
  - Only requires at least **16GB of VRAM**
  - Perfect for higher-end consumer GPUs or Apple Silicon Macs
- [**`openai/gpt-oss-120b`**](https://lmstudio.ai/models/openai/gpt-oss-120b)
  - Our larger full-sized model
  - Best with **≥60GB VRAM**
  - Ideal for multi-GPU or beefy workstation setup

LM Studio ships both a [llama.cpp](https://github.com/ggml-org/llama.cpp) inferencing engine (running GGUF formatted models), as well as an [Apple MLX](https://github.com/ml-explore/mlx) engine for Apple Silicon Macs. 

## Quick setup

1. **Install LM Studio**
   LM Studio is available for Windows, macOS, and Linux. [Get it here](https://lmstudio.ai/download).

2. **Download the gpt-oss model** → 

```shell
# For 20B
lms get openai/gpt-oss-20b
# or for 120B
lms get openai/gpt-oss-120b
``` 

3. **Load the model in LM Studio** 
  → Open LM Studio and use the model loading interface to load the gpt-oss model you downloaded. Alternatively, you can use the command line:

```shell
# For 20B
lms load openai/gpt-oss-20b
# or for 120B
lms load openai/gpt-oss-120b
```

4. **Use the model** → Once loaded, you can interact with the model directly in LM Studio's chat interface or through the API.

## Chat with gpt-oss

Use LM Studio's chat interface to start a conversation with gpt-oss, or use the `chat` command in the terminal:

```shell
lms chat openai/gpt-oss-20b
```

Note about prompt formatting: LM Studio utilizes OpenAI's [Harmony](https://cookbook.openai.com/articles/openai-harmony) library to construct the input to gpt-oss models, both when running via llama.cpp and MLX.

## Use gpt-oss with a local /v1/chat/completions endpoint

LM Studio exposes a **Chat Completions-compatible API** so you can use the OpenAI SDK without changing much. Here’s a Python example:

```py
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="not-needed"  # LM Studio does not require an API key
)

result = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain what MXFP4 quantization is."}
    ]
)

print(result.choices[0].message.content)
```

If you’ve used the OpenAI SDK before, this will feel instantly familiar and your existing code should work by changing the base URL.

## How to use MCPs in the chat UI

LM Studio is an [MCP client](https://lmstudio.ai/docs/app/plugins/mcp), which means you can connect MCP servers to it. This allows you to provide external tools to gpt-oss models.

LM Studio's mcp.json file is located in:

```shell
~/.lmstudio/mcp.json
```

## Local tool use with gpt-oss in Python or TypeScript

LM Studio's SDK is available in both [Python](https://github.com/lmstudio-ai/lmstudio-python) and [TypeScript](https://github.com/lmstudio-ai/lmstudio-js). You can leverage the SDK to implement tool calling and local function execution with gpt-oss.

The way to achieve this is via the `.act()` call, which allows you to provide tools to the gpt-oss and have it go between calling tools and reasoning, until it completes your task.

The example below shows how to provide a single tool to the model that is able to create files on your local filesystem. You can use this example as a starting point, and extend it with more tools. See docs about tool definitions here for [Python](https://lmstudio.ai/docs/python/agent/tools) and [TypeScript](https://lmstudio.ai/docs/typescript/agent/tools).

```shell
uv pip install lmstudio
```

```python
import readline # Enables input line editing
from pathlib import Path

import lmstudio as lms

# Define a function that can be called by the model and provide them as tools to the model.
# Tools are just regular Python functions. They can be anything at all.
def create_file(name: str, content: str):
    """Create a file with the given name and content."""
    dest_path = Path(name)
    if dest_path.exists():
        return "Error: File already exists."
    try:
        dest_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        return "Error: {exc!r}"
    return "File created."

def print_fragment(fragment, round_index=0):
    # .act() supplies the round index as the second parameter
    # Setting a default value means the callback is also
    # compatible with .complete() and .respond().
    print(fragment.content, end="", flush=True)

model = lms.llm("openai/gpt-oss-20b")
chat = lms.Chat("You are a helpful assistant running on the user's computer.")

while True:
    try:
        user_input = input("User (leave blank to exit): ")
    except EOFError:
        print()
        break
    if not user_input:
        break
    chat.add_user_message(user_input)
    print("Assistant: ", end="", flush=True)
    model.act(
        chat,
        [create_file],
        on_message=chat.append,
        on_prediction_fragment=print_fragment,
    )
    print()

```

For TypeScript developers who want to utilize gpt-oss locally, here's a similar example using `lmstudio-js`:

```shell
npm install @lmstudio/sdk
```

```typescript
import { Chat, LMStudioClient, tool } from "@lmstudio/sdk";
import { existsSync } from "fs";
import { writeFile } from "fs/promises";
import { createInterface } from "readline/promises";
import { z } from "zod";

const rl = createInterface({ input: process.stdin, output: process.stdout });
const client = new LMStudioClient();
const model = await client.llm.model("openai/gpt-oss-20b");
const chat = Chat.empty();

const createFileTool = tool({
  name: "createFile",
  description: "Create a file with the given name and content.",
  parameters: { name: z.string(), content: z.string() },
  implementation: async ({ name, content }) => {
    if (existsSync(name)) {
      return "Error: File already exists.";
    }
    await writeFile(name, content, "utf-8");
    return "File created.";
  },
});

while (true) {
  const input = await rl.question("User: ");
  // Append the user input to the chat
  chat.append("user", input);

  process.stdout.write("Assistant: ");
  await model.act(chat, [createFileTool], {
    // When the model finish the entire message, push it to the chat
    onMessage: (message) => chat.append(message),
    onPredictionFragment: ({ content }) => {
      process.stdout.write(content);
    },
  });
  process.stdout.write("\n");
}
```