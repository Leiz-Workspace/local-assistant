"""Verify optional image/video job boundaries without downloading or running a generation model."""

import asyncio
import logging
from uuid import UUID, uuid4

import pytest

from apps.harness.generation import GenerationJobs
from apps.harness.service import HarnessError
from src.application.ports.media_generation import GeneratedMedia, GenerationRequest
from tests import test_product_harness

product_client = test_product_harness.product_client
LOGGER = logging.getLogger(__name__)


class FixtureBackend:
    """Return synthetic byte contracts only, never an actual generated image or movie."""

    def __init__(self, *, block=False, invalid=False):
        """Track calls and optional cancellation without allocating model resources."""
        self.calls, self.invalid = 0, invalid
        self.wait = asyncio.Event() if block else None

    async def generate(self, request):
        """Provide explicit fixture provenance and bounded bytes for lifecycle tests."""
        self.calls += 1
        if self.wait is not None:
            await self.wait.wait()
        return GeneratedMedia(
            b"synthetic output contract",
            "invalid"
            if self.invalid
            else ("image/png" if request.kind == "image" else "video/mp4"),
            "fixture-only",
            "fixture-revision-not-a-real-model",
        )


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.asyncio
async def test_missing_adapter_never_starts_work(kind):
    """Fail before retaining a prompt, creating a job or selecting another provider."""
    jobs = GenerationJobs(asyncio.Lock())
    request = GenerationRequest(
        kind=kind,
        prompt="fixture",
        **({"seconds": 2, "fps": 12} if kind == "video" else {}),
    )
    with pytest.raises(HarnessError, match="generation_capability_unavailable"):
        jobs.start(uuid4(), request)
    assert not jobs.jobs and not jobs.tasks
    await jobs.close()


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.asyncio
async def test_job_artifact_ownership_receipt_and_removal(kind):
    """Retain exact metadata/digests and prevent cross-owner artifact access."""
    owner = uuid4()
    backend = FixtureBackend()
    jobs = GenerationJobs(asyncio.Lock(), backends={kind: backend})
    request = GenerationRequest(
        kind=kind,
        prompt="fixture",
        **({"seconds": 2, "fps": 12} if kind == "video" else {}),
    )
    identifier = UUID(jobs.start(owner, request)["id"])
    await jobs.tasks[identifier]
    row = jobs.get(owner, identifier)
    assert row["state"] == "succeeded" and row["model_id"] == "fixture-only"
    assert "prompt" not in row["options"] and backend.calls == 1
    assert jobs.artifact(owner, identifier).content == b"synthetic output contract"
    with pytest.raises(HarnessError, match="generation_not_found"):
        jobs.artifact(uuid4(), identifier)
    assert jobs.remove(owner, identifier)["removed"]
    assert not jobs.artifacts
    await jobs.close()
    LOGGER.info("test_optional_generation_contract_verified kind=%s", kind)


@pytest.mark.asyncio
async def test_generation_cancel_and_failure_do_not_publish_partial_assets():
    """Join a blocked adapter and retain failures without automatic retries or artifact publication."""
    owner = uuid4()
    backend = FixtureBackend(block=True)
    jobs = GenerationJobs(asyncio.Lock(), backends={"image": backend})
    identifier = UUID(
        jobs.start(owner, GenerationRequest(kind="image", prompt="fixture"))["id"]
    )
    await asyncio.sleep(0)
    assert (await jobs.cancel(owner, identifier))["state"] == "cancelled"
    assert jobs.tasks[identifier].done() and not jobs.artifacts
    invalid = FixtureBackend(invalid=True)
    jobs.backends["image"] = invalid
    second = UUID(
        jobs.start(owner, GenerationRequest(kind="image", prompt="fixture"))["id"]
    )
    await jobs.tasks[second]
    assert jobs.get(owner, second)["state"] == "failed"
    assert invalid.calls == 1 and not jobs.artifacts
    await jobs.close()


@pytest.mark.parametrize(
    "override",
    [
        {"model": "unapproved"},
        {"path": "/tmp/output"},
        {"width": 513},
        {"width": 4096},
        {"seconds": 10},
        {"seed": -1},
        {"prompt": " "},
    ],
)
def test_generation_rejects_authority_and_unbounded_options(override):
    """Reject caller-selected models, paths and invalid resource envelopes before admission."""
    with pytest.raises(ValueError):
        GenerationRequest.model_validate(
            {"kind": "image", "prompt": "fixture", **override}
        )


def test_generation_api_unavailable_without_backend_and_no_job_retained(product_client):
    """Expose honest capability errors rather than producing placeholder media or loading a model."""
    client, _, settings, _ = product_client
    headers = test_product_harness.bearer(settings)
    response = client.post(
        "/api/v1/harness/generations",
        headers=headers,
        json={"kind": "image", "prompt": "fixture"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "generation_capability_unavailable"
    assert client.get("/api/v1/harness/generations", headers=headers).json() == []
