"""Exercise real isolated CFR/VFR video provenance, malformed-input refusal, complete schema bounds and native ownership."""

import base64
import hashlib
import io
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest
from PIL import Image

from scripts.generate_video_golden import generate
from src.application.services.video_contract import (
    MAX_SOURCE,
    VideoError,
    resolve_video,
    video_input,
)
from src.infrastructure.video_sampler import NativeVideoSampler


@pytest.fixture(scope="module")
def golden():
    """Decode one authored CFR audio-bearing fixture once for contract mutation controls."""
    raw = Path("tests/fixtures/video/stages.mkv").read_bytes()
    return raw, NativeVideoSampler().sample(raw, (0, 1000, 2000))


def protocol(sample):
    """Serialize exact original typed observations into the isolated JSON protocol for independent mutation checks."""
    rows = []
    for frame in sample.frames:
        row = asdict(frame)
        row["png_base64"] = base64.b64encode(row.pop("png")).decode()
        rows.append(row)
    metadata = asdict(sample.metadata)
    metadata["audio"] = list(metadata["audio"])
    return dict(
        source_sha256=sample.source_sha256,
        metadata=metadata,
        frames=rows,
        processor=sample.processor,
    )


def test_real_repeat_preserves_three_exact_frames_timestamps_and_audio_presence(
    golden, caplog
):
    """Verify decoded PTS, whole-source binding, reproducible RGB pixels and explicit synthetic audio without ASR claims."""
    caplog.set_level("INFO")
    raw, first = golden
    second = NativeVideoSampler().sample(raw, (0, 1000, 2000))
    assert first == second and first.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert first.metadata.frame_count == 3 and first.metadata.codec == "ffv1"
    assert (
        first.metadata.audio[0].codec == "pcm_s16le"
        and first.metadata.audio[0].sample_rate == 16000
    )
    assert [f.pts for f in first.frames] == [0, 1000, 2000]
    assert [(f.relative_time_num, f.relative_time_den) for f in first.frames] == [
        (0, 1),
        (1, 1),
        (2, 1),
    ]
    assert len({f.png_sha256 for f in first.frames}) == 3
    assert first.persisted is False and first.content_trust == "untrusted"
    assert "READY" not in caplog.text and "MOVING" not in caplog.text
    assert "png=" not in repr(first.frames[0]) and "png=" not in repr(first)
    with Image.open(io.BytesIO(first.frames[1].png)) as image:
        assert image.mode == "RGB" and image.size == (960, 360)


