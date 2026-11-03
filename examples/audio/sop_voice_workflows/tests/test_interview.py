"""The semantic model is substituted only in offline tests. The runtime takes PCM and native events."""

import asyncio

import json

from pathlib import Path

import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice.audio import FRAME_BYTES

from interview_app.live import Controller

from interview_app.meaning import INTERPRETER, read_proposal, request, start_event

from interview_app.store import ATS

from interview_app.workflow import Interview


def intent(action, *, day="none", shift="none", focus="current", delivered=False, evidence=""):
    return dict(
        action=action,
        day=day,
        shift=shift,
        focus=focus,
        condition_evidence=evidence,
        complete_summary_in_speech=delivered,
    )


class Session:
    def __init__(self, **kwargs):
        self.store = ATS(**kwargs)
        self.events = []
        self.app = Interview(self.store, self.capture)
        self.turn = 0
        scope, self.app.step = self.app.opening("session")

    def capture(self, kind, **data):
        self.events.append(dict(event=kind, **data))

    def apply(self, proposal, condition="unconditional", *, ready=False, caller_text=""):
        self.turn += 1
        scope = dict(
            turn=self.turn,
            source_event_id="source_" + str(self.turn),
            revision=self.store.snapshot()["revision"],
        )
        result = self.app.apply(scope, proposal, condition, ready, caller_text=caller_text)
        if result:
            self.app.step = result
        return result

    def tools(self):
        return [e for e in self.events if e["event"] == "app.tool"]


def test_request_shapes_and_semantic_schema():
    body = start_event()["session"]
    assert body["delegation"] == {"type": "client"} and body["audio"]["format"]["rate"] == 24000
    (trigger,) = body["triggers"]
    assert trigger["event_type"] == "session.input_transcript.delta"
    assert [q["name"] for q in trigger["decisions"]["questions"]] == [
        "needs_backend_v1",
        "condition_v1",
    ]
    payload = request({"completed_caller_contribution": "Actually Tuesday."})
    assert payload["text"]["format"]["schema"]["additionalProperties"] is False
    assert payload["instructions"] == INTERPRETER
    assert json.loads(payload["input"][0]["content"]) == {
        "completed_caller_contribution": "Actually Tuesday."
    }

    def parse(p):
        return read_proposal(
            {
                "status": "completed",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(p)}]}
                ],
            }
        )

    assert parse(intent("answer", day="Tuesday"))["day"] == "Tuesday"
    assert parse(intent("answer", day="Monday", shift="either"))["shift"] == "either"
    qualified = intent(
        "conditional", day="Tuesday", focus="day", evidence="if I can arrange a lift"
    )
    assert parse(qualified) == qualified
    for invalid in (
        intent("answer"),
        intent("cancel", shift="morning"),
        intent("answer", day="Wednesday"),
        intent("conditional", day="Tuesday", focus="shift"),
        intent("resolve", day="Tuesday", focus="day"),
        intent("confirm", evidence="unrelated"),
        {"action": "confirm"},
    ):
        with pytest.raises(ValueError):
            parse(invalid)


@pytest.mark.parametrize(
    "parts",
    [
        [{"type": "refusal"}],
        [{"type": "output_text"}],
        [{"type": "output_text", "text": None}],
        [
            {"type": "refusal"},
            {"type": "output_text", "text": json.dumps(intent("answer", day="Tuesday"))},
        ],
    ],
)
def test_unusable_interpreter_reply_cannot_propose_an_action(parts):
    response = {"status": "completed", "output": [{"type": "message", "content": parts}]}
    with pytest.raises(ValueError, match="structured backend message"):
        read_proposal(response)


def test_happy_path_saves_then_retrieves_and_confirms_once():
    s = Session()
    assert s.app.step.kind == "day"
    assert s.apply(intent("answer", day="Monday")).kind == "shift"
    assert s.apply(intent("answer", shift="morning")).kind == "summary"
    assert s.apply(intent("confirm", delivered=True), ready=True).kind == "completed"
    assert s.apply(intent("confirm", delivered=True), ready=True) is None
    assert [r["name"] for r in s.tools()] == [
        "get_next_question",
        "record_answer",
        "get_next_question",
        "record_answer",
        "get_next_question",
        "complete_interview",
    ]
    assert s.store.snapshot() == {
        "answers": {"day": "Monday", "shift": "morning"},
        "status": "completed",
        "revision": 3,
        "completed": True,
        "cancelled": False,
    }


