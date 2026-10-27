import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DATA, STAGES


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path=None):
        self.path = path or DATA / 'reviews.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_job ON events(job_id, seq);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, repo, mode, days):
        job = {'id': uuid.uuid4().hex, 'repository_url': repo, 'mode': mode, 'days': days,
               'status': 'queued', 'created_at': now(), 'updated_at': now(),
               'stages': {s: 'queued' for s in STAGES}, 'artifacts': {}, 'report': '', 'error': ''}
        with self.connect() as db:
            db.execute('INSERT INTO jobs VALUES (?,?)', (job['id'], json.dumps(job)))
        return job

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def update(self, job_id, **updates):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            job = json.loads(row[0])
            job.update(updates, updated_at=now())
            db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(job), job_id))
        return job

    def artifact(self, job_id, key, value):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
            job = json.loads(row[0])
            job['artifacts'][key] = value
            job['updated_at'] = now()
            db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(job), job_id))

    def transition(self, job_id, expected, **updates):
        """Atomically avoid cancellation/completion races between HTTP and worker threads."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                return False
            job = json.loads(row[0])
            if job['status'] not in expected:
                return False
            job.update(updates, updated_at=now())
            db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(job), job_id))
        return True

    def stage(self, job_id, stage, state):
        job = self.get(job_id)
        stages = {**job['stages'], stage: state}
        self.update(job_id, stages=stages)

    def emit(self, job_id, stage, title, detail=''):
        event = {'stage': stage, 'title': title, 'detail': detail, 'at': now()}
        with self.connect() as db:
            cursor = db.execute('INSERT INTO events(job_id,data) VALUES (?,?)', (job_id, json.dumps(event)))
            event['seq'] = cursor.lastrowid
        return event

    def events(self, job_id, after=0):
        with self.connect() as db:
            rows = db.execute('SELECT seq,data FROM events WHERE job_id=? AND seq>? ORDER BY seq LIMIT 200', (job_id, after)).fetchall()
        return [{**json.loads(data), 'seq': seq} for seq, data in rows]

    def list(self):
        with self.connect() as db:
            rows = db.execute('SELECT data FROM jobs ORDER BY rowid DESC LIMIT 50').fetchall()
        return [{k: v for k, v in json.loads(row[0]).items() if k not in ('report', 'artifacts')} for row in rows]

    def recover(self):
        for job in self.list():
            if job['status'] in ('queued', 'running', 'cancelling'):
                stages = {k: ('failed' if v == 'running' else 'skipped' if v == 'queued' else v) for k, v in job['stages'].items()}
                self.update(job['id'], status='failed', stages=stages, error='Server restarted during this analysis. Start a new review; saved evidence remains available.')
