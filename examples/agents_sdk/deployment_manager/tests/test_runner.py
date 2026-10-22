from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.models import Deployment, Project
from app.runner import start_local_docker, start_local_process


class RunnerReadinessTests(unittest.TestCase):
    def _project(self, path: str) -> Project:
        return Project(
            id="project-1",
            name="demo",
            path=path,
            run_command=["python", "main.py"],
        )

    def test_local_process_timeout_fails_and_terminates_process(self) -> None:
        process = Mock(pid=4321)
        process.poll.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "app.runner._port_is_open", return_value=False
        ), patch("app.runner.subprocess.Popen", return_value=process), patch(
            "app.runner.time.sleep"
        ), patch("app.runner.os.killpg") as killpg:
            deployment = Deployment(
                id="dep-1",
                project_id="project-1",
                name="demo",
                target="local-process",
                port=8123,
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "process did not listen on port 8123 before startup timeout",
            ):
                start_local_process(Path(tmpdir), self._project(tmpdir), deployment)

        killpg.assert_called_once_with(4321, 15)

    def test_local_docker_timeout_fails_and_removes_container(self) -> None:
        build = subprocess.CompletedProcess(["docker"], 0, stdout="", stderr="")
        run = subprocess.CompletedProcess(
            ["docker"], 0, stdout="container-id\n", stderr=""
        )

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "app.runner._port_is_open", return_value=False
        ), patch("app.runner.ensure_dockerfile", return_value=Path(tmpdir) / "Dockerfile"), patch(
            "app.runner._docker_output", side_effect=[build, run]
        ), patch("app.runner._container_is_running", return_value=True), patch(
            "app.runner.read_deployment_log", return_value=""
        ), patch("app.runner._remove_managed_container") as remove_container, patch(
            "app.runner.time.sleep"
        ):
            deployment = Deployment(
                id="dep-2",
                project_id="project-1",
                name="demo",
                target="local-docker",
                port=8124,
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "container did not listen on port 8124 before startup timeout",
            ):
                start_local_docker(Path(tmpdir), self._project(tmpdir), deployment)

        remove_container.assert_any_call("container-id", "dep-2")


if __name__ == "__main__":
    unittest.main()