@pytest.mark.parametrize("shift", ["morning", "afternoon", "either"])
def test_volunteered_shift_is_applied_after_current_ats_lookup(shift):
    s = Session()
    step = s.apply(intent("answer", day="Monday", shift=shift))
    assert step.kind == "summary" and "does not confirm a job offer" in step.content
    assert s.store.snapshot()["answers"] == {"day": "Monday", "shift": shift}
    tools = s.tools()
    assert [(r["name"], r["expected_revision"]) for r in tools] == [
        ("get_next_question", 0),
        ("record_answer", 0),
        ("get_next_question", 1),
        ("record_answer", 1),
        ("get_next_question", 2),
    ]
    assert tools[2]["result"]["step"] == "shift" and shift in tools[2]["result"]["choices"]
    assert (
        tools[4]["result"]["step"] == "summary" and step.content == tools[4]["result"]["question"]
    )
    assert len({r["source_event_id"] for r in tools[1:]}) == 1
    if shift == "either":
        assert (
            "either shift works for you" in step.content
            and "preferred shift is" not in step.content
        )
    assert s.apply(intent("answer", day="Monday", shift=shift)).kind == "summary"
    assert sum(r["name"] == "record_answer" for r in s.tools()) == 2


@pytest.mark.parametrize("alter", ["unavailable", "wrong_revision", "wrong_field", "choice_absent"])
def test_volunteered_shift_requires_successful_current_field_and_choice(alter):
    s = Session()
    execute = s.store.execute

    def altered(name, args, **kwargs):
        result = execute(name, args, **kwargs)
        if name == "get_next_question" and kwargs["expected_revision"] == 1:
            if alter == "unavailable":
                return {"status": "unavailable"}
            if alter == "wrong_revision":
                result["state"]["revision"] = 0
            if alter == "wrong_field":
                result["step"] = "day"
            if alter == "choice_absent":
                result["choices"].remove("either")
        return result

    s.store.execute = altered
    step = s.apply(intent("answer", day="Monday", shift="either"))
    assert step.kind != "summary"
    assert s.store.snapshot()["answers"] == {"day": "Monday", "shift": ""}
    assert [r["name"] for r in s.tools()] == [
        "get_next_question",
        "record_answer",
        "get_next_question",
    ]


def test_shift_alone_before_day_has_no_authority():
    s = Session()
    assert s.apply(intent("answer", shift="afternoon")).kind == "clarify_day"
    assert not any(r["name"] == "record_answer" for r in s.tools())


@pytest.mark.parametrize(
    "condition,proposal",
    [
        ("conditional", intent("answer", day="Tuesday", focus="day")),
        ("conditional", intent("answer", day="Tuesday")),
        ("unconditional", intent("conditional", focus="day")),
    ],
)
def test_conditional_change_to_day_preserves_saved_day_and_clarifies_right_field(
    condition, proposal
):
    s = Session(day="Monday")
    assert s.app.step.kind == "shift"
    clarify = s.apply(proposal, condition)
    assert clarify.kind == "clarify_day" and "unconfirmed" in clarify.content
    assert s.store.snapshot()["answers"] == {"day": "Monday", "shift": ""}
    assert (
        s.apply(
            intent("resolve", day="Tuesday", focus="day", evidence="Tuesday regardless"),
            caller_text="Tuesday regardless of the end time.",
        ).kind
        == "shift"
    )
    assert s.store.snapshot()["answers"] == {"day": "Tuesday", "shift": ""}
    assert sum(r["name"] == "record_answer" for r in s.tools()) == 1


