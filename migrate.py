"""Versioned, atomic SQLite SQL migrations; no dependency on external services."""
from hashlib import sha256
from pathlib import Path
import sqlite3
from datetime import datetime
from sqlalchemy import inspect
from models import db


def upgrade():
    if db.engine.dialect.name != 'sqlite':
        raise RuntimeError('These migrations support SQLite, the existing project database.')
    directory = Path(__file__).parent / 'migrations'
    scripts = sorted(directory.glob('[0-9]*.sql'))
    existing = set(inspect(db.engine).get_table_names())
    if 'schema_migrations' not in existing and 'activities' in existing:
        for table in ('skills', 'activities'):
            actual = {c['name'] for c in inspect(db.engine).get_columns(table)}
            columns = db.metadata.tables[table].columns
            expected = {c.name for c in columns}
            # Columns added by later migrations (with defaults) may be absent in a legacy DB.
            missing = expected - actual
            fillable = {c.name for c in columns if c.default is not None or c.server_default is not None}
            if actual - expected or not missing <= fillable:
                raise RuntimeError('Unrecognized legacy schema: ' + table)
    # Back up existing databases before any pending upgrade.
    db_path = db.engine.url.database
    applied_versions = set()
    if 'schema_migrations' in existing:
        with db.engine.connect() as connection:
            applied_versions = set(connection.exec_driver_sql('SELECT version FROM schema_migrations').scalars())
    pending = any(script.stem not in applied_versions for script in scripts)
    if db_path and db_path != ':memory:' and 'activities' in existing and pending:
        path = Path(db_path)
        backup = path.with_name(path.name + '.pre-planning-' + datetime.utcnow().strftime('%Y%m%dT%H%M%S%f') + '.bak')
        with sqlite3.connect(path) as source, sqlite3.connect(backup) as dest:
            source.backup(dest)
    raw = db.engine.raw_connection()
    try:
        connection = raw.driver_connection
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)')
        applied = dict(connection.execute('SELECT version, checksum FROM schema_migrations'))
        for script in scripts:
            sql = script.read_text()
            checksum = sha256(sql.encode()).hexdigest()
            if script.stem in applied:
                if applied[script.stem] != checksum:
                    raise RuntimeError('Applied migration was modified: ' + script.name)
                continue
            for statement in sql.split(';'):
                if statement.strip(): connection.execute(statement)
            connection.execute('INSERT INTO schema_migrations VALUES (?, ?, ?)', (script.stem, checksum, datetime.utcnow().isoformat()))
        connection.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
