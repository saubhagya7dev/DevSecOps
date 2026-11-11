import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from devsecops.cache import ResearchCache
from devsecops.pipeline import Runner
from devsecops.server import make_handler
from devsecops.store import Store
from tests.test_review import workspace_temp


class LocalStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = workspace_temp()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'reviews.sqlite3')
        self.cache = ResearchCache(self.root / 'cache')

    def tearDown(self):
        self.tmp.cleanup()

    def saved(self):
        job = self.store.create('https://github.com/example/repository', 'demo', 180)
        self.store.update(job['id'], status='completed', report='Saved report', artifacts={'evidence': 'saved'})
        self.store.emit(job['id'], 'validation', 'Completed')
        return job

    def test_clear_history_removes_reports_evidence_and_events(self):
        job = self.saved()
        self.assertEqual(self.store.clear_history(), {'investigations': 1, 'events': 1})
        self.assertIsNone(self.store.get(job['id']))
        self.assertEqual(self.store.events(job['id']), [])
        self.assertEqual(self.store.storage_stats()['investigations'], 0)

    def test_active_jobs_outside_the_recent_fifty_block_deletion(self):
        active = self.store.create('https://github.com/example/active', 'demo', 180)
        for _ in range(51):
            self.saved()
        self.assertNotIn(active['id'], [j['id'] for j in self.store.list()])
        self.assertEqual(self.store.storage_stats()['active'], 1)
        with self.assertRaisesRegex(ValueError, 'active investigations'):
            self.store.clear_history()
        self.assertEqual(self.store.storage_stats()['investigations'], 52)

    def test_cache_clear_only_removes_owned_cache_entries(self):
        self.cache.put('fixture', {'text': 'cached evidence'})
        temporary = self.cache.root / ('a' * 64 + '.123.tmp')
        temporary.write_text('stale write')
        unrelated = self.cache.root / 'keep.txt'
        unrelated.write_text('unrelated file')
        outside = self.root / 'credentials-placeholder.txt'
        outside.write_text('not a credential')
        self.assertEqual(self.cache.clear()['files'], 2)
        self.assertTrue(unrelated.exists())
        self.assertTrue(outside.exists())
        self.assertEqual(self.cache.storage_stats()['files'], 0)


class StorageApiTests(LocalStorageTests):
    # Inherit fixture helpers, not the direct-store tests.
    test_clear_history_removes_reports_evidence_and_events = None
    test_active_jobs_outside_the_recent_fifty_block_deletion = None
    test_cache_clear_only_removes_owned_cache_entries = None

    def setUp(self):
        super().setUp()
        self.runner = Runner(self.store, demo_delay=0)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, self.runner, 'fixture-token', self.cache))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.runner.pool.shutdown(wait=True)
        super().tearDown()

    def request(self, path, body=None, token='fixture-token'):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request('POST' if body is not None else 'GET', path,
                           body=json.dumps(body) if body is not None else None,
                           headers={'X-Review-Token': token})
        response = connection.getresponse()
        status, data = response.status, json.loads(response.read())
        connection.close()
        return status, data

    def test_explicit_confirmation_and_local_token_are_required(self):
        job = self.saved()
        for body, token, expected in [({'scope': 'all', 'confirmation': 'CLEAR'}, '', 403),
                                      ({'scope': 'all'}, 'fixture-token', 400),
                                      ({'scope': '../', 'confirmation': 'CLEAR'}, 'fixture-token', 400)]:
            self.assertEqual(self.request('/api/storage/clear', body, token)[0], expected)
        self.assertIsNotNone(self.store.get(job['id']))

    def test_history_only_keeps_research_cache(self):
        self.saved()
        self.cache.put('fixture', {'ok': True})
        self.assertEqual(self.request('/api/storage/clear', {'scope': 'history', 'confirmation': 'CLEAR'})[0], 200)
        self.assertEqual(self.store.list(), [])
        self.assertEqual(self.cache.get('fixture'), {'ok': True})

    def test_cache_only_keeps_reports_and_evidence(self):
        job = self.saved()
        self.cache.put('fixture', {'ok': True})
        self.assertEqual(self.request('/api/storage/clear', {'scope': 'cache', 'confirmation': 'CLEAR'})[0], 200)
        self.assertEqual(self.store.get(job['id'])['report'], 'Saved report')
        self.assertIsNone(self.cache.get('fixture'))

    def test_all_clears_both_scopes_and_updates_statistics(self):
        self.saved()
        self.cache.put('fixture', {'ok': True})
        self.assertEqual(self.request('/api/storage/clear', {'scope': 'all', 'confirmation': 'CLEAR'})[0], 200)
        status, data = self.request('/api/storage')
        self.assertEqual(status, 200)
        self.assertEqual(data['history']['investigations'], 0)
        self.assertEqual(data['cache']['files'], 0)

    def test_active_worker_prevents_both_history_and_cache_clear(self):
        self.store.create('https://github.com/example/active', 'demo', 180)
        self.cache.put('fixture', {'ok': True})
        self.assertEqual(self.request('/api/storage/clear', {'scope': 'all', 'confirmation': 'CLEAR'})[0], 409)
        self.assertIsNotNone(self.cache.get('fixture'))
        self.assertEqual(self.store.storage_stats()['investigations'], 1)

    def test_status_endpoint_omits_evidence_and_tracks_payload_revision(self):
        job = self.saved()
        status, metadata = self.request('/api/jobs/' + job['id'] + '/status')
        self.assertEqual(status, 200)
        self.assertNotIn('artifacts', metadata)
        self.assertNotIn('report', metadata)
        before = metadata['payload_revision']
        self.store.stage(job['id'], 'validation', 'completed')
        updated = self.request('/api/jobs/' + job['id'] + '/status')[1]
        self.assertGreater(updated['revision'], metadata['revision'])
        self.assertEqual(updated['payload_revision'], before)
        self.store.artifact(job['id'], 'additional', {'saved': True})
        self.assertGreater(self.request('/api/jobs/' + job['id'] + '/status')[1]['payload_revision'], before)

    def test_history_pagination_is_separate_from_lifecycle_queries(self):
        oldest = self.saved()
        newest = self.saved()
        status, page = self.request('/api/jobs?limit=1')
        self.assertEqual(status, 200)
        self.assertEqual([j['id'] for j in page], [newest['id']])
        page = self.request('/api/jobs?limit=1&before=' + newest['id'])[1]
        self.assertEqual([j['id'] for j in page], [oldest['id']])
        self.assertEqual(self.request('/api/jobs?limit=0')[0], 400)
