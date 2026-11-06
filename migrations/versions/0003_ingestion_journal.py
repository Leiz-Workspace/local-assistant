"""Add immutable private ingestion jobs and scoped generation pointers without altering accepted source tables."""

import logging

from alembic import op
from sqlalchemy import text

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None
logger = logging.getLogger(__name__)

INGESTION_DDL = """
CREATE TABLE assistant.ingestion_jobs (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL,
    namespace_id uuid NOT NULL,
    file_id uuid NOT NULL,
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    model_fingerprint text NOT NULL CHECK (model_fingerprint ~ '^[0-9a-f]{64}$'),
    collection_name text NOT NULL CHECK (collection_name = 'la_chunks_' || model_fingerprint || '_v1'),
    generation text NOT NULL CHECK (generation ~ '^[0-9a-f]{64}$'),
    manifest_json text NOT NULL CHECK (octet_length(manifest_json) BETWEEN 2 AND 16384
        AND jsonb_typeof(manifest_json::jsonb) = 'object'),
    plan_sha256 text NOT NULL CHECK (plan_sha256 ~ '^[0-9a-f]{64}$'),
    point_ids uuid[] NOT NULL,
    token_counts integer[] NOT NULL,
    admission_revision bigint NOT NULL CHECK (admission_revision > 0),
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','running','ready','failed','stale','tombstone')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
    lease_token uuid,
    lease_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    deadline_at timestamptz NOT NULL DEFAULT clock_timestamp() + interval '1 hour',
    next_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    published_at timestamptz,
    cleanup_done_at timestamptz,
    error_code text CHECK (error_code IN ('source_changed','superseded','source_deleted','attempts_exhausted','deadline_exceeded','worker_failed')),
    FOREIGN KEY (file_id, owner_id) REFERENCES assistant.files(id, owner_id),
    UNIQUE (id, owner_id, namespace_id, file_id, model_fingerprint),
    UNIQUE (owner_id, namespace_id, file_id, model_fingerprint, generation),
    CHECK (cardinality(point_ids) BETWEEN 0 AND 1000 AND cardinality(point_ids) = cardinality(token_counts)),
    CHECK (array_position(point_ids, NULL) IS NULL AND array_position(token_counts, NULL) IS NULL
        AND 1 <= ALL(token_counts) AND 512 >= ALL(token_counts)),
    CHECK ((state = 'running') = (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)),
    CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)),
    CHECK (lease_expires_at IS NULL OR (attempts > 0 AND lease_expires_at <= deadline_at)),
    CHECK (deadline_at > created_at),
    CHECK (state <> 'ready' OR published_at IS NOT NULL),
    CHECK (cleanup_done_at IS NULL OR state IN ('failed','stale','tombstone'))
);
CREATE TABLE assistant.ingestion_heads (
    owner_id uuid NOT NULL,
    namespace_id uuid NOT NULL,
    file_id uuid NOT NULL,
    model_fingerprint text NOT NULL,
    desired_job_id uuid,
    active_job_id uuid,
    admission_revision bigint NOT NULL CHECK (admission_revision > 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (owner_id, namespace_id, file_id, model_fingerprint),
    FOREIGN KEY (file_id, owner_id) REFERENCES assistant.files(id, owner_id),
    FOREIGN KEY (desired_job_id, owner_id, namespace_id, file_id, model_fingerprint)
        REFERENCES assistant.ingestion_jobs(id, owner_id, namespace_id, file_id, model_fingerprint),
    FOREIGN KEY (active_job_id, owner_id, namespace_id, file_id, model_fingerprint)
        REFERENCES assistant.ingestion_jobs(id, owner_id, namespace_id, file_id, model_fingerprint)
);
CREATE INDEX ix_ingestion_jobs_due ON assistant.ingestion_jobs(namespace_id, state, next_attempt_at, id);
CREATE INDEX ix_ingestion_jobs_source ON assistant.ingestion_jobs(owner_id, namespace_id, file_id, model_fingerprint);
GRANT SELECT, INSERT, DELETE ON assistant.ingestion_jobs, assistant.ingestion_heads TO local_assistant_app;
GRANT UPDATE (state, attempts, lease_token, lease_expires_at, updated_at, next_attempt_at,
    published_at, cleanup_done_at, error_code) ON assistant.ingestion_jobs TO local_assistant_app;
GRANT UPDATE (desired_job_id, active_job_id, admission_revision, updated_at)
    ON assistant.ingestion_heads TO local_assistant_app;
REVOKE TRUNCATE, REFERENCES, TRIGGER ON assistant.ingestion_jobs, assistant.ingestion_heads FROM local_assistant_app;
"""


def upgrade():
    """Create additive constrained journal tables and least-change runtime grants transactionally."""
    op.execute(text("SET LOCAL lock_timeout='5s'"))
    op.execute(text("SET LOCAL statement_timeout='30s'"))
    op.execute(text(INGESTION_DDL))
    logger.info("ingestion_journal_schema_upgraded revision=0003")


def downgrade():
    """Refuse any destructive downgrade while a live or terminal ingestion record exists."""
    op.execute(
        text("""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM assistant.ingestion_jobs)
         OR EXISTS (SELECT 1 FROM assistant.ingestion_heads) THEN
        RAISE EXCEPTION 'Ingestion journal must be empty before reviewed downgrade';
      END IF;
    END $$;
    DROP TABLE assistant.ingestion_heads;
    DROP TABLE assistant.ingestion_jobs;
    """)
    )
    logger.info("ingestion_journal_schema_downgraded revision=0002")
