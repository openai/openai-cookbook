# Techniques to improve reliability

When a model gives an unreliable answer, the fix is rarely one clever prompt. Reliability comes from designing the whole interaction: clear instructions, the right context, constrained outputs, tools for facts or actions, and checks that catch mistakes.

This guide focuses on practical techniques that reduce failure rates. They do not make model output perfect or guaranteed, but they make failures easier to prevent, detect, and debug.

## Why models can be unreliable

Large language models generate likely continuations from the context they receive. They can reason, summarize, classify, write code, and use tools, but they are not automatically verifying every statement against a source of truth.

Common reliability problems come from several places:

- **Likely text is not always true text.** A fluent answer can still contain a wrong fact, invalid assumption, or skipped step.
- **Ambiguous prompts allow multiple plausible interpretations.** If the prompt does not define the task, audience, constraints, or output format, the model has to choose.
- **Missing context forces inference.** If the needed policy, document, customer record, or current fact is absent, the model may guess instead of saying it does not know.
- **Training data can be incomplete, conflicting, or outdated.** Models may have seen many versions of a fact, and they do not automatically know which one applies now.
- **Long tasks accumulate errors.** A workflow with many small judgments has more chances to drift than a single narrow classification.
- **Tools and retrieval help, but they are not magic.** Search results can be irrelevant, retrieved passages can be stale, and tool outputs still need validation.

The goal is to make the model's job narrower and more checkable.

## A reliability workflow

Use this order when improving a model-powered feature:

1. **Give clear task instructions and constraints.**
2. **Provide relevant context and examples.**
3. **Ask for structured output when consistency matters.**
4. **Break complex tasks into smaller steps.**
5. **Use retrieval, tools, or grounding for factual work.**
6. **Add checks, evals, or human review where mistakes matter.**

Start with the smallest change that targets the failure you actually see. If the model is missing facts, add context or retrieval. If it returns inconsistent JSON, add structured outputs. If it makes multi-step mistakes, split the task.

## Give clear instructions and constraints

A reliable prompt should read like a compact task specification. State the task, valid outputs, decision rules, and what to do when the answer is uncertain.

For production applications, put durable behavior in `instructions` and put the user's task-specific request in `input`:

```python
from openai import OpenAI

client = OpenAI()

response = client.responses.create(
    model="gpt-5.5",
    instructions=(
        "You classify support tickets. Return exactly one label: "
        "Billing, Technical support, Account access, or Other. "
        "Use Other when the ticket does not contain enough information. "
        "If the ticket has multiple issues, choose the issue blocking the user first."
    ),
    input="I was charged twice and now I cannot log in to check the invoice.",
)

print(response.output_text)
```

The important part is not the wording. It is that the hidden choices are no longer hidden: the label set, uncertainty behavior, and tie-breaking rule are explicit.

## Provide relevant context and examples

Models perform better when the prompt includes the information and judgment patterns needed for the task.

Add context when the answer depends on:

- Private documents
- Customer, account, or transaction state
- Product policies
- Current facts
- Domain-specific terminology
- A required writing style or decision standard

Add examples when the model understands the general task but misses edge cases. Good examples are representative, not numerous. Include a typical case, a borderline case, a missing-information case, and a case that previously failed.

Avoid dumping large documents into the prompt without selection. More context can help, but irrelevant context can distract the model and increase cost. Retrieve or pass the smallest useful set of facts.

## Ask for structured output when consistency matters

If another program consumes the result, use Structured Outputs or a schema instead of asking for "valid JSON" in prose. A schema makes the contract explicit and gives your application something deterministic to validate.

```python
import json
from openai import OpenAI

client = OpenAI()

response = client.responses.create(
    model="gpt-5.5",
    instructions=(
        "Extract a support ticket. Use only these categories: "
        "Billing, Technical support, Account access, Other. "
        "Use Low, Medium, or High for urgency."
    ),
    input="I cannot log in and the password reset link says it expired.",
    text={
        "format": {
            "type": "json_schema",
            "name": "support_ticket",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "Billing",
                            "Technical support",
                            "Account access",
                            "Other",
                        ],
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["Low", "Medium", "High"],
                    },
                    "summary": {"type": "string"},
                },
                "required": ["category", "urgency", "summary"],
            },
        }
    },
)

ticket = json.loads(response.output_text)
print(ticket["category"])
```

