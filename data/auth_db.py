# data/auth_db.py
#
# Separate PostgreSQL connection pool exclusively for user authentication.
# Uses AUTH_DATABASE_URL — completely isolated from the main DATABASE_URL.

import os
import time
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import psycopg2
from psycopg2.pool import SimpleConnectionPool

AUTH_DATABASE_URL = os.environ.get("AUTH_DATABASE_URL")

if not AUTH_DATABASE_URL:
    raise RuntimeError("AUTH_DATABASE_URL missing. Link a separate PostgreSQL instance for auth.")

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


AUTH_DATABASE_URL = _normalize_postgres_url(AUTH_DATABASE_URL)

_auth_pool = None


def _create_auth_pool():
    return SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=AUTH_DATABASE_URL,
    )


def _get_auth_pool():
    global _auth_pool
    if _auth_pool is not None:
        return _auth_pool

    last_exc = None
    for _ in range(5):
        try:
            _auth_pool = _create_auth_pool()
            return _auth_pool
        except Exception as exc:
            last_exc = exc
            time.sleep(2)

    raise last_exc


def get_auth_conn():
    conn = _get_auth_pool().getconn()
    conn.autocommit = True
    return conn


def release_auth_conn(conn):
    _get_auth_pool().putconn(conn)


def init_auth_db():
    """
    Creates the auth schema if it doesn't exist.
    Uses a PostgreSQL advisory lock (different constant from main DB)
    so only one gunicorn worker performs the migration.
    """
    conn = get_auth_conn()
    cur = conn.cursor()

    cur.execute("SELECT pg_advisory_lock(111222333);")

    try:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS auth_users (
            id          UUID PRIMARY KEY,
            email       TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT NOW()
        );
        """)

        conn.commit()
        print("[auth_db] Schema ready.")

    finally:
        cur.execute("SELECT pg_advisory_unlock(111222333);")
        cur.close()
        release_auth_conn(conn)
