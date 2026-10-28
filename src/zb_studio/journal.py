"""Durable local operation journal; not a multi-computer coordinator."""
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4
from .config import path

def connection():
    db=sqlite3.connect(path().with_name('operations.sqlite3'))
    db.execute('CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, kind TEXT, state TEXT, payload TEXT, updated TEXT)')
    return db

def record(kind,state,payload,operation_id=None):
    operation_id=operation_id or uuid4().hex
    with connection() as db:
        db.execute('INSERT OR REPLACE INTO operations VALUES (?,?,?,?,?)',(operation_id,kind,state,json.dumps(payload,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
    return operation_id

def list_operations(limit=300):
    location=path().with_name('operations.sqlite3')
    if not location.exists():return []
    with sqlite3.connect(location.as_uri()+'?mode=ro',uri=True) as db:
        query='SELECT id,kind,state,payload,updated FROM operations ORDER BY updated DESC'
        rows=db.execute(query+' LIMIT ?', (limit,)).fetchall() if limit is not None else db.execute(query).fetchall()
    return [{'id':r[0],'kind':r[1],'state':r[2],'payload':json.loads(r[3]),'updated':r[4]} for r in rows]

def append_activity(message):
    from logging.handlers import RotatingFileHandler
    import logging
    handler=RotatingFileHandler(path().with_name('activity.log'),maxBytes=2*1024*1024,backupCount=2,encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s  %(message)s'))
    try:handler.emit(logging.LogRecord('activity',logging.INFO,'',0,message,(),None))
    finally:handler.close()

def read_activity():
    location=path().with_name('activity.log')
    if not location.exists():return ''
    with location.open('rb') as f:
        f.seek(max(0,location.stat().st_size-256*1024))
        return f.read().decode('utf-8',errors='replace')
