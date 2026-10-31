import copy
import json
import unittest
from unittest.mock import patch

from devsecops import contracts
from devsecops.agents import PageText, INCIDENT_INSTRUCTIONS
from devsecops.demo import fixture
from devsecops.evidence import validate_research
from devsecops.incident_research import run_research, empty_discovery, deduplicate_incidents
from devsecops.network import FetchError
from devsecops.providers import ModelClient, RequestBudgetError, ResearchPacer
from tests.test_review import MemoryCache, TEST_KEYS, groq_response

URL_A = 'https://thedfirreport.com/2026/01/01/synthetic-first-attack'
URL_B = 'https://thedfirreport.com/2026/01/02/synthetic-second-attack'
TEXT_A = 'In this fictional incident an attacker exploited an exposed preview server to fetch private network resources. The prerequisite was attacker control over the destination and access to an exposed URL preview route.'
TEXT_B = 'In another fictional incident an attacker exploited an exposed service using an untrusted URL. The attacker required network access to the service and a route that accepted arbitrary destinations without network controls.'


def incident(source_id, text, identifier='I1'):
    return {'id': identifier, 'title': 'Synthetic fixture campaign', 'source_id': source_id, 'source_quote': text,
            'publication_date': 'unknown', 'incident_date': 'unknown', 'victim': 'Fictional fixture victim',
            'source_type': 'observed attack', 'mechanism': 'Attacker-selected URL request.', 'prerequisites': ['Untrusted URL'],
            'technologies': ['Preview service'], 'mitigations': ['Validate destinations'], 'unknowns': []}


class FixtureClient:
    def __init__(self, searches, extractions):
        self.calls = self.search_calls = 0
        self.searches, self.extractions = list(searches), list(extractions)
        self.context_omissions, self.requests = [], []

    def call(self, role, instructions, data, schema, **kwargs):
        self.calls += 1
        self.requests.append(copy.deepcopy(data))
        if schema is contracts.SEARCH_PLAN:
            return {'queries': ['Preview SSRF incident']}
        response = self.extractions.pop(0)
        if isinstance(response, Exception):
            raise response
        return {'incidents': copy.deepcopy(response), 'research_limitations': []}

    def search(self, query, domains, since, today):
        self.search_calls += 1
        return {'results': self.searches.pop(0) if self.searches else []}


