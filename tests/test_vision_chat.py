"""Verify image-operation ownership, independent quotas, native-thread lifetime and joined model cancellation with authored ports."""

import asyncio
import logging
import threading
import time
from dataclasses import replace
from uuid import uuid4

import pytest
from test_vision_chat_policy import completion
from test_vision_chat_policy import image as image

import src.application.services.vision_chat as module
from src.application.services.vision_chat import VisionChatService
from src.application.services.vision_chat_policy import ImageChatError

RAW = b"authored source"


class Normalizer:
    """Return an authored normalized image for lifecycle tests without claiming actual native execution."""

    def __init__(self, image):
        """Bind an immutable test raster and an empty native-attempt ledger."""
        self.image, self.calls = image, []

    def normalize(self, raw, suffix):
        """Record the unchanged explicit source and suffix before returning authored normalized output."""
        self.calls.append((raw, suffix))
        return self.image


class Core:
    """Record image/question-only requests with no external model, history or tool calls."""

    def __init__(self):
        """Initialize one authored response and a shared-lifetime poison indicator."""
        self.calls, self.result, self.closing = [], completion(), False

    async def complete_image(self, **options):
        """Return one unchanged authored fixed-model answer while preserving request identity."""
        self.calls.append(options)
        return self.result


def configured(image):
    """Compose a current-operation service with separate authored CPU/model resources and no image persistence."""
    normalizer, core = Normalizer(image), Core()
    return (
        VisionChatService(
            normalizer=normalizer, inference=core, expected_model="fixture-core"
        ),
        normalizer,
        core,
    )


async def wait_entered(event):
    """Bound polling of a controlled native thread event without spawning an unowned blocking waiter."""
    async with asyncio.timeout(1):
        while not event.is_set():
            await asyncio.sleep(0.001)


@pytest.mark.asyncio
async def test_complete_private_operation_preserves_owner_hashes_without_persistence_or_shared_shutdown(
    image, caplog
):
    """Keep explicit image identity and unverified answer metadata while logs and shared resources stay private."""
    caplog.set_level(logging.INFO)
    service, native, core = configured(image)
    owner = uuid4()
    result = await service.answer(owner, RAW, "png", "PRIVATE-QUESTION-CANARY")
    assert (
        result.owner_id == owner
        and result.source_sha256 == image.source_sha256
        and result.normalized_sha256 == image.png_sha256
    )
    assert (
        result.confidence is None
        and not result.persisted
        and not result.semantic_validation
    )
    assert len(native.calls) == len(core.calls) == service.quota.total == 1
    assert (
        set(core.calls[0]) == {"image", "question"} and core.calls[0]["image"] is image
    )
    assert "PRIVATE-QUESTION-CANARY" not in caplog.text and str(
        owner
    ) not in caplog.text + repr(result)
    assert not service.operations and not service.admission.locked()
    await service.shutdown()
    assert not core.closing


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", ["owner", "source", "suffix", "question", "closed", "normalizer", "core"]
)
async def test_invalid_input_disabled_and_closed_operations_have_zero_native_model_or_quota_effects(
    image, fault
):
    """Reject inert requests before the first resource admission without a path, URL or remote model option."""
    service, native, core = configured(image)
    owner, raw, suffix, question = uuid4(), RAW, "png", "Question"
    if fault == "owner":
        owner = "forged"
    elif fault == "source":
        raw = "https://private.invalid/image.png"
    elif fault == "suffix":
        suffix = "svg"
    elif fault == "question":
        question = "\x00private"
    elif fault == "closed":
        await service.shutdown()
    elif fault == "normalizer":
        service.normalizer = None
    elif fault == "core":
        service.inference = None
    with pytest.raises(ImageChatError):
        await service.answer(owner, raw, suffix, question)
    assert not native.calls and not core.calls and service.quota.total == 0


@pytest.mark.asyncio
async def test_invalid_normalized_source_refuses_before_model_disclosure(image):
    """Check complete source/PNG identity after isolated work instead of trusting an arbitrary normalizer payload."""
    service, native, core = configured(replace(image, source_sha256="0" * 64))
    with pytest.raises(ImageChatError, match="image_chat_invalid_image"):
        await service.answer(uuid4(), RAW, "png", "Question")
    assert len(native.calls) == service.quota.total == 1 and not core.calls
    assert not service.operations and not service.admission.locked()


@pytest.mark.asyncio
async def test_failed_answer_charges_each_attempt_and_caps_owner_without_refund(image):
    """Keep invalid complete replies as charged failures and reject the fifth request before native/model work."""
    service, native, core = configured(image)
    owner = uuid4()
    core.result = completion("{}")
    for _ in range(4):
        with pytest.raises(ImageChatError, match="image_chat_invalid_result"):
            await service.answer(owner, RAW, "png", "Question")
    with pytest.raises(ImageChatError, match="image_chat_rate_limited"):
        await service.answer(owner, RAW, "png", "Question")
    assert len(native.calls) == len(core.calls) == service.quota.total == 4


@pytest.mark.asyncio
async def test_independent_global_quota_is_bounded_across_explicit_current_operation_owners(
    image,
):
    """Cap four distinct current-operation owners without creating a retained image history or refunding completed attempts."""
    service, native, core = configured(image)
    for _ in range(4):
        owner = uuid4()
        for _ in range(4):
            await service.answer(owner, RAW, "png", "Question")
    with pytest.raises(ImageChatError, match="image_chat_rate_limited"):
        await service.answer(uuid4(), RAW, "png", "Question")
    assert (
        service.quota.total == len(core.calls) == len(native.calls) == 16
        and len(service.quota.owners) == 4
    )


