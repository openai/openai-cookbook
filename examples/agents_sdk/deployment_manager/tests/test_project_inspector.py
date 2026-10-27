from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from app.project_inspector import inspect_project


class ProjectInspectorTests(TestCase):
    def test_detects_required_os_environ_subscript(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            (project_path / "main.py").write_text(
                "import os\n"
                "service_token = os.environ[\"SERVICE_TOKEN\"]\n"
                "service_region = os.environ['SERVICE_REGION']\n",
                encoding="utf-8",
            )

            project = inspect_project(str(project_path))

        self.assertEqual(
            project.required_env,
            ["SERVICE_REGION", "SERVICE_TOKEN"],
        )