class ResearchFlowTests(unittest.TestCase):
    def setUp(self):
        pacing = patch("devsecops.providers.RESEARCH_PACER")
        pacing.start()
        self.addCleanup(pacing.stop)

    def run_flow(self, client, pages, cache=None):
        _, profile, _, _ = fixture()
        attempts = []
        def fetch(url, **kwargs):
            attempts.append(url)
            value = pages[url]
            if isinstance(value, Exception):
                raise value
            return ('<article>' + value + '</article>').encode(), 'text/html', url
        result = run_research(profile, client, lambda *args: None, lambda: None, 180, {},
                              lambda *args: empty_discovery(), fetch, PageText,
                              INCIDENT_INSTRUCTIONS, cache or MemoryCache())
        return result, attempts

    def test_fallback_after_failed_retrieval_replaces_candidate_within_six_attempts(self):
        client = FixtureClient([[{'url': URL_A}], [{'url': URL_B}]], [[incident('S1', TEXT_B)]])
        result, attempts = self.run_flow(client, {URL_A: FetchError('403'), URL_B: TEXT_B})
        self.assertEqual(attempts, [URL_A, URL_B])
        self.assertEqual(len(result['incidents']), 1)
        self.assertEqual(client.search_calls, 2)
        self.assertEqual(result['coverage']['page_fetch_attempts'], 2)
        self.assertEqual(result['status'], 'partial')

    def test_empty_extraction_triggers_one_fallback_without_new_planning_call(self):
        client = FixtureClient([[{'url': URL_A}], [{'url': URL_B}]], [[], [incident('S2', TEXT_B)]])
        result, _ = self.run_flow(client, {URL_A: TEXT_A, URL_B: TEXT_B})
        self.assertEqual(client.calls, 3)  # one plan + two sequential extraction calls
        self.assertEqual(result['incidents'][0]['source_id'], 'S2')
        self.assertLessEqual(result['coverage']['source_text_characters_submitted'], 6000)
        self.assertEqual(result['coverage']['extraction_attempts'], 2)
        self.assertNotIn('profile', client.requests[-1])

    def test_blocked_optional_planning_does_not_mislabel_completed_discovery(self):
        class BlockedPlanner(FixtureClient):
            def call(self, role, instructions, data, schema, **kwargs):
                if schema is contracts.SEARCH_PLAN:
                    raise RequestBudgetError('Configured conservative token allowance is 1000')
                return super().call(role, instructions, data, schema, **kwargs)
        client = BlockedPlanner([[], []], [])
        result, attempts = self.run_flow(client, {})
        self.assertEqual(result['coverage']['query_planning'], 'deterministic fallback')
        self.assertEqual(client.search_calls, 3)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['error'], '')
        self.assertEqual(result['outcome'], 'no relevant incident found within searched coverage')
        self.assertEqual(result['coverage']['extraction_attempts'], 0)
        self.assertTrue(any('1000' in value for value in result['research_limitations']))
        self.assertEqual(attempts, [])

    def test_bad_quote_is_rejected_before_deciding_to_fallback(self):
        bad = incident('S1', 'A fabricated supporting quotation that does not exist anywhere in the stored source text.')
        client = FixtureClient([[{'url': URL_A}], [{'url': URL_B}]], [[bad], [incident('S2', TEXT_B)]])
        result, _ = self.run_flow(client, {URL_A: TEXT_A, URL_B: TEXT_B})
        self.assertEqual(len(result['incidents']), 1)
        self.assertEqual(result['incidents'][0]['source_id'], 'S2')
        self.assertTrue(any('could not be verified' in value for value in result['research_limitations']))

    def test_redirect_to_index_is_not_accepted_as_evidence(self):
        _, profile, _, _ = fixture()
        client = FixtureClient([[{'url': URL_A}], []], [])
        result = run_research(profile, client, lambda *args: None, lambda: None, 180, {},
                              lambda *args: empty_discovery(),
                              lambda *args, **kwargs: (TEXT_A.encode(), 'text/plain', 'https://thedfirreport.com/'),
                              PageText, INCIDENT_INSTRUCTIONS, MemoryCache())
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('Redirect outside' in value for value in result['research_limitations']))

    def test_six_fetch_attempts_are_not_increased_when_pages_fail(self):
        urls = [f'https://thedfirreport.com/2026/01/01/synthetic-{i}' for i in range(12)]
        client = FixtureClient([[{'url': url} for url in urls[:6]], [{'url': url} for url in urls[6:]]], [])
        result, attempts = self.run_flow(client, {url: FetchError('403') for url in urls})
        self.assertEqual(len(attempts), 6)
        self.assertEqual(result['coverage']['page_fetch_attempts'], 6)
        self.assertGreater(result['coverage']['omitted_candidates'], 0)
        self.assertEqual(client.calls, 1)

    def test_extraction_cache_reuses_work_but_model_change_invalidates_it(self):
        cache = MemoryCache()
        first = FixtureClient([[{'url': URL_A}]], [[incident('S1', TEXT_A)]])
        a, _ = self.run_flow(first, {URL_A: TEXT_A}, cache)
        second = FixtureClient([[{'url': URL_A}]], [])
        b, attempts = self.run_flow(second, {}, cache)
        self.assertEqual(second.calls, 1)  # planning only; extraction and page retrieval were cached
        self.assertEqual(attempts, [])
        self.assertEqual(b['coverage']['extraction_cache_hits'], 1)
        with patch('devsecops.incident_research.ROLE_MODELS', {'researcher': {'provider': 'groq', 'model': 'different'}}):
            third = FixtureClient([[{'url': URL_A}]], [[incident('S1', TEXT_A)]])
            c, _ = self.run_flow(third, {}, cache)
        self.assertEqual(third.calls, 2)
        self.assertEqual(c['coverage']['extraction_cache_hits'], 0)

    def test_multiple_sources_for_same_incident_are_retained_and_revalidated(self):
        sources = [{'id': 'S1', 'url': URL_A, 'text': TEXT_A, 'retrieved_at': 'fixture'},
                   {'id': 'S2', 'url': URL_B, 'text': TEXT_B, 'retrieved_at': 'fixture'}]
        merged = deduplicate_incidents([incident('S1', TEXT_A), incident('S2', TEXT_B, 'I2')], sources)
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]['supporting_sources']), 2)
        merged[0]['supporting_sources'][1]['source_quote'] = 'Fabricated quotation that cannot be found in the referenced stored source text.'
        research, warnings = validate_research({'incidents': merged, 'sources': sources, 'research_limitations': []}, 180)
        self.assertEqual(len(research['incidents'][0]['supporting_sources']), 1)
        self.assertTrue(warnings)

    @patch.dict('os.environ', TEST_KEYS)
    @patch('devsecops.providers.get_json')
    def test_token_guard_never_sends_unfit_researcher_request(self, request):
        client = ModelClient(lambda *args: None, lambda: None)
        with patch('devsecops.providers.RESEARCHER_TOKEN_BUDGET', 300):
            with self.assertRaises(RequestBudgetError):
                client.call('researcher', 'Extract facts', {'sources': [{'id': 'S1', 'passages': [TEXT_A * 30]}]}, contracts.INCIDENTS)
        request.assert_not_called()
        self.assertEqual(client.calls, 0)
        self.assertTrue(client.context_omissions)

    @patch.dict('os.environ', TEST_KEYS)
    @patch('devsecops.providers.get_json')
    def test_request_is_rebuilt_to_smaller_passages_before_submission(self, request):
        answer = {'answer': 'unknown', 'evidence_ids': [], 'incident_ids': [], 'unknowns': []}
        request.return_value = groq_response(answer)
        client = ModelClient(lambda *args: None, lambda: None)
        with patch('devsecops.providers.RESEARCHER_TOKEN_BUDGET', 2500):
            client.call('researcher', 'Extract facts', {'sources': [{'id': 'S1', 'passages': [TEXT_A * 40]}]}, contracts.FOLLOWUP)
        payload = json.loads(request.call_args.kwargs['body'])
        self.assertLess(len(payload['messages'][1]['content']), len(TEXT_A * 40))
        self.assertLessEqual(len(request.call_args.kwargs['body']), 18000)

    def test_local_minute_pacing_does_not_spike_sequential_research_calls(self):
        clock = [0.0]
        pacer = ResearchPacer()
        def advance(seconds):
            clock[0] += seconds
        with patch('devsecops.providers.time.monotonic', side_effect=lambda: clock[0]), \
                patch('devsecops.providers.time.sleep', side_effect=advance):
            pacer.reserve('fixture-model', 700, 1000, lambda: None, lambda *args: None)
            pacer.reserve('fixture-model', 700, 1000, lambda: None, lambda *args: None)
        self.assertGreaterEqual(clock[0], 60)
        self.assertEqual(sum(tokens for _, tokens in pacer.entries['fixture-model']), 700)

    @patch.dict('os.environ', TEST_KEYS)
    @patch('devsecops.providers.get_json')
    def test_exhausted_estimated_job_budget_sends_no_request(self, request):
        client = ModelClient(lambda *args: None, lambda: None)
        client.estimated_research_tokens = 7500
        with patch('devsecops.providers.RESEARCHER_TOKEN_BUDGET', 2500):
            with self.assertRaisesRegex(RequestBudgetError, 'job-token budget'):
                client.call('researcher', 'Answer', {}, contracts.FOLLOWUP, max_output_tokens=500)
        request.assert_not_called()

    def test_source_retry_after_defers_other_pages_on_same_host(self):
        client = FixtureClient([[{'url': URL_A}, {'url': URL_B}], []], [])
        result, attempts = self.run_flow(client, {URL_A: FetchError('429', status=429, retry_after=60), URL_B: TEXT_B})
        self.assertEqual(attempts, [URL_A])
        self.assertTrue(any('Retry-After' in value for value in result['research_limitations']))

    @patch.dict('os.environ', TEST_KEYS)
    @patch('devsecops.providers.time.monotonic', side_effect=[0, 1])
    @patch('devsecops.providers.get_json')
    def test_tavily_retry_counts_against_the_existing_search_ceiling(self, request, clock):
        request.side_effect = [FetchError('429', status=429, retry_after=0), {'results': []}]
        client = ModelClient(lambda *args: None, lambda: None)
        self.assertEqual(client.search('fixture query', ['thedfirreport.com'], None, None), {'results': []})
        self.assertEqual(client.search_calls, 2)


if __name__ == '__main__':
    unittest.main()
