import asyncio
import json
from copy import deepcopy
import os
import subprocess
import sys

import pytest

from delivery import runner


def test_same_model_inputs_and_schema_without_oracle():
    cases = json.loads((runner.ROOT / "cases.json").read_text())
    case = next(c for c in cases if c["id"] == "status_to_damage")
    sent = []

    async def record(request, turn, step):
        sent.append(request)
        return await runner.reference(request, turn, step)

    trace = asyncio.run(runner.play(case, "reference", record))
    assert trace["grade"]["pass"]
    assert trace["effects"] == [{"kind": "replacement", "ref": "REPL-LAMP-1"}]
    assert len(sent) == 8
    paths = [x for x in trace["events"] if x["type"] in ("withheld", "stale_drop")]
    assert paths[0]["call_id"] == paths[1]["call_id"]
    (reviewed,) = [r for r in sent if r["text"]["format"]["name"] == "offer_consent"]
    assert reviewed["model"] == runner.consent.MODEL and not reviewed.get("tools")
    assert set(json.loads(reviewed["input"][0]["content"])) == {
        "verified_offer",
        "preceding_context",
        "offer_as_spoken",
        "caller_reply",
    }
    for request in (r for r in sent if r is not reviewed):
        assert request["tools"] == runner.FUNCTIONS
        assert request["reasoning"]["effort"] == "low"
        assert request["store"] is False
        assert set(json.loads(request["input"][0]["content"])) == {"call_history"}
        assert "expect" not in json.loads(request["input"][0]["content"])
    prior = sent[-1]["input"][-2:]
    assert [part["type"] for part in prior] == ["function_call", "function_call_output"]
    assert prior[0]["call_id"] == prior[1]["call_id"]
    assert json.loads(prior[1]["output"])["replacement_id"] == "RP001"
    bad = deepcopy(case)
    bad["expect"]["effects"] = []
    changed_grade = asyncio.run(runner.play(bad, "reference", record))
    assert not changed_grade["grade"]["pass"]
    assert trace["input_sha256"] == changed_grade["input_sha256"]


def test_one_comparison_changes_only_model_id():
    history = [{"speaker": "caller", "words": "Where is my order?"}]
    luna, terra = [runner.request(model, history, []) for model in runner.MODELS]
    assert luna.pop("model") != terra.pop("model")
    assert luna == terra
    assert all(
        "returns" not in t and t["strict"] and t["type"] == "function" for t in luna["tools"]
    )


def test_outage_cannot_count_as_a_correct_refusal():
    case = {"expect": {"tools": [], "guidance": {}, "effects": []}}
    review = {"type": "consent_review", "turn": 2, "decision": "not_accepted"}
    trace = {"events": [review], "effects": []}
    assert runner.grade(case, trace)["pass"]
    review["decision"] = "unavailable"  # Same empty ledger, different reason.
    grade = runner.grade(case, trace)
    assert not grade["pass"] and "no usable consent decision" in " ".join(grade["failures"])


def test_model_cannot_turn_a_changed_destination_into_permission():
    cases = json.loads((runner.ROOT / "cases.json").read_text())
    case = next(c for c in cases if c["id"] == "status_to_damage")
    case["turns"][-1] = "Yes, but send it to my office."

    # The reference backend still proposes the original-address replacement.
    async def counteroffer_fixture(request, turn, step):
        if request["text"]["format"]["name"] == "offer_consent":
            evidence = json.loads(request["input"][0]["content"])
            assert evidence["caller_reply"] == case["turns"][-1]
            return {"type": "consent", "decision": "not_accepted"}, {}
        return await runner.reference(request, turn, step)

    trace = asyncio.run(runner.play(case, "reference", counteroffer_fixture))
    proposal = next(e for e in trace["events"] if e.get("name") == "create_replacement")
    assert proposal["result"]["status"] == "rejected"
    assert trace["effects"] == []


def test_store_defaults_to_terra_and_comparison_is_explicit():
    args = runner.parse_args(["--out", "runs/store"])
    assert args.models == ["gpt-6.1-terra"]
    assert runner.request(args.models[0], [], [])["model"] == "gpt-6.1-terra"

    args = runner.parse_args(["--out", "runs/paired", "--models", *runner.MODELS])
    assert args.models == ["gpt-6-luna", "gpt-6.1-terra"]


def test_reference_cli_returns_nonzero_and_keeps_a_failed_grade(tmp_path):
    cases = json.loads((runner.ROOT / "cases.json").read_text())
    case = next(c for c in cases if c["id"] == "status_to_damage")
    case["expect"]["effects"] = []
    fixture = tmp_path / "cases.json"
    fixture.write_text(json.dumps([case]))
    out = tmp_path / "run"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "delivery.runner",
            "--reference",
            "--cases",
            str(fixture),
            "--out",
            str(out),
        ],
        capture_output=True,
    )
    assert process.returncode == 1
    assert not json.loads((out / "reference.json").read_text())["grade"]["pass"]


def test_backend_error_fails_the_campaign_and_preserves_trace(tmp_path, monkeypatch):
    async def unavailable(*args):
        return {"type": "error", "error": "Injected failure"}, {}

    monkeypatch.setattr(runner, "http_sender", unavailable)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-stub")
    out = tmp_path / "run"
    args = runner.parse_args(["--ids", "credit_counteroffer", "--out", str(out)])
    assert asyncio.run(runner.main(args)) == 1
    record = json.loads(next(out.glob("*__*.json")).read_text())
    assert record["status"] == "error" and not record["grade"]["pass"]


@pytest.mark.parametrize(
    "extra,reason",
    [
        (["--reference", "--ids", "credit_counteroffer"], "status_to_damage"),
        (["--reference", "--ids", "unknown"], "valid case IDs"),
        (["--ids", "credit_accept"], "OPENAI_API_KEY"),
    ],
)
def test_cli_preflight_fails_before_claiming_the_output_directory(tmp_path, extra, reason):
    env = dict(os.environ, PYTHONPATH=str(runner.ROOT.parent))
    env.pop("OPENAI_API_KEY", None)
    out = tmp_path / "receipts"
    result = subprocess.run(
        [sys.executable, "-m", "delivery.runner", *extra, "--out", str(out)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2 and reason in result.stderr
    assert "Traceback" not in result.stderr and not out.exists()


def test_completed_response_still_rejects_an_explicitly_incomplete_tool_item():
    item = {
        "type": "function_call",
        "name": "register_credit",
        "call_id": "w",
        "arguments": '{"quote_id":"CREDIT-20"}',
    }
    body = {"model": runner.DEFAULT_BACKEND_MODEL, "status": "completed", "output": [item]}
    assert runner.parse_model(body, runner.DEFAULT_BACKEND_MODEL)["call_id"] == "w"
    item["status"] = "in_progress"
    with pytest.raises(ValueError, match="incomplete"):
        runner.parse_model(body, runner.DEFAULT_BACKEND_MODEL)


def test_auth_error_does_not_copy_the_response_body_into_a_trace():
    class Unauthorized:
        status = 401
        headers = {"x-request-id": "auth-request"}

        def post(self, url, *, json):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def json(self):
            raise AssertionError("An upstream authentication error may echo a credential")

    result, receipt = asyncio.run(
        runner.http_sender(
            Unauthorized(), runner.request(runner.DEFAULT_BACKEND_MODEL, [], []), 1, 0
        )
    )
    assert result == {"type": "error", "error": "Responses returned HTTP 401"}
    assert receipt["http"] == 401 and receipt["request_id"] == "auth-request"