def test_pending_choice_survives_defer_restart_and_a_changed_condition(tmp_path):
    path = tmp_path / "interview.sqlite"
    s = Session(path=path, day="Monday", shift="morning")
    text = "My old job ended at four. Tuesday if I have a ride."
    step = s.apply(
        intent("conditional", day="Tuesday", focus="day", evidence="if I have a ride"),
        "conditional",
        caller_text=text,
    )
    assert (
        "if I have a ride" in step.content
        and "Tuesday" in step.content
        and "old job" not in step.content
    )
    assert "Monday" not in step.content and s.store.snapshot()["revision"] == 0
    assert s.apply(intent("defer"), caller_text="Yes, leave it open.").kind == "deferred"
    assert s.apply(intent("backchannel")) is None
    assert s.apply(intent("repeat")).kind == "deferred"
    s.store.close()

    s = Session(path=path)
    assert s.app.step.kind == "clarify_day" and "if I have a ride" in s.app.step.content
    step = s.apply(
        intent("conditional", day="Tuesday", focus="day", evidence="if I can get childcare"),
        "conditional",
        caller_text="Actually, that day depends on if I can get childcare.",
    )
    assert "if I can get childcare" in step.content and "ride" not in step.content
    assert (
        s.apply(intent("answer", shift="afternoon"), caller_text="Afternoon.").kind == "clarify_day"
    )
    assert s.store.snapshot()["answers"] == {"day": "Monday", "shift": "afternoon"}
    assert s.apply(intent("confirm", delivered=True), ready=True).kind == "clarify_day"
    assert (
        s.apply(
            intent("answer", day="Tuesday", focus="day", evidence="Tuesday regardless"),
            caller_text="The bus comes at nine.",
        ).kind
        == "clarify_day"
    )
    repeated = s.apply(
        intent("answer", day="Tuesday", focus="day", evidence="Tuesday"), caller_text="Tuesday."
    )
    assert repeated.kind == "clarify_day" and "?" not in repeated.content
    for action in ("conditional", "resolve"):
        assert (
            s.apply(
                intent(action, day="Tuesday", focus="day", evidence="Tuesday."),
                caller_text="Tuesday.",
            ).kind
            == "clarify_day"
        )
        assert s.store.pending_conditions()["day"]["quote"] == "if I can get childcare"
    assert (
        s.store.execute(
            "complete_interview",
            s.store.snapshot()["answers"],
            operation_id="bypass",
            expected_revision=1,
        )["status"]
        == "rejected"
    )

    step = s.apply(
        intent("resolve", day="Tuesday", focus="day", evidence="I found childcare"),
        caller_text="I found childcare, so that day works.",
    )
    assert step.kind == "summary" and "Tuesday" in step.content and "afternoon" in step.content
    assert not s.store.pending_conditions()
    assert s.apply(intent("confirm", delivered=True), ready=True).kind == "completed"
    s.store.close()


def test_unrelated_or_unretrieved_qualifier_cannot_be_quoted_as_the_callers_condition():
    s = Session()
    step = s.apply(
        intent("conditional", day="Tuesday", focus="day", evidence="the shift ends at four"),
        "conditional",
        caller_text="Tuesday if the shift ends before five.",
    )
    assert "ends at four" not in step.content and "Tuesday" in step.content
    step = s.apply(
        intent("conditional", shift="afternoon", focus="shift", evidence="if parking is free"),
        "conditional",
        caller_text="Afternoon if parking is free.",
    )
    assert "parking" not in step.content and "afternoon" not in step.content
    assert list(s.store.pending_conditions()) == ["day"] and s.store.snapshot()["revision"] == 0


def test_different_choice_can_replace_a_condition_without_resolving_its_premise():
    s = Session(day="Monday")
    s.apply(
        intent("conditional", shift="morning", focus="shift", evidence="if my train is running"),
        "conditional",
        caller_text="Morning, if my train is running.",
    )
    step = s.apply(
        intent("answer", shift="afternoon", focus="shift", evidence="afternoon instead"),
        caller_text="Make it afternoon instead.",
    )
    assert step.kind == "summary" and s.store.snapshot()["answers"] == {
        "day": "Monday",
        "shift": "afternoon",
    }
    assert not s.store.pending_conditions()


def test_correction_during_summary_refreshes_each_choice_and_requires_fresh_confirmation():
    s = Session(day="Monday", shift="morning")
    old = dict(turn=1, source_event_id="old", revision=0)
    new = s.apply(intent("answer", day="Tuesday", shift="afternoon"))
    assert new.kind == "summary" and "Tuesday" in new.content and "afternoon" in new.content
    assert s.app.apply(old, intent("confirm", delivered=True), "unconditional", True) is None
    for condition, delivered, ready in [
        ("unconditional", False, True),
        ("unconditional", True, False),
        ("incomplete", True, True),
    ]:
        assert (
            s.apply(intent("confirm", delivered=delivered), condition, ready=ready).kind
            == "summary"
        )
        assert not s.store.snapshot()["completed"]
    assert s.apply(intent("confirm", delivered=True), ready=True).kind == "completed"


