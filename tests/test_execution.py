import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from devsecops.execution import cancellation_checks, check_execution, execution_budget, request_deadline
from devsecops.pipeline import Runner, ReviewServices
from devsecops.store import Store
from tests.test_review import workspace_temp


class ExecutionTests(unittest.TestCase):
    def test_request_deadline_is_clamped_and_context_resets(self):
        with patch('devsecops.execution.time.monotonic', return_value=100):
            with execution_budget(5):
                self.assertEqual(request_deadline(180), 105)
            self.assertEqual(request_deadline(180), 280)

    def test_expired_budget_stops_before_another_network_operation(self):
        with patch('devsecops.execution.time.monotonic', return_value=100):
            with execution_budget(5):
                with patch('devsecops.execution.time.monotonic', return_value=106):
                    with self.assertRaisesRegex(ValueError, 'time budget'):
                        check_execution()

    def test_cancellation_callback_is_scoped_to_the_current_job(self):
        callback = Mock(side_effect=RuntimeError('cancelled'))
        with cancellation_checks(callback):
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                check_execution()
        check_execution()
        callback.assert_called_once()

    def test_expired_queue_job_never_constructs_a_provider_client(self):
        with workspace_temp() as tmp:
            store = Store(Path(tmp) / 'reviews.sqlite3')
            job = store.create('https://github.com/example/repo', 'demo', 180)
            store.update(job['id'], created_at='2000-01-01T00:00:00+00:00')
            client = Mock()
            services = ReviewServices(client, Mock(), Mock(), Mock(), Mock(), Mock())
            runner = Runner(store, demo_delay=0, services=services)
            try:
                with self.assertLogs('devsecops.pipeline', level='ERROR'):
                    runner.run(job['id'])
                client.assert_not_called()
                self.assertEqual(store.metadata(job['id'])['status'], 'failed')
                self.assertIn('queue', store.metadata(job['id'])['error'])
            finally:
                runner.pool.shutdown(wait=True)
