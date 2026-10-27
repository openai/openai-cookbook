import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from evidence_teams import (
    Evidence, Finding, Fixture, Limits, Probe, ResponsesSpecialist, Scheduler, Task,
    decide, fixture_specialist, fixtures,
)

TOPIC = ("active_schema", "fictional-service/release-42")


class SchedulerTests(unittest.TestCase):
    def test_empty_seed_plan_rejected(self):
        with self.assertRaises(ValueError):
            Scheduler((), {}).run((), fixture_specialist)

    def test_malformed_task_rejected(self):
        for changes in ({"sources": ()}, {"sources": ["x"]}, {"depth": -1}, {"claim": ""}):
            values = {"role": "reader", "claim": "c", "scope": "s", "sources": ("x",)}
            values.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Task(**values)

    def test_agreement_does_not_spawn(self):
        result = fixtures()["agreement"].run()
        self.assertEqual((result.calls, result.created_branches), (2, 0))
        self.assertEqual(result.decisions[TOPIC].status, "supported")
        self.assertFalse(result.needs_review)

    def test_conflict_creates_targeted_specialist(self):
        result = fixtures()["conflict"].run()
        self.assertEqual((result.calls, result.created_branches), (3, 1))
        branch = result.branches[-1]
        self.assertEqual(branch.task.role, "manifest_reconciler")
        self.assertEqual(branch.task.context_ids, ("c1", "c2"))
        self.assertEqual(branch.task.depth, 1)
        decision = result.decisions[TOPIC]
        self.assertEqual((decision.status, decision.value), ("resolved_by_policy", "v3"))
        self.assertEqual(decision.dissent_ids, ("c2",))
        self.assertIn("c2", [e.id for e in result.evidence])
        self.assertNotIn("archive_checker", [b.task.role for b in result.branches])

    def test_unresolved_contradiction_is_preserved(self):
        result = fixtures()["unresolved"].run()
        self.assertEqual(result.calls, 4)
        self.assertEqual(result.termination, "exhausted")
        self.assertEqual(result.decisions[TOPIC].status, "unresolved")
        self.assertIsNone(result.decisions[TOPIC].value)
        self.assertEqual(set(result.decisions[TOPIC].dissent_ids), {"u1", "u2", "u3", "u4", "u5"})
        self.assertTrue(result.needs_review)

    def test_fixed_fanout_always_runs_four_calls(self):
        for name, fixture in fixtures().items():
            with self.subTest(name=name):
                result = fixture.run(adaptive=False)
                self.assertEqual(result.calls, 4)
                self.assertEqual(result.termination, "fixed_plan_complete")
                self.assertEqual(result.created_branches, 0)
                # Baseline has the same decision rule; call count isn't quality.
                self.assertEqual(result.decisions[TOPIC].value, fixture.run().decisions[TOPIC].value)

    def test_duplicate_task_does_not_consume_call(self):
        fixture = fixtures()["agreement"]
        result = Scheduler(fixture.catalog, {}).run((fixture.seeds[0],) * 3, fixture_specialist)
        self.assertEqual(result.calls, 1)
        self.assertEqual([b.status for b in result.branches], ["productive", "duplicate_task", "duplicate_task"])

    def test_duplicate_probe_does_not_spawn_again(self):
        fixture = fixtures()["unresolved"]
        probe = Probe("manifest_reconciler", ("signed_manifest",))
        result = Scheduler(fixture.catalog, {TOPIC: (probe, probe)}, fixture.authoritative_sources).run(
            fixture.seeds, fixture_specialist
        )
        self.assertEqual((result.calls, result.created_branches), (3, 1))
        self.assertIn("duplicate_task", [b.status for b in result.branches])

    def test_repeated_id_does_not_amplify_evidence(self):
        fixture = fixtures()["agreement"]
        def repeat(task, allowed):
            return Finding(tuple(e.id for e in allowed) * 4)
        result = fixture.run(specialist=repeat)
        self.assertEqual(len(result.evidence), 2)

    def test_alias_evidence_from_same_source_is_deduplicated(self):
        item = Evidence("x", "source", "claim", "scope", "yes", "First wording")
        alias = Evidence("y", "source", "claim", "scope", "yes", "Reworded excerpt")
        task = Task("reader", "claim", "scope", ("source",))
        result = Scheduler((item, alias), {}).run((task,), fixture_specialist)
        self.assertEqual([e.id for e in result.evidence], ["x"])

    def test_redundant_branch_is_terminal_not_retried(self):
        fixture = fixtures()["unresolved"]
        probes = {TOPIC: (Probe("different_role", ("release_note",)),)}
        result = Scheduler(fixture.catalog, probes).run(fixture.seeds, fixture_specialist)
        self.assertEqual(result.branches[-1].status, "redundant")
        self.assertEqual(result.calls, 3)
        self.assertEqual(result.termination, "exhausted")

    def test_empty_branch_is_exhausted_and_next_probe_can_resolve(self):
        fixture = fixtures()["conflict"]
        probes = {TOPIC: (Probe("missing_record", ("missing",)),) + fixture.probes[TOPIC]}
        result = Scheduler(fixture.catalog, probes, fixture.authoritative_sources).run(
            fixture.seeds, fixture_specialist
        )
        self.assertEqual(result.branches[2].status, "exhausted")
        self.assertEqual(result.calls, 4)
        self.assertEqual(result.decisions[TOPIC].status, "resolved_by_policy")

    def test_failed_specialist_consumes_budget_and_keeps_dissent(self):
        fixture = fixtures()["conflict"]
        def failing(task, allowed):
            if task.role == "manifest_reconciler":
                raise TimeoutError("fictional timeout")
            return fixture_specialist(task, allowed)
        result = fixture.run(specialist=failing)
        self.assertEqual(result.calls, 4)
        self.assertEqual(result.branches[2].error_type, "TimeoutError")
        self.assertEqual(result.decisions[TOPIC].status, "unresolved")
        self.assertTrue(result.needs_review)

    def test_empty_seed_requires_review_even_with_one_supported_value(self):
        fixture = fixtures()["agreement"]
        def empty(task, allowed):
            if task.sources == ("ops_note",):
                return Finding()
            return fixture_specialist(task, allowed)
        result = fixture.run(specialist=empty)
        self.assertTrue(result.needs_review)
        self.assertEqual(result.decisions[TOPIC].status, "supported")
        self.assertEqual(result.termination, "no_open_conflicts")

    def test_failed_seed_is_not_reported_as_complete(self):
        fixture = fixtures()["agreement"]
        def failing(task, allowed):
            if task.sources == ("ops_note",):
                raise RuntimeError("fixture")
            return fixture_specialist(task, allowed)
        result = fixture.run(specialist=failing)
        self.assertTrue(result.needs_review)
        self.assertEqual(result.decisions[TOPIC].status, "supported")

    def test_unknown_citation_rejects_whole_branch(self):
        fixture = fixtures()["agreement"]
        result = fixture.run(specialist=lambda task, allowed: Finding((allowed[0].id, "fabricated")))
        self.assertEqual(result.evidence, ())
        self.assertTrue(all(b.status == "failed" for b in result.branches))
        self.assertTrue(result.needs_review)

    def test_other_source_citation_rejected_even_if_in_catalog(self):
        result = fixtures()["agreement"].run(specialist=lambda task, allowed: Finding(("a3",)))
        self.assertFalse(result.evidence)

    def test_scope_mismatch_does_not_become_a_conflict(self):
        records = (
            Evidence("x", "one", "release", "staging", "v3", "Fixture"),
            Evidence("y", "two", "release", "production", "v2", "Fixture"),
        )
        seeds = tuple(Task("reader", e.claim, e.scope, (e.source,)) for e in records)
        result = Scheduler(records, {}).run(seeds, fixture_specialist)
        self.assertEqual(result.created_branches, 0)
        self.assertEqual({d.status for d in result.decisions.values()}, {"supported"})

    def test_majority_never_resolves_a_contradiction(self):
        records = [Evidence(str(i), f"source{i}", "c", "s", "yes", "Fixture") for i in range(10)]
        records.append(Evidence("no", "dissent", "c", "s", "no", "Fixture"))
        self.assertEqual(decide(records, frozenset()).status, "unresolved")

    def test_branch_limit(self):
        result = fixtures()["unresolved"].run(limits=Limits(max_branches=1))
        self.assertEqual((result.calls, result.created_branches, result.termination), (3, 1, "branch_limit"))
        self.assertTrue(result.needs_review)

    def test_zero_branches_stops_before_creation(self):
        result = fixtures()["conflict"].run(limits=Limits(max_branches=0))
        self.assertEqual((result.calls, result.created_branches), (2, 0))

    def test_depth_limit(self):
        result = fixtures()["unresolved"].run(limits=Limits(max_depth=1))
        self.assertEqual((result.calls, result.termination), (3, "depth_limit"))

    def test_call_limit_counts_seeds(self):
        for adaptive in (True, False):
            result = fixtures()["conflict"].run(adaptive=adaptive, limits=Limits(max_calls=1))
            self.assertEqual((result.calls, result.termination), (1, "call_limit"))
            self.assertTrue(result.needs_review)

    def test_zero_calls_produces_unknown_not_agreement(self):
        result = fixtures()["agreement"].run(limits=Limits(max_calls=0))
        self.assertEqual(result.calls, 0)
        self.assertEqual(result.decisions[TOPIC].status, "unknown")

    def test_calls_are_hard_bounded_in_both_modes(self):
        for cap in range(7):
            for adaptive in (True, False):
                result = fixtures()["unresolved"].run(adaptive=adaptive, limits=Limits(max_calls=cap))
                self.assertLessEqual(result.calls, cap)

    def test_round_robin_does_not_starve_second_conflict(self):
        records, seeds, probes = [], [], {}
        for topic in (("a", "s"), ("b", "s")):
            for value in ("yes", "no"):
                source = f"{topic[0]}-{value}"
                records.append(Evidence(source, source, *topic, value, "Fixture"))
                seeds.append(Task("reader", *topic, (source,)))
            probes[topic] = (Probe("empty_one", ("missing1",)), Probe("empty_two", ("missing2",)))
        result = Scheduler(records, probes, limits=Limits(max_branches=2)).run(seeds, fixture_specialist)
        self.assertEqual([b.task.claim for b in result.branches[4:]], ["a", "b"])

    def test_duplicate_catalog_ids_rejected(self):
        item = fixtures()["agreement"].catalog[0]
        with self.assertRaises(ValueError):
            Scheduler((item, item), {})

    def test_limits_reject_negative_or_bool(self):
        for value in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                Limits(max_calls=value)

    def test_runs_do_not_share_mutable_execution_state(self):
        fixture = fixtures()["conflict"]
        scheduler = Scheduler(fixture.catalog, fixture.probes, fixture.authoritative_sources)
        self.assertEqual(scheduler.run(fixture.seeds, fixture_specialist), scheduler.run(fixture.seeds, fixture_specialist))

    def test_keyboard_interrupt_is_not_swallowed(self):
        def interrupt(task, allowed):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            fixtures()["agreement"].run(specialist=interrupt)


