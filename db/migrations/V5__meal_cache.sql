-- V5__meal_cache.sql

CREATE TABLE IF NOT EXISTS meal_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city            TEXT NOT NULL,
    day_number      INTEGER NOT NULL,
    meal_type       TEXT NOT NULL CHECK (meal_type IN ('lunch', 'dinner')),
    meal_option     JSONB NOT NULL,          -- single MealOption dict
    lat             DOUBLE PRECISION,        -- restaurant lat (from Places API)
    lng             DOUBLE PRECISION,        -- restaurant lng (from Places API)
    meal_preferences TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '1 year')
);

-- GiST index for pg_trgm city similarity matching
CREATE INDEX IF NOT EXISTS idx_meal_cache_city_trgm
    ON meal_cache USING GIST (city gist_trgm_ops);

-- B-Tree for meal_type + day_number filtering
CREATE INDEX IF NOT EXISTS idx_meal_cache_lookup
    ON meal_cache(city, meal_type);

-- Expiry filter
CREATE INDEX IF NOT EXISTS idx_meal_cache_expires
    ON meal_cache(expires_at);
