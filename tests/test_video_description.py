"""Test owner/source/PTS-bound sparse video descriptions and joined native/model lifecycle without model inference."""

import asyncio
import logging
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

import src.application.services.video_description as module
from src.application.ports.video_description import VideoDescription
from src.application.ports.vision_chat import ImageChatReply
from src.application.services.ocr_contract import OCR_VERSION
from src.application.services.video_description import (
    VideoDescriptionError,
    VideoDescriptionService,
)
from src.application.services.vision_chat_policy import digest
from src.infrastructure.video_sampler import NativeVideoSampler

RAW = Path("tests/fixtures/video/stages.mkv").read_bytes()
MODEL = "fixture-core"
QUESTION = "PRIVATE-VISUAL-QUESTION"


@pytest.fixture(scope="module")
def sample():
    """Acquire one real typed three-frame video sample for controlled composition dependency tests."""
    return NativeVideoSampler().sample(RAW, (0, 1000, 2000))


class Sampler:
    """Record explicit native sampling requests without spawning additional decoder operations."""

    def __init__(self, value):
        """Bind immutable actual sample metadata and an empty call ledger."""
        self.value, self.calls = value, []

    def sample(self, raw, targets):
        """Record full explicit input/schedule before returning a controlled typed dependency result."""
        self.calls.append((raw, targets))
        return self.value


class Vision:
    """Return authored source-bound image replies while recording only current-operation calls."""

    def __init__(self):
        """Initialize a shared unclosed dependency and complete finite call ledger."""
        self.calls, self.closing = [], False

    async def answer(self, owner, raw, suffix, question):
        """Build one unverified ephemeral source/question-bound reply without a backend or temporal inference."""
        self.calls.append((owner, raw, suffix, question))
        return ImageChatReply(
            owner,
            digest(question.encode()),
            digest(raw),
            digest(raw),
            960,
            360,
            OCR_VERSION,
            MODEL,
            "Visible frame",
            (),
            datetime.now(UTC),
        )


def configured(sample):
    """Compose the new service with externally shared controlled dependencies and the unchanged actual native sample."""
    native, vision = Sampler(sample), Vision()
    return (
        VideoDescriptionService(sampler=native, vision=vision, expected_model=MODEL),
        native,
        vision,
    )


@pytest.mark.asyncio
async def test_complete_clip_binds_all_timestamps_and_pixels_without_motion_audio_or_persistence_claim(
    sample, caplog
):
    """Retain host PTS, source/owner provenance and all three complete replies while routine logs omit question/pixels."""
    caplog.set_level(logging.INFO)
    service, native, vision = configured(sample)
    owner = uuid4()
    result = await service.describe(owner, RAW, (0, 1000, 2000), QUESTION)
    assert type(result) is VideoDescription and result.owner_id == owner
    assert result.source_sha256 == digest(RAW) and result.question_sha256 == digest(
        QUESTION.encode()
    )
    assert [f.pts for f in result.frames] == [0, 1000, 2000]
    assert [f.image_sha256 for f in result.frames] == [
        f.png_sha256 for f in sample.frames
    ]
    assert [f.relative_time_num for f in result.frames] == [0, 1, 2]
    assert (
        result.observed_frames_only
        and not result.continuous_motion_verified
        and not result.audio_transcribed
    )
    assert (
        not result.persisted
        and not result.semantic_validation
        and result.confidence is None
    )
    assert len(native.calls) == service.quota.total == 1 and len(vision.calls) == 3
    assert QUESTION not in caplog.text and str(owner) not in caplog.text + repr(result)
    assert not service.operations and not service.admission.locked()
    await service.shutdown()
    assert not vision.closing


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "raw",
        "targets",
        "question",
        "closed",
        "sampler",
        "vision",
        "vision_closed",
    ],
)
async def test_invalid_disabled_closed_requests_do_not_sample_disclose_or_charge(
    sample, fault
):
    """Reject inert operations before native or private image/model activity begins."""
    service, native, vision = configured(sample)
    owner, raw, targets, question = uuid4(), RAW, (0, 1000, 2000), QUESTION
    if fault == "owner":
        owner = "forged"
    elif fault == "raw":
        raw = "https://private.invalid/video"
    elif fault == "targets":
        targets = (True,)
    elif fault == "question":
        question = "\x00private"
    elif fault == "closed":
        await service.shutdown()
    elif fault == "sampler":
        service.sampler = None
    elif fault == "vision":
        service.vision = None
    elif fault == "vision_closed":
        vision.closing = True
    with pytest.raises(VideoDescriptionError):
        await service.describe(owner, raw, targets, question)
    assert not native.calls and not vision.calls and service.quota.total == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", ["source", "pts", "frame_hash", "persisted", "frame_count"]
)
async def test_invalid_native_sample_fails_before_first_image_disclosure(sample, fault):
    """Validate complete native source/timing/hash/retention metadata before disclosing any frame pixels."""
    value = sample
    if fault == "source":
        value = replace(sample, source_sha256="0" * 64)
    elif fault == "pts":
        value = replace(
            sample, frames=(replace(sample.frames[0], pts=500), *sample.frames[1:])
        )
    elif fault == "frame_hash":
        value = replace(
            sample,
            frames=(replace(sample.frames[0], png_sha256="0" * 64), *sample.frames[1:]),
        )
    elif fault == "persisted":
        value = replace(sample, persisted=True)
    elif fault == "frame_count":
        value = replace(sample, frames=sample.frames[:2])
    service, native, vision = configured(value)
    with pytest.raises(VideoDescriptionError, match="video_description_invalid_sample"):
        await service.describe(uuid4(), RAW, (0, 1000, 2000), QUESTION)
    assert len(native.calls) == service.quota.total == 1 and not vision.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", uuid4()),
        ("source_sha256", "0" * 64),
        ("question_sha256", "0" * 64),
        ("model_id", "foreign"),
        ("processor", "foreign"),
        ("persisted", True),
        ("semantic_validation", True),
        ("confidence", 0.9),
        ("answer", "bad\x00private"),
        ("uncertainties", ["mutable"]),
        ("width", 1),
        ("normalized_sha256", "invalid"),
        ("model_attempts", 2),
    ],
)
async def test_bad_second_frame_reply_never_publishes_partial_success(
    sample, field, value
):
    """Stop at a bad second reply instead of returning a partial completed clip or starting a third disclosure."""
    service, native, vision = configured(sample)
    original = vision.answer

    async def altered(*args):
        """Corrupt one complete authored second-frame dependency response without touching its first reply."""
        answer = await original(*args)
        return replace(answer, **{field: value}) if len(vision.calls) == 2 else answer

    vision.answer = altered
    with pytest.raises(VideoDescriptionError, match="video_description_invalid_answer"):
        await service.describe(uuid4(), RAW, (0, 1000, 2000), QUESTION)
    assert len(vision.calls) == 2 and service.quota.total == 1
    assert not service.operations and not service.admission.locked()


