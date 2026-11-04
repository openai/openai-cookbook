import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from examples.agents_api.apps.github_issues.agent import investigate_issue


class MockEvent:
    def __init__(self, event_type: str, delta: str = "", text: str = ""):
        self.type = event_type
        self.delta = delta
        self.text = text


class MockStreamContext:
    def __init__(self, events_fn):
        self.events_fn = events_fn

    async def __aenter__(self):
        events = self.events_fn()
        async def event_generator():
            for e in events:
                yield e
        return event_generator()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def mock_openai():
    with patch("examples.agents_api.apps.github_issues.agent.AsyncOpenAI") as mock_cls, \
         patch("examples.agents_api.apps.github_issues.agent.start_executor") as mock_exec:
        client = MagicMock()
        mock_cls.return_value.__aenter__.return_value = client

        # Mock session
        session = MagicMock()
        session.id = "sess_123"
        session.environment = MagicMock()
        session.environment.type = "self_hosted"
        session.environment.id = "env_123"
        session.environment.remote_url = "http://remote"
        client.beta.agents.sessions.create = AsyncMock(return_value=session)
        client.beta.agents.sessions.delete = AsyncMock()

        # Mock container
        container = MagicMock()
        container.remove = MagicMock()
        mock_exec.return_value = container

        yield client


@pytest.mark.asyncio
async def test_investigate_issue_success(tmp_path: Path, mock_openai):
    report_file = tmp_path / "investigation.md"

    def generate_events():
        report_file.write_text("Root cause identified.")
        return [
            MockEvent("agent.session.turn.output_text.delta", delta="Done"),
        ]

    mock_openai.beta.agents.sessions.stream.return_value = MockStreamContext(generate_events)

    result = await investigate_issue({"number": 1, "title": "Crash on launch"}, tmp_path)
    assert result["issue_number"] == 1
    assert result["findings"] == "Root cause identified."
    assert report_file.read_text() == "Root cause identified."


@pytest.mark.asyncio
async def test_investigate_issue_same_content_rerun(tmp_path: Path, mock_openai):
    """Rerunning with identical content must succeed and detect a fresh write."""
    report_file = tmp_path / "investigation.md"
    initial_content = "Existing valid investigation."
    report_file.write_text(initial_content)

    def generate_events():
        # Verify the stale report was removed before the agent wrote fresh output
        assert not report_file.exists()
        # Agent creates report with identical content
        report_file.write_text(initial_content)
        return [
            MockEvent("agent.session.turn.output_text.delta", delta="Done"),
        ]

    mock_openai.beta.agents.sessions.stream.return_value = MockStreamContext(generate_events)

    result = await investigate_issue({"number": 1, "title": "Crash on launch"}, tmp_path)
    assert result["findings"] == initial_content
    assert report_file.read_text() == initial_content


@pytest.mark.asyncio
async def test_investigate_issue_restores_on_missing_report(tmp_path: Path, mock_openai):
    """If the agent fails to write a report, previous report is restored and RuntimeError is raised."""
    report_file = tmp_path / "investigation.md"
    initial_content = "Prior investigation content."
    report_file.write_text(initial_content)

    def generate_events():
        # Agent fails to write any report
        return [
            MockEvent("agent.session.turn.output_text.delta", delta="Done"),
        ]

    mock_openai.beta.agents.sessions.stream.return_value = MockStreamContext(generate_events)

    with pytest.raises(RuntimeError, match="The agent did not create /workspace/investigation.md."):
        await investigate_issue({"number": 1, "title": "Crash on launch"}, tmp_path)

    # Previous report must be restored
    assert report_file.exists()
    assert report_file.read_text() == initial_content


@pytest.mark.asyncio
async def test_investigate_issue_restores_on_failure(tmp_path: Path, mock_openai):
    """If the agent session fails, previous report is restored."""
    report_file = tmp_path / "investigation.md"
    initial_content = "Prior investigation content."
    report_file.write_text(initial_content)

    def generate_events():
        raise RuntimeError("Network disconnect during stream")

    mock_openai.beta.agents.sessions.stream.return_value = MockStreamContext(generate_events)

    with pytest.raises(RuntimeError, match="Network disconnect during stream"):
        await investigate_issue({"number": 1, "title": "Crash on launch"}, tmp_path)

    # Previous report must be restored
    assert report_file.exists()
    assert report_file.read_text() == initial_content
