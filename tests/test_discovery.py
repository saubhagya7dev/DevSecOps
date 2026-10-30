import copy
import json
import os
import base64
import unittest
from unittest.mock import patch

from devsecops.cache import ResearchCache
from devsecops.discovery import DiscoveryBudget, deduplicate_advisories, discover_structured, normalize_advisory
from devsecops.knowledge import normalize_attack, normalize_vcdb, technique_candidates, attack_mappings
from devsecops.knowledge import discover_knowledge, ATTACK_URL
from devsecops.network import FetchError
from devsecops.packages import package_inventory
from devsecops.sources import eligible_report
from tests.test_review import MemoryCache, workspace_temp

REPORT = 'https://thedfirreport.com/2026/02/23/fixture-intrusion/'
PACKAGE = {'name': 'demo-pkg', 'ecosystem': 'PyPI', 'version': None, 'version_kind': 'range or unknown',
           'path': 'requirements.txt', 'declaration': '>=1.0', 'exposure': 'unknown'}
OSV = {'id': 'PYSEC-2024-1', 'aliases': ['CVE-2024-12345', 'GHSA-aaaa-bbbb-cccc'], 'summary': 'Synthetic advisory',
       'published': '2024-01-01T00:00:00Z', 'affected': [{'package': {'name': 'demo_pkg', 'ecosystem': 'PyPI'},
            'ranges': [{'type': 'ECOSYSTEM', 'events': [{'introduced': '0'}, {'fixed': '2.0'}]}]}],
       'references': [{'url': REPORT}, {'url': 'https://evil.test/payload.exe'}]}
GHSA = {'ghsa_id': 'GHSA-aaaa-bbbb-cccc', 'cve_id': 'CVE-2024-12345', 'summary': 'Synthetic duplicate advisory',
        'published_at': '2024-01-01T00:00:00Z', 'html_url': 'https://github.com/advisories/GHSA-aaaa-bbbb-cccc',
        'vulnerabilities': [{'package': {'name': 'demo-pkg', 'ecosystem': 'pip'},
                              'vulnerable_version_range': '<2.0', 'first_patched_version': '2.0'}], 'references': [REPORT]}
STIX = {'id': 'bundle--fixture', 'objects': [
    {'type': 'attack-pattern', 'id': 'attack-pattern--supply', 'name': 'Compromise Software Dependencies',
     'description': 'Supply chain compromise of dependencies and package publication.',
     'external_references': [{'source_name': 'mitre-attack', 'external_id': 'T1195.001'}]},
    {'type': 'attack-pattern', 'id': 'attack-pattern--revoked', 'revoked': True, 'name': 'Revoked',
     'external_references': [{'source_name': 'mitre-attack', 'external_id': 'T9999'}]},
    {'type': 'relationship', 'relationship_type': 'uses', 'target_ref': 'attack-pattern--supply',
     'description': 'Synthetic procedure example.', 'external_references': [{'url': REPORT}]}]}


