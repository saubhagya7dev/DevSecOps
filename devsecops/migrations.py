"""Versioned SQLite layout; upgrades are transactional and retain a pre-upgrade backup."""
import json
import sqlite3
from contextlib import closing

SCHEMA_VERSION = 1


def migrate(db, path):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ValueError('Local database was created by a newer DevSecOps version.')
    legacy = version == 0 and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()
    if legacy:
        backup = path.with_name(path.name + '.v0.bak')
        if not backup.exists():
            with closing(sqlite3.connect(str(backup))) as target:
                db.backup(target)
    db.execute('BEGIN IMMEDIATE')
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    db.execute("ALTER TABLE jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'")
    db.execute('CREATE INDEX jobs_status ON jobs(status)')
    db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, data TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS events_job ON events(job_id, seq)')
    db.execute('CREATE TABLE artifacts (job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, key TEXT NOT NULL, schema_version INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(job_id,key))')
    db.execute('CREATE TABLE reports (job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE, content TEXT NOT NULL)')
    rows = db.execute('SELECT id,data FROM jobs').fetchall()
    for job_id, raw in rows:
        job = json.loads(raw)
        for key, value in job.pop('artifacts', {}).items():
            db.execute('INSERT INTO artifacts VALUES (?,?,?,?)', (job_id, key, 1, json.dumps(value)))
        report = job.pop('report', '')
        if report:
            db.execute('INSERT INTO reports VALUES (?,?)', (job_id, report))
        job.update(revision=1, payload_revision=1)
        db.execute('UPDATE jobs SET data=?,status=? WHERE id=?', (json.dumps(job), job['status'], job_id))
    db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
