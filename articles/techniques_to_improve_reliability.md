# Techniques to improve reliability

When a model gives an unreliable answer, do not jump straight to "the model cannot do this" or "we need fine-tuning." First ask a narrower question: what part of the task was underspecified, unsupported, too complex, or unchecked?

Most reliability work is not one magic prompt. It is the process of turning a single model call into a small, testable system with clear instructions, relevant context, constrained outputs, and verification.

## Why models can be unreliable

Large language models generate output one token at a time from the context they are given. They are powerful pattern matchers and reasoners, but their default behavior is still probabilistic generation, not guaranteed truth.

That creates a few predictable failure modes:

- **Missing context.** If the prompt does not include the needed facts, the model may fill gaps with a plausible answer.
- **Ambiguous instructions.** If several interpretations fit the request, the model may choose a reasonable one that is not the one you intended.
- **Long reasoning chains.** Multi-step tasks compound error. Even if each step is likely to be correct, a long sequence has more chances to go wrong. A ten-step process where each step is 95% reliable is only about 60% reliable end to end.
- **Weak constraints.** Free-form text gives the model room to drift, omit required fields, or mix answer formats.
- **Sampling variation.** Temperature, tie-breaking, and small context changes can produce different outputs.
- **World knowledge limits.** A model is not a live database. It may not know private, recent, or domain-specific facts unless you provide them through context or tools.

Lowering temperature can reduce variation, but it does not solve missing context, ambiguous goals, or faulty reasoning. Asking for an explanation can help on reasoning tasks, but an explanation is not proof. For production systems, reliability comes from design and evaluation.

## A practical reliability loop

Use this loop before reaching for heavier solutions:

1. **Define success.** Write down the exact output shape, acceptable uncertainty, and failure cases.
2. **Create a small eval set.** Include easy, hard, ambiguous, adversarial, and real failed examples.
3. **Start simple.** Use a capable model, a clear prompt, and representative examples.
4. **Inspect failures.** Identify whether each miss is caused by missing context, unclear instructions, invalid structure, reasoning depth, or external knowledge.
5. **Add the smallest control that targets the failure.** Use structured outputs, retrieval, tools, decomposition, examples, or verification as needed.
6. **Run the eval again.** Keep changes that improve the target metric without creating regressions.

## Write the task as a specification

A reliable prompt reads more like a compact task spec than a clever phrase. Include:

- The role or task
- The input the model should use
- The output format
- The decision rules
- What to do when information is missing
- A few examples when judgment is subtle

For example:

```text
Classify the support ticket into one of these categories:
Billing, Technical issue, Account access, Other.

Rules:
- Use Other when the ticket does not clearly fit one category.
- If the ticket has multiple issues, choose the category that blocks the user first.
- Return only JSON with keys: category, confidence, rationale.
- Keep rationale under 20 words.

Ticket:
"""
I was charged twice and now I cannot log in to check the invoice.
"""
```

This prompt is more reliable than "Classify this ticket" because it removes hidden choices: the label set, tie-breaking rule, uncertainty behavior, and output shape are explicit.

## Provide the facts the model needs

If the answer depends on private documents, current facts, account state, prices, laws, policies, or database records, do not rely on the model's memory. Give the model the relevant context or a tool that can fetch it.

Common patterns:

- Use retrieval or file search for private or long documents.
- Use web search or a trusted API for current facts.
- Use database queries for account-specific state.
- Ask the model to cite the source span or record ID it used.
- Tell the model to say when the provided context is insufficient.

Fine-tuning is usually not the right way to add changing facts. Fine-tuning changes behavior; retrieval supplies knowledge.

## Split complex tasks into smaller steps

Models are more reliable when each step has a clear local objective. Instead of asking for a final answer from a large mixed task, split the work into smaller operations:

- Extract relevant facts.
- Identify constraints.
- Resolve conflicts or missing information.
- Compute or compare.
- Produce the final answer in the required format.

For example, a legal, policy, or troubleshooting assistant might use this sequence:

1. Retrieve candidate source passages.
2. Extract the passages that directly apply.
3. Decide whether the question is answerable from those passages.
4. Draft the answer with citations.
5. Run a verifier that checks whether every claim is supported.

This works because each step narrows the model's job. It also gives you intermediate artifacts to test, log, and debug.

## Ask for useful intermediate work

For reasoning-heavy tasks, give the model room to work, but ask for intermediate artifacts that are useful to your application:

- A checklist of criteria and whether each one is met
- A table of evidence and source references
- A list of assumptions
- A calculation with named inputs and outputs
- A short rationale for the final decision

Avoid depending on long hidden reasoning transcripts as the product output. A concise rationale, evidence table, or trace of tool calls is easier to verify and easier for users to trust.

## Constrain the output

If another program will consume the answer, do not rely on prose conventions. Use Structured Outputs or a schema so the model must return fields your code can validate.

