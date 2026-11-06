"""Remove inherited table-level UPDATE grants from only the new ingestion journal tables."""

import logging

from alembic import op
from sqlalchemy import text

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None
logger = logging.getLogger(__name__)


def upgrade():
    """Override existing migrator default UPDATE grants while retaining mutable runtime columns."""
    op.execute(text("SET LOCAL lock_timeout='5s'"))
    op.execute(text("SET LOCAL statement_timeout='30s'"))
    op.execute(
        text("""
    REVOKE UPDATE ON assistant.ingestion_jobs, assistant.ingestion_heads FROM local_assistant_app;
    GRANT UPDATE (state, attempts, lease_token, lease_expires_at, updated_at, next_attempt_at,
        published_at, cleanup_done_at, error_code) ON assistant.ingestion_jobs TO local_assistant_app;
    GRANT UPDATE (desired_job_id, active_job_id, admission_revision, updated_at)
        ON assistant.ingestion_heads TO local_assistant_app;
    """)
    )
    logger.info("ingestion_column_grants_restricted revision=0004")


def downgrade():
    """Preserve immutable journal protections rather than silently broaden runtime privileges."""
    logger.warning("ingestion_privilege_downgrade_refused")
    raise RuntimeError(
        "Ingestion privilege rollback requires a reviewed forward migration"
    )
