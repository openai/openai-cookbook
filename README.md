# OpenAI Cookbook

## What is the OpenAI Cookbook?

The OpenAI Cookbook is a community-driven collection of examples and guides for building with OpenAI's API. Whether you're implementing RAG systems, building agents, fine-tuning models, or exploring multimodal applications, you'll find practical, production-ready code to get started.

This resource is designed for developers, researchers, and anyone looking to understand how to leverage modern language models in real-world applications.

## OpenAI API Overview

OpenAI's platform provides powerful tools for building AI applications:

- **Language Models**: `gpt-4o` and `gpt-4o-mini` deliver strong performance across reasoning, coding, and creative tasks
- **Multimodal Capabilities**: Process and generate text, images, and audio in unified workflows
- **Responses API**: Simplified, stateful API for multi-turn conversations with built-in tool orchestration
- **Function Calling**: Connect models to external tools, APIs, and databases
- **Structured Outputs**: Generate guaranteed JSON responses using `response_format`
- **Embeddings**: Build semantic search and RAG systems with `text-embedding-3-small` and `text-embedding-3-large`
- **Image Generation**: Create images with the DALL-E API
- **Voice & Audio**: Real-time audio processing with `gpt-4o-audio-preview` and the Realtime API

## Getting Started

### 1. Create an OpenAI Account

Sign up at [platform.openai.com/signup](https://platform.openai.com/signup) to get API access. Free-tier accounts can explore the API with usage limits.

### 2. Get Your API Key

Navigate to [platform.openai.com/api-keys](https://platform.openai.com/api-keys) and create a new API key. Keep it secure—treat it like a password.

### 3. Set Up Your Environment

**Option A: Environment Variable**

```bash
# macOS/Linux
export OPENAI_API_KEY='your-api-key-here'

# Windows (Command Prompt)
set OPENAI_API_KEY=your-api-key-here

# Windows (PowerShell)
$env:OPENAI_API_KEY='your-api-key-here'
```

**Option B: .env File (Recommended)**

Create a `.env` file in your project root:

```
OPENAI_API_KEY=your-api-key-here
```

Most notebooks and Python applications will automatically load this file.

### 4. Install the SDK

```bash
# Python
pip install openai

# Node.js
npm install openai
```

### 5. Run the Examples

Most examples are Jupyter notebooks. Install Jupyter if you haven't already:

```bash
pip install jupyter
jupyter notebook
```

Then open any `.ipynb` file from the `examples/` directory and run the cells.

## What's in the Cookbook

The cookbook is organized into focused examples covering common use cases:

- **[Function Calling](examples/function_calling/)**: Connect models to external tools, APIs, and databases
- **[Embeddings & RAG](examples/rag/)**: Build retrieval-augmented generation systems over your own data
- **[Agents](examples/agents/)**: Create autonomous agents that plan, reason, and execute tasks
- **[Vision](examples/vision/)**: Work with image inputs for analysis and understanding
- **[Audio](examples/audio/)**: Build applications for transcription, speech recognition, and audio processing
- **[Image Generation](examples/image_generation/)**: Create images using the DALL·E API
- **[Structured Outputs](examples/structured_outputs/)**: Produce guaranteed JSON using `response_format`
- **[Batch Processing](examples/batch/)**: Run large-scale inference jobs efficiently
- **[Prompt Engineering](examples/prompt_engineering/)**: Learn effective prompt design techniques
- **[Evaluation & Reasoning](examples/reasoning/)**: Evaluate model performance and test reasoning quality
- **[Data ETL](examples/data_etl/)**: Prepare and transform data for downstream tasks
- **[Python Examples](examples/python/)**: How to use the Python SDK in real applications
- **[JavaScript Examples](examples/javascript/)**: Examples demonstrating the Node.js SDK
- **[Assistants](examples/assistants/)**: Build assistants with persistent threads and tool use

Browse the full collection at [cookbook.openai.com](https://cookbook.openai.com) or explore the [examples directory](examples/) directly.

## Resources

- **[OpenAI Platform Documentation](https://platform.openai.com/docs)**: Official API reference and guides
- **[OpenAI API Reference](https://platform.openai.com/docs/api-reference)**: Complete endpoint documentation
- **[Community Forum](https://community.openai.com)**: Get help and share what you're building
- **[Related Resources](https://cookbook.openai.com/related_resources)**: Curated tools, guides, and courses from the community

## Contributing

We welcome contributions! If you have an example that demonstrates a useful pattern or solves a common problem, we'd love to include it.

Check out [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to submit examples.

## License

MIT License
