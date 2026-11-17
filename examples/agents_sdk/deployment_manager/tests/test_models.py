from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.models import CreateDeploymentRequest, Deployment, Project
from app.store import Store


class PortValidationTests(unittest.TestCase):
    def test_rejects_ports_outside_tcp_range(self) -> None:
        for port in (-1, 0, 65536, 70000):
            with self.subTest(port=port), self.assertRaises(ValidationError):
                CreateDeploymentRequest(project_id="project-1", port=port)

            with self.subTest(project_port=port), self.assertRaises(ValidationError):
                Project(id="project-1", name="demo", path="/tmp/demo", port=port)

            with self.subTest(deployment_port=port), self.assertRaises(ValidationError):
                Deployment(
                    id="dep-1",
                    project_id="project-1",
                    name="demo",
                    target="local-process",
                    port=port,
                )

    def test_accepts_tcp_port_boundaries(self) -> None:
        for port in (1, 65535):
            with self.subTest(port=port):
                request = CreateDeploymentRequest(project_id="project-1", port=port)
                self.assertEqual(request.port, port)


    def test_existing_invalid_ports_remain_accessible_and_deletable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project-legacy": {
                                "id": "project-legacy",
                                "name": "legacy",
                                "path": "/tmp/legacy",
                                "port": 70000,
                            }
                        },
                        "deployments": {
                            "dep-legacy": {
                                "id": "dep-legacy",
                                "project_id": "project-legacy",
                                "name": "legacy",
                                "target": "local-process",
                                "port": 0,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            store = Store(path)

            self.assertEqual(store.list_projects()[0].port, 70000)
            self.assertEqual(store.get_project("project-legacy").port, 70000)
            self.assertEqual(store.list_deployments()[0].port, 0)
            self.assertEqual(store.get_deployment("dep-legacy").port, 0)
            self.assertTrue(store.delete_deployment("dep-legacy"))
            self.assertEqual(store.list_deployments(), [])

        with self.assertRaises(ValidationError):
            Project(id="new", name="new", path="/tmp/new", port=70000)


if __name__ == "__main__":
    unittest.main()