@pytest.mark.asyncio
async def test_failed_clips_charge_quota_without_refund_before_fifth_native_operation(
    sample,
):
    """Keep failed complete attempts charged and prevent a fifth native dispatch for the same owner in one window."""
    service, native, vision = configured(replace(sample, source_sha256="0" * 64))
    owner = uuid4()
    for _ in range(4):
        with pytest.raises(VideoDescriptionError):
            await service.describe(owner, RAW, (0, 1000, 2000), QUESTION)
    with pytest.raises(VideoDescriptionError, match="video_description_rate_limited"):
        await service.describe(owner, RAW, (0, 1000, 2000), QUESTION)
    assert len(native.calls) == service.quota.total == 4 and not vision.calls


async def entered(event):
    """Wait finitely for an owned test thread without creating an unjoined blocking waiter."""
    async with asyncio.timeout(2):
        while not event.is_set():
            await asyncio.sleep(0.001)


@pytest.mark.asyncio
async def test_repeated_cancel_keeps_native_thread_and_admission_until_actual_cleanup(
    sample,
):
    """Retain native thread/source lifetime through repeated cancellation and refuse overlapping work without charging it."""
    service, native, vision = configured(sample)
    started, release, cleaned = threading.Event(), threading.Event(), threading.Event()

    def held(raw, targets):
        """Hold a finite actual thread until explicit acknowledgement closes its controlled native lifetime."""
        started.set()
        try:
            assert release.wait(2)
        finally:
            cleaned.set()
        return sample

    native.sample = held
    task = asyncio.create_task(
        service.describe(uuid4(), RAW, (0, 1000, 2000), QUESTION)
    )
    try:
        await entered(started)
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.01)
        assert (
            not task.done()
            and service.admission.locked()
            and service.operations
            and not cleaned.is_set()
        )
        with pytest.raises(VideoDescriptionError, match="video_description_busy"):
            await service.describe(uuid4(), RAW, (0, 1000, 2000), QUESTION)
        assert service.quota.total == 1
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        cleaned.is_set()
        and not vision.calls
        and not service.operations
        and not service.admission.locked()
    )


@pytest.mark.asyncio
async def test_shutdown_joins_own_model_work_leaves_shared_dependency_and_unrelated_task(
    sample,
):
    """Shutdown must await cancellation acknowledgment while retaining unrelated tasks and shared vision lifetime."""
    service, native, vision = configured(sample)
    started, release = asyncio.Event(), asyncio.Event()
    original = vision.answer

    async def held(*args):
        """Suppress one cancellation only until a finite controlled model cleanup acknowledgement is available."""
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        return await original(*args)

    vision.answer = held
    unrelated = asyncio.create_task(asyncio.sleep(0.2))
    task = asyncio.create_task(
        service.describe(uuid4(), RAW, (0, 1000, 2000), QUESTION)
    )
    await asyncio.wait_for(started.wait(), 2)
    closing = asyncio.create_task(service.shutdown())
    await asyncio.sleep(0.01)
    assert (
        not closing.done() and service.admission.locked() and not unrelated.cancelled()
    )
    release.set()
    await closing
    with pytest.raises(asyncio.CancelledError):
        await task
    await unrelated
    assert (
        len(vision.calls) == 1
        and not vision.closing
        and service.closing
        and not service.operations
    )


