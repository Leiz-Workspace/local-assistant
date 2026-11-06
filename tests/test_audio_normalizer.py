"""Exercise actual isolated PCM normalization, decoded source clocks, whole-response bounds and native timeout ownership."""

import base64
import io
import json
import struct
import subprocess
import wave
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.infrastructure.audio_normalizer as module
from src.application.services.audio_contract import AudioError, resolve_audio
from src.application.services.vision_chat_policy import digest
from src.infrastructure.audio_normalizer import NativeAudioNormalizer


@pytest.fixture(scope="module")
def normalized():
    """Decode the original pinned official public speech fixture once for independent protocol controls."""
    raw = Path("tests/fixtures/audio/jfk.flac").read_bytes()
    return raw, NativeAudioNormalizer().normalize(raw)


def protocol(value):
    """Serialize a complete real typed normalized observation into the worker's exact JSON-shaped data contract."""
    result = asdict(value)
    result.pop("content_trust")
    result.pop("persisted")
    result["pcm_base64"] = base64.b64encode(result.pop("pcm_s16le")).decode()
    return result


def authored_wav(rate=16000, channels=1):
    """Create one second of public deterministic PCM data without reading codecs, microphones or external input."""
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(struct.pack("<h", 1000) * rate * channels)
    return output.getvalue()


def test_real_public_speech_repeat_has_exact_pcm_source_hash_and_known_clock(
    normalized, caplog
):
    """Verify exact reproducibility and original source/decoded-clock binding without claiming speech recognition or word timing."""
    caplog.set_level("INFO")
    raw, first = normalized
    second = NativeAudioNormalizer().normalize(raw)
    assert (
        first == second
        and first.source_sha256 == digest(raw)
        and first.pcm_sha256 == digest(first.pcm_s16le)
    )
    assert (
        first.source_codec == "flac"
        and first.sample_rate == 16000
        and first.channels == 1
    )
    assert (
        first.first_pts == 0
        and 16000 < first.sample_count <= 480000
        and len(first.pcm_s16le) == 2 * first.sample_count
    )
    assert first.content_trust == "untrusted" and not first.persisted
    assert "pcm_s16le=" not in repr(first) and "my fellow" not in caplog.text


@pytest.mark.parametrize("rate,channels", [(16000, 1), (44100, 2), (48000, 1)])
def test_real_authored_pcm_resampling_preserves_duration_and_explicit_original_clock(
    rate, channels
):
    """Normalize supported rates/channels with exact decoded duration and no origin guessed from average FPS or metadata dates."""
    raw = authored_wav(rate, channels)
    value = NativeAudioNormalizer().normalize(raw)
    assert (
        value.source_codec == "pcm_s16le"
        and value.source_sample_rate == rate
        and value.source_channels == channels
    )
    assert (
        value.source_sample_count == rate
        and value.sample_count == 16000
        and value.first_pts == 0
    )


def test_real_audio_from_existing_video_retains_same_whole_clip_source_hash():
    """Keep audio tied to the exact original video bytes instead of authorizing another media source with a matching name."""
    raw = Path("tests/fixtures/video/stages.mkv").read_bytes()
    value = NativeAudioNormalizer().normalize(raw)
    assert (
        value.source_sha256 == digest(raw)
        and value.source_sample_count == 48000
        and value.sample_count == 48000
    )
    assert (
        value.time_base_num == 1
        and value.time_base_den == 1000
        and value.first_pts == 0
    )


@pytest.mark.parametrize(
    "raw", [b"", bytearray(b"data"), "https://private.invalid/audio"]
)
def test_bad_explicit_input_has_no_native_dispatch(raw, monkeypatch):
    """Reject mutable bytes and locations before native execution or any external media read."""

    def forbidden(*args, **kwargs):
        """Fail immediately if invalid input reaches the native boundary."""
        pytest.fail("unexpected native dispatch")

    monkeypatch.setattr(module.subprocess, "run", forbidden)
    with pytest.raises(AudioError, match="audio_invalid_input"):
        NativeAudioNormalizer().normalize(raw)


@pytest.mark.parametrize(
    "raw", [b"not media", b"#EXTM3U\nhttps://private.invalid/audio", b"fLaCbroken"]
)
def test_real_malformed_and_playlist_input_fails_inside_networkless_decoder(raw):
    """Refuse unsupported source content rather than following remote playlist pointers or interpreting text as audio."""
    with pytest.raises(AudioError):
        NativeAudioNormalizer().normalize(raw)


@pytest.mark.parametrize(
    "path,replacement",
    [
        (("source_sha256",), "0" * 64),
        (("pcm_sha256",), "0" * 64),
        (("pcm_base64",), "invalid"),
        (("sample_count",), 1),
        (("sample_count",), True),
        (("sample_rate",), 8000),
        (("channels",), 2),
        (("source_sample_rate",), 0),
        (("source_channels",), 3),
        (("source_sample_count",), 1),
        (("time_base_den",), 0),
        (("first_pts",), None),
        (("first_pts",), True),
        (("processor",), "foreign"),
        (("source_codec",), "mp3"),
    ],
)
def test_complete_pcm_protocol_rejects_altered_hash_count_clock_and_codec(
    normalized, path, replacement
):
    """Refuse whole-response corruption instead of silently truncating PCM or repairing source-clock metadata."""
    value = protocol(normalized[1])
    value[path[0]] = replacement
    with pytest.raises(AudioError, match="audio_invalid_result"):
        resolve_audio(value, normalized[1].source_sha256)


def test_exact_protocol_reconstructs_the_original_immutable_audio(normalized):
    """Accept complete genuine native output while preserving all PCM bytes, source counts and rational timebase fields."""
    assert (
        resolve_audio(protocol(normalized[1]), normalized[1].source_sha256)
        == normalized[1]
    )


