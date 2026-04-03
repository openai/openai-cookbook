"""Image generation eval harness runner.

Two example use cases:
- UI mockups (mobile checkout screen)
- Marketing flyers (coffee shop promotion)

Run:
  python generation_harness/run_imagegen_evals.py
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.reporting import default_run_id, save_results
from vision_harness.evaluate import evaluate
from vision_harness.graders import (
    LLMajRubricGrader,
    build_generation_judge_content,
)
from vision_harness.io import image_to_data_url
from vision_harness.storage import OutputStore
from vision_harness.types import ModelRun, Score, TestCase

DEFAULT_RESULTS_DIR = ROOT_DIR / "generation_harness" / "results"
DEFAULT_MODEL = "gpt-image-1.5"
DEFAULT_JUDGE_MODEL = "gpt-5.2"
DEFAULT_IMAGE_SIZE = "1024x1024"

UI_JUDGE_PROMPT = """<core_mission>
Evaluate whether a generated UI mockup image represents a usable mobile checkout screen by checking screen type fidelity, layout/hierarchy, in-image text rendering, and UI affordance clarity.
</core_mission>

<role>
You are an expert evaluator of UI mockups used by designers and engineers. You care about structural correctness, readable UI text, clear hierarchy, and realistic rendering of UI elements.
</role>

<scope_constraints>
- Judge only against the provided instructions.
- Be strict about required UI elements and exact button/link text.
- Do NOT infer intent beyond what is explicitly stated.
- Do NOT reward creativity that violates constraints.
- Missing or extra required components are serious errors.
- If the UI intent or function is unclear, score conservatively.
</scope_constraints>

<metrics>
1) instruction_following: PASS/FAIL
2) layout_hierarchy: 0–5
3) in_image_text_rendering: PASS/FAIL
4) ui_affordance_rendering: 0–5
</metrics>

Evaluate EACH metric independently using the definitions below.
--------------------------------
1) Instruction Following (PASS / FAIL)
--------------------------------
PASS if:
- All required components are present.
- No unrequested components or features are added.
- The screen matches the requested type and product context.

FAIL if:
- Any required component is missing.
- Any unrequested component materially alters the UI.
- The screen does not match the requested type.

--------------------------------
2) Layout and Hierarchy (0–5)
--------------------------------
5: Layout is clear, coherent, and immediately usable.
   Hierarchy, grouping, spacing, and alignment are strong.

3: Generally understandable, but one notable hierarchy or layout issue
   that would require iteration.

0-2: Layout problems materially hinder usability or comprehension.

--------------------------------
3) In-Image Text Rendering (PASS / FAIL)
--------------------------------
PASS if:
- Text is readable, correctly spelled, and sensibly labeled.
- Font sizes reflect hierarchy (headings vs labels vs helper text).

FAIL if:
- Any critical text is unreadable, cut off, misspelled, or distorted.

--------------------------------
4) UI Affordance Rendering (0–5)
--------------------------------
5: Clearly resembles a real product interface that designers could use.

3: Marginally plausible; intent is visible but execution is weak.

0-2: Poor realism; interface would be difficult to use in practice.

<verdict_rules>
- Instruction Following must PASS.
- In-Image Text Rendering must PASS.
- Layout and Hierarchy score must be ≥ 3.
- UI Affordance Rendering score must be ≥ 3.

If ANY rule fails, the overall verdict is FAIL.
Do not average scores to determine the verdict.
</verdict_rules>

<output_constraints>
Return JSON only.
No extra text.
</output_constraints>
"""

MARKETING_JUDGE_PROMPT = """<core_mission>
Evaluate whether a generated marketing flyer is usable for a real coffee shop
promotion by checking instruction adherence, exact text correctness, layout clarity,
style fit, and artifact severity.
</core_mission>

<role>
You are an expert evaluator of marketing design deliverables.
You care about correctness, readability, hierarchy, and brand-fit.
You do NOT reward creativity that violates constraints.
</role>

<scope_constraints>
- Judge ONLY against the provided prompt and criteria.
- Be strict about required copy: spelling, punctuation, casing, and symbols must match exactly.
- Extra or missing text is a serious error.
- If unsure, score conservatively (lower score).
</scope_constraints>

<metrics>
1) instruction_following: PASS/FAIL
2) text_rendering: PASS/FAIL
3) layout_hierarchy: 0-5
4) style_brand_fit: 0-5
5) visual_quality: 0-5

Use these anchors:
Layout/Hierarchy 5 = instantly readable; clear order; strong spacing/alignment.
3 = understandable but needs iteration (one clear issue).
0-2 = confusing or hard to parse.

