import unittest
import os
from unittest.mock import patch

from devsecops import contracts
from devsecops.providers import ModelClient
from devsecops.incident_research import COMPACT_PROMPT, expand_compact
from devsecops.evidence import validate_research
from devsecops.context import reviewer_views
from tests.test_review import TEST_KEYS, groq_response

PASSAGE = 'The attacker exploited an exposed endpoint to access private resources through an attacker-controlled destination.'


class CompactResearchTests(unittest.TestCase):
    def test_reviewer_retains_quote_tail_that_can_dispute_a_claim(self):
        quote = 'An initially reported vulnerability. ' * 12 + 'The claimed vulnerable function does not exist.'
        _, view = reviewer_views({'observations': [], 'technologies': [], 'unknowns': []},
                                {'incidents': [{'source_quote': quote}], 'research_limitations': []})
        self.assertEqual(view['incidents'][0]['source_quote'], quote)

    @patch.dict(os.environ, TEST_KEYS)
    @patch('devsecops.providers.RESEARCHER_TOKEN_BUDGET', 1000)
    @patch('devsecops.providers.RESEARCH_PACER')
    @patch('devsecops.providers.get_json')
    def test_real_serialized_contract_fits_existing_1000_token_guard(self, request, pacing):
        value = {'k': 1, 'm': 'SSRF', 'p': 'Attacker controls destination'}
        request.return_value = groq_response(value)
        client = ModelClient(lambda *args: None, lambda: None)
        response = client.call('researcher', COMPACT_PROMPT, {'sources': [
            {'id': 'S7', 'passages': [PASSAGE * 4]}]}, contracts.COMPACT_INCIDENT, max_output_tokens=192)
        self.assertEqual(response, value)
        self.assertEqual(request.call_count, 1)
        context = client.request_contexts[0]
        self.assertLessEqual(context['estimated_input_tokens'] + context['reserved_output_tokens'], 1000)
        self.assertEqual(context['source_ids'], ['S7'])

    def test_python_assigns_source_and_does_not_invent_dates_or_victim(self):
        source = {'id': 'S7', 'title': 'Synthetic attack report', 'text': PASSAGE,
                  'url': 'https://thedfirreport.com/2026/01/01/fixture', 'retrieved_at': 'fixture'}
        result = expand_compact({'k': 1, 'm': 'SSRF', 'p': 'Attacker control'},
                                [{'id': 'S7', 'passages': [PASSAGE]}], [source])
        result['sources'] = [source]
        result, warnings = validate_research(result, 180)
        self.assertFalse(warnings)
        self.assertEqual(result['incidents'][0]['source_id'], 'S7')
        self.assertEqual(result['incidents'][0]['publication_date'], 'unknown')
        self.assertEqual(result['incidents'][0]['victim'], 'undisclosed')

    def test_fabricated_compact_quote_is_still_rejected(self):
        source = {'id': 'S1', 'title': 'Fixture', 'text': PASSAGE}
        result = expand_compact({'k': 1, 'm': 'Invented', 'p': 'unknown'},
                                [{'id': 'S1', 'passages': ['A fabricated passage that does not appear anywhere in the retained source text.']}], [source])
        result['sources'] = [source]
        checked, warnings = validate_research(result, 180)
        self.assertFalse(checked['incidents'])
        self.assertTrue(warnings)

    def test_none_remains_valid_without_forcing_an_incident(self):
        result = expand_compact({'k': 0, 'm': '', 'p': ''}, [{'id': 'S1'}], [])
        self.assertEqual(result['incidents'], [])

    def test_category_is_preserved_separately_from_observed_attacks(self):
        source = {'id': 'S1', 'title': 'Fixture', 'text': PASSAGE}
        for kind, category in [(2, 'vulnerability advisory'), (3, 'background guidance')]:
            result = expand_compact({'k': kind, 'm': 'Mechanism', 'p': 'unknown'},
                                    [{'id': 'S1', 'passages': [PASSAGE]}], [source])
            self.assertEqual(result['incidents'][0]['source_type'], category)
