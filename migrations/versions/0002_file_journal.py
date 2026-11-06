"""Add owner-scoped file journals and atomic allocation counters without modifying V001."""

import logging

from alembic import op
from sqlalchemy import text

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None
logger = logging.getLogger(__name__)

FILE_DDL = """
CREATE TABLE assistant.file_global_usage (
    singleton integer PRIMARY KEY CHECK (singleton = 1),
    allocated_bytes bigint NOT NULL DEFAULT 0,
    allocated_files bigint NOT NULL DEFAULT 0,
    active_uploads bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (allocated_files >= 0 AND active_uploads >= 0
        AND active_uploads <= allocated_files AND allocated_bytes >= allocated_files
        AND (allocated_files > 0 OR allocated_bytes = 0))
);
INSERT INTO assistant.file_global_usage (singleton) VALUES (1);
CREATE TABLE assistant.file_owner_usage (
    owner_id uuid PRIMARY KEY,
    allocated_bytes bigint NOT NULL DEFAULT 0,
    allocated_files bigint NOT NULL DEFAULT 0,
    active_uploads bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (allocated_files >= 0 AND active_uploads >= 0
        AND active_uploads <= allocated_files AND allocated_bytes >= allocated_files
        AND (allocated_files > 0 OR allocated_bytes = 0))
);
CREATE TABLE assistant.files (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES assistant.file_owner_usage(owner_id),
    display_name text NOT NULL CHECK (octet_length(display_name) BETWEEN 1 AND 255),
    declared_size_bytes bigint NOT NULL CHECK (declared_size_bytes > 0),
    expected_sha256 char(64) NOT NULL CHECK (expected_sha256 ~ '^[0-9a-f]{64}$'),
    actual_size_bytes bigint,
    actual_sha256 char(64) CHECK (actual_sha256 ~ '^[0-9a-f]{64}$'),
    detected_media_type text,
    state text NOT NULL DEFAULT 'reserved' CHECK (state IN
        ('reserved','receiving','verifying','ready','purging','deleted','rejected','interrupted')),
    request_key varchar(128) CHECK (request_key IS NULL OR length(request_key) > 0),
    request_fingerprint char(64) NOT NULL CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    storage_backend text NOT NULL DEFAULT 'local_fs' CHECK (storage_backend = 'local_fs'),
    storage_key text NOT NULL UNIQUE,
    policy_version integer NOT NULL DEFAULT 1 CHECK (policy_version = 1),
    policy_snapshot jsonb NOT NULL CHECK (jsonb_typeof(policy_snapshot) = 'object'),
    verification_version integer,
    source_kind text NOT NULL DEFAULT 'local_upload' CHECK (source_kind = 'local_upload'),
    uploaded_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    verified_at timestamptz,
    reservation_expires_at timestamptz NOT NULL,
    lease_owner uuid,
    lease_expires_at timestamptz,
    claimed_at timestamptz,
    stream_deadline_at timestamptz,
    bytes_received bigint NOT NULL DEFAULT 0,
    upload_slot_released_at timestamptz,
    quota_released_at timestamptz,
    purge_token uuid,
    purge_target text CHECK (purge_target IN ('deleted','rejected','interrupted')),
    error_code varchar(64),
    deleted_at timestamptz,
    UNIQUE (id, owner_id),
    UNIQUE (owner_id, request_key),
    CHECK (uploaded_by = owner_id),
    CHECK (storage_key = 'objects/' || owner_id::text || '/' ||
        substring(replace(id::text, '-', ''), 1, 2) || '/' || id::text || '.blob'),
    CHECK (bytes_received BETWEEN 0 AND declared_size_bytes),
    CHECK (actual_size_bytes IS NULL OR actual_size_bytes BETWEEN 0 AND declared_size_bytes),
    CHECK (quota_released_at IS NULL OR upload_slot_released_at IS NOT NULL),
    CHECK (state NOT IN ('receiving','verifying') OR
        (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL
         AND claimed_at IS NOT NULL AND stream_deadline_at IS NOT NULL
         AND lease_expires_at <= stream_deadline_at)),
    CHECK (state <> 'ready' OR
        (actual_size_bytes IS NOT NULL AND actual_size_bytes = declared_size_bytes
         AND actual_sha256 IS NOT NULL AND actual_sha256 = expected_sha256
         AND bytes_received = declared_size_bytes AND detected_media_type IS NOT NULL
         AND verification_version IS NOT NULL AND verified_at IS NOT NULL
         AND upload_slot_released_at IS NOT NULL AND quota_released_at IS NULL
         AND deleted_at IS NULL)),
    CHECK (state <> 'purging' OR (purge_token IS NOT NULL AND purge_target IS NOT NULL)),
    CHECK ((state IN ('deleted','rejected','interrupted')) = (quota_released_at IS NOT NULL)),
    CHECK (state <> 'deleted' OR deleted_at IS NOT NULL),
    CHECK (deleted_at IS NULL OR state IN ('purging','deleted'))
);
CREATE INDEX ix_files_owner_created ON assistant.files(owner_id, created_at DESC, id DESC);
CREATE INDEX ix_files_recovery ON assistant.files(state, lease_expires_at, reservation_expires_at);
GRANT SELECT, INSERT, UPDATE, DELETE ON assistant.files,
    assistant.file_owner_usage, assistant.file_global_usage TO local_assistant_app;
REVOKE TRUNCATE, REFERENCES, TRIGGER ON assistant.files,
    assistant.file_owner_usage, assistant.file_global_usage FROM local_assistant_app;
"""


def upgrade() -> None:
    """Create additive tables, constraints/indexes and explicit bounded runtime grants."""
    op.execute(text("SET LOCAL lock_timeout='5s'"))
    op.execute(text("SET LOCAL statement_timeout='30s'"))
    op.execute(text(FILE_DDL))
    logger.info("file_journal_schema_upgraded revision=0002")


def downgrade() -> None:
    """Refuse destructive rollback when any file journal or allocation still exists."""
    op.execute(
        text("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM assistant.files)
             OR EXISTS (SELECT 1 FROM assistant.file_owner_usage WHERE allocated_files <> 0
                 OR allocated_bytes <> 0 OR active_uploads <> 0)
             OR EXISTS (SELECT 1 FROM assistant.file_global_usage WHERE allocated_files <> 0
                 OR allocated_bytes <> 0 OR active_uploads <> 0) THEN
            RAISE EXCEPTION 'File journal must be empty before reviewed downgrade';
          END IF;
        END $$;
        DROP TABLE assistant.files;
        DROP TABLE assistant.file_owner_usage;
        DROP TABLE assistant.file_global_usage;
    """)
    )
    logger.info("file_journal_schema_downgraded revision=0001")
