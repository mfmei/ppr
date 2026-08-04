-- Parks & Rec Finder schema
-- All ages stored in months to avoid unit-mismatch bugs (some youth
-- programs use age bands finer than whole years).
-- All times are local (Portland) — no timezone handling needed.

CREATE TABLE IF NOT EXISTS facilities (
    facility_id     TEXT PRIMARY KEY,   -- ID as given by ActiveNet, not invented
    name            TEXT NOT NULL,
    address         TEXT,               -- raw address string from source
    lat             REAL,               -- nullable; populated later for distance sort
    lon             REAL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id          TEXT PRIMARY KEY,  -- ID as given by ActiveNet
    activity_name       TEXT NOT NULL,
    category            TEXT,
    facility_id         TEXT NOT NULL REFERENCES facilities(facility_id),

    min_age_months      INTEGER,
    max_age_months      INTEGER,

    days_of_week        TEXT,   -- JSON array, e.g. '["Mon","Wed"]'
    start_time          TEXT,   -- 24hr "HH:MM"
    end_time            TEXT,   -- 24hr "HH:MM"

    session_start_date  TEXT,   -- ISO date "YYYY-MM-DD"
    session_end_date    TEXT,

    status              TEXT NOT NULL,  -- 'open' | 'full' | 'closed'
    spots_available     INTEGER,        -- nullable, if source provides it
    price               REAL,

    registration_url    TEXT,
    last_scraped_at     TEXT NOT NULL   -- ISO datetime
);

CREATE INDEX IF NOT EXISTS idx_sessions_age
    ON sessions (min_age_months, max_age_months);

CREATE INDEX IF NOT EXISTS idx_sessions_status_date
    ON sessions (status, session_start_date);

CREATE INDEX IF NOT EXISTS idx_sessions_facility
    ON sessions (facility_id);
