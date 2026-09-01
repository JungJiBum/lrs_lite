CREATE TABLE profile_documents (
    resource_type TEXT NOT NULL
        CHECK (resource_type IN ('agent', 'activity')),
    owner_key TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    content BYTEA NOT NULL,
    content_type TEXT NOT NULL,
    etag CHAR(40) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (resource_type, owner_key, profile_id),
    CHECK (owner_key <> ''),
    CHECK (profile_id <> ''),
    CHECK (content_type <> '')
);

CREATE INDEX idx_profile_documents_owner_updated
    ON profile_documents (resource_type, owner_key, updated_at);