class StructuredDiscoveryTests(unittest.TestCase):
    def test_precise_individual_report_paths_and_untrusted_urls(self):
        for url in [REPORT, 'https://cloud.google.com/blog/topics/threat-intelligence/fixture',
                    'https://www.microsoft.com/en-us/security/blog/2026/01/01/fixture/',
                    'https://unit42.paloaltonetworks.com/fixture-attack/', 'https://www.wiz.io/blog/fixture-attack']:
            self.assertTrue(eligible_report(url), url)
        for url in ['https://thedfirreport.com/', 'https://thedfirreport.com/category/ransomware/',
                    'https://www.wiz.io/blog', 'https://cloud.google.com/blog/topics/threat-intelligence',
                    'https://learn.microsoft.com/answers/test', 'https://www.wiz.io.evil.test/blog/x',
                    'https://key@www.wiz.io/blog/x', 'https://www.wiz.io:8443/blog/x',
                    'https://unit42.paloaltonetworks.com/payload.exe']:
            self.assertFalse(eligible_report(url), url)
        self.assertFalse(eligible_report('https://www.wiz.io/blog/new-product', 'Introducing a new product'))

    def test_ranges_remain_unknown_and_lockfile_resolution_takes_precedence(self):
        repo = {'files': [{'path': 'requirements.txt', 'content': 'Demo_Pkg>=1.0,<2.0\nexact==1.2.3\n'},
                          {'path': 'package.json', 'content': '{"dependencies":{"left-pad":"^1.0.0"}}'},
                          {'path': 'package-lock.json', 'content': '{"packages":{"node_modules/left-pad":{"version":"1.3.0"}}}'}]}
        packages, _ = package_inventory(repo)
        by_name = {p['name']: p for p in packages}
        self.assertIsNone(by_name['demo-pkg']['version'])
        self.assertEqual(by_name['left-pad']['version'], '1.3.0')
        self.assertEqual(by_name['left-pad']['version_kind'], 'lockfile resolution')
        self.assertEqual(by_name['exact']['version_kind'], 'exact declaration')
        self.assertIn('not established', by_name['left-pad']['exposure'])

    def test_observed_technology_names_rank_packages_before_inventory_truncation(self):
        dependencies = {f'irrelevant-{i}': '^1.0' for i in range(30)}
        dependencies['express'] = '^4.0'
        packages, limitations = package_inventory({'files': [{'path': 'package.json',
            'content': json.dumps({'dependencies': dependencies})}]}, {'technologies': [{'name': 'Express'}]})
        self.assertEqual(packages[0]['name'], 'express')
        self.assertEqual(len(packages), 24)
        self.assertIsNone(packages[0]['version'])

    def test_advisory_normalization_alias_dedup_and_version_uncertainty(self):
        osv = normalize_advisory(OSV, PACKAGE, 'osv')
        ghsa = normalize_advisory(GHSA, PACKAGE, 'github')
        merged = deduplicate_advisories([osv, ghsa])
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]['provenance']), 2)
        self.assertEqual(merged[0]['fixed_versions'], ['2.0'])
        self.assertEqual(merged[0]['category'], 'vulnerability advisory')
        self.assertEqual(merged[0]['incident_date'], 'unknown')
        self.assertIn('unresolved', merged[0]['version_assessment'])
        self.assertIsNone(normalize_advisory(OSV, {**PACKAGE, 'name': 'other'}, 'osv'))

    @patch('devsecops.discovery.get_json')
    def test_structured_requests_use_declared_ecosystem_and_isolate_github_token(self, request):
        def respond(url, **kwargs):
            if 'osv.dev' in url:
                self.assertNotIn('Authorization', kwargs['headers'])
                body = json.loads(kwargs['body'])
                self.assertNotIn('version', body)
                self.assertEqual(body['package']['ecosystem'], 'PyPI')
                return {'vulns': [OSV]}
            self.assertIn('affects=demo-pkg', url)
            self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test-github')
            self.assertEqual(kwargs['redirects'], 0)
            return [GHSA]
        request.side_effect = respond
        budget = DiscoveryBudget(lambda: None, MemoryCache())
        repo = {'files': [{'path': 'requirements.txt', 'content': 'demo-pkg>=1.0'}]}
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'test-github'}), patch('devsecops.knowledge.discover_knowledge', return_value={
                'techniques': [], 'historical_records': [], 'attack_provenance': {}, 'references': [], 'limitations': []}):
            result = discover_structured(repo, {}, lambda: None, lambda *args: None, budget)
        self.assertEqual(len(result['advisories']), 1)
        self.assertEqual(len(result['references']), 1)
        self.assertEqual(request.call_count, 2)

    @patch('devsecops.discovery.get_json', return_value={})
    def test_api_and_dataset_budgets_and_cache_are_independent(self, request):
        budget = DiscoveryBudget(lambda: None, MemoryCache())
        budget.json('https://api.osv.dev/one')
        acquired = budget.retrieval_times['https://api.osv.dev/one']
        budget.json('https://api.osv.dev/one')
        self.assertEqual(budget.retrieval_times['https://api.osv.dev/one'], acquired)
        self.assertEqual(budget.cache_hits, 1)
        for i in range(11):
            budget.json(f'https://api.osv.dev/unique-{i}')
        with self.assertRaisesRegex(FetchError, 'budget exhausted'):
            budget.json('https://api.osv.dev/overflow')
        self.assertEqual(request.call_count, 12)
        separate = DiscoveryBudget(lambda: None, MemoryCache())
        separate.json('https://raw.githubusercontent.com/first', dataset=True)
        separate.json('https://raw.githubusercontent.com/second', dataset=True)
        with self.assertRaises(FetchError):
            separate.json('https://raw.githubusercontent.com/third', dataset=True)

    @patch('devsecops.discovery.time.monotonic', side_effect=[0, 1])
    @patch('devsecops.discovery.get_json')
    def test_structured_transient_retry_consumes_request_budget(self, request, clock):
        request.side_effect = [FetchError('429', status=429, retry_after=0), {'vulns': []}]
        budget = DiscoveryBudget(lambda: None, MemoryCache())
        self.assertEqual(budget.json('https://api.osv.dev/v1/query'), {'vulns': []})
        self.assertEqual(budget.requests, 2)
        self.assertEqual(budget.retries, 1)

    def test_attack_normalization_rejects_revoked_and_unsupported_mappings(self):
        index = normalize_attack(STIX)
        self.assertEqual(len(index['techniques']), 1)
        candidates = technique_candidates(index, {'summary': 'supply chain dependency compromise'}, [])
        self.assertEqual(candidates[0]['id'], 'T1195.001')
        mapped = attack_mappings([{'id': 'I1', 'source_quote': 'Technique T9999 was guessed by a model.'},
                                  {'id': 'I2', 'source_quote': 'Observed technique T1195.001 in the report.'}], candidates)
        self.assertEqual(mapped[0]['status'], 'unmapped')
        self.assertEqual(mapped[1]['technique_ids'], ['T1195.001'])
        self.assertIn(REPORT, candidates[0]['procedures'][0]['references'])

    def test_sparse_vcdb_is_historical_not_a_technical_finding(self):
        record = normalize_vcdb({'incident_id': 'synthetic-vcdb', 'summary': 'Demo-pkg was mentioned.',
                                 'timeline': {'incident': {'year': 2018}}, 'reference': [REPORT]},
                                {'demo-pkg'}, 'https://api.github.com/repos/vz-risk/VCDB/git/blobs/' + 'a' * 40)
        self.assertEqual(record['category'], 'historical incident record')
        self.assertEqual(record['incident_date'], 'unknown')
        self.assertIn('sparse', record['limitation'])
        self.assertIsNone(normalize_vcdb({'summary': 'Unrelated company'}, {'demo-pkg'}, 'origin'))
        invalid = normalize_vcdb({'summary': 'demo-pkg fixture', 'timeline': {'incident': {
            'year': 2024, 'month': 40, 'day': 90}}}, {'demo-pkg'}, 'origin')
        self.assertEqual(invalid['incident_date'], 'unknown')

    @patch.dict(os.environ, {'GITHUB_TOKEN': 'test-github'})
    def test_optional_vcdb_fetches_only_official_bounded_json_records(self):
        raw = {'incident_id': 'fixture-history', 'summary': 'demo-pkg historical incident', 'reference': [REPORT]}
        class Budget:
            def __init__(self):
                self.calls = []
            def json(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if url == ATTACK_URL:
                    return normalize_attack(STIX)
                if '/search/code?' in url:
                    return {'items': [{'sha': 'a' * 40, 'path': 'data/json/validated/fixture.json'},
                                      {'sha': 'b' * 40, 'path': 'payload.exe'}]}
                return {'encoding': 'base64', 'content': base64.b64encode(json.dumps(raw).encode()).decode()}
        budget = Budget()
        result = discover_knowledge({'technologies': [{'name': 'demo-pkg'}]}, [], budget, True)
        self.assertEqual(len(result['historical_records']), 1)
        self.assertEqual(len(budget.calls), 3)
        self.assertNotIn('headers', budget.calls[0][1])
        self.assertEqual(budget.calls[1][1]['headers']['Authorization'], 'Bearer test-github')
        self.assertTrue(budget.calls[2][0].startswith('https://api.github.com/repos/vz-risk/VCDB/git/blobs/'))

    @patch.dict(os.environ, {'GITHUB_TOKEN': ''})
    def test_vcdb_without_search_credentials_reports_a_limitation(self):
        from unittest.mock import Mock
        budget = Mock()
        budget.json.return_value = normalize_attack(STIX)
        result = discover_knowledge({'technologies': []}, [], budget, True)
        self.assertEqual(result['historical_records'], [])
        self.assertTrue(any('requires GITHUB_TOKEN' in value for value in result['limitations']))

    def test_advisory_cannot_become_an_observed_incident_by_normalization(self):
        advisory = normalize_advisory(OSV, PACKAGE, 'osv')
        self.assertNotIn('source_quote', advisory)
        self.assertNotIn('source_type', advisory)
        self.assertEqual(advisory['category'], 'vulnerability advisory')
        self.assertIn('does not establish an observed attack', advisory['limitation'])

    def test_cache_expiry_and_configuration_sensitive_keys(self):
        with workspace_temp() as temporary:
            cache = ResearchCache(temporary)
            cache.put(['model-a', {'schema': 1}, 'content-hash'], {'ok': True})
            self.assertEqual(cache.get(['model-a', {'schema': 1}, 'content-hash']), {'ok': True})
            self.assertIsNone(cache.get(['model-b', {'schema': 1}, 'content-hash']))
            self.assertIsNone(cache.get(['model-a', {'schema': 2}, 'content-hash']))
            expired = ResearchCache(temporary, ttl=-1)
            self.assertIsNone(expired.get(['model-a', {'schema': 1}, 'content-hash']))


if __name__ == '__main__':
    unittest.main()