@pytest.mark.asyncio
async def test_repeated_native_cancellation_keeps_thread_source_and_admission_until_real_ack(
    image, monkeypatch
):
    """Do not cancel a to_thread future and lose the native worker when the caller repeats cancellation."""
    service, native, core = configured(image)
    entered, release, cleaned = threading.Event(), threading.Event(), threading.Event()

    def held(raw, suffix):
        """Keep a finite real thread active until its explicit acknowledgment releases native ownership."""
        entered.set()
        try:
            assert release.wait(2)
            return image
        finally:
            cleaned.set()

    monkeypatch.setattr(native, "normalize", held)
    active = asyncio.create_task(service.answer(uuid4(), RAW, "png", "Question"))
    try:
        await wait_entered(entered)
        active.cancel()
        await asyncio.sleep(0.01)
        active.cancel()
        with pytest.raises(ImageChatError, match="image_chat_busy"):
            await service.answer(uuid4(), RAW, "png", "Question")
        assert not active.done() and not cleaned.is_set() and not core.calls
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await active
    assert (
        cleaned.is_set() and not service.operations and not service.admission.locked()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", ["NATIVE_SECONDS", "TOTAL_SECONDS"])
async def test_native_deadline_joins_real_thread_before_releasing_admission(
    image, monkeypatch, budget
):
    """Bound the stage while still waiting for actual blocking cleanup instead of returning a false late success."""
    service, native, core = configured(image)
    cleaned = threading.Event()

    def slow(raw, suffix):
        """Model a finite real native task whose resource acknowledgment follows the async deadline."""
        try:
            time.sleep(0.04)
            return image
        finally:
            cleaned.set()

    monkeypatch.setattr(native, "normalize", slow)
    monkeypatch.setattr(module, budget, 0.01)
    with pytest.raises(
        ImageChatError,
        match="image_chat_native_timeout"
        if budget == "NATIVE_SECONDS"
        else "image_chat_timeout",
    ):
        await service.answer(uuid4(), RAW, "png", "Question")
    assert (
        cleaned.is_set()
        and not core.calls
        and not service.operations
        and not service.admission.locked()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("suppress", [False, True])
async def test_model_stage_deadline_closes_backend_and_refuses_suppressed_late_answer(
    image, monkeypatch, suppress
):
    """Require cleanup and no successful publication after a model consumes its stage cancellation."""
    service, native, core = configured(image)
    cleaned = asyncio.Event()

    async def held(**options):
        """Hold one authored model request until the host deadline while recording cleanup acknowledgment."""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if suppress:
                return core.result
            raise
        finally:
            cleaned.set()

    monkeypatch.setattr(core, "complete_image", held)
    monkeypatch.setattr(module, "MODEL_SECONDS", 0.01)
    with pytest.raises(ImageChatError, match="image_chat_model_timeout"):
        await service.answer(uuid4(), RAW, "png", "Question")
    assert (
        cleaned.is_set() and not service.operations and not service.admission.locked()
    )


@pytest.mark.asyncio
async def test_shutdown_joins_active_model_preserves_other_tasks_and_does_not_close_shared_core(
    image, monkeypatch
):
    """Hold admission through model cancellation cleanup and leave unrelated operations alone during shutdown."""
    service, native, core = configured(image)
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def held(**options):
        """Expose a controlled in-flight model resource whose cleanup completes only after explicit release."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    monkeypatch.setattr(core, "complete_image", held)
    active = asyncio.create_task(service.answer(uuid4(), RAW, "png", "Question"))
    unrelated = asyncio.create_task(asyncio.Event().wait())
    await entered.wait()
    closing = asyncio.create_task(service.shutdown())
    await cleanup.wait()
    assert service.closing and not closing.done() and not unrelated.done()
    with pytest.raises(ImageChatError, match="image_chat_closed"):
        await service.answer(uuid4(), RAW, "png", "Question")
    release.set()
    await closing
    assert (
        active.cancelled()
        and not service.operations
        and not service.admission.locked()
        and not core.closing
    )
    unrelated.cancel()
    with pytest.raises(asyncio.CancelledError):
        await unrelated


@pytest.mark.asyncio
async def test_swallowed_caller_cancellation_cannot_publish_late_model_answer(
    image, monkeypatch
):
    """Keep caller cancellation terminal even when the model returns authored valid data after consuming it."""
    service, native, core = configured(image)
    entered = asyncio.Event()

    async def suppress(**options):
        """Return authored valid data only after the nested operation receives its cancellation."""
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return core.result

    monkeypatch.setattr(core, "complete_image", suppress)
    active = asyncio.create_task(service.answer(uuid4(), RAW, "png", "Question"))
    await entered.wait()
    active.cancel()
    with pytest.raises(asyncio.CancelledError):
        await active
    assert not service.operations and not service.admission.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["native", "model"])
async def test_private_backend_errors_are_finite_and_release_ownership(
    image, monkeypatch, stage
):
    """Discard arbitrary native/model exception text while retaining a charged attempt and joined resource state."""
    service, native, core = configured(image)

    def native_failure(raw, suffix):
        """Inject a private native exception without external effects."""
        raise RuntimeError("PRIVATE-BACKEND-CANARY")

    async def model_failure(**options):
        """Inject a private model exception without external effects."""
        raise RuntimeError("PRIVATE-BACKEND-CANARY")

    monkeypatch.setattr(
        native, "normalize", native_failure
    ) if stage == "native" else monkeypatch.setattr(
        core, "complete_image", model_failure
    )
    with pytest.raises(ImageChatError) as error:
        await service.answer(uuid4(), RAW, "png", "Question")
    assert "PRIVATE-BACKEND-CANARY" not in str(error.value) and service.quota.total == 1
    assert not service.operations and not service.admission.locked()
    logging.getLogger(__name__).info(
        "image_chat_lifecycle_failure_verified stage=%s", stage
    )
