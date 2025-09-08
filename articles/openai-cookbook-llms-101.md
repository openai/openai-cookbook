Introduction

The OpenAI Cookbook is a code‑first guide to building reliable, production‑grade AI features—fast. It focuses on the patterns, snippets, and guardrails that matter when you ship, with clear paths from “hello world” to evals, retrieval, agents, and deployment.

What’s new right now
	•	GPT‑5 is our most advanced model to date (launched August 7, 2025). It pairs a fast “default” model with a deeper reasoning model and a real‑time router that decides when to “think harder,” plus new developer controls for steerability. If you used GPT‑4‑class models, expect better tool use, longer chains of actions, and crisper instruction‑following.  ￼
	•	Open models (gpt‑oss): we now offer open‑weight, Apache‑2.0‑licensed models—gpt‑oss‑120b and gpt‑oss‑20b—that deliver strong reasoning and tool‑use performance and are optimized for efficient self‑hosting. Use them when you need full control over runtime, cost, or data locality.  ￼ ￼
	•	Smaller, fast reasoning: o4‑mini (April 16, 2025) is a cost‑efficient model with standout math/coding performance and excellent results when paired with a Python tool—useful for latency‑sensitive backends.  ￼
	•	Agents & search with citations: the API includes tooling for multi‑step agents and optional web search that returns inline source links—helpful for grounded answers and UX transparency.  ￼
	•	Safety in open models: our open‑weight releases undergo safety training and evaluation; the Open Models overview explains the approach and expectations.  ￼

Who this is for

Developers who want a practical, working understanding of LLMs and the knobs that actually move quality, latency, and cost in real apps. This introduction builds on our “LLMs 101: A Practical Introduction” primer for core concepts like tokenization, decoding, and sampling.  ￼

How to use this Cookbook
	•	Start with quickstarts for generation, structured outputs (JSON), streaming, and tool calling.
	•	Ground models with your data (RAG) and add evals before you promote prompts or retrievers.
	•	Scale with agents only where they beat simpler request‑response patterns; measure with scenario‑based evals.
	•	Ship safely: validate outputs, handle PII appropriately, and prefer designs that degrade gracefully.

Picking a model (at a glance)
	•	Highest quality & capability → GPT‑5 for complex reasoning, long tool chains, and highly steerable UX. See the Cookbook’s GPT‑5 prompting and new parameters guides for hands‑on patterns.  ￼
	•	Open‑weight / self‑hosted → gpt‑oss‑120b/20b when you need full control, custom fine‑tuning, or on‑prem deployment with strong reasoning.  ￼ ￼
	•	Throughput & cost → o4‑mini for fast, high‑accuracy tasks (especially math/coding), optionally with a Python tool.  ￼

Conventions you’ll see throughout
	•	Prefer streaming for chat‑like UIs and long generations.
	•	Ask for structured outputs (and validate) when machines will read the result.
	•	Keep a small, real‑world eval set and re‑score whenever you change models, prompts, or retrieval.
	•	Model names and parameters evolve; consult your Models list in the dashboard before shipping.

Responsible use

Model quality and capability come with responsibilities. For GPT‑5, review the System Card for how we route, evaluate, and mitigate risks across tasks. For open‑weight models, follow the published safety guidance and eval your end‑to‑end system (not just the base model).  ￼

Ready to build: jump to the quickstarts, then layer in retrieval and evals. When you need the latest prompting patterns for GPT‑5—or recipes for running gpt‑oss—this Cookbook has you covered.