@pytest.mark.parametrize(
    "fault", ["timeout", "os_error", "crash", "oversize", "duplicate", "error_type"]
)
def test_parent_native_failures_and_json_tail_are_sanitized(
    normalized, monkeypatch, fault
):
    """Inspect scoped source/output policy and refuse incomplete or oversized replies without private backend diagnostics."""

    def failed(command, **options):
        """Observe complete source ownership and return one controlled bounded native failure."""
        assert options["stdin"].read() == normalized[0]
        assert (
            options["env"] == {}
            and options["close_fds"] is True
            and options["start_new_session"] is True
        )
        if fault == "timeout":
            raise subprocess.TimeoutExpired(command, 1)
        if fault == "os_error":
            raise OSError("PRIVATE-AUDIO-DETAIL")
        raw = (
            b"x" * (module.MAX_OUTPUT + 1)
            if fault == "oversize"
            else b'{"error":"audio_invalid_content","error":"audio_processing_unavailable"}'
            if fault == "duplicate"
            else b'{"error":[]}'
            if fault == "error_type"
            else b"{}"
        )
        options["stdout"].write(raw)
        return SimpleNamespace(returncode=1 if fault == "crash" else 0)

    monkeypatch.setattr(module.subprocess, "run", failed)
    with pytest.raises(AudioError) as error:
        NativeAudioNormalizer().normalize(normalized[0])
    assert "PRIVATE-AUDIO-DETAIL" not in str(error.value)


def test_real_timeout_reaps_namespace_and_nested_audio_child(normalized, monkeypatch):
    """Hold source lifetime until a deliberately stalled namespace and descendant are actually gone after timeout."""
    marker = "audio-timeout-" + uuid4().hex
    original = module.sandbox_command

    def stalled(arguments):
        """Retain original namespace policy around a finite intentionally stalled native child tree."""
        code = 'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)",sys.argv[1]]);time.sleep(30)'
        return original(["/venv/bin/python", "-c", code, marker])

    monkeypatch.setattr(module, "sandbox_command", stalled)
    monkeypatch.setattr(module, "WALL_SECONDS", 0.2)
    with pytest.raises(AudioError, match="audio_processing_timeout"):
        NativeAudioNormalizer().normalize(normalized[0])
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            assert marker.encode() not in path.read_bytes()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass


def test_official_fixture_provenance_hashes_and_original_license_are_preserved():
    """Bind the public speech input to its pinned source commit and retained complete license/test artifacts."""
    root = Path("tests/fixtures/audio")
    value = json.loads((root / "provenance.json").read_text())
    assert value["revision"] == "86098128c0b4f24f0e2aa2994de830614b474227"
    for name, row in value["files"].items():
        assert digest((root / name).read_bytes()) == row["sha256"]


@pytest.mark.parametrize("fault", ["gap", "too_long", "unsupported_codec"])
def test_real_discontinuous_long_or_unsupported_audio_is_not_assigned_a_fabricated_clock(
    tmp_path, fault
):
    """Reject actual sample timeline gaps, oversized duration and unsupported precision before publishing normalized audio."""
    path = tmp_path / "source.mkv"
    duration = "31" if fault == "too_long" else "2"
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
        f"sine=frequency=440:sample_rate=16000:duration={duration}",
    ]
    if fault == "gap":
        command += ["-af", "asetpts=PTS+gte(N\\,16000)/TB"]
    command += [
        "-c:a",
        "pcm_s24le" if fault == "unsupported_codec" else "pcm_s16le",
        "-y",
        str(path),
    ]
    subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=8,
    )
    with pytest.raises(AudioError) as error:
        NativeAudioNormalizer().normalize(path.read_bytes())
    assert (
        error.value.code == "audio_clock_unavailable"
        if fault == "gap"
        else error.value.code in {"audio_invalid_content", "audio_limits_exceeded"}
    )


def test_real_audio_worker_kernel_limits_readonly_source_and_no_host_credentials(
    normalized, monkeypatch
):
    """Inspect actual native entrypoint caps and readonly private paths before decoding the pinned speech fixture."""
    original = module.sandbox_command
    code = '''
"""Inspect native audio isolation before the original decoded-clock normalization."""
import os,resource
from src.infrastructure import audio_worker
original=audio_worker.process
def inspect():
    """Assert resource and filesystem guarantees then run the unchanged native audio process."""
    assert resource.getrlimit(resource.RLIMIT_AS)==(512*1024**2,512*1024**2)
    assert resource.getrlimit(resource.RLIMIT_CPU)==(8,9)
    assert resource.getrlimit(resource.RLIMIT_FSIZE)==(8*1024**2,8*1024**2)
    assert resource.getrlimit(resource.RLIMIT_NOFILE)==(32,32)
    assert resource.getrlimit(resource.RLIMIT_CORE)==(0,0)
    assert not os.path.exists('/app/data') and not os.path.exists('/home/korosaki-ryukai')
    assert not any('VAULT' in key or 'DATABASE' in key for key in os.environ)
    for path in ['/payload','/tmp/audio-probe']:
        try:descriptor=os.open(path,os.O_CREAT|os.O_WRONLY,0o600)
        except OSError:pass
        else:
            os.close(descriptor)
            raise AssertionError('writable parser source or tmp')
    return original()
audio_worker.process=inspect
audio_worker.main()
'''

    def observed(arguments):
        """Keep original native mounts and change only the test entrypoint to observe actual kernel limits."""
        return original(["/venv/bin/python", "-c", code])

    monkeypatch.setattr(module, "sandbox_command", observed)
    assert (
        NativeAudioNormalizer().normalize(normalized[0]).pcm_sha256
        == normalized[1].pcm_sha256
    )
