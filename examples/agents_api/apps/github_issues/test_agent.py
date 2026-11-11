import asyncio
import os
import re
import subprocess
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from examples.agents_api.apps.github_issues import agent as agent_mod
from examples.agents_api.apps.github_issues.agent import investigate_issue

REPORT_UUID = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
REPORT_NAME = f"investigation-{REPORT_UUID.hex}.md"
WORKSPACE_REPORT_PATH = f"/workspace/{REPORT_NAME}"


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


@pytest.fixture
def unique_report(tmp_path: Path):
    with patch(
        "examples.agents_api.apps.github_issues.agent.uuid.uuid4",
        return_value=REPORT_UUID,
    ):
        yield tmp_path / REPORT_NAME


def _init_tracked_investigation(workspace: Path, content: str) -> Path:
    tracked = workspace / "investigation.md"
    tracked.write_text(content)
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(
        ["git", "init"], cwd=workspace, check=True, capture_output=True, env=env
    )
    subprocess.run(
        ["git", "add", "investigation.md"],
        cwd=workspace,
        check=True,
        capture_output=True,
        env=env,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add investigation notes"],
        cwd=workspace,
        check=True,
        capture_output=True,
        env=env,
    )
    return tracked


@pytest.mark.asyncio
async def test_investigate_issue_success(tmp_path: Path, mock_openai, unique_report: Path):
    def generate_events():
        unique_report.write_text("Root cause identified.")
        return [
            MockEvent("agent.session.turn.output_text.delta", delta="Done"),
        ]

    mock_openai.beta.agents.sessions.stream.return_value = MockStreamContext(generate_events)

    result = await investigate_issue({"number": 1, "title": "Crash on launch"}, tmp_path)
    assert result["issue_number"] == 1
    assert result["findings"] == "Root cause identified."
    assert unique_report.read_text() == "Root cause identified."
    instructions = mock_openai.beta.agents.sessions.create.call_args.kwargs["agent"][
        "instructions"
    ]
    assert WORKSPACE_REPORT_PATH in instructions
    assert (tmp_path / "investigation.md").exists() is False


@pytest.mark.asyncio
async def test_investigate_issue_same_content_rerun(
    tmp_path: Path, mock_openai, unique_report: Path
):
    """A fresh unique report is accepted even when its text matches investigation.md."""
    existing = tmp_path / "investigation.md"
    initial_content = "Existing valid investigation."
    existing.write_text(initial_content)

    def generate_events():
        assert existing.read_text() == initial_content
        unique_report.write_text(initial_content)
        return [
            MockEvent("agent.session.turn.output_text.delta", delta="Done"),
        ]

    mock_openai.beta.agents.sessions.stream.return_value = MockStreamContext(generate_events)

    result = await investigate_issue({"number": 1, "title": "Crash on launch"}, tmp_path)
    assert result["findings"] == initial_content
    assert existing.read_text() == initial_content
    assert unique_report.read_text() == initial_content


@pytest.mark.asyncio
async def test_investigate_issue_preserves_existing_report_when_missing(
    tmp_path: Path, mock_openai, unique_report: Path
):
    """If the agent fails to write a report, an existing investigation.md is left intact."""
    report_file = tmp_path / "investigation.md"
    initial_content = "Prior investigation content."
    report_file.write_text(initial_content)

    def generate_events():
        return [
            MockEvent("agent.session.turn.output_text.delta", delta="Done"),
        ]

    mock_openai.beta.agents.sessions.stream.return_value = MockStreamContext(generate_events)

    with pytest.raises(
        RuntimeError, match=re.escape(f"The agent did not create {WORKSPACE_REPORT_PATH}.")
    ):
        await investigate_issue({"number": 1, "title": "Crash on launch"}, tmp_path)

    assert report_file.read_text() == initial_content
    assert unique_report.exists() is False


@pytest.mark.asyncio
async def test_investigate_issue_preserves_existing_report_on_failure(
    tmp_path: Path, mock_openai, unique_report: Path
):
    """If the agent session fails, an existing investigation.md is left intact."""
    report_file = tmp_path / "investigation.md"
    initial_content = "Prior investigation content."
    report_file.write_text(initial_content)

    def generate_events():
        raise RuntimeError("Network disconnect during stream")

    mock_openai.beta.agents.sessions.stream.return_value = MockStreamContext(generate_events)

    with pytest.raises(RuntimeError, match="Network disconnect during stream"):
        await investigate_issue({"number": 1, "title": "Crash on launch"}, tmp_path)

    assert report_file.read_text() == initial_content
    assert unique_report.exists() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["client_init", "client_enter", "session_create"])
async def test_investigate_issue_preserves_report_on_setup_failure(
    tmp_path: Path, mock_openai, unique_report: Path, stage: str
):
    report_file = tmp_path / "investigation.md"
    previous_report = b"Previous investigation.\r\n"
    report_file.write_bytes(previous_report)
    failure = RuntimeError("Investigation setup failed")

    with patch("examples.agents_api.apps.github_issues.agent.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.__aenter__.return_value = mock_openai
        if stage == "client_init":
            mock_cls.side_effect = failure
        elif stage == "client_enter":
            mock_cls.return_value.__aenter__.side_effect = failure
        else:
            mock_openai.beta.agents.sessions.create.side_effect = failure

        with pytest.raises(RuntimeError, match="Investigation setup failed") as caught:
            await investigate_issue({"number": 1, "title": "Crash"}, tmp_path)

    assert caught.value is failure
    assert report_file.read_bytes() == previous_report


@pytest.mark.asyncio
async def test_investigate_issue_preserves_report_on_setup_cancellation(
    tmp_path: Path, mock_openai, unique_report: Path
):
    report_file = tmp_path / "investigation.md"
    report_file.write_bytes(b"Previous investigation.")
    mock_openai.beta.agents.sessions.create.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await investigate_issue({"number": 1, "title": "Crash"}, tmp_path)

    assert report_file.read_bytes() == b"Previous investigation."


@pytest.mark.asyncio
async def test_investigate_issue_preserves_git_tracked_investigation_md(
    tmp_path: Path, mock_openai, unique_report: Path
):
    """A Git-tracked investigation.md stays readable when the executor starts."""
    original = "Project investigation notes from the repository.\n"
    tracked = _init_tracked_investigation(tmp_path, original)
    seen: dict[str, object] = {}
    container = agent_mod.start_executor.return_value

    def start_and_check(*args, **kwargs):
        seen["exists"] = tracked.exists()
        seen["content"] = tracked.read_text()
        return container

    agent_mod.start_executor.side_effect = start_and_check

    def generate_events():
        assert tracked.read_text() == original
        unique_report.write_text("Fresh findings for this issue.")
        return [
            MockEvent("agent.session.turn.output_text.delta", delta="Done"),
        ]

    mock_openai.beta.agents.sessions.stream.return_value = MockStreamContext(generate_events)

    result = await investigate_issue({"number": 1, "title": "Crash on launch"}, tmp_path)

    assert result["findings"] == "Fresh findings for this issue."
    assert unique_report.read_text() == "Fresh findings for this issue."
    assert tracked.read_text() == original
    assert seen == {"exists": True, "content": original}
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "investigation.md"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""
