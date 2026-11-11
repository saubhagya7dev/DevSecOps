import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from devsecops.ownership import InstanceLock
from devsecops.server import LocalHTTPServer, _serve, serve
from devsecops.store import Store
from tests.test_review import workspace_temp


class ServerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = workspace_temp()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'reviews.sqlite3')

    def test_second_start_fails_before_opening_database(self):
        with InstanceLock(self.root), patch('devsecops.server.InstanceLock', side_effect=lambda: InstanceLock(self.root)), \
                patch('devsecops.server.Store') as factory:
            with self.assertRaisesRegex(ValueError, 'Another DevSecOps instance'):
                serve(0)
            factory.assert_not_called()

    def test_port_bind_failure_does_not_recover_or_cancel_existing_work(self):
        job = self.store.create('https://github.com/example/repo', 'demo', 180)
        self.store.update(job['id'], status='running')
        with patch('devsecops.server.Store', return_value=self.store), \
                patch('devsecops.server.LocalHTTPServer', side_effect=OSError('occupied')):
            with self.assertRaisesRegex(OSError, 'occupied'):
                _serve(8765)
        self.assertEqual(self.store.metadata(job['id'])['status'], 'running')

    def test_connection_limit_rejects_excess_requests_without_spawning_threads(self):
        server = LocalHTTPServer(('127.0.0.1', 0), Mock(), max_clients=1)
        self.addCleanup(server.server_close)
        server.slots.acquire()
        request = Mock()
        with patch.object(server, 'shutdown_request') as close:
            server.process_request(request, ('127.0.0.1', 1))
            close.assert_called_once_with(request)
        server.slots.release()
