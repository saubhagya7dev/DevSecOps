import os
import unittest
from unittest.mock import patch

from devsecops.diagnostics import check_apis
from tests.test_review import TEST_KEYS


@patch.dict(os.environ, {**TEST_KEYS, 'GITHUB_TOKEN': ''})
class DiagnosticTests(unittest.TestCase):
    def run_checks(self):
        output = []
        results = check_apis(lambda message, **kwargs: output.append(message))
        return results, '\n'.join(output)

    def configure(self, client, github):
        client.return_value.call.side_effect = lambda role, prompt, data, schema, **kwargs: data['expected_response']
        client.return_value.search.return_value = {'results': [{'url': 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog'}]}
        github.return_value = {'full_name': 'octocat/Hello-World'}

    @patch('devsecops.diagnostics.get_json')
    @patch('devsecops.diagnostics.ModelClient')
    def test_all_integrations_are_checked_using_small_role_contract_requests(self, client, github):
        self.configure(client, github)
        results, output = self.run_checks()
        self.assertTrue(all(result['status'] == 'PASS' for result in results))
        self.assertEqual(len(results), 5)
        self.assertEqual([call.args[0] for call in client.return_value.call.call_args_list],
                         ['analyst', 'researcher', 'reviewer'])
        self.assertTrue(all(call.kwargs['max_output_tokens'] == 2048
                            for call in client.return_value.call.call_args_list))
        self.assertEqual(client.return_value.search.call_args.args[-2:], (None, None))
        self.assertIn('5/5', output)
        for key in TEST_KEYS.values():
            self.assertNotIn(key, output)

    @patch('devsecops.diagnostics.get_json')
    @patch('devsecops.diagnostics.ModelClient')
    def test_one_failed_model_does_not_prevent_other_api_checks(self, client, github):
        self.configure(client, github)
        def answer(role, prompt, data, schema, **kwargs):
            if role == 'analyst':
                raise ValueError('Upstream HTTP 403')
            return data['expected_response']
        client.return_value.call.side_effect = answer
        results, _ = self.run_checks()
        self.assertEqual(results[0]['status'], 'FAIL')
        self.assertTrue(all(result['status'] == 'PASS' for result in results[1:]))

    @patch('devsecops.diagnostics.get_json')
    @patch('devsecops.diagnostics.ModelClient')
    def test_missing_keys_are_reported_without_model_or_search_requests(self, client, github):
        self.configure(client, github)
        with patch.dict(os.environ, {name: '' for name in TEST_KEYS}):
            results, output = self.run_checks()
        self.assertEqual([r['status'] for r in results], ['MISSING'] * 4 + ['PASS'])
        client.return_value.call.assert_not_called()
        client.return_value.search.assert_not_called()
        self.assertIn('GEMINI_API_KEY', output)

    @patch('devsecops.diagnostics.get_json')
    @patch('devsecops.diagnostics.ModelClient')
    def test_unexpected_provider_errors_do_not_print_response_data(self, client, github):
        self.configure(client, github)
        client.return_value.call.side_effect = RuntimeError('sensitive-response-body')
        results, output = self.run_checks()
        self.assertEqual(results[0]['status'], 'FAIL')
        self.assertNotIn('sensitive-response-body', output)


if __name__ == '__main__':
    unittest.main()