@pytest.mark.parametrize("uncertain", ["conditional", "incomplete", None])
def test_cancel_waits_for_clear_consent_and_closes_once(uncertain):
    s = Session(day="Monday")
    assert s.apply(intent("cancel"), uncertain).kind == "clarify_cancel"
    assert s.store.snapshot()["status"] == "active"
    assert all(row["name"] != "cancel_interview" for row in s.tools())
    assert s.apply(intent("cancel"), "unconditional").kind == "cancelled"
    assert s.apply(intent("cancel"), "unconditional") is None
    assert sum(r["name"] == "cancel_interview" for r in s.tools()) == 1


def test_candidate_can_continue_after_a_cancellation_question():
    s = Session(day="Monday")
    assert s.apply(intent("cancel"), "incomplete").kind == "clarify_cancel"
    assert s.apply(intent("decline")).kind == "shift"
    assert s.store.snapshot()["status"] == "active"
    assert [row["name"] for row in s.tools()] == ["get_next_question", "get_next_question"]


def test_acknowledgement_repeat_and_negative_summary_have_no_side_effect():
    s = Session(day="Tuesday", shift="afternoon")
    assert s.apply(intent("backchannel"), "incomplete") is None
    assert s.apply(intent("repeat"), "incomplete").kind == "summary"
    assert s.apply(intent("scope"), "incomplete").kind == "summary"
    assert s.apply(intent("decline")).kind == "amend"
    assert [r["name"] for r in s.tools()] == ["get_next_question"]


def test_lookup_failure_after_save_reports_both_receipts_no_second_save():
    def fault(name, phase, args, state, key):
        return (
            name == "get_next_question"
            and phase == "before"
            and state["answers"]["shift"] == "morning"
        )

    s = Session(day="Monday", fault=fault)
    step = s.apply(intent("answer", shift="morning"))
    assert step.kind == "lookup_unavailable"
    assert (
        step.content
        == "I've saved morning. I couldn't retrieve the next question, so we'll pause here."
    )
    assert s.app.paused and s.store.snapshot()["status"] == "active"
    assert [r["name"] for r in s.tools()] == [
        "get_next_question",
        "record_answer",
        "get_next_question",
    ]
    assert s.store.snapshot()["answers"] == {"day": "Monday", "shift": "morning"}
    assert s.apply(intent("answer", shift="morning")) is None


@pytest.mark.parametrize(
    "operation,proposal",
    [
        ("record_answer", intent("answer", shift="morning")),
        ("complete_interview", intent("confirm", delivered=True)),
        ("cancel_interview", intent("cancel")),
    ],
)
@pytest.mark.parametrize("phase", ["before", "after", "unreadable"])
def test_write_failure_and_receipt_reconciliation(operation, proposal, phase):
    def fault(name, step, args, state, key):
        return (name == operation and step == ("after" if phase == "unreadable" else phase)) or (
            name == "get_operation" and step == "before" and phase == "unreadable"
        )

    s = Session(
        day="Monday", shift="morning" if operation == "complete_interview" else "", fault=fault
    )
    result = s.apply(proposal, ready=True)
    writes = [r for r in s.tools() if r["name"] == operation]
    assert len(writes) == 1 and writes[0]["result"]["status"] == (
        "unavailable" if phase == "before" else "unknown"
    )
    if phase == "before":
        assert result.kind.endswith("unavailable")
        assert s.store.snapshot()["revision"] == 0
    else:
        assert s.store.snapshot()["revision"] == 1
        (read,) = [r for r in s.tools() if r["name"] == "get_operation"]
        assert read["arguments"]["operation_id"] == writes[0]["operation_id"]
        assert result.kind == (
            "unknown"
            if phase == "unreadable"
            else {
                "record_answer": "summary",
                "complete_interview": "completed",
                "cancel_interview": "cancelled",
            }[operation]
        )
    if phase != "after":
        assert "follow up" in result.content and s.apply(proposal, ready=True) is None


