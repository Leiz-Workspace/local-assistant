"""Export bounded database-pool counters through periodic structured application logs."""

import asyncio
import json
import logging
from threading import Lock

from sqlalchemy import event

logger = logging.getLogger(__name__)


class PoolTelemetry:
    """Observe pool events without retaining connections, queries or credentials."""

    def __init__(self, engine):
        """Register lightweight checkout, checkin and invalidation observers."""
        self.engine = engine
        self.lock = Lock()
        self.counters = {
            "checkouts": 0,
            "checkins": 0,
            "invalidations": 0,
            "timeouts": 0,
            "peak_checked_out": 0,
        }
        self.listeners = [
            ("checkout", self.on_checkout),
            ("checkin", self.on_checkin),
            ("invalidate", self.on_invalidate),
        ]
        for name, handler in self.listeners:
            event.listen(engine.sync_engine, name, handler)

    def on_checkout(self, connection, record, proxy):
        """Count acquired connections and track observed peak concurrent checkout."""
        with self.lock:
            self.counters["checkouts"] += 1
            self.counters["peak_checked_out"] = max(
                self.counters["peak_checked_out"], self.engine.pool.checkedout()
            )

    def on_checkin(self, connection, record):
        """Count returned connections without inspecting DBAPI state."""
        with self.lock:
            self.counters["checkins"] += 1

    def on_invalidate(self, connection, record, error):
        """Count invalidations while deliberately omitting driver exception text."""
        with self.lock:
            self.counters["invalidations"] += 1

    def note_timeout(self):
        """Count a pool timeout reported by the HTTP composition boundary."""
        with self.lock:
            self.counters["timeouts"] += 1
        self.emit()

    def snapshot(self) -> dict[str, int]:
        """Return only aggregate operational counters and current pool utilization."""
        with self.lock:
            return {
                **self.counters,
                "pool_size": self.engine.pool.size(),
                "checked_out": self.engine.pool.checkedout(),
                "overflow": max(0, self.engine.pool.overflow()),
            }

    def emit(self):
        """Write a machine-readable sample through the deployment logging pipeline."""
        logger.info(
            json.dumps(
                {"event": "database_pool_metrics", **self.snapshot()}, sort_keys=True
            )
        )

    async def sample(self, interval: float = 30):
        """Export samples while sleeping outside database sessions or transactions."""
        if not 0 < interval <= 3600:
            raise ValueError("Pool sampling interval must be within 0..3600 seconds")
        while True:
            self.emit()
            await asyncio.sleep(interval)

    def close(self):
        """Emit a final sample and unregister listeners before pool disposal."""
        self.emit()
        for name, handler in self.listeners:
            event.remove(self.engine.sync_engine, name, handler)
