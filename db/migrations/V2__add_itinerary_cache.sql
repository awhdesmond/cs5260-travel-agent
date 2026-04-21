-- V2__add_itinerary_cache.sql
-- Adds itinerary cache table with pg_trgm similarity matching

-- Enable pg_trgm extension for fuzzy destination matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Cache table: stores full itinerary JSON blob + key fields for matching
CREATE TABLE IF NOT EXISTS itinerary_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    destination     TEXT NOT NULL,
    preferences     JSONB NOT NULL DEFAULT '[]'::jsonb,
    itinerary       JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '1 year')
);

-- GiST index for pg_trgm destination similarity (supports % operator and ORDER BY similarity())
CREATE INDEX IF NOT EXISTS idx_cache_dest_trgm
    ON itinerary_cache USING GIST (destination gist_trgm_ops);

-- Index on expires_at for TTL filter queries
CREATE INDEX IF NOT EXISTS idx_cache_expires
    ON itinerary_cache(expires_at);
