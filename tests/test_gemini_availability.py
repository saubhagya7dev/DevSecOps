import os
import unittest
from unittest.mock import patch, Mock

from devsecops.contracts import PROFILE
from devsecops.demo import fixture
from devsecops.network import FetchError
from devsecops.providers import ModelClient
from tests.test_review import TEST_KEYS, gemini_response


@patch.dict(os.environ, TEST_KEYS)
class GeminiAvailabilityTests(unittest.TestCase):
    @patch('devsecops.providers.time.monotonic', side_effect=[0, 10])
    @patch('devsecops.providers.get_json')
    def test_503_without_header_retries_same_request_and_model(self, request, clock):
        profile = fixture()[1]
        request.side_effect = [FetchError('503', status=503), gemini_response(profile)]
        events = []
        client = ModelClient(lambda *args: events.append(args), lambda: None)
        self.assertEqual(client.call('analyst', 'Map', {}, PROFILE), profile)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0], request.call_args_list[1])
        self.assertEqual(client.calls, 1)
        self.assertEqual(client.retries, 1)
        self.assertTrue(any(event[1] == 'Provider unavailable; waiting to retry' for event in events))

    @patch('devsecops.providers.time.monotonic', side_effect=[0, 10])
    @patch('devsecops.providers.get_json')
    def test_persistent_503_stops_after_two_attempts_with_service_error(self, request, clock):
        request.side_effect = FetchError('503', status=503, retry_after=2)
        client = ModelClient(lambda *args: None, lambda: None)
        with self.assertRaisesRegex(ValueError, 'Provider service unavailable'):
            client.call('analyst', 'Map', {}, PROFILE)
        self.assertEqual(client.request_attempts, 2)
        self.assertEqual(client.retries, 1)

    @patch('devsecops.providers.get_json')
    def test_authentication_errors_are_not_retried(self, request):
        request.side_effect = FetchError('401', status=401)
        with self.assertRaises(ValueError):
            ModelClient(lambda *args: None, lambda: None).call('analyst', 'Map', {}, PROFILE)
        self.assertEqual(request.call_count, 1)

    @patch('devsecops.providers.get_json')
    def test_long_retry_after_is_not_ignored(self, request):
        request.side_effect = FetchError('503', status=503, retry_after=120)
        with self.assertRaises(ValueError):
            ModelClient(lambda *args: None, lambda: None).call('analyst', 'Map', {}, PROFILE)
        self.assertEqual(request.call_count, 1)

    @patch('devsecops.providers.time.monotonic', side_effect=[0, 0.1])
    @patch('devsecops.providers.get_json')
    def test_cancellation_interrupts_503_wait(self, request, clock):
        request.side_effect = FetchError('503', status=503)
        checkpoint = Mock(side_effect=[None, RuntimeError('Cancelled')])
        with self.assertRaisesRegex(RuntimeError, 'Cancelled'):
            ModelClient(lambda *args: None, checkpoint).call('analyst', 'Map', {}, PROFILE)
        self.assertEqual(request.call_count, 1)
