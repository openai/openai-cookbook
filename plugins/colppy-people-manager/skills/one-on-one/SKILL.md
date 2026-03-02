---
name: one-on-one
description: CEO coaching tool for 1:1s with direct reports. Log sessions from Fellow/Granola transcripts or documents, track leadership development over quarters, generate feedforward evaluations, and reflect on your own growth as a leader. Use when the user says "log my 1:1", "evaluate", "feedforward", or asks about a direct report.
---

# One-on-One Coaching

CEO-level coaching system for developing a leadership team and tracking your own growth as a leader.

**Transcript-first:** Primary input is Fellow or Granola MCP. Also accepts pasted notes, PDFs, slides, or documents prepared by the direct report.

**All data lives in:** `plugins/colppy-people-manager/data/`
- `_self/` — your own development as a leader
- `<person-slug>/` — each direct report (e.g. `ana-gomez`, `martin-lopez`)

---

## Detect operating mode

| User says | Mode |
|-----------|------|
| "Log my 1:1 with Ana" / "Process this transcript" / "Add this doc from Martin" | **A — Session** |
| "Evaluate Ana" / "Feedforward for Martin" / "I need to review Pedro" | **B — Evaluation** |
| "Where is Ana?" / "What patterns do I see?" / "What was Martin like in Q4?" | **C — Query / Coach** |

---

## MODE A — Session Logging

Handles both **1:1 sessions** and **group calls** (3–8 participants). The same blueprint runs for both — the difference is detected in Step 1 and determines whether one or N session files are written.

### [D] Step 1: Detect session type and identify participants

Read the transcript header or speaker labels (Fellow and Granola label speakers by name automatically).

**Count distinct speakers** (excluding yourself):
- **1 speaker** → 1:1 mode. Proceed with that one person.
- **2+ speakers** → Group call mode. List all participants found.

For each participant, derive their slug:

- Take firstname-lastname, lowercase, hyphens between words
- Remove diacritics: á→a, é→e, í→i, ó→o, ú→u, ñ→n, ü→u
- Keep only alphanumeric characters and hyphens
- Examples: Ana Gómez → `ana-gomez`, María José García López → `maria-jose-garcia-lopez`

If ambiguous (only first name, initials, or unusual formatting): do NOT guess. Ask: "How should I format [Name]'s folder slug? (e.g., `pedro-silva`)"

If **any participant has no folder** in `data/`: note them, offer to create — "I found [Name] in the transcript but no folder exists. Create one now?"

### [D] Step 2: Hydrate context — ALWAYS DO THIS FIRST

Read for **every participant** before doing any extraction:
- `plugins/colppy-people-manager/data/<slug>/profile.md`
- `plugins/colppy-people-manager/data/<slug>/summary.md`

Also read once (applies to all):
- `plugins/colppy-people-manager/data/_self/summary.md`

If a person folder doesn't exist and the user confirmed creation:

1. Create `data/<slug>/`
2. Copy these 4 files from `data/_template/`: `profile.md`, `summary.md`, `coaching_arc.md`, `action_items.md`
3. In each file, replace every occurrence of `<Full Name>` with the person's actual full name

### [D] Step 3: Accept input

Try in this order:
1. **Fellow MCP** — use `mcp__claude_ai_Fellow_ai__search_meetings` to find the meeting, then `mcp__claude_ai_Fellow_ai__get_meeting_transcript`
2. **Granola MCP** — use `mcp__claude_ai_Granola__query_granola_meetings` or `mcp__claude_ai_Granola__list_meetings`
3. **Pasted text** — user pasted transcript or notes directly
4. **Attached file** — PDF, image, slides (Claude reads natively)

If the document origin is **clear** (user says "Ana prepared this", "from Martin", "his self-assessment", "her plan"):
Flag it: _"self-reported from [Name]: weight as their own voice and perception, not external observation."_

If the document origin is **unclear**: Ask before extracting — "Did [Name] prepare this document, or is it external feedback about them?"

Multiple inputs can be combined (e.g. transcript + attached self-assessment from one person).

### [A] Step 4: Extract coaching signals — per person

Run this extraction **once per participant**. For group calls: loop through each person.

**Leadership signals** — how they lead. In a 1:1: how they communicate, give feedback, handle conflict, build their team. In a group call: how they show up with peers — vocal vs. silent, how they handle disagreement, whether they build on others' ideas or stay isolated, how they respond to challenge.

**Execution signals** — how they deliver. Ownership depth, accountability, decision quality under pressure, stakeholder management, follow-through on commitments.

**Group dynamics signals** (group calls only) — how they interact with specific peers. Who they align with, who they challenge, who they ignore. Patterns across the group that reveal something about their leadership style not visible in 1:1s.

