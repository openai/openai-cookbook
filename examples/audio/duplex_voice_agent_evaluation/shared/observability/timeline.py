"""Timed transcript/audio state and a causally valid, overlap-aware text projection."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from shared.observability.delegation import DelegationState, active_intervals, lifecycle_event


@dataclass(frozen=True, slots=True)
class Transcript:
    role: str
    start_ms: int
    end_ms: int
    text: str
    source: str
    action: str = ""


@dataclass(frozen=True, slots=True)
class Turn:
    role: str
    start_ms: int
    end_ms: int
    transcript: str
    turn_id: str = ""


class TranscriptTurnProjector:
    """Revisable local turns; transcript clocks never become audio timestamps."""

    def __init__(self) -> None:
        self.groups: dict[str, list[dict[str, Any]]] = {"user": [], "assistant": []}
        self.seen: set[tuple[str, str]] = set()
        self._audio_intervals: dict[str, tuple[tuple[int, int], ...]] = {"user": (), "assistant": ()}
        self._quiet_intervals: dict[str, tuple[tuple[int, int], ...]] = {"user": (), "assistant": ()}

    def record(self, role: str, event: dict[str, Any], *, received_ms: int, boundary: int = 0) -> bool:
        text = event.get("delta")
        if not isinstance(text, str) or not text:
            return False
        identifier = event.get("event_id")
        if isinstance(identifier, str):
            if (role, identifier) in self.seen:
                return False
            self.seen.add((role, identifier))
        start, end = event["start_ms"], event["end_ms"]
        groups = self.groups[role]
        group = next(
            (item for item in reversed(groups) if start <= item["end"] + 500 and end + 500 >= item["start"]), None
        )
        if group is None:
            group = {"id": f"local-{role}-{len(groups)}", "start": start, "end": end, "parts": [], "turn": None}
            groups.append(group)
        group.setdefault("first_received_ms", received_ms)
        group["parts"].append((start, end, text))
        group["start"] = min(group["start"], start)
        group["end"] = max(group["end"], end)
        group["received_ms"] = received_ms
        group["boundary"] = max(group.get("boundary", 0), boundary)
        group["dirty"] = True
        group["text_dirty"] = True
        if "owner" in group:
            groups[group["owner"]]["dirty"] = True
        return True

    def pending(self, role: str) -> bool:
        return any(group.get("dirty") for group in self.groups[role])

    def project(
        self,
        role: str,
        intervals: tuple[tuple[int, int], ...],
        *,
        now_ms: int,
        consumed: int = 0,
        quiet_ms: int = 600,
        quiet_intervals: tuple[tuple[int, int], ...] = (),
    ) -> list[Turn]:
        if not intervals and not quiet_intervals:
            return []
        audio_changed = intervals != self._audio_intervals[role] or quiet_intervals != self._quiet_intervals[role]
        self._audio_intervals[role] = intervals
        self._quiet_intervals[role] = quiet_intervals
        episodes: list[tuple[int, int]] = []
        for left, right in intervals:
            if episodes and left <= episodes[-1][1] + 500:
                episodes[-1] = (episodes[-1][0], max(right, episodes[-1][1]))
            else:
                episodes.append((left, right))
        quiet_episodes: list[tuple[int, int]] = []
        for left, right in quiet_intervals:
            if quiet_episodes and left <= quiet_episodes[-1][1] + 500:
                quiet_episodes[-1] = (quiet_episodes[-1][0], max(right, quiet_episodes[-1][1]))
            else:
                quiet_episodes.append((left, right))
        turns: dict[str, Turn] = {}
        previous_end = -1
        groups = self.groups[role]
        owners = [index for index, group in enumerate(groups) if "owner" not in group]
        previous_owner: int | None = None
        for position, index in enumerate(owners):
            group = groups[index]
            members = [item for number, item in enumerate(groups) if item.get("owner", number) == index]
            parts = sorted((part for item in members for part in item["parts"]), key=lambda part: part[:2])
            existing = group["turn"]
            if not group.get("dirty") and not audio_changed:
                previous_end = existing.end_ms if existing is not None else previous_end
                previous_owner = index
                continue
            # A caption may lead its audio and arrive during the previous word.
            # Keep that whole observed interval with the earlier group; never
            # assign its remaining tail to a future caption or clip a word.
            cutoff = groups[owners[position + 1]]["first_received_ms"] if position + 1 < len(owners) else now_ms
            candidates = (
                [episodes[position]]
                if existing is None and len(episodes) == len(owners)
                else [(left, right) for left, right in intervals if right > previous_end and left < cutoff]
            )
            # A quiet match must be a single complete, unclaimed episode. Never
            # clip a neighboring word to manufacture a caption boundary.
            fallback = [
                (left, right)
                for left, right in quiet_episodes
                if left >= previous_end and right <= cutoff and (existing is None or right > existing.start_ms)
            ]
            if len(fallback) != 1:
                fallback = []
            if existing is not None and not candidates:
                candidates = fallback
            if existing is not None:
                candidates = [(left, right) for left, right in candidates if right > existing.start_ms]
                if not any(item.get("text_dirty") for item in members):
                    # Only extend a clean turn across a separate acoustic gap
                    # when its caption span is not yet covered. Otherwise new
                    # untranscribed speech must stay outside the completed turn.
                    growing_interval = any(left < existing.end_ms < right for left, right in candidates)
                    caption_span = max(part[1] for part in parts) - parts[0][0]
                    caption_gap = max(
                        (right[0] - left[1] for left, right in zip(parts, parts[1:], strict=False)), default=0
                    )
                    resolution = min((end - start for start, end, _ in parts if end > start), default=0)
                    tail = [(left, right) for left, right in candidates if right > existing.end_ms]
                    captioned_tail = (
                        existing.end_ms - existing.start_ms < caption_span
                        and tail
                        and tail[0][0] - existing.end_ms <= max(0, caption_gap) + quiet_ms
                        and sum(right - max(left, existing.end_ms) for left, right in tail)
                        <= caption_span - (existing.end_ms - existing.start_ms) + resolution
                    )
                    if not growing_interval and not captioned_tail:
                        group["dirty"] = False
                        previous_end = existing.end_ms
                        previous_owner = index
                        continue
                    group["dirty"] = True
            if (
                max(item["boundary"] for item in members) > consumed
                or now_ms < max(item["received_ms"] for item in members) + quiet_ms
            ):
                break
            if not candidates and existing is None and previous_owner is not None:
                prior = groups[previous_owner]["turn"]
                prior_members = [
                    item for number, item in enumerate(groups) if item.get("owner", number) == previous_owner
                ]
                combined = sorted(
                    (part for item in [*prior_members, *members] for part in item["parts"]), key=lambda part: part[:2]
                )
                resolution = min((end - start for start, end, _ in combined if end > start), default=0)
                shared = any(
                    prior.start_ms <= left <= group["first_received_ms"] <= group["received_ms"]
                    and group["received_ms"] + resolution <= right <= prior.end_ms
                    for left, right in intervals
                )
                # Receipt overlap alone also describes a caption ahead of its
                # audio. Require enough observed span for both caption groups,
                # allowing only their own frame resolution. No clock offset is
                # used to manufacture a word boundary or reported timestamp.
                if shared and max(part[1] for part in combined) - combined[0][0] <= (
                    prior.end_ms - prior.start_ms + resolution
                ):
                    group["owner"] = previous_owner
                    turn = Turn(
                        role, prior.start_ms, prior.end_ms, "".join(part[2] for part in combined).strip(), prior.turn_id
                    )
                    for item in [*prior_members, *members]:
                        item["turn"] = turn
                        item["dirty"] = False
                        item["text_dirty"] = False
                    turns[turn.turn_id] = turn
                    previous_end = turn.end_ms
                    continue
            if not candidates:
                candidates = fallback
            if not candidates or now_ms < candidates[-1][1] + quiet_ms:
                break
            text = "".join(part[2] for part in parts).strip()
            if not text:
                continue
            turn = Turn(role, existing.start_ms if existing else candidates[0][0], candidates[-1][1], text, group["id"])
            for item in members:
                item["turn"] = turn
                item["dirty"] = False
                item["text_dirty"] = False
            if turn != existing:
                turns[turn.turn_id] = turn
            previous_end = turn.end_ms
            previous_owner = index
        return list(turns.values())


@dataclass(frozen=True, slots=True)
class AgentEvent:
    timestamp_ms: int
    event_type: str
    kind: str
    name: str = ""
    status: str = ""
    arguments: Any = None
    result: Any = None
    response_id: str = ""
    call_id: str = ""
    error: str = ""
    delegation_id: str = ""

    def model_dump(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value not in (None, "", {}, [])}

    def transcript_line(self) -> str:
        label = {"delegation": "DELEGATION", "tool": "TOOL", "backend_result": "BACKEND"}[self.kind]
        fields: list[str] = []
        if self.name:
            fields.append(f"name={self.name}" if self.kind == "tool" else f"target={self.name}")
        if self.status:
            fields.append(f"status={self.status}")
        if self.arguments not in (None, "", {}, []):
            fields.append(f"arguments={_display_value(self.arguments)}")
        if self.result not in (None, "", {}, []):
            fields.append(f"result={_display_value(self.result)}")
        if self.error:
            fields.append(f"error={_display_value(self.error)}")
        return f"{label} {self.timestamp_ms}ms: {' '.join(fields)}"


def _display_value(value: Any, limit: int = 240) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return rendered if len(rendered) <= limit else f"{rendered[: limit - 1]}…"


def _parsed_arguments(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _content_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    return " ".join(
        str(part.get("text", "")).strip()
        for part in content
        if isinstance(part, dict) and part.get("type") in {"input_text", "output_text", "text"}
    ).strip()


def _output_item_agent_event(
    item: dict[str, Any],
    kind: str,
    timestamp_ms: int,
    response_id: str,
) -> AgentEvent | None:
    """Summarize a backend output item without mixing it with lifecycle state."""
    item_type = str(item.get("type", ""))
    if item_type.endswith("_call") or item_type.endswith("_call_output"):
        action = item.get("action")
        arguments = action if isinstance(action, dict) else _parsed_arguments(item.get("arguments"))
        return AgentEvent(
            timestamp_ms,
            kind,
            "tool",
            name=str(item.get("name") or item_type.removesuffix("_call").removesuffix("_output")),
            status=str(item.get("status") or ("completed" if kind.endswith(".done") else "called")),
            arguments=arguments,
            result=item.get("output"),
            response_id=response_id,
            call_id=str(item.get("call_id") or ""),
        )
    if kind.endswith(".done") and item_type == "message":
        output = _content_text(item.get("content"))
        if output:
            return AgentEvent(
                timestamp_ms,
                kind,
                "backend_result",
                name="responses",
                status=str(item.get("status", "completed")),
                result=output,
                response_id=response_id,
            )
    return None


def project_agent_event(event: dict[str, Any], timeline_ms: int) -> dict[str, Any]:
    """Place untimed delegation/backend events on the session's shared audio clock."""
    kind = str(event.get("type", ""))
    if (
        kind != "session.delegation.created"
        and not kind.startswith(("response.", "tool.", "client_delegation."))
        and not (kind == "error" and event.get("delegation_id"))
    ):
        return event
    if any(isinstance(event.get(field), int) for field in ("offset_ms", "start_ms", "end_ms")):
        return event
    return {**event, "offset_ms": max(0, timeline_ms)}