Style/Brand Fit 5 = clearly matches requested vibe; consistent; not off-style.
3 = generally matches but with noticeable mismatch.
0-2 = wrong style (e.g. cartoonish when photo-real requested).

Visual Quality 5 = clean; no distracting artifacts; hero image coherent.
3 = minor artifacts but still usable.
0-2 = obvious artifacts or distortions that break usability.
</metrics>

<verdict_rules>
Overall verdict is FAIL if:
- instruction_following is FAIL, OR
- text_rendering is FAIL, OR
- any of layout_hierarchy/style_brand_fit/visual_quality is < 3.
Otherwise PASS.
</verdict_rules>

<output_constraints>
Return JSON only.
No extra text.
</output_constraints>
"""

UI_PROMPT = """Generate a high-fidelity mobile checkout screen for an ecommerce app.
Orientation: portrait.
Screen type: checkout / order review.
Use the REQUIRED TEXT:
- Checkout
- Place Order
- Edit Cart
Constraints:
- Order total appears directly above the primary CTA.
- Primary CTA is the most visually prominent element.
- Do not include popups, ads, marketing copy, or extra screens.
- Do not include placeholder or lorem ipsum text.
"""

UI_CRITERIA = """The image clearly depicts a mobile checkout screen.
All required sections are present and visually distinct.
UI elements look clickable/editable and follow common conventions.
Primary vs secondary actions are unambiguous.
No extra UI states, decorative noise, or placeholder text."""

COFFEE_PROMPT = """Create a print-ready vertical A4 flyer for a coffee shop called Sunrise Coffee.
Use a warm, cozy, minimal specialty coffee aesthetic (not cartoonish).
Required text (must be exact):
- WINTER LATTE WEEK
- Try our Cinnamon Oat Latte
- 20% OFF - Mon-Thu
- Order Ahead
- 123 Market St - 7am-6pm
Do not include any other words, prices, URLs, or QR codes.
"""

COFFEE_CRITERIA = """All required text appears exactly as written and is legible.
Layout reads clearly: shop name -> headline -> subheadline -> offer -> CTA -> footer.
Style matches warm, cozy, specialty coffee and is not cartoonish.
No extra text, watermarks, or irrelevant UI-like elements."""

UI_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "instruction_following": {"type": "boolean"},
        "layout_hierarchy": {"type": "number"},
        "in_image_text_rendering": {"type": "boolean"},
        "ui_affordance_rendering": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": [
        "verdict",
        "instruction_following",
        "layout_hierarchy",
        "in_image_text_rendering",
        "ui_affordance_rendering",
        "reason",
    ],
    "additionalProperties": False,
}

MARKETING_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "instruction_following": {"type": "boolean"},
        "text_rendering": {"type": "boolean"},
        "layout_hierarchy": {"type": "number"},
        "style_brand_fit": {"type": "number"},
        "visual_quality": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": [
        "verdict",
        "instruction_following",
        "text_rendering",
        "layout_hierarchy",
        "style_brand_fit",
        "visual_quality",
        "reason",
    ],
    "additionalProperties": False,
}

REQUIRED_TEXT = {
    "WINTER LATTE WEEK",
    "Try our Cinnamon Oat Latte",
    "20% OFF • Mon–Thu",
    "Order Ahead",
    "123 Market St • 7am–6pm",
}


def parse_ui_result(data: dict, base_key: str) -> list[Score]:
    return [
        Score(key="instruction_following", value=bool(data["instruction_following"]), reason=""),
        Score(key="layout_hierarchy", value=float(data["layout_hierarchy"]), reason=""),
        Score(key="in_image_text_rendering", value=bool(data["in_image_text_rendering"]), reason=""),
        Score(key="ui_affordance_rendering", value=float(data["ui_affordance_rendering"]), reason=""),
        Score(key="verdict", value=str(data["verdict"]), reason=(data.get("reason") or "").strip()),
    ]


def parse_marketing_result(data: dict, base_key: str) -> list[Score]:
    return [
        Score(key="instruction_following", value=bool(data["instruction_following"]), reason=""),
        Score(key="text_rendering", value=bool(data["text_rendering"]), reason=""),
        Score(key="layout_hierarchy", value=float(data["layout_hierarchy"]), reason=""),
        Score(key="style_brand_fit", value=float(data["style_brand_fit"]), reason=""),
        Score(key="visual_quality", value=float(data["visual_quality"]), reason=""),
        Score(key="verdict", value=str(data["verdict"]), reason=(data.get("reason") or "").strip()),
    ]


def extract_text_from_flyer(image_path: str | Path, model: str) -> list[str]:
    client = OpenAI()
    image_url = image_to_data_url(Path(image_path))

    instructions = (
        "List every piece of text visible in this flyer image. "
        "Return one line per text item and preserve capitalization, punctuation, and spacing exactly."
    )

    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": image_url},
                ],
            }
        ],
    )

    return [line.strip() for line in (response.output_text or "").splitlines() if line.strip()]


def add_ocr_text_check(result: dict[str, Any], model: str) -> None:
    coffee_image_path = Path(result["artifact_paths"][0])
    extracted_lines = extract_text_from_flyer(coffee_image_path, model=model)

    missing = sorted(REQUIRED_TEXT - set(extracted_lines))
    extra = sorted(set(extracted_lines) - REQUIRED_TEXT)
    text_rendering_pass = not missing and not extra

    parts = []
    if missing:
        parts.append("missing: " + ", ".join(missing))
    if extra:
        parts.append("extra: " + ", ".join(extra))
    text_rendering_reason = "; ".join(parts) if parts else "Exact text match."

    text_rendering_judge_score = result["scores"].get("text_rendering")
    text_rendering_judge_reason = result["reasons"].get("text_rendering", "")

    result["scores"]["text_rendering_judge"] = text_rendering_judge_score
    result["reasons"]["text_rendering_judge"] = text_rendering_judge_reason
    result["scores"]["text_rendering_ocr"] = text_rendering_pass
    result["reasons"]["text_rendering_ocr"] = text_rendering_reason


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run image generation evals for UI mockups and marketing flyers."
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--run-name", type=str, default="")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--judge-model", type=str, default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--image-size", type=str, default=DEFAULT_IMAGE_SIZE)
    parser.add_argument("--num-images", type=int, default=1)
    parser.add_argument(
        "--cases",
        type=str,
        default="",
        help="Comma-separated list of case ids to run (ui_checkout_mockup, coffee_flyer_generation).",
    )
    parser.add_argument(
        "--run-ocr",
        action="store_true",
        help="Run an OCR-style text check for the coffee flyer.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = default_run_id(args.run_name)

    run_dir = args.results_dir / run_id
    artifacts_dir = run_dir / "artifacts"
    output_store = OutputStore(root=artifacts_dir)

    ui_case = TestCase(
        id="ui_checkout_mockup",
        task_type="image_generation",
        prompt=UI_PROMPT,
        criteria=UI_CRITERIA,
    )
    coffee_case = TestCase(
        id="coffee_flyer_generation",
        task_type="image_generation",
        prompt=COFFEE_PROMPT,
        criteria=COFFEE_CRITERIA,
    )

    ui_run = ModelRun(
        label=f"{args.model}-ui",
        task_type="image_generation",
        params={
            "model": args.model,
            "n": args.num_images,
            "size": args.image_size,
        },
    )
    coffee_run = ModelRun(
        label=f"{args.model}-coffee",
        task_type="image_generation",
        params={
            "model": args.model,
            "n": args.num_images,
            "size": args.image_size,
        },
    )

    ui_grader = LLMajRubricGrader(
        key="ui_eval",
        system_prompt=UI_JUDGE_PROMPT,
        content_builder=build_generation_judge_content,
        judge_model=args.judge_model,
        json_schema_name="ui_mockup_eval",
        json_schema=UI_SCHEMA,
        result_parser=parse_ui_result,
    )
    coffee_grader = LLMajRubricGrader(
        key="marketing_eval",
        system_prompt=MARKETING_JUDGE_PROMPT,
        content_builder=build_generation_judge_content,
        judge_model=args.judge_model,
        json_schema_name="marketing_flyer_eval",
        json_schema=MARKETING_SCHEMA,
        result_parser=parse_marketing_result,
    )

    selected = {c.strip() for c in args.cases.split(",") if c.strip()}
    results: list[dict[str, Any]] = []

    if not selected or ui_case.id in selected:
        ui_results = evaluate(
            cases=[ui_case],
            model_runs=[ui_run],
            graders=[ui_grader],
            output_store=output_store,
        )
        results.extend(ui_results)

    if not selected or coffee_case.id in selected:
        coffee_results = evaluate(
            cases=[coffee_case],
            model_runs=[coffee_run],
            graders=[coffee_grader],
            output_store=output_store,
        )
        if coffee_results and args.run_ocr:
            add_ocr_text_check(coffee_results[0], model=args.judge_model)
        results.extend(coffee_results)

    summary = save_results(run_dir, results)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Artifacts written to: {artifacts_dir}")


if __name__ == "__main__":
    main()