def test_database_persists_and_compares_idempotency_key_and_revision(tmp_path):
    db = tmp_path / "interview.sqlite"
    a = ATS(db)
    b = ATS(db)
    a.execute("get_next_question", {}, operation_id="open", expected_revision=0)
    args = {"question_id": "day", "value": "Tuesday"}
    initial = a.execute("record_answer", args, operation_id="turn_1/save_day", expected_revision=0)
    assert initial["changed"]
    assert b.execute("record_answer", args, operation_id="turn_1/save_day", expected_revision=0)[
        "replayed"
    ]
    assert (
        b.execute(
            "record_answer",
            {**args, "value": "Monday"},
            operation_id="turn_1/save_day",
            expected_revision=1,
        )["reason"]
        == "operation_id_conflict"
    )
    assert (
        b.execute(
            "record_answer", {**args, "value": "Monday"}, operation_id="late", expected_revision=0
        )["status"]
        == "stale"
    )
    assert b.snapshot()["answers"]["day"] == "Tuesday" and b.snapshot()["revision"] == 1
    a.close()
    b.close()
    c = ATS(db)
    assert (
        c.execute(
            "get_operation",
            {"operation_id": "turn_1/save_day"},
            operation_id="read",
            expected_revision=0,
        )["receipt"]
        == initial
    )
    c.close()


LOUD = (700).to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)

QUIET = bytes(FRAME_BYTES)


class Loopback:
    """Inject wire-shaped events; no network/model behavior is inferred from these unit tests."""

    def __init__(
        self, interpret, *, day="", shift="", before_delegation=None, after_interpret=None
    ):
        self.store = ATS(day=day, shift=shift)
        self.events, self.sent = [], []

        def emit(event_type, **values):
            self.events.append(dict(type=event_type, **values))

        async def send(body):
            self.sent.append(body)
            if body["type"] == "session.commentary.append":
                self.c.observe(
                    {
                        "type": "session.commentary.appended",
                        "event_id": "ack/" + body["event_id"],
                        "client_event_id": body["event_id"],
                        "start_ms": self.clock,
                        "end_ms": self.clock + 200,
                    },
                    self.clock,
                )

        self.c = Controller(
            self.store,
            "demo-session",
            emit,
            send,
            interpret,
            before_delegation=before_delegation,
            after_interpret=after_interpret,
        )
        self.clock = 0

    def frames(self, n, *, user=QUIET, agent=QUIET):
        for _ in range(n):
            self.clock += 20
            played = agent
            self.c.frame(user, played, self.clock, remaining_output_samples=0)

    def transcript(self, sid, value):
        self.c.observe(
            dict(
                type="session.input_transcript.delta",
                event_id=sid,
                delta=value,
                start_ms=self.c.current.start_ms,
                end_ms=self.c.media_ms,
            ),
            self.clock,
        )

    def labels(self, sid, handoff="yes", condition="unconditional"):
        answers = [
            {"name": "needs_backend_v1", "choice": handoff},
            {"name": "condition_v1", "choice": condition},
        ]
        self.c.observe(
            {
                "type": "decision.event",
                "source_event_id": sid,
                "event": {"type": "decision.completed", "decision": {"answers": answers}},
            },
            self.clock,
        )

    def native(self, delegation_id, at_ms=None):
        at_ms = self.c.media_ms if at_ms is None else at_ms
        event = {
            "type": "session.delegation.created",
            "event_id": "native_" + delegation_id,
            "offset_ms": at_ms,
            "delegation": {"id": delegation_id, "target": "client"},
        }
        self.c.observe(event, self.clock)
        return event

    def say(self, sid, text, handoff="yes", condition="unconditional"):
        self.frames(6, user=LOUD)
        self.transcript(sid, text)
        self.labels(sid, handoff, condition)
        self.frames(100)

    def rows(self, kind):
        return [e for e in self.events if e["type"] == kind]


@pytest.mark.parametrize(
    "delegates, label, reason, quiet_ms, expected_saves",
    [
        (True, "yes", "native_delegation", 1000, 1),
        (True, None, "native_delegation", 1800, 0),
        (False, "yes", "decisions_recovery", 1800, 1),
        (False, None, "settled_unclassified", 1800, 0),
        (False, "incomplete", "settled_unclassified", 1800, 0),
        (False, "no", None, None, 0),
    ],
)
def test_what_starts_interpretation_and_what_allows_a_save(
    delegates, label, reason, quiet_ms, expected_saves
):
    async def exercise():
        async def interpret(evidence):
            return intent("answer", day="Tuesday")

        call = Loopback(interpret)
        try:
            await call.c.opening()
            call.frames(6, user=LOUD)
            call.transcript("candidate-day", "Tuesday")
            if label:
                call.labels(
                    "candidate-day",
                    handoff=label,
                    condition="unconditional" if label == "yes" else "incomplete",
                )
            if delegates:
                call.native("day-handoff")
                await asyncio.gather(*call.c.tasks)
            call.frames(100)
            await asyncio.gather(*call.c.tasks)
            routes = call.rows("app.route")
            assert [(r["reason"], r["quiet_ms"]) for r in routes] == (
                [(reason, quiet_ms)] if reason else []
            )
            saves = [r for r in call.rows("app.tool") if r["name"] == "record_answer"]
            assert len(saves) == expected_saves
        finally:
            await call.c.stop()
            call.store.close()

    asyncio.run(exercise())


