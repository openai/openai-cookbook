"""An isolated SQLite applicant tracking system. One connection owns one interview."""

from __future__ import annotations

import json
import sqlite3


from .script import CHOICES, QUESTIONS, summary


class ATS:
    def __init__(self, path=":memory:", *, day="", shift="", fault=None):
        if (day and day not in CHOICES["day"]) or (shift and shift not in CHOICES["shift"]):
            raise ValueError("Unexpected initial availability")
        self.db = sqlite3.connect(path)
        self.fault = fault
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS interview (
                id INTEGER PRIMARY KEY CHECK(id = 1), day TEXT, shift TEXT,
                status TEXT, revision INTEGER);
            CREATE TABLE IF NOT EXISTS operations (
                operation_id TEXT PRIMARY KEY, name TEXT, arguments TEXT, result TEXT);
            CREATE TABLE IF NOT EXISTS retrieved (field TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS pending_conditions (
                field TEXT PRIMARY KEY, choice TEXT, quote TEXT, source_event_id TEXT);
        """)
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO interview VALUES(1, ?, ?, 'active', 0)", (day, shift)
            )
            for field, value in self.snapshot()["answers"].items():
                if value:
                    self.db.execute("INSERT OR IGNORE INTO retrieved VALUES(?)", (field,))

    def snapshot(self):
        day, shift, status, revision = self.db.execute(
            "SELECT day, shift, status, revision FROM interview WHERE id=1"
        ).fetchone()
        return {
            "answers": {"day": day, "shift": shift},
            "status": status,
            "revision": revision,
            "completed": status == "completed",
            "cancelled": status == "cancelled",
        }

    def close(self):
        self.db.close()

    def retrieved_fields(self):
        return {row[0] for row in self.db.execute("SELECT field FROM retrieved")}

    def pending_conditions(self):
        """Application-held qualifications, separate from the ATS answer values."""
        rows = self.db.execute(
            "SELECT field, choice, quote, source_event_id FROM pending_conditions ORDER BY rowid"
        )
        return {
            field: {"choice": choice, "quote": quote, "source_event_id": source}
            for field, choice, quote, source in rows
        }

    def hold_condition(self, field, choice, quote, scope):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            state = self.snapshot()
            if (
                state["status"] != "active"
                or state["revision"] != scope["revision"]
                or field not in self.retrieved_fields()
            ):
                return False
            self.db.execute(
                "INSERT OR REPLACE INTO pending_conditions VALUES(?, ?, ?, ?)",
                (field, choice, quote, scope["source_event_id"]),
            )
            return True

    def _fault(self, name, phase, args, key):
        return bool(self.fault and self.fault(name, phase, args, self.snapshot(), key))

    def execute(self, name, args, *, operation_id, expected_revision, resolves_condition=None):
        """Look up a saved action by ID if its confirmation did not arrive."""
        if not operation_id or not isinstance(args, dict):
            raise ValueError("An operation ID and arguments object are required")
        if self._fault(name, "before", args, operation_id):
            return {"status": "unavailable", "operation_id": operation_id}
        encoded = json.dumps(args, sort_keys=True, separators=(",", ":"))
        with self.db:
            # Take the SQLite writer lock before checking revision and idempotency.
            self.db.execute("BEGIN IMMEDIATE")
            if name == "get_operation":
                row = self.db.execute(
                    "SELECT result FROM operations WHERE operation_id=?",
                    (args.get("operation_id"),),
                ).fetchone()
                return {
                    "status": "ok" if row else "unknown",
                    "receipt": json.loads(row[0]) if row else None,
                }
            prior = self.db.execute(
                "SELECT name, arguments, result FROM operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if prior:
                if prior[:2] != (name, encoded):
                    return {"status": "rejected", "reason": "operation_id_conflict"}
                return {**json.loads(prior[2]), "replayed": True}
            current = self.snapshot()
            if current["revision"] != expected_revision:
                return {"status": "stale", "operation_id": operation_id}
            result = self._execute(name, args, current, resolves_condition)
            result.update(operation_id=operation_id, state=self.snapshot())
            self.db.execute(
                "INSERT INTO operations VALUES(?, ?, ?, ?)",
                (operation_id, name, encoded, json.dumps(result)),
            )
        if self._fault(name, "after", args, operation_id):
            return {"status": "unknown", "operation_id": operation_id}
        return result

    def _execute(self, name, args, current, resolves_condition):
        answers = current["answers"]
        if name == "get_next_question" and not args:
            if current["status"] != "active":
                return {"status": "ok", "step": current["status"]}
            field = next((key for key, value in answers.items() if not value), "summary")
            if field in CHOICES:
                self.db.execute("INSERT OR IGNORE INTO retrieved VALUES(?)", (field,))
                return {
                    "status": "ok",
                    "step": field,
                    "question": QUESTIONS[field],
                    "choices": list(CHOICES[field]),
                }
            text = summary(answers["day"], answers["shift"])
            return {"status": "ok", "step": "summary", "question": text}
        if current["status"] != "active":
            return {"status": "rejected", "reason": "interview_closed"}
        if name == "record_answer" and set(args) == {"question_id", "value"}:
            field, value = args["question_id"], args["value"]
            if (
                field not in CHOICES
                or value not in CHOICES[field]
                or not self.db.execute("SELECT 1 FROM retrieved WHERE field=?", (field,)).fetchone()
            ):
                return {"status": "rejected", "reason": "invalid_or_unretrieved_answer"}
            pending = self.pending_conditions().get(field)
            if pending:
                if pending["source_event_id"] != resolves_condition:
                    return {"status": "rejected", "reason": "unresolved_condition"}
                self.db.execute("DELETE FROM pending_conditions WHERE field=?", (field,))
            if answers[field] == value:
                return {"status": "ok", "changed": False}
            # Column names come from the fixed CHOICES dictionary above.
            self.db.execute(
                f"UPDATE interview SET {field}=?, revision=revision+1 WHERE id=1", (value,)
            )
        elif (
            name == "complete_interview"
            and args == answers
            and all(answers.values())
            and not self.pending_conditions()
        ):
            self.db.execute(
                "UPDATE interview SET status='completed', revision=revision+1 WHERE id=1"
            )
        elif name == "cancel_interview" and not args:
            self.db.execute(
                "UPDATE interview SET status='cancelled', revision=revision+1 WHERE id=1"
            )
        else:
            return {"status": "rejected", "reason": "invalid_operation"}
        return {"status": "ok", "changed": True}
