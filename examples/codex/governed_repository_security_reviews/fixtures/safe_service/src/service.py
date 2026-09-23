"""Entirely synthetic service with no security finding markers."""


def health() -> dict[str, str]:
    return {"status": "ok"}
