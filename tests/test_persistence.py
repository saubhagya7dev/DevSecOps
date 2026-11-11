import json
import sqlite3
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from devsecops.store import Store
from tests.test_review import workspace_temp


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = workspace_temp()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'reviews.sqlite3'

    def test_legacy_upgrade_preserves_payload_events_and_backup(self):
        job = {'id': 'a' * 32, 'status': 'completed', 'stages': {}, 'updated_at': '2020-01-01T00:00:00+00:00',
               'report': 'report', 'artifacts': {'repository': {'commit': 'saved'}}}
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, data TEXT NOT NULL)')
            db.execute('INSERT INTO jobs VALUES (?,?)', (job['id'], json.dumps(job)))
            db.execute('INSERT INTO events(job_id,data) VALUES (?,?)', (job['id'], json.dumps({'title': 'retained'})))
        store = Store(self.path)
        saved = store.get(job['id'])
        self.assertEqual(saved['artifacts'], job['artifacts'])
        self.assertEqual(saved['report'], 'report')
        self.assertEqual(store.events(job['id'])[0]['seq'], 1)
        backup = self.path.with_name(self.path.name + '.v0.bak')
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(json.loads(db.execute('SELECT data FROM jobs').fetchone()[0]), job)
        self.assertEqual(Store(self.path).get(job['id']), saved)

    def test_metadata_updates_do_not_load_or_rewrite_artifacts(self):
        store = Store(self.path)
        job = store.create('https://github.com/example/repo', 'demo', 180)
        store.artifact(job['id'], 'large', {'text': 'x' * 100000})
        before = store.metadata(job['id'])
        store.stage(job['id'], 'prepare', 'running')
        after = store.metadata(job['id'])
        self.assertGreater(after['revision'], before['revision'])
        self.assertEqual(after['payload_revision'], before['payload_revision'])
        self.assertNotIn('artifacts', after)
        self.assertNotIn('report', store.list()[0])
        with store.connect() as db:
            self.assertLess(len(db.execute('SELECT data FROM jobs').fetchone()[0]), 1000)
        self.assertEqual(len(store.get(job['id'])['artifacts']['large']['text']), 100000)

    def test_concurrent_stage_writes_do_not_lose_other_stage_updates(self):
        store = Store(self.path)
        job = store.create('https://github.com/example/repo', 'demo', 180)
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda stage: store.stage(job['id'], stage, 'completed'), job['stages']))
        self.assertTrue(all(s == 'completed' for s in store.metadata(job['id'])['stages'].values()))

    def test_backup_and_retention_keep_active_work_and_remove_related_payloads(self):
        store = Store(self.path)
        old = store.create('https://github.com/example/old', 'demo', 180)
        active = store.create('https://github.com/example/active', 'demo', 180)
        store.update(old['id'], status='completed', report='saved')
        store.artifact(old['id'], 'evidence', {'saved': True})
        store.emit(old['id'], 'validation', 'done')
        backup = store.backup(Path(self.tmp.name) / 'backup.sqlite3')
        self.assertEqual(Store(backup).get(old['id'])['report'], 'saved')
        self.assertEqual(store.prune_history('9999-01-01T00:00:00+00:00'), 1)
        self.assertIsNotNone(store.get(active['id']))
        self.assertIsNone(store.get(old['id']))
        self.assertEqual(store.events(old['id']), [])
        with store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM artifacts').fetchone()[0], 0)
        with self.assertRaises(ValueError):
            store.backup(store.path)

    def test_unknown_future_schema_is_rejected(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('PRAGMA user_version=999')
        with self.assertRaisesRegex(ValueError, 'newer'):
            Store(self.path)
