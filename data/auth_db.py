# data/auth_db.py
#
# Separate PostgreSQL connection pool exclusively for user authentication.
# Uses AUTH_DATABASE_URL — completely isolated from the main DATABASE_URL.

import os
import psycopg2
from psycopg2.pool import SimpleConnectionPool

AUTH_DATABASE_URL = os.environ.get("AUTH_DATABASE_URL")

if not AUTH_DATABASE_URL:
    raise RuntimeError("AUTH_DATABASE_URL missing. Link a separate PostgreSQL instance for auth.")

if AUTH_DATABASE_URL.startswith("postgres://"):
    AUTH_DATABASE_URL = AUTH_DATABASE_URL.replace("postgres://", "postgresql://", 1)

auth_pool = SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    dsn=AUTH_DATABASE_URL
)


def get_auth_conn():
    conn = auth_pool.getconn()
    conn.autocommit = True
    return conn


def release_auth_conn(conn):
    auth_pool.putconn(conn)


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
