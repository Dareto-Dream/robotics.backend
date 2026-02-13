-- ========== USERS ==========

CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY,
    username TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    last_seen TIMESTAMP DEFAULT NOW()
);

-- ========== TEAMS ==========

CREATE TABLE IF NOT EXISTS teams (
    team_code CHAR(6) PRIMARY KEY,
    name TEXT NOT NULL,
    team_number TEXT,
    description TEXT DEFAULT '',
    created_by UUID REFERENCES users(user_id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ========== MEMBERSHIPS ==========
-- is_active is COSMETIC ONLY: indicates if user is currently on the app.
-- Membership is determined by row existence. Leaving = row deleted.

CREATE TABLE IF NOT EXISTS memberships (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(user_id),
    team_code CHAR(6) REFERENCES teams(team_code) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'scout',
    display_name TEXT,
    bio TEXT DEFAULT '',
    profile_pic_url TEXT DEFAULT '',
    subteam TEXT DEFAULT '',
    joined_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT FALSE,
    UNIQUE(user_id)
);

-- ========== DEVICES (OAC / Offline Auth) ==========

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

-- ========== MATCH REPORTS ==========

CREATE TABLE IF NOT EXISTS match_reports (
    id SERIAL PRIMARY KEY,
    submitted_by UUID REFERENCES users(user_id),
    event_code TEXT NOT NULL,
    team_number TEXT NOT NULL,
    match_number INTEGER NOT NULL,
    data JSONB NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- ========== PIT REPORTS ==========

CREATE TABLE IF NOT EXISTS pit_reports (
    id SERIAL PRIMARY KEY,
    submitted_by UUID REFERENCES users(user_id),
    event_code TEXT NOT NULL,
    team_number TEXT NOT NULL,
    data JSONB NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- ========== INDEXES ==========

CREATE INDEX IF NOT EXISTS idx_match_reports_event_team
ON match_reports (event_code, team_number);

CREATE INDEX IF NOT EXISTS idx_pit_reports_event_team
ON pit_reports (event_code, team_number);

CREATE INDEX IF NOT EXISTS idx_memberships_team
ON memberships (team_code);

CREATE INDEX IF NOT EXISTS idx_devices_user
ON devices (user_id);
