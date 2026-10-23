import unittest
from dataclasses import replace
from revision_gate import Source, snapshot, bind_finding, revalidate

class RevisionGateTests(unittest.TestCase):
    def setUp(self):
        self.sources = snapshot([Source('a', 'A fictional workshop opens at 10:00.'), Source('b', 'Twelve seats are available.')])
        self.candidate = {'claim': 'Workshop opens at ten.', 'source_id': 'a', 'quote': 'opens at 10:00'}
        self.bound = bind_finding(self.candidate, self.sources)

    def test_unchanged(self):
        self.assertEqual(revalidate(self.bound, self.sources), 'snapshot_matches_not_semantically_verified')

    def test_revised_context_with_surviving_quote(self):
        revised = snapshot([Source('a', self.sources['a'].text + ' Update: canceled today.')])
        self.assertIn(self.bound.quote, revised['a'].text)
        self.assertEqual(revalidate(self.bound, revised), 'source_changed')

    def test_changed_quote(self):
        self.assertEqual(revalidate(self.bound, snapshot([Source('a', 'Opens at 11:00.')])), 'source_changed')

    def test_missing_source(self):
        self.assertEqual(revalidate(self.bound, snapshot([])), 'source_missing')

    def test_unknown_reference(self):
        with self.assertRaises(ValueError): bind_finding(dict(self.candidate, source_id='unknown'), self.sources)

    def test_wrong_source(self):
        with self.assertRaises(ValueError): bind_finding(dict(self.candidate, source_id='b'), self.sources)

    def test_fabricated_quote(self):
        with self.assertRaises(ValueError): bind_finding(dict(self.candidate, quote='opens at 11:00'), self.sources)

    def test_empty_quote(self):
        with self.assertRaises(ValueError): bind_finding(dict(self.candidate, quote=' '), self.sources)

    def test_model_cannot_supply_digest(self):
        with self.assertRaises(ValueError): bind_finding(dict(self.candidate, source_digest='fake'), self.sources)

    def test_duplicate_source_ids(self):
        with self.assertRaises(ValueError): snapshot([Source('a','one'), Source('a','two')])

    def test_snapshot_is_immutable(self):
        with self.assertRaises(TypeError): self.sources['a'] = Source('a', 'changed')

    def test_false_claim_can_pass_integrity(self):
        bad = bind_finding(dict(self.candidate, claim='Workshop opens at midnight.'), self.sources)
        self.assertEqual(revalidate(bad, self.sources), 'snapshot_matches_not_semantically_verified')

    def test_unicode_is_not_silently_normalized(self):
        original = snapshot([Source('a','Café opens at 10:00.')])
        candidate = dict(self.candidate, quote='Café')
        bound = bind_finding(candidate, original)
        self.assertEqual(revalidate(bound, snapshot([Source('a','Cafe\u0301 opens at 10:00.')])), 'source_changed')

    def test_mutated_bound_quote_detected(self):
        self.assertEqual(revalidate(replace(self.bound, quote='fabricated'), self.sources), 'quote_missing')

    def test_oversized_field(self):
        with self.assertRaises(ValueError): bind_finding(dict(self.candidate, claim='x'*2001), self.sources)

    def test_non_string_field(self):
        with self.assertRaises(ValueError): bind_finding(dict(self.candidate, quote=10), self.sources)


class ExtractionBoundaryTests(unittest.TestCase):
    def test_mock_does_not_import_or_call_sdk(self):
        import sys
        from unittest.mock import patch
        from live_extraction import extract_candidate
        with patch.dict(sys.modules, {'openai': None}):
            self.assertEqual(extract_candidate({})['source_id'], 'workshop')

    def test_live_requires_key(self):
        import os
        from unittest.mock import patch
        from live_extraction import extract_candidate
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'OPENAI_API_KEY'):
                extract_candidate({}, live=True)

    @unittest.skipUnless(__import__("importlib.util", fromlist=["find_spec"]).find_spec("openai"), "optional OpenAI SDK is not installed")
    def test_live_request_contract_without_network(self):
        import os
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        from live_extraction import extract_candidate
        fake = MagicMock()
        fake.responses.parse.return_value = SimpleNamespace(status='completed', output_parsed=SimpleNamespace(
            model_dump=lambda: {'claim': 'Ten.', 'source_id': 'a', 'quote': '10:00'}))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-test-placeholder'}), patch('openai.OpenAI') as factory:
            factory.return_value.__enter__.return_value = fake
            extract_candidate(snapshot([Source('a', 'Opens at 10:00.')]), live=True)
            self.assertEqual(factory.call_args.kwargs['max_retries'], 0)
            self.assertEqual(factory.call_args.kwargs['base_url'], 'https://api.openai.com/v1')
            self.assertFalse(fake.responses.parse.call_args.kwargs['store'])
            self.assertEqual(fake.responses.parse.call_args.kwargs['max_output_tokens'], 512)

    @unittest.skipUnless(__import__("importlib.util", fromlist=["find_spec"]).find_spec("openai"), "optional OpenAI SDK is not installed")
    def test_raw_failure_is_not_echoed(self):
        import os
        from unittest.mock import patch
        from live_extraction import extract_candidate
        with patch.dict(os.environ, {'OPENAI_API_KEY':'synthetic-test-placeholder'}), patch('openai.OpenAI', side_effect=Exception('PRIVATE BODY')):
            with self.assertRaises(RuntimeError) as ctx: extract_candidate({}, live=True)
            self.assertNotIn('PRIVATE', str(ctx.exception))

if __name__ == '__main__': unittest.main()