def test_qualifier_before_or_after_the_day_save():
    async def exercise(split):
        async def interpret(evidence):
            words = evidence["completed_caller_contribution"]
            if "before five" in words:
                return intent(
                    "conditional",
                    day="Tuesday",
                    focus="day",
                    evidence="if I can finish before five",
                )
            if words == "Morning.":
                assert (
                    evidence["pending_conditions"]["day"]["quote"] == "if I can finish before five"
                )
                return intent("answer", shift="morning")
            return intent("answer", day="Tuesday", focus="day")

        b = Loopback(interpret)
        try:
            await b.c.opening()
            b.frames(6, user=LOUD)
            b.transcript("day", "Tuesday")
            b.labels("day")
            if split:
                b.frames(150)  # Three quiet seconds allow the first contribution to save.
                await asyncio.gather(*b.c.tasks)
                assert b.store.snapshot()["answers"]["day"] == "Tuesday"
            else:
                b.frames(10)  # The candidate continues the same contribution.
            b.frames(6, user=LOUD)
            b.transcript("condition", " if I can finish before five.")
            b.labels("condition", condition="conditional")
            b.frames(100)
            await asyncio.gather(*b.c.tasks)
            assert b.c.workflow.step.kind == "clarify_day"
            assert "if I can finish before five" in b.c.workflow.step.content
            assert b.store.snapshot()["answers"] == {"day": "Tuesday" if split else "", "shift": ""}
            assert b.store.snapshot()["status"] == "active"
            saves = [e for e in b.rows("app.tool") if e["name"] == "record_answer"]
            assert len(saves) == int(split)
            if split:
                b.say("shift", "Morning.")
                await asyncio.gather(*b.c.tasks)
                assert b.store.snapshot()["answers"] == {"day": "Tuesday", "shift": "morning"}
                assert (
                    b.c.workflow.step.kind == "clarify_day"
                    and b.store.snapshot()["status"] == "active"
                )
        finally:
            await b.c.stop()
            b.store.close()

    for split in (False, True):
        asyncio.run(exercise(split))


def test_decisions_recovery_and_delayed_actual_event_reach_shared_owner():
    async def exercise():
        calls, delay = [], asyncio.Event()

        async def interpret(evidence):
            calls.append(evidence)
            return intent("answer", day="Tuesday")

        async def before(event):
            await delay.wait()

        b = Loopback(interpret, before_delegation=before)
        await b.c.opening()
        b.frames(6, user=LOUD)
        b.transcript("source.1", "Tuesday works best.")
        b.labels("source.1")
        native = b.native("d_actual")
        await asyncio.sleep(0)
        b.frames(100)
        await asyncio.sleep(0)
        assert len(calls) == 1 and b.rows("app.route")[0]["reason"] == "decisions_recovery"
        assert b.store.snapshot()["answers"]["day"] == "Tuesday"
        delay.set()
        await asyncio.sleep(0)
        b.c.observe(native, b.clock)
        await asyncio.sleep(0)
        assert [e["disposition"] for e in b.rows("app.delegation_received")] == [
            "turn_already_owned",
            "repeated_delegation",
        ]
        assert [e["delegation_id"] for e in b.rows("app.delivery_released")] == [
            "d_actual",
            "d_actual",
        ]
        assert [e["name"] for e in b.rows("app.tool")] == [
            "get_next_question",
            "record_answer",
            "get_next_question",
        ]
        assert (
            b.sent[-1]["delegation_id"] is None
            and b.sent[-1]["type"] == "session.commentary.append"
        )
        await b.c.stop()

    asyncio.run(exercise())


