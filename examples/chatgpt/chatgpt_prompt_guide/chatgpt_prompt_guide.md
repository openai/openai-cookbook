# **ChatGPT Enterprise: Practical prompt engineering for everyday work**

This guide is for Enterprise users who want more reliable results from ChatGPT without needing advanced technical expertise. It is a practical, example-driven guide that is easy to apply to your everyday work, whether that’s summarizing documents, drafting emails, translating content, analyzing simple scenarios, or brainstorming narratives.

Note, there is no single perfect prompt template. This guide is designed to help you make your task clear enough for ChatGPT to produce reliable, useful results.

> <details>
> <summary><strong>Start using this right away</strong> — install the accompanying Skill and apply these best practices immediately</summary>
> 
> Don't have time to read the full guide right now? You can start applying these prompting best practices immediately by installing the accompanying Skill in ChatGPT.
> 
> **Download the Skill here:** [Prompting Best Practices Skill](https://cdn.openai.com/cookbook/chatgpt-prompt-guide/prompt-redrafter.zip)
> 
> Skills are small reusable add-ons that teach ChatGPT how to perform a specific task or follow a repeatable workflow. This Skill is designed to help apply the guidance in this guide more consistently, so you can get better results with less setup each time.
> 
> **To install it:**
> 1. Download the Skill from the link above
> 2. Log into ChatGPT
> 3. Click your profile icon in ChatGPT
> 4. Select Skills in the pop-up menu
> 5. Click **New Skill**
> 6. Select **Upload from your computer**
> 7. Upload the downloaded file
> 8. Start a new chat and use it in your everyday work
> 
> Then, when you have time, come back to this guide for the deeper explanations, examples, and reasoning behind the approach.
> </details>


## **Table of Contents**
1. [Introduction](#1-introduction)
2. [Mindset](#2-mindset)
3. [Scope the problem](#3-scope-the-problem)
4. [Write the prompt clearly](#4-write-the-prompt-clearly)
5. [Use ChatGPT to help you prompt (meta-prompting)](#5-use-chatgpt-to-help-you-prompt-meta-prompting)
6. [Improve accuracy](#6-improve-accuracy)
7. [Conclusion](#7-conclusion)
8. [Prompting 101 Examples](#prompting-101-examples)

## 1. Introduction
Prompt engineering is the art and science of designing and optimizing prompts to effectively interact with language models and to get responses that are accurate, concise, and relevant.

Large language models generate responses by predicting the next word based on patterns learned from data. That’s why the way you ask matters so much: your prompt is the model’s starting point for what “good” looks like.

A few key themes to guide these next sections: 
- Prompting isn’t about tricking the model - it’s about being clear about the job, the context, and what success looks like.
- Prompting is iterative (and that’s normal) – Don’t expect your first prompt to work perfectly. Try something, fail, learn from the failure, and build a better prompt. You should expect to refine prompts over time.

## 2. Mindset
**Treat your prompt like a “handoff” to a new intern**

Imagine you’re assigning work to a smart intern on their first week. They’re eager and capable — but they don’t know your project, your preferences, or what your team considers “good.” They can’t fill in missing context the way a longtime coworker can.

If you were handing off a task, especially to a new intern, you’d usually include:
* What you’re working on (background + why it matters)
* What you want them to do (the specific task)
* What “good” looks like (audience, tone, format, and any must-include points)

The same mindset works for prompts. You’re not just asking a question — you’re defining a task so ChatGPT can deliver something you can actually use.

**Optimize for clarity, not cleverness**

Many prompts fail for simple reasons: the model wasn’t told the audience, the format, or the decision criteria. If you make those explicit, quality tends to jump quickly.

**Sanity check:** If you showed your prompt to someone outside your role or your organization, would they understand what you want without additional explanation?

## 3. Scope the problem 

Scoping is defining success and limits before you start. Good scope prevents long, flailing prompts and reduces wasted iterations. It also makes results easier to trust because you’ve clearly defined what “good” looks like.

### A. Before you write anything, think carefully 

* **What context do I need to feed the model to understand this task?**
* **What is the single output I want?**
Examples: “a 300‑word executive summary,” “an email reply draft,” “a table of key facts.”
* **What formatting and settings matter?**
Length, tone, bullets vs. paragraph, legal/regulatory restrictions, which data sources to use.
* **What will I judge as “good”?**
Clarity, accuracy, style, or a checklist of items the reply must include.

**Rule of thumb:** If you can’t describe “good” in one or two sentences, the model can’t reliably hit it either.

### B. Scope the problem to what a prompt can do
**Remember: A single prompt can only do so much.** If you keep expanding a prompt to include more tasks, more formats, and more edge cases, you’re more likely to get shallow, inconsistent, or incomplete results. Tight scope usually beats a “do everything” prompt.

**Why?** ChatGPT typically produces a similar amount of output each time. If you ask it to cover more things, it spreads that same amount of attention across everything — which means less depth per item. More tasks → thinner answers.

So when a prompt feels vague or overloaded, shrink it until it’s clearly one deliverable.

For example, if you ask ChatGPT to “Write a biography for each president of the US”, it will likely return 45 1-sentence summaries. But if you ask ChatGPT to “Write a section of a biography of the 6th president of the US, focusing only on his first year in office”, then it will return a lot of depth on major highlights of 1 year in office

**Smaller scope → better depth and control.** Break up your prompts into multiple separate prompts if required.

## 4. Write the prompt clearly 
**Before you write the full prompt, take 30 seconds to outline the job in a simple structure. The easiest way is to use headings.**

All LLMs understand a language called “markdown” – the easiest aspect to master in markdown is that “#” is a label for “Header”. So in ChatGPT, the model understands that a line that starts with “#” is a section or header title in a document. It helps both you and ChatGPT quickly see what each part of the prompt is doing.

We recommend the prompt layout below. Below are several examples using real use cases.

```md
# Context
What you’re working on and any background information the model needs.

# Instructions
Exactly what you want ChatGPT to do.

# Additional info / Constraints
Anything it must follow: tone, length, rules, constraints, etc.
```

This is a minimal recommended structure, not a fixed template. You can add, remove, or rename headers as needed to fit the task.

### Context
In Context, we recommend you encourage the model to adopt a persona.

**Examples**

* “You are a program manager writing a weekly status update.”
* “You are a customer support lead drafting a calm, helpful reply.”
* “You are a finance analyst explaining assumptions clearly.”
* “You are a clear, concise writing assistant. Do not invent facts. If information is missing, do not make assumptions.”

### Instructions

In Instructions, you should clearly list exactly what you want ChatGPT to do. 

**Examples**
* “Extract relevant information and present it in a clean, organized format.”
* “Read the document and produce a 3–5 bullet executive summary”
* “Provide a recommendation with 2–3 supporting reasons.”


### Additional Information

In Additional Information, below are some examples of what to include to improve output quality:

* Goal: What does “good” look like? <br>
Examples: “3‑sentence executive summary with actions,” “CSV of extracted table rows,” “policy draft for managers.”
* Audience / tone: Who’s reading it? <br>
Senior exec, legal, developer, customer, internal team - each implies different language and detail level.
* Format & length: What shape should the output take? <br>
Bulleted list, table, JSON, 100–200 words, or “one slide worth of content.”
* Coverage: What must it consider, and what can it ignore? <br>
Which documents, time period, departments, or regions matter?
* Constraints: Anything non‑negotiable. <br>
Deadlines, data privacy rules, prohibited content, “don’t invent facts,” “don’t include names,” etc.
* Acceptance criteria: How you’ll decide it’s correct. <br>
Examples: “contains 3 action items,” “matches our template,” “valid CSV that parses.”

## 5. Use ChatGPT to help you prompt (meta-prompting)

Meta-prompting is when you use ChatGPT to **write or improve your prompt.** You're essentially asking the model to help you give it better instructions. This is especially helpful when you know what you want, but you're not sure how to phrase it clearly or consistently.

To do this, simply paste in your messy notes to ChatGPT (or use the speech feature to talk to it directly) and ask ChatGPT for help making the prompt clearer: ask it to ask you questions, ask it to play back what you're trying to do, identify missing gaps, etc.

You can also use a **Skill** to assist with this. For example, if you find yourself repeatedly asking ChatGPT to clean up rough prompts in a consistent way, a prompt-redrafting Skill can turn that into a more repeatable workflow.

**Example Prompt**

```
Help me build a prompt that I can feed to a GenAI language model. I'm going to paste my draft prompt below - you ask me questions, then write up a clean prompt summarizing what we covered. The final prompt should have 3 sections ("# Context", "# Instructions", and "# Additional Information").
```

**When *not* to meta‑prompt**

Meta‑prompting isn't the right tool when:

* The task is already simple and you can write the prompt directly
* The missing piece is **source material** (you need the right document or data, not a prettier prompt)
* You're trying to "prompt your way" out of unclear requirements - scoping still comes first

Skills can help make meta-prompting more consistent, but they do not replace good scoping or the need for the right source material.

## 6. Improve accuracy

If the output must be factual or high‑stakes, add simple guardrails:

* **Ask for sources** (or ask it to quote directly from the provided material when possible).
* **Mark uncertainty:** “Label anything uncertain with (needs verification).”
* **Add a quality checklist** at the end of your prompt:
    * “Make sure the output includes X, Y, Z; avoid A, B.”
* **Request self‑checks:**
    * “Before finishing, list any assumptions you made.”

This is one of the fastest ways to catch “confident guesses” early.

Additionally, make sure the model has all the context it needs. For example, make sure to upload relevant files and/or connect to relevant ChatGPT Apps. 

To test accuracy, we recommend running a small evaluation. Come up with 5-10 questions (where you know the answer). Then ask ChatGPT to write up its answers and compare the results. Alternatively, you could even ask ChatGPT to review an output, with a prompt like this: 

```
Check the output for:
- Accuracy: Does it avoid making up facts?
- Completeness: Did it include the required points?
- Format: Does it match the requested structure?
- Tone: Is it appropriate for the audience?
- Assumptions: Are any guesses clearly labeled?
```

## 7. Conclusion
The fastest way to get more reliable results from ChatGPT Enterprise is to treat each prompt like a clear handoff: share the minimum background, define the task, and describe what "good" looks like. When you do that, you'll spend less time wrestling with inconsistent outputs and more time shipping work you can actually use.

Remember:
* Scope first: one prompt, one deliverable. Smaller scope leads to better depth and fewer surprises.
* Structure your prompt: use simple headings like # Context, # Instructions, and # Additional Information / Constraints to remove ambiguity.
* Iterate intentionally: if the first result is off, refine the prompt based on what went wrong (missing context, unclear format, unclear audience, overloaded asks).
* Add accuracy guardrails when it matters: ask for sources or quotes when possible.

If you follow this guidance consistently, you'll get outputs that are clearer, more trustworthy, and faster to turn into valuable work. Next, we'll make this concrete with some prompt examples showing OK → Good → Excellent prompts across common everyday tasks.

## Prompting 101 Examples

To illustrate the difference between okay, good, and excellent prompts, let’s start with a simple example.

#### Okay prompt (task)  
```md
Tell me about perennial gardening.
```

#### Good prompt (+ context / persona)
```md
I am a novice gardener living in Northern Virginia. Tell me about perennial gardening. I am interested in planting some perennials in a 10 ft x 10 ft flower bed in front of my house.
```

#### Excellent prompt (+ output) 
```md
I am a novice gardener living in Northern Virginia. Tell me about perennial gardening. I am interested in planting some perennials in a 10 ft x 10 ft flower bed in front of my house. Provide a beginners guide to perennial gardening in my area with step by step instructions. Include a list of recommended plants for my area and a shopping list of supplies I need to buy. 
```

With that foundation in mind, here are a few practical use cases.

### 1. Summarize a Document

#### 1. Okay prompt
```md 
Summarize the attached document for **[audience]** in **10 bullets**, focusing on **what it is, key points, and what to do next**.
```

#### 2. Good prompt
```md
# Context
I've attached a document that I need summarized for **[audience]**.

# Task
Summarize the document so the audience can quickly understand:
- what it is and why it matters
- the key takeaways
- decisions needed and next steps

# Requirements
- 1-paragraph overview (what this doc is + purpose)
- Key points (7–12 bullets)
- Decisions required (if any)
- Action items / next steps (owner + timeline if stated)
- Risks / caveats (if any)
- Open questions (if the doc is unclear)

# Output format
Use headings and bullets. Keep it concise. Do not invent details — if missing, say “not specified.”
```
#### 3. Excellent prompt
```md
## System
You are an expert synthesizer. Convert the uploaded document into a crisp, decision-ready brief.
**Do not invent details.** If something is missing, label it as **Not specified** or add it to **Open Questions**.

## Audience
Summarize for: **[audience]**  
Their goal: **[e.g., decide / align / get informed / take action]**

## Task
Create a decision-ready summary of the document below.

## Output format (NON-NEGOTIABLE)
1) **Executive Summary (5 bullets max)**
   - What this document is
   - Why it matters
   - Most important takeaway
   - Decision(s) needed (if any)
   - Immediate next step

2) **Key Takeaways**
   - 8–12 bullets, written in plain language
   - Include numbers/dates only if stated in the document

3) **Decisions & Recommendations**
   - Decisions required (if any)
   - Recommendations stated in the document (if any)
   - If the document is informational only, say “No decisions requested.”

4) **Action Items**
   - List action items explicitly stated or clearly implied
   - Format: Action | Owner (if stated) | Due date (if stated) | Notes
   - If not stated, use “Not specified.”

5) **Risks / Constraints / Caveats**
   - Up to 5 bullets
   - Only include what the document supports

6) **Open Questions**
   - Up to 10 questions that must be answered to execute or decide

7) **Direct Quotes (optional, max 3)**
   - Include up to 3 short quotes (≤25 words each) that are the most “load-bearing”
   - If the doc is long, select quotes that best represent its intent

## Constraints
- Keep it skimmable; no long paragraphs
- Use the document’s terminology; don’t rebrand concepts
- Be explicit about uncertainty; mark anything missing as **Not specified**
- If there are multiple sections, preserve structure by grouping takeaways by section
```

### 2. Search for (Apps)

#### 1. Okay prompt
```md
Search our SharePoint for the latest HR handbook and summarize the current PTO policy.
```

#### 2. Good prompt
```md
## Context
I need the most current, authoritative internal guidance on our **PTO policy**, located in SharePoint (HR handbook).

## Task
Search our **SharePoint** for the latest **HR handbook** and summarize the **current PTO policy**.

## Requirements
- Prefer the newest and most authoritative HR-owned doc(s).
- If multiple versions exist, identify which one is current and why.
- Summarize in plain language:
  - Eligibility (who the policy applies to)
  - Accrual/balance rules OR “unlimited PTO” rules (whichever applies)
  - Request/approval process
- Include links/titles to the sources you used.

## Output format
1) Source(s) found (with SharePoint links)  
2) PTO policy summary (headed bullets)  
3) Any recent changes/updates (if found)  
4) Open questions / missing info (if unclear)
```

#### 3. Excellent prompt

```md
## System (role)
You are an expert internal knowledge navigator. Your job is to find the **most authoritative and up-to-date** internal answer, reconcile conflicts across documents, and cite exactly where each key point comes from.

## Goal
Find and summarize our company’s current **PTO policy** from internal knowledge sources (SharePoint).

## Search strategy (do this in order)
1) Find the canonical handbook/policy doc for PTO
2) Find recent updates and amendments to the PTO policy
3) Find clarifications and edge cases e.g. carryover, accrual, medical leave etc.

## Source ranking rules
Prioritize in this order:
1) HR/People Ops owned handbook or policy repository (source of truth)
2) Official HR announcements that link to the policy
3) HR FAQs / manager guides that clarify edge cases
De-prioritize personal notes, outdated slide decks, or duplicated wiki pages.

## Conflict handling
If two docs disagree:
- Prefer the most recent HR-owned doc OR the doc that explicitly says it is the source of truth
- Call out the discrepancy and recommend which doc should be treated as current
- If still unclear, list the exact question to ask HR/Payroll (and who to ask)

## Output format
1) **Best sources** (up to 5)
   - Title + SharePoint link + owner (if available) + last updated date (if available)
   - 1-line why it’s authoritative
2) **PTO policy summary** (copy/paste ready)
   - Eligibility / coverage
   - How PTO is earned/managed (accrual vs unlimited, balance visibility)
   - Request & approval process (lead time, manager approval, blackout rules if any)
   - Carryover / caps / payout rules (if applicable)
   - Related policies: sick time, holidays, LOA (only if referenced)
   - Edge cases: new hires, part-time, transfers, LOA, termination
3) **What changed recently** (last 6–18 months, if found)
4) **Gray areas** (max 5) + how internal docs address them (or “Not specified”)
5) **What to open next** (3 links) for deeper detail
   - e.g., sick leave policy, holiday calendar, leave of absence policy, payroll payout rules
6) **Open questions** (max 7) + suggested owners (HR/People Ops/Payroll)

## Constraints
- Use only what’s supported by internal sources; do not guess
- If you can’t find the policy, propose the best next queries and likely owners
- Keep it concise and skimmable
```

### 3. Adopt a Persona

#### 1. Okay prompt

```md
Act as a procurement lead and critique this memo, focusing on risks, missing info, and what you’d negotiate.

Memo [paste or attach memo]
```

#### 2. Good prompt

```md
# Persona
You are a Procurement Lead reviewing the attached proposal for a new vendor/tool.

# Context
I’m sharing a draft memo. Your job is to pressure-test it before it goes to leadership.

# What to do
- Identify what’s unclear, risky, or missing for procurement approval
- Call out likely blockers (security, data handling, pricing, implementation, vendor lock-in)
- Suggest the top changes to make this memo procurement-ready

# Output format
1) 5 bullet critique (most important issues first)  
2) A “questions procurement will ask” list (8–12 questions)  

# Memo
[paste memo here or attach as file]
```

#### 3. Excellent prompt
```md
# Persona
You are a seasoned Procurement Lead at a 1,000–10,000 employee company. You protect the business from vendor risk, unclear scope, and hidden costs while enabling teams to move fast when the case is strong.

# Goal
Review the memo below as if it’s headed to an exec approval meeting. Pressure-test it for procurement readiness: cost clarity, implementation realism, legal/security risk, and negotiation posture.

# How to behave
- Be direct, specific, and skeptical—but fair.
- If the memo lacks needed info, propose the exact missing content and where it should go.

# What to focus on (non-negotiable)
## Commercials / pricing
- Pricing model (seats/usage/tier), expected year-1 cost, renewal risk
- Hidden costs (implementation, training, admin overhead, integrations)
- Term flexibility (pilot, ramp, opt-out, true-ups)

## Risk & compliance
- Data types involved, data retention/deletion, sub-processors
- Security requirements (SSO/SAML, RBAC, audit logs, encryption)
- Regulatory/contract risks (DPAs, SLAs, liability caps)

## Implementation & adoption
- Realistic timeline, owners, dependencies, change management
- Support model (who administers, who supports users)
- Success metrics and how they’ll be measured

## Vendor viability & lock-in
- Exit plan, portability of data, migration costs
- Roadmap dependency risk, vendor support quality

# Output format (NON-NEGOTIABLE)
1) **Procurement Verdict**: Approve / Approve with conditions / Block (1 line)  
2) **Top 7 issues** (bullets): each must include *why it matters* + *how to fix*  
3) **Negotiation asks** (table): Ask | Rationale | “Fallback if they refuse”  
4) **Due diligence checklist** (max 12 bullets): what we must confirm before signing  
5) **Missing information**: exact sections/lines you’d add to the memo (copy/paste-ready)  
6) **Questions for the business owner** (max 10): the highest-leverage clarifications

# Memo
[paste memo here or attach as file]
```

### 4. Research for… (Deep Research)

#### 1. Okay prompt
```md
Research the best East Coast cities for a first showroom for a mid-sized California D2C furniture brand. Compare the top markets on market opportunity, channels/distribution, costs/complexity, and strategic considerations, and include an executive summary with sources.
```

#### 2. Good prompt
```md
# Context
I’m building a market entry strategy for a mid-sized California D2C furniture brand considering its **first East Coast showroom**. We haven’t chosen a city yet.

# Task
Identify and compare the **best 5–7 East Coast cities** for a first showroom. Prioritize an objective view of **opportunity vs. complexity**.

# What “good” looks like
- For each city, cover the key factors below with **sources for major numbers and claims**
- End with a **comparison table** and a **top-2 recommendation**

# What to cover (per city)
1) **Market opportunity**
- Furniture demand signals
- Competitive landscape

2) **Channel & distribution**
- Major channels (e-comm + retail) and how customers discover/buy
- Logistics considerations

3) **Cost & complexity**
- Real estate / operating cost considerations for a showroom

# Output format
- Executive summary (8–12 bullets)
- City-by-city sections
- Final comparison table + recommended top 2 cities (with rationale)
```

#### 3. Excellent prompt

```md
# Decision goal
We must pick **one** city to open the first East Coast showroom for our mid-sized D2C furniture brand. Produce a recommendation that is **auditably sourced** and **directly comparable across cities**.

# Context
- Brand: mid-sized D2C furniture, California-based
- Showroom role: drive **brand trust + conversion lift**, not just revenue in-store
- Constraints: we can realistically support **one** launch market with a small team

# Task
1) Build a shortlist of **6 cities** (East Coast)  
2) Score each city using the rubric below  
3) Recommend **top 1** (plus a backup) with explicit tradeoffs and assumptions

# Rubric (use this exact weighting)
Score each city **1–5** (5 = best). Provide a short justification + citation(s).
- **Market pull (35%)**: demand proxy strength, target customer density, growth signals
- **Showroom economics (25%)**: rent ranges, staffing costs, expected operating burden
- **Delivery feasibility (15%)**: last-mile constraints, service expectations, return complexity
- **Competitive intensity (25%)**: concentration of strong incumbents + differentiation room

# Evidence rules
- For any numeric claim, include **source + date**. Prefer data from the last **24 months**.
- If a metric is unavailable, use a **proxy** (and label it clearly as a proxy).
- Call out **key uncertainties** and how they could change the ranking.

# City sections
For each city:
- 3–5 bullets “why it wins / why it loses”
- Key metrics table (only the metrics you used for scoring)
- Notes on major assumptions / proxies

# Output format
1) Executive summary (10 bullets max)  
2) Scored ranking table (with weighted totals)  
3) City writeups
4) Final recommendation
5) Sources
```