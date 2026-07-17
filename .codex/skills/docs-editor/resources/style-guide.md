# Developer documentation style rules

_Based on the Microsoft Style Guide._

This document is a **review + rewrite checklist** optimized for consistent wording, capitalization, UI verbs, list/step structure, formatting patterns, and conventions.

## Scope and intent

- Write for developers and technical users: assume **general programming knowledge** and focus on **product- or technology-specific** guidance that helps readers accomplish goals.
- Prefer content that is **task- and outcome-oriented**: what the reader can do and what happens when they do it.
- Treat **reference documentation and code examples** as first-class documentation artifacts.

---

## Voice and tone rules

### Get to the point

- Put the **key takeaway first**. Lead with the action/outcome the reader wants.
- Keep intros short; avoid long warmups before any actionable content.

### Sound human (not casual, not corporate)

- Use short, everyday words.
- Use contractions when they improve flow.
- Avoid unnecessary formality and inflated language.

### Keep it simple

- Prefer shorter sentences and paragraphs.
- Break complex ideas into steps, lists, or layered explanations.
- Remove filler and repeated information.

---

## Scannability and structure

- Put the most important information **near the top**.
- Use headings, lists, and tables to make content **scan-first**.
- Keep paragraphs short (rule of thumb: **3–7 lines**). Single-line paragraphs are okay occasionally.
- Keep formatting consistent within a section (especially for UI labels and procedures).
- Use parallel sentence structure in comparisons, lists, and sibling headings.

---

## Headings

### What headings should do

- Keep headings short and **front-load the key idea**.
- Prefer headings about **what the reader can do**, not internal feature names.
- Avoid consecutive headings with no text between them.
- Use parallel structure at the same heading level.

Recommended heading patterns by level:

- Top-level: **noun phrases** (topic labels)
- Second-level: **verb phrases** (actions within the topic)
- Task/procedure headings: **infinitive phrases** (“To …”)

### Heading formatting

- Use **sentence-style capitalization** for headings and titles:
  - Capitalize the first word; lowercase the rest except proper nouns.
- Don’t end headings with a period. Use question marks only when needed.
- Avoid `&` and `+` unless they are literal UI text or space is extremely constrained.
- Avoid hyphens in headings when you can rewrite.
- Use **“vs.”** (not “v.” or “versus”).

---

## Lists

### Choose the right list type

- Use **bullets** for items in no particular order.
- Use **numbers** for sequences, procedures, rankings, or priority.

### Introduce lists correctly

Use one of:

- A heading, or
- A complete sentence, or
- A fragment ending with a colon.

Avoid list-intros that must be “completed” by the list items (harder to translate and easier to mispunctuate).

### Capitalization and punctuation in list items

- Start each item with a capital letter unless it must be lowercase (e.g., a command).
- Don’t end items with semicolons, commas, or conjunctions (“and/or”).
- Don’t end items with periods unless items are complete sentences.
- If a fragment + colon intro makes list items read as full sentences when combined, use periods on **all** items.
  - Exception: don’t add periods if all items are **three or fewer words** or if items are **UI labels/strings/headings**.

---

## Procedures and step-by-step instructions

### Structure and consistency

