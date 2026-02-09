"""Image editing eval harness runner.

Two example use cases:
- Virtual try-on (garment swap)
- Logo editing (precision text edits)

Run:
  python editing_harness/run_imagegen_evals.py
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.reporting import default_run_id, save_results
from vision_harness.evaluate import evaluate
from vision_harness.graders import (
    LLMajRubricGrader,
    build_editing_judge_content,
)
from vision_harness.storage import OutputStore
from vision_harness.types import ImageInputs, ModelRun, Score, TestCase

DEFAULT_RESULTS_DIR = ROOT_DIR / "editing_harness" / "results"
DEFAULT_MODEL = "gpt-image-1.5"
DEFAULT_JUDGE_MODEL = "gpt-5.2"

VTO_JUDGE_PROMPT = """<core_mission>
Evaluate whether a virtual try-on edit preserves the person while accurately applying the reference garment.
</core_mission>

<role>
You are an expert evaluator of virtual try-on outputs.
You focus on identity preservation, garment fidelity, and body-shape preservation.
</role>

<metrics>
1) facial_similarity: 0-5
2) outfit_fidelity: 0-5
3) body_shape_preservation: 0-5
</metrics>

<verdict_rules>
FAIL if any metric <= 2.
PASS if all metrics >= 3.
</verdict_rules>

<output_constraints>
Return JSON only with the fields specified in the schema.
</output_constraints>
"""

LOGO_JUDGE_PROMPT = """<core_mission>
Evaluate whether a logo edit was executed with exact correctness,
strict preservation, and high visual integrity.

Logo editing is a precision task.
Small errors matter.
Near-misses are failures.
</core_mission>

<role>
You are an expert evaluator of high-precision logo and brand asset editing.
You specialize in detecting subtle text errors, unintended changes,
and preservation drift across single-step and multi-step edits.
</role>

<scope_constraints>
- Judge only against the provided edit instruction and input logo.
- Do NOT judge aesthetics or visual appeal.
- Do NOT infer intent beyond what is explicitly stated.
- Be strict, conservative, and consistent across cases.
</scope_constraints>

<metrics_and_scoring>

Evaluate EACH metric independently using the definitions below.
All metrics are scored from 0 to 5.
Scores apply across ALL requested edit steps.

--------------------------------
1) Edit Intent Correctness (0–5)
--------------------------------
Measures whether every requested edit step was applied correctly
to the correct target.

5: All edit steps applied exactly as specified. Character-level
   accuracy is perfect for every step.
4: All steps applied correctly with extremely minor visual
   imperfections visible only on close inspection.
3: All steps applied, but one or more steps show noticeable
   degradation in clarity or precision.
2: Most steps applied correctly, but one or more steps contain
   a meaningful error.
1: One or more steps are incorrect or applied to the wrong element.
0: Most steps missing, incorrect, or misapplied.

What to consider:
- Exact character identity (letters, numbers, symbols)
- Correct sequencing and targeting of multi-step edits
- No ambiguous characters (Common confusions: 0 vs 6, O vs D, R vs B)

--------------------------------
2) Non-Target Invariance (0–5)
--------------------------------
Measures whether content outside the requested edits remains unchanged.

5: No detectable changes outside the requested edits.
4: Extremely minor drift visible only on close inspection.
3: Noticeable but limited drift in nearby elements.
2: Clear unrequested changes affecting adjacent text,
   symbols, or background.
1: Widespread unintended changes across the logo.
0: Logo identity compromised.

What to consider:
- Adjacent letter deformation or spacing shifts
- Background, texture, or color changes
- Cumulative drift from multi-step edits

--------------------------------
3) Character and Style Integrity (0–5)
--------------------------------
Measures whether the edited content preserves the original
logo’s visual system.

This includes color, stroke weight, letterform structure,
and icon geometry.

5: Edited characters and symbols perfectly match the original
   style. Colors, strokes, letterforms, and icons are
   indistinguishable from the original.
4: Extremely minor deviation visible only on close inspection,
   with no impact on brand perception.
3: Noticeable but limited deviation in one or more properties
   that does not break recognition.
2: Clear inconsistency in color, stroke, letterform, or icon
   geometry that affects visual cohesion.
1: Major inconsistency that materially alters the logo’s appearance.
0: Visual system is corrupted or no longer recognizable.

</metrics_and_scoring>

<verdict_rules>
- Edit Intent Correctness must be ≥ 4.
- Non-Target Invariance must be ≥ 4.
- Character and Style Integrity must be ≥ 4.

If ANY metric falls below threshold, the overall verdict is FAIL.
Do not average scores to determine the verdict.
</verdict_rules>

<consistency_rules>
- Score conservatively.
- If uncertain between two scores, choose the lower one.
- Base all scores on concrete visual observations.
- Penalize cumulative degradation across multi-step edits.
</consistency_rules>

