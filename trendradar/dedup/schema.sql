CREATE TABLE IF NOT EXISTS sent_notification_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    platform_id TEXT NOT NULL,
    platform_name TEXT DEFAULT '',
    region_type TEXT NOT NULL,
    match_policy TEXT NOT NULL,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    url TEXT DEFAULT '',
    normalized_url TEXT DEFAULT '',
    fact_signature_json TEXT DEFAULT '{}',
    embedding_blob BLOB,
    sent_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dedup_expires_at
    ON sent_notification_records(expires_at);

CREATE INDEX IF NOT EXISTS idx_dedup_source_region
    ON sent_notification_records(source_type, platform_id, region_type);

CREATE INDEX IF NOT EXISTS idx_dedup_normalized_url
    ON sent_notification_records(normalized_url);

CREATE INDEX IF NOT EXISTS idx_dedup_normalized_title
    ON sent_notification_records(normalized_title);

CREATE INDEX IF NOT EXISTS idx_dedup_sent_at
    ON sent_notification_records(sent_at);