class ResponsesAdapterTests(unittest.TestCase):
    def setUp(self):
        self.task = fixtures()["agreement"].seeds[0]
        self.allowed = (fixtures()["agreement"].catalog[0],)

    def adapter(self, payload=None, status="completed", output=()):
        response = SimpleNamespace(status=status, output=output, output_text=json.dumps(payload or {"evidence_ids": ["a1"], "note": "Fixture"}))
        self.client = SimpleNamespace(responses=SimpleNamespace(create=Mock(return_value=response)))
        return ResponsesSpecialist(self.client, "fixture-model-not-a-live-model")

    def test_request_shape_and_fake_response(self):
        finding = self.adapter()(self.task, self.allowed)
        self.assertEqual(finding.evidence_ids, ("a1",))
        kwargs = self.client.responses.create.call_args.kwargs
        self.assertFalse(kwargs["store"])
        self.assertEqual(kwargs["max_output_tokens"], 600)
        self.assertTrue(kwargs["text"]["format"]["strict"])
        self.assertEqual(kwargs["text"]["format"]["type"], "json_schema")
        self.assertNotIn("tools", kwargs)
        self.assertEqual(json.loads(kwargs["input"])["records"][0]["id"], "a1")

    def test_missing_model_rejected(self):
        with self.assertRaises(ValueError):
            ResponsesSpecialist(object(), "")

    def test_incomplete_response_rejected(self):
        with self.assertRaises(ValueError):
            self.adapter(status="incomplete")(self.task, self.allowed)

    def test_refusal_rejected(self):
        output = [SimpleNamespace(content=[SimpleNamespace(type="refusal")])]
        with self.assertRaises(ValueError):
            self.adapter(output=output)(self.task, self.allowed)

    def test_invalid_payloads_rejected(self):
        payloads = [
            {"evidence_ids": ["fabricated"], "note": "x"},
            {"evidence_ids": "a1", "note": "x"},
            {"evidence_ids": [3], "note": "x"},
            {"evidence_ids": ["a1"] * 33, "note": "x"},
            {"evidence_ids": ["a1"], "note": "x", "authority": True},
            {"evidence_ids": ["a1"], "note": "x" * 1001},
            {"evidence_ids": ["a1"], "note": None},
        ]
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.adapter(payload)(self.task, self.allowed)

    def test_malformed_json_rejected(self):
        adapter = self.adapter()
        self.client.responses.create.return_value.output_text = "not JSON"
        with self.assertRaises(ValueError):
            adapter(self.task, self.allowed)

    def test_transport_failure_recorded_as_branch_failure(self):
        adapter = self.adapter()
        self.client.responses.create.side_effect = TimeoutError("fixture")
        result = fixtures()["agreement"].run(specialist=adapter)
        self.assertEqual(result.calls, 2)
        self.assertTrue(all(b.error_type == "TimeoutError" for b in result.branches))
        self.assertTrue(result.needs_review)


if __name__ == "__main__":
    unittest.main()
