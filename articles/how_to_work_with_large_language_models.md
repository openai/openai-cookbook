# How to work with large language models

Large language models are useful because they turn natural language, code, images, and other inputs into useful outputs. You can ask a model to summarize a document, classify a support ticket, explain a concept, transform messy text into structured data, write code, call tools, or answer questions from your own documents.

This guide is for people using large language models for the first time. It explains the mental model, the first API call, the prompting patterns that matter most, and the engineering habits that keep model-powered applications reliable.

## Start with the practical mental model

A large language model predicts output tokens from input context. Tokens are chunks of text, code, or other data that the model reads and writes. A model receives context, uses patterns learned during training plus any data and tools you provide, and generates a response one token at a time.

That simple description has a few important consequences:

- **Models are not databases.** A model may know many facts from training, but it does not automatically know your private data or the latest facts unless you provide them through context or tools.
- **Models are not deterministic by default.** The same request can produce different valid answers. Treat output quality as something to measure, not something to assume.
- **Models follow instructions and examples.** Clear instructions, relevant context, and representative examples are the main ways to steer behavior.
- **Models have limits.** Every request has a context window, output token limits, rate limits, latency, and cost. More context is not always better.
- **Models can use tools.** Modern model applications often combine the model with web search, file search, function calling, code execution, or other external systems.

The goal is not to write a perfect prompt on the first try. The goal is to build a small loop: write a prompt, run examples, inspect failures, improve the prompt or add tools, and measure again.

## Make your first API call

For new OpenAI API projects, use the [Responses API][Responses API]. It is the recommended interface for new applications and supports text, image inputs, structured outputs, conversation state, and tools.

Install the Python SDK and set your API key in an environment variable:

```bash
pip install openai
export OPENAI_API_KEY="your_api_key"
```

Then make a request:

```python
from openai import OpenAI

client = OpenAI()

response = client.responses.create(
    model="gpt-5.5",
    input="Explain what a vector database is in one paragraph.",
)

print(response.output_text)
```

Model names change over time. If you are not sure where to start, check the [model guide][Model guide]. As of May 2026, the model guide recommends `gpt-5.5` as the starting point for complex reasoning and coding, with smaller models such as `gpt-5.4-mini` and `gpt-5.4-nano` for lower latency and lower cost.

## Choose the right model for the job

Model choice is a product decision. Bigger models tend to do better on complex, ambiguous, or high-stakes work. Smaller models tend to be faster and cheaper, and can be excellent for well-defined tasks.

Use this rough starting point:

| Need | Good starting point |
| --- | --- |
| Complex reasoning, coding, planning, broad-domain work | A frontier model such as `gpt-5.5` |
| High-volume classification, rewriting, extraction, or routing | A smaller model after you verify quality with evals |
| Answers from private documents | A model plus file search or retrieval |
| Current facts | A model plus web search or a trusted external API |
| Structured JSON for an app | A model plus Structured Outputs |
| External actions, such as checking an order or booking a slot | A model plus function calling |

For reasoning models, tune `reasoning.effort` after you have a baseline. Lower effort usually improves latency and cost. Higher effort can improve quality on complex tasks. Defaults are model-dependent, so set the effort explicitly when predictable cost or latency matters.

```python
response = client.responses.create(
    model="gpt-5.5",
    reasoning={"effort": "low"},
    input="Draft three subject lines for a product launch email.",
)
```

## Write prompts as clear task specifications

A prompt is the information you give the model. In an API request, the prompt can include instructions, user input, examples, files, images, tool definitions, and prior conversation state.

Good prompts usually answer five questions:

1. **What is the task?** Say exactly what the model should do.
2. **What context should it use?** Include the relevant facts, documents, examples, or constraints.
3. **What output should it produce?** Specify format, length, tone, and required fields.
4. **What should it avoid?** State important boundaries, failure modes, and cases where it should ask for clarification.
5. **How will success be judged?** Include examples or criteria when quality matters.

