"""Coordinate bounded read-only specialist runs with process-local reviews, cancellation and context receipts."""

import asyncio
import hashlib
import logging
from uuid import UUID, uuid4

from apps.api.services.harness_tools import HarnessToolRun
from apps.api.services.skill_tools import SkillToolRun
from src.application.services.mcp_adapter import canonical
from src.application.services.skill_contract import SkillError, SkillRegistry
from src.infrastructure.harness_history import HistoryError
from src.infrastructure.context_archive import ContextArchive
from src.infrastructure.summary_cache import SummaryCache
from src.application.services.source_output_contract import SourceContractError, digest

LOGGER = logging.getLogger(__name__)
TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
RUN_TERMINAL = TERMINAL | {"interrupted"}


class HarnessError(Exception):
    """Carry a finite safe product failure code without leaking underlying payloads."""

    def __init__(self, code, status=409):
        """Keep only the public code and HTTP status for the API boundary."""
        self.code, self.status = code, status
        super().__init__(code)


class ProductHarness:
    """Own a single-admission read-only task coordinator and ephemeral exact skill grants."""

    def __init__(self, inference, workspace=None, *, history=None):
        """Bind existing host services without creating roots, restoring grants or loading models."""
        self.inference, self.workspace = inference, workspace
        self.skills = SkillRegistry()
        self.review_bytes, self.runs, self.tasks = {}, {}, {}
        self.admission = asyncio.Lock()
        self.context_archive = ContextArchive()
        self.summary_cache = SummaryCache()
        self.closed = False
        self.history, self.history_broken = history, False
        if history is not None:
            for record in history.load():
                owner = UUID(record["owner_id"])
                if sum(row["owner"] == owner for row in self.runs.values()) >= 8:
                    raise HistoryError("history_owner_capacity")
                row = {
                    key: record[key]
                    for key in (
                        "id",
                        "workspace_id",
                        "state",
                        "events",
                        "request_sha256",
                        "result_sha256",
                        "context_sha256",
                    )
                }
                row.update(owner=owner, archive_only=True, result_available=False)
                if record["error_code"] is not None:
                    row["error"] = {"code": record["error_code"]}
                if row["state"] not in RUN_TERMINAL:
                    self.event(
                        row, "interrupted", error={"code": "restart_interrupted"}
                    )
                self.runs[UUID(row["id"])] = row
        LOGGER.info("product_harness_initialized")

    def installed(self, owner, workspace, identifier):
        """Resolve an exact current installation owned by this principal and workspace."""
        for installed in self.skills.installed.values():
            if (
                installed.identifier == identifier
                and installed.owner_id == owner
                and installed.workspace_id == workspace
            ):
                self.skills.authorize(
                    owner, workspace, installed, installed.manifest.permissions[0]
                )
                return installed
        raise HarnessError("skill_not_installed", 404)

    def list_skills(self, owner):
        """Return only this owner's installations without exposing instructions by default."""
        return [
            dict(
                installation_id=str(row.identifier),
                workspace_id=str(row.workspace_id),
                id=row.manifest.identifier,
                version=row.manifest.version,
                sha256=row.manifest.raw_sha256,
                permissions=row.manifest.permissions,
            )
            for row in self.skills.installed.values()
            if row.owner_id == owner
        ]

    def review(self, owner, workspace, raw):
        """Retain bounded raw bytes for exactly the existing expiring owner review."""
        review = self.skills.review(owner, workspace, raw)
        self.review_bytes = {
            key: value
            for key, value in self.review_bytes.items()
            if key in self.skills.reviews
        }
        self.review_bytes[review.identifier] = raw
        LOGGER.info("product_skill_reviewed review_id=%s", review.identifier)
        return dict(
            review_id=str(review.identifier),
            sha256=review.manifest_sha256,
            permissions=review.permissions,
            manifest=raw.decode("utf-8"),
            expires_in_seconds=120,
        )

    def install(self, owner, workspace, review_id, digest):
        """Consume an explicit exact-hash owner installation request using the original trust registry."""
        raw = self.review_bytes.get(review_id)
        if raw is None:
            raise HarnessError("review_required", 404)
        installed = self.skills.install(
            owner,
            workspace,
            review_id,
            raw,
            reviewed_sha256=digest,
            explicit_trust=True,
        )
        self.review_bytes.pop(review_id, None)
        return dict(
            installation_id=str(installed.identifier),
            sha256=installed.manifest.raw_sha256,
        )

    def get(self, owner, identifier):
        """Hide absent and cross-owner runs behind the same not-found response."""
        row = self.runs.get(identifier)
        if row is None or row["owner"] != owner:
            raise HarnessError("run_not_found", 404)
        return {
            **{key: value for key, value in row.items() if key != "owner"},
            "result_available": "result" in row,
            "archive_only": row.get("archive_only", False),
        }

    def event(self, row, state, **values):
        """Append a bounded metadata-only ordered state transition."""
        candidate = {
            **row,
            **values,
            "state": state,
            "events": row["events"]
            + [dict(sequence=len(row["events"]) + 1, state=state)],
        }
        if self.history is not None:
            if self.history_broken:
                raise HarnessError("history_unavailable", 503)
            try:
                self.history.save(candidate)
            except HistoryError:
                self.history_broken = True
                LOGGER.error("product_history_write_failed run_id=%s", row["id"])
                raise HarnessError("history_unavailable", 503) from None
        row.update(candidate)
        LOGGER.info("product_run_state run_id=%s state=%s", row["id"], state)

    def history_failure(self, row):
        """Expose a nonpersisted failure without publishing a model result or retrying the failed snapshot."""
        row.update(
            state="failed",
            error={"code": "history_unavailable"},
            history_persisted=False,
        )
        row.pop("result", None)
        row.pop("context", None)
        LOGGER.error("product_run_not_persisted run_id=%s", row["id"])

    def start(self, owner, request):
        """Admit finite task input and schedule a bounded worker without accepting write capabilities."""
        if self.closed:
            raise HarnessError("harness_closed", 503)
        if self.history_broken:
            raise HarnessError("history_unavailable", 503)
        if (
            len(self.runs) >= 64
            or sum(row["owner"] == owner for row in self.runs.values()) >= 8
        ):
            raise HarnessError("run_capacity", 429)
        installed = None
        if request.skill is not None:
            installed = self.installed(owner, request.workspace_id, request.skill)
        if request.tools and self.workspace is None:
            raise HarnessError("workspace_unavailable", 503)
        identifier = uuid4()
        row = dict(
            id=str(identifier),
            owner=owner,
            workspace_id=str(request.workspace_id),
            state="created",
            events=[],
            request_sha256=hashlib.sha256(
                request.model_dump_json().encode()
            ).hexdigest(),
        )
        self.event(row, "created")
        self.runs[identifier] = row
        self.tasks[identifier] = asyncio.create_task(
            self.execute(owner, row, request, installed)
        )
        return self.get(owner, identifier)

    async def execute(self, owner, row, request, installed):
        """Run at most four readonly calls then one verified completion, joining all owned work on exit."""
        try:
            async with asyncio.timeout(120):
                async with self.admission:
                    self.event(row, "running")
                    evidence = []
                    if request.tools:
                        reader = (
                            SkillToolRun(
                                self.skills,
                                installed,
                                self.workspace,
                                owner,
                                request.workspace_id,
                            )
                            if installed is not None
                            else HarnessToolRun(
                                owner,
                                request.workspace_id,
                                profile="core",
                                workspace_service=self.workspace,
                            )
                        )
                        try:
                            for tool in request.tools:
                                evidence.append(
                                    await reader.execute(canonical(tool.model_dump()))
                                )
                        finally:
                            await reader.close()
                    if installed is not None:
                        self.skills.authorize(
                            owner,
                            request.workspace_id,
                            installed,
                            installed.manifest.permissions[0],
                        )
                    result, context = await self.inference.complete(
                        [{"role": "user", "content": request.task}],
                        preset=request.preset,
                        max_tokens=request.max_tokens,
                        skill=installed.manifest if installed is not None else None,
                        evidence=evidence,
                        context_strategy=request.context_strategy,
                        output_contract=request.output_contract,
                        review_target=request.review_target,
                    )
                    if installed is not None:
                        self.skills.authorize(
                            owner,
                            request.workspace_id,
                            installed,
                            installed.manifest.permissions[0],
                        )
                    self.event(row, "succeeded", result=result, context=context)
        except asyncio.CancelledError:
            try:
                self.event(row, "cancelled")
            except HarnessError:
                self.history_failure(row)
            raise
        except Exception as error:
            code = "skill_revoked" if isinstance(error, SkillError) else "run_failed"
            if isinstance(error, TimeoutError):
                code = "run_timeout"
            diagnostic = {}
            if isinstance(error, SourceContractError):
                diagnostic["diagnostic"] = {"code": error.code}
                if error.raw_result is not None:
                    diagnostic["diagnostic"]["raw_result"] = error.raw_result
                    diagnostic["result_sha256"] = digest(error.raw_result)
            try:
                self.event(row, "failed", error={"code": code}, **diagnostic)
            except HarnessError:
                self.history_failure(row)

    async def cancel(self, owner, identifier):
        """Cancel only the owner's active worker and wait for resource cleanup before returning."""
        self.get(owner, identifier)
        task = self.tasks.get(identifier)
        if task is None:
            if self.runs[identifier]["state"] in RUN_TERMINAL:
                return self.get(owner, identifier)
            raise HarnessError("run_not_active")
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if self.runs[identifier]["state"] not in RUN_TERMINAL:
                try:
                    self.event(self.runs[identifier], "cancelled")
                except HarnessError:
                    self.history_failure(self.runs[identifier])
        return self.get(owner, identifier)

    def remove(self, owner, identifier):
        """Release terminal result capacity without cancelling or replaying an active operation."""
        row = self.get(owner, identifier)
        if row["state"] not in RUN_TERMINAL:
            raise HarnessError("run_active")
        if self.history is not None:
            try:
                if self.history_broken:
                    raise HistoryError("history_unavailable")
                self.history.remove(owner, identifier)
            except HistoryError:
                self.history_broken = True
                raise HarnessError("history_unavailable", 503) from None
        self.runs.pop(identifier)
        self.tasks.pop(identifier, None)
        LOGGER.info("product_run_removed run_id=%s", identifier)
        return {"removed": True}

    async def close(self):
        """Join all owned tasks and revoke process-local skills before shared services close."""
        self.closed = True
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        for identifier, row in self.runs.items():
            if identifier in self.tasks and row["state"] not in RUN_TERMINAL:
                try:
                    self.event(row, "cancelled")
                except HarnessError:
                    self.history_failure(row)
        self.skills.shutdown()
        self.review_bytes.clear()
        self.context_archive.close()
        self.summary_cache.close()
        LOGGER.info("product_harness_closed")