@pytest.mark.asyncio
async def test_total_timeout_refuses_suppressed_late_answer_and_later_frames(
    sample, monkeypatch
):
    """Reject a late result even when an injected vision port suppresses its deadline cancellation."""
    service, native, vision = configured(sample)
    original = vision.answer

    async def late(*args):
        """Return an authored late image reply after explicitly suppressing the timeout cancellation."""
        try:
            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        return await original(*args)

    vision.answer = late
    monkeypatch.setattr(module, "TOTAL_SECONDS", 0.02)
    with pytest.raises(VideoDescriptionError, match="video_description_timeout"):
        await service.describe(uuid4(), RAW, (0, 1000, 2000), QUESTION)
    assert (
        len(vision.calls) == 1
        and not service.operations
        and not service.admission.locked()
    )


@pytest.mark.asyncio
async def test_native_deadline_joins_real_thread_without_late_model_dispatch(
    sample, monkeypatch
):
    """Expire native work while retaining its actual thread until acknowledged cleanup, then reject rather than disclose frames."""
    service, native, vision = configured(sample)
    cleaned = threading.Event()

    def delayed(raw, targets):
        """Finish a finite controlled native lifetime after the service deadline without losing its ownership."""
        cleaned.wait(0.04)
        cleaned.set()
        return sample

    native.sample = delayed
    monkeypatch.setattr(module, "NATIVE_SECONDS", 0.01)
    with pytest.raises(VideoDescriptionError, match="video_description_native_timeout"):
        await service.describe(uuid4(), RAW, (0, 1000, 2000), QUESTION)
    assert (
        cleaned.is_set()
        and not vision.calls
        and not service.operations
        and not service.admission.locked()
    )


@pytest.mark.asyncio
async def test_native_failure_is_sanitized_and_admission_released(sample):
    """Retain a charged native failure without leaking raw backend error text or starting any model call."""
    service, native, vision = configured(sample)

    def failed(raw, targets):
        """Raise a controlled private decoder diagnostic to exercise finite boundary sanitization."""
        raise RuntimeError("PRIVATE-DECODER-DETAIL")

    native.sample = failed
    with pytest.raises(
        VideoDescriptionError, match="video_description_native_failed"
    ) as error:
        await service.describe(uuid4(), RAW, (0, 1000, 2000), QUESTION)
    assert "PRIVATE-DECODER-DETAIL" not in str(error.value) and not vision.calls
    assert (
        service.quota.total == 1
        and not service.operations
        and not service.admission.locked()
    )


@pytest.mark.asyncio
async def test_independent_clip_global_quota_caps_before_seventeenth_native_attempt(
    sample,
):
    """Bound four owners with failed no-refund attempts before another owner can start a seventeenth clip."""
    service, native, vision = configured(replace(sample, source_sha256="0" * 64))
    for _ in range(4):
        owner = uuid4()
        for _ in range(4):
            with pytest.raises(VideoDescriptionError):
                await service.describe(owner, RAW, (0, 1000, 2000), QUESTION)
    with pytest.raises(VideoDescriptionError, match="video_description_rate_limited"):
        await service.describe(uuid4(), RAW, (0, 1000, 2000), QUESTION)
    assert len(native.calls) == service.quota.total == 16 and not vision.calls


@pytest.mark.asyncio
async def test_unstarted_owned_coroutine_is_closed_on_task_creation_failure(
    sample, monkeypatch
):
    """Release admission and close the unstarted native/model coroutine when asyncio task ownership cannot be established."""
    import src.application.services.web_fetch_tasks as tasks

    service, native, vision = configured(sample)

    def failed(pending):
        """Refuse task creation before any native thread or private model disclosure begins."""
        raise RuntimeError("PRIVATE-TASK-FAILURE")

    monkeypatch.setattr(tasks, "create_task", failed)
    with pytest.raises(VideoDescriptionError, match="video_description_internal"):
        await service.describe(uuid4(), RAW, (0, 1000, 2000), QUESTION)
    assert (
        not native.calls
        and not vision.calls
        and not service.operations
        and not service.admission.locked()
    )


@pytest.mark.asyncio
async def test_naive_reply_clock_does_not_publish_a_completed_clip(sample):
    """Reject invalid trusted response UTC rather than silently attaching timezone-free provenance to a complete clip."""
    service, native, vision = configured(sample)

    def naive_clock():
        """Return a deliberately timezone-free trusted-clock observation for rejection testing."""
        return datetime(2026, 10, 22)

    service.utcnow = naive_clock
    with pytest.raises(VideoDescriptionError, match="video_description_invalid_answer"):
        await service.describe(uuid4(), RAW, (0, 1000, 2000), QUESTION)
    assert len(vision.calls) == 3 and not service.operations


@pytest.mark.parametrize("value", ["", "bad model", None, True])
def test_invalid_fixed_model_configuration_cannot_initialize_service(value):
    """Refuse ambiguous trusted model configuration before creating quota or native/model operations."""
    with pytest.raises(VideoDescriptionError):
        VideoDescriptionService(sampler=None, vision=None, expected_model=value)
