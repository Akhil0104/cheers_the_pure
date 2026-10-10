-- PostgreSQL / Supabase
CREATE TABLE IF NOT EXISTS created_websites (
    id UUID PRIMARY KEY,
    prompt TEXT NOT NULL,
    brand_name VARCHAR(255) NOT NULL,
    theme VARCHAR(32) NOT NULL,
    schema_json JSONB NOT NULL CHECK (jsonb_typeof(schema_json) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- SQLite (3.38+ for built-in JSON validation)
CREATE TABLE IF NOT EXISTS created_websites (
    id TEXT PRIMARY KEY CHECK (length(id) = 36),
    prompt TEXT NOT NULL,
    brand_name VARCHAR(255) NOT NULL,
    theme VARCHAR(32) NOT NULL,
    schema_json TEXT NOT NULL CHECK (
        json_valid(schema_json) AND json_type(schema_json) = 'object'
    ),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);