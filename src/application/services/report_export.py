"""Own one issuer-authenticated fixed DOCX/PDF export through quota, source revalidation and joined native cleanup without changing shared services."""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from src.application.ports.report_export import ReportExport
from src.application.services.report_export_policy import (
    ReportExportError,
    check_native,
    make_payload,
)
from src.application.services.research import cancelled
from src.application.services.research_report_policy import ResearchReportError
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.application.services.web_search_policy import WebSearchError, WebSearchQuota

logger = logging.getLogger(__name__)
TOTAL_SECONDS = 25


class ReportExportService:
    """Gate complete artifact bytes on the original issuer/owner/report receipt while retaining native ownership until actual cleanup."""

    def __init__(self, *, reports, exporter, quota=None):
        """Bind inert trusted issuer/native dependencies with an independent finite counter and no file/model/network/profile activity."""
        self.reports, self.exporter = reports, exporter
        self.quota = quota if quota is not None else WebSearchQuota()
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False
        logger.info("report_export_service_initialized")

    def verify(self, owner, report):
        """Require an issuer-authenticated original report before native work and before publishing completed artifacts."""
        try:
            self.reports.verify(owner, report)
        except ResearchReportError:
            raise ReportExportError("export_proof_invalid") from None

    def charge(self, owner):
        """Charge one admitted both-format native attempt without refund after cancellation, failure or dispatch."""
        try:
            self.quota.charge(owner)
        except WebSearchError as error:
            raise ReportExportError(
                "export_rate_limited"
                if error.code == "web_search_rate_limited"
                else "export_unavailable"
            ) from None

    async def export(self, owner, report):
        """Validate complete owner-bound report/payload before nonqueued native admission and retain task ownership under repeated cancellation."""
        if type(owner) is not UUID:
            raise ReportExportError("export_invalid")
        if self.reports is None or self.exporter is None:
            raise ReportExportError("export_unavailable")
        if self.closing or getattr(self.exporter, "closing", False):
            self.closing = True
            raise ReportExportError("export_closed")
        self.verify(owner, report)
        payload = make_payload(report)
        if self.admission.locked():
            raise ReportExportError("export_busy")
        await self.admission.acquire()
        caller, task = asyncio.current_task(), None
        try:
            self.charge(owner)
            self.operations.add(caller)
            task = spawn_owned(self.run(owner, report, payload))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException as error:
                    if (
                        isinstance(error, ReportExportError)
                        and error.code == "export_cleanup_uncertain"
                    ):
                        self.closing = True
                    logger.info("report_export_cancelled_operation_joined")
                raise
        except asyncio.CancelledError:
            raise
        except ReportExportError as error:
            if error.code == "export_cleanup_uncertain":
                self.closing = True
            raise
        except Exception:
            raise ReportExportError("export_internal") from None
        finally:
            if getattr(self.exporter, "closing", False):
                self.closing = True
                logger.warning(
                    "report_export_native_dependency_closed_admission_poisoned"
                )
            self.operations.discard(caller)
            self.admission.release()
            logger.info("report_export_operation_closed")

    async def run(self, owner, report, payload):
        """Join one fixed native batch and reject expired or altered source receipts before returning complete immutable artifact bytes."""
        try:
            async with asyncio.timeout(TOTAL_SECONDS) as deadline:
                native = await self.exporter.render(payload)
                cancelled()
                if deadline.expired():
                    raise ReportExportError("export_timeout")
                check_native(native, report.markdown_sha256)
                self.verify(owner, report)
        except TimeoutError:
            raise ReportExportError("export_timeout") from None
        cancelled()
        logger.info(
            "report_export_complete_both_formats_verified pages=%d", native.pdf_pages
        )
        return ReportExport(
            owner,
            report.markdown_sha256,
            native.artifacts,
            native.pdf_pages,
            datetime.now(UTC),
        )

    async def shutdown(self):
        """Close admission and join only owned native export operations without shutting down shared report/evidence/model/provider services."""
        self.closing = True
        callers = [
            task for task in self.operations if task is not asyncio.current_task()
        ]
        for task in callers:
            task.cancel()
        for task in callers:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("report_export_shutdown_operation_joined")
        logger.info("report_export_shutdown_complete")
