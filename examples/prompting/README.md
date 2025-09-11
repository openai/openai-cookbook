Prompting Examples (LLMs)

This folder gathers all prompting-related examples in one place so you can learn, compare, and reuse patterns quickly. It ranges from fundamentals (input formatting, caching) to advanced techniques (meta-prompting, guardrails, evaluation with a judge model), plus model-specific guides and applied recipes.

⸻

Quick start
	1.	From repo root, install deps and set credentials as described in the main Cookbook README.
	2.	Open any notebook in Jupyter / VS Code.
	3.	If a notebook references a model you don’t have access to, swap in a compatible one (e.g., replace gpt-5 with gpt-4o, or o4-mini with gpt-4o-mini).
	4.	For consistent comparisons, keep temperature low (e.g., 0–0.3) and set any random seed where applicable.

⸻

What’s inside

Foundations & Building Blocks
	•	How_to_format_inputs_to_ChatGPT_models.ipynb
Practical patterns for structuring inputs (system/user messages, delimiters, schemas) to reduce ambiguity and boost reliability.
	•	Prompt_Caching101.ipynb
Shows how and when to cache stable prompt segments to reduce cost/latency on repeated operations.
	•	prompt-engineering.txt
Concise notes/checklist of core prompting heuristics.
	•	prompts/ (directory)
Reusable prompt templates/snippets you can copy into your own projects.

Prompt Optimization & Patterns
	•	Optimize_Prompts.ipynb
Step-by-step refinements from vague → specific → structured; includes measurable checkpoints (accuracy, determinism, length).
	•	Enhance_your_prompts_with_meta_prompting.ipynb
“Prompt the prompter”: use meta-instructions and self-review to systematically improve outputs.
	•	prompt-optimization-cookbook.ipynb
A recipe-style tour of optimization tactics (role specification, constraints, formatting contracts, failure-mode nudges).
	•	prompt-optimization-cookbook/ (directory)
Companion assets and extended recipes referenced by the notebook.

Guardrails, Evaluation & QA
	•	Developing_hallucination_guardrails.ipynb
Patterns to reduce unsupported claims: retrieval checks, cite-or-abstain, schema-validation, and refusal scaffolds.
	•	Custom-LLM-as-a-Judge.ipynb
Use an independent “judge” model to evaluate task outputs (rubrics, pairwise comparisons, error taxonomies).

Model-Specific Prompting Guides
	•	gpt-5_prompting_guide.ipynb
Guidance for newest-gen models: leveraging extended context/tools while keeping prompts lean and structured. (Swap to your available model if needed.)
	•	gpt4-1_prompting_guide.ipynb
Tips tailored to the 4.1 series: instruction clarity, tool-use hooks, JSON contracts.
	•	o3o4-mini_prompting_guide.ipynb
Best practices for smaller/efficient models: tighter constraints, shorter exemplars, robust formatting to offset capacity limits.
	•	Realtime_prompting_guide.ipynb
Streaming + low-latency interaction patterns (turn-taking prompts, incremental planning, partial results).
	•	Whisper_prompting_guide.ipynb
Using prompts to bias/condition speech-to-text (domain terms, speaker/style context, punctuation/number handling).
	•	Prompt_migration_guide.ipynb
How to port prompts across model/API versions while preserving behavior (capabilities, defaults, temperature/top-p changes).

Applied Examples
	•	Unit_test_writing_using_a_multi-step_prompt.ipynb
Multi-step prompting to draft and refine unit tests from natural-language specs with verification passes.
	•	Unit_test_writing_using_a_multi-step_prompt_with_older_completions_API.ipynb
Historical version of the above using the legacy Completions API for comparison/reference.

⸻

Suggested learning paths

New to prompting?
	1.	How_to_format_inputs… → 2) Optimize_Prompts → 3) Enhance_your_prompts_with_meta_prompting → 4) Prompt_Caching101

Shipping something production-ish
	1.	Developing_hallucination_guardrails → 2) Custom-LLM-as-a-Judge → 3) prompt-optimization-cookbook.ipynb → 4) your model-specific guide

Speech / real-time track
	1.	Whisper_prompting_guide → 2) Realtime_prompting_guide

Legacy → modern migration
	1.	Unit_test… (older completions) → 2) Unit_test… (multi-step) → 3) Prompt_migration_guide

⸻

Conventions for this folder
	•	File naming: use snake_case and end with _guide.ipynb or a clear verb phrase (e.g., optimize_prompts.ipynb).
	•	Comparisons: when demonstrating “bad vs. good,” keep identical tasks & evaluation across cells; only change the prompt.
	•	Determinism: set low temperature and, where relevant, seeds to keep diffs meaningful.
	•	Outputs: prefer structured outputs (JSON/Markdown tables) to ease automated checking.
	•	Safety: when showing failure modes (e.g., hallucinations), add a final cell with a fix pattern (cite-or-abstain, schema checks, etc.).

⸻

Contributing
	•	Add a short intro cell explaining the goal and what success looks like.
	•	Include at least one automatable check (regex/schema/assert) to make improvements measurable.
	•	If your example targets a specific model family, call it out up front and suggest fallback models.
	•	Keep any shared assets in this folder (or its subfolders) and use relative paths.

⸻

Notes
	•	Model names evolve. If a referenced model isn’t available in your account/region, substitute the closest family (e.g., gpt-4o / gpt-4o-mini).
	•	Some notebooks intentionally show anti-patterns for teaching—read the headers to avoid copying them into production.

If you spot missing patterns (retrieval-augmented prompts, evaluation rubrics for specific domains, code-gen chains, etc.), feel free to open a PR adding a focused notebook here.
