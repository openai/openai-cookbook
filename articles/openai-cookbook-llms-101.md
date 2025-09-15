---
title: "LLMs 101: A Practical Introduction"
description: "A hands-on, code-first introduction to large language models for Cookbook readers."
last_updated: "2025-08-24"
---

# LLMs 101: A Practical Introduction

> **Who this is for.** Developers who want a fast, working understanding of large language models and the knobs that matter in real apps.

## At a glance

```
Text prompt
   ↓  (tokenization)
Tokens → Embeddings → [Transformer layers × N] → Next‑token probabilities
   ↓                       ↓
Detokenization         Sampling (temperature/top_p) → Output text
```

- **LLMs** are neural networks (usually **transformers**) trained on lots of text to predict the next token.  
- **Tokenization** splits text into subword units; **embeddings** map tokens to vectors; transformer layers build context‑aware representations.  
- Generation repeats next‑token sampling until a stop condition (length or stop sequences) is met.

---

## Quick start: generate text

### Python

```python
from openai import OpenAI

client = OpenAI()
resp = client.responses.create(
    model="gpt-4o",
    instructions="You are a concise technical explainer.",
    input="In one paragraph, explain what a token is in an LLM."
)
print(resp.output_text)
```

### JavaScript / TypeScript

```js
import OpenAI from "openai";
const client = new OpenAI();

const resp = await client.responses.create({
  model: "gpt-4o",
  instructions: "You are a concise technical explainer.",
  input: "In one paragraph, explain what a token is in an LLM."
});
console.log(resp.output_text);
```

> **Tip.** Model names evolve; check your Models list before shipping. Prefer streaming for chat‑like UIs (see below).

---

## What can LLMs do?

Despite the name, LLMs can be **multi‑modal** when models and inputs support it (text, code, sometimes images/audio). Core text tasks:

- **Generate**: draft, rewrite, continue, or brainstorm.  
- **Transform**: translate, rephrase, format, classify, extract.  
- **Analyze**: summarize, compare, tag, or answer questions.  
- **Tool use / agents**: call functions or APIs as part of a loop to act.

These patterns compose into search, assistants, form‑fillers, data extraction, QA, and more.

---

## How LLMs work (just enough to be dangerous)

1. **Tokenization.** Input text → tokens (IDs). Whitespace and punctuation matter—“token‑budget math” is a real constraint.  
2. **Embeddings.** Each token ID becomes a vector; positions are encoded so order matters.  
3. **Transformer layers.** Self‑attention mixes information across positions so each token’s representation becomes **contextual** (richer than the raw embedding).  
4. **Decoding.** The model outputs a probability distribution over the next token.  
5. **Sampling.** Choose how “adventurous” generation is (see knobs below), append the token, and repeat until done.

---

## The knobs you’ll touch most

- **Temperature** *(0.0–2.0)* — Lower → more deterministic/boring; higher → more diverse/creative.  
- **Top‑p (nucleus)** *(0–1)* — Sample only from the smallest set of tokens whose cumulative probability ≤ *p*.  
- **Max output tokens** — Hard limit on output length; controls latency and cost.  
- **System / instructions** — Up‑front role, constraints, and style to steer behavior.  
- **Stop sequences** — Cleanly cut off output at known boundaries.  
- **Streaming** — Receive tokens as they’re generated; improves perceived latency.

**Practical defaults:** `temperature=0.2–0.7`, `top_p=1.0`, set a **max output** that fits your UI, and **stream** by default for chat UX.

---

## Make context do the heavy lifting

- **Context window.** Inputs + outputs share a finite token budget; plan prompts and retrieval to fit.  
- **Ground with your data (RAG).** Retrieve relevant snippets and include them in the prompt to improve factuality.  
- **Structured outputs.** Ask for JSON (and validate) when you need machine‑readable results.  
- **Few‑shot examples.** Provide 1–3 compact exemplars to stabilize format and tone.

---

## Minimal streaming example

### Python

```python
from openai import OpenAI
client = OpenAI()

with client.responses.stream(
    model="gpt-4o",
    input="Stream a two-sentence explanation of context windows."
) as stream:
    for event in stream:
        if event.type == "response.output_text.delta":
            print(event.delta, end="")
```

### JavaScript

```js
import OpenAI from "openai";
const client = new OpenAI();

const stream = await client.responses.stream({
  model: "gpt-4o",
  input: "Stream a two-sentence explanation of context windows."
});

for await (const event of stream) {
  if (event.type === "response.output_text.delta") {
    process.stdout.write(event.delta);
  }
}
```

---

## Limitations (design around these)

- **Hallucinations.** Models can generate plausible but false statements. Ground with citations/RAG; validate critical outputs.  
- **Recency.** Models don’t inherently know the latest facts; retrieve or provide current data.  
- **Ambiguity.** Vague prompts → vague answers; specify domain, audience, length, and format.  
- **Determinism.** Even at `temperature=0`, responses may vary across runs/envs. Don’t promise bit‑for‑bit reproducibility.  
- **Cost & latency.** Longer prompts and bigger models are slower and costlier; iterate toward the smallest model that meets quality.

---

## Common gotchas

- **Characters ≠ tokens.** Budget both input and output to avoid truncation.  
- **Over‑prompting.** Prefer simple, testable instructions; add examples sparingly.  
- **Leaky formats.** If you need JSON, enforce it (schema + validators) and add a repair step.  
- **One prompt for everything.** Separate prompts per task/endpoint; keep them versioned and testable.  
- **Skipping evaluation.** Keep a tiny dataset of real tasks; score changes whenever you tweak prompts, models, or retrieval.

---

## Glossary

- **Token** — Small unit of text (≈ subword) used by models.  
- **Embedding** — Vector representation of a token or text span.  
- **Context window** — Max tokens the model can attend to at once (prompt + output).  
- **Temperature / top‑p** — Randomness controls during sampling.  
- **System / instructions** — Up‑front guidance that shapes responses.  
- **RAG** — Retrieval‑Augmented Generation; retrieve data and include it in the prompt.

---

## Where to go next

- Prompt patterns for **structured outputs**  
- **Retrieval‑augmented generation (RAG)** basics  
- **Evaluating** LLM quality (offline + online)  
- **Streaming UX** patterns and backpressure handling  
- **Safety** and policy‑aware prompting

> Adapted from a shorter draft and expanded with code-first guidance.
