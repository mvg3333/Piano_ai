import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from .config import DATA, initialize

@contextmanager
def db():
    initialize()
    conn = sqlite3.connect(DATA / 'piano.sqlite3', timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def setup():
    with db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pieces(id TEXT PRIMARY KEY, title TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY, piece_id TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, source_id TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
          payload TEXT NOT NULL, error TEXT, piece_id TEXT, cancel INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL,
          updated REAL NOT NULL, heartbeat REAL);
        CREATE TABLE IF NOT EXISTS pending_piece_deletions(id TEXT PRIMARY KEY);
        PRAGMA user_version=2;
        ''')

def uid():
    return uuid.uuid4().hex

def source_get(source_id):
    with db() as conn:
        row = conn.execute('SELECT payload FROM sources WHERE id=?', (source_id,)).fetchone()
    return json.loads(row[0]) if row else None

def source_save(source):
    with db() as conn:
        conn.execute('INSERT OR REPLACE INTO sources VALUES (?,?)', (source['id'], json.dumps(source)))

def piece_get(piece_id):
    with db() as conn:
        row = conn.execute('SELECT payload FROM pieces WHERE id=?', (piece_id,)).fetchone()
    return json.loads(row[0]) if row else None

def piece_save(piece):
    with db() as conn:
        conn.execute('INSERT INTO pieces VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,payload=excluded.payload',
                     (piece['id'], piece['title'], json.dumps(piece), time.time()))

def job_get(job_id):
    with db() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    if not row:
        return None
    job = dict(row)
    job['request'] = json.loads(job.pop('payload'))
    return job

def job_stage(job_id, stage):
    with db() as conn:
        conn.execute('UPDATE jobs SET stage=?, updated=? WHERE id=?', (stage, time.time(), job_id))
