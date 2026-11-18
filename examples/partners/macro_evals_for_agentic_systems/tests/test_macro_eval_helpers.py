from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

HELPERS_DIR = Path(__file__).resolve().parents[1] / "helpers"
if str(HELPERS_DIR) not in sys.path:
    sys.path.insert(0, str(HELPERS_DIR))

import data_prep
import macro_eval_pipeline


def test_compute_topic_keywords_handles_filtered_non_contiguous_index() -> None:
    df = pd.DataFrame(
        {
            "topic_id": [-1, 0, 0, 1, 1],
            "document_text": [
                "unclustered noise trace",
                "pricing drift msrp margin mismatch",
                "pricing drift msrp quote mismatch",
                "factory routing fulfillment reroute delay",
                "factory routing fulfillment schedule delay",
            ],
        }
    )
    filtered = df[df["topic_id"] != -1]

    result = macro_eval_pipeline.compute_topic_keywords(filtered, top_n=5, min_df=2)

    by_topic = dict(zip(result["topic_id"], result["keywords"]))
    assert "pricing" in by_topic[0]
    assert "routing" in by_topic[1]


def test_compute_topic_keywords_uses_positional_rows_when_index_is_permuted() -> None:
    df = pd.DataFrame(
        {
            "topic_id": [1, 1, 0, 0],
            "document_text": [
                "factory routing fulfillment reroute",
                "factory routing fulfillment schedule",
                "pricing drift msrp margin",
                "pricing drift msrp quote",
            ],
        },
        index=[2, 3, 0, 1],
    )

    result = macro_eval_pipeline.compute_topic_keywords(df, top_n=5, min_df=2)

    by_topic = dict(zip(result["topic_id"], result["keywords"]))
    assert "pricing" in by_topic[0]
    assert "routing" not in by_topic[0]
    assert "routing" in by_topic[1]
    assert "pricing" not in by_topic[1]


def test_compute_topic_keywords_returns_schema_when_vocabulary_is_empty() -> None:
    single_doc = pd.DataFrame(
        {"topic_id": [0], "document_text": ["pricing drift"]}
    )

    result = macro_eval_pipeline.compute_topic_keywords(single_doc, min_df=2)

    assert list(result.columns) == [
        "topic_id",
        "keywords",
        "weights",
        "document_count",
    ]
    assert result.empty
    labels = macro_eval_pipeline.build_topic_labels(result)
    assert labels.empty


def test_compute_topic_keywords_propagates_invalid_vectorizer_config() -> None:
    df = pd.DataFrame(
        {
            "topic_id": [0, 0],
            "document_text": ["pricing drift msrp", "pricing drift quote"],
        }
    )

    with pytest.raises(ValueError, match="Invalid value for ngram_range"):
        macro_eval_pipeline.compute_topic_keywords(df, ngram_range=(2, 1))


def test_normalize_bundle_sorts_untimed_findings_after_utc_spans_and_backfills_ts() -> None:
    bundle = {
        "run": {
            "run_id": "run-1",
            "status": "failed",
            "updated_at": None,
            "summary": {
                "terminal_state": "failed",
                "findings": [
                    {
                        "code": "BASE_MSRP_DRIFT",
                        "severity": "error",
                        "agent_name": "pricing_agent",
                        "message": "MSRP drifted from quote.",
                    }
                ],
            },
        },
        "trace": {
            "trace_id": "trace-1",
            "started_at": "2026-03-01T10:00:00Z",
            "ended_at": None,
        },
        "spans": [
            {
                "span_id": "span-1",
                "span_type": "agent",
                "agent_name": "router",
                "started_at": "2026-03-01T10:00:01Z",
                "ended_at": "2026-03-01T10:00:02Z",
                "span_data": {},
            },
            {
                "span_id": "span-2",
                "span_type": "agent",
                "agent_name": "pricing_agent",
                "started_at": "2026-03-01T10:00:03Z",
                "ended_at": "2026-03-01T10:00:05Z",
                "span_data": {},
            },
        ],
        "events": [],
    }

    _, events = data_prep.normalize_bundle(
        bundle, {"status": "failed"}, 1, "bundle.json"
    )

    assert [event["event_id"] for event in events] == [
        "span-1",
        "span-2",
        "finding::1",
    ]
    assert events[-1]["ts"] == "2026-03-01T10:00:03Z"
    assert events[-1]["ended_at"] == "2026-03-01T10:00:05Z"


def test_normalize_bundle_sorts_mixed_naive_and_utc_timestamps() -> None:
    bundle = {
        "run": {"run_id": "run-2", "status": "completed", "summary": {}},
        "trace": {
            "trace_id": "trace-2",
            "started_at": "2026-03-01T10:00:00Z",
            "ended_at": "2026-03-01T10:00:05Z",
        },
        "spans": [
            {
                "span_id": "span-late-naive",
                "span_type": "agent",
                "agent_name": "pricing_agent",
                "started_at": "2026-03-01T10:00:04",
                "ended_at": "2026-03-01T10:00:05",
                "span_data": {},
            },
            {
                "span_id": "span-early-utc",
                "span_type": "agent",
                "agent_name": "router",
                "started_at": "2026-03-01T10:00:01Z",
                "ended_at": "2026-03-01T10:00:02Z",
                "span_data": {},
            },
        ],
        "events": [],
    }

    _, events = data_prep.normalize_bundle(
        bundle, {"status": "completed"}, 1, "bundle.json"
    )

    assert [event["event_id"] for event in events] == [
        "span-early-utc",
        "span-late-naive",
    ]


def test_normalize_bundle_preserves_nanosecond_timestamp_order_with_untimed_finding() -> None:
    bundle = {
        "run": {
            "run_id": "run-3",
            "status": "failed",
            "updated_at": None,
            "summary": {
                "terminal_state": "failed",
                "findings": [
                    {
                        "code": "WHEEL_TRIM_CONFLICT",
                        "severity": "error",
                        "agent_name": "validation_agent",
                        "message": "Wheel and trim conflict.",
                    }
                ],
            },
        },
        "trace": {
            "trace_id": "trace-3",
            "started_at": "2026-03-01T10:00:00Z",
            "ended_at": None,
        },
        "spans": [
            {
                "span_id": "a-later-ns",
                "span_type": "handoff",
                "agent_name": "router",
                "started_at": "2026-03-01T10:00:00.000000200Z",
                "ended_at": "2026-03-01T10:00:00.000000300Z",
                "span_data": {"from_agent": "router", "to_agent": "validation_agent"},
            },
            {
                "span_id": "z-earlier-ns",
                "span_type": "function",
                "agent_name": "router",
                "started_at": "2026-03-01T10:00:00.000000100Z",
                "ended_at": "2026-03-01T10:00:00.000000150Z",
                "span_data": {"name": "lookup_trim"},
            },
        ],
        "events": [],
    }

    _, events = data_prep.normalize_bundle(
        bundle, {"status": "failed"}, 1, "bundle.json"
    )

    assert [event["event_id"] for event in events] == [
        "z-earlier-ns",
        "a-later-ns",
        "finding::1",
    ]
    assert events[-1]["ts"] == "2026-03-01T10:00:00.000000200Z"
    assert events[-1]["ended_at"] == "2026-03-01T10:00:00.000000300Z"
