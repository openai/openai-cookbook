#!/usr/bin/env python3
"""Build the clean, customer-neutral governed security-review Cookbook notebook."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]
ROOT_NOTEBOOK = ROOT / "governed_repository_security_reviews.ipynb"
DEFAULT_NOTEBOOK = ROOT_NOTEBOOK if ROOT_NOTEBOOK.is_file() else ROOT / "cookbook" / ROOT_NOTEBOOK.name


def cell(kind: str, source: str) -> dict[str, object]:
    cleaned = dedent(source).strip("\n") + "\n"
    record: dict[str, object] = {
        "cell_type": kind,
        "id": hashlib.sha256((kind + cleaned).encode("utf-8")).hexdigest()[:12],
        "metadata": {},
        "source": cleaned.splitlines(keepends=True),
    }
    if kind == "code":
        record.update({"execution_count": None, "outputs": []})
    return record


def build_cells(*, diagram_prefix: str | None = None) -> list[dict[str, object]]:
    if diagram_prefix is None:
        base = "../../../images" if ROOT_NOTEBOOK.is_file() else "../images"
        diagram_prefix = base + "/governed_repository_security_reviews"
    def md(source: str) -> dict[str, object]:
        if diagram_prefix.startswith("../../../"):
            source = source.replace(
                "scripts/execute_notebook.py cookbook/governed_repository_security_reviews.ipynb",
                "scripts/execute_notebook.py governed_repository_security_reviews.ipynb",
            )
            source = source.replace(
                "For a root-level copy, replace the last argument with `governed_repository_security_reviews.ipynb`. ",
                "",
            )
        return cell("markdown", source)
    py = lambda source: cell("code", source)
    return [
        md("""
        # Govern repository security reviews with versioned context

        ## What you will build

        Build a **customer-owned security-review control plane**: trusted inventory → approved threat context → bounded work → authenticated evidence → human review. You will run a first review cycle, restart without duplicate scans, record a simulated reviewer decision and reject a tampered checkpoint.

        Six fictional repository records exercise the complete local workflow. A separate 2,000-record simulation illustrates the size of a reusable threat-context catalogue; those records are not scanned. The scanner recognises deterministic fixture markers rather than detecting real vulnerabilities.

        No cell starts a Codex Security scan, makes a hosted or paid model request, contacts a repository provider, creates a pull request, merges or deploys. The native CLI command later in the notebook is an inspection-only integration plan.
        """),
        md(f"""
        ## System boundary and authority model

        ![Trusted inventory and human scope feed host admission, separate optional Docker fixture workers, authenticated evidence and named review. A dashed future Codex Security adapter is not executed.]({diagram_prefix}/architecture.svg)

        **Figure 1.** The solid path shows the optional Docker fixture mode. The host launches the separate workers; the daemon-free Compose service has only its outer container boundary. The dashed live adapter is future work, not a product scan performed by this notebook. [Editable Mermaid source]({diagram_prefix}/architecture.mmd) · [Full text alternative and source notes]({diagram_prefix}/DIAGRAMS.md).

        The trusted host owns inventory, policy, authorisation and the local signing key. Repository content and scanner output cannot grant permission. The JSON approvals in this example are fictional trusted inputs, not an enterprise identity or approval service.

        A real scanner needs a separately approved model-network route. Untrusted code verification belongs in a separate sandbox that denies networking and inherited credentials. The default path below reads bundled source as data; it does not claim operating-system isolation. Set the explicit Docker opt-in only after preparing its prerequisites.
        """),
        md("""
        ## 1. Load the portable recipe without making a model request

        ### Prerequisites and launch

        - Python 3.11+ on Linux or macOS. The recipe uses POSIX file ownership and `fcntl` locks; on Windows use a suitable Linux environment.
        - The complete package, including `src/`, `scripts/`, `cookbook/security-review-pipeline/`, `fixtures/` and `contracts/codex-security-schemas/`. Downloading the notebook alone is insufficient.
        - No API key, employee-only plugin or third-party Python package is needed. The public schema snapshot is bundled, pinned and checked for integrity.
        - Optional Docker: an available daemon and the already cached, approved `python:3.12-alpine` image. No cell pulls an image or silently falls back if requested isolation is unavailable.

        Open the notebook from the package root or its `cookbook/` directory and choose **Restart Kernel and Run All**. A notebook published directly at the root of the self-contained example uses the same setup. Alternatively, from that package root run:

        ```sh
        python3 -B scripts/execute_notebook.py cookbook/governed_repository_security_reviews.ipynb
        ```

        For a root-level copy, replace the last argument with `governed_repository_security_reviews.ipynb`. To opt in to real Docker verification, set `RUN_SECURITY_COOKBOOK_DOCKER=1` before launching the runner or kernel.

        The setup below checks only these documented locations, never arbitrary siblings, parent repositories or an injected global root. An incomplete package fails with a clear setup error. **Expected:** `docker_enabled` is `false` by default and `hosted_requests` is `0`.
        """),
        py("""
        import json
        import os
        import stat
        import sys
        import tempfile
        from pathlib import Path

        # Keep the distributed source tree unchanged in an ordinary Jupyter kernel.
        sys.dont_write_bytecode = True

        def find_package_root(start):
            start = Path(start).resolve()
            # Only the package root or its immediate notebook directory is valid.
            source_marker = start / "src" / "fleet_security" / "recipe.py"
            root = (
                start.parent
                if start.name == "cookbook" and not source_marker.is_file()
                else start
            )
            required = (
                "src/fleet_security/recipe.py",
                "src/fleet_security/reproduction.py",
                "scripts/execute_notebook.py",
                "scripts/evaluate_threat_context.py",
                "evals/security_context_cases.json",
                "cookbook/security-review-pipeline/config.example.json",
                "cookbook/security-review-pipeline/inventory.example.json",
                "cookbook/security-review-pipeline/approvals.example.json",
                "contracts/codex-security-schemas/PROVENANCE.json",
                "fixtures/vulnerable_service/src/service.py",
            )
            for relative in required:
                path = root / relative
                parts = (path, *path.parents[:len(Path(relative).parts) - 1])
                if not path.is_file() or any(part.is_symlink() for part in parts):
                    raise RuntimeError(
                        "Incomplete example package: missing or linked " + relative
                        + ". Start in the complete package root or its cookbook directory."
                    )
            return root

        if sys.version_info < (3, 11) or os.name != "posix":
            raise RuntimeError(
                "Use Python 3.11+ on Linux or macOS, or a suitable Linux environment."
            )
        ROOT = find_package_root(Path.cwd())
        sys.path.insert(0, str(ROOT / "src"))

        from fleet_security import ThreatCatalogue, classify
        from fleet_security.evidence import EvidenceError
        from fleet_security.planning import prepare_repository_review
        from fleet_security.recipe import (
            RecipeConfiguration,
            RecurringSecurityRecipe,
            load_recipe_inventory,
        )
        from fleet_security.schema_validation import official_schema_directory
        from fleet_security.reproduction import (
            DEMO_ATTEMPTED_REPOSITORIES,
            DEMO_EXPECTED_STATUSES,
            assert_cycle_accounting,
        )

        EXAMPLES = ROOT / "cookbook" / "security-review-pipeline"
        CONFIG = EXAMPLES / "config.example.json"
        INVENTORY = EXAMPLES / "inventory.example.json"
        APPROVALS = EXAMPLES / "approvals.example.json"
        configuration = RecipeConfiguration.from_file(CONFIG)
        docker_enabled = os.environ.get("RUN_SECURITY_COOKBOOK_DOCKER") == "1"
        print(json.dumps({
            "organisation": configuration.organisation_id,
            "docker_enabled": docker_enabled,
            "hosted_requests": 0,
        }))
        """),
        md("""
        ## 2. Inspect trusted repository inventory and explicit owner approvals

        Every repository has an immutable full SHA, accountable service owner, language/framework, deployment topology, data class, exposure, authentication, dependencies, existing controls and criticality. Repository-owned files never grant scope or approval.

        Real-format metadata follows a separately labelled **planning-only** path. It may produce an inert campaign or explicit approval holds, but it never reads repository code, launches a scan, records findings, or declares any repository clean.

        **Expected:** six fictional records. The separate three-record metadata plan returns one planned item, one missing-scope hold and one high-risk-context hold, with zero inspected repositories and zero review packets.
        """),
        py("""
        inventory = load_recipe_inventory(INVENTORY)
        classes = {repo.repo_id: classify(repo) for repo in inventory}
        assert len(inventory) == 6
        assert all(len(repo.commit_sha) == 40 and repo.owner for repo in inventory)
        approvals = json.loads(APPROVALS.read_text())
        assert all(entry.get("actor") for entry in approvals["approvals"])
        metadata_plan = prepare_repository_review(
            configuration_path=CONFIG,
            inventory_path=EXAMPLES / "inventory.real.example.json",
            approvals_path=EXAMPLES / "approvals.real.example.json",
        )
        assert metadata_plan["mode"] == "planning_only"
        assert (
            metadata_plan["scanned_repositories"]
            == metadata_plan["review_packets_created"]
            == 0
        )
        assert metadata_plan["finding_count"] is None
        assert metadata_plan["decision_states"] == {
            "awaiting_scope_approval": 1,
            "awaiting_threat_model_acceptance": 1,
            "planned_not_executed": 1,
        }
        print(json.dumps({
            "inventory": len(inventory),
            "archetypes": sorted({item.archetype for item in classes.values()}),
            "high_risk": [repo.repo_id for repo in inventory if repo.risk_tier == "high"],
            "metadata_plan": metadata_plan["decision_states"],
        }, indent=2))
        """),
        md(f"""
        ## 3. Compose organisation, archetype, repository delta and bespoke context

        Shared organisation controls are reviewed once per version. Archetypes describe reusable workload trust boundaries. Every repository retains its own delta. High-risk or materially distinct services require a complete, independently approved bespoke context.

        ![Organisation baseline, archetype and repository delta combine with bespoke high-risk context into an effective hash. High-risk repositories require named acceptance of the exact hash before admission. A baseline edit can invalidate all repositories.]({diagram_prefix}/threat_context.svg)

        **Figure 2.** Compute the effective hash first, then bind required human acceptance to that hash. Editing one shared baseline may invalidate every repository; fewer model artefacts do not mean fewer required revalidations. [Editable Mermaid source]({diagram_prefix}/threat_context.mmd).

        A version and content hash bind the effective context to the repository. A later material change invalidates the earlier approval. This example assigns structured scenario metadata; it does not ask a model to author or assess real threat models. **Expected:** the fictional edge-auth service requires human acceptance and its context hash matches its scoped fixture approval.
        """),
        py("""
        catalogue = ThreatCatalogue(
            organisation_controls=configuration.organisation_controls,
            version=configuration.organisation_model_version,
        )
        contexts = {repo.repo_id: catalogue.assign(repo) for repo in inventory}
        risky = contexts["synthetic/edge-auth"]
        assert risky.requires_human_acceptance and risky.repository_model_id
        assert risky.effective_model_hash == next(
            row["context_sha256"]
            for row in approvals["approvals"]
            if row["gate"] == "threat_model"
        )
        print(json.dumps({
            "organisation_version": configuration.organisation_model_version,
            "archetype": risky.archetype_model_id,
            "repository_delta": risky.delta,
            "human_approval_required": risky.requires_human_acceptance,
        }, indent=2))
        """),
        md("""
        ## 4. Check independent context labels, then count synthetic fleet artefacts

        A shared model has few review artefacts but omits distinctions. Full per-repository models repeat common context. The hierarchy keeps a shared baseline and archetype patterns, while preserving a delta for every repository and reserving bespoke context for high-risk cases.

        The evaluation declares eight synthetic cases and six drift cases separately from the catalogue implementation. It checks expected scenario labels and human-review requirements; those labels have not received independent security-domain validation. Removing a required label must make the evaluation fail.

        **Expected:** the individual and hierarchical strategies retain all 45 declared scenario occurrences; the shared baseline retains 24. A separate generated inventory has **68 substantial hierarchical models = 1 organisation + 10 archetypes + 57 exceptions**, plus **2,000 per-repository deltas**. These are context checks and metadata counts, not vulnerability recall, reviewer time, cost savings or production throughput. The older `compare_strategies()` helper remains an illustrative self-oracle simulation and is not the evidence used here.
        """),
        py("""
        sys.path.insert(0, str(ROOT / "scripts"))
        from evaluate_threat_context import evaluate, load_cases

        labelled_cases = load_cases(ROOT / "evals" / "security_context_cases.json")
        context_check = evaluate(labelled_cases, metadata_records=2_000)
        assert context_check["status"] == "PASS"
        assert (
            context_check["strategies"]["hierarchical"]["summary"]["matched_label_occurrences"]
            == 45
        )
        assert (
            evaluate(
                labelled_cases,
                metadata_records=0,
                drop_scenario="authentication_bypass",
            )["status"]
            == "FAIL"
        )
        hierarchy_count = (
            context_check["metadata_artefact_counts"]["strategies"]["hierarchical"]
        )
        assert hierarchy_count["substantial_model_artefacts"] == 68
        assert hierarchy_count["repository_delta_records"] == 2_000
        print(json.dumps({
            "labelled_cases": context_check["labelled_cases"],
            "label_occurrences_retained": {
                key: value["summary"]["matched_label_occurrences"]
                for key, value in context_check["strategies"].items()
            },
            "mutation_correctly_failed": True,
            "synthetic_metadata_records": 2_000,
            "hierarchical_model_artefacts": hierarchy_count["substantial_model_artefacts"],
            "hierarchical_repository_deltas": hierarchy_count["repository_delta_records"],
            "repositories_scanned": 0,
        }, indent=2))
        """),
        md("""
        ## 5. Execute one bounded, human-governed synthetic review cycle

        A private temporary directory stores a `0600` host key, HMAC-authenticated checkpoints, synthetic evidence in the pinned public schema format and run receipts. Keeping state outside the source tree avoids committing keys or findings. A local HMAC is not protection against a malicious writer who controls the same operating-system account and key; no power-loss durability is established here.

        Missing scope, missing high-risk approval, hostile content and findings awaiting disposition stop safely. **Expected:** four distinct repositories are attempted; two finding-review holds, one scope hold, one threat-context hold, one hostile-content refusal and one ready review packet. Docker mode produces three successful isolation receipts; the hostile fixture is refused.

        Without transient failures, this means four scan attempts. A permitted retry can increase attempts without adding another repository or duplicating a successful review. The check below requires every extra attempt to match a recorded, policy-bounded retry; an unexplained duplicate, exhausted failure, missing isolation receipt or wrong decision still fails. Raw attempts and retry counts remain visible.
        """),
        py("""
        temporary_state = tempfile.TemporaryDirectory(prefix="governed-security-cookbook-")
        STATE = Path(temporary_state.name) / "private-state"
        first = RecurringSecurityRecipe.from_files(
            configuration_path=CONFIG,
            inventory_path=INVENTORY,
            approvals_path=APPROVALS,
            state_directory=STATE,
            docker=docker_enabled,
        ).cycle()
        expected = {
            "awaiting_finding_disposition": 2,
            "awaiting_scope_approval": 1,
            "awaiting_threat_model_approval": 1,
            "failed_safe_abstention": 1,
            "review_packet_ready": 1,
        }
        first_accounting = assert_cycle_accounting(
            first,
            expected_attempted_repositories=DEMO_ATTEMPTED_REPOSITORIES,
            expected_statuses=DEMO_EXPECTED_STATUSES,
            policy=configuration.policy,
            expected_isolation_receipts=3 if docker_enabled else 0,
            context="first_cycle",
        )
        assert first["decision_states"] == expected
        assert (
            not first["live_product_execution"]
            and first["paid_api_calls"] == first["external_writes"] == 0
        )
        print(json.dumps({
            "run": first["run_number"],
            "decisions": first["decision_states"],
            "synthetic_scans": first["scanner_invocations"],
            "attempted_repositories": first["attempted_repositories"],
            "retry_attempts": first["retry_attempts"],
            "docker_receipts": first["restricted_docker_receipts"],
        }, indent=2))
        """),
        md("""
        ## 6. Inspect the documented native bulk-scan contract without running it

        The product natively accepts a pinned CSV, workers, retry limit, repeatable campaign-wide knowledge-base documents and resumable output. Repository deltas live in row prompts. `bulk-scan --max-cost USD` is a documented per-repository-attempt estimated threshold; in-flight requests can overshoot and it is not a hard aggregate campaign cap. An independent customer-owned admission budget remains mandatory.

        The generated plan pins `@openai/codex-security@0.1.20`. A package pin and a schema check do not prove model access, product entitlement or an executed integration. Verify the exact installed CLI capabilities before a separately authorised real run; make the approved model, effort, charge owner and triggering policy explicit.

        **Expected:** every generated command is a plan, contains explicit model and effort, and records both `command_executed: false` and `customer_model_approval_verified: false`. Do not paste these synthetic plans into a live shell.

        Sources: [pinned official CLI and SDK source](https://github.com/openai/codex-security/blob/59d026a0579af084b419cd7f33b8e1b867338ee8/sdk/typescript/README.md), [bulk scans](https://developers.openai.com/codex/security/cli/bulk-scans), [CLI reference](https://developers.openai.com/codex/security/cli/reference).
        """),
        py("""
        for plan in first["native_campaign_plans"]:
            command = plan["command"]
            assert command[:3] == ["npx", "@openai/codex-security@0.1.20", "bulk-scan"]
            assert command.count("--knowledge-base") == 2
            assert "--model" in command and "--effort" in command
            # This inert example deliberately omits the supported optional
            # per-attempt estimate; no real scan or expenditure is approved.
            assert "--max-cost" not in command
            assert (
                plan["command_executed"] is False
                and plan["customer_model_approval_verified"] is False
            )
        print(json.dumps({
            "campaign_count": len(first["native_campaign_plans"]),
            "commands_are_plans_only": True,
            "model_approval_verified": first["customer_model_approval_verified"],
        }, indent=2))
        """),
        md("""
        ## 7. Validate signed synthetic findings, coverage and manifest contracts

        Findings, coverage and scan manifests conform to the integrity-verified official schemas while explicitly carrying `synthetic: true`. The public reference bundles an immutable Apache-licensed official schema snapshot, so the portable notebook needs no installed private plugin. Schema validity checks the document shape, not whether a reported vulnerability is true. The host's signing key is never a review artefact, and partial or unknown coverage is never interpreted as clean.

        **Expected:** three pinned contracts, nine validated synthetic documents and `0600` state/key permissions. A ready packet means ready for human inspection; it does not mean security acceptance or permission to merge.
        """),
        py("""
        schemas = official_schema_directory()
        assert all(
            (schemas / f"{name}.schema.json").is_file()
            for name in ("findings", "coverage", "scan-manifest")
        )
        assert first["official_schema_validated_synthetic_documents"] == 9
        assert stat.S_IMODE((STATE / ".local-state-key").stat().st_mode) == 0o600
        assert stat.S_IMODE((STATE / "state.json").stat().st_mode) == 0o600
        print(json.dumps({
            "official_contracts_found": 3,
            "validated_synthetic_documents": (
                first["official_schema_validated_synthetic_documents"]
            ),
            "private_state_permissions": "0600",
        }))
        """),
        md("""
        ## 8. Restart the process and prove unchanged repositories are not rescanned

        Each reconciliation cycle reloads the trusted inventory, named approvals and authenticated prior evidence. Unchanged successful reviews are reused; unchanged hostile content remains quarantined. Missing approvals still hold even if previous evidence exists.

        **Expected:** run two makes **zero** scanner calls, preserves all decision states and keeps the hostile fixture quarantined. This local restart checks idempotency, not a continuously deployed scheduler or distributed service.
        """),
        py("""
        restarted = RecurringSecurityRecipe.from_files(
            configuration_path=CONFIG,
            inventory_path=INVENTORY,
            approvals_path=APPROVALS,
            state_directory=STATE,
            docker=docker_enabled,
        ).cycle()
        assert restarted["run_number"] == 2
        assert_cycle_accounting(
            restarted,
            expected_attempted_repositories=(),
            expected_statuses=DEMO_EXPECTED_STATUSES,
            policy=configuration.policy,
            expected_isolation_receipts=0,
            context="restart_cycle",
        )
        assert restarted["scanner_invocations"] == 0
        assert restarted["quarantined_unchanged"] == ["synthetic/adversarial-docs"]
        assert restarted["decision_states"] == first["decision_states"]
        print(json.dumps({
            "run": restarted["run_number"],
            "new_scans": restarted["scanner_invocations"],
            "quarantined": restarted["quarantined_unchanged"],
        }))
        """),
        md("""
        ## 9. Simulate a scoped reviewer decision without rescanning

        The next cell writes a **fictional reviewer fixture**, bound to the exact repository, revision, finding and idempotency key, which includes the effective context and scanner/policy versions. The decision expires after one hour. It teaches the decision contract; a production adapter must independently authenticate the reviewer and verify their authority. Repository text or a model response must never supply that authority.

        **Expected:** only the selected payments finding becomes ready for review, with zero new scans and no pull request, merge or deployment. A real acceptance decision stays with a named human.
        """),
        py("""
        import time
        from fleet_security.inventory import stable_digest

        snapshot = json.loads((STATE / "state.json").read_text())
        payment = next(
            row
            for row in snapshot["payload"]["states"]
            if row["repository_id"] == "synthetic/payments-api"
        )
        accepted_finding = payment["current_findings"][0]["findingId"]
        reviewed_approvals = Path(temporary_state.name) / "named-human-approvals.json"
        approved_rows = json.loads(APPROVALS.read_text())
        finding_target = stable_digest({
            "repository_id": payment["repository_id"],
            "commit_sha": payment["reviewed_revision"],
            "idempotency_key": payment["idempotency_key"],
            "finding_id": accepted_finding,
        })
        approved_rows["approvals"].append({
            "gate": "finding_disposition", "repository_id": "synthetic/payments-api",
            "revision": payment["reviewed_revision"], "finding_id": accepted_finding,
            "target_sha256": finding_target, "expires_at": int(time.time()) + 3_600,
            "actor": "finding-owner",
        })
        reviewed_approvals.write_text(json.dumps(approved_rows))
        reviewed_approvals.chmod(0o600)
        reviewed = RecurringSecurityRecipe.from_files(
            configuration_path=CONFIG,
            inventory_path=INVENTORY,
            approvals_path=reviewed_approvals,
            state_directory=STATE,
        ).cycle()
        assert reviewed["records"]["synthetic/payments-api"]["status"] == "review_packet_ready"
        assert reviewed["scanner_invocations"] == 0
        assert not reviewed["automatic_pr_merge_or_deploy"]
        print(json.dumps({
            "finding": accepted_finding,
            "decision": "review_packet_ready",
            "new_scans": 0,
            "external_writes": 0,
        }))
        """),
        md("""
        ## 10. Reject a tampered checkpoint before any scan can start

        The recurring state envelope is authenticated with an owner-private signing key. Altering the checkpoint without recomputing its HMAC must fail before dispatch. This deliberately corrupts a separate disposable state directory, leaving the main example untouched.

        **Expected:** `Tampered checkpoint correctly refused before scanner dispatch.` If no exception occurs, the cell raises an assertion instead of treating the run as successful.
        """),
        py("""
        with tempfile.TemporaryDirectory(prefix="governed-security-tamper-") as tamper_root:
            unsafe_state = Path(tamper_root) / "state"
            RecurringSecurityRecipe.from_files(
                configuration_path=CONFIG,
                inventory_path=INVENTORY,
                approvals_path=APPROVALS,
                state_directory=unsafe_state,
            ).cycle()
            checkpoint = unsafe_state / "state.json"
            envelope = json.loads(checkpoint.read_text())
            envelope["payload"]["run_number"] = 999
            checkpoint.write_text(json.dumps(envelope))
            try:
                RecurringSecurityRecipe.from_files(
                    configuration_path=CONFIG,
                    inventory_path=INVENTORY,
                    approvals_path=APPROVALS,
                    state_directory=unsafe_state,
                ).cycle()
            except EvidenceError as error:
                assert "signature" in str(error)
                print("Tampered checkpoint correctly refused before scanner dispatch.")
            else:
                raise AssertionError("tampered checkpoint was incorrectly accepted")
        """),
        md("""
        ## 11. Revalidate a changed revision and a changed boundary

        Exact revision, effective threat context, scanner version and policy are part of idempotency. A new revision cannot inherit scope approval. After simulating a refreshed scope decision, only the changed repository is inspected. A later boundary change must also trigger inspection, even when the changed-path hint contains only documentation.

        No scheduler, webhook, background worker or production integration is created by this notebook. Those deployment choices require separate customer approval and enterprise identity, retention, secret-management and observability controls.

        **Expected:** the stale-scope attempt is refused without changing the checkpoint. Each approved revision or boundary change schedules exactly the affected repository. A transient retry may add an accounted attempt, but never another repository. The configured periodic interval is `168` hours; the notebook does not wait a week or create a live scheduler.
        """),
        py("""
        from fleet_security.pipeline import PipelineError

        changed_inventory = json.loads(INVENTORY.read_text())
        changed_record = next(
            row
            for row in changed_inventory["repositories"]
            if row["repo_id"] == "synthetic/catalog-service"
        )
        changed_record.update(commit_sha="c" * 40, changed_paths=["src/service.py"])
        candidate_inventory = Path(temporary_state.name) / "changed-inventory.json"
        candidate_inventory.write_text(json.dumps(changed_inventory))
        candidate_inventory.chmod(0o600)
        checkpoint_before = (STATE / "state.json").read_bytes()
        try:
            RecurringSecurityRecipe.from_files(
                configuration_path=CONFIG,
                inventory_path=candidate_inventory,
                approvals_path=APPROVALS,
                state_directory=STATE,
            ).cycle()
        except PipelineError:
            assert (STATE / "state.json").read_bytes() == checkpoint_before
        else:
            raise AssertionError("a new revision inherited stale scope approval")

        # Simulated owner decision for this exact fictional revision, not real authority.
        changed_approvals = json.loads(APPROVALS.read_text())
        next(
            row
            for row in changed_approvals["approvals"]
            if row["repository_id"] == changed_record["repo_id"]
        )["revision"] = changed_record["commit_sha"]
        candidate_approvals = Path(temporary_state.name) / "changed-scope-approvals.json"
        candidate_approvals.write_text(json.dumps(changed_approvals))
        candidate_approvals.chmod(0o600)
        changed_revision = RecurringSecurityRecipe.from_files(
            configuration_path=CONFIG,
            inventory_path=candidate_inventory,
            approvals_path=candidate_approvals,
            state_directory=STATE,
            docker=docker_enabled,
        ).cycle()
        assert_cycle_accounting(
            changed_revision,
            expected_attempted_repositories=(changed_record["repo_id"],),
            expected_statuses=DEMO_EXPECTED_STATUSES,
            policy=configuration.policy,
            expected_isolation_receipts=1 if docker_enabled else 0,
            context="changed_revision",
        )
        assert (
            changed_revision["records"][changed_record["repo_id"]]["reviewed_revision"]
            == "c" * 40
        )

        changed_record.update(exposure="internet", changed_paths=["docs/operator-notes.md"])
        candidate_inventory.write_text(json.dumps(changed_inventory))
        changed_boundary = RecurringSecurityRecipe.from_files(
            configuration_path=CONFIG,
            inventory_path=candidate_inventory,
            approvals_path=candidate_approvals,
            state_directory=STATE,
            docker=docker_enabled,
        ).cycle()
        assert_cycle_accounting(
            changed_boundary,
            expected_attempted_repositories=(changed_record["repo_id"],),
            expected_statuses=DEMO_EXPECTED_STATUSES,
            policy=configuration.policy,
            expected_isolation_receipts=1 if docker_enabled else 0,
            context="changed_boundary",
        )
        assert configuration.periodic_revalidation_hours == 168
        print(json.dumps({
            "stale_scope_refused": True,
            "changed_revision_scans": changed_revision["scanner_invocations"],
            "changed_boundary_scans": changed_boundary["scanner_invocations"],
            "changed_revision_jobs": changed_revision["attempted_repositories"],
            "changed_boundary_jobs": changed_boundary["attempted_repositories"],
            "changed_revision_retries": changed_revision["retry_attempts"],
            "changed_boundary_retries": changed_boundary["retry_attempts"],
            "scheduled_revalidation_hours": 168,
            "live_scheduler_created": False,
        }))
        """),
        md("""
        ## 12. Clean up and decide the next evidence to collect

        Before running real repositories, obtain exact asset authorisation, confirmed product access, a named spending owner, an explicitly approved model/effort, a permitted data-processing route, scoped service credentials, real scanner isolation and named finding reviewers. Start with two or three approved repositories, then expand only when customer-owned quality and operating gates pass.

        Native bulk scanning, GitHub discovery, immutable CSVs, worker concurrency, resume/retry and shared knowledge-base inputs are documented product features. Hierarchical context synthesis, durable policy, hard campaign-spend admission, repository ownership and review routing are customer-owned orchestration. This notebook proves synthetic control behaviour only; it does not prove customer entitlement, real finding quality, production cost, throughput or remediation.

        An appropriate next experiment is a separately authorised small public or synthetic repository corpus with independently labelled expected findings. Measure false positives, misses, severity, evidence usefulness and reviewer effort before making any quality claim. Select acceptance thresholds with the security owner before running the experiment.

        **Expected:** the final cell finds the review receipts, removes the private temporary state and prints `synthetic_only: true` and `cleanup: complete`. Successful execution reproduces this teaching example, not a deployment or an approved Cookbook publication.
        """),
        py("""
        assert (STATE / "runs" / "run-0001.json").is_file()
        assert (STATE / "runs" / "run-0003.json").is_file()
        temporary_state.cleanup()
        assert not STATE.exists()
        print(json.dumps({
            "decision": "customer_neutral_recipe_verified",
            "synthetic_only": True,
            "human_authority_preserved": True,
            "cleanup": "complete",
        }))
        """),
        md("""
        ### Sources

        - [Pinned official CLI and TypeScript SDK source](https://github.com/openai/codex-security/blob/59d026a0579af084b419cd7f33b8e1b867338ee8/sdk/typescript/README.md)
        - [Run bulk security scans](https://developers.openai.com/codex/security/cli/bulk-scans)
        - [Codex Security CLI reference](https://developers.openai.com/codex/security/cli/reference)
        - [Pinned public evidence schemas](https://github.com/openai/codex-security/tree/59d026a0579af084b419cd7f33b8e1b867338ee8/sdk/typescript/_bundled_plugin/schemas)

        Publication, sharing, real product execution and customer access require separate explicit approval. Keep all customer names, private evidence and account material outside this reusable notebook.
        """),
    ]


def build_notebook(destination: Path = DEFAULT_NOTEBOOK, *, diagram_prefix: str | None = None) -> dict[str, int]:
    cells = build_cells(diagram_prefix=diagram_prefix)
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(notebook, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "cells": len(cells),
        "code_cells": sum(item["cell_type"] == "code" for item in cells),
        "markdown_cells": sum(item["cell_type"] == "markdown" for item in cells),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_NOTEBOOK)
    parser.add_argument("--diagram-prefix", help="Relative path to the two reviewed diagram assets.")
    args = parser.parse_args()
    print(json.dumps({"notebook": str(args.output), **build_notebook(args.output, diagram_prefix=args.diagram_prefix)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