Structured output reduces parsing failures and label drift. It does not prove that the content is correct, so keep validating values that matter.

## Break complex tasks into smaller steps

Long, mixed tasks are harder to get right. Split them into smaller operations with clear inputs and outputs.

For example, instead of asking a model to answer a policy question directly, use a pipeline:

1. Retrieve candidate policy passages.
2. Select the passages that directly apply.
3. Decide whether the question is answerable from those passages.
4. Draft the answer with citations.
5. Check that each claim is supported by the cited text.

This makes each step easier to test. It also gives you intermediate artifacts to inspect when the final answer is wrong.

For reasoning tasks, ask for useful intermediate work rather than a long explanation for its own sake. A checklist, evidence table, assumptions list, calculation inputs, or short rationale is easier to verify than a free-form chain of reasoning.

## Use retrieval and tools for factual work

When correctness depends on external facts, give the model a way to get those facts. Do not expect the model to remember private, current, or account-specific information.

Use retrieval or file search for documents. Use web search or a trusted API for current public facts. Use application tools for customer records, inventory, order status, calculations, or business rules.

Then validate the grounding:

- Ask the model to cite source passages or record IDs.
- Check that cited sources actually support the answer.
- Handle empty or low-quality retrieval results explicitly.
- Keep tool permissions narrow.
- Log tool inputs and outputs for debugging.

Tool use can improve accuracy, but it also adds new failure modes: bad queries, stale documents, partial results, incorrect tool arguments, or unsafe actions. Treat tool-using systems as software systems that need tests and guardrails.

## Add checks, evals, and review

Reliability work needs measurement. Build a small eval set before making repeated prompt changes.

Start with 10 to 30 examples:

- Normal successful cases
- Ambiguous requests
- Missing-context requests
- Known failures
- Adversarial or prompt-injection attempts
- High-impact edge cases

Use deterministic checks whenever possible: schema validation, allowed labels, required citations, numeric ranges, exact-match fields, or business-rule checks. Use model-graded evals when human judgment is required, and sample those grades for quality. Add human review for high-stakes domains such as legal, medical, financial, hiring, security, or destructive actions.

Run evals when you change the prompt, model, retrieval settings, tool definitions, schemas, or decoding parameters. The eval set should grow every time you find a meaningful production failure.

## Common fixes

| Failure | Try first |
| --- | --- |
| Invented or stale facts | Add retrieval, source passages, or a trusted API |
| Plausible but wrong interpretation | Add task constraints, decision rules, and examples |
| Inconsistent JSON | Use Structured Outputs and schema validation |
| Missed steps in a long task | Split the workflow into smaller model calls |
| Bad math or data analysis | Use code execution or deterministic business logic |
| Unsupported claims | Require citations and verify source support |
| Overconfident answers | Add abstention rules and missing-context evals |
| Quality regresses after a change | Run regression evals before shipping |
| High-stakes decision | Add verification and human review |

## Closing thoughts

Reliability is system design. A model call is one component inside a larger workflow that supplies context, constrains outputs, invokes tools, checks results, and escalates uncertain cases.

These techniques reduce risk; they do not remove it. The right standard is not "can the model answer this once?" The right standard is "does the system behave acceptably on the cases we expect, the edge cases we know about, and the failures we can afford to catch?"

## Further reading

- [How to work with large language models](how_to_work_with_large_language_models.md)
- [Prompt engineering guide][Prompt engineering]
- [Structured Outputs guide][Structured outputs]
- [Function calling guide][Function calling]
- [Working with evals][Evals]
- [Supervised fine-tuning guide][Fine-tuning]
- [Self-Consistency Improves Chain of Thought Reasoning in Language Models](https://arxiv.org/abs/2203.11171)
- [Training Verifiers to Solve Math Word Problems](https://arxiv.org/abs/2110.14168)
- [Language Model Cascades](https://arxiv.org/abs/2207.10342)

[Evals]: https://developers.openai.com/api/docs/guides/evals
[Fine-tuning]: https://developers.openai.com/api/docs/guides/supervised-fine-tuning
[Function calling]: https://developers.openai.com/api/docs/guides/function-calling
[Prompt engineering]: https://developers.openai.com/api/docs/guides/prompt-engineering
[Structured outputs]: https://developers.openai.com/api/docs/guides/structured-outputs