<output_constraints>
Return JSON only.
No additional text.
</output_constraints>
"""

VTO_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "facial_similarity": {"type": "number"},
        "outfit_fidelity": {"type": "number"},
        "body_shape_preservation": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": [
        "verdict",
        "facial_similarity",
        "outfit_fidelity",
        "body_shape_preservation",
        "reason",
    ],
    "additionalProperties": False,
}

LOGO_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "edit_intent_correctness": {"type": "number"},
        "non_target_invariance": {"type": "number"},
        "character_and_style_integrity": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": [
        "verdict",
        "edit_intent_correctness",
        "non_target_invariance",
        "character_and_style_integrity",
        "reason",
    ],
    "additionalProperties": False,
}


def parse_vto_result(data: dict, base_key: str) -> list[Score]:
    return [
        Score(key="facial_similarity", value=float(data["facial_similarity"]), reason=""),
        Score(key="outfit_fidelity", value=float(data["outfit_fidelity"]), reason=""),
        Score(key="body_shape_preservation", value=float(data["body_shape_preservation"]), reason=""),
        Score(key="verdict", value=str(data["verdict"]), reason=(data.get("reason") or "").strip()),
    ]


def parse_logo_result(data: dict, base_key: str) -> list[Score]:
    return [
        Score(key="edit_intent_correctness", value=float(data["edit_intent_correctness"]), reason=""),
        Score(key="non_target_invariance", value=float(data["non_target_invariance"]), reason=""),
        Score(key="character_and_style_integrity", value=float(data["character_and_style_integrity"]), reason=""),
        Score(key="verdict", value=str(data["verdict"]), reason=(data.get("reason") or "").strip()),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run image editing evals for virtual try-on and logo edits."
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--run-name", type=str, default="")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--judge-model", type=str, default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--num-images", type=int, default=1)
    parser.add_argument(
        "--cases",
        type=str,
        default="",
        help="Comma-separated list of case ids to run (vto_jacket_tryon, logo_year_edit).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = default_run_id(args.run_name)

    run_dir = args.results_dir / run_id
    artifacts_dir = run_dir / "artifacts"
    output_store = OutputStore(root=artifacts_dir)

    repo_root = ROOT_DIR.parents[2]
    images_dir = repo_root / "images"

    vto_person_path = images_dir / "base_woman.png"
    vto_garment_path = images_dir / "jacket.png"
    logo_input_path = images_dir / "logo_generation_1.png"

    for path in [vto_person_path, vto_garment_path, logo_input_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing required image: {path}")

    vto_case = TestCase(
        id="vto_jacket_tryon",
        task_type="image_editing",
        prompt=(
            "Put the person in the first image into the jacket shown in the second image.\n"
            "Keep the person's face, pose, body shape, and background unchanged.\n"
            "Preserve the garment's color, pattern, and key details.\n"
            "Do not add extra accessories, text, or new elements."
        ),
        criteria=(
            "The output preserves the same person and background.\n"
            "The jacket matches the reference garment closely.\n"
            "Body shape and pose remain consistent outside normal garment effects.\n"
            "The result looks physically plausible."
        ),
        image_inputs=ImageInputs(image_paths=[vto_person_path, vto_garment_path]),
    )

    logo_case = TestCase(
        id="logo_year_edit",
        task_type="image_editing",
        prompt=(
            "Edit the logo by changing the text from FIELD to BUTTER .\n"
            "Do not change any other text, colors, shapes, or layout."
        ),
        criteria=(
            "The requested edit is applied exactly.\n"
            "All non-target content remains unchanged.\n"
            "Character style, color, and geometry remain consistent with the original."
        ),
        image_inputs=ImageInputs(image_paths=[logo_input_path]),
    )

    vto_run = ModelRun(
        label=f"{args.model}-vto",
        task_type="image_editing",
        params={
            "model": args.model,
            "n": args.num_images,
        },
    )

    logo_run = ModelRun(
        label=f"{args.model}-logo",
        task_type="image_editing",
        params={
            "model": args.model,
            "n": args.num_images,
        },
    )

    vto_grader = LLMajRubricGrader(
        key="vto_eval",
        system_prompt=VTO_JUDGE_PROMPT,
        content_builder=build_editing_judge_content,
        judge_model=args.judge_model,
        json_schema_name="vto_eval",
        json_schema=VTO_SCHEMA,
        result_parser=parse_vto_result,
    )

    logo_grader = LLMajRubricGrader(
        key="logo_eval",
        system_prompt=LOGO_JUDGE_PROMPT,
        content_builder=build_editing_judge_content,
        judge_model=args.judge_model,
        json_schema_name="logo_eval",
        json_schema=LOGO_SCHEMA,
        result_parser=parse_logo_result,
    )

    selected = {c.strip() for c in args.cases.split(",") if c.strip()}
    results: list[dict[str, Any]] = []

    if not selected or vto_case.id in selected:
        vto_results = evaluate(
            cases=[vto_case],
            model_runs=[vto_run],
            graders=[vto_grader],
            output_store=output_store,
        )
        results.extend(vto_results)

    if not selected or logo_case.id in selected:
        logo_results = evaluate(
            cases=[logo_case],
            model_runs=[logo_run],
            graders=[logo_grader],
            output_store=output_store,
        )
        results.extend(logo_results)

    summary = save_results(run_dir, results)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Artifacts written to: {artifacts_dir}")


if __name__ == "__main__":
    main()
