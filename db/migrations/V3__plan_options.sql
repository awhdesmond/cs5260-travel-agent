-- V3__plan_options.sql

CREATE TABLE IF NOT EXISTS plan_options (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    plan_state      JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '2 hours'
);
CREATE INDEX IF NOT EXISTS idx_plan_options_expires ON plan_options(expires_at);
