from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.models import CreateDeploymentRequest, Deployment, Project


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


if __name__ == "__main__":
    unittest.main()
