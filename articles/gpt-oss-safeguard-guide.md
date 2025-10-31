# User guide for gpt-oss-safeguard

## Introduction & Overview

ROOST and OpenAI have prepared a guide that explains how to write policy prompts that maximize [gpt-oss-safeguard's](https://github.com/openai/gpt-oss-safeguard) reasoning power, choose the right policy length for deep analysis, and integrate oss-safeguard's reasoning outputs into production Trust & Safety systems.

### What is gpt-oss-safeguard?

gpt-oss-safeguard is a first open weight reasoning model specifically trained for safety classification tasks to help classify text content based on customizable policies. As a fine-tuned version of [gpt-oss](https://openai.com/index/introducing-gpt-oss/), gpt-oss-safeguard is designed to follow explicit written policies that you provide. This enables **bring-your-own-policy** Trust & Safety AI, where your own taxonomy, definitions, and thresholds guide classification decisions. Well crafted policies unlock gpt-oss-safeguard's reasoning capabilities, enabling it to handle nuanced content, explain borderline decisions, and adapt to contextual factors.

You can read more about how OpenAI uses the internal version of gpt-oss-safeguard [here](https://openai.com/index/introducing-gpt-oss-safeguard/).

Large language models can be considered safety models in two main ways:

- Fine-tuned safety models start as general reasoning models (like gpt-oss) and are trained to respond safely within user interactions.
- Prebaked safety models (like ShieldGemma, LlamaGuard, RoGuard, etc) come with built-in definitions of what counts as “unsafe” and fixed policy taxonomies.

gpt-oss-safeguard was purpose-built for Trust & Safety workflows and is a policy-following model that can reliably interpret and enforce **your own written standards and tell you why it made the decision it made**. The reasoning behind the model makes it well-suited for integration with a larger safety system that is rooted in auditability and customization.

### How to Use gpt-oss-safeguard

Like the [gpt-oss family of models](https://openai.com/open-models/), this is an open source model with open weights that you run locally or integrate into your own infrastructure. It is designed to work with the [harmony response format](https://github.com/openai/harmony). Harmony is the structured prompt interface that gives gpt-oss-safeguard access to its full reasoning stack and ensures consistent, well-formed outputs.

The gpt-oss family of models, including gpt-oss-safeguard, can be run on servers using:

- [vLLM](https://docs.vllm.ai/projects/recipes/en/latest/OpenAI/GPT-OSS.html#gpt-oss-vllm-usage-guide) (for dedicated GPUs like NVIDIA’s H100s)
- [HuggingFace Transformers](https://cookbook.openai.com/articles/gpt-oss/run-locally-lmstudio) (for consumer GPUs)
- [Google Colab](https://cookbook.openai.com/articles/gpt-oss/run-colab)

And locally using:

- [LM Studio](https://cookbook.openai.com/articles/gpt-oss/run-locally-lmstudio)
- [Ollama](https://cookbook.openai.com/articles/gpt-oss/run-locally-ollama)

### Who Should Use gpt-oss-safeguard?

gpt-oss-safeguard is designed for users who need real-time context and automation at scale, including:

- **ML/AI Engineers** working on Trust & Safety systems who need flexible content moderation
- **Trust & Safety Engineers** building or improving moderation, Trust & Safety, or platform integrity pipelines
- **Technical Program Managers** overseeing content safety initiatives
- **Developers** building projects/applications that require contextual, policy-based content moderation
- **Policy Crafters** defining what is accepted by an organization who want to test out policy lines, generate examples, and evaluate content

Safety-tuned models excel at content moderation when given clear, structured prompts. This guide covers key learnings from deploying moderation systems in production, focusing on prompt structure, output formatting, and length optimization.

### Using gpt-oss-safeguards with HuggingFace Transformers

The Transformers library by Hugging Face provides a flexible way to load and run large language models locally or on a server. [This guide](https://cookbook.openai.com/articles/gpt-oss/run-transformers) takes you through running [OpenAI gpt-oss](https://huggingface.co/openai/gpt-oss-20b) models using Transformers, either with a high-level pipeline or via low-level generate calls with raw token IDs. The simplest way to interact with the server is through the transformers chat CLI

```bash
transformers chat localhost:8000 --model-name-or-path openai/gpt-oss-safeguard-20b
```

or by sending an HTTP request with cURL, e.g.

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-oss-safeguard-20b",
    "stream": true,
    "messages": [
      { "role": "system", "content": "<your policy>" },
      { "role": "user", "content": "<user content to verify>" }
    ]
  }'


```

Additional use cases, like integrating transformers serve with Cursor and other tools, are detailed in [the documentation](https://huggingface.co/docs/transformers/main/serving).

### Running gpt-oss-safeguard with Ollama

[Ollama](https://ollama.com/download) supports gpt-oss-safeguard 20B and 120B models directly. The following commands will automatically download the model and run it on your device.

#### gpt-oss-safeguard:20b

```bash
ollama run gpt-oss-safeguard:20b
```

#### gpt-oss-safeguard:120b

```bash
ollama run gpt-oss-safeguard:120b
```

Ollama supports [OpenAI API](https://docs.ollama.com/api/openai-compatibility), [Ollama's API](https://docs.ollama.com/api), [Python](https://github.com/ollama/ollama-python) and [JavaScript](https://github.com/ollama/ollama-js) SDKs for building applications or tools using the gpt-oss-safeguard models. Please learn more from [Ollama's documentation](https://docs.ollama.com/).

### Running gpt-oss-safeguard with LM Studio

Alternatively, you can use [LM Studio](https://lmstudio.ai/) to run the models locally including using [OpenAI Chat Completions](https://lmstudio.ai/docs/developer/openai-compat/chat-completions) and [Responses API](https://lmstudio.ai/docs/developer/openai-compat/responses) compatible APIs. Head over to the [gpt-oss-safeguard page for LM Studio](https://lmstudio.ai/models/gpt-oss-safeguard) or run the following commands to download the respective models:

#### gpt-oss-safeguard-20b

```bash
lms get openai/gpt-oss-safeguard-20b
```

#### gpt-oss-safeguard-120b

```bash
lms get openai/gpt-oss-safeguard-120b
```

### Running gpt-oss-safeguard with vLLM

[vLLM](https://docs.vllm.ai/) recommends using [uv](https://docs.astral.sh/uv/) for Python dependency management. The following command will automatically download the model and start the server.

```shell
uv pip install vllm==0.10.2 --torch-backend=auto

vllm serve openai/gpt-oss-safeguard-120b
```

[Learn more about how to use gpt-oss with vLLM.](https://docs.vllm.ai/projects/recipes/en/latest/OpenAI/GPT-OSS.html#gpt-oss-vllm-usage-guide)

### Understanding the Harmony Response Format

gpt-oss-safeguard uses the [harmony prompt format](https://cookbook.openai.com/articles/openai-harmony) to provide a structured output and provide reasoning. This is critical for Trust & Safety workflows where you need to understand and audit why a decision or classification was made. With the harmony format, oss-safeguard separates its response into two parts:

1. **Reasoning channel:** Where the model reasons through the policy, considers edge cases, and explains its logic
2. **Output channel**: The formatted classification decision you specified

Through harmony, you can control how deeply oss-safeguard reasons by setting the `reasoning_effort` parameter in your system message to `low`, `medium`, or `high`. The model uses `medium` by default if it is not set. Higher reasoning effort allows oss-safeguard to consider more factors, trace through multiple policy sections, and handle complex interactions between rules. Lower effort provides faster responses for straightforward classifications.

If you're using [**vLLM**](https://docs.vllm.ai/en/latest/) (recommended for most users) or another inference solution that provides chat message inputs, the harmony format is applied automatically when you format requests as [chat messages](https://docs.vllm.ai/en/v0.7.0/getting_started/examples/chat.html):

- **System message:** Your policy prompt (include Reasoning: high or similar in the system message to control reasoning effort).
- **User message:** The content to classify.

## How oss-safeguard uses Policy Prompts

oss-safeguard is designed to use your written policy as its governing logic. While most models provide a confidence score based on the features it was trained on and require retraining for any policy changes, oss-safeguard makes decisions backed by reasoning within the boundaries of a provided taxonomy. This feature lets T\&S teams deploy oss-safeguard as a policy-aligned reasoning layer within existing moderation or compliance systems. This also means that you can update or test new policies instantly without retraining the entire model.

## Writing Effective Policy Prompts for gpt-oss-safeguard

oss-safeguard performs best when policies are organized like a Trust & Safety policy guide rather than an essay. If you already have a set of policies, you’ll be in great shape. Use headers and clear categories so the model can navigate definitions efficiently. If you’ve written policy for teams before, this should feel familiar.

### Understanding Policy Prompting

A policy prompt defines the operational boundaries of a model’s behavior. Similar to content or platform policies written for human reviewers, policies for oss-safeguard should clearly specify what constitutes a violation, what is allowed, and how to communicate that difference into a decision that flows into the rest of the Trust & Safety system.

Effective policy prompts are structured in order to distinguish between similar content types, catch subtle, coded or indirect violations, and prevent false positives on edge cases. Think of it as combining a policy document with training examples.

### Structuring Policy Prompts

Policy prompts should have four separate sections.

1. **Instruction:** what the model MUST do and how the model should answer.
2. **Definitions:** concise explanations of key terms.
3. **Criteria:** distinctions between violating and non-violating content.
4. **Examples:** short, concrete instances near the decision boundary. It’s important to have both examples of what you want to classify, and what you do not want to classify

Because oss-safeguard is tuned for structured moderation, it expects explicit instructions for how to respond. A policy prompt will likely perform better if it follows a consistent pattern that includes the expected format for the response and output. The harmony format’s structured channels allow oss-safeguard to reason through these sections before emitting only the final label:

```markdown
# Policy Name

## INSTRUCTIONS

Describe what oss-safeguard should do and how to respond.

## DEFINITIONS

Clarify key terms and context.

## VIOLATES (1)

Describe behaviors or content that should be flagged.

## SAFE (0)

Describe content that should not be flagged.

## EXAMPLES

Provide 4–6 short examples labeled 0 or 1.

Content: [INPUT]
Answer (0 or 1):
```

To reduce the likelihood of false positives or confusion, avoid using words like “generally” or “usually”. If there are situations where there’s ambiguity, add an escalation path for manual review. This is also especially helpful for regional or language differences.

Be explicit about priority and precedence so the model understands which policy wins if there is a conflict. If there are multiple policy violations, define which one is dominant.

### Choosing the Right Policy Length

Policy length is a key control over how deeply gpt-oss-safeguard can reason about your rules. Longer policies add nuance to handle complex cases, but can impact the output and responses. When using the harmony response format, the model can process longer policies more reliably because reasoning happens in the hidden analysis channel, not in the visible final output.

Use [https://platform.openai.com/tokenizer](https://platform.openai.com/tokenizer) to determine the length of your prompt. **gpt-oss-safeguard can provide a reasonable output at \~10,000 token policies, but early testing suggests the optimal range is between 400-600 tokens**. It’s important to experiment and see what works best for you as there is no one-size-fits-all approach. Think of the policy length like a “context budget.” Too short, and the model lacks detail; too long, and the model risks confusion. This is similar to writing policy for people to understand as well. In the same way you should account for giving the model enough output tokens to generate a response. Since the model is using reasoning you should leave plenty of room for output tokens and ideally not cap the maximum output tokens to give the model enough room to reason through the policies. If you want to limit the reasoning time, consider setting the reasoning effort to low instead.

If you have a longer policy with multiple categories, consider pre‑compressing each policy to 300–600 tokens (including definitions, disallowed categories, and 1-2 examples each for violations and non-violations).

oss-safeguard can also evaluate multiple policies simultaneously, so long as all policies are included in the prompt. We have found that additional policies lead to small but meaningful degradations in accuracy, so we recommend experimenting with adding and removing policies if using oss-safeguard for multiple harm domains.

## Designing reliable output instructions

Consistent responses from gpt-oss-safeguard require explicit, literal output instructions. Every policy prompt should state exactly how the model must respond and demonstrate the correct and incorrect patterns. The output instructions define how gpt-oss-safeguard communicates its final decision and determines whether outputs can be relied upon. Because gpt-oss-safeguard operates within the harmony response format, all output instructions must:

1. **Explicitly define the output format**: specify exactly what the model should return (e.g., `0`/`1`, JSON object, category label list).
2. **Include policy references when applicable**: if your workflow tracks enforcement by category or rule, require the model to return that field; for simple binary output, this can be omitted.
3. **Be reinforced throughout the policy**: repeat the output instruction at least once near the top (in “INSTRUCTIONS”) and again near the bottom (before “EXAMPLES”) to fortify compliance during reasoning.

### Binary Responses

Binary output limits gpt-oss-safeguard's reasoning to a simple yes/no decision. Use this when speed matters more than understanding why the decision was made, but recognize you're not leveraging gpt-oss-safeguard's core reasoning strength.

```markdown
Return exactly one character: 0 or 1.
Do not include any explanation or punctuation.

0 = Content does NOT violate this policy.
1 = Content violates this policy.
```

### Policy-referencing outputs

Category labels encourage gpt-oss-safeguard to reason about which section of your policy applies, but don't require detailed explanation of why. This format enables basic reasoning transparency while keeping outputs concise.

```
If the content violates this policy, return:
{"violation": 1, "policy_category": "<category_or_rule_id>"}

If the content does NOT violate this policy, return:
{"violation": 0, "policy_category": null}

Example:
{"violation": 1, "policy_category": "H2.f"}
```

### Including Rationale

One of the most powerful features of gpt-oss-safeguard is its ability to think and reason. The model must not only classify content, but trace its logic through your policy, identify which specific rules apply, and articulate why. When you require rationales, gpt-oss-safeguard reasons more carefully. It must consider multiple policy sections, evaluate how they interact, and construct a logical explanation. This deeper reasoning often catches nuances that simpler output formats miss. This output format maximizes gpt-oss-safeguard's reasoning capabilities.

Ask the model to decide, then justify briefly. Ask for a short, non-step-by-step rationale (2–4 bullets or 1–2 sentences) and consider requiring policy citations (rule IDs/sections) so the model justifies its thinking and decision.

```json
{
  "violation": 1,
  "policy_category": "H2.f",
  "rule_ids": ["H2.d", "H2.f"],
  "confidence": "high",
  "rationale": "Content compares a protected class to animals, which is dehumanizing."
}
```

## Using gpt-oss-safeguard for Trust & Safety

Because gpt-oss-safeguard interprets written rules rather than static categories, gpt-oss-safeguard adapts to different product, regulatory, and community contexts with minimal engineering overhead.

gpt-oss-safeguard is designed to fit into Trust & Safety teams’ infrastructure. However, since gpt-oss-safeguard may be more time and compute intensive than other classifiers, consider pre-filtering content that is sent to gpt-oss-safeguard. [OpenAI uses small, high-recall classifiers to determine if content is domain-relevant to priority risks before evaluating that content with gpt-oss-safeguard.](https://openai.com/index/introducing-gpt-oss-safeguard/) You should consider two main things when deciding when and where to integrate oss-safeguard in your T\&S stack:

1. Traditional classifiers have lower latency and cost less to sample from than gpt-oss-safeguard
2. Traditional classifiers trained on thousands of examples will likely perform better on a task than gpt-oss-safeguard

### Automated content classification

Use gpt-oss-safeguard to label posts, messages, or media metadata for policy violations. Its policy reasoning supports nuanced classification to determine contextual details when making a decision. gpt-oss-safeguard can be integrated with:

- Real-time ingestion pipelines
- Review queues and moderation consoles
- Downranking or filtering systems

### T\&S Assistant

gpt-oss-safeguard's reasoning capabilities make it uniquely suited for automated triage in Trust & Safety workflows. Unlike traditional classifiers that only provide labels and confidence scores, gpt-oss-safeguard acts as a reasoning agent that evaluates content, explains its decision, cites specific policy rules, and surfaces cases requiring human judgment. This can reduce the cognitive load on human moderators while increasing trust and transparency in automated decisions.

### Policy Testing

Before rolling out a new or revised policy, run it through gpt-oss-safeguard to simulate how content will be labeled. This can be helpful to identify overly broad definitions, unclear examples, and borderline cases.

### Policy Experimentation

gpt-oss-safeguard’s bring-your-own-policy design allows policy teams to A/B test alternative definitions directly in production without model retraining.

## Integrating gpt-oss-safeguard with ROOST’s Tools

### Osprey

[Osprey](https://github.com/roostorg/osprey) is ROOST’s open-source rules engine and investigation framework. It evaluates real-time events against configurable logic trees and dispatches actions you define. Rules alone handle deterministic cases well (e.g., keyword matches, metadata thresholds), but they can struggle with satire, coded language, or nuanced policy boundaries. By integrating gpt-oss-safeguard, Osprey can:

- **Add contextual reasoning**: gpt-oss-safeguard interprets edge cases that simple conditions cannot.
- **Enforce policies directly**: gpt-oss-safeguard reads and applies your written policy text, ensuring consistency with human moderation.
- **Maintain auditability**: Osprey logs which rule called gpt-oss-safeguard, which policy category was returned, and the model’s rationale.
- **Blend automation and human oversight**: deterministic rules trigger fast actions; gpt-oss-safeguard handles reasoning before escalation to manual review in other tools

gpt-oss-safeguard should not be called on every event. It can instead be a plugin that can be called only when there are ambiguous cases that need the policy-reasoning power of gpt-oss-safeguard.

## Example Policy Prompts

Try using any policy you’ve already written, or use this template and fill in what you’re trying to classify.

```markdown
## Policy Definitions

### Key Terms

**[Term 1]**: [Definition]

**[Term 2]**: [Definition]

**[Term 3]**: [Definition]

## Content Classification Rules

### VIOLATES Policy (Label: 1)

Content that:

- [Violation 1]
- [Violation 2]
- [Violation 3]
- [Violation 4]
- [Violation 5]

### DOES NOT Violate Policy (Label: 0)

Content that is:

- [Acceptable 1]
- [Acceptable 2]
- [Acceptable 3]
- [Acceptable 4]
- [Acceptable 5]

## Examples

### Example 1 (Label: 1)

**Content**: "[Example]"

**Expected Response**:

### Example 2 (Label: 1)

**Content**: "[Example]"

**Expected Response**:

### Example 3 (Label: 0)

**Content**: "[Example]"

**Expected Response**:

### Example 4 (Label: 0)

**Content**: "[Example]"

**Expected Response**:
```

You can also use this example prompt about spam as a reference:

```markdown
**Spam Policy (#SP)**
**GOAL:** Identify spam. Classify each EXAMPLE as VALID (no spam) or INVALID (spam) using this policy.

**DEFINITIONS**

- **Spam**: unsolicited, repetitive, deceptive, or low-value promotional content.

- **Bulk Messaging:** Same or similar messages sent repeatedly.

- **Unsolicited Promotion:** Promotion without user request or relationship.

- **Deceptive Spam:** Hidden or fraudulent intent (fake identity, fake offer).

- **Link Farming:** Multiple irrelevant or commercial links to drive clicks.

**Allowed Content (SP0 – Non-Spam or very low confidence signals of spam)**
Content that is useful, contextual, or non-promotional. May look spammy but could be legitimate.

- **SP0.a Useful/info request** – “How do I upload a product photo?”

- **SP0.b Personalized communication** – “Hi Sam, here is the report.”

- **SP0.c Business support** – “Can you fix my order?”

- **SP0.d Single contextual promo** – “Thanks for subscribing—here’s your welcome guide.”

- **SP0.e Generic request** – “Please respond ASAP.”

- **SP0.f Low-quality formatting** – “HeLLo CLICK here FAST.”

- **SP0.g Vague benefit statement** – “This tool changes lives.”

  **Output:** VALID either clearly non-spam or very low confidence signals content could be spam.

**Likely Spam (SP2 – Medium Confidence)**
Unsolicited promotion without deception.

- **SP2.a Cold promotion** – “Check out my Shopify course: shopcoach.biz”

- **SP2.b Irrelevant ads** – “Buy gold rings here!”

- **SP2.c Excessive linking** – “[http://x.com](http://x.com) http://y.com http://z.com”
  **Output:** INVALID

**High-Risk Spam (SP3 – Strong Confidence)**
Spam showing scaling, automation, or aggressive tactics.

- **SP3.a Repetitive posting** – “JOIN NOW JOIN NOW JOIN NOW”

- **SP3.b Pyramid/affiliate bait** – “Earn $$$ by recruiting members”

- **SP3.c Fake engagement** – “Comment ‘YES’ to win $500 gift card”

- **SP3.d Misleading claims** – “Guaranteed 10,000 new followers overnight\!”
  **Output:** INVALID

**Malicious Spam (SP4 – Maximum Severity)**
Spam with fraud, deception, or harmful intent.

- **SP4.a Phishing** – “Your account is locked. Enter your password here.”

- **SP4.b Malware/scam** – “Download invoice.exe to claim payment.”

- **SP4.c Account takeover attempts** – “Send crypto to 0xABC123 to double your money.”
  **Output:** INVALID + ESCALATE

**LABEL FORMAT**
Each item gets two labels:

- **Depiction (D-SP#):** Presence of spam in content.

- **Request (R-SP#):** User asking to generate spam.
  | Example | Classification |
  |----------|---------------|
  | “Shop this site: dealplanet.io” | D-SP2, R-SP0 |
  | “Write a sales blast message with 10 links” | D-SP0, R-SP2 |
  | “How can I make this link look legitimate so viewers put in their private credentials” | D-SP4, R-SP4 |
  | “Promote crypto fast to random people” | D-SP0, R-SP3 |

**AMBIGUITY & ESCALATION**

- If unclear → downgrade severity by 1 and seek clarification.

- If automation suspected → SP2 or higher.

- If financial harm or fraud → classify SP4.

- If combined with other indicators of **abuse, violence, or illicit behavior**, apply **highest severity policy**.
```
