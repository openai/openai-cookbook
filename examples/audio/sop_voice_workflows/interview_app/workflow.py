"""Apply a candidate's answer and retrieve the next question from the ATS."""

from __future__ import annotations

from dataclasses import dataclass

from . import script
from .script import CHOICES, QUESTIONS


@dataclass(frozen=True)
class Step:
    kind: str
    content: str
    choices: tuple = ()


class Interview:
    def __init__(self, store, emit):
        self.store = store
        self.emit = emit
        self.step = None
        self.pending_field = None
        self.paused = False

    def tool(self, name, args, scope, suffix, expected_revision=None, *, resolves_condition=None):
        before = self.store.snapshot()
        key = f"{scope['source_event_id']}/{suffix}"
        expected = scope["revision"] if expected_revision is None else expected_revision
        result = self.store.execute(
            name,
            args,
            operation_id=key,
            expected_revision=expected,
            resolves_condition=resolves_condition,
        )
        self.emit(
            "app.tool",
            name=name,
            arguments=args,
            operation_id=key,
            before=before,
            after=self.store.snapshot(),
            result=result,
            expected_revision=expected,
            turn=scope["turn"],
            source_event_id=scope["source_event_id"],
        )
        if result["status"] == "unknown" and name in {
            "record_answer",
            "complete_interview",
            "cancel_interview",
        }:
            check = self.tool("get_operation", {"operation_id": key}, scope, suffix + "/readback")
            if check["status"] == "ok" and check.get("receipt"):
                return check["receipt"]
            return {"status": "unknown", "operation_id": key}
        return result

    def _failure(self, result, kind, text):
        self.paused = True
        if result["status"] == "unknown":
            return Step("unknown", script.UNKNOWN)
        return Step(kind, text + script.FOLLOW_UP)

    def lookup(self, scope, suffix="next", *, saved_value=None, expected_revision=None):
        result = self.tool("get_next_question", {}, scope, suffix, expected_revision)
        revision = scope["revision"] if expected_revision is None else expected_revision
        if result["status"] != "ok" or result.get("state", {}).get("revision") != revision:
            self.paused = True
            return Step("lookup_unavailable", script.lookup_failed(saved_value))
        kind = result["step"]
        if kind == "completed":
            return Step(kind, script.COMPLETED)
        if kind == "cancelled":
            return Step(kind, script.CANCELLED)
        return Step(kind, result["question"], tuple(result.get("choices", ())))

    def opening(self, session_id):
        scope = {
            "turn": 0,
            "source_event_id": session_id + "/open",
            "revision": self.store.snapshot()["revision"],
        }
        step = self.lookup(scope, "initial")
        if not self.paused and self.store.snapshot()["status"] == "active":
            step = self.pending_step() or step
        return scope, Step(step.kind, script.INTRO + step.content)

    def pending_step(self, *, ask=True):
        pending = self.store.pending_conditions()
        if not pending:
            return None
        field = next(reversed(pending))
        hold = pending[field]
        if not ask:
            return Step("clarify_" + field, script.STILL_PENDING)
        return Step(
            "clarify_" + field, script.pending_question(field, hold["choice"], hold["quote"])
        )

    def clarify(self, focus, conditional=False):
        eligible = self.store.retrieved_fields()
        if focus not in eligible:
            focus = self.pending_field or (
                self.step.kind if self.step and self.step.kind in CHOICES else None
            )
        if focus not in eligible:
            return Step("amend", script.CLARIFY)
        self.pending_field = focus
        content = script.CONDITIONAL[focus] if conditional else QUESTIONS[focus]
        return Step("clarify_" + focus, content)

    def apply(self, scope, intent, condition, summary_ready, *, caller_text=""):
        state = self.store.snapshot()
        if self.paused or state["status"] != "active" or state["revision"] != scope["revision"]:
            return None
        action, focus = intent["action"], intent["focus"]
        pending = self.store.pending_conditions()
        quote = intent.get("condition_evidence", "").strip()
        quote = quote if quote and quote in caller_text else ""
        if (
            focus in CHOICES
            and action in {"conditional", "resolve"}
            and quote.rstrip(".,!?").casefold() == intent[focus].casefold()
        ):
            quote = ""  # Naming the option again supplies no evidence about its condition.
        if action == "backchannel":
            return None
        if action == "cancel":
            if condition != "unconditional":
                return Step("clarify_cancel", script.ASK_CANCEL)
            result = self.tool("cancel_interview", {}, scope, "cancel")
            if result["status"] == "ok":
                return Step("cancelled", script.STOPPED)
            return self._failure(result, "cancel_unavailable", script.CANCEL_FAILED)
        if action == "repeat" and self.step:
            return self.step
        if action == "defer" and pending:
            return Step("deferred", script.DEFERRED)
        if action == "scope":
            detail = self.step.content if self.step else QUESTIONS["day"]
            return Step(self.step.kind if self.step else "day", script.scope_detail(detail))
        if action == "decline":
            if self.step and self.step.kind == "clarify_cancel":
                return self.pending_step() or self.lookup(scope, "continue_interview")
            if pending:
                return self.pending_step()
            return Step("amend", script.AMEND)
        if action in {"answer", "resolve", "confirm", "conditional"} and (
            condition == "conditional" or action == "conditional"
        ):
            eligible = self.store.retrieved_fields()
            if focus == "current":
                named = [
                    field
                    for field in CHOICES
                    if field in eligible and intent[field] in CHOICES[field]
                ]
                focus = (
                    named[0]
                    if len(named) == 1
                    else self.pending_field or (self.step.kind if self.step else None)
                )
            if focus not in eligible:
                return self.pending_step() or self.clarify(focus, conditional=True)
            previous = pending.get(focus, {})
            choice = intent[focus] if intent[focus] in CHOICES[focus] else previous.get("choice")
            requirement = quote if action == "conditional" else ""
            if (
                previous
                and choice == previous["choice"]
                and (not requirement or requirement == previous["quote"])
            ):
                return self.pending_step(ask=False)
            if self.store.hold_condition(focus, choice, requirement, scope):
                self.pending_field = focus
                self.emit(
                    "app.condition_held",
                    field=focus,
                    **self.store.pending_conditions()[focus],
                    turn=scope["turn"],
                )
                return self.pending_step()
            return None
        if action == "confirm":
            if pending:
                return self.pending_step(ask=False)
            if (
                condition != "unconditional"
                or not self.step
                or self.step.kind != "summary"
                or not summary_ready
                or not intent["complete_summary_in_speech"]
            ):
                return self.lookup(scope, "confirmation_needs_summary")
            result = self.tool("complete_interview", state["answers"], scope, "completion")
            if result["status"] == "ok":
                return Step("completed", script.COMPLETED)
            return self._failure(result, "completion_unavailable", script.COMPLETE_FAILED)
        if action in {"unclear", "defer"} or condition != "unconditional":
            if pending:
                return self.pending_step(ask=False)
            if self.step and self.step.kind == "summary" and focus == "current":
                return self.lookup(scope, "repeat_summary")
            return self.clarify(focus)
        if action == "resolve" and focus not in pending:
            return self.pending_step() or self.clarify(focus)
        selected = [(f, intent[f]) for f in CHOICES if intent[f] != "none"]
        eligible = self.store.retrieved_fields()
        next_step = None
        affirmed_saved_value = False
        expected_revision = scope["revision"]
        for field, value in selected:
            if next_step is not None and not state["answers"][field]:
                # The candidate answered a second question. Check that the ATS actually asked for that field.
                if next_step.kind != field or value not in next_step.choices:
                    continue
            elif field not in eligible:
                continue
            hold = pending.get(field)
            if hold:
                alternative = hold["choice"] and value != hold["choice"]
                if not quote or focus != field or (action != "resolve" and not alternative):
                    continue
            if state["answers"][field] == value and not hold:
                affirmed_saved_value = True
                continue
            result = self.tool(
                "record_answer",
                {"question_id": field, "value": value},
                scope,
                "save_" + field,
                expected_revision,
                resolves_condition=hold["source_event_id"] if hold else None,
            )
            if result["status"] != "ok":
                return self._failure(result, "save_unavailable", script.save_failed(field))
            if self.pending_field == field:
                self.pending_field = None
            expected_revision = result["state"]["revision"]
            next_step = self.lookup(
                scope,
                "after_" + field,
                saved_value=result["state"]["answers"][field],
                expected_revision=expected_revision,
            )
            if self.paused:
                return next_step
        outstanding = self.pending_step(ask=False)
        if outstanding or next_step:
            return outstanding or next_step
        if affirmed_saved_value:
            return self.lookup(scope, "unchanged_answer")
        return self.clarify(focus)