Good candidates for structured outputs:

- Classification labels
- Extracted entities
- Routing decisions
- Tool arguments
- Evaluation results
- Summaries with required sections

Constraints are especially useful when the valid answer space is small. An enum is easier to verify than a paragraph. A schema is easier to test than "return JSON if possible."

## Use tools for deterministic work

Language models are not calculators, databases, browsers, or permission systems. When correctness depends on an external operation, let the model call a tool and let the tool do the deterministic part.

Use tools for:

- Arithmetic, code execution, and data analysis
- Search and retrieval
- Looking up customer, order, or inventory records
- Creating, updating, or deleting records
- Calling business logic that already exists in your application

Keep tool permissions narrow. A model should only have access to the actions and data needed for the current task.

## Generate, then verify

Sometimes the cheapest reliability gain is to separate generation from checking.

Useful patterns:

- **Self-consistency:** sample several answers and choose the answer that appears most often. This works best when the answer space is limited.
- **Verifier model:** ask a second model call to check whether the answer follows the prompt, uses the provided evidence, and matches the requested format.
- **Code-based checks:** validate JSON schemas, required citations, numeric constraints, policy labels, or exact-match fields with deterministic code.
- **Human review:** route low-confidence or high-impact cases to a person.

Verification costs extra latency and tokens, so reserve it for tasks where the quality gain is worth the cost.

## Tune model settings deliberately

Model choice and decoding settings matter, but they should be tuned against evals rather than guessed.

- Use a stronger model for ambiguous, high-stakes, or multi-step tasks.
- Use smaller models for high-volume tasks after evals show they are good enough.
- Lower temperature when you want less variation.
- Increase reasoning effort only when the task benefits from deeper reasoning.
- Cap output length when concise answers are part of correctness.

Change one variable at a time and measure the result.

## Fine-tune when behavior is the bottleneck

Fine-tuning can improve reliability when you already know the task, have high-quality examples, and can measure success. It is often useful for stable style, domain-specific formatting, classification behavior, or repeated workflows where prompting alone is not enough.

Before fine-tuning, try:

1. Clearer instructions
2. Better examples
3. Structured outputs
4. Retrieval or tools for missing facts
5. A verifier or deterministic validation
6. A representative eval set

Fine-tuning should make a working system better. It should not be the first response to unclear requirements or missing data.

## Common reliability playbook

| Problem | First thing to try |
| --- | --- |
| The model invents facts | Provide retrieval, source passages, or a lookup tool; require citations |
| The answer is plausible but not what you wanted | Rewrite the prompt as a task spec with decision rules and examples |
| JSON is invalid or inconsistent | Use Structured Outputs or stricter schema validation |
| The model misses a step | Split the task into smaller stages with intermediate outputs |
| Math or data analysis is wrong | Use code execution, a calculator, or deterministic business logic |
| Labels drift over time | Add examples, enum constraints, and evals for edge cases |
| Long prompts cause missed details | Retrieve only relevant context or summarize before answering |
| Quality changes after a prompt or model update | Run regression evals before shipping |
| The task is high impact | Add abstention rules, verification, logging, and human review |

## Closing thoughts

The central idea is simple: do not ask one model call to be a complete reliable system by itself. Give the model the right context, narrow the job, constrain the output, use tools for deterministic work, and measure behavior with evals.

Most reliability improvements are not exotic. They are the same engineering habits used everywhere else: specify the contract, reduce ambiguity, isolate failure modes, test representative cases, and add checks where mistakes matter.

## Further reading

- [How to work with large language models](how_to_work_with_large_language_models.md)
- [Prompt engineering guide][Prompt engineering]
- [Structured Outputs guide][Structured outputs]
- [Function calling guide][Function calling]
- [Working with evals][Evals]
- [Supervised fine-tuning guide][Fine-tuning]
- [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models](https://arxiv.org/abs/2201.11903)
- [Large Language Models are Zero-Shot Reasoners](https://arxiv.org/abs/2205.11916)
- [Self-Consistency Improves Chain of Thought Reasoning in Language Models](https://arxiv.org/abs/2203.11171)
- [Training Verifiers to Solve Math Word Problems](https://arxiv.org/abs/2110.14168)
- [Least-to-most Prompting Enables Complex Reasoning in Large Language Models](https://arxiv.org/abs/2205.10625)
- [Language Model Cascades](https://arxiv.org/abs/2207.10342)

[Evals]: https://developers.openai.com/api/docs/guides/evals
[Fine-tuning]: https://developers.openai.com/api/docs/guides/supervised-fine-tuning
[Function calling]: https://developers.openai.com/api/docs/guides/function-calling
[Prompt engineering]: https://developers.openai.com/api/docs/guides/prompt-engineering
[Structured outputs]: https://developers.openai.com/api/docs/guides/structured-outputs