**Growth vs last session** — compare against that person's current `summary.md`:
- What concretely moved? (evidence required)
- What's still stuck? (name what was tried before)

**Coaching intervention:**

- In a **1:1**: Describe the specific frame or approach used. What you tried. What happened. Be concrete.
- In a **group call**: Write `—` for this field unless you directly addressed one person publicly in the meeting (not in a later side conversation). If you did address someone publicly, note it briefly.

**Self-reflection** (once for the whole session, not per person) — what you noticed about yourself. In a group call: how you facilitated, who you gave airtime to, who you ignored, how you handled tension. In a 1:1: what you did well and what you'd do differently as their coach.

### [D] Step 5: Write session files — one per participant

Path per person: `plugins/colppy-people-manager/data/<slug>/history/<YYYY-QN>/<YYYY-MM-DD>.md`

Quarter format: `2026-Q1`, `2025-Q4`, etc. Quarter is determined by the **session date** (not the content discussed):

- Jan 1–Mar 31 → Q1 | Apr 1–Jun 30 → Q2 | Jul 1–Sep 30 → Q3 | Oct 1–Dec 31 → Q4

Example: Session on 2026-03-25 → file under `2026-Q1/` even if reviewing Q4 2025 performance.

**Always write all files. Do not skip any participant even if signals were weak.**

Session file format:

```
# YYYY-MM-DD — <Full Name>
_Source: [Fellow | Granola | pasted | attached] | [1:1 | Group call — N participants: Name1, Name2, ...]_
_[+ self-prepared doc: TITLE]_

## Leadership signals
- [Specific observation with evidence — quote or describe the moment]

## Execution signals
- [Specific observation with evidence]

## Group dynamics (group calls only — omit for 1:1s)
- [How they showed up with peers — specific interactions, patterns]

## Growth vs last session
- Progress: [what moved, with concrete evidence]
- Stuck: [what didn't, and what was previously tried]

## Coaching intervention this session
[1:1 only: what frame or approach was used, what happened. For group calls: write "—" unless you directly coached this person in the group.]

## Self-reflection (me as their coach)
[What I noticed about my own coaching/leadership relevant to this person in this session.]
```

### [D] Step 6: Write self-reflection entry

Path: `plugins/colppy-people-manager/data/_self/history/<YYYY-QN>/<YYYY-MM-DD>.md`

One entry for the whole session — written once, even if it was a group call.
If a file already exists for this date (multiple sessions in one day), **append** — do not overwrite.

Self-reflection file format:

```
# YYYY-MM-DD — Self-reflection
_[1:1 with NAME | Group call with: Name1, Name2, ...]_

## What I noticed about my own leadership
[How I showed up. In group calls: facilitation, airtime distribution, how I handled tension, who I centered and who I left out.]

## Connection to my development areas
[How this connects to themes in _self/profile.md — 360, CEO feedback, personal history. If no clear connection, write "—".]
```

### [A] Step 7: Rewrite each person's summary.md

Run once per participant. Incorporate their session signals. Rewrite the whole file — do not append.
**Target: under 700 words.** Update "Last updated" date.

Seven sections, all required:
1. **Leadership Profile** — current strengths and development areas as a leader
2. **Execution Profile** — how they deliver, accountability patterns
3. **Active Coaching Themes** — the 2-3 things being actively worked on now
4. **Growth Arc (this quarter)** — what's moving (with evidence), what's stuck
5. **My Coaching Approach** — what's working, what you need to adjust as their leader
6. **Watch Items** — early signals, blind spots, questions to probe next session
7. **Materials on file** — any PDFs/docs incorporated, with dates

### [A] Step 8: Update _self/summary.md

Incorporate the self-reflection from this session. Rewrite — do not append.
Target: under 700 words. Update "Last updated" date.

### [D] Step 9: Update action_items.md per person

For each participant: mark items done if mentioned in transcript (add ✓ + date), add new ones.

### [A] Step 10: Surface coaching observations

**For 1:1s:** 1-2 specific observations to act on before next session with that person.

**For group calls:** Do NOT write per-person coaching observations. Instead surface:

1. Group dynamic (1-2 observations): patterns in how the group interacted, power dynamics, who dominated or went silent, unresolved tension
2. Your facilitation (1 observation): what you did well and one thing to try differently next time

Add these observations at the end of the self-reflection entry in `_self/history/`, not in individual participant files.

Example: "Martin went silent every time Ana made a strong assertion — worth exploring privately whether that's deference or conflict avoidance. Facilitation: you resolved tension before it developed each time — experiment with letting it sit next time."

### Mode A — Completion checklist

Before closing a session, confirm ALL steps are done:

- [ ] Step 1: Detected session type and identified all participants
- [ ] Step 2: Hydrated context (profile.md + summary.md read for each person)
- [ ] Step 3: Accepted and labeled all inputs (transcripts, docs, flags self-reported if applicable)
- [ ] Step 4: Extracted coaching signals per person
- [ ] Step 5: Wrote session file(s) — one per participant
- [ ] Step 6: Wrote self-reflection entry to `_self/history/`
- [ ] Step 7: Rewrote each person's `summary.md` (all 7 sections, under 700 words)
- [ ] Step 8: Updated `_self/summary.md`
- [ ] Step 9: Updated `action_items.md` per person
- [ ] Step 10: Surfaced coaching observations

**Do not consider the session logged until all 10 steps are complete.**

---

## MODE B — Evaluation / Feedforward

Can be triggered **anytime** — not gated to quarter boundaries.

### [D] Step 1: Identify person and period
Ask if ambiguous: "Which period should this cover? (default: all available history)"

### [D] Step 2: Load full context
Read ALL of:
- `data/<slug>/profile.md`
- `data/<slug>/summary.md`
- `data/<slug>/coaching_arc.md`
- All `data/<slug>/history/<Q>/*.md` files for the period (skip `evaluations/` subfolder)

### [A] Step 3: Synthesize patterns
Across all sessions, identify:
- Consistent leadership strengths (appear repeatedly, across different contexts)
- Persistent development gaps (despite coaching — note what was tried and what happened)
- Growth trajectory: direction and velocity of change
- Your own coaching effectiveness with this person

### [A] Step 4: Generate feedforward document

Feedforward file format:

```
# <Full Name> — Feedforward
_Generated: YYYY-MM-DD | Period: YYYY-QN → YYYY-QN | Based on N sessions_

## Leadership assessment
[Pattern across sessions — how they lead. Evidence-based, specific. Not a list of sessions — a synthesis of what the pattern reveals about them as a leader.]

## Execution assessment
[How they deliver. Consistency, ownership depth, accountability. Specific examples.]

## Growth: what moved
[Concrete evidence of development across the period. "By Q1, she was..." not "she improved."]

## Growth: what's stuck
[Persistent patterns despite coaching. Name the interventions tried and what happened each time.]

## Coaching plan going forward
[Specific focus areas. Approaches to try. What to stop doing with this person.]

## My own contribution as their coach
[Where my coaching helped this person grow. Where I need to adjust.]
```

### [D] Step 5: Save feedforward
Path: `data/<slug>/history/evaluations/<YYYY-MM-DD>-feedforward.md`

Note: `evaluations/` is a **subfolder inside `history/`** — not a sibling. Full path example:
`data/ana-gomez/history/evaluations/2026-03-02-feedforward.md`

Create the `evaluations/` directory if it doesn't exist.

### [A] Step 6: Rewrite coaching_arc.md
Target ~1500 words. Update the longitudinal story to incorporate evaluation findings:
- Quarter-by-quarter headline
- Coaching approaches tried and outcomes
- Breakthrough moments and regression patterns
- Evolution of your coaching relationship

### [A] Step 7: Surface
What does this evaluation reveal about your own coaching of this person? Connect to `_self/profile.md`.

---

## MODE C — Query / Coaching

### [D] Step 1: Identify scope and load selectively
- Current state of one person → read `summary.md` only
- Historical range → read `history/<Q>/` files for that range
- Long-term arc → read `coaching_arc.md`
- Team-wide patterns → read all `summary.md` files across `data/`

### [A] Step 2: Answer / synthesize / coach
Think like a coaching partner. Surface patterns. Push back when useful. Ask questions back when the user needs to think something through, not just retrieve information.

---

## Adding a new person

When the user says "Add [name] as a new direct report":
1. Create `data/<slug>/` (e.g. `data/carolina-diaz/`)
2. Copy all 4 files from `data/_template/`
3. Replace `<Full Name>` placeholder with their actual name in each file
4. Fill in `profile.md` with any context provided by the user
5. Confirm: "Created data/<slug>/. Add their current quarter context to profile.md before the first session."

---

## Example prompts

```
"Log my 1:1 with Ana from today"
"Process the transcript from my meeting with Martin"
"Add this self-assessment from Pedro" [attach PDF]
"Evaluate Ana — give me a feedforward"
"I need to do a feedforward for Martin for his performance review"
"Where is Ana this quarter?"
"What patterns do I see across my whole team?"
"Where was Pedro in Q4 2025?"
"What does my 360 say I should work on, and how is that showing up in my sessions?"
"Add Carolina Díaz — Head of Product, joined Q4 2025"
```