def test_real_vfr_nonzero_origin_uses_decoded_pts_not_index_or_average_fps(tmp_path):
    """Keep an original2s origin and select actual relative1.6s for target0.5s in a genuinely uneven timestamp sequence."""
    path = tmp_path / "vfr.mkv"
    subprocess.run(
        [
            "/usr/bin/ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-threads",
            "1",
            "-filter_threads",
            "1",
            "-f",
            "lavfi",
            "-i",
            "color=red:size=64x48:rate=10:duration=0.3",
            "-vf",
            "setpts=if(eq(N\\,0)\\,20\\,if(eq(N\\,1)\\,24\\,36))",
            "-fps_mode",
            "vfr",
            "-c:v",
            "ffv1",
            "-threads",
            "1",
            "-y",
            str(path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=8,
    )
    sample = NativeVideoSampler().sample(path.read_bytes(), (0, 300, 500))
    assert sample.metadata.origin_pts == 2000 and sample.metadata.frame_count == 3
    assert [f.pts for f in sample.frames] == [2000, 2400, 3600]
    assert [(f.relative_time_num, f.relative_time_den) for f in sample.frames] == [
        (0, 1),
        (2, 5),
        (8, 5),
    ]
    assert [f.frame_index for f in sample.frames] == [0, 1, 2]
    assert not sample.metadata.audio


@pytest.mark.parametrize(
    "raw,targets",
    [
        (b"", (0,)),
        (bytearray(b"video"), (0,)),
        (b"v", ()),
        (b"v", [0]),
        (b"v", (True,)),
        (b"v", (-1,)),
        (b"v", (30001,)),
        (b"v", (1, 0)),
        (b"v", (0, 0)),
        (b"v", (0, 1, 2, 3)),
    ],
)
def test_invalid_explicit_input_and_schedule_fail_before_native_dispatch(
    raw, targets, monkeypatch
):
    """Refuse locations, mutable input, booleans and invalid schedules without launching any native operation."""

    def forbidden(*args, **kwargs):
        """Fail if native work starts for invalid application input."""
        pytest.fail("unexpected native dispatch")

    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(VideoError, match="video_invalid_input"):
        NativeVideoSampler().sample(raw, targets)


def test_oversized_source_refuses_before_native_work():
    """Keep complete source admission bounded without clipping an oversized video."""
    with pytest.raises(VideoError, match="video_invalid_input"):
        video_input(b"x" * (MAX_SOURCE + 1), (0,))


@pytest.mark.parametrize(
    "raw",
    [b"not video", b"#EXTM3U\nhttp://private.invalid/secret", b"\x1aE\xdf\xa3broken"],
)
def test_real_broken_or_playlist_input_never_becomes_a_remote_media_request(raw):
    """Reject malformed/container-mismatched input in the networkless fixed-protocol namespace."""
    with pytest.raises(VideoError):
        NativeVideoSampler().sample(raw)


def test_real_target_after_last_decoded_frame_is_not_silently_duplicated(golden):
    """Reject relative2.5s when the final decoded frame is2s even though the container duration is3s."""
    with pytest.raises(VideoError, match="video_time_unavailable"):
        NativeVideoSampler().sample(golden[0], (2500,))


@pytest.mark.parametrize(
    "path,value",
    [
        (("processor",), "foreign"),
        (("source_sha256",), "0" * 64),
        (("metadata", "codec"), "foreign"),
        (("metadata", "duration_seconds"), float("nan")),
        (("metadata", "duration_seconds"), 31),
        (("metadata", "frame_count"), 901),
        (("metadata", "width"), True),
        (("metadata", "audio", 0, "sample_rate"), 0),
        (("metadata", "audio", 0, "channels"), 3),
        (("metadata", "time_base_den"), 0),
        (("frames", 0, "requested_ms"), True),
        (("frames", 1, "pts"), 0),
        (("frames", 1, "relative_time_num"), 100),
        (("frames", 1, "relative_time_den"), 0),
        (("frames", 1, "png_sha256"), "0" * 64),
        (("frames", 1, "png_base64"), "invalid"),
        (("frames", 1, "width"), 2000),
        (("frames", 1, "frame_index"), 900),
    ],
)
def test_complete_response_rejects_altered_geometry_hash_timing_bounds_and_audio(
    golden, path, value
):
    """Refuse a corrupted full protocol instead of publishing truncated or incorrectly timestamped frame bytes."""
    response = protocol(golden[1])
    target = response
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(VideoError, match="video_invalid_result"):
        resolve_video(response, golden[1].source_sha256, (0, 1000, 2000))


def test_exact_complete_protocol_reconstructs_original_immutable_port(golden):
    """Validate the full exact worker response rather than treating all malformed-protocol controls as sufficient acceptance."""
    assert (
        resolve_video(protocol(golden[1]), golden[1].source_sha256, (0, 1000, 2000))
        == golden[1]
    )


def test_generator_uses_only_authored_frames_and_synthetic_tone(tmp_path):
    """Recreate an audio-bearing authored source with the same decoded frame hashes and timestamps."""
    destination = tmp_path / "authored.mkv"
    generate(destination)
    generated = NativeVideoSampler().sample(destination.read_bytes(), (0, 1000, 2000))
    frozen = NativeVideoSampler().sample(
        Path("tests/fixtures/video/stages.mkv").read_bytes(), (0, 1000, 2000)
    )
    assert generated.metadata == frozen.metadata
    assert [f.png_sha256 for f in generated.frames] == [
        f.png_sha256 for f in frozen.frames
    ]


def test_actual_multiple_targets_may_explicitly_select_same_later_frame(golden):
    """Retain all distinct requested times when two correctly map to the same observed decoded PTS."""
    sample = NativeVideoSampler().sample(golden[0], (0, 100, 200))
    assert [f.frame_index for f in sample.frames] == [0, 1, 1]
    assert [f.pts for f in sample.frames] == [0, 1000, 1000]
    assert sample.frames[1].png_sha256 == sample.frames[2].png_sha256


def test_real_timeout_reaps_namespace_and_descendant(monkeypatch, golden):
    """Keep native ownership until a real stalled namespace and nested child no longer retain source descriptors."""
    from uuid import uuid4

    import src.infrastructure.video_sampler as module

    marker = "video-timeout-" + uuid4().hex
    original = module.sandbox_command

    def stalled(arguments):
        """Use unchanged production namespace mounts around a finite deliberately stalled child tree."""
        code = 'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)",sys.argv[1]]);time.sleep(30)'
        return original(["/venv/bin/python", "-c", code, marker])

    monkeypatch.setattr(module, "sandbox_command", stalled)
    monkeypatch.setattr(module, "WALL_SECONDS", 0.2)
    with pytest.raises(VideoError, match="video_processing_timeout"):
        module.NativeVideoSampler().sample(golden[0])
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            assert marker.encode() not in path.read_bytes()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass


def test_real_worker_limits_readonly_mounts_and_no_host_credentials(
    monkeypatch, golden
):
    """Inspect kernel and filesystem boundaries at the actual worker entry before normal decoding."""
    import src.infrastructure.video_sampler as module

    original = module.sandbox_command
    code = '''
"""Inspect D64 production kernel limits before decoding the authored public video."""
import os,resource
from src.infrastructure import video_worker
original=video_worker.process
def inspect(targets):
    """Verify the actual private namespace and source restrictions before calling the unchanged worker."""
    assert resource.getrlimit(resource.RLIMIT_AS)==(512*1024**2,512*1024**2)
    assert resource.getrlimit(resource.RLIMIT_CPU)==(8,9)
    assert resource.getrlimit(resource.RLIMIT_FSIZE)==(8*1024**2,8*1024**2)
    assert resource.getrlimit(resource.RLIMIT_NOFILE)==(32,32)
    assert resource.getrlimit(resource.RLIMIT_CORE)==(0,0)
    assert not os.path.exists('/app/data') and not os.path.exists('/home/korosaki-ryukai')
    assert not any('VAULT' in key or 'DATABASE' in key for key in os.environ)
    for path in ['/payload','/tmp/video-probe']:
        try:descriptor=os.open(path,os.O_CREAT|os.O_WRONLY,0o600)
        except OSError:pass
        else:
            os.close(descriptor)
            raise AssertionError('writable source or temporary filesystem')
    return original(targets)
video_worker.process=inspect
video_worker.main()
'''

    def inspected(arguments):
        """Retain original mount/network/PID policy while substituting only the test kernel observer."""
        return original(["/venv/bin/python", "-c", code, "[0]"])

    monkeypatch.setattr(module, "sandbox_command", inspected)
    assert module.NativeVideoSampler().sample(golden[0]).frames[0].pts == 0


@pytest.mark.parametrize(
    "fault",
    [
        "timeout",
        "os_error",
        "crash",
        "oversize",
        "duplicate",
        "nonfinite",
        "error_type",
        "unknown_error",
    ],
)
def test_parent_subprocess_failures_and_complete_protocol_are_finite(
    monkeypatch, golden, fault
):
    """Sanitize failures and reject altered tail content while inspecting the parent's scoped anonymous FD policy."""
    from types import SimpleNamespace

    import src.infrastructure.video_sampler as module

    def failed(command, **options):
        """Observe immutable source/anonymous output ownership without real decoder work."""
        assert (
            options["env"] == {}
            and options["close_fds"] is True
            and options["start_new_session"] is True
        )
        assert options["stdin"].read() == golden[0]
        if fault == "timeout":
            raise subprocess.TimeoutExpired(command, 1)
        if fault == "os_error":
            raise OSError("PRIVATE-ERROR-CANARY")
        raw = {
            "duplicate": b'{"error":"video_invalid_content","error":"video_processing_unavailable"}',
            "nonfinite": b'{"value":NaN}',
            "error_type": b'{"error":[]}',
            "unknown_error": b'{"error":"PRIVATE-ERROR-CANARY"}',
        }.get(fault, b"x" * (module.MAX_OUTPUT + 1) if fault == "oversize" else b"{}")
        options["stdout"].write(raw)
        return SimpleNamespace(returncode=1 if fault == "crash" else 0)

    monkeypatch.setattr(module.subprocess, "run", failed)
    with pytest.raises(VideoError) as error:
        module.NativeVideoSampler().sample(golden[0])
    assert "PRIVATE-ERROR-CANARY" not in str(error.value)


@pytest.mark.parametrize(
    "container,video_codec,audio_codec,expected_video,expected_audio",
    [
        ("mp4", "libx264", "aac", "h264", "aac"),
        ("webm", "libvpx-vp9", "libopus", "vp9", "opus"),
    ],
)
def test_real_supported_container_families_decode_actual_video_and_audio_metadata(
    tmp_path, container, video_codec, audio_codec, expected_video, expected_audio
):
    """Verify supported MP4/WebM decoder paths with real authored media rather than inferring support from codec names."""
    path = tmp_path / ("fixture." + container)
    subprocess.run(
        [
            "/usr/bin/ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-threads",
            "1",
            "-filter_threads",
            "1",
            "-f",
            "lavfi",
            "-i",
            "color=blue:size=64x48:rate=2:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000:duration=2",
            "-c:v",
            video_codec,
            "-threads",
            "1",
            "-c:a",
            audio_codec,
            "-t",
            "2",
            "-y",
            str(path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=8,
    )
    sample = NativeVideoSampler().sample(path.read_bytes(), (0, 500, 1000))
    assert (
        sample.metadata.codec == expected_video
        and sample.metadata.audio[0].codec == expected_audio
    )
    assert len(sample.frames) == 3 and sample.frames[0].relative_time_num == 0


@pytest.mark.parametrize(
    "fault", ["long_duration", "large_dimension", "too_many_frames", "multiple_video"]
)
def test_real_media_expansion_and_stream_ambiguity_refuse_before_publication(
    tmp_path, fault
):
    """Reject actual oversized timelines/geometry/frame counts and multiple video streams despite otherwise valid encoding."""
    source = {
        "long_duration": "color=red:size=16x16:rate=1:duration=31",
        "large_dimension": "color=red:size=2000x16:rate=1:duration=1",
        "too_many_frames": "color=red:size=16x16:rate=31:duration=30",
        "multiple_video": "color=red:size=16x16:rate=1:duration=1",
    }[fault]
    path = tmp_path / "limits.mkv"
    command = [
        "/usr/bin/ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-threads",
        "1",
        "-filter_threads",
        "1",
        "-f",
        "lavfi",
        "-i",
        source,
    ]
    if fault == "multiple_video":
        command += ["-map", "0:v", "-map", "0:v"]
    command += ["-c:v", "ffv1", "-threads", "1", "-y", str(path)]
    subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=8,
    )
    with pytest.raises(VideoError):
        NativeVideoSampler().sample(path.read_bytes())


@pytest.mark.parametrize("start", [None, -7])
def test_audio_origin_unknown_or_negative_is_preserved_in_its_own_clock(golden, start):
    """Keep unknown/negative audio origins explicit without converting them to video relative zero."""
    value = protocol(golden[1])
    value["metadata"]["audio"][0]["start_pts"] = start
    result = resolve_video(value, golden[1].source_sha256, (0, 1000, 2000))
    assert result.metadata.audio[0].start_pts == start
    assert result.metadata.audio[0].time_base_den == 1000


@pytest.mark.parametrize(
    "key,value", [("start_pts", True), ("time_base_den", 0), ("time_base_num", -1)]
)
def test_invalid_audio_clock_is_rejected(golden, key, value):
    """Refuse coerced or invalid audio clock metadata before downstream synchronized-media use."""
    response = protocol(golden[1])
    response["metadata"]["audio"][0][key] = value
    with pytest.raises(VideoError):
        resolve_video(response, golden[1].source_sha256, (0, 1000, 2000))
