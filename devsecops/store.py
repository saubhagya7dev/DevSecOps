"""SQLite adapter: indexed job metadata and separately versioned evidence payloads."""
import json
import sqlite3
import uuid
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA, STAGES
from .migrations import migrate

ACTIVE = ('queued', 'running', 'cancelling')
TERMINAL = ('completed', 'partial', 'failed', 'cancelled')


def now():
    return datetime.now(timezone.utc).isoformat()


class QueueFull(ValueError):
    pass


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else DATA / 'reviews.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            migrate(db, self.path)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _metadata(db, job_id):
        row = db.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _payload(db, job_id):
        artifacts = {key: json.loads(data) for key, data in db.execute(
            'SELECT key,data FROM artifacts WHERE job_id=?', (job_id,))}
        report = db.execute('SELECT content FROM reports WHERE job_id=?', (job_id,)).fetchone()
        return {'artifacts': artifacts, 'report': report[0] if report else ''}

    @staticmethod
    def _save(db, job, updates, *, payload_changed=False):
        updates = dict(updates)
        changed_payload = payload_changed or 'artifacts' in updates or 'report' in updates
        if 'artifacts' in updates:
            db.execute('DELETE FROM artifacts WHERE job_id=?', (job['id'],))
            for key, value in updates.pop('artifacts').items():
                db.execute('INSERT INTO artifacts VALUES (?,?,?,?)', (job['id'], key, 1, json.dumps(value)))
        if 'report' in updates:
            report = updates.pop('report')
            db.execute('INSERT OR REPLACE INTO reports VALUES (?,?)', (job['id'], report))
        job.update(updates, updated_at=now(), revision=job['revision'] + 1,
                   payload_revision=job['payload_revision'] + int(changed_payload))
        db.execute('UPDATE jobs SET data=?,status=? WHERE id=?', (json.dumps(job), job['status'], job['id']))
        return job

    @staticmethod
    def _active_count(db):
        return db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','cancelling')").fetchone()[0]

    def create(self, repo, mode, days, capacity=None):
        job = {'id': uuid.uuid4().hex, 'repository_url': repo, 'mode': mode, 'days': days,
               'status': 'queued', 'created_at': now(), 'updated_at': now(),
               'stages': {s: 'queued' for s in STAGES}, 'error': '', 'revision': 1, 'payload_revision': 0}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if capacity is not None and self._active_count(db) >= capacity:
                raise QueueFull('Analysis queue is full. Wait for a job to finish.')
            db.execute('INSERT INTO jobs(id,data,status) VALUES (?,?,?)', (job['id'], json.dumps(job), job['status']))
        return {**job, 'artifacts': {}, 'report': ''}

    def get(self, job_id):
        with self.connect() as db:
            # One consistent snapshot for metadata and payload revisions.
            db.execute('BEGIN')
            job = self._metadata(db, job_id)
            return {**job, **self._payload(db, job_id)} if job else None

    def metadata(self, job_id):
        with self.connect() as db:
            return self._metadata(db, job_id)

    def update(self, job_id, **updates):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._metadata(db, job_id)
            if not job:
                raise KeyError(job_id)
            self._save(db, job, updates)
            return job

    def artifact(self, job_id, key, value):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._metadata(db, job_id)
            if not job:
                raise KeyError(job_id)
            db.execute('INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?)', (job_id, key, 1, json.dumps(value)))
            self._save(db, job, {}, payload_changed=True)

    def transition(self, job_id, expected, **updates):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._metadata(db, job_id)
            if not job or job['status'] not in expected:
                return False
            self._save(db, job, updates)
        return True

    def stage(self, job_id, stage, state):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._metadata(db, job_id)
            if not job:
                raise KeyError(job_id)
            self._save(db, job, {'stages': {**job['stages'], stage: state}})

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

    def list(self, limit=50, before=None):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('History page size must be between 1 and 200.')
        with self.connect() as db:
            if before is None:
                rows = db.execute('SELECT data FROM jobs ORDER BY rowid DESC LIMIT ?', (limit,)).fetchall()
            else:
                rows = db.execute('SELECT data FROM jobs WHERE rowid < (SELECT rowid FROM jobs WHERE id=?) ORDER BY rowid DESC LIMIT ?', (before, limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def count_active(self):
        with self.connect() as db:
            return self._active_count(db)

    def list_active(self):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM jobs WHERE status IN ('queued','running','cancelling')").fetchall()
        return [json.loads(row[0]) for row in rows]

    def cancel(self, job_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._metadata(db, job_id)
            if not job:
                return None
            if job['status'] == 'queued':
                updates = {'status': 'cancelled', 'stages': {s: 'skipped' for s in job['stages']}}
            elif job['status'] == 'running':
                updates = {'status': 'cancelling'}
            else:
                return job['status']
            self._save(db, job, updates)
            return job['status']

    def recover(self):
        for job in self.list_active():
            stages = {k: ('failed' if v == 'running' else 'skipped' if v == 'queued' else v) for k, v in job['stages'].items()}
            self.transition(job['id'], ACTIVE, status='failed', stages=stages,
                            error='Server restarted during this analysis. Start a new review; saved evidence remains available.')

    def storage_stats(self):
        with self.connect() as db:
            db.execute('BEGIN')
            jobs = db.execute('SELECT count(*) FROM jobs').fetchone()[0]
            events = db.execute('SELECT count(*) FROM events').fetchone()[0]
            active = self._active_count(db)
        return {'investigations': jobs, 'events': events, 'active': active}

    def backup(self, destination):
        destination = Path(destination).resolve()
        live = self.path.resolve()
        reserved = {live, *(Path(str(live) + suffix) for suffix in ('-wal', '-shm', '-journal'))}
        if destination in reserved or destination.exists():
            raise ValueError('Choose a new backup file outside the live database files.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db, closing(sqlite3.connect(str(destination))) as target:
            db.backup(target)
        return destination

    def prune_history(self, before):
        """Explicit retention: terminal investigations older than an ISO timestamp only."""
        cutoff = datetime.fromisoformat(before)
        if cutoff.tzinfo is None:
            raise ValueError('Retention cutoff must include a timezone.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute("SELECT id,data FROM jobs WHERE status IN ('completed','partial','failed','cancelled')").fetchall()
            ids = [(job_id,) for job_id, data in rows if datetime.fromisoformat(json.loads(data)['updated_at']) < cutoff]
            db.executemany('DELETE FROM events WHERE job_id=?', ids)
            db.executemany('DELETE FROM jobs WHERE id=?', ids)
        return len(ids)

    def clear_history(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._active_count(db):
                raise ValueError('Finish or cancel active investigations before clearing local data.')
            jobs = db.execute('SELECT count(*) FROM jobs').fetchone()[0]
            events = db.execute('SELECT count(*) FROM events').fetchone()[0]
            db.execute('DELETE FROM events')
            db.execute('DELETE FROM jobs')
        try:
            with self.connect() as db:
                db.execute('VACUUM')
                db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except sqlite3.OperationalError:
            pass
        return {'investigations': jobs, 'events': events}