def test_real_proposal_return_rejected_after_new_source_before_commit():
    async def exercise():
        held, release = asyncio.Event(), asyncio.Event()

        async def interpret(evidence):
            return intent("answer", day="Monday" if evidence["source"]["turn"] == 1 else "Tuesday")

        async def hold(scope, result):
            if scope["turn"] == 1:
                held.set()
                await release.wait()

        b = Loopback(interpret, after_interpret=hold)
        await b.c.opening()
        b.say("monday", "Monday.")
        await held.wait()
        b.say("tuesday", "Actually, make that Tuesday.")
        await asyncio.sleep(0)
        assert b.store.snapshot()["answers"]["day"] == "Tuesday"
        release.set()
        await asyncio.sleep(0)
        assert [(e["source_event_id"], e["reason"]) for e in b.rows("app.stale")] == [
            ("monday", "scope_changed_while_interpreting")
        ]
        assert [e["arguments"] for e in b.rows("app.tool") if e["name"] == "record_answer"] == [
            {"question_id": "day", "value": "Tuesday"}
        ]
        assert b.rows("app.proposal_released")[-1]["source_event_id"] == "monday"
        await b.c.stop()

    asyncio.run(exercise())


def test_held_native_event_bound_to_earlier_turn_cannot_own_correction():
    async def exercise():
        hold = asyncio.Event()

        async def interpret(e):
            return intent("answer", day="Tuesday" if e["source"]["turn"] == 2 else "Monday")

        async def delayed(e):
            await hold.wait()

        b = Loopback(interpret, before_delegation=delayed)
        await b.c.opening()
        b.frames(5, user=LOUD)
        b.transcript("first", "Monday.")
        b.labels("first")
        b.native("d_monday")
        await asyncio.sleep(0)
        b.frames(38)  # A new speech burst starts before any job for Monday settled.
        b.say("second", "Actually, Tuesday, please.")
        await asyncio.sleep(0)
        hold.set()
        await asyncio.sleep(0)
        assert b.store.snapshot()["answers"]["day"] == "Tuesday"
        assert [
            (e["delegation_id"], e["disposition"]) for e in b.rows("app.delegation_received")
        ] == [("d_monday", "old_or_unknown_delegation")]
        assert len([e for e in b.rows("app.tool") if e["name"] == "record_answer"]) == 1
        await b.c.stop()

    asyncio.run(exercise())


def test_decisions_backchannel_has_no_model_request_or_tool_and_native_handoff_is_bound():
    async def exercise():
        calls = []

        async def interpret(e):
            calls.append(e)
            return intent("answer", day="Monday")

        b = Loopback(interpret)
        await b.c.opening()
        b.say("ack", "Mm-hmm.", "no", "incomplete")
        await asyncio.sleep(0)
        assert not calls and len(b.rows("app.tool")) == 1
        b.frames(6, user=LOUD)
        b.transcript("choice", "I can do Monday.")
        b.labels("choice")
        b.native("d_choice")
        await asyncio.sleep(0)
        b.frames(55)
        await asyncio.sleep(0)
        assert len(calls) == 1
        assert b.rows("app.route")[0]["reason"] == "native_delegation"
        assert b.sent[-1]["delegation_id"] == "d_choice"
        await b.c.stop()

    asyncio.run(exercise())


def test_barge_in_and_missing_captions_cannot_confirm_a_summary():
    async def exercise():
        evidence = []

        async def interpret(e):
            evidence.append(e)
            return intent(
                "confirm", delivered=bool(e["assistant_speech_before_this_caller_started"])
            )

        b = Loopback(interpret, day="Monday", shift="morning")
        await b.c.opening()
        summary = b.c.guidance[-1]["content"]
        b.frames(10)
        b.c.observe(
            {
                "type": "session.output_transcript.delta",
                "event_id": "speech/" + str(b.clock),
                "start_ms": b.clock,
                "delta": summary,
            },
            b.clock,
        )
        b.frames(5, agent=LOUD)
        b.say("early", "Yes.")
        await asyncio.sleep(0)
        assert evidence[-1]["summary_playout_ready"] is False
        assert b.c.guidance[-1]["kind"] == "summary" and not b.store.snapshot()["completed"]
        b.frames(5, agent=LOUD)
        b.frames(35)
        b.say("no-captions", "Yes.")
        await asyncio.sleep(0)
        assert (
            not evidence[-1]["summary_playout_ready"]
            and not evidence[-1]["assistant_speech_before_this_caller_started"]
        )
        assert not b.store.snapshot()["completed"]
        b.frames(10)
        b.c.observe(
            {
                "type": "session.output_transcript.delta",
                "event_id": "speech/" + str(b.clock),
                "start_ms": b.clock,
                "delta": summary,
            },
            b.clock,
        )
        b.frames(5, agent=LOUD)
        b.frames(35)
        b.say("current", "Yes, those both work.")
        await asyncio.sleep(0)
        assert b.store.snapshot()["completed"]
        assert len([e for e in b.rows("app.tool") if e["name"] == "complete_interview"]) == 1
        await b.c.stop()

    asyncio.run(exercise())


