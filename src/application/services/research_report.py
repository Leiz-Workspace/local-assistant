"""Own bounded CORE-assessed cited Markdown and expiring owner-bound report receipts without modifying shared evidence or model services."""

import asyncio
import hashlib
import hmac
import logging
import math
import re
import secrets
from dataclasses import replace
from uuid import UUID

from src.application.ports.research_report import ResearchReport
from src.application.services.claim_validation import ClaimValidationService
from src.application.services.claim_validation_policy import (
    ClaimValidationError,
    prepare_claims,
)
from src.application.services.research import cancelled
from src.application.services.research_report_policy import (
    ResearchReportError,
    assessment_digest,
    check_assessment,
    render_markdown,
    report_bytes,
)
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

logger = logging.getLogger(__name__)
TOTAL_SECONDS = 25


class ResearchReportService:
    """Compose reproducible complete reports from one owned accepted claim assessment and authenticate later reuse within original proof lifetime."""

    def __init__(self, *, evidence, inference, expected_model, quota=None):
        """Bind inert dependencies, an owned validator and an ephemeral report key without source/model/filesystem activity."""
        self.evidence = evidence
        self.validator = ClaimValidationService(
            evidence=evidence,
            inference=inference,
            expected_model=expected_model,
            quota=quota,
        )
        self.proof_key = secrets.token_bytes(32)
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False
        logger.info("research_report_service_initialized")

    def sign(self, report):
        """Authenticate every report field using only the current service's ephemeral owner-bound key."""
        return hmac.digest(
            self.proof_key, report_bytes(report, proof=False), "sha256"
        ).hex()

    def verify(self, owner, report):
        """Verify exact owner/content/receipt/deadline and shared proof-service lifetime without model, filesystem or source I/O."""
        if (
            self.closing
            or not self.proof_key
            or self.evidence is None
            or getattr(self.evidence, "closing", False)
        ):
            raise ResearchReportError("report_closed")
        try:
            if (
                type(owner) is not UUID
                or type(report) is not ResearchReport
                or report.owner_id != owner
                or report.assessment.owner_id != owner
            ):
                raise ValueError()
            if (
                type(report.proof) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", report.proof)
                or type(report.citation_deadline) not in {int, float}
                or not math.isfinite(report.citation_deadline)
            ):
                raise ValueError()
            if (
                self.evidence.tick() >= report.citation_deadline
                or not hmac.compare_digest(self.sign(report), report.proof)
            ):
                raise ValueError()
            logger.info("research_report_owner_receipt_verified")
            return report
        except Exception:
            if getattr(self.evidence, "closing", False):
                self.closing = True
            raise ResearchReportError("report_proof_invalid") from None

    async def generate(self, owner, goal, claims, selections):
        """Admit one nonqueued report operation, joining nested assessment cleanup under repeated cancellation before releasing ownership."""
        if type(owner) is not UUID:
            raise ResearchReportError("report_invalid")
        if self.evidence is None or self.validator.inference is None:
            raise ResearchReportError("report_unavailable")
        if self.closing or getattr(self.evidence, "closing", False):
            self.closing = True
            raise ResearchReportError("report_closed")
        if self.admission.locked():
            raise ResearchReportError("report_busy")
        await self.admission.acquire()
        caller, task = asyncio.current_task(), None
        try:
            self.operations.add(caller)
            task = spawn_owned(self.run(owner, goal, claims, selections))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info("research_report_cancelled_operation_joined")
                raise
        except asyncio.CancelledError:
            raise
        except ResearchReportError:
            raise
        except ClaimValidationError as error:
            logger.info("research_report_assessment_rejected code=%s", error.code)
            mapping = {
                "claim_invalid": "report_invalid",
                "claim_proof_invalid": "report_proof_invalid",
                "claim_rate_limited": "report_rate_limited",
                "claim_model_timeout": "report_timeout",
                "claim_timeout": "report_timeout",
                "claim_cleanup_uncertain": "report_cleanup_uncertain",
            }
            raise ResearchReportError(
                mapping.get(error.code, "report_assessment_failed")
            ) from None
        except Exception:
            raise ResearchReportError("report_internal") from None
        finally:
            if getattr(self.evidence, "closing", False) or self.validator.closing:
                self.closing = True
                logger.warning("research_report_dependency_closed_admission_poisoned")
            self.operations.discard(caller)
            self.admission.release()
            logger.info("research_report_operation_closed")

    async def run(self, owner, goal, claims, selections):
        """Bind freshly authenticated inputs around one accepted assessment and deterministic rendering before signing an expiring complete report."""
        try:
            async with asyncio.timeout(TOTAL_SECONDS) as deadline:
                goal, claims = prepare_claims(goal, claims)
                references = self.validator.references(owner, selections)
                assessed = await self.validator.validate(
                    owner, goal, claims, selections
                )
                cancelled()
                if self.validator.references(owner, selections) != references:
                    raise ResearchReportError("report_proof_invalid")
                check_assessment(assessed, owner, goal, claims, references)
                markdown = render_markdown(assessed)
                cancelled()
                if self.validator.references(owner, selections) != references:
                    raise ResearchReportError("report_proof_invalid")
                expiry = min(
                    self.evidence.tick() + 300,
                    *(row.snapshot.citation_deadline for row in selections),
                )
                report = ResearchReport(
                    owner,
                    assessed,
                    markdown,
                    hashlib.sha256(markdown.encode()).hexdigest(),
                    assessment_digest(assessed),
                    expiry,
                    "",
                )
                report = replace(report, proof=self.sign(report))
                report_bytes(report)
                self.verify(owner, report)
                if deadline.expired():
                    raise ResearchReportError("report_timeout")
        except TimeoutError:
            raise ResearchReportError("report_timeout") from None
        cancelled()
        logger.info(
            "research_report_complete_receipt_issued claims=%d citations=%d",
            len(report.assessment.claims),
            len(report.assessment.evidence),
        )
        return report

    async def shutdown(self):
        """Join only report-owned work/validator and revoke report receipts while keeping shared evidence/model lifetime external."""
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
                logger.info("research_report_shutdown_operation_joined")
        await self.validator.shutdown()
        self.proof_key = b""
        logger.info("research_report_shutdown_complete")
