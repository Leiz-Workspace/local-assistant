"""Own optional generation jobs and bounded owner-scoped in-memory artifacts without model auto-selection."""

import asyncio
import hashlib
import logging
from uuid import uuid4

from apps.harness.service import HarnessError, TERMINAL
from src.application.ports.media_generation import GeneratedMedia

LOGGER = logging.getLogger(__name__)


class GenerationJobs:
    """Coordinate explicitly supplied adapters while leaving generation unavailable by default."""

    def __init__(self, admission, *, backends=None):
        """Bind trusted adapters and shared admission without importing, downloading or loading a model."""
        self.admission, self.backends = admission, dict(backends or {})
        if set(self.backends) - {"image", "video"}:
            raise ValueError("unknown_generation_kind")
        self.jobs, self.tasks, self.artifacts = {}, {}, {}
        self.closed = False

    def get(self, owner, identifier):
        """Hide all cross-owner job metadata behind the same absent-job response."""
        row = self.jobs.get(identifier)
        if row is None or row["owner"] != owner:
            raise HarnessError("generation_not_found", 404)
        return {key: value for key, value in row.items() if key != "owner"}

    def start(self, owner, request):
        """Refuse missing capabilities before retaining prompts or allocating job resources."""
        if self.closed or request.kind not in self.backends:
            raise HarnessError("generation_capability_unavailable", 503)
        if (
            len(self.jobs) >= 16
            or sum(row["owner"] == owner for row in self.jobs.values()) >= 4
        ):
            raise HarnessError("generation_capacity", 429)
        identifier = uuid4()
        self.jobs[identifier] = dict(
            id=str(identifier), owner=owner, state="created", kind=request.kind
        )
        self.tasks[identifier] = asyncio.create_task(self.execute(identifier, request))
        LOGGER.info(
            "generation_job_created job_id=%s kind=%s", identifier, request.kind
        )
        return self.get(owner, identifier)

    async def execute(self, identifier, request):
        """Generate one bounded artifact without retries and clear unfinished output on failure or cancellation."""
        row = self.jobs[identifier]
        try:
            async with asyncio.timeout(120):
                async with self.admission:
                    row["state"] = "running"
                    result = await self.backends[request.kind].generate(request)
                    expected = "image/png" if request.kind == "image" else "video/mp4"
                    if (
                        type(result) is not GeneratedMedia
                        or type(result.content) is not bytes
                        or not 1 <= len(result.content) <= 8388608
                        or result.mime_type != expected
                        or not result.model_id
                        or not result.model_revision
                    ):
                        raise ValueError("invalid_generated_artifact")
                    if (
                        sum(len(value.content) for value in self.artifacts.values())
                        + len(result.content)
                        > 33554432
                    ):
                        raise ValueError("artifact_capacity")
                    self.artifacts[identifier] = result
                    row.update(
                        state="succeeded",
                        sha256=hashlib.sha256(result.content).hexdigest(),
                        bytes=len(result.content),
                        mime_type=result.mime_type,
                        model_id=result.model_id,
                        model_revision=result.model_revision,
                        options={
                            key: value
                            for key, value in request.model_dump().items()
                            if key != "prompt"
                        },
                    )
        except asyncio.CancelledError:
            row["state"] = "cancelled"
            raise
        except Exception:
            row.update(state="failed", error={"code": "generation_failed"})
        finally:
            LOGGER.info(
                "generation_job_finished job_id=%s state=%s", identifier, row["state"]
            )

    def artifact(self, owner, identifier):
        """Return only a completed artifact belonging to the current authenticated owner."""
        if self.get(owner, identifier)["state"] != "succeeded":
            raise HarnessError("artifact_not_ready")
        return self.artifacts[identifier]

    async def cancel(self, owner, identifier):
        """Wait for adapter cancellation cleanup without retrying an interrupted job."""
        self.get(owner, identifier)
        task = self.tasks[identifier]
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.jobs[identifier]["state"] = "cancelled"
        return self.get(owner, identifier)

    def remove(self, owner, identifier):
        """Delete retained terminal bytes and metadata without accepting arbitrary filesystem paths."""
        if self.get(owner, identifier)["state"] not in TERMINAL:
            raise HarnessError("generation_active")
        self.jobs.pop(identifier)
        self.tasks.pop(identifier)
        self.artifacts.pop(identifier, None)
        LOGGER.info("generation_job_removed job_id=%s", identifier)
        return {"removed": True}

    async def close(self):
        """Join owned workers and discard ephemeral bytes before shared admission is retired."""
        self.closed = True
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.artifacts.clear()
        LOGGER.info("generation_jobs_closed")
