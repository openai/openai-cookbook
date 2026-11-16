"""Normalize supported historical result labels at read boundaries."""

from typing import Any


def is_live_frontend_usage(source: object) -> bool:
    """Accept the former label without emitting it in new result artifacts."""
    return source in ("live_frontend", "bidi")


def normalize_run_configuration(value: object) -> dict[str, Any]:
    """Read pre-2.0 dual-Live reports without restoring retired caller backends."""
    if not isinstance(value, dict):
        raise ValueError("RUN configuration must be an object")
    configuration = dict(value)
    legacy_backend = configuration.pop("user_backend", None)
    if legacy_backend not in (None, "gpt-live", "offline_fixture"):
        raise ValueError("The conversation viewer no longer supports legacy RUN caller backends")
    return configuration


def normalize_run_observability(value: object) -> dict[str, Any]:
    """Keep useful inferred observations from 1.x; discard floor-control state."""
    observations = dict(value) if isinstance(value, dict) else {}
    legacy_floor = observations.pop("floor", {})
    interaction = observations.get("interaction")
    if not isinstance(interaction, dict):
        interaction = legacy_floor if isinstance(legacy_floor, dict) else {}
    actions = interaction.get("caller_actions", {})
    observations["interaction"] = {
        "attribution": "post_hoc_audio_and_transcript",
        "caller_actions": {
            name: count
            for name, count in (actions.items() if isinstance(actions, dict) else ())
            if name in {"OPENING", "SPEAK", "BACKCHANNEL", "INTERRUPT", "STOP"} and type(count) is int and count >= 0
        },
    }
    return observations
