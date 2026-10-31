import json
import os
import unittest
from unittest.mock import Mock, patch

from devsecops.agents import PageText, research_incidents, search_sources
from devsecops.context import source_views, reviewer_views
from devsecops.contracts import FOLLOWUP
from devsecops.demo import fixture
from devsecops.network import FetchError, upstream_error
from devsecops.providers import ModelClient
from tests.test_review import MemoryCache, TEST_KEYS, groq_response

ANSWER = {'answer': 'Unknown', 'evidence_ids': [], 'incident_ids': [], 'unknowns': []}


@patch.dict(os.environ, TEST_KEYS)
class RateLimitTests(unittest.TestCase):
    def test_github_403_identifies_exhausted_requests_and_reset_without_body(self):
        response = Mock(status=403)
        headers = {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '1793414451'}
        response.getheader.side_effect = lambda key, default=None: headers.get(key, default)
        error = upstream_error(response, host='api.github.com')
        self.assertIn('GitHub API rate limit exhausted', str(error))
        self.assertIn('2026-10-31 02:40:51 UTC', str(error))
        self.assertEqual(error.status, 403)
        response.read.assert_not_called()

    def test_permission_denials_and_other_hosts_are_not_called_github_rate_limits(self):
        for host, remaining in [('api.github.com', '1'), ('api.groq.com', '0')]:
            response = Mock(status=403)
            response.getheader.side_effect = lambda key, default=None: remaining if key == 'X-RateLimit-Remaining' else default
            self.assertIn('check credentials or access', str(upstream_error(response, host=host)))

    def setUp(self):
        pacing = patch("devsecops.providers.RESEARCH_PACER")
        pacing.start()
        self.addCleanup(pacing.stop)
        quota = patch("devsecops.providers.RESEARCHER_TOKEN_BUDGET", 8000)
        quota.start()
        self.addCleanup(quota.stop)
        cache = patch("devsecops.incident_research.ResearchCache", side_effect=MemoryCache)
        cache.start()
        self.addCleanup(cache.stop)
    @patch('devsecops.providers.time.monotonic', side_effect=[0, 1])
    @patch('devsecops.providers.get_json')
    def test_short_transient_429_is_retried_once_without_extra_logical_call(self, request, clock):
        request.side_effect = [FetchError('Rate limit', status=429, retry_after=0), groq_response(ANSWER)]
        events = []
        client = ModelClient(lambda *args: events.append(args), lambda: None)
        self.assertEqual(client.call('researcher', 'Answer', {}, FOLLOWUP), ANSWER)
        self.assertEqual(client.calls, 1)
        self.assertEqual(client.request_attempts, 2)
        self.assertEqual(client.retries, 1)
        self.assertTrue(any(event[1] == 'Rate limited; waiting to retry' for event in events))

    @patch('devsecops.providers.get_json')
    def test_daily_oversized_and_long_wait_limits_are_not_retried(self, request):
        errors = [FetchError('Rate limit', status=429, retry_after=1, token_limit=8000, requested_tokens=20000),
                  FetchError('Daily quota', status=429, retry_after=1, daily_limit=True),
                  FetchError('Long wait', status=429, retry_after=90),
                  FetchError('Unknown reset', status=429)]
        for error in errors:
            request.reset_mock()
            request.side_effect = error
            with self.assertRaises(ValueError):
                ModelClient(lambda *args: None, lambda: None).call('researcher', 'Answer', {}, FOLLOWUP)
            self.assertEqual(request.call_count, 1)

    @patch('devsecops.providers.time.monotonic', side_effect=[0, 0.1])
    @patch('devsecops.providers.get_json')
    def test_cancellation_interrupts_rate_limit_wait(self, request, clock):
        request.side_effect = FetchError('Rate limit', status=429, retry_after=1)
        checkpoint = Mock(side_effect=[None, RuntimeError('Cancelled')])
        with self.assertRaisesRegex(RuntimeError, 'Cancelled'):
            ModelClient(lambda *args: None, checkpoint).call('researcher', 'Answer', {}, FOLLOWUP)
        self.assertEqual(request.call_count, 1)

    @patch('devsecops.providers.get_json')
    def test_oversized_local_payload_is_blocked_before_request(self, request):
        with self.assertRaisesRegex(ValueError, 'context budget|token allowance'):
            ModelClient(lambda *args: None, lambda: None).call('researcher', 'Answer', {'text': 'x' * 18000}, FOLLOWUP)
        request.assert_not_called()

    def test_rate_metadata_exposes_only_numbers_not_org_or_message(self):
        response = Mock(status=429)
        response.getheader.return_value = '2'
        response.read.return_value = json.dumps({'error': {'message':
            'Request too large in organization SECRET_ORG tokens per minute (TPM): Limit 8000, Requested 23000 secret-key'}}).encode()
        error = upstream_error(response)
        self.assertEqual(error.status, 429)
        self.assertEqual(error.retry_after, 2)
        self.assertEqual(error.token_limit, 8000)
        self.assertEqual(error.requested_tokens, 23000)
        self.assertNotIn('SECRET_ORG', str(error))
        self.assertNotIn('secret-key', str(error))

    def test_source_excerpts_are_bounded_contiguous_and_keep_original_evidence(self):
        _, profile, research, _ = fixture()
        source = research['sources'][0]
        source['text'] = ('Unrelated navigation. ' * 100 + 'Attacker exploits requests SSRF vulnerability. ' * 100)
        original = source['text']
        views = source_views([source], profile, budget=1200)
        self.assertLessEqual(sum(len(p) for p in views[0]['passages']), 1200)
        self.assertTrue(all(p in original for p in views[0]['passages']))
        self.assertEqual(source['text'], original)

    def test_reviewer_does_not_receive_full_fetched_pages(self):
        _, profile, research, _ = fixture()
        research['sources'][0]['text'] = 'FULL_PAGE_SENTINEL'
        profile_view, research_view = reviewer_views(profile, research)
        self.assertNotIn('FULL_PAGE_SENTINEL', json.dumps(research_view))
        self.assertEqual(profile_view['observations'][0]['id'], 'E1')
        self.assertEqual(research_view['incidents'][0]['id'], 'I1')

    @patch('devsecops.agents.fetch')
    def test_extraction_failure_retains_fetched_sources_and_error(self, page):
        _, profile, research, _ = fixture()
        url = 'https://www.cisa.gov/news-events/cybersecurity-advisories/aa-fixture'
        page.return_value = (research['sources'][0]['text'].encode(), 'text/plain', url)
        client = Mock()
        client.search_calls = 0
        client.call.side_effect = [{'queries': ['SSRF attack']}, ValueError('Upstream HTTP 429')]
        client.search.return_value = {'results': [{'url': url}]}
        result = research_incidents(profile, client, lambda *args: None, lambda: None)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['sources'][0]['url'], url)
        self.assertEqual(result['incidents'], [])
        self.assertIn('429', result['error'])

    def test_weekly_indexes_and_support_threads_are_not_incident_candidates(self):
        candidates = search_sources({'results': [
            {'url': 'https://www.cisa.gov/news-events/bulletins/weekly'},
            {'url': 'https://learn.microsoft.com/en-us/answers/question'},
            {'url': 'https://cloud.google.com/blog/topics/threat-intelligence/report', 'title': 'Attack analysis'}]})
        self.assertEqual(len(candidates), 1)
        self.assertIn('threat-intelligence', candidates[0]['url'])

    def test_article_body_is_selected_before_navigation_consumes_context(self):
        parser = PageText()
        article = 'An attacker exploited a vulnerable model loading path. ' * 8
        parser.feed('<nav>' + 'Navigation ' * 3000 + '</nav><main><article>' + article + '</article></main><footer>Footer</footer>')
        self.assertEqual(parser.text(), article.strip())
        self.assertNotIn('Navigation', parser.text())

    def test_request_limit_is_not_misreported_as_a_token_limit(self):
        response = Mock(status=429)
        response.getheader.return_value = None
        response.read.return_value = json.dumps({'error': {'message':
            'requests per day (RPD): Limit 1000, Requested 1194'}}).encode()
        error = upstream_error(response)
        self.assertEqual(error.limit_kind, 'requests_per_day')
        self.assertTrue(error.daily_limit)
        self.assertIsNone(error.requested_tokens)
        self.assertNotIn('1194 tokens', str(error))

    def test_transient_503_preserves_retry_after_without_exposing_body(self):
        response = Mock(status=503)
        response.getheader.return_value = '4'
        error = upstream_error(response)
        self.assertEqual(error.status, 503)
        self.assertEqual(error.retry_after, 4)
        response.read.assert_not_called()

    @patch('devsecops.agents.fetch')
    def test_external_incident_extraction_receives_sources_without_target_profile(self, page):
        _, profile, research, _ = fixture()
        url = 'https://www.cisa.gov/news-events/cybersecurity-advisories/aa-fixture'
        page.return_value = (research['sources'][0]['text'].encode(), 'text/plain', url)
        client = Mock()
        client.search_calls = 0
        client.call.side_effect = [{'queries': ['SSRF incident']},
                                   {key: research[key] for key in ('incidents', 'research_limitations')}]
        client.search.return_value = {'results': [{'url': url}]}
        result = research_incidents(profile, client, lambda *args: None, lambda: None)
        extraction_data = client.call.call_args.args[2]
        self.assertNotIn('profile', extraction_data)
        self.assertTrue(extraction_data['sources'])
        self.assertEqual(result['incidents'][0]['id'], 'I1')


if __name__ == '__main__':
    unittest.main()
