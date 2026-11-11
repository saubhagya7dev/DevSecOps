import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from devsecops import contracts
from devsecops.demo import fixture
from devsecops.evidence import validate_review
from devsecops.pipeline import Runner, ReviewServices
from devsecops.review_fallback import repository_fallback
from devsecops.store import Store
from tests.test_review import workspace_temp, TEST_KEYS


class RepositoryReviewTests(unittest.TestCase):
    def setUp(self):
        self.repo, self.profile, self.research, self.review = fixture()

    def test_improvements_require_repository_citations_but_no_incident(self):
        review = repository_fallback(self.profile)
        checked, warnings = validate_review(review, self.profile, {'incidents': []})
        self.assertTrue(checked['findings'])
        self.assertFalse(warnings)
        self.assertEqual(checked['findings'][0]['classification'], 'Repository improvement')
        self.assertEqual(checked['findings'][0]['incident_ids'], [])
        self.assertTrue(checked['findings'][0]['evidence_ids'])

    def test_improvement_cannot_smuggle_incident_or_prerequisite_claim(self):
        for field, value in [('incident_ids', ['I1']), ('prerequisite_assessments', [{'state': 'supported'}]), ('evidence_ids', ['E999'])]:
            with self.subTest(field=field):
                review = repository_fallback(self.profile)
                review['findings'][0][field] = value
                checked, warnings = validate_review(review, self.profile, self.research)
                self.assertFalse(checked['findings'])
                self.assertTrue(warnings)

    def test_incident_classifications_still_require_external_evidence(self):
        for classification in ('Supported concern', 'Needs verification', 'Background lesson'):
            review = repository_fallback(self.profile)
            review['findings'][0]['classification'] = classification
            checked, warnings = validate_review(review, self.profile, {'incidents': []})
            self.assertFalse(checked['findings'])
            self.assertTrue(warnings)

    def test_no_observations_returns_explicit_questions_without_invented_citations(self):
        self.profile['observations'] = []
        review = repository_fallback(self.profile)
        self.assertFalse(review['findings'])
        self.assertTrue(any('No direct repository observations' in q for q in review['questions']))

    def test_no_inferred_observation_becomes_a_local_security_claim(self):
        self.profile['observations'][0]['kind'] = 'inferred'
        self.assertFalse(repository_fallback(self.profile)['findings'])

    def test_badge_urls_do_not_create_outbound_request_findings(self):
        self.profile['observations'][0].update(path='README.md', claim='Uses Python', quote='https://example.org/badge')
        review = repository_fallback(self.profile)
        self.assertNotIn('outbound', review['findings'][0]['title'])

    def test_manifest_parser_declaration_is_reviewed_as_dependency_configuration(self):
        self.profile['observations'][0].update(path='requirements.txt', claim='Declares PyYAML', quote='PyYAML')
        review = repository_fallback(self.profile)
        self.assertEqual(review['findings'][0]['title'], 'Review dependency reproducibility')

    def test_fallback_contract_matches_hosted_review_fields(self):
        review = repository_fallback(self.profile)
        review.pop('origin')
        contracts.validate_shape(review, contracts.REVIEW)

    @patch.dict('os.environ', TEST_KEYS)
    def test_zero_incidents_still_invokes_reviewer_and_finishes_report(self):
        self.research.update(incidents=[], sources=[], status='completed')
        self.review.update(findings=[], followup_requests=[])
        reviewer = Mock(return_value=self.review)
        client = SimpleNamespace(calls=2, tokens=0, role_usage={}, search_calls=0, request_attempts=0,
                                 retries=0, estimated_research_tokens=0, context_omissions=[], request_contexts=[])
        services = ReviewServices(lambda *args: client, lambda *args: self.repo, lambda *args: self.profile,
                                  lambda *args, **kwargs: self.research, reviewer, Mock())
        with workspace_temp() as root:
            store = Store(Path(root) / 'review.sqlite3')
            runner = Runner(store, services=services)
            try:
                job = store.create('https://github.com/test/repository', 'live', 180)
                runner.run(job['id'])
                result = store.get(job['id'])
                reviewer.assert_called_once()
                self.assertEqual(result['stages']['reviewer'], 'completed')
                self.assertEqual(result['status'], 'completed', result['error'])
                self.assertIn('Repository improvement', result['report'])
                self.assertEqual(result['artifacts']['review']['findings'][0]['incident_ids'], [])
            finally:
                runner.close()
