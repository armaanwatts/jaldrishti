"""Private Postgres storage, preserving the existing community transaction contract."""
from contextlib import contextmanager
import os
import re
import threading

SCHEMA='jaldrishti_private'
LOCK=78240619
_ready=False
_guard=threading.Lock()

class Row(dict):
    def __getitem__(self,key):
        return list(self.values())[key] if isinstance(key,int) else super().__getitem__(key)

class Cursor:
    def __init__(self,cursor):self.cursor=cursor
    def fetchone(self):
        row=self.cursor.fetchone();return None if row is None else Row(row)
    def fetchall(self):return [Row(r) for r in self.cursor.fetchall()]
    def __iter__(self):return iter(self.fetchall())

def translate(sql):
    sql=sql.strip().rstrip(';')
    if sql.upper()=='BEGIN IMMEDIATE':return 'SELECT pg_advisory_xact_lock('+str(LOCK)+')'
    ignore=bool(re.match(r'INSERT OR IGNORE\b',sql,re.I))
    sql=re.sub(r'INSERT OR IGNORE\b','INSERT',sql,flags=re.I)
    sql=sql.replace("json_extract(payload,'$.endpoint')","(payload::jsonb ->> 'endpoint')")
    sql=sql.replace('?','%s')
    if ignore:sql+=' ON CONFLICT DO NOTHING'
    return sql

class Connection:
    def __init__(self,raw):self.raw=raw
    def execute(self,sql,args=()):return Cursor(self.raw.execute(translate(sql),args))

def connect():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(os.environ['DATABASE_URL'],sslmode='require',connect_timeout=10,row_factory=dict_row,prepare_threshold=None)

def initialize():
    global _ready
    if _ready:return
    with _guard:
        if _ready:return
        from community import COMMUNITY_SCHEMA
        schema=COMMUNITY_SCHEMA.replace('INTEGER PRIMARY KEY AUTOINCREMENT','BIGSERIAL PRIMARY KEY')
        schema=re.sub(r'\bREAL\b','DOUBLE PRECISION',schema)
        tables=['profiles','regions','subscriptions','alerts','inbox','outbox','events','settings']
        with connect() as raw:
            raw.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK,))
            raw.execute('CREATE SCHEMA IF NOT EXISTS '+SCHEMA)
            raw.execute('REVOKE ALL ON SCHEMA '+SCHEMA+' FROM PUBLIC')
            raw.execute('SET LOCAL search_path TO '+SCHEMA)
            for statement in schema.split(';'):
                if statement.strip():raw.execute(statement)
            raw.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            for table in tables:
                raw.execute('ALTER TABLE '+table+' ENABLE ROW LEVEL SECURITY')
                raw.execute('REVOKE ALL ON TABLE '+table+' FROM PUBLIC')
            # Supabase frontend roles must never read device tokens or push keys.
            for role in ('anon','authenticated'):
                if raw.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                    raw.execute('REVOKE ALL ON SCHEMA '+SCHEMA+' FROM '+role)
                    for table in tables:raw.execute('REVOKE ALL ON TABLE '+table+' FROM '+role)
        _ready=True

@contextmanager
def database():
    initialize()
    # Serialise short community transactions. Network push delivery runs outside this lock.
    with connect() as raw:
        raw.execute('SET LOCAL search_path TO '+SCHEMA)
        raw.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK,))
        yield Connection(raw)

def get_setting(key):
    with database() as c:
        row=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row['value'] if row else None

def put_setting_once(key,value):
    with database() as c:
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(key,value))
        return c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()['value']
