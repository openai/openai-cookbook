"""New container fail-closed checks and opt-in genuine restricted Docker probes."""
from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from stress_helpers import EVIDENCE, ROOT, PrivateRecipeCase, append_container_receipt
from support import approve_scope, pipeline, repository
from field_autonomy.policy import PolicyViolation
from field_autonomy.sandbox import ContainerConfiguration, ContainerExecutor, ContainerRuntime, scrubbed_environment
from fleet_security import FleetPolicy, InventoryError, SyntheticScanner
from fleet_security.recipe import RecipeConfiguration
from fleet_security.reproduction import (
    DEMO_ATTEMPTED_REPOSITORIES, DEMO_EXPECTED_STATUSES,
    ReproductionFailure, assert_cycle_accounting,
)
from fleet_security.scanner import parse_restricted_content_refusal, restricted_isolation_verified


class RetryAwareSoakAccountingStress(unittest.TestCase):
    """Exercise soak accounting deterministically without a Docker daemon."""

    @classmethod
    def setUpClass(cls) -> None:
        specification = importlib.util.spec_from_file_location(
            "retry_aware_soak_accounting", ROOT / "scripts" / "run_security_stress_soak.py",
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        cls.soak = module.StressSoak
        cls.instrumentation_type = module.RuntimeInstrumentation
        cls.stress_failure = module.StressFailure

    def observe_stubbed_executor(self, returncode: int, stdout: str):
        """Classify a test double; this helper never invokes a Docker command."""
        observed = self.instrumentation_type()
        executor = SimpleNamespace(container_names=[])

        def stubbed_run(executor, arguments, *, timeout):
            executor.container_names.append("synthetic-instrumentation-only")
            return subprocess.CompletedProcess(arguments, returncode, stdout=stdout, stderr="")

        self.latest_instrumentation = observed
        with patch.object(ContainerExecutor, "run", new=stubbed_run):
            with observed.install():
                ContainerExecutor.run(executor, ["synthetic-no-execution"], timeout=1)
        return observed

    def test_malformed_success_output_never_counts_as_verified_isolation(self) -> None:
        observed = self.observe_stubbed_executor(0, "synthetic malformed receipt")
        receipt = observed.containers[0]
        self.assertEqual(receipt["status"], "completed_unverified_receipt")
        self.assertTrue(receipt["container_started"])
        self.assertEqual(receipt["start_evidence"], "successful_worker_exit")
        self.assertFalse(receipt["isolation_verified"])
        self.assertEqual(observed.launch_metrics(observed.containers), {
            "executor_run_invocations": 1, "actual_container_starts": 1,
            "rejected_container_launches": 0, "unresolved_container_starts": 0,
        })

    def test_daemon_exit_125_is_not_claimed_as_started_container(self) -> None:
        observed = self.observe_stubbed_executor(125, "")
        self.assertEqual(observed.containers[0]["status"], "launch_rejected")
        self.assertFalse(observed.containers[0]["container_started"])
        self.assertEqual(observed.launch_metrics(observed.containers), {
            "executor_run_invocations": 1, "actual_container_starts": 0,
            "rejected_container_launches": 1, "unresolved_container_starts": 0,
        })

    def test_ambiguous_killed_exit_is_reported_as_unresolved_start(self) -> None:
        observed = self.observe_stubbed_executor(137, "")
        self.assertEqual(observed.containers[0]["status"], "unresolved_worker_failure")
        self.assertEqual(observed.launch_metrics(observed.containers), {
            "executor_run_invocations": 1, "actual_container_starts": 0,
            "rejected_container_launches": 0, "unresolved_container_starts": 1,
        })

    def test_only_trusted_refusal_protocol_proves_hostile_worker_exit(self) -> None:
        observed = self.observe_stubbed_executor(65, json.dumps({
            "status": "refused_untrusted_content", "reason_code": "repository_instruction",
        }))
        self.assertEqual(observed.containers[0]["status"], "hostile_or_failed_exit")
        self.assertTrue(observed.containers[0]["container_started"])
        self.assertFalse(observed.containers[0]["isolation_verified"])
        unknown = self.observe_stubbed_executor(65, "synthetic malformed refusal")
        self.assertFalse(unknown.containers[0]["container_started"])
        self.assertEqual(unknown.containers[0]["status"], "unresolved_worker_failure")

    def test_mandatory_isolation_failure_remains_a_hard_failure(self) -> None:
        with self.assertRaises(self.stress_failure):
            self.observe_stubbed_executor(0, json.dumps({
                "uid": 65532, "effectiveCapabilities": "0", "networkBlocked": False,
            }))
        receipt = self.latest_instrumentation.containers[0]
        self.assertEqual(receipt["status"], "launch_or_policy_failure")
        self.assertFalse(receipt["isolation_verified"])

    @staticmethod
    def complete_isolation_receipt() -> dict:
        return {
            "matches": [], "uid": 65532, "networkBlocked": True, "rootReadOnly": True,
            "mountChecks": {
                "source": "read_only", "protectedTests": "read_only", "scratch": "writable",
            },
            "effectiveCapabilities": "0000000000000000", "noNewPrivileges": "1",
            "hiddenPathPresence": {
                "/var/run/docker.sock": False, "/workspace/.env.local": False,
                "/workspace/.git": False, "/Users": False, "/host": False,
            },
            "credentialPresence": {
                "OPENAI_API_KEY": False, "CODEX_API_KEY": False, "GITHUB_TOKEN": False,
                "GH_TOKEN": False, "OPENAI_WEBHOOK_SECRET": False, "AWS_SECRET_ACCESS_KEY": False,
            },
        }

    def assert_incomplete_isolation_refused(self, payload: dict) -> None:
        self.assertFalse(restricted_isolation_verified(payload))
        with self.assertRaises(self.stress_failure):
            self.observe_stubbed_executor(0, json.dumps(payload))
        receipt = self.latest_instrumentation.containers[0]
        self.assertEqual(receipt["status"], "launch_or_policy_failure")
        self.assertFalse(receipt["isolation_verified"])

    def test_complete_exact_isolation_receipt_uses_canonical_verification(self) -> None:
        payload = self.complete_isolation_receipt()
        self.assertTrue(restricted_isolation_verified(payload))
        observed = self.observe_stubbed_executor(0, json.dumps(payload))
        self.assertEqual(observed.containers[0]["status"], "completed")
        self.assertTrue(observed.containers[0]["isolation_verified"])
        self.assertEqual(observed.containers[0]["start_evidence"], "validated_isolation_receipt")

    def test_omitted_or_empty_presence_maps_never_prove_isolation(self) -> None:
        for field in ("hiddenPathPresence", "credentialPresence"):
            for mutation in ("omit", "empty"):
                with self.subTest(field=field, mutation=mutation):
                    payload = self.complete_isolation_receipt()
                    if mutation == "omit":
                        payload.pop(field)
                    else:
                        payload[field] = {}
                    self.assert_incomplete_isolation_refused(payload)

    def test_presence_maps_require_exact_keys_and_mapping_types(self) -> None:
        for field in ("hiddenPathPresence", "credentialPresence"):
            for mutation in ("missing_key", "extra_key", "wrong_key", "list", "null", "false"):
                with self.subTest(field=field, mutation=mutation):
                    payload = self.complete_isolation_receipt()
                    first_key = next(iter(payload[field]))
                    if mutation in {"missing_key", "wrong_key"}:
                        payload[field].pop(first_key)
                    if mutation in {"extra_key", "wrong_key"}:
                        payload[field]["synthetic-unexpected-field"] = False
                    if mutation == "list":
                        payload[field] = []
                    elif mutation == "null":
                        payload[field] = None
                    elif mutation == "false":
                        payload[field] = False
                    self.assert_incomplete_isolation_refused(payload)

    def test_presence_map_values_must_be_literal_false_not_merely_falsey(self) -> None:
        for field in ("hiddenPathPresence", "credentialPresence"):
            for invalid in (0, None, "", [], {}, True, "false"):
                with self.subTest(field=field, invalid_type=type(invalid).__name__):
                    payload = self.complete_isolation_receipt()
                    payload[field][next(iter(payload[field]))] = invalid
                    self.assert_incomplete_isolation_refused(payload)

    def test_omitted_or_non_exact_integer_uid_never_proves_isolation(self) -> None:
        for invalid in (None, 0, "0", "65532", 65532.0, True, 65533):
            with self.subTest(uid_type=type(invalid).__name__, omitted=invalid is None):
                payload = self.complete_isolation_receipt()
                if invalid is None:
                    payload.pop("uid")
                else:
                    payload["uid"] = invalid
                self.assert_incomplete_isolation_refused(payload)

    def test_593_character_refusal_does_not_prove_a_trusted_worker_start(self) -> None:
        refusal = json.dumps({
            "status": "refused_untrusted_content", "reason_code": "repository_instruction",
        })
        refusal += " " * (593 - len(refusal))
        self.assertEqual(len(refusal), 593)
        self.assertIsNone(parse_restricted_content_refusal(65, refusal))
        observed = self.observe_stubbed_executor(65, refusal)
        receipt = observed.containers[0]
        self.assertEqual(receipt["status"], "unresolved_worker_failure")
        self.assertFalse(receipt["container_started"])
        self.assertFalse(receipt["isolation_verified"])
        self.assertIsNone(receipt["refusal_reason_code"])

    def test_refusal_protocol_requires_exact_keys_types_and_allowlisted_reason(self) -> None:
        valid = {"status": "refused_untrusted_content", "reason_code": "repository_instruction"}
        cases = (
            (65.0, valid), ("65", valid),
            (65, {**valid, "extra": False}),
            (65, {"status": "refused_untrusted_content"}),
            (65, {**valid, "reason_code": True}),
            (65, {**valid, "reason_code": "synthetic_unknown_reason"}),
        )
        for index, (returncode, payload) in enumerate(cases):
            with self.subTest(case=index):
                observed = self.observe_stubbed_executor(returncode, json.dumps(payload))
                self.assertEqual(observed.containers[0]["status"], "unresolved_worker_failure")
                self.assertFalse(observed.containers[0]["container_started"])
                self.assertIsNone(observed.containers[0]["refusal_reason_code"])

    def observe_stubbed_timeout(self, *, running: bool):
        observed = self.instrumentation_type()
        removals = []
        executor = SimpleNamespace(
            container_names=[],
            _inspect=lambda name: subprocess.CompletedProcess(
                ["synthetic-inspect-only", name], 0 if running else 1,
                stdout="running\n" if running else "", stderr="",
            ),
        )

        def stubbed_remove(executor, name):
            removals.append(name)

        def stubbed_run(executor, arguments, *, timeout):
            name = "synthetic-timeout-instrumentation-only"
            executor.container_names.append(name)
            ContainerExecutor._remove(executor, name)
            raise subprocess.TimeoutExpired(arguments, timeout)

        with patch.object(ContainerExecutor, "_remove", new=stubbed_remove):
            with patch.object(ContainerExecutor, "run", new=stubbed_run):
                with observed.install(), self.assertRaises(subprocess.TimeoutExpired):
                    ContainerExecutor.run(executor, ["synthetic-no-execution"], timeout=1)
        self.assertEqual(removals, ["synthetic-timeout-instrumentation-only"])
        return observed

    def test_timeout_start_requires_pre_cleanup_running_observation(self) -> None:
        observed = self.observe_stubbed_timeout(running=True)
        receipt = observed.containers[0]
        self.assertEqual(receipt["status"], "timeout_forced_cleanup")
        self.assertTrue(receipt["container_started"])
        self.assertEqual(receipt["start_evidence"], "daemon_running_before_forced_cleanup")

    def test_timeout_without_start_evidence_stays_unresolved_and_still_cleans_up(self) -> None:
        observed = self.observe_stubbed_timeout(running=False)
        receipt = observed.containers[0]
        self.assertEqual(receipt["status"], "timeout_unresolved_start_cleanup_verified")
        self.assertFalse(receipt["container_started"])
        self.assertEqual(observed.launch_metrics(observed.containers)["unresolved_container_starts"], 1)

    def test_bounded_retry_and_cumulative_replay_keep_exact_current_job_sets(self) -> None:
        rows = (repository(306), repository(307))
        policy = FleetPolicy(max_concurrent=1, max_scans_per_run=1, max_campaign_units=100)
        scanner = SyntheticScanner(behaviour={rows[0].repo_id: ("transient", "success")})
        flow = pipeline(policy=policy, scanner=scanner)
        for row in rows:
            approve_scope(flow, row)
        first = flow.run(rows)
        self.soak._assert_pipeline_accounting(
            first, policy=policy, expected_attempted_repositories=(rows[0].repo_id,),
            expected_statuses={
                rows[0].repo_id: "review_packet_ready",
                rows[1].repo_id: "deferred_rate_limit",
            },
        )
        second = flow.run(rows)
        completed = {row.repo_id: "review_packet_ready" for row in rows}
        self.soak._assert_pipeline_accounting(
            second, policy=policy, expected_attempted_repositories=(rows[1].repo_id,),
            expected_statuses=completed, scanner_invocations_before=first["scanner_invocations"],
        )
        third = flow.run(rows)
        self.soak._assert_pipeline_accounting(
            third, policy=policy, expected_attempted_repositories=(),
            expected_statuses=completed, scanner_invocations_before=second["scanner_invocations"],
        )
        self.assertEqual([row["scanner_invocations"] for row in (first, second, third)], [2, 3, 3])
        self.assertEqual([row["retry_attempts"] for row in (first, second, third)], [1, 0, 0])
        self.assertEqual(third["scanner_attempts_by_repository"], {})

    def test_retry_without_its_event_is_not_accepted_by_soak(self) -> None:
        row = repository(308)
        policy = FleetPolicy()
        scanner = SyntheticScanner(behaviour={row.repo_id: ("transient", "success")})
        flow = pipeline(policy=policy, scanner=scanner)
        approve_scope(flow, row)
        result = flow.run((row,))
        result["transient_retry_events"] = []
        with self.assertRaisesRegex(ReproductionFailure, "retry_event_count"):
            self.soak._assert_pipeline_accounting(
                result, policy=policy, expected_attempted_repositories=(row.repo_id,),
                expected_statuses={row.repo_id: "review_packet_ready"},
            )


class ContainerFailClosedStress(unittest.TestCase):
    def test_missing_docker_binary_fails_without_host_or_network_fallback(self) -> None:
        with patch("field_autonomy.sandbox.shutil.which", return_value=None):
            with patch("field_autonomy.sandbox.subprocess.run") as launch:
                with self.assertRaisesRegex(PolicyViolation, "fallback is prohibited"):
                    ContainerRuntime()._validate_daemon_and_image()
        launch.assert_not_called()

    def test_unavailable_docker_daemon_fails_without_image_pull(self) -> None:
        failure = subprocess.CompletedProcess(["docker", "info"], 1, stdout="", stderr="synthetic unavailable")
        with patch("field_autonomy.sandbox.shutil.which", return_value="/usr/bin/docker"):
            with patch("field_autonomy.sandbox.subprocess.run", return_value=failure) as launch:
                with self.assertRaisesRegex(PolicyViolation, "daemon is not running"):
                    ContainerRuntime()._validate_daemon_and_image()
        self.assertEqual(launch.call_count, 1)
        self.assertEqual(launch.call_args.args[0][:2], ["docker", "info"])

    def test_missing_cached_image_fails_without_pull_or_host_execution(self) -> None:
        present = subprocess.CompletedProcess(["docker", "info"], 0, stdout="synthetic-daemon\n", stderr="")
        absent = subprocess.CompletedProcess(["docker", "image", "inspect"], 1, stdout="", stderr="synthetic absent")
        with patch("field_autonomy.sandbox.shutil.which", return_value="/usr/bin/docker"):
            with patch("field_autonomy.sandbox.subprocess.run", side_effect=(present, absent)) as launch:
                with self.assertRaisesRegex(PolicyViolation, "automatic image pulls are prohibited"):
                    ContainerRuntime()._validate_daemon_and_image()
        self.assertEqual(launch.call_count, 2)
        self.assertTrue(all("pull" not in call.args[0] for call in launch.call_args_list))

    def test_docker_validation_timeout_fails_closed(self) -> None:
        with patch("field_autonomy.sandbox.shutil.which", return_value="/usr/bin/docker"):
            with patch("field_autonomy.sandbox.subprocess.run", side_effect=subprocess.TimeoutExpired(["docker", "info"], 8)):
                with self.assertRaisesRegex(PolicyViolation, "no fallback"):
                    ContainerRuntime()._validate_daemon_and_image()

    def test_isolated_scanner_missing_daemon_never_scans_locally(self) -> None:
        row = repository(301)
        scanner = SyntheticScanner(isolated=True)
        flow = pipeline(scanner=scanner)
        approve_scope(flow, row)
        with patch.object(ContainerRuntime, "_validate_daemon_and_image", side_effect=PolicyViolation("synthetic daemon unavailable")):
            result = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(result["status"], "failed_safe_abstention")
        self.assertIn("no local fallback", result["reason"])
        self.assertEqual(scanner.isolation_receipts, [])

    def test_symlinked_untrusted_source_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stress-link-", dir=EVIDENCE) as temporary:
            fixture = Path(temporary)
            (fixture / "src").mkdir()
            (fixture / "tests").mkdir()
            (fixture / "src" / "escape.py").symlink_to(ROOT / "src" / "fleet_security" / "scanner.py")
            row = repository(302)
            flow = pipeline()
            approve_scope(flow, row)
            with patch.object(SyntheticScanner, "_fixture", return_value=fixture):
                result = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(result["status"], "failed_safe_abstention")
        self.assertIn("symbolic", result["reason"])

    def test_hidden_repository_credential_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stress-secret-", dir=EVIDENCE) as temporary:
            fixture = Path(temporary)
            (fixture / "src").mkdir()
            (fixture / "tests").mkdir()
            (fixture / "src" / ".env.production").write_text("SYNTHETIC_TOKEN=never-read", encoding="utf-8")
            row = repository(303)
            flow = pipeline()
            approve_scope(flow, row)
            with patch.object(SyntheticScanner, "_fixture", return_value=fixture):
                result = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(result["status"], "failed_safe_abstention")
        self.assertIn("hidden secret", result["reason"])

    def test_untrusted_oversized_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stress-large-", dir=EVIDENCE) as temporary:
            fixture = Path(temporary)
            (fixture / "src").mkdir()
            (fixture / "tests").mkdir()
            (fixture / "src" / "large.py").write_bytes(b"x" * 65_537)
            row = repository(304)
            flow = pipeline()
            approve_scope(flow, row)
            with patch.object(SyntheticScanner, "_fixture", return_value=fixture):
                result = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(result["status"], "failed_safe_abstention")
        self.assertIn("inspection budget", result["reason"])

    def test_all_changed_path_escape_variants_are_rejected(self) -> None:
        for candidate in ("../private-token", "/etc/passwd", "~/.ssh/id_rsa", "src\\..\\secret", "src/../../secret"):
            with self.subTest(candidate=candidate), self.assertRaises(InventoryError):
                from dataclasses import replace
                replace(repository(305), changed_paths=(candidate,))

    def test_synthetic_host_credentials_are_absent_from_scrubbed_environment(self) -> None:
        injected = {key: "synthetic-host-only" for key in (
            "OPENAI_API_KEY", "CODEX_API_KEY", "GITHUB_TOKEN", "GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "OPENAI_WEBHOOK_SECRET",
        )}
        with patch.dict(os.environ, injected):
            environment = scrubbed_environment()
        self.assertTrue(all(key not in environment for key in injected))
        self.assertTrue(all(value != "synthetic-host-only" for value in environment.values()))

    def test_container_contract_uses_never_pull_no_network_and_exact_restricted_mounts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stress-mount-", dir=EVIDENCE) as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("source", "tests", "scratch")]
            for path in paths:
                path.mkdir()
            command = ContainerExecutor(*paths, ContainerConfiguration()).command(["python3", "-I", "-c", "pass"], "stress-proof")
        self.assertEqual(command[command.index("--pull") + 1], "never")
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertEqual(command[command.index("--cap-drop") + 1], "ALL")
        self.assertEqual(command[command.index("--security-opt") + 1], "no-new-privileges")
        self.assertEqual(command[command.index("--user") + 1], "65532:65532")
        self.assertIn("--read-only", command)
        self.assertEqual(command.count("--mount"), 3)


@unittest.skipUnless(os.environ.get("RUN_STRESS_DOCKER") == "1", "actual restricted Docker stress requires RUN_STRESS_DOCKER=1")
class GenuineRestrictedContainerStress(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture = ROOT / "fixtures" / "safe_service"
        cls.fixture = fixture
        cls.context = ContainerRuntime().open(fixture, "independent-adversarial-stress")
        cls.workspace = cls.context.__enter__()
        if cls.workspace.executor is None:
            raise AssertionError("restricted container executor did not initialise")
        cls.executor = cls.workspace.executor

    @classmethod
    def tearDownClass(cls) -> None:
        cls.context.__exit__(None, None, None)

    def execute_json(self, program: str) -> dict:
        completed = self.executor.run(["python3", "-I", "-c", program], timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        name = self.executor.container_names[-1]
        append_container_receipt(self.id(), kind="restricted-runtime", details={"container_name": name})
        return json.loads(completed.stdout)

    def test_actual_container_uid_gid_and_effective_capabilities_are_restricted(self) -> None:
        result = self.execute_json(
            "import os,json; s=dict(line.split(':',1) for line in open('/proc/self/status') if ':' in line); "
            "print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),'cap':s['CapEff'].strip(),'nnp':s['NoNewPrivs'].strip()}))"
        )
        self.assertEqual((result["uid"], result["gid"]), (65532, 65532))
        self.assertEqual(int(result["cap"], 16), 0)
        self.assertEqual(result["nnp"], "1")

    def test_actual_container_network_has_no_egress(self) -> None:
        result = self.execute_json(
            "import json,socket; r={};\n"
            "try: socket.create_connection(('203.0.113.1',443),timeout=1);r['connected']=True\n"
            "except OSError as e:r.update(connected=False,errno=e.errno)\n"
            "print(json.dumps(r))"
        )
        self.assertFalse(result["connected"])

    def test_actual_container_root_source_and_tests_are_read_only(self) -> None:
        result = self.execute_json(
            "import json,pathlib; r={};\n"
            "for k,p in {'root':'/stress-proof','source':'/workspace/src/stress-proof','tests':'/workspace/tests/stress-proof'}.items():\n"
            " try:pathlib.Path(p).write_text('synthetic');r[k]='writable'\n"
            " except OSError as e:r[k]=e.errno\n"
            "print(json.dumps(r))"
        )
        self.assertTrue(all(value in (errno.EROFS, errno.EACCES) for value in result.values()), result)

    def test_actual_container_scratch_and_tmp_are_writable(self) -> None:
        result = self.execute_json(
            "import json,pathlib; p={'scratch':'/workspace/.scratch/stress-proof','tmp':'/tmp/stress-proof'}; "
            "print(json.dumps({k:pathlib.Path(v).write_text('synthetic') for k,v in p.items()}))"
        )
        self.assertEqual(result, {"scratch": 9, "tmp": 9})

    def test_actual_container_never_receives_host_credentials(self) -> None:
        names = ("OPENAI_API_KEY", "CODEX_API_KEY", "GITHUB_TOKEN", "GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "OPENAI_WEBHOOK_SECRET")
        with patch.dict(os.environ, {name: "synthetic-do-not-forward" for name in names}):
            result = self.execute_json("import os,json; n=" + repr(names) + ";print(json.dumps({k:k in os.environ for k in n}))")
        self.assertTrue(all(value is False for value in result.values()), result)

    def test_actual_container_cannot_reach_host_paths_or_docker_socket(self) -> None:
        result = self.execute_json(
            "import json,pathlib;p=['/var/run/docker.sock','/workspace/.git','/workspace/.env','/Users','/host'];"
            "print(json.dumps({v:pathlib.Path(v).exists() for v in p}))"
        )
        self.assertTrue(all(value is False for value in result.values()), result)

    def test_actual_container_memory_process_and_cpu_limits_apply(self) -> None:
        result = self.execute_json(
            "import json,pathlib,resource;c=pathlib.Path('/sys/fs/cgroup');"
            "print(json.dumps({'memory':int((c/'memory.max').read_text()),'pids':int((c/'pids.max').read_text()),"
            "'cpu':(c/'cpu.max').read_text().strip(),'files':resource.getrlimit(resource.RLIMIT_NOFILE)[0]}))"
        )
        self.assertEqual(result["memory"], 256 * 1024 * 1024)
        self.assertEqual(result["pids"], 64)
        quota, period = (int(value) for value in result["cpu"].split())
        self.assertLessEqual(quota / period, 0.5)
        self.assertEqual(result["files"], 128)

    def test_actual_protected_tests_remain_byte_identical(self) -> None:
        protected = self.fixture / "tests" / "test_service.py"
        before = hashlib.sha256(protected.read_bytes()).hexdigest()
        result = self.execute_json(
            "import hashlib,json,pathlib;p=pathlib.Path('/workspace/tests/test_service.py');"
            "print(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
        )
        self.assertEqual(result["sha256"], before)
        self.assertEqual(hashlib.sha256(protected.read_bytes()).hexdigest(), before)

    def test_actual_container_timeout_forces_verified_cleanup(self) -> None:
        with self.assertRaises(subprocess.TimeoutExpired):
            self.executor.run(["python3", "-I", "-c", "import time;time.sleep(30)"], timeout=0.35)
        name = self.executor.container_names[-1]
        append_container_receipt(self.id(), kind="restricted-timeout", details={"container_name": name})
        self.assertNotEqual(self.executor._inspect(name).returncode, 0)


@unittest.skipUnless(os.environ.get("RUN_STRESS_DOCKER") == "1", "actual restricted Docker stress requires RUN_STRESS_DOCKER=1")
class GenuineGovernedScannerStress(PrivateRecipeCase):
    def test_actual_isolated_scanner_emits_independently_checked_restricted_receipt(self) -> None:
        row = repository(390, fixture="vulnerable_service")
        scanner = SyntheticScanner(isolated=True)
        flow = pipeline(scanner=scanner)
        approve_scope(flow, row)
        outcome = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(outcome["status"], "awaiting_finding_disposition")
        self.assertEqual(len(scanner.isolation_receipts), 1)
        receipt = scanner.isolation_receipts[0]
        append_container_receipt(self.id(), kind="restricted-scanner", details={"uid": receipt["uid"]})
        self.assertTrue(restricted_isolation_verified(receipt))
        self.assertEqual(receipt["uid"], 65532)
        self.assertTrue(receipt["networkBlocked"])
        self.assertTrue(receipt["rootReadOnly"])
        self.assertEqual(int(receipt["effectiveCapabilities"], 16), 0)
        self.assertEqual(receipt["noNewPrivileges"], "1")
        self.assertFalse(any(receipt["credentialPresence"].values()))

    def test_actual_recipe_containers_prove_restart_idempotency(self) -> None:
        observed_names = []
        original_run = ContainerExecutor.run

        def observed_run(executor, arguments, *, timeout):
            completed = None
            try:
                completed = original_run(executor, arguments, timeout=timeout)
                return completed
            finally:
                name = executor.container_names[-1]
                observed_names.append(name)
                start_evidence = None
                if completed is not None and completed.returncode == 0:
                    start_evidence = "successful_worker_exit"
                elif completed is not None:
                    refusal_reason = parse_restricted_content_refusal(
                        completed.returncode, completed.stdout,
                    )
                    if refusal_reason is not None:
                        start_evidence = (
                            "trusted_instruction_refusal_protocol"
                            if refusal_reason == "repository_instruction"
                            else "trusted_content_refusal_protocol"
                        )
                if start_evidence is not None:
                    append_container_receipt(self.id(), kind="restricted-recipe", details={
                        "container_name": name, "start_evidence": start_evidence,
                    })

        with patch.object(ContainerExecutor, "run", new=observed_run):
            first = self.cycle(docker=True)
            first_executor_invocations = len(observed_names)
            second = self.cycle(docker=True)
        policy = RecipeConfiguration.from_file(self.config).policy
        assert_cycle_accounting(
            first, expected_attempted_repositories=DEMO_ATTEMPTED_REPOSITORIES,
            expected_statuses=DEMO_EXPECTED_STATUSES, policy=policy,
            expected_isolation_receipts=3, context="first_cycle",
        )
        assert_cycle_accounting(
            second, expected_attempted_repositories=(),
            expected_statuses=DEMO_EXPECTED_STATUSES, policy=policy,
            expected_isolation_receipts=0, context="restart_cycle",
        )
        self.assertEqual(second["scanner_invocations"], 0)
        self.assertEqual((first["restricted_docker_receipts"], second["restricted_docker_receipts"]), (3, 0))
        # A transient failure may precede container creation. These are
        # executor calls; only evidence-backed starts enter the container log.
        self.assertGreaterEqual(first_executor_invocations, len(DEMO_ATTEMPTED_REPOSITORIES))
        self.assertLessEqual(first_executor_invocations, first["scanner_invocations"])
        self.assertEqual(len(observed_names), first_executor_invocations)
        self.assertEqual(len(set(observed_names)), first_executor_invocations)
        self.assertEqual(first["decision_states"], second["decision_states"])
        self.assert_owner_private_tree(self.state)


if __name__ == "__main__":
    unittest.main()
