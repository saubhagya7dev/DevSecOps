import unittest

from devsecops.demo import fixture
from devsecops.research_queries import discovery_queries
from devsecops.sources import eligible_report
from devsecops.evidence import validate_research
from tests import test_incident_discovery_flow as research_fixtures
from tests.test_incident_discovery_flow import FixtureClient, incident, TEXT_A, TEXT_B, URL_A, URL_B


class QueryBreadthTests(unittest.TestCase):
    def test_queries_cover_recent_historical_and_guidance_without_requiring_a_victim(self):
        _, profile, _, _ = fixture()
        queries = discovery_queries(profile)
        self.assertEqual(set(queries), {'recent', 'historical', 'guidance'})
        self.assertEqual(len(queries['recent']), 2)
        self.assertEqual(len(queries['historical']), 3)
        self.assertIn('SSRF', ' '.join(queries['recent']))
        self.assertIn('hardening', queries['guidance'][0])
        self.assertEqual(len(set(sum(queries.values(), []))), 6)

    def test_no_verified_technology_or_component_produces_no_generic_search(self):
        queries = discovery_queries({'technologies': [], 'observations': [], 'components': []})
        self.assertFalse(any(queries.values()))

    def test_badge_urls_do_not_force_ssrf_and_queries_do_not_require_two_stacks_together(self):
        profile = {'technologies': [{'name': 'C++', 'evidence_ids': ['E1']},
                                    {'name': 'PyYAML', 'evidence_ids': ['E2']}],
                   'observations': [{'claim': 'Uses C++', 'quote': 'https://example.org/badge'},
                                    {'claim': 'Declares PyYAML', 'quote': 'PyYAML'}], 'components': []}
        queries = discovery_queries(profile)
        self.assertNotIn('SSRF', ' '.join(sum(queries.values(), [])))
        self.assertIn('memory safety', queries['recent'][0])
        self.assertIn('PyYAML unsafe deserialization', queries['recent'][1])
        self.assertNotIn('C++ PyYAML', ' '.join(sum(queries.values(), [])))

    def test_more_primary_publishers_and_specific_guidance_keep_index_pages_excluded(self):
        for url in ('https://www.elastic.co/security-labs/fixture-attack',
                    'https://www.sentinelone.com/labs/fixture-attack/',
                    'https://research.checkpoint.com/2026/fixture-attack/',
                    'https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html'):
            self.assertTrue(eligible_report(url), url)
        for url in ('https://cheatsheetseries.owasp.org/', 'https://www.elastic.co/security-labs/',
                    'https://untrusted.example/blog/attack'):
            self.assertFalse(eligible_report(url), url)

    def test_official_guidance_cannot_be_presented_as_an_observed_attack(self):
        source = {'id': 'S1', 'text': TEXT_A,
                  'url': 'https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html'}
        record = incident('S1', TEXT_A)
        result, warnings = validate_research({'sources': [source], 'incidents': [record], 'research_limitations': []}, 180)
        self.assertFalse(warnings)
        self.assertEqual(result['incidents'][0]['source_type'], 'background guidance')


class BreadthFlowTests(unittest.TestCase):
    # Reuse only the fixture helper; do not inherit its complete test suite.
    run_flow = research_fixtures.ResearchFlowTests.run_flow

    def test_background_record_does_not_block_historical_attack_discovery(self):
        background = incident('S1', TEXT_A)
        background['source_type'] = 'background guidance'
        old_attack = incident('S2', TEXT_B, 'I2')
        old_attack['title'] = 'Distinct historical attack'
        old_attack['publication_date'] = '2015-01-01'
        client = FixtureClient([[{'url': URL_A}], [{'url': URL_B}]], [[background], [old_attack]])
        result, attempts = self.run_flow(client, {URL_A: TEXT_A, URL_B: TEXT_B})
        self.assertTrue(result['coverage']['fallback_used'])
        self.assertEqual(result['coverage']['observed_attacks'], 1)
        self.assertEqual(result['coverage']['background_records'], 1)
        self.assertEqual(result['incidents'][1]['recency'], 'Background / outside window')
        self.assertIn('historical', [q['phase'] for q in result['coverage']['queries']])
        self.assertIn('guidance', [q['phase'] for q in result['coverage']['queries']])
        self.assertNotEqual(client.requests[1]['sources'][0]['id'], client.requests[2]['sources'][0]['id'])

    def test_empty_search_records_coverage_without_inventing_an_incident(self):
        client = FixtureClient([], [])
        client.researcher_allowance = 1000
        result, _ = self.run_flow(client, {})
        self.assertEqual(client.search_calls, 6)
        self.assertEqual(len(result['coverage']['queries']), 6)
        self.assertEqual(result['incidents'], [])
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(all(q['status'] == 'completed' and q['eligible_results'] == 0 for q in result['coverage']['queries']))

    def test_failed_searches_remain_failed_not_no_matching_incidents(self):
        class FailingSearch(FixtureClient):
            def search(self, *args):
                self.search_calls += 1
                raise ValueError('Tavily fixture unavailable')
        result, _ = self.run_flow(FailingSearch([], []), {})
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(all(q['status'] == 'failed' for q in result['coverage']['queries']))
        self.assertIn('failure', result['outcome'])
