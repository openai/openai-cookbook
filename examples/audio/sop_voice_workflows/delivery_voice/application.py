"""Blossom Store's client-delegated voice workflow."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import json

from voice.audio import RATE
from delivery import backend
from delivery.store import Store

TURN_TIMEOUT_SECONDS = 30


def has_voice(pcm):
    samples = memoryview(pcm).cast("h")
    return bool(samples) and sum(s * s for s in samples) > len(samples) * 120**2


def session_start():
    return {
        "type": "session.start",
        "event_id": "blossom_start",
        "session": {
            "model": "gpt-live-1",
            "instructions": (backend.ROOT / "live_prompt.txt").read_text(),
            "audio": {"format": {"type": "audio/pcm", "rate": RATE}, "output": {"voice": "marin"}},
            "delegation": {"type": "client"},
        },
    }


@dataclass
class Offer:
    kind: str
    ref: str
    facts: dict
    revision: int
    after_ms: int
    words: str = ""
    repeated: bool = False
    heard_ms: int | None = None


class Application:
    """Handle GPT-Live handoffs and check the offer before the store changes an order."""

    def __init__(self, bundle, model, send, sender, *, store=None):
        self.bundle, self.model, self.send, self.sender = bundle, model, send, sender
        self.store = store if store is not None else Store({})
        self.turns = {}
        self.requests = []
        self.jobs = set()
        self.closed = False
        self.input_active = False
        self.last_input_voice = -9999
        self.last_output_voice = -9999
        self.verified_offer = {}
        self.offer = None
        self.interrupted = None
        self.presented = set()
        self.owners = {}
        self.started = set()
        self.errors = []
        self.start_event = session_start()

    def log(self, kind, **fields):
        return self.bundle.emit("app." + kind, **fields)

    def snapshot(self):
        return {
            "model": self.model,
            "reasoning_effort": "low",
            "mode": "client_delegated_responses",
            "store": self.store.snapshot(),
            "store_log": self.store.log,
            "turns": self.turns,
            "errors": self.errors,
            "requests": self.requests,
        }

    def busy(self):
        return bool(self.jobs)

    async def opening(self, _session):
        pass

    def start_turn(self, now):
        # GPT-Live can repeat an offer on its own. Keep that offer only if it is
        # still current when the customer starts replying.
        previous = self.offer
        if previous and previous.heard_ms is not None:
            if self.store.present(
                previous.kind,
                previous.ref,
                revision=previous.revision,
                words=previous.words,
                context=backend.conversation_context(self.history(previous.revision)),
            ):
                self.presented.add(previous.revision)
                self.log(
                    "presentation",
                    revision=previous.revision,
                    ref=previous.ref,
                    accepted=True,
                    words=previous.words,
                    heard_ms=previous.heard_ms,
                )
        self.interrupted = (
            previous if previous and previous.revision not in self.presented else None
        )
        rev = self.store.new_turn()
        self.turns[rev] = {
            "start_ms": now,
            "heard_input": "",
            "output_caption": "",
            "tools": [],
            "fragments": {},
            "output_fragments": {},
            "interrupted_offer": bool(self.interrupted),
        }
        self.offer = None
        self.log("input_speech_onset", revision=rev, media_ms=now)

    def frame(self, incoming, played, elapsed):
        if self.closed:
            return
        now = self.bundle.media_ms
        speaking = has_voice(incoming)
        if speaking:
            if now - self.last_input_voice > 1250:
                self.start_turn(now)
            elif not self.input_active:
                self.store.update_reply(self.store.revision, "")
            self.last_input_voice = now
            if self.interrupted and self.offer:
                self.offer.after_ms = max(self.offer.after_ms, now + 20)
                self.offer.words = ""
                self.offer.heard_ms = None
        self.input_active = speaking
        offer = self.offer
        if has_voice(played):
            self.last_output_voice = now
            if offer:
                offer.heard_ms = None
        if (
            offer
            and offer.words
            and offer.heard_ms is None
            and self.last_output_voice >= offer.after_ms
            and now - self.last_output_voice >= 520
            and not self.bundle.remaining_native_voice
        ):
            # Keep the spoken offer here. Review consent if the backend later asks to change the order.
            offer.heard_ms = now

    def by_offset(self, offset):
        if type(offset) is int and offset >= 0:
            return next(
                (n for n in reversed(self.turns) if self.turns[n]["start_ms"] <= offset), None
            )

    def observe(self, e, elapsed):
        if self.closed:
            return
        kind = e.get("type")
        if kind == "session.delegation.created":
            d = e.get("delegation", {})
            owner = d.get("id")
            if d.get("target") != "client" or not owner:
                return
            rev = self.by_offset(e.get("offset_ms"))
            if rev is None or rev != self.store.revision:
                self.log(
                    "delegation_ignored", revision=rev, owner=owner, reason="old_or_unknown_turn"
                )
            elif rev in self.owners or owner in self.owners.values():
                self.log("delegation_ignored", revision=rev, owner=owner, reason="already_owned")
            else:
                self.owners[rev] = owner
                self.log("delegation_bound", revision=rev, owner=owner)
        elif kind in ("session.input_transcript.delta", "session.output_transcript.delta"):
            start, end = e.get("start_ms"), e.get("end_ms")
            rev = self.by_offset(start)
            if rev is None or rev != self.by_offset(end) or end < start:
                return
            turn = self.turns[rev]
            if kind == "session.output_transcript.delta":
                delta = e["delta"]
                key = e.get("event_id") or json.dumps([start, end, delta])
                if key in turn["output_fragments"]:
                    return
                turn["output_fragments"][key] = (start, end, delta)
                captions = sorted(turn["output_fragments"].values(), key=lambda part: part[:2])
                turn["output_caption"] = "".join(part[2] for part in captions)
                if self.offer and start >= self.offer.after_ms and self.offer.revision == rev:
                    self.offer.words = "".join(
                        part[2] for part in captions if part[0] >= self.offer.after_ms
                    )
                    self.offer.heard_ms = None
            elif (
                rev == self.store.revision
                and e.get("event_id")
                and e["event_id"] not in turn["fragments"]
            ):
                turn["fragments"][e["event_id"]] = (start, end, e["delta"])
                previous = turn["heard_input"]
                parts = sorted(turn["fragments"].values(), key=lambda part: part[:2])
                turn["heard_input"] = "".join(part[2] for part in parts)
                if turn["heard_input"] != previous and turn.pop("answered", False):
                    # A caption can finish after the backend already answered its first part.
                    self.started.discard(rev)
                    self.offer = None
                self.store.update_reply(rev, turn["heard_input"])
                turn["last_transcript_ms"] = self.bundle.media_ms
                if self.interrupted:
                    # To repeat an interrupted offer, use only speech delivered after the interruption.
                    after = max(
                        self.last_input_voice + 20,
                        max(part[1] for part in turn["fragments"].values()),
                    )
                    self.offer = replace(
                        self.interrupted,
                        revision=rev,
                        after_ms=after,
                        words="",
                        repeated=False,
                        heard_ms=None,
                    )

    def history(self, rev):
        history = []
        for n in sorted(self.turns):
            if n > rev:
                break
            t = self.turns[n]
            history.append({"speaker": "caller", "words": t["heard_input"]})
            if t.get("interrupted_offer"):
                history.append(
                    {
                        "application": "The caller interrupted before the offer was complete. If they still want it, restate the terms and ask for permission again."
                    }
                )
            history.extend(t["tools"])
            if n < rev and t["output_caption"]:
                history.append({"speaker": "agent", "words": t["output_caption"]})
        return history

    async def backend(self, rev, owner):
        caller_reply = self.turns[rev]["heard_input"]
        if self.closed or not self.store.is_current_reply(rev, caller_reply):
            self.started.discard(rev)
            return
        try:
            async with asyncio.timeout(TURN_TIMEOUT_SECONDS):
                guidance = await self.respond(rev, owner, caller_reply)
        except (TimeoutError, OSError, RuntimeError) as exc:
            error = type(exc).__name__
            self.errors.append(error)
            self.log("backend_error", revision=rev, detail=error)
            if self.closed or not self.store.is_current_reply(rev, caller_reply):
                self.started.discard(rev)
                return
            guidance = "I couldn't verify your request. Please contact Blossom Store support to check its status."
            for record in reversed(self.turns[rev]["tools"]):
                result = record.get("verified_result", {})
                if record.get("tool") not in ("register_credit", "create_replacement"):
                    continue
                if result.get("status") in ("registered", "already_registered"):
                    guidance = f"Your credit was registered for processing. Your reference is {result['refund_id']}."
                elif result.get("status") in ("created", "already_created"):
                    guidance = f"Your replacement was created. Your reference is {result['replacement_id']}."
                break
        if guidance is not None:
            turn = self.turns[rev]
            turn["answered"] = True
            await self.send(
                {
                    "type": "session.commentary.append",
                    "event_id": f"guidance_{rev}_{len(turn['fragments'])}",
                    "delegation_id": owner,
                    "content": guidance,
                }
            )

    async def respond(self, rev, owner, caller_reply):
        exchanges = []
        history = self.history(rev)
        for step in range(16):
            req = backend.request(self.model, history, exchanges)
            row, receipt = await self.sender(req, rev, step)
            self.requests.append(receipt)
            self.bundle.requests.append(receipt)
            if self.closed or not self.store.is_current_reply(rev, caller_reply):
                self.log(
                    "outdated_response",
                    revision=rev,
                    current=self.store.revision,
                    kind_proposed=row["type"],
                )
                self.started.discard(rev)
                return
            if row["type"] == "error":
                raise RuntimeError("The Responses backend could not finish the request.")
            if row["type"] == "reply":
                self.interrupted = None
                self.offer = None
                ref = row["offer_ref"]
                kind = row["offer_kind"]
                if (
                    ref
                    and kind in ("credit", "replacement")
                    and ref
                    == self.verified_offer.get("quote_id" if kind == "credit" else "offer_id")
                ):
                    self.offer = Offer(kind, ref, self.verified_offer, rev, self.bundle.media_ms)
                self.log(
                    "guidance",
                    revision=rev,
                    owner=owner,
                    **{k: v for k, v in row.items() if k != "type"},
                )
                return row["reply"]
            name, args, call_id = row["name"], row["args"], row["call_id"]

            def record_review(review, receipt):
                self.log("consent_review", revision=rev, **review)
                self.requests.append(receipt)
                self.bundle.requests.append(receipt)

            result = await backend.dispatch_tool(
                self.store,
                name,
                args,
                revision=rev,
                call_id=call_id,
                send=self.sender,
                step=step,
                on_review=record_review,
            )
            if (
                result["status"] == "stale"
                or self.closed
                or not self.store.is_current_reply(rev, caller_reply)
            ):
                self.log(
                    "outdated_response",
                    revision=rev,
                    current=self.store.revision,
                    kind_proposed="tool",
                    result=result,
                )
                self.started.discard(rev)
                return
            self.log("tool", revision=rev, name=name, args=args, call_id=call_id, result=result)
            self.turns[rev]["tools"].append(
                {"tool": name, "arguments": args, "verified_result": result}
            )
            if name in ("check_replacement_availability", "check_credit_eligibility"):
                self.interrupted = None
                self.offer = None
                self.verified_offer = result
            exchanges.extend(row["continuation"])
            exchanges.append(
                {"type": "function_call_output", "call_id": call_id, "output": json.dumps(result)}
            )
        raise RuntimeError("Runaway tool sequence on one caller turn")

    async def tick(self):
        if self.closed:
            return
        rev = self.store.revision
        now = self.bundle.media_ms
        offer = self.offer
        if (
            offer
            and offer.heard_ms is None
            and not offer.repeated
            and rev not in self.presented
            and now - offer.after_ms >= 5500
            and now - self.last_output_voice >= 1400
            and not self.input_active
            and now - self.last_input_voice >= 780
            and not self.bundle.remaining_native_voice
        ):
            # Ask GPT-Live to repeat the offer once, then wait for the new speech.
            offer.repeated = True
            offer.words = ""
            offer.after_ms = now
            if offer.kind == "credit":
                terms = (
                    f"A ${offer.facts['amount']:g} credit to the {offer.facts['payment_method']}."
                )
            else:
                terms = f"A replacement {offer.facts['item']} at no charge, sent to the {offer.facts['destination']}."
            self.log("offer_restate", revision=rev, ref=offer.ref)
            await self.send(
                {
                    "type": "session.commentary.append",
                    "event_id": f"restate_{rev}",
                    "delegation_id": None,
                    "content": f"{terms} Would you like me to arrange that?",
                }
            )
        if rev and rev in self.owners and rev not in self.started:
            t = self.turns[rev]
            if (
                self.store.is_current_reply(rev, t["heard_input"])
                and now - self.last_input_voice >= 780
                and now - t.get("last_transcript_ms", now) >= 360
            ):
                self.started.add(rev)
                task = asyncio.create_task(self.backend(rev, self.owners[rev]))
                self.jobs.add(task)

                def done(job):
                    self.jobs.discard(job)
                    if not job.cancelled() and job.exception():
                        error = type(job.exception()).__name__
                        self.errors.append(error)
                        self.log("backend_error", revision=rev, detail=error)

                task.add_done_callback(done)

    async def close(self):
        self.closed = True
        self.store.update_reply(self.store.revision, "")
        for t in tuple(self.jobs):
            t.cancel()
        await asyncio.gather(*self.jobs, return_exceptions=True)
