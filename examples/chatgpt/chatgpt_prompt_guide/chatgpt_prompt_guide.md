# **ChatGPT Enterprise: Practical prompt engineering for everyday work**

This guide is for Enterprise users who want more reliable results from ChatGPT without becoming prompt-engineering specialists. It is designed for everyday work: summarizing documents, drafting messages, searching internal knowledge, translating content, analyzing simple scenarios, pressure-testing ideas, and preparing polished first drafts.

Prompting is not about finding a magic phrase. It is about giving ChatGPT a clear handoff: what you are working on, what you want, what constraints matter, and what a useful result looks like.

The core formula is simple:

```md
Good prompt = context + task + constraints + output format + success criteria
```

You do not need all five pieces every time. For simple tasks, one or two sentences may be enough. For important work, the extra structure helps ChatGPT produce answers that are easier to trust, review, and use.

---

<details>
<summary><strong>Start using this right away</strong> — use the companion Skill</summary>

If you do not have time to read the full guide now, you can start by installing the companion Skill:

**Download the Skill here:** [Prompting Best Practices Skill](https://cdn.openai.com/cookbook/chatgpt-prompt-guide/prompt-redrafter.zip)

Skills are reusable workflows that help ChatGPT follow a repeatable process more consistently. This Skill helps turn rough instructions into clearer prompts using the ideas in this guide.

To install it:

1. Download the Skill from the link above.
2. Log into ChatGPT.
3. Open your profile or workspace menu.
4. Go to Skills.
5. Choose New Skill.
6. Upload the downloaded file.
7. Start a new chat and use it when you want help improving a prompt.

Then return to this guide when you want the reasoning behind the workflow.

</details>

---

## Table of Contents

1. [The basic mindset](#1-the-basic-mindset)
2. [Scope the job before writing the prompt](#2-scope-the-job-before-writing-the-prompt)
3. [Use a simple prompt structure](#3-use-a-simple-prompt-structure)
4. [Add accuracy guardrails when facts matter](#4-add-accuracy-guardrails-when-facts-matter)
5. [Use ChatGPT to improve your prompts](#5-use-chatgpt-to-improve-your-prompts)
6. [Debug bad outputs](#6-debug-bad-outputs)
7. [When prompting is not the problem](#7-when-prompting-is-not-the-problem)
8. [Reusable prompt template](#8-reusable-prompt-template)
9. [Examples](#9-examples)

---

## 1. The basic mindset

Treat your prompt like a handoff to a capable new colleague.

Imagine you are giving work to someone smart, motivated, and fast, but new to your team. They do not automatically know your project, your audience, your style preferences, your internal acronyms, or what your organization considers a good answer.

A strong handoff usually includes:

- the background they need
- the specific task you want done
- the audience or use case
- the constraints they must respect
- the format you want back
- the criteria you will use to judge quality

That same pattern works for ChatGPT.

A weak prompt asks ChatGPT to guess the job. A strong prompt defines the job.

### Optimize for clarity, not cleverness

Many bad outputs come from ordinary missing information. The prompt did not say who the audience was. It did not specify whether the answer should be short or detailed. It asked for analysis but did not define the decision. It asked for a summary but did not say what the summary would be used for.

Before blaming the model, ask:

> If I handed this prompt to a person outside my team, would they understand what I wanted without more explanation?

If the answer is no, add the missing context.

---

## 2. Scope the job before writing the prompt

Scoping means deciding what success looks like before asking ChatGPT to produce anything. Good scope prevents rambling prompts, shallow answers, and wasted iterations.

Before writing the prompt, answer four questions:

1. **What is the single deliverable I want?**
   Examples: a 300-word executive summary, a reply email, a comparison table, a risk checklist, a draft slide outline.

2. **What context does ChatGPT need?**
   Examples: the document to summarize, the audience, the business goal, the relevant time period, the source of truth.

3. **What constraints matter?**
   Examples: tone, length, privacy rules, required terminology, legal or compliance limits, source restrictions, formatting rules.

4. **How will I judge the answer?**
   Examples: it includes three action items, it uses only the attached document, it fits on one page, it explains assumptions, it is written for executives.

### One prompt, one main deliverable

A single prompt can only do so much. If you ask ChatGPT to summarize a document, draft an email, create a project plan, identify risks, rewrite in three tones, and produce a table all at once, the answer is more likely to be thin or inconsistent.

Tight scope usually beats an overloaded prompt.

Instead of:

```md
Analyze this report, summarize it, make slides, write an email, and create a rollout plan.
```

Break it into stages:

```md
First, summarize the report for an executive audience in 8 bullets. Focus on decisions, risks, and next steps.
```

Then:

```md
Using that summary, draft a concise email to the leadership team asking for a decision on the open issues.
```

Smaller steps give you more control and make it easier to catch mistakes.

---

## 3. Use a simple prompt structure

For everyday work, simple headings are enough. You do not need a complicated template. Headings help both you and ChatGPT see the job clearly.

A reliable structure is:

```md
# Context
What ChatGPT needs to know.

# Task
Exactly what you want ChatGPT to do.

# Constraints
Rules, limits, tone, sources, or things to avoid.

# Output format
The shape of the answer you want.

# Success criteria
How you will judge whether the answer is good.
```

The names of the headings matter less than the function they serve. You can rename them to fit the task: Background, Goal, Requirements, Audience, Sources, Format, Review Checklist, and so on.

### What to include in each section

**Context** gives the model the situation.

Examples:

- “I am preparing a weekly status update for senior leadership.”
- “This is a customer complaint about delayed implementation.”
- “I attached a draft policy and want to make it clearer for managers.”
- “The audience is nontechnical and needs a plain-language explanation.”

**Task** says what to do.

Examples:

- “Summarize the document into a decision-ready brief.”
- “Rewrite this email so it is firm but polite.”
- “Compare these three options and recommend one.”
- “Extract action items, owners, and dates.”

**Constraints** prevent common failure modes.

Examples:

- “Use only the attached document.”
- “Do not invent missing details.”
- “Keep it under 200 words.”
- “Use plain language and avoid legal jargon.”
- “Preserve the original meaning.”
- “Label anything uncertain as ‘Needs verification.’”

**Output format** makes the answer usable.

Examples:

- “Use a table with columns: Issue, Evidence, Impact, Recommended action.”
- “Return 5 bullets, then a short recommendation.”
- “Write the final answer as a ready-to-send email.”
- “Use Markdown headings.”

**Success criteria** tells ChatGPT what “good” means.

Examples:

- “A busy executive should understand the decision in under one minute.”
- “The answer should be copy/paste-ready.”
- “The summary must include risks, open questions, and next steps.”
- “The output should clearly separate facts from assumptions.”

---

## 4. Add accuracy guardrails when facts matter

For low-stakes drafting, you may only need tone and format. For factual, high-stakes, or source-grounded work, add guardrails.

Use a simple trust ladder:

### Low-stakes work

For brainstorming, rewriting, formatting, or tone-polishing, focus on usefulness.

Useful constraints:

- desired tone
- length
- audience
- format
- examples of what you like or dislike

### Factual work

For summaries, policy questions, internal research, or document review, provide source material and require source-grounded answers.

Useful constraints:

- “Use only the attached file.”
- “Quote directly when possible.”
- “If the answer is not in the document, say ‘Not specified.’”
- “Separate facts from assumptions.”
- “List any open questions.”

### High-stakes work

For legal, financial, medical, security, compliance, or executive-decision support, treat ChatGPT as an analysis and drafting aid, not the final authority.

Useful constraints:

- “Include citations or exact source references for key claims.”
- “Label uncertainty.”
- “List assumptions before the final recommendation.”
- “Provide a human review checklist.”
- “Do not present this as final advice.”

### Quick accuracy checklist

Add this to prompts when reliability matters:

```md
Before finishing, check:
- Did you use only the provided source material?
- Did you avoid inventing names, dates, numbers, or policies?
- Did you mark missing information as Not specified?
- Did you separate facts from assumptions?
- Did you include open questions where the source is unclear?
```

---

## 5. Use ChatGPT to improve your prompts

Meta-prompting means asking ChatGPT to help you write or improve the prompt itself. This is useful when you know the outcome you want but do not know how to phrase the request.

Use meta-prompting when:

- your notes are messy
- the task has many constraints
- you are not sure what context matters
- you want a repeatable prompt for a recurring workflow
- you want ChatGPT to ask clarifying questions before drafting

Example:

```md
Help me turn these rough notes into a strong prompt for ChatGPT.

First, identify what is unclear or missing. Then ask up to 5 clarifying questions. After that, write a clean prompt with these sections:

# Context
# Task
# Constraints
# Output format
# Success criteria

Here are my notes:
[paste notes]
```

Meta-prompting is not always necessary. If the task is simple, write the prompt directly. If the problem is missing source material, find the source material first. If the business requirement is unclear, resolve the requirement before asking ChatGPT to produce the final work.

---

## 6. Debug bad outputs

A bad response is often a diagnostic signal. Instead of starting over blindly, identify what went wrong and adjust the prompt.

| Bad output | Likely cause | Prompt fix |
|---|---|---|
| Too generic | Missing audience, goal, or context | Add the use case, reader, and decision being supported |
| Too long | No length limit or prioritization | Specify length and ask for only the highest-impact points |
| Wrong tone | Tone was implied, not stated | Name the tone and provide an example |
| Invented details | Source rules were missing | Require “Not specified” for missing information |
| Missed key points | Task was broad or vague | Add a checklist of required topics |
| Wrong format | Format was not explicit | Provide the exact output structure |
| Shallow analysis | Too many tasks in one prompt | Split the work into stages |
| Overconfident answer | No uncertainty instruction | Ask for assumptions, caveats, and confidence limits |

You can also ask ChatGPT to critique the output:

```md
Review your previous answer against this checklist:
- Accuracy: Did you invent any unsupported facts?
- Completeness: Did you cover all required points?
- Format: Did you follow the requested structure?
- Tone: Is it appropriate for the audience?
- Assumptions: Are guesses clearly labeled?

Then revise the answer.
```

---

## 7. When prompting is not the problem

Sometimes the prompt is not the real issue.

Prompting will not fix missing information, unclear requirements, contradictory source documents, outdated data, or a decision that requires human judgment. In those cases, the best prompt is one that makes the gap visible.

Use instructions like:

```md
If the source material does not contain enough information to answer confidently, say so. List what is missing and suggest the next source, person, or document to check.
```

or:

```md
If the requirements conflict, do not choose silently. Identify the conflict, explain the tradeoff, and recommend what decision needs to be made by a human owner.
```

This keeps ChatGPT from smoothing over ambiguity and producing a polished answer that looks more certain than it should.

---

## 8. Reusable prompt template

Use this when the task matters enough to structure clearly.

```md
# Context
[What are you working on? What background does ChatGPT need?]

# Task
[What exactly should ChatGPT do?]

# Audience
[Who will read or use the output? What do they care about?]

# Source material
[Paste or attach the relevant document, data, notes, or links.]

# Constraints
[Rules: length, tone, source limits, privacy, terminology, things to avoid.]

# Output format
[Bullets, table, email, memo, JSON, slide outline, etc.]

# Success criteria
[A good answer should accomplish X, include Y, and avoid Z.]
```

For quick tasks, compress it:

```md
I need [deliverable] for [audience/use case]. Use [source/context]. Keep it [tone/length]. Format it as [format]. Do not [constraint].
```

---

## 9. Examples

The examples below show how prompts improve as they become more specific. The goal is not to memorize these exact templates. The goal is to notice what changes: clearer context, sharper task, explicit constraints, and usable output format.

---

### Example 1: Summarize a document

#### Weak prompt: summarize a document

```md
Summarize this document.
```

#### Strong prompt: summarize a document

```md
# Context
I attached a document that I need to summarize for senior leadership. They need to understand the main point, risks, decisions, and next steps quickly.

# Task
Create a decision-ready summary of the document.

# Constraints
- Use only the attached document.
- Do not invent missing details.
- If something is unclear or absent, write Not specified.
- Keep it concise and skimmable.

# Output format
1. Executive summary: 5 bullets max
2. Key takeaways: 8-12 bullets
3. Decisions needed: bullets, or “No decisions requested”
4. Action items: Action | Owner | Due date | Notes
5. Risks and caveats: up to 5 bullets
6. Open questions: up to 10
```

#### Why it works: summarize a document

The weak prompt asks for a summary but gives no audience, purpose, source rules, or output structure. The strong prompt defines the reader, the decision context, the factual boundary, and the exact format.

---

### Example 2: Search internal knowledge

#### Weak prompt: search internal knowledge

```md
Search SharePoint for the PTO policy and summarize it.
```

#### Strong prompt: search internal knowledge

```md
# Context
I need the most current and authoritative internal guidance on our PTO policy.

# Task
Search SharePoint for the latest HR-owned PTO policy or employee handbook section. Summarize the current policy in plain language.

# Source ranking
Prioritize sources in this order:
1. HR or People Ops owned handbook or policy page
2. Official HR announcement linking to the policy
3. HR FAQ or manager guide

De-prioritize personal notes, old slide decks, duplicated pages, or documents without an owner/date.

# Conflict handling
If sources disagree, identify the conflict. Prefer the most recent HR-owned source or the source that explicitly identifies itself as the source of truth. If still unclear, list the question to ask HR.

# Output format
1. Best sources found: title, link, owner if available, last updated date if available, and why it is authoritative
2. PTO policy summary:
   - eligibility
   - accrual or unlimited PTO rules
   - request and approval process
   - carryover, caps, payout, or termination rules if stated
   - edge cases such as new hires, part-time employees, transfers, and leave of absence if stated
3. Recent changes, if found
4. Gray areas or missing information
5. Open questions for HR or Payroll

# Constraints
Use only internal sources. Do not guess. If a policy detail is missing, say Not specified.
```

#### Why it works: search internal knowledge

Internal-search prompts need more than keywords. They need source ranking and conflict handling. This prompt tells ChatGPT what counts as authoritative, what to ignore, and how to behave when documents disagree.

---

### Example 3: Adopt a professional role

#### Weak prompt: adopt a professional role

```md
Act as procurement and critique this memo.
```

#### Strong prompt: adopt a professional role

```md
# Role
You are a seasoned Procurement Lead at a 1,000-10,000 employee company. You protect the business from vendor risk, unclear scope, hidden costs, and weak negotiation posture while helping teams move quickly when the business case is strong.

# Context
I am sharing a vendor proposal memo before it goes to executive approval.

# Task
Pressure-test the memo for procurement readiness.

# Focus areas
- Pricing model, year-1 cost, renewal risk, and hidden costs
- Contract flexibility: pilot, ramp, opt-out, true-ups, renewal terms
- Security and compliance: data types, retention, deletion, subprocessors, SSO, RBAC, audit logs, encryption
- Implementation: timeline, owners, support model, dependencies, adoption plan
- Vendor lock-in: exit plan, data portability, migration cost
- Success metrics: how the business will know the tool worked

# Output format
1. Procurement verdict: Approve / Approve with conditions / Block
2. Top 7 issues: each with why it matters and how to fix it
3. Negotiation asks table: Ask | Rationale | Fallback if vendor refuses
4. Due diligence checklist: max 12 bullets
5. Missing information: copy/paste-ready sections to add to the memo
6. Questions for the business owner: max 10

# Memo
[paste memo here]
```

#### Why it works: adopt a professional role

The role is not a gimmick. It gives ChatGPT a professional lens. The prompt also defines the review criteria and requires specific, usable outputs instead of general criticism.

---

### Example 4: Research a business decision

#### Weak prompt: research a business decision

```md
Research the best East Coast cities for our first showroom.
```

#### Strong prompt: research a business decision

```md
# Decision goal
We need to pick one East Coast city for the first showroom of a mid-sized California-based D2C furniture brand.

# Context
The showroom's purpose is to increase brand trust and improve conversion, not just generate in-store revenue. We can support one launch market with a small team.

# Task
Build a shortlist of 6 East Coast cities, score them using the rubric below, and recommend one city plus a backup.

# Scoring rubric
Score each city from 1-5, where 5 is best.

- Market pull: 35%
  Demand proxies, target customer density, growth signals
- Showroom economics: 25%
  Rent, staffing, and operating burden
- Delivery feasibility: 15%
  Last-mile complexity, returns, service expectations
- Competitive intensity: 25%
  Incumbents, differentiation room, saturation risk

# Evidence rules
- Cite sources for numeric claims.
- Prefer sources from the last 24 months.
- If a direct metric is unavailable, use a proxy and label it clearly.
- Call out uncertainties that could change the ranking.

# Output format
1. Executive summary: 10 bullets max
2. Scored ranking table with weighted totals
3. City writeups:
   - why it wins
   - why it loses
   - key metrics used
   - assumptions or proxies
4. Final recommendation
5. Sources
```

#### Why it works: research a business decision

This turns a vague research request into a decision model. It tells ChatGPT how to compare options, what evidence to prefer, how to handle missing data, and what final output the business needs.

---

### Example 5: Rewrite rough notes into an email

#### Weak prompt: rewrite rough notes into an email

```md
Make this email sound better.
```

#### Strong prompt: rewrite rough notes into an email

```md
# Context
I need to send this email to a customer whose project has been delayed. We want to be honest about the delay, avoid sounding defensive, and preserve trust.

# Task
Rewrite my rough notes into a polished customer email.

# Tone
Calm, accountable, clear, and professional. Do not over-apologize. Do not blame another team.

# Constraints
- Keep it under 250 words.
- Include the new timeline.
- Include what we are doing next.
- End with an offer to answer questions.
- Do not invent details beyond my notes.

# Output format
Write the final email only.

# Rough notes
[paste notes]
```

#### Why it works: rewrite rough notes into an email

The prompt defines the situation, the relationship risk, the desired tone, the required content, and the length. That gives ChatGPT enough information to improve the message without changing its meaning.

---

## Final takeaway

Good prompting is good delegation.

You do not need to write elaborate prompts for every task. But when the output matters, take a moment to define the job clearly:

- What is the context?
- What is the task?
- What constraints matter?
- What should the output look like?
- What would make the answer successful?

The clearer the handoff, the more useful the result.
