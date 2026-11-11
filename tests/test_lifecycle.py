import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from devsecops.ownership import InstanceLock
from devsecops.pipeline import Runner
from devsecops.store import QueueFull, Store
from tests.test_review import workspace_temp


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = workspace_temp()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'reviews.sqlite3')

    def create(self):
        return self.store.create('https://github.com/example/repo', 'demo', 180)

    def test_second_process_cannot_take_ownership_or_recover_live_job(self):
        job = self.create()
        self.store.update(job['id'], status='running')
        code = ('import sys; from devsecops.ownership import InstanceLock; '
                'lock=InstanceLock(sys.argv[1]); lock.__enter__()')
        with InstanceLock(self.root):
            result = subprocess.run([sys.executable, '-c', code, str(self.root)],
                                    capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Another DevSecOps instance', result.stderr)
            self.assertEqual(self.store.get(job['id'])['status'], 'running')
        with InstanceLock(self.root):
            pass

    def test_recovery_includes_jobs_older_than_history_page(self):
        old = self.create()
        for _ in range(51):
            newer = self.create()
            self.store.update(newer['id'], status='completed')
        self.assertEqual(self.store.count_active(), 1)
        self.store.recover()
        self.assertEqual(self.store.get(old['id'])['status'], 'failed')
        self.assertEqual(self.store.count_active(), 0)

    def test_admission_is_atomic_across_store_instances(self):
        def submit(_):
            try:
                Store(self.store.path).create('https://github.com/example/repo', 'demo', 180, capacity=5)
                return True
            except QueueFull:
                return False
        with ThreadPoolExecutor(max_workers=10) as pool:
            accepted = list(pool.map(submit, range(10)))
        self.assertEqual(sum(accepted), 5)
        self.assertEqual(self.store.count_active(), 5)

    def test_queued_cancellation_is_immediate_and_worker_does_not_reopen_it(self):
        job = self.create()
        self.assertEqual(self.store.cancel(job['id']), 'cancelled')
        self.assertEqual(self.store.count_active(), 0)
        runner = Runner(self.store, demo_delay=0)
        self.addCleanup(runner.pool.shutdown)
        runner.run(job['id'])
        saved = self.store.get(job['id'])
        self.assertEqual(saved['status'], 'cancelled')
        self.assertEqual(saved['artifacts'], {})
