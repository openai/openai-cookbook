from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def deterministic_demo_travel_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COOKBOOK_DEMO_TRAVEL_DATE", "2099-09-21")
