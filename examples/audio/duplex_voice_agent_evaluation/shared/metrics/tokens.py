"""Source-attributed GPT Live frontend and Responses-backend token metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class TokenUsage:
    audio_duration_ms: int | None = None
    total_tokens: int | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    input_audio_tokens: int | None = None
    input_text_tokens: int | None = None
    input_image_tokens: int | None = None
    output_tokens: int | None = None
    cached_output_tokens: int | None = None
    output_audio_tokens: int | None = None
    output_text_tokens: int | None = None
    output_image_tokens: int | None = None
    output_reasoning_tokens: int | None = None
    backend_model_usage: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_mapping(cls, usage: dict[str, Any] | None, *, text_only: bool = False) -> TokenUsage:
        if not isinstance(usage, dict):
            return cls()
        input_details = usage.get("input_token_details") or usage.get("input_tokens_details") or {}
        output_details = usage.get("output_token_details") or usage.get("output_tokens_details") or {}
        if not isinstance(input_details, dict):
            input_details = {}
        if not isinstance(output_details, dict):
            output_details = {}
        input_audio_tokens = input_details.get("audio_tokens", usage.get("input_audio_tokens"))
        input_text_tokens = input_details.get("text_tokens", usage.get("input_text_tokens"))
        input_image_tokens = input_details.get("image_tokens", usage.get("input_image_tokens"))
        input_tokens = usage.get("input_tokens")
        if input_tokens is None:
            input_parts = (input_audio_tokens, input_text_tokens, input_image_tokens)
            observed_input = [int(value) for value in input_parts if isinstance(value, int)]
            input_tokens = sum(observed_input) if observed_input else None
        if text_only and input_text_tokens is None and isinstance(input_tokens, int):
            input_text_tokens = input_tokens
        output_audio_tokens = output_details.get("audio_tokens", usage.get("output_audio_tokens"))
        output_text_tokens = output_details.get("text_tokens", usage.get("output_text_tokens"))
        output_image_tokens = output_details.get("image_tokens", usage.get("output_image_tokens"))
        output_tokens = usage.get("output_tokens")
        if output_tokens is None:
            output_parts = (output_audio_tokens, output_text_tokens, output_image_tokens)
            observed_output = [int(value) for value in output_parts if isinstance(value, int)]
            output_tokens = sum(observed_output) if observed_output else None
        if text_only and output_text_tokens is None and isinstance(output_tokens, int):
            output_text_tokens = output_tokens
        total_tokens = usage.get("total_tokens")
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = int(input_tokens) + int(output_tokens)
        raw_backend_models = usage.get("backend_model_usage")
        backend_models = (
            tuple(dict(item) for item in raw_backend_models if isinstance(item, dict))
            if isinstance(raw_backend_models, list | tuple)
            else ()
        )
        seconds = usage.get("seconds")
        audio_duration_ms = (
            round(seconds * 1_000)
            if isinstance(seconds, (int, float)) and seconds >= 0
            else usage.get("audio_duration_ms")
        )
        return cls(
            audio_duration_ms=audio_duration_ms if isinstance(audio_duration_ms, int) else None,
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            cached_input_tokens=input_details.get("cached_tokens"),
            cache_write_input_tokens=input_details.get("cache_write_tokens"),
            input_audio_tokens=input_audio_tokens,
            input_text_tokens=input_text_tokens,
            input_image_tokens=input_image_tokens,
            output_tokens=output_tokens,
            cached_output_tokens=output_details.get("cached_tokens"),
            output_audio_tokens=output_audio_tokens,
            output_text_tokens=output_text_tokens,
            output_image_tokens=output_image_tokens,
            output_reasoning_tokens=output_details.get("reasoning_tokens"),
            backend_model_usage=backend_models,
        )


def aggregate_backend_usage(usages: list[dict[str, Any]]) -> dict[str, Any]:
    """Count every Responses lifecycle created by one frontend delegation."""
    if not usages:
        return {}
    expanded: list[dict[str, Any]] = []
    for usage in usages:
        nested = usage.get("backend_model_usage")
        if isinstance(nested, list):
            expanded.extend(item for item in nested if isinstance(item, dict))
        else:
            expanded.append(usage)
    if not expanded:
        return {}
    combined: dict[str, Any] = {}
    for field in ("total_tokens", "input_tokens", "output_tokens"):
        values = [usage[field] for usage in expanded if isinstance(usage.get(field), int)]
        if values:
            combined[field] = sum(values)
    for aliases, output_name in (
        (("input_token_details", "input_tokens_details"), "input_tokens_details"),
        (("output_token_details", "output_tokens_details"), "output_tokens_details"),
    ):
        details: dict[str, int] = {}
        for usage in expanded:
            found = next((usage.get(alias) for alias in aliases if isinstance(usage.get(alias), dict)), {})
            for key, value in found.items():
                if isinstance(value, int):
                    details[key] = details.get(key, 0) + value
        if details:
            combined[output_name] = details
    by_model: dict[str, list[dict[str, Any]]] = {}
    for usage in expanded:
        model = usage.get("model")
        if isinstance(model, str) and model:
            by_model.setdefault(model, []).append(usage)
    if by_model:
        model_usage: list[dict[str, Any]] = []
        for model, entries in by_model.items():
            model_totals: dict[str, Any] = {"model": model}
            for field in ("total_tokens", "input_tokens", "output_tokens"):
                values = [entry[field] for entry in entries if isinstance(entry.get(field), int)]
                if values:
                    model_totals[field] = sum(values)
            for aliases, output_name in (
                (("input_token_details", "input_tokens_details"), "input_tokens_details"),
                (("output_token_details", "output_tokens_details"), "output_tokens_details"),
            ):
                details: dict[str, int] = {}
                for entry in entries:
                    found = next((entry.get(alias) for alias in aliases if isinstance(entry.get(alias), dict)), {})
                    for key, value in found.items():
                        if isinstance(value, int):
                            details[key] = details.get(key, 0) + value
                if details:
                    model_totals[output_name] = details
            model_usage.append(model_totals)
        combined["backend_model_usage"] = model_usage
    return combined
