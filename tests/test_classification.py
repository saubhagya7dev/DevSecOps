import unittest

from devsecops.demo import fixture
from devsecops.evidence import validate_review


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        _, self.profile, self.research, self.review = fixture()
        self.finding = self.review['findings'][0]
        self.finding['classification'] = 'Supported concern'
        self.finding['missing_information'] = []
        self.research['incidents'][0]['source_type'] = 'observed attack'
        self.assessment = self.finding['prerequisite_assessments'][0]
        self.assessment['state'] = 'supported'

    def validate(self):
        return validate_review(self.review, self.profile, self.research)[0]

    def test_direct_complete_assessment_can_retain_supported_classification(self):
        self.assertEqual(self.validate()['findings'][0]['classification'], 'Supported concern')

    def test_unknown_prerequisite_or_missing_context_downgrades(self):
        self.assessment['state'] = 'unknown'
        self.assertEqual(self.validate()['findings'][0]['classification'], 'Needs verification')

    def test_missing_information_overrides_model_supported_label(self):
        self.finding['missing_information'] = ['Deployment policy']
        self.assertEqual(self.validate()['findings'][0]['classification'], 'Needs verification')

    def test_contradiction_rejects_finding_and_retains_reason(self):
        self.assessment['state'] = 'contradicted'
        review = self.validate()
        self.assertEqual(review['findings'], [])
        self.assertIn('contradicted', review['rejected_matches'][0]['reason'])

    def test_invalid_or_inferred_assessment_cannot_establish_prerequisite(self):
        self.assessment['evidence_ids'] = ['E999']
        self.assertEqual(self.validate()['findings'][0]['classification'], 'Needs verification')

    def test_old_review_without_assessments_is_conservatively_downgraded(self):
        self.finding.pop('prerequisite_assessments')
        self.assertEqual(self.validate()['findings'][0]['classification'], 'Needs verification')
