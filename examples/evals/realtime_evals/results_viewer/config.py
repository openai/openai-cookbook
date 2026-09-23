from __future__ import annotations

DEFAULT_SCORE_KEYS = [
    "grade_mean",
    "tool_call_correctness_mean",
    "tool_call_arg_correctness_mean",
]

DEFAULT_LATENCY_SERIES = [
    "First audio latency (ms)",
    "First text latency (ms)",
    "Response done latency (ms)",
]

DEFAULT_TOKEN_SERIES = [
    "Output tokens",
    "Output audio tokens",
    "Output text tokens",
]

LATENCY_CHART_KEYS = {
    "First audio latency (ms)": [
        "latency_first_audio_ms_avg",
        "latency_first_audio_ms_p50",
        "latency_first_audio_ms_p95",
        "latency_first_audio_ms_p99",
    ],
    "First text latency (ms)": [
        "latency_first_text_ms_avg",
        "latency_first_text_ms_p50",
        "latency_first_text_ms_p95",
        "latency_first_text_ms_p99",
    ],
    "Response done latency (ms)": [
        "latency_response_done_ms_avg",
        "latency_response_done_ms_p50",
        "latency_response_done_ms_p95",
        "latency_response_done_ms_p99",
    ],
}

TOKEN_CHART_KEYS = {
    "Output tokens": [
        "output_tokens_avg",
        "output_tokens_p50",
        "output_tokens_p95",
        "output_tokens_p99",
    ],
    "Output audio tokens": [
        "output_audio_tokens_avg",
        "output_audio_tokens_p50",
        "output_audio_tokens_p95",
        "output_audio_tokens_p99",
    ],
    "Output text tokens": [
        "output_text_tokens_avg",
        "output_text_tokens_p50",
        "output_text_tokens_p95",
        "output_text_tokens_p99",
    ],
}

SCORE_KEY_LABELS = {
    "grade_mean": "Grade",
    "tool_call_correctness_mean": "Tool call correctness",
    "tool_call_arg_correctness_mean": "Tool arg correctness",
}

PERCENTILE_LABELS = {
    "avg": "avg",
    "p50": "p50",
    "p95": "p95",
    "p99": "p99",
}

SUMMARY_TABLE_BASE_COLUMNS = [
    "run_label",
    "run_name",
    "model",
    "assistant_model_default",
    "simulator_model_default",
]
