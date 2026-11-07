import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = Path(os.environ.get('SPR_RUNTIME', ROOT / 'runtime')).resolve()
DATA_ROOT = Path(os.environ.get('SPR_DATA_ROOT', ROOT.parent.parent / 'платформа данные' / 'ЗАДАНИЕ')).resolve()
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL','http://127.0.0.1:8000').rstrip('/')
TABLES = {'datasets','scripts','configs','runs','check_executions'}

def now():
    return datetime.now(timezone.utc).isoformat()

def uid():
    return secrets.token_hex(12)

@contextmanager
def db():
    RUNTIME.mkdir(parents=True,exist_ok=True)
    c = sqlite3.connect(RUNTIME / 'meta.sqlite',timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA synchronous=NORMAL')
    try:
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()

def password_hash(password,salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),180000).hex()

def init():
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY,name TEXT UNIQUE,salt TEXT,password TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY,owner_id TEXT,created TEXT)')
        for table in TABLES:
            c.execute(f'CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL)')
            c.execute(f'CREATE INDEX IF NOT EXISTS {table}_owner ON {table}(owner_id,status)')
        c.execute('CREATE TABLE IF NOT EXISTS run_events (id INTEGER PRIMARY KEY,run_id TEXT,stage TEXT,time TEXT,message TEXT,processed INTEGER,total INTEGER,snapshot_id TEXT,code_hash TEXT,traceback TEXT)')
        for name in ['alice','bob']:
            if not c.execute('SELECT 1 FROM users WHERE name=?',(name,)).fetchone():
                salt = secrets.token_hex(16)
                c.execute('INSERT INTO users VALUES(?,?,?,?)',(uid(),name,salt,password_hash(os.environ.get('SPR_DEMO_PASSWORD','demo'),salt)))

def put(table,owner,payload,status='SAVED',id=None):
    assert table in TABLES
    id = id or uid()
    created = payload.get('created',now())
    payload = {**payload,'id':id,'owner_id':owner,'status':status,'created':created}
    with db() as c:
        c.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload',
                  (id,owner,status,json.dumps(payload,ensure_ascii=False),created))
    return payload

def get(table,id,owner=None):
    assert table in TABLES
    with db() as c:
        r = c.execute(f'SELECT payload FROM {table} WHERE id=?' + (' AND owner_id=?' if owner else ''), (id,owner) if owner else (id,)).fetchone()
    if r is None:
        raise KeyError(id)
    return json.loads(r[0])

def listing(table,owner,limit=100,offset=0):
    assert table in TABLES
    with db() as c:
        return [json.loads(r[0]) for r in c.execute(f'SELECT payload FROM {table} WHERE owner_id=? ORDER BY created DESC LIMIT ? OFFSET ?',(owner,limit,offset))]

def dataset_listing(owner,limit=100,offset=0):
    """One visible snapshot per checksum, before pagination; older IDs stay readable."""
    with db() as c:
        rows = c.execute('''WITH ranked AS (
            SELECT payload,created,id,row_number() OVER (
                PARTITION BY coalesce(nullif(json_extract(payload,'$.checksum'),''),id)
                ORDER BY created DESC,id DESC) AS position
            FROM datasets WHERE owner_id=?)
            SELECT payload FROM ranked WHERE position=1
            ORDER BY created DESC,id DESC LIMIT ? OFFSET ?''',(owner,limit,offset))
        return [json.loads(r[0]) for r in rows]


def register_dataset(owner,payload,id):
    """Atomically reuse an identical dataset, including simultaneous imports."""
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        previous = c.execute('''SELECT payload FROM datasets
            WHERE owner_id=? AND json_extract(payload,'$.checksum')=?
            ORDER BY created DESC,id DESC LIMIT 1''',(owner,payload['checksum'])).fetchone()
        if previous:
            return json.loads(previous[0])
        created = now()
        dataset = {**payload,'id':id,'owner_id':owner,'status':'VALIDATED','created':created}
        c.execute('INSERT INTO datasets VALUES(?,?,?,?,?)',
                  (id,owner,'VALIDATED',json.dumps(dataset,ensure_ascii=False),created))
        return dataset


def update(table,id,**fields):
    assert table in TABLES
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute(f'SELECT payload FROM {table} WHERE id=?',(id,)).fetchone()
        if row is None:
            raise KeyError(id)
        p = json.loads(row[0])
        p.update(fields)
        c.execute(f'UPDATE {table} SET status=?,payload=? WHERE id=?',(p['status'],json.dumps(p,ensure_ascii=False),id))
        return p

def event(run_id,stage,message,processed=0,total=0,snapshot_id=None,code_hash=None,traceback=None):
    with db() as c:
        c.execute('INSERT INTO run_events(run_id,stage,time,message,processed,total,snapshot_id,code_hash,traceback) VALUES(?,?,?,?,?,?,?,?,?)',
                  (run_id,stage,now(),message,processed,total,snapshot_id,code_hash,traceback))

def claim():
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        for table in ['runs','check_executions']:
            row = c.execute(f"SELECT id,payload FROM {table} WHERE status='QUEUED' ORDER BY created LIMIT 1").fetchone()
            if row:
                payload = json.loads(row['payload'])
                payload.update(status='NORMALIZING' if table=='runs' else 'CHECKS',worker_id=os.getpid(),heartbeat=now())
                c.execute(f'UPDATE {table} SET status=?,payload=? WHERE id=?',(payload['status'],json.dumps(payload),row['id']))
                return table,row['id']
    return None