class Timeline:
    def __init__(self) -> None:
        self.transcript_projection = TranscriptTurnProjector()
        self._usage_response_ids: set[str] = set()
        self._transcript_event_ids: set[str] = set()
        self.fragments: list[Transcript] = []
        self.provider_fragments: list[Transcript] = []
        self.user_utterances: list[Transcript] = []
        self._user_turn_indices: dict[str, int] = {}
        self.turns: list[Turn] = []
        self.delegations: list[dict] = []
        self.tool_events: list[dict] = []
        self.agent_events: list[AgentEvent] = []
        self.usage: list[dict] = []
        self.last_assistant_audio_ms = -1
        self.last_assistant_speech_ms = -1
        self.last_assistant_text_ms = -1
        self.last_user_text_ms = -1
        self.last_user_speech_ms = -1
        self.assistant_speech_started_ms = -1
        self.delegation_active = False
        self._delegation_state = DelegationState()
        self._lifecycle_events: list[dict[str, Any]] = []
        self.version = 0
        self.content_version = 0
        self.overlap_ms = 0
        self._assistant_intervals: list[tuple[int, int]] = []
        self._user_intervals: list[tuple[int, int]] = []

    def delegation_intervals(self, duration_ms: int) -> tuple[tuple[int, int], ...]:
        """Replay the same correlated reducer used live, without tick rounding."""
        return active_intervals(self._lifecycle_events, max(0, duration_ms))

    def delegation_events(self) -> tuple[dict[str, Any], ...]:
        """Portable lifecycle evidence for saved-result replay, without payloads."""
        return tuple(dict(event) for event in self._lifecycle_events)

    def add_transcript(self, role: str, start_ms: int, end_ms: int, text: str, source: str) -> bool:
        if not text or (not source.endswith("_transcript.delta") and not text.strip()):
            return False
        item = Transcript(
            role, start_ms, end_ms, text if source.endswith("_transcript.delta") else text.strip(), source
        )
        if source.endswith("_transcript.delta"):
            self.provider_fragments.append(item)
            self.version += 1
            self.content_version += 1
            return True  # Provider caption timestamps are not local playout timestamps.
        if item in self.fragments:
            return False
        self.fragments.append(item)
        self.version += 1
        self.content_version += 1
        if role == "assistant":
            self.last_assistant_text_ms = max(self.last_assistant_text_ms, end_ms)
        else:
            self.last_user_text_ms = max(self.last_user_text_ms, end_ms)
        return True

    def add_turn(self, turn: Turn) -> bool:
        if turn in self.turns:
            return False
        for index, existing in enumerate(self.turns):
            if turn.turn_id.startswith("local-") and existing.turn_id == turn.turn_id:
                self.turns[index] = turn
                break
        else:
            self.turns.append(turn)
        self.version += 1
        if turn.turn_id.startswith("local-"):
            self.content_version += 1
            if turn.role == "assistant":
                self.last_assistant_text_ms = max(self.last_assistant_text_ms, turn.end_ms)
            else:
                self.last_user_text_ms = max(self.last_user_text_ms, turn.end_ms)
        return True

    def add_user_utterance(
        self,
        start_ms: int,
        end_ms: int,
        text: str,
        source: str = "simulator.tts",
        *,
        action: str = "",
        turn_id: str = "",
    ) -> bool:
        """Preserve the text actually submitted to user TTS independently of provider ASR."""
        if not text.strip():
            return False
        item = Transcript("user", start_ms, end_ms, text.strip(), source, action)
        if item in self.user_utterances:
            return False
        if turn_id and turn_id in self._user_turn_indices:
            self.user_utterances[self._user_turn_indices[turn_id]] = item
        else:
            if turn_id:
                self._user_turn_indices[turn_id] = len(self.user_utterances)
            self.user_utterances.append(item)
        self.last_user_text_ms = max(self.last_user_text_ms, end_ms)
        self.version += 1
        self.content_version += 1
        return True

    def add_audio(
        self,
        role: str,
        start_ms: int,
        end_ms: int,
        speaking: bool,
        *,
        speech_intervals: list[tuple[int, int]] | None = None,
    ) -> None:
        intervals = speech_intervals if speech_intervals is not None else ([(start_ms, end_ms)] if speaking else [])
        if role == "assistant":
            self.last_assistant_audio_ms = max(self.last_assistant_audio_ms, end_ms)
        own = self._assistant_intervals if role == "assistant" else self._user_intervals
        other = self._user_intervals if role == "assistant" else self._assistant_intervals
        for speech_start, speech_end in intervals:
            if speech_end <= speech_start:
                continue
            if role == "assistant":
                if self.last_assistant_speech_ms < 0 or self.last_assistant_speech_ms < speech_start - 500:
                    self.assistant_speech_started_ms = speech_start
                self.last_assistant_speech_ms = max(self.last_assistant_speech_ms, speech_end)
            else:
                self.last_user_speech_ms = max(self.last_user_speech_ms, speech_end)
            self.overlap_ms += sum(
                max(0, min(speech_end, other_end) - max(speech_start, other_start)) for other_start, other_end in other
            )
            if own and own[-1][1] == speech_start:
                own[-1] = (own[-1][0], speech_end)
            else:
                own.append((speech_start, speech_end))

    def latest_turn(self, role: str) -> Turn | None:
        candidates = [turn for turn in self.turns if turn.role == role]
        return max(candidates, key=lambda turn: turn.end_ms, default=None)

    def speech_intervals(self, role: str) -> tuple[tuple[int, int], ...]:
        if role == "user":
            return tuple(self._user_intervals)
        if role == "assistant":
            return tuple(self._assistant_intervals)
        raise ValueError(f"unknown audio role: {role}")

    @staticmethod
    def _join_text(left: str, right: str) -> str:
        if not left:
            return right
        if not right:
            return left
        if right[0] in ".,!?;:%)]}" or right.startswith(("'", "’")):
            return left.rstrip() + right
        if left[-1] in "([{" or left.endswith(("'", "’")):
            return left + right.lstrip()
        return f"{left.rstrip()} {right.lstrip()}"

    def _audio_bounds(self, role: str, start_ms: int, end_ms: int, *, expand: bool = False) -> tuple[int, int]:
        """Anchor a semantic span to actual speech, retaining its own timestamps as a fallback."""
        intervals = self._assistant_intervals if role == "assistant" else self._user_intervals
        matching = [(start, end) for start, end in intervals if start < end_ms and start_ms < end]
        if matching:
            if expand:
                return matching[0][0], matching[-1][1]
            return max(start_ms, matching[0][0]), min(end_ms, matching[-1][1])
        return start_ms, end_ms

    def _has_acoustic_overlap(self, role: str, start_ms: int, end_ms: int) -> bool:
        own = self._assistant_intervals if role == "assistant" else self._user_intervals
        other = self._user_intervals if role == "assistant" else self._assistant_intervals
        return any(
            max(start_ms, own_start, other_start) < min(end_ms, own_end, other_end)
            for own_start, own_end in own
            for other_start, other_end in other
        )

    def _projected_fragments(self, until_ms: int | None = None) -> list[Transcript]:
        completed_turns = [
            turn
            for turn in self.turns
            if turn.role == "assistant" and turn.transcript.strip() and (until_ms is None or turn.end_ms <= until_ms)
        ]
        visible: list[Transcript] = []
        for item in self.fragments:
            if until_ms is not None and item.end_ms > until_ms:
                continue
            if item.role == "user" and self.user_utterances:
                continue
            if item.role == "assistant" and any(
                (item.start_ms < turn.end_ms and turn.start_ms < item.end_ms)
                or item.text.casefold() in turn.transcript.casefold()
                for turn in completed_turns
            ):
                continue
            start_ms, end_ms = self._audio_bounds(item.role, item.start_ms, item.end_ms)
            if until_ms is None or end_ms <= until_ms:
                visible.append(Transcript(item.role, start_ms, end_ms, item.text, item.source))

        for item in self.user_utterances:
            start_ms, end_ms = self._audio_bounds("user", item.start_ms, item.end_ms, expand=True)
            if until_ms is None or end_ms <= until_ms:
                visible.append(Transcript("user", start_ms, end_ms, item.text, item.source))

        for turn in completed_turns:
            start_ms, end_ms = self._audio_bounds("assistant", turn.start_ms, turn.end_ms, expand=True)
            if until_ms is None or end_ms <= until_ms:
                visible.append(Transcript("assistant", start_ms, end_ms, turn.transcript.strip(), "turn.done"))
        return visible

    def _assistant_text_cut(self, item: Transcript, boundary_ms: int, minimum: int) -> int | None:
        """Prefer streamed transcript boundaries; otherwise split finalized text near the audio ratio."""
        text = item.text
        cursor = 0
        for fragment in sorted(self.fragments, key=lambda part: (part.start_ms, part.end_ms)):
            if fragment.role != "assistant":
                continue
            start_ms, end_ms = self._audio_bounds("assistant", fragment.start_ms, fragment.end_ms)
            if end_ms <= item.start_ms or start_ms >= item.end_ms or end_ms > boundary_ms:
                continue
            fragment_text = fragment.text.strip()
            position = text.casefold().find(fragment_text.casefold(), cursor)
            if position >= 0:
                cursor = position + len(fragment_text)
        if minimum < cursor < len(text) and text[cursor:].strip():
            return cursor

        duration_ms = item.end_ms - item.start_ms
        if duration_ms <= 0:
            return None
        target = round(len(text) * (boundary_ms - item.start_ms) / duration_ms)
        boundaries = [index for index, character in enumerate(text) if character.isspace()]
        candidates = [index for index in boundaries if minimum < index < len(text) and text[index:].strip()]
        return min(candidates, key=lambda index: abs(index - target)) if candidates else None

    def _interleave_assistant_turns(self, visible: list[Transcript]) -> list[Transcript]:
        users = [item for item in visible if item.role == "user"]
        result: list[Transcript] = []
        for item in visible:
            if item.role != "assistant" or item.source != "turn.done":
                result.append(item)
                continue
            interruptions = sorted(
                {
                    user.start_ms
                    for user in users
                    if item.start_ms < user.start_ms < item.end_ms
                    and self._has_acoustic_overlap("user", user.start_ms, user.end_ms)
                }
            )
            start_ms = item.start_ms
            position = 0
            for boundary_ms in interruptions:
                cut = self._assistant_text_cut(item, boundary_ms, position)
                if cut is None:
                    continue
                before = item.text[position:cut].strip()
                if before:
                    result.append(Transcript("assistant", start_ms, boundary_ms, before, item.source))
                    start_ms = boundary_ms
                    position = cut
            remaining = item.text[position:].strip()
            if remaining:
                result.append(Transcript("assistant", start_ms, item.end_ms, remaining, item.source))
        return result

    def _transcript_entries(
        self,
        until_ms: int | None = None,
        integration_ms: int = 500,
        *,
        interleave_overlaps: bool = False,
    ) -> list[tuple[int, str]]:
        visible = self._projected_fragments(until_ms)
        if interleave_overlaps:
            visible = self._interleave_assistant_turns(visible)
            visible.sort(key=lambda item: (item.start_ms, item.role != "user", item.end_ms))
        else:
            visible.sort(key=lambda item: (item.start_ms, item.end_ms, item.role))
        merged: list[Transcript] = []
        for item in visible:
            if (
                merged
                and merged[-1].role == item.role
                and item.source != "simulator.tts"
                and merged[-1].source != "simulator.tts"
                and item.start_ms - merged[-1].end_ms <= integration_ms
            ):
                prior = merged[-1]
                merged[-1] = Transcript(
                    prior.role,
                    prior.start_ms,
                    max(prior.end_ms, item.end_ms),
                    self._join_text(prior.text, item.text),
                    prior.source,
                )
            else:
                merged.append(item)
        entries: list[tuple[int, str]] = []
        for item in merged:
            overlapping = self._has_acoustic_overlap(item.role, item.start_ms, item.end_ms)
            marker = " [OVERLAP]" if overlapping else ""
            entries.append(
                (item.start_ms, f"{item.role.upper()} {item.start_ms}..{item.end_ms}ms{marker}: {item.text}")
            )
        return entries

    def linearized(self, until_ms: int | None = None, integration_ms: int = 500) -> str:
        """Return only spoken conversation, suitable for the text-based user simulator."""
        return "\n".join(line for _, line in self._transcript_entries(until_ms, integration_ms))

    def spoken_text(self, role: str, until_ms: int | None = None) -> str:
        """Return one participant's causally visible spoken words without hidden tool data."""
        if role not in {"user", "assistant"}:
            raise ValueError(f"unknown transcript role: {role}")
        text = ""
        for item in sorted(self._projected_fragments(until_ms), key=lambda item: (item.start_ms, item.end_ms)):
            if item.role == role:
                text = self._join_text(text, item.text)
        return text

    def evaluation_transcript(self) -> str:
        """Interleave spoken conversation with agent actions for evaluation and saved artifacts."""
        entries = [
            (timestamp_ms, 1, index, line)
            for index, (timestamp_ms, line) in enumerate(self._transcript_entries(interleave_overlaps=True))
        ]
        entries.extend(
            (event.timestamp_ms, 0, index, event.transcript_line()) for index, event in enumerate(self.agent_events)
        )
        entries.sort(key=lambda item: (item[0], item[1], item[2]))
        return "\n".join(line for _, _, _, line in entries)

    def _event_timestamp(self, event: dict[str, Any]) -> int:
        for field in ("offset_ms", "start_ms", "end_ms"):
            value = event.get(field)
            if isinstance(value, int):
                return value
        return max(
            self.last_assistant_audio_ms,
            self.last_assistant_text_ms,
            self.last_user_text_ms,
            self.agent_events[-1].timestamp_ms if self.agent_events else -1,
            0,
        )

    def _record_agent_event(self, event: dict[str, Any]) -> AgentEvent | None:
        kind = str(event.get("type", "unknown"))
        item = event.get("delegation") if kind == "session.delegation.created" else event.get("item")
        item = item if isinstance(item, dict) else {}
        response = event.get("response") if isinstance(event.get("response"), dict) else {}
        timestamp_ms = self._event_timestamp(event)
        response_id = str(event.get("response_id") or item.get("response_id") or response.get("id") or "")
        delegation_id = str(
            event.get("delegation_id") or (item.get("id") if kind == "session.delegation.created" else "") or ""
        )
        recorded: AgentEvent | None = None

        if kind == "session.delegation.created":
            recorded = AgentEvent(
                timestamp_ms,
                kind,
                "delegation",
                name=str(item.get("target", event.get("target", "responses"))),
                arguments=_content_text(item.get("content")) or None,
                response_id=response_id,
                delegation_id=delegation_id,
            )
        elif kind in {"client_delegation.completed", "client_delegation.failed"}:
            recorded = AgentEvent(
                timestamp_ms,
                kind,
                "backend_result",
                name="client",
                status=kind.rsplit(".", 1)[-1],
                result=event.get("text"),
                delegation_id=delegation_id,
                error=str(event.get("error") or ""),
            )
        elif kind in {"tool.called", "tool.completed", "tool.failed"}:
            recorded = AgentEvent(
                timestamp_ms,
                kind,
                "tool",
                name=str(event.get("name") or item.get("name") or "unknown"),
                status=kind.rsplit(".", 1)[-1],
                arguments=_parsed_arguments(event.get("arguments", item.get("arguments"))),
                result=event.get("result", event.get("output", item.get("output"))),
                response_id=response_id,
                call_id=str(event.get("call_id") or item.get("call_id") or ""),
                error=str(event.get("error", "")),
            )
        elif kind.startswith("response.web_search_call."):
            status = kind.rsplit(".", 1)[-1]
            recorded = AgentEvent(
                timestamp_ms,
                kind,
                "tool",
                name="web_search",
                status=status,
                arguments=event.get("action") or event.get("arguments"),
                response_id=response_id,
            )
        elif kind in {"response.output_item.added", "response.output_item.done"}:
            recorded = _output_item_agent_event(item, kind, timestamp_ms, response_id)
        elif kind in {"response.completed", "response.failed"}:
            error = response.get("error") or event.get("error") or ""
            recorded = AgentEvent(
                timestamp_ms,
                kind,
                "backend_result",
                name="responses",
                status=str(response.get("status") or kind.rsplit(".", 1)[-1]),
                response_id=response_id,
                error=str(error) if error else "",
            )

        if recorded is not None:
            self.agent_events.append(recorded)
        return recorded

    def apply_event(
        self,
        event: dict,
        assistant_speaking: bool | None = None,
        *,
        speech_intervals: list[tuple[int, int]] | None = None,
    ) -> str | None:
        kind = event.get("type", "unknown")
        normalized = lifecycle_event(event, self._event_timestamp(event))
        if normalized is not None:
            self._lifecycle_events.append(normalized)
            self._delegation_state.apply(normalized)
            self.delegation_active = self._delegation_state.active
            if normalized["type"] != kind:
                # Local controller errors have an explicit delegation_id but
                # no provider terminal event. Retain a normalized terminal so
                # runtime state, saved evidence, and metric replay agree.
                event = {**event, "type": normalized["type"]}
                kind = normalized["type"]
        if kind in {"session.input_transcript.delta", "session.output_transcript.delta"}:
            identifier = event.get("event_id")
            if identifier and identifier in self._transcript_event_ids:
                return None
            if identifier:
                self._transcript_event_ids.add(identifier)
            role = "user" if kind == "session.input_transcript.delta" else "assistant"
            text = str(event.get("delta", ""))
            self.add_transcript(role, int(event.get("start_ms", 0)), int(event.get("end_ms", 0)), text, kind)
            return f"{role.upper()} FRAGMENT: {text}"
        if kind == "turn.done":
            raw = event.get("turn", {})
            turn = Turn(
                str(raw.get("role", "unknown")),
                int(raw.get("start_ms", 0)),
                int(raw.get("end_ms", 0)),
                str(raw.get("transcript", "")),
                str(raw.get("id", "")),
            )
            self.add_turn(turn)
            return f"TURN {turn.role.upper()}: {turn.transcript}"
        if kind == "session.output_audio.delta":
            start = int(event.get("start_ms", event.get("offset_ms", 0)))
            end = int(event.get("end_ms", start))
            self.add_audio("assistant", start, end, bool(assistant_speaking), speech_intervals=speech_intervals)
            return None
        if kind == "session.delegation.created":
            self.delegations.append(event)
            self.version += 1
            self.content_version += 1
            recorded = self._record_agent_event(event)
            return recorded.transcript_line() if recorded is not None else None
        if kind in {"client_delegation.completed", "client_delegation.failed"}:
            self.version += 1
            self.content_version += 1
            recorded = self._record_agent_event(event)
            return recorded.transcript_line() if recorded is not None else kind
        if kind.startswith("response.") or kind.startswith("tool."):
            self.tool_events.append(event)
            if kind == "response.completed":
                usage = event.get("response", {}).get("usage")
                response_id = event.get("response", {}).get("id", "")
                if usage and response_id not in self._usage_response_ids:
                    self._usage_response_ids.add(response_id)
                    self.usage.append({"source": "delegated_response", **usage})
            self.version += 1
            self.content_version += 1
            recorded = self._record_agent_event(event)
            return recorded.transcript_line() if recorded is not None else kind
        if kind in {"session.usage.updated", "session.closed"} and event.get("usage"):
            self.usage.append({"source": "live_frontend", **event["usage"]})
            return "USAGE updated"
        if kind == "error":
            err = event.get("error", {})
            return f"ERROR {err.get('code', '')}: {err.get('message', '')}"
        return None