For example:

```text
You are helping triage customer support tickets.

Classify the ticket into exactly one category:
- Billing
- Technical support
- Account access
- Other

Return only the category name. If the ticket does not contain enough
information, return Other.

Ticket:
"I was charged twice after upgrading my workspace yesterday."
```

For production applications, put durable application behavior in `instructions` or a `developer` message, and put the user's task-specific request in the user input.

```python
response = client.responses.create(
    model="gpt-5.5",
    reasoning={"effort": "low"},
    instructions=(
        "You classify support tickets. Return exactly one label: "
        "Billing, Technical support, Account access, or Other."
    ),
    input="I was charged twice after upgrading my workspace yesterday.",
)
```

## Use examples when instructions are not enough

Examples are often the fastest way to communicate judgment. If the model is making subtle mistakes, add a few representative input/output examples to the prompt.

```text
# Task
Label short product reviews as Positive, Neutral, or Negative.
Return only the label.

# Examples
Review: "Battery life is fine, but the case feels cheap."
Label: Neutral

Review: "Terrible support. I waited two weeks and got no answer."
Label: Negative

Review: "Setup took five minutes and the dashboard is excellent."
Label: Positive

# New review
Review: "It works, but the export button is hard to find."
Label:
```

Choose examples that cover the cases you care about:

- A typical easy case
- A borderline case
- A case that should be refused or marked unknown
- A case with messy formatting, typos, or missing information

Avoid adding hundreds of examples to a prompt unless you have tested that the added context improves quality enough to justify the cost and latency. If you have many high-quality examples and need stable behavior at scale, consider fine-tuning after you have a working prompt and eval set.

## Prefer structured outputs for JSON

If your application needs JSON, use [Structured Outputs][Structured outputs] instead of asking the model to "return valid JSON" in plain text. Structured Outputs constrain the model to a JSON Schema, which makes parsing and validation much more reliable.

```python
from pydantic import BaseModel
from openai import OpenAI

client = OpenAI()


class SupportTicket(BaseModel):
    category: str
    urgency: str
    summary: str


response = client.responses.parse(
    model="gpt-5.5",
    instructions=(
        "Extract a support ticket. Category must be Billing, "
        "Technical support, Account access, or Other. Urgency must be "
        "Low, Medium, or High."
    ),
    input="I cannot log in and the password reset link says it expired.",
    text_format=SupportTicket,
)

ticket = response.output_parsed
print(ticket.category)
```

Use Structured Outputs when another part of your application will consume the response. Use normal text when the output is meant to be read directly by a person.

## Add context instead of hoping the model knows

Models can only answer from information available in the request, in their training data, or through tools. When the task depends on specific facts, provide those facts.

For small amounts of context, put the relevant text directly in the prompt:

```text
Answer the question using only the policy excerpt below.
If the excerpt does not answer the question, say "I don't know."

Policy excerpt:
Employees may expense meals during business travel up to $75 per day.
Alcohol is not reimbursable.

Question:
Can I expense wine with dinner during a work trip?
```

For larger document collections, use file search or your own retrieval system. This pattern is often called retrieval-augmented generation:

1. Search your documents for passages relevant to the user's question.
2. Put the best passages in the model context.
3. Instruct the model to answer from those passages.
4. Ask the model to cite or identify the passages it used when traceability matters.

Retrieval is usually better than fine-tuning for factual knowledge that changes, private documents, policy manuals, catalogs, or customer-specific data. Fine-tuning changes behavior; retrieval supplies information.

## Use tools when the model needs to know or do something external

Tools let a model interact with systems outside its own context. OpenAI supports built-in tools, such as web search and file search, and custom tools through [function calling][Function calling].

Use tools when the model needs to:

- Look up fresh information
- Search private files
- Query a database
- Calculate with trusted code
- Take an application action
- Call an internal service

Function calling is a loop:

1. You define tools the model may call.
2. The model decides whether it needs a tool.
3. Your application executes the tool call.
4. Your application sends the result back to the model.
5. The model uses the result to answer the user or call another tool.

Tools need the same engineering discipline as any other interface. Give tools narrow names, clear descriptions, typed parameters, and explicit safety boundaries. Do not expose destructive actions, payment actions, or private data access without authorization checks and human confirmation where appropriate.

## Manage multi-turn conversations deliberately

For a short chat, you can pass previous messages yourself. With the Responses API, you can also chain turns with `previous_response_id`, which lets the model continue from an earlier response.

```python
first = client.responses.create(
    model="gpt-5.5",
    input="Give me a two-sentence explanation of prompt caching.",
)

second = client.responses.create(
    model="gpt-5.5",
    previous_response_id=first.id,
    input="Now explain the same idea to a non-technical product manager.",
)
```

Conversation state is convenient, but it is not free. Prior context still counts toward token usage, and long conversations can accumulate irrelevant information. For production systems, decide what should persist, what should be summarized, and what should be dropped.

## Understand common failure modes

Large language models are powerful, but they fail in recognizable ways.

| Failure mode | What it looks like | Better design |
| --- | --- | --- |
| Missing context | The model guesses about facts you did not provide | Add retrieval, file search, web search, or a trusted API |
| Ambiguous instructions | The answer is plausible but not what you wanted | Specify the task, format, constraints, and examples |
| Invalid structure | JSON is missing fields or has the wrong shape | Use Structured Outputs |
| Overconfident answers | The model answers when it should say it does not know | Tell it when to abstain, then test abstention cases |
| Prompt injection | User or retrieved text tells the model to ignore instructions | Separate trusted instructions from untrusted content, and limit tool permissions |
| Long-context drift | The model misses key details in a large prompt | Retrieve only relevant context, summarize, or split the task |
| Cost or latency surprises | A request is slow or expensive | Use smaller models, lower reasoning effort, fewer tokens, caching, or batch processing |

Do not treat a model response as inherently true. Treat it as a generated output that needs the right context, constraints, and verification for the job.

## Evaluate before you ship

For prototypes, manual testing is fine. For production, build evals. An eval is a repeatable test that checks whether your model application behaves the way you expect on representative inputs.

Start with a small table:

| Input | Expected behavior |
| --- | --- |
| A normal support ticket | Correct category |
| A vague ticket | Returns Other or asks for clarification |
| A ticket with two issues | Follows your tie-breaking rule |
| A prompt injection attempt | Ignores the malicious instruction |
| A request for unavailable facts | Says it does not know or uses a tool |

Run this set whenever you change the prompt, model, tools, retrieval settings, or schema. Expand the eval set every time you find a real failure. Over time, your evals become the safety net that lets you improve the application without guessing.

Use model-graded evals when human judgment is needed, but include exact-match or code-based checks whenever possible. For example, classification labels, JSON schemas, required citations, and refusal behavior can often be checked automatically.

## Keep users safe and in control

Safety is part of the application design, not a final prompt line. The right safeguards depend on the use case, but first-time builders should start with these habits:

- **Protect secrets.** Store API keys in environment variables or a secret manager. Do not put keys in notebooks, browser code, screenshots, or public repositories.
- **Use moderation and policy checks when relevant.** Add input and output checks for applications that may handle unsafe or sensitive content.
- **Red-team the application.** Test adversarial inputs, prompt injection attempts, off-topic requests, and requests that try to misuse tools.
- **Add human review for high-stakes work.** Medical, legal, financial, hiring, security, and code-changing workflows need appropriate human oversight.
- **Limit tool permissions.** A model should only have access to the data and actions needed for the current task.
- **Show uncertainty.** When the application cannot verify an answer, design the user experience so uncertainty is visible.

## Optimize after correctness

The first version should be clear and measurable. Optimize only after you know the system works.

