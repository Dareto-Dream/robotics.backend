-- migrations/auth_schema.sql
--
-- Run this manually against AUTH_DATABASE_URL if you prefer explicit
-- migrations over the auto-init in data/auth_db.py.
-- The application's init_auth_db() is idempotent and will also apply
-- this schema on first boot, so running this script is optional.

CREATE TABLE IF NOT EXISTS auth_users (
    id            UUID        PRIMARY KEY,
    email         TEXT        UNIQUE NOT NULL,
    password_hash TEXT        NOT NULL,
    created_at    TIMESTAMP   DEFAULT NOW()
);

-- Index on email for fast login lookups
CREATE INDEX IF NOT EXISTS idx_auth_users_email ON auth_users (email);
