import json
import os
import unittest
from datetime import date
from unittest.mock import Mock, patch

from devsecops.config import missing_credentials, provider_configuration
from devsecops.contracts import FOLLOWUP
from devsecops.network import FetchError, redact
from devsecops.providers import ModelClient
from devsecops.agents import research_incidents
from devsecops.demo import fixture
from tests.test_review import TEST_KEYS, gemini_response, groq_response

ANSWER = {'answer': 'Unknown', 'evidence_ids': [], 'incident_ids': [], 'unknowns': []}


@patch.dict(os.environ, TEST_KEYS)
class ProviderTests(unittest.TestCase):
    def client(self):
        return ModelClient(lambda *args: None, lambda: None)

    @patch('devsecops.providers.get_json')
    def test_groq_roles_use_distinct_models_and_only_groq_credentials(self, request):
        request.return_value = groq_response(ANSWER)
        client = self.client()
        for role, model in [('researcher', 'qwen/qwen3.8-27b'), ('reviewer', 'openai/gpt-oss-120b')]:
            client.call(role, 'Answer using JSON', {}, FOLLOWUP)
            call = request.call_args
            self.assertEqual(call.args[0], 'https://api.groq.com/openai/v1/chat/completions')
            payload = json.loads(call.kwargs['body'])
            self.assertEqual(payload['model'], model)
            self.assertTrue(payload['response_format']['json_schema']['strict'])
            self.assertNotIn('tools', payload)
            self.assertEqual(call.kwargs['headers']['Authorization'], 'Bearer test-groq')
            self.assertNotIn('x-goog-api-key', call.kwargs['headers'])
        self.assertEqual(client.tokens, 100)
        self.assertEqual(set(client.role_usage), {'researcher', 'reviewer'})

    @patch('devsecops.providers.get_json')
    def test_truncated_blocked_and_refused_outputs_are_rejected(self, request):
        truncated = groq_response(ANSWER)
        truncated['choices'][0]['finish_reason'] = 'length'
        refused = groq_response(ANSWER)
        refused['choices'][0]['message']['refusal'] = 'No'
        for response in (truncated, refused, {}, {'choices': []}):
            request.return_value = response
            with self.assertRaisesRegex(ValueError, 'invalid structured handoff'):
                self.client().call('reviewer', 'Answer', {}, FOLLOWUP)
        blocked = gemini_response(ANSWER)
        blocked['candidates'][0]['finishReason'] = 'SAFETY'
        request.return_value = blocked
        with self.assertRaises(ValueError):
            self.client().call('analyst', 'Answer', {}, FOLLOWUP)

    @patch('devsecops.providers.get_json')
    def test_json_and_local_schema_validation_fail_closed(self, request):
        for value in ({**ANSWER, 'execute': 'shell'}, {'answer': 'Missing fields'}, None):
            request.return_value = groq_response(value)
            with self.assertRaises(ValueError):
                self.client().call('reviewer', 'Answer', {}, FOLLOWUP)

    @patch('devsecops.providers.get_json')
    def test_model_call_cap_is_shared_across_roles(self, request):
        request.return_value = groq_response(ANSWER)
        client = self.client()
        for _ in range(6):
            client.call('reviewer', 'Answer', {}, FOLLOWUP)
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            client.call('researcher', 'Answer', {}, FOLLOWUP)
        self.assertEqual(request.call_count, 6)

    @patch('devsecops.providers.get_json')
    def test_tavily_uses_separate_auth_and_bounded_allowlisted_search(self, request):
        request.return_value = {'results': []}
        client = self.client()
        for _ in range(3):
            client.search('SSRF incident', ['cisa.gov'], date(2026, 1, 1), date(2026, 10, 30))
        payload = json.loads(request.call_args.kwargs['body'])
        self.assertEqual(payload['include_domains'], ['cisa.gov'])
        self.assertEqual(payload['start_date'], '2026-01-01')
        self.assertEqual(payload['max_results'], 6)
        self.assertFalse(payload['include_answer'])
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'], 'Bearer test-tavily')
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            client.search('fourth query', [], '', '')
        self.assertEqual(request.call_count, 3)
        self.assertEqual(client.calls, 0)

    @patch('devsecops.providers.get_json')
    def test_failed_search_consumes_budget_and_malformed_results_fail(self, request):
        request.side_effect = FetchError('Upstream HTTP 429: check credentials, rate limits, or access.')
        client = self.client()
        with self.assertRaisesRegex(ValueError, 'Tavily search failed'):
            client.search('query', [], '', '')
        self.assertEqual(client.search_calls, 1)
        request.side_effect = None
        request.return_value = {'results': 'unexpected'}
        with self.assertRaisesRegex(ValueError, 'invalid search results'):
            client.search('query', [], '', '')

    @patch('devsecops.providers.get_json')
    def test_missing_role_credential_fails_before_network(self, request):
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            with self.assertRaisesRegex(ValueError, 'GEMINI_API_KEY'):
                self.client().call('analyst', 'Answer', {}, FOLLOWUP)
        request.assert_not_called()

    def test_each_required_credential_controls_readiness_without_exposing_values(self):
        for name in TEST_KEYS:
            with patch.dict(os.environ, {name: ''}):
                config = provider_configuration()
                self.assertFalse(config['live_ready'])
                self.assertEqual(missing_credentials(), [name])
                for value in TEST_KEYS.values():
                    self.assertNotIn(value, json.dumps(config))
        self.assertTrue(provider_configuration()['live_ready'])

    def test_new_provider_key_formats_are_redacted(self):
        for prefix in ('gsk_', 'tvly-', 'AIza'):
            secret = prefix + 'a' * 40
            self.assertNotIn(secret, redact('key: ' + secret))

    @patch('devsecops.agents.fetch')
    def test_partial_search_failure_preserves_independently_fetched_evidence(self, fetch_page):
        _, profile, research, _ = fixture()
        source = research['sources'][0]
        url = 'https://www.cisa.gov/report'
        fetch_page.return_value = (source['text'].encode(), 'text/plain', url)
        client = Mock()
        client.call.side_effect = [
            {'queries': ['first query', 'second query']},
            {key: research[key] for key in ('incidents', 'research_limitations')}]
        client.search.side_effect = [ValueError('Tavily search failed'), {'results': [{'url': url}]}]
        result = research_incidents(profile, client, lambda *args: None, lambda: None)
        self.assertEqual(len(result['sources']), 1)
        self.assertTrue(result['incidents'])
        self.assertTrue(any(x.startswith('Search unavailable:') for x in result['research_limitations']))
        self.assertEqual(fetch_page.call_args.args[0], url)

    @patch('devsecops.agents.fetch')
    def test_untrusted_search_url_is_never_fetched(self, fetch_page):
        _, profile, _, _ = fixture()
        client = Mock()
        client.call.return_value = {'queries': ['SSRF campaign']}
        client.search_calls = 1
        client.search.return_value = {'results': [{'url': 'https://cisa.gov.evil.test/report'}]}
        result = research_incidents(profile, client, lambda *args: None, lambda: None)
        fetch_page.assert_not_called()
        self.assertEqual(result['incidents'], [])
        self.assertEqual(client.call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