Common optimization levers:

- **Use a smaller model** for simple or high-volume tasks after evals show acceptable quality.
- **Lower `reasoning.effort`** for tasks that do not need deep reasoning.
- **Reduce input tokens** by retrieving only relevant passages instead of sending whole documents.
- **Cap output length** with explicit instructions or `max_output_tokens`.
- **Reuse stable prompt prefixes** so prompt caching can help.
- **Batch offline work** when latency is not important.
- **Stream responses** when users benefit from seeing partial output quickly.

Cost, latency, and quality move together. Change one variable at a time and measure the result.

## Know when to use fine-tuning

Fine-tuning trains a model on examples so it better matches a task, style, or format. It is useful when you already have a good dataset and a clear success metric.

Before fine-tuning, try:

1. Better instructions
2. A few high-quality examples
3. Structured Outputs
4. Retrieval or file search for missing facts
5. Tool calling for external actions
6. Evals to identify the actual failure pattern

Fine-tuning is usually not the right way to add fast-changing knowledge. Use retrieval for knowledge and fine-tuning for behavior.

## A good first workflow

Use this sequence for a new project:

1. **Write the task in one sentence.** Example: "Classify support tickets into four categories."
2. **Create five to twenty test cases.** Include easy, hard, ambiguous, and adversarial examples.
3. **Make the simplest Responses API call.** Use a strong model first so you can learn the task shape.
4. **Add clear instructions and output constraints.** Keep the prompt readable.
5. **Add examples for judgment.** Cover the cases where the model is failing.
6. **Add Structured Outputs if code consumes the result.**
7. **Add retrieval or tools if the model needs external facts or actions.**
8. **Run evals and inspect failures.**
9. **Optimize model, reasoning effort, tokens, and latency.**
10. **Ship with monitoring, guardrails, and a plan for improvement.**

## Quick reference

| If you need... | Use... |
| --- | --- |
| A first model response | Responses API |
| Stable JSON | Structured Outputs |
| Current public facts | Web search or another trusted API |
| Answers from private docs | File search or retrieval-augmented generation |
| Actions in your product | Function calling |
| Better behavior on a known task | Prompt examples, evals, then possibly fine-tuning |
| Lower cost | Smaller model, fewer tokens, lower reasoning effort, caching, or batching |
| Higher reliability | Evals, tools, retrieval, structured outputs, and human review |

## Further reading

- [OpenAI model guide][Model guide]
- [Responses API reference][Responses API]
- [Prompt engineering guide][Prompt engineering]
- [Reasoning models guide][Reasoning models]
- [Structured Outputs guide][Structured outputs]
- [Function calling guide][Function calling]
- [Tools guide][Tools guide]
- [Conversation state guide][Conversation state]
- [Working with evals][Evals]
- [Supervised fine-tuning guide][Fine-tuning]
- [Safety best practices][Safety best practices]
- [Production best practices][Production best practices]

[Conversation state]: https://developers.openai.com/api/docs/guides/conversation-state
[Evals]: https://developers.openai.com/api/docs/guides/evals
[Fine-tuning]: https://developers.openai.com/api/docs/guides/supervised-fine-tuning
[Function calling]: https://developers.openai.com/api/docs/guides/function-calling
[Model guide]: https://developers.openai.com/api/docs/models
[Production best practices]: https://developers.openai.com/api/docs/guides/production-best-practices
[Prompt engineering]: https://developers.openai.com/api/docs/guides/prompt-engineering
[Reasoning models]: https://developers.openai.com/api/docs/guides/reasoning
[Responses API]: https://developers.openai.com/api/reference/resources/responses/methods/create
[Safety best practices]: https://developers.openai.com/api/docs/guides/safety-best-practices
[Structured outputs]: https://developers.openai.com/api/docs/guides/structured-outputs
[Tools guide]: https://developers.openai.com/api/docs/guides/tools
