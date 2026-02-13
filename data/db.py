# data/db.py
import os
import time
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import psycopg2
from psycopg2.pool import SimpleConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing. Link Railway PostgreSQL plugin.")

def _normalize_postgres_url(raw_url: str) -> str:
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)

    parsed = urlparse(raw_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    sslmode = os.environ.get("PGSSLMODE")
    if sslmode:
        query.setdefault("sslmode", sslmode)
    else:
        is_local = parsed.hostname in {"localhost", "127.0.0.1"} if parsed.hostname else False
        if not is_local:
            query.setdefault("sslmode", "require")

    connect_timeout = os.environ.get("PGCONNECT_TIMEOUT")
    if connect_timeout:
        query.setdefault("connect_timeout", connect_timeout)
    else:
        query.setdefault("connect_timeout", "10")

    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


DATABASE_URL = _normalize_postgres_url(DATABASE_URL)

_pool = None


def _create_pool():
    return SimpleConnectionPool(
        minconn=1,
        maxconn=3,
        dsn=DATABASE_URL,
    )


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool

    last_exc = None
    for _ in range(5):
        try:
            _pool = _create_pool()
            return _pool
        except Exception as exc:
            last_exc = exc
            time.sleep(2)

    raise last_exc

def get_conn():
    conn = _get_pool().getconn()
    conn.autocommit = True
    return conn

def release_conn(conn):
    _get_pool().putconn(conn)


def init_db():
    """
    Safe DB initialization.
    Uses PostgreSQL advisory lock so only ONE gunicorn worker
    performs schema creation.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT pg_advisory_lock(987654321);")

    try:
        # USERS
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id UUID PRIMARY KEY,
            username TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            last_seen TIMESTAMP DEFAULT NOW()
        );
        """)

        # TEAMS
        cur.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            team_code CHAR(6) PRIMARY KEY,
            name TEXT NOT NULL,
            team_number TEXT,
            description TEXT DEFAULT '',
            created_by UUID REFERENCES users(user_id),
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # MEMBERSHIPS
        # is_active is COSMETIC ONLY — shows whether user is currently on the app.
        # Team membership is determined by row existence.
        cur.execute("""
        CREATE TABLE IF NOT EXISTS memberships (
            id SERIAL PRIMARY KEY,
            user_id UUID REFERENCES users(user_id),
            team_code CHAR(6) REFERENCES teams(team_code) ON DELETE CASCADE,
            role TEXT NOT NULL,
            display_name TEXT,
            bio TEXT DEFAULT '',
            profile_pic_url TEXT DEFAULT '',
            subteam TEXT DEFAULT '',
            joined_at TIMESTAMP DEFAULT NOW(),
            is_active BOOLEAN DEFAULT FALSE,
            UNIQUE(user_id)
        );
        """)

        # DEVICES (for OAC / offline auth)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(user_id),
            device_name TEXT NOT NULL,
            device_type TEXT NOT NULL,
            device_public_key_hash TEXT NOT NULL,
            app_version TEXT DEFAULT '',
            is_revoked BOOLEAN DEFAULT FALSE,
            registered_at TIMESTAMP DEFAULT NOW(),
            last_renewed TIMESTAMP DEFAULT NOW()
        );
        """)

        # MATCH REPORTS
        cur.execute("""
        CREATE TABLE IF NOT EXISTS match_reports (
            id SERIAL PRIMARY KEY,
            submitted_by UUID REFERENCES users(user_id),
            event_code TEXT,
            team_number TEXT,
            match_number INTEGER,
            data JSONB,
            timestamp TIMESTAMP DEFAULT NOW()
        );
        """)

        # PIT REPORTS
        cur.execute("""
        CREATE TABLE IF NOT EXISTS pit_reports (
            id SERIAL PRIMARY KEY,
            submitted_by UUID REFERENCES users(user_id),
            event_code TEXT,
            team_number TEXT,
            data JSONB,
            timestamp TIMESTAMP DEFAULT NOW()
        );
        """)

        # INDEXES
        cur.execute("CREATE INDEX IF NOT EXISTS idx_match_reports_event_team ON match_reports (event_code, team_number);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pit_reports_event_team ON pit_reports (event_code, team_number);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memberships_team ON memberships (team_code);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_user ON devices (user_id);")

        conn.commit()

    finally:
        cur.execute("SELECT pg_advisory_unlock(987654321);")
        cur.close()
        release_conn(conn)
