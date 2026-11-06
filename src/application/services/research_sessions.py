"""Own finite explicit durable research stages with fresh-proof resume, archived output and joined cancellation."""

import asyncio
import logging
from dataclasses import asdict

from src.application.services.research import cancelled
from src.application.services.research_policy import check_result
from src.application.services.research_session_policy import (
    ResearchSessionError,
    export_payload,
    identifiers,
    pack_archive,
    report_payload,
)
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

logger = logging.getLogger(__name__)
STAGE_SECONDS = 60


class ResearchSessionService:
    """Advance one explicit discover or publish stage without background loops, receipt persistence or automatic retry."""

    def __init__(self, *, store, planner, reports, exports):
        """Bind externally owned trusted components and inert nonqueued admission without tool calls or storage provisioning."""
        self.store, self.planner, self.reports, self.exports = (
            store,
            planner,
            reports,
            exports,
        )
        self.admission = asyncio.Lock()
        self.operations = {}
        self.closing = False
        logger.info("research_session_service_initialized")

    def available(self):
        """Refuse unavailable/closed components and poison admission when a shared dependency cannot guarantee cleanup."""
        if self.closing or any(
            getattr(item, "closing", False)
            for item in (self.store, self.planner, self.reports, self.exports)
        ):
            self.closing = True
            raise ResearchSessionError("session_closed")
        if any(
            item is None
            for item in (self.store, self.planner, self.reports, self.exports)
        ):
            raise ResearchSessionError("session_invalid")

    def create(self, owner, goal, claims):
        """Durably record one explicit owner's normalized inputs without executing any research stage."""
        self.available()
        return self.store.create(owner, goal, claims)

    def status(self, owner, run_id):
        """Read retained progress even after workflow shutdown without reviving model/source authority."""
        identifiers(owner, run_id)
        return self.store.load(owner, run_id)

    def archive(self, owner, run_id, kind):
        """Retrieve complete owned archived bytes without interpreting them as a live report receipt or current facts."""
        identifiers(owner, run_id)
        return self.store.archive(owner, run_id, kind)

    async def execute(self, owner, run_id, value, selections):
        """Execute the sole reserved stage and checkpoint complete outputs before pausing or completing the finite session."""
        async with asyncio.timeout(STAGE_SECONDS) as deadline:
            if value["attempts"][-1] == "discover":
                result = check_result(await self.planner.research(owner, value["goal"]))
                cancelled()
                if result.owner_id != owner or result.goal != value["goal"]:
                    raise ResearchSessionError("session_stage_failed")
                raw = pack_archive("discover", owner, run_id, asdict(result))
                self.store.append(owner, run_id, "discover", raw)
            else:
                report = await self.reports.generate(
                    owner, value["goal"], tuple(value["claims"]), selections
                )
                cancelled()
                self.reports.verify(owner, report)
                self.store.append(
                    owner,
                    run_id,
                    "report",
                    pack_archive("report", owner, run_id, report_payload(report)),
                )
                cancelled()
                if deadline.expired():
                    raise TimeoutError()
                exported = await self.exports.export(owner, report)
                cancelled()
                self.reports.verify(owner, report)
                raw = pack_archive(
                    "export", owner, run_id, export_payload(exported, owner, report)
                )
                self.store.append(owner, run_id, "export", raw)
            cancelled()
            if deadline.expired():
                raise TimeoutError()
            return self.store.finish(owner, run_id)

    def interrupted(self, owner, run_id, code):
        """Retain charged attempts and prior bytes after owned cleanup, closing admission on uncertain durable publication."""
        try:
            self.store.interrupt(owner, run_id, code)
        except Exception:
            self.closing = True
            logger.warning("research_session_interruption_publication_uncertain")

    async def advance(self, owner, run_id, selections=()):
        """Reserve/execute exactly one stage and join its task through repeated cancellation before releasing admission."""
        identifiers(owner, run_id)
        self.available()
        value = self.store.load(owner, run_id)
        if value["state"] not in {"ready", "paused"}:
            raise ResearchSessionError("session_state_invalid")
        if value["state"] == "paused":
            try:
                self.reports.validator.references(owner, selections)
            except Exception:
                raise ResearchSessionError("session_fresh_sources_required") from None
        elif selections != ():
            raise ResearchSessionError("session_invalid")
        if self.admission.locked():
            raise ResearchSessionError("session_busy")
        await self.admission.acquire()
        caller, task, reserved = asyncio.current_task(), None, False
        try:
            self.operations[run_id] = caller
            value = self.store.begin(owner, run_id)
            reserved = True
            try:
                task = spawn_owned(self.execute(owner, run_id, value, selections))
            except Exception:
                self.interrupted(owner, run_id, "session_dispatch_failed")
                reserved = False
                raise ResearchSessionError("session_dispatch_failed") from None
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info("research_session_cancelled_stage_joined")
                raise
        except asyncio.CancelledError:
            if reserved:
                self.interrupted(owner, run_id, "session_cancelled")
            raise
        except Exception as error:
            code = (
                "session_timeout"
                if isinstance(error, TimeoutError)
                else "session_stage_failed"
            )
            if isinstance(error, ResearchSessionError):
                code = error.code
            if getattr(error, "code", "").endswith("cleanup_uncertain"):
                code, self.closing = "session_cleanup_uncertain", True
            if reserved:
                self.interrupted(owner, run_id, code)
            raise ResearchSessionError(code) from None
        finally:
            if any(
                getattr(item, "closing", False)
                for item in (self.store, self.planner, self.reports, self.exports)
            ):
                self.closing = True
            self.operations.pop(run_id, None)
            self.admission.release()
            logger.info("research_session_operation_closed")

    async def cancel(self, owner, run_id):
        """Cancel/join only an authenticated owner's active session caller without affecting foreign/shared operations."""
        identifiers(owner, run_id)
        self.store.load(owner, run_id)
        caller = self.operations.get(run_id)
        if caller is None:
            return self.store.load(owner, run_id)
        if caller is asyncio.current_task():
            raise ResearchSessionError("session_busy")
        caller.cancel()
        try:
            await finish_owned(caller)
        except BaseException:
            logger.info("research_session_owner_cancel_joined")
        return self.store.load(owner, run_id)

    async def shutdown(self):
        """Join only session-owned callers while leaving store closure and shared model/report/export/provider lifetime external."""
        self.closing = True
        callers = [
            task
            for task in self.operations.values()
            if task is not asyncio.current_task()
        ]
        for task in callers:
            task.cancel()
        for task in callers:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("research_session_shutdown_caller_joined")
        logger.info("research_session_shutdown_complete")