@pytest.mark.parametrize("cancel", [False, True], ids=["normal-close", "cancel-during-call"])
def test_network_adapter_closes_and_writes_the_receipt(monkeypatch, tmp_path, cancel):
    import base64
    from types import SimpleNamespace
    import aiohttp
    from voice.audio import Recorder, WavAudio
    from interview_app import live

    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.sent = []
            self.closed = False

        async def send_json(self, event):
            self.sent.append(event)
            if event["type"] == "session.start":
                self.queue.put_nowait(
                    {"type": "session.started", "session": {"id": "s1", "model": "live-fixture"}}
                )
            if event["type"] == "session.commentary.append":
                self.queue.put_nowait(
                    {"type": "session.output_audio.delta", "delta": base64.b64encode(LOUD).decode()}
                )
            if event["type"] == "session.close":
                self.queue.put_nowait(
                    {
                        "type": "session.closed",
                        "reason": "client_request",
                        "usage": {"seconds": 0.1},
                    }
                )

        async def receive_json(self, timeout=None):
            return await self.queue.get()

        def __aiter__(self):
            return self

        async def __anext__(self):
            return SimpleNamespace(
                type=aiohttp.WSMsgType.TEXT, data=json.dumps(await self.queue.get())
            )

        async def close(self):
            self.closed = True

    socket = Socket()

    class Http:
        def __init__(self, **kwargs):
            pass

        async def ws_connect(self, url, **kwargs):
            return socket

        async def close(self):
            pass

    monkeypatch.setattr(live.aiohttp, "ClientSession", Http)
    path = tmp_path / "user.wav"
    Recorder.save_mono(path, LOUD)
    received = []

    def collect(row):
        received.append(row)
        if cancel and row["event"]["type"] == "session.input_audio.append":
            asyncio.current_task().cancel()

    call = live.run_interview(
        WavAudio(path), tmp_path / "call", api_key="unit-test", duration=0.1, on_event=collect
    )
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(call)
        receipt = json.loads((tmp_path / "call" / "receipt.json").read_text())
        assert (
            socket.closed
            and receipt["termination"] == "cancelled"
            and receipt["status"] == "incomplete"
        )
        return
    result = asyncio.run(call)
    assert (
        socket.closed
        and result["status"] == "collected"
        and result["final_usage"] == {"seconds": 0.1}
    )
    assert [e["type"] for e in socket.sent if e["type"] != "session.input_audio.append"] == [
        "session.start",
        "session.commentary.append",
        "session.close",
    ]
    guidance = next(e["event"] for e in received if e["event"]["type"] == "app.guidance")
    assert guidance["kind"] == "day" and guidance["source_event_id"] == "s1/open"
    capture = next(e["event"] for e in received if e["event"]["type"] == "app.capture_end")
    assert capture["reason"] == "duration" and capture["output_buffer_bytes"] == 0
    assert result["output_nonzero_bytes"] and (tmp_path / "call" / "conversation.wav").is_file()
    assert all(
        "audio" not in e["event"] and "delta" not in e["event"]
        for e in received
        if "audio" in e["event"]["type"]
    )


def test_restatement_retrieves_official_step_without_new_mutation_request():
    unchanged = Session(day="Tuesday")
    assert unchanged.apply(intent("answer", day="Tuesday")).kind == "shift"
    assert [r["name"] for r in unchanged.tools()] == ["get_next_question", "get_next_question"]
    mixed = Session(day="Tuesday")
    assert mixed.apply(intent("answer", day="Tuesday", shift="morning")).kind == "summary"
    writes = [r["arguments"] for r in mixed.tools() if r["name"] == "record_answer"]
    assert writes == [{"question_id": "shift", "value": "morning"}]
