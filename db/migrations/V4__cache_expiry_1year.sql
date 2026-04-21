-- Update existing rows that haven't expired yet to the new TTL
UPDATE itinerary_cache
    SET expires_at = created_at + INTERVAL '1 year'
    WHERE expires_at > NOW();
