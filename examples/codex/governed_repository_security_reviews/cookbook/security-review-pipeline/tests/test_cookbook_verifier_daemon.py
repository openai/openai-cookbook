"""The reproduction verifier may validate only the harness's actual local daemon."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("example_verifier", ROOT / "scripts/verify_cookbook_example.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LocalDaemonTests(unittest.TestCase):
    def resolve(self, environment, outputs):
        with mock.patch.dict(os.environ, environment, clear=True):
            with mock.patch.object(MODULE.subprocess, "run", side_effect=[
                SimpleNamespace(stdout=value) for value in outputs
            ]) as command:
                result = MODULE._local_docker_endpoint()
        return result, command.call_args_list

    def test_default_local_socket_is_checked_under_scrubbed_harness_environment(self):
        result, calls = self.resolve({"PATH": os.defpath, "OPENAI_API_KEY": "synthetic-canary"}, ["unix:///tmp/fixture-docker.sock"])
        self.assertEqual(result, "unix:///tmp/fixture-docker.sock")
        self.assertNotIn("OPENAI_API_KEY", calls[0].kwargs["env"])
        self.assertNotIn("HOME", calls[0].kwargs["env"])
        self.assertNotIn("DOCKER_HOST", calls[0].kwargs["env"])

    def test_matching_local_override_is_accepted(self):
        result, _ = self.resolve({"DOCKER_HOST": "unix:///tmp/fixture-docker.sock"}, ["unix:///tmp/fixture-docker.sock"])
        self.assertEqual(result, "unix:///tmp/fixture-docker.sock")

    def test_remote_host_override_is_refused_without_connecting(self):
        with self.assertRaisesRegex(RuntimeError, "Unix-socket"):
            self.resolve({"DOCKER_HOST": "tcp://example.invalid:2375"}, ["unix:///tmp/fixture-docker.sock"])

    def test_remote_default_context_is_refused_without_connecting(self):
        with self.assertRaisesRegex(RuntimeError, "Unix-socket"):
            self.resolve({}, ["ssh://example.invalid"])

    def test_context_takes_precedence_but_must_match_the_harness(self):
        with self.assertRaisesRegex(RuntimeError, "Unix-socket"):
            self.resolve({"DOCKER_CONTEXT": "remote", "DOCKER_HOST": "unix:///tmp/fixture-docker.sock"},
                         ["unix:///tmp/fixture-docker.sock", "tcp://example.invalid:2375"])

    def test_alternate_local_socket_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "default local daemon only"):
            self.resolve({"DOCKER_HOST": "unix:///tmp/other-fixture.sock"}, ["unix:///tmp/fixture-docker.sock"])

    def test_context_cannot_inject_a_cli_option(self):
        with self.assertRaisesRegex(RuntimeError, "context name"):
            self.resolve({"DOCKER_CONTEXT": "--format"}, ["unix:///tmp/fixture-docker.sock"])

    def test_unix_endpoint_with_network_authority_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "Unix-socket"):
            self.resolve({"DOCKER_HOST": "unix://example.invalid/socket"}, ["unix:///tmp/fixture-docker.sock"])

    def test_unix_endpoint_with_query_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "Unix-socket"):
            self.resolve({"DOCKER_HOST": "unix:///tmp/fixture-docker.sock?forward=remote"}, ["unix:///tmp/fixture-docker.sock"])


if __name__ == "__main__":
    unittest.main()
