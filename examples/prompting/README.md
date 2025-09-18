# Prompting: Guides & Examples

This directory consolidates prompting-related guides, examples, and reusable prompt assets from across the Cookbook. It’s a single place to learn core prompting patterns, optimize prompts, and discover application-specific prompt sets.

## Why this exists
Effective prompting solves a large share of practical model issues. The right prompt is as important as parameters like `temperature` or `reasoning_effort`. Centralizing examples and references makes them easier to find, reuse, and maintain.

## Start here (recommended path)
1. **GPT-4.1 Prompting Guide** → techniques, structure, and patterns:  
   [`gpt4-1_prompting_guide.ipynb`](./gpt4-1_prompting_guide.ipynb)
2. **Prompt engineering best practices** (reference):  
   <https://platform.openai.com/docs/guides/prompt-engineering>
3. **Orchestrating agents & handoffs** (for multi-agent apps):  
   `../orchestrating_agents` (see the top-level Examples index)
4. **Structured outputs** (JSON schemas, validation):  
   `../structured_outputs_multi_agent`

> Tip: Keep prompts short, specific, and testable. Add minimal examples, define outputs precisely, and prefer explicit instructions over implications.

## Contents

### Core Guides
- **GPT-4.1 Prompting Guide** — system prompts, tool use, decomposition, evaluation  
  [`gpt4-1_prompting_guide.ipynb`](./gpt4-1_prompting_guide.ipynb)
- **Realtime prompting guide** — working with the Realtime API  
  [`Realtime_prompting_guide.ipynb`](./Realtime_prompting_guide.ipynb)
- **Whisper prompting guide** — task hints and formatting for speech recognition  
  [`Whisper_prompting_guide.ipynb`](./Whisper_prompting_guide.ipynb)

### Prompt Optimization
- **Optimize Prompts** — automated checks & fixes for common prompt issues  
  [`Optimize_Prompts.ipynb`](./Optimize_Prompts.ipynb)
- **Enhance your prompts with meta-prompting** — programmatic refinement strategies  
  [`Enhance_your_prompts_with_meta_prompting.ipynb`](./Enhance_your_prompts_with_meta_prompting.ipynb)
- **Prompt migration guide** — safely updating existing prompts across changes  
  [`Prompt_migration_guide.ipynb`](./Prompt_migration_guide.ipynb)

### Agent & App Prompts
- **Multi-agent portfolio collaboration prompts** — reusable prompt set for agent roles  
  [`../agents_sdk/multi-agent-portfolio-collaboration/prompts/`](../agents_sdk/multi-agent-portfolio-collaboration/prompts/)

### Supporting Resources
- OpenAI Prompt Engineering (plain-text reference)  
  [`../data/oai_docs/prompt-engineering.txt`](../data/oai_docs/prompt-engineering.txt)

## Usage pattern

1. **Draft** a minimal instruction with explicit output shape (e.g., JSON schema).
2. **Ground** with constraints (tone, audience, knowledge limits) and a tiny example if needed.
3. **Test** with real inputs; watch for ambiguity and output drift.
4. **Evaluate** with checks (format validation, assertions).
5. **Iterate**: shorten, remove redundant rules, and pin “must-haves”.

## Contributing

- Keep notebooks **runnable end-to-end** (no hidden cell state).
- Prefer **relative links** within `examples/`, so both GitHub and the site render cleanly.
- When adding new files here, **update** `registry.yaml` so content appears on the site.
- If you introduce a new subfolder of prompts, include a short `README.md` explaining scope and usage.
