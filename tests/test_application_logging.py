"""Verify application logs remain visible in a fresh runtime without duplicated handlers."""

import subprocess
import sys


def test_fresh_runtime_exports_application_logs():
    """Launch a fresh interpreter and prove INFO audit events reach stderr exactly once."""
    source = '''
"""Exercise audit logging with the same fresh interpreter state as an application launch."""
from apps.api.core.logging_config import configure_application_logging
import logging
configure_application_logging()
configure_application_logging()
logging.getLogger('src.infrastructure.database.pool_telemetry').info('ONE_POOL_EVENT')
'''
    result = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, check=True
    )
    assert result.stderr.count("ONE_POOL_EVENT") == 1
    assert "INFO" in result.stderr
