-- Describe the proposed additive D29 memory schema; not an applied migration or runtime bootstrap.
-- D30 must review backup/restore, explicit grants, source checks, indexes and startup compatibility first.

CREATE TABLE assistant.memory_settings (
    owner_id uuid PRIMARY KEY,
    revision bigint NOT NULL CHECK (revision > 0),
    enabled boolean NOT NULL DEFAULT false,
    extraction_enabled boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL,
    CHECK (NOT extraction_enabled OR enabled)
);

CREATE TABLE assistant.memory_consents (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES assistant.memory_settings(owner_id),
    kind text NOT NULL CHECK (kind IN ('session','episodic','preference','project')),
    scope_id uuid NOT NULL,
    settings_revision bigint NOT NULL CHECK (settings_revision > 0),
    policy_version integer NOT NULL DEFAULT 1 CHECK (policy_version = 1),
    allow_extraction boolean NOT NULL DEFAULT false,
    granted_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    UNIQUE (id, owner_id, kind, scope_id),
    CHECK (kind NOT IN ('episodic','preference') OR scope_id = owner_id),
    CHECK (expires_at > granted_at AND EXTRACT(EPOCH FROM expires_at - granted_at)
        <= CASE WHEN kind = 'session' THEN 86400 ELSE 31536000 END),
    CHECK (revoked_at IS NULL OR revoked_at >= granted_at)
);

CREATE TABLE assistant.memories (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('session','episodic','preference','project')),
    scope_id uuid NOT NULL,
    consent_id uuid NOT NULL,
    text text NOT NULL CHECK (octet_length(text) BETWEEN 1 AND 4096 AND text ~ '[^[:space:]]'),
    method text NOT NULL CHECK (method IN ('manual','extracted')),
    model_id text CHECK (octet_length(model_id) BETWEEN 1 AND 256),
    provenance jsonb NOT NULL CHECK (jsonb_typeof(provenance) = 'object'
        AND octet_length(provenance::text) <= 16384
        AND provenance ? 'kind'
        AND provenance->>'kind' IS NOT NULL
        AND provenance->>'kind' IN ('manual','conversation_message','file_quote')),
    content_trust text NOT NULL DEFAULT 'untrusted' CHECK (content_trust = 'untrusted'),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    FOREIGN KEY (consent_id, owner_id, kind, scope_id)
        REFERENCES assistant.memory_consents(id, owner_id, kind, scope_id),
    CHECK (kind NOT IN ('episodic','preference') OR scope_id = owner_id),
    CHECK (expires_at > created_at AND updated_at >= created_at
        AND EXTRACT(EPOCH FROM expires_at - created_at)
        <= CASE WHEN kind = 'session' THEN 86400 ELSE 31536000 END),
    CHECK ((method = 'manual' AND model_id IS NULL AND provenance->>'kind' = 'manual')
        OR (method = 'extracted' AND model_id IS NOT NULL
            AND provenance->>'kind' IN ('conversation_message','file_quote')))
);

-- These constraints do not authenticate owners, validate source bytes, lock current consent epochs,
-- enforce cross-row expiry ordering or implement purge. D30 service transactions must do those checks.
-- Never apply inherited default privileges as the final runtime grant policy; see ADR-034/V004.
