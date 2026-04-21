-- V1__initial_schema.sql

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Itineraries: one row per generated itinerary
CREATE TABLE IF NOT EXISTS itineraries (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES users(id) ON DELETE CASCADE,
    destination   TEXT NOT NULL,
    travel_dates  JSONB,
    architecture  TEXT NOT NULL,
    itinerary     JSONB,
    status        TEXT NOT NULL DEFAULT 'pending_approval',
    booking_confirmation_id TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Runs: per-request performance metrics
CREATE TABLE IF NOT EXISTS runs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID REFERENCES users(id) ON DELETE SET NULL,
    architecture       TEXT NOT NULL,
    booking_mode       TEXT NOT NULL,
    latency_ms         INTEGER,
    total_tokens       INTEGER,
    estimated_cost_sgd NUMERIC(10, 4),
    llm_call_count     INTEGER,
    conflicts_detected INTEGER DEFAULT 0,
    destination        TEXT,
    travel_dates       JSONB,
    cache_hit          BOOLEAN NOT NULL DEFAULT FALSE,
    retry_count.       INTEGER DEFAULT 0,
    success.           BOOLEAN DEFAULT FALSE,
    traveler_count.    INTEGER,
    trip_days.         INTEGER,
    num_cities.        INTEGER,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_itineraries_user_id ON itineraries(user_id);
CREATE INDEX IF NOT EXISTS idx_runs_user_id ON runs(user_id);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC);


INSERT INTO users (id, email, password_hash)
VALUES (
    '00000000-0000-4000-a000-000000000001',
    'admin@cs5260.nus.edu.sg',
    '$2b$12$Q5rqAFAi9/lrYkuniNI5a.p9SjgIH.c84ZCaJxEVL/SfR0FJ8ZaQe'
)
ON CONFLICT (email) DO NOTHING;
