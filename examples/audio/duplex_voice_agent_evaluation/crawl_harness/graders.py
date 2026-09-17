"""CRAWL's single-turn grading interface, backed by shared evaluation logic."""

from __future__ import annotations

from shared.single_turn.grading import (
    DEFAULT_JUDGE_MODEL,
    DEFAULT_JUDGE_REASONING_EFFORT,
    JUDGE_RUBRIC_VERSION,
    SEMANTIC_RUBRICS,
    DimensionGrade,
    SemanticJudgeDecision,
    SemanticJudgeError,
    applicable_semantic_dimensions,
    apply_semantic_grades,
    build_semantic_judge_input,
    compute_tool_call_grade,
    expected_args_subset,
    expected_tool_fields,
    grade_deterministic_dimensions,
    judge_semantic_dimensions,
    normalize_text,
    parse_json_dict,
    unassessed_semantic_dimensions,
    verify_final_state,
)
from shared.single_turn.grading import (
    SingleTurnGradeResult as CrawlGradeResult,
)
from shared.single_turn.grading import (
    grade_single_turn_example as grade_crawl_example,
)

__all__ = (
    "DEFAULT_JUDGE_MODEL",
    "DEFAULT_JUDGE_REASONING_EFFORT",
    "JUDGE_RUBRIC_VERSION",
    "SEMANTIC_RUBRICS",
    "CrawlGradeResult",
    "DimensionGrade",
    "SemanticJudgeDecision",
    "SemanticJudgeError",
    "applicable_semantic_dimensions",
    "apply_semantic_grades",
    "build_semantic_judge_input",
    "compute_tool_call_grade",
    "expected_args_subset",
    "expected_tool_fields",
    "grade_crawl_example",
    "grade_deterministic_dimensions",
    "judge_semantic_dimensions",
    "normalize_text",
    "parse_json_dict",
    "unassessed_semantic_dimensions",
    "verify_final_state",
)