- Use a numbered list for multi-step procedures.
- Use a procedure heading that states what the reader will accomplish.
- Use one numbered entry per step (combine only very short actions that occur in the same place).
- Include “finalize” actions (like selecting **OK**/**Apply**) when they matter.
- Use **imperative verbs** and complete sentences.
- Keep steps consistent:
  - Use a location phrase only when needed (“On the …, …”).
  - Otherwise start with a verb.

### Formatting rules

- Capitalize the first word in each step.
- End each step with a period.
  - Exception: if a step is _only_ user input that must not include punctuation, put the input on its own line and don’t force a period into the input.
- Keep procedures short: aim for **7 steps or fewer** (prefer fewer); try to fit on one screen.

### Single-step procedures

- If your docs consistently use “steps,” keep the same structure but use a **bullet** for single-step instructions.

---

## Describing interactions with UI

### Prefer input-neutral verbs

Avoid input-specific verbs (mouse/touch dependent). Prefer verbs that work across input methods.

Preferred verb patterns:

- **Open**: apps, files, folders, panels (not typically commands/menus).
- **Close**: apps, dialogs, tabs, panels.
- **Go to**: locations in UI, pages, tabs, websites.
- **Select**: buttons, checkboxes, menu items, links, list values, and keys/shortcuts.
- **Choose**: selecting among options based on preference/outcome.
- **Clear**: removing a checkbox selection.
- **Turn on / Turn off / Switch**: toggles.
- **Select and hold (or right-click)**: when both interaction modes are relevant.

### UI path shorthand using `>`

Use `>` to abbreviate simple sequences when:

- The path is obvious, and
- The interaction method is consistent across steps.

Formatting rules:

- Use spaces around the symbol: `A > B > C`
- Don’t bold the `>`.

---

## Formatting conventions in instructions

General rule: focus on actions; avoid unnecessary UI-element jargon. When you must name UI text, follow consistent formatting rules.

### UI labels and elements (procedures)

- **Bold** literal UI names when the reader must interact with them (buttons, menu items, toggles, dialog names, panel names).
- Don’t include element types (“button”, “menu”, “pane”, “panel”) unless it clarifies meaning.
- If a UI label ends with a colon or ellipsis, omit that punctuation when writing instructions.

Examples:

- Prefer: Select **Save as**
- Avoid: Click the **Save as…** button

### Commands and command-line

- Use `code style` for command-line commands and anything the reader must type verbatim.
- Use `code style` for options/switches/flags; match required capitalization exactly.

### Dialogs

- Refer to them as “dialog” (avoid “dialog box” and “pop-up window”).
- Bold dialog names when referenced as literal UI text.

### Error messages

- Use sentence-style capitalization.
- When referencing an error message in prose, put it in **quotation marks**.

### plaintext vs. plain text

- Use **plaintext** when describing data that is stored or transmitted without encryption or encoding (for example, "stored in a plaintext file").
- Use **plain text** when describing formatting or rich-text behavior (for example, "enter plain text").

### Files, folders, extensions, attributes

- File attributes: lowercase.
- File extensions: lowercase (e.g., `.json`, `.yaml`).
- File/folder names:
  - Use `code style` when used as code or literal paths.
  - In procedures, bold file/folder names when the reader must select or enter them.

### Keys and keyboard shortcuts

- Bold key names and shortcuts in instructions.
- No spaces around plus signs in shortcuts (e.g., `Ctrl+Alt+Del`).

### Placeholders, strings, URLs, user input

- Placeholders:
  - Use italics for placeholder UI text when needed.
  - Use angle brackets for code placeholders when they aren’t part of the language syntax: `<placeholder>`.
- Slashes:
  - If the reader must type a slash, name it and show the symbol: “enter a backslash (`\`)”.
- Strings:
  - Use sentence-style capitalization unless the literal text differs.
  - Use `code style` for literal strings used in code.
- URLs:
  - Use lowercase for complete URLs.
  - Don’t hyphenate URLs; line-break before a slash when possible.
- User input:
  - Use lowercase unless case-sensitive.
  - Don’t italicize user input unless it’s a placeholder.

---

## Developer text elements: what to format as code

Use `code style` (inline code or fenced blocks) for programmatic elements, including:

- Class, method, function, parameter, and member names
- Keywords and tokens
- Markup tags
- Commands, flags, and environment variables
- File paths and code identifiers

Capitalization:

- Match the language/environment conventions.
- Match exact casing when the reader must type it.

---

## Reference documentation rules

Enforce consistency: predictable structure helps readers quickly find what they need.

### Reference article titles

- Title format: `ElementName` + element type (e.g., “Thing method”, “Thing class”).
- If names collide, add a differentiator (parent element, technology name) for clarity in navigation and search.

### Reference article content checklist

Include sections as applicable:

- **Title and description**: concise description of what the element does; don’t just repeat the element name.
- **Syntax/Declaration**: signature(s); per-language syntax where relevant.
- **Parameters**: for each parameter, include type and meaningful behavioral detail; don’t just restate name/type.
- **Return value**: describe the type and meaning; for booleans, define the condition.
- **Remarks**: behavior, edge cases, comparisons, pitfalls.
- **Example**: a practical usage example (see next section).
- **Requirements / Applies to**: platform/language requirements.
- **See also**: related elements.

---

## Code examples rules

Code examples are often copy/pasted, so make them usable and meaningful.

### Planning examples

- Prefer concise examples for key tasks.
- Start with simple, common scenarios; add complexity later.
- Prioritize frequently used or tricky elements.
- Avoid contrived examples that illustrate obvious points.

### Writing examples

- Add a short intro describing the scenario.
- List prerequisites/dependencies needed to run the code.
- Make it easy to copy and run.
- Use comments to explain non-obvious parts (don’t narrate the code line-by-line).
- Show expected output when output matters.
- Prefer secure patterns: don’t hard-code secrets; validate input.
- Include exception handling only when it’s intrinsic to the concept being demonstrated.
- Ensure examples are tested and correct.

---

## Capitalization

Default to **sentence-style capitalization** in headings, titles, UI labels, and standalone phrases:

- Capitalize the first word.
- Capitalize proper nouns.
- Lowercase everything else.

Avoid:

- ALL CAPS for emphasis.
- Internal capitalization unless it’s part of a proper name.

Colon rule:

- In titles/headings with a colon, capitalize the first word after the colon.

---

## Bias-free and inclusive language (lintable word rules)

### Gender-neutral language

Replace gendered job titles and generic gendered phrasing with neutral alternatives.

Examples (non-exhaustive):

- chairman → chair, moderator
- mankind/man → humanity, people
- salesman → sales representative
- manmade → synthetic, manufactured
- manpower → workforce, staff, personnel

### Pronouns in generic references

Avoid “he/him” and “she/her” for generic references. Prefer:

- “you”
- plural nouns/pronouns
- “the” + noun (“the user”, “the admin”)
- role terms (“reader”, “customer”, “developer”)

Singular “they” is acceptable when needed. Avoid “he/she” or “s/he”.

### Avoid biased or loaded terms

Replace terms with problematic historical or militaristic associations or common biased usage.
Examples:

- master/slave → primary/secondary, primary/subordinate
- demilitarized zone (DMZ) → perimeter network
- hang (in computing sense) → stop responding

### Disability language

- Focus on people, not disabilities.
- Avoid pity language (“suffering from”).
- Don’t mention disability unless relevant.

---

## Fast agent workflow checklist

1. **Developer fit**: remove basics; focus on product/tech-specific tasks and details.
2. **Scannability**: shorten intro, headings, paragraphs; add lists/steps for scannability.
3. **Headings**: sentence case; no periods; parallel structure; avoid `&/+/-`; use `vs.`
4. **Lists**: correct list type; clean intros; consistent punctuation/capitalization.
5. **Procedures**: imperative steps; correct UI verbs; <=7 steps; step punctuation rules.
6. **UI formatting**: bold UI labels; omit element-type words unless needed; drop label colons/ellipses.
7. **Developer formatting**: `code style` for identifiers/commands; lowercase extensions/URLs; quote error messages; shortcut formatting.
8. **Inclusive language**: neutral terms; avoid generic he/she; avoid loaded terminology.
9. **Reference + examples**: ensure required sections and non-contrived, runnable examples; ensure secure patterns.
