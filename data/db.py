# data/db.py
import os
import psycopg2
from psycopg2.pool import SimpleConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL missing. Attach a PostgreSQL plugin in Railway."
    )

# Railway sometimes gives postgres:// but psycopg2 expects postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

pool = SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    dsn=DATABASE_URL
)

def get_conn():
    return pool.getconn()

def release_conn(conn):
    pool.putconn(conn)


def init_db():
    conn = get_conn()
    cur = conn.cursor()

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

    # MEMBERSHIP (user ↔ team)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS memberships (
        id SERIAL PRIMARY KEY,
        user_id UUID REFERENCES users(user_id),
        team_code CHAR(6) REFERENCES teams(team_code),
        role TEXT NOT NULL,
        display_name TEXT,
        bio TEXT DEFAULT '',
        profile_pic_url TEXT DEFAULT '',
        subteam TEXT DEFAULT '',
        joined_at TIMESTAMP DEFAULT NOW(),
        is_active BOOLEAN DEFAULT TRUE,
        UNIQUE(user_id)
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

    conn.commit()
    cur.close()
    release_conn(conn)
