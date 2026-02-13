-- ========== USERS ==========

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    last_seen TIMESTAMP DEFAULT NOW()
);

-- ========== TEAMS ==========

CREATE TABLE IF NOT EXISTS teams (
    team_code CHAR(6) PRIMARY KEY,
    name TEXT NOT NULL,
    team_number TEXT,
    description TEXT,
    created_by TEXT REFERENCES users(user_id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ========== MEMBERSHIPS ==========

CREATE TABLE IF NOT EXISTS memberships (
    user_id TEXT REFERENCES users(user_id),
    team_code CHAR(6) REFERENCES teams(team_code) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'scout',
    display_name TEXT,
    bio TEXT,
    profile_pic_url TEXT,
    subteam TEXT,
    joined_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (user_id)
);

-- ========== MATCH REPORTS ==========

CREATE TABLE IF NOT EXISTS match_reports (
    id SERIAL PRIMARY KEY,
    submitted_by TEXT REFERENCES users(user_id),
    event_code TEXT NOT NULL,
    team_number TEXT NOT NULL,
    match_number INTEGER NOT NULL,
    data JSONB NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- ========== PIT REPORTS ==========

CREATE TABLE IF NOT EXISTS pit_reports (
    id SERIAL PRIMARY KEY,
    submitted_by TEXT REFERENCES users(user_id),
    event_code TEXT NOT NULL,
    team_number TEXT NOT NULL,
    data JSONB NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- helpful indexes (IMPORTANT for events with thousands of matches)

CREATE INDEX IF NOT EXISTS idx_match_reports_event_team
ON match_reports (event_code, team_number);

CREATE INDEX IF NOT EXISTS idx_pit_reports_event_team
ON pit_reports (event_code, team_number);

CREATE INDEX IF NOT EXISTS idx_memberships_team
ON memberships (team_code);
