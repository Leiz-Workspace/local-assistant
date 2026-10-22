"""Guard synthetic-only public audio-review authority, PCM fidelity, bounded SSE and first-response retention without network access or neural inference."""

import io
import json
import signal
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.tts_public_audio_review import (
    BASE,
    PROMPT,
    SYSTEM,
    NoRedirect,
    PublicDemo,
    ReviewError,
    evaluate,
    extract_review,
    load_upload,
    parse_events,
    pcm_wave,
    sha,
    validate_packet,
    wall_limit,
)


def judgement():
    """Return one authored schema-valid AI observation without claiming a real audio evaluation."""
    return dict(
        presence="speech",
        language="english",
        naturalness="uncertain",
        confidence="low",
        artifacts=[],
        prosody="Authored unit fixture.",
        notes="No model inference in this test.",
    )


def complete_event(value=None):
    """Construct a Gradio-shaped complete response using an authored assistant JSON string."""
    return dict(
        event="complete",
        data=[
            None,
            None,
            None,
            None,
            [dict(role="assistant", content=json.dumps(value or judgement()))],
        ],
    )


def packet(tmp_path):
    """Create a complete five-file synthetic packet with exact no-gain PCM16 inspection metadata and parent-only labels."""
    inputs = tmp_path / "inputs"
    inputs.mkdir(mode=0o700)
    rows = []
    for index in range(1, 6):
        identity = f"input-{index:02d}"
        values = np.zeros(16000, dtype="<f4")
        raw = pcm_wave(values, 16000)
        path = inputs / (identity + ".wav")
        path.write_bytes(raw)
        path.chmod(0o600)
        rows.append(
            dict(
                id=identity,
                filename=identity + ".wav",
                upload_sha256=sha(raw),
                source_float32_sha256=sha(values.tobytes()),
                sample_rate=16000,
                sample_count=16000,
            )
        )
    value = dict(
        description="Authored test fixture; not actual audio evaluation.",
        kind="qualification",
        synthetic_audio_only=True,
        cases=rows,
    )
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(value))
    (tmp_path / "expectations.json").write_text(
        json.dumps(dict(cases=[dict(id=row["id"], presence="speech") for row in rows]))
    )
    return path, value


@pytest.mark.parametrize("rate", [16000, 22050, 24000])
def test_pcm_inspection_preserves_native_bits_timeline_and_declared_quantization(rate):
    """Verify no gain or trimming, native data unchanged and PCM16 error bounded to one half-level."""
    values = np.array([-1, -0.3, 0, 0.2, 1], dtype="<f4")
    original = values.tobytes()
    raw = pcm_wave(values, rate)
    with wave.open(io.BytesIO(raw), "rb") as stream:
        assert stream.getframerate() == rate and stream.getnframes() == len(values)
        assert stream.getnchannels() == 1 and stream.getsampwidth() == 2
        decoded = (
            np.frombuffer(stream.readframes(len(values)), dtype="<i2").astype(
                np.float64
            )
            / 32767
        )
    assert np.max(np.abs(decoded - values)) <= 0.5 / 32767
    assert values.tobytes() == original


@pytest.mark.parametrize(
    "values,rate",
    [
        (np.zeros(3, dtype=np.float64), 16000),
        (np.zeros((2, 2), dtype=np.float32), 16000),
        (np.array([np.nan], dtype=np.float32), 16000),
        (np.array([1.1], dtype=np.float32), 16000),
        (np.array([], dtype=np.float32), 16000),
        (np.zeros(1, dtype=np.float32), 44100),
    ],
)
def test_invalid_native_signal_is_not_repaired_for_upload(values, rate):
    """Refuse unsupported, nonfinite or excessive native samples instead of clipping or inventing usable input."""
    with pytest.raises(ReviewError):
        pcm_wave(values, rate)


@pytest.mark.parametrize(
    "fault",
    ["non_synthetic", "label", "missing", "duplicate", "traversal", "hash", "duration"],
)
def test_packet_refuses_foreign_labels_or_unbounded_authority(tmp_path, fault):
    """Prevent an accidental user-recording upload or leakage of parent-only source/candidate/expected class information."""
    _, value = packet(tmp_path)
    if fault == "non_synthetic":
        value["synthetic_audio_only"] = False
    elif fault == "label":
        value["cases"][0]["expected"] = "speech"
    elif fault == "missing":
        value["cases"].pop()
    elif fault == "duplicate":
        value["cases"][-1] = dict(value["cases"][0])
    elif fault == "traversal":
        value["cases"][0]["filename"] = "../foreign.wav"
    elif fault == "hash":
        value["cases"][0]["upload_sha256"] = "wrong"
    else:
        value["cases"][0]["sample_count"] = 16000 * 21
    with pytest.raises(ReviewError):
        validate_packet(value)


@pytest.mark.parametrize("fault", [None, "hash", "symlink", "permissions", "count"])
def test_uploaded_leaf_is_owned_exact_regular_and_complete(tmp_path, fault):
    """Bind exact uploaded WAV frames/rate/hash without adopting links or reading a source with changed publication permissions."""
    _, value = packet(tmp_path)
    row = value["cases"][0]
    path = tmp_path / "inputs" / row["filename"]
    if fault == "hash":
        row["upload_sha256"] = "0" * 64
    elif fault == "symlink":
        path.unlink()
        path.symlink_to("missing")
    elif fault == "permissions":
        path.chmod(0o644)
    elif fault == "count":
        row["sample_count"] -= 1
    if fault is None:
        assert load_upload(row, path.parent) == path.read_bytes()
    else:
        with pytest.raises((ReviewError, OSError)):
            load_upload(row, path.parent)


def test_bounded_SSE_only_extracts_final_text_and_never_downloads_generated_audio():
    """Ignore untrusted file components while preserving the final authored JSON and refusing to equate streaming fragments with completion."""
    event = complete_event()
    event["data"][4].append(
        dict(
            role="assistant",
            content=dict(
                component="audio", value=dict(path="https://foreign.invalid/audio.wav")
            ),
        )
    )
    raw = (
        "event: heartbeat\ndata: null\n\nevent: complete\ndata: "
        + json.dumps(event["data"])
        + "\n\n"
    ).encode()
    parsed = parse_events(raw)
    value, text = extract_review(parsed)
    assert value == judgement() and json.loads(text) == judgement()


@pytest.mark.parametrize(
    "fault",
    [
        "oversized",
        "line",
        "unknown",
        "error",
        "partial",
        "duplicate_complete",
        "shape",
        "fake_MOS",
        "long_notes",
    ],
)
def test_stream_or_judgement_corruption_never_counts_as_audio_acceptance(fault):
    """Refuse oversized streams, failed/incomplete events, forged human ratings and excessive reviewer content."""
    if fault in {"oversized", "line", "unknown"}:
        raw = (
            b"x" * (2 * 1024**2 + 1)
            if fault == "oversized"
            else b"event: generating\ndata: " + b"x" * 65537 + b"\n\n"
            if fault == "line"
            else b"event: foreign\ndata: null\n\n"
        )
        with pytest.raises((ReviewError, ValueError)):
            parse_events(raw)
        return
    events = [complete_event()]
    if fault == "error":
        events.append(dict(event="error", data="failed"))
    elif fault == "partial":
        events[0]["event"] = "generating"
    elif fault == "duplicate_complete":
        events *= 2
    elif fault == "shape":
        events[0]["data"] = []
    else:
        value = judgement()
        if fault == "fake_MOS":
            value["human_MOS"] = 5
        else:
            value["notes"] = "x" * 1201
        events = [complete_event(value)]
    with pytest.raises((ReviewError, ValueError)):
        extract_review(events)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/etc/passwd"),
        ("POST", "https://foreign.invalid/upload"),
        ("GET", "/gradio_api/upload"),
        ("PUT", "/gradio_api/upload"),
    ],
)
def test_transport_refuses_foreign_endpoints_before_network(method, path):
    """Keep API access within the exact ordinary published interface and never follow arbitrary remote paths."""
    with pytest.raises(ReviewError):
        PublicDemo().open(method, path)


def test_redirects_cannot_forward_the_audio():
    """Refuse adopting any response-selected destination even when an HTTP redirect would normally be followed."""
    with pytest.raises(ReviewError):
        NoRedirect().redirect_request(
            None, None, 307, "redirect", {}, "https://foreign.invalid"
        )


def test_fixed_origin_transport_contains_no_cookies_or_authorization():
    """Verify the client sends no owner credentials and never mutates the constant demo origin."""
    captured = []

    def opened(request, **kwargs):
        """Capture request authority without opening an actual connection."""
        captured.append(request)
        return SimpleNamespace()

    client = PublicDemo()
    client.opener = SimpleNamespace(open=opened)
    client.open("POST", "/gradio_api/upload", b"fixture", "application/octet-stream")
    request = captured[0]
    assert request.full_url == BASE + "/gradio_api/upload"
    assert not any(
        name.lower() in {"authorization", "cookie", "x-vault-token"}
        for name, value in request.header_items()
    )


def test_first_remote_failure_is_retained_without_fallback_or_retry(
    tmp_path, monkeypatch
):
    """Keep the first partial stream and error, stop subsequent requests and leave D70 incomplete."""
    path, value = packet(tmp_path)
    calls = []

    def fail(self, raw):
        """Retain one authored remote failure without a real service call."""
        calls.append(raw)
        self.raw_stream.extend(b"event: error\ndata: null\n\n")
        raise ReviewError("fixture_remote_error")

    monkeypatch.setattr(PublicDemo, "review", fail)
    output = tmp_path / "run"
    evaluate(path, output)
    result = json.loads((output / "result.json").read_text())
    assert len(calls) == result["observed"] == 1 and result["expected"] == 5
    assert result["D70_complete"] is False and result["qualification_passed"] is False
    assert (output / "input-01.sse").read_bytes().startswith(b"event: error")
    assert result["model_selected"] is None
    assert "TTS" not in PROMPT and SYSTEM


def test_wall_timer_is_owned_and_restored_without_overriding_an_existing_guard():
    """Ensure a completed request leaves no timer or signal-handler mutation in the caller."""
    original = signal.getsignal(signal.SIGALRM)
    with wall_limit(1):
        assert 0 < signal.getitimer(signal.ITIMER_REAL)[0] <= 1
        with pytest.raises(ReviewError, match="existing_wall_timer"):
            with wall_limit(2):
                pytest.fail("An existing deadline must not be replaced.")
    assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)
    assert signal.getsignal(signal.SIGALRM) == original


def test_complete_public_flow_uses_fresh_blind_state_and_retains_first_SSE(monkeypatch):
    """Verify exact public API argument order, opaque upload names and final text extraction without any actual request."""
    calls = []
    event = complete_event()
    stream = ("event: complete\ndata: " + json.dumps(event["data"]) + "\n\n").encode()

    def receipt(self, path, raw, content_type):
        """Return authored normal upload/event receipts and record the full transmitted scope."""
        calls.append((path, raw))
        return (
            ["/tmp/gradio/fixture/clip.wav"]
            if path.endswith("upload")
            else dict(event_id="a" * 32)
        )

    def opened(self, method, path, **kwargs):
        """Return a complete authored SSE stream rather than invoking the public service."""
        assert method == "GET" and path.endswith("a" * 32)
        return io.BytesIO(stream)

    monkeypatch.setattr(PublicDemo, "json_request", receipt)
    monkeypatch.setattr(PublicDemo, "open", opened)
    client = PublicDemo()
    result, text = client.review(pcm_wave(np.zeros(16000, dtype=np.float32), 16000))
    assert result == judgement() and bytes(client.raw_stream) == stream
    request = json.loads(calls[1][1])
    assert (
        request["data"][0] == PROMPT
        and request["data"][4] == []
        and request["data"][5] == SYSTEM
    )
    assert request["data"][1]["orig_name"] == "clip.wav" and len(request["data"]) == 7
    assert "session_hash" not in request


def test_event_receipt_survives_interrupted_stream_and_uses_server_owned_session(
    tmp_path, monkeypatch
):
    """Retain the exact owned event before GET and avoid the first observed wrong-session queue lookup without changing audio or prompt."""

    def receipt(self, path, raw, content_type):
        """Return authored upload/event receipts and require automatic event-linked session allocation."""
        if path.endswith("upload"):
            return ["/tmp/gradio/fixture/clip.wav"]
        assert set(json.loads(raw)) == {"data"}
        return dict(event_id="b" * 32)

    def interrupted(self, method, path, **kwargs):
        """Fail the stream only after its recoverable owned receipt has been published."""
        assert path.endswith("b" * 32)
        assert (tmp_path / "receipt.json").is_file()
        raise ReviewError("fixture_stream_interruption")

    monkeypatch.setattr(PublicDemo, "json_request", receipt)
    monkeypatch.setattr(PublicDemo, "open", interrupted)
    client = PublicDemo(tmp_path / "receipt.json")
    with pytest.raises(ReviewError):
        client.review(pcm_wave(np.zeros(16000, dtype=np.float32), 16000))
    value = json.loads((tmp_path / "receipt.json").read_text())
    assert value["event_id"] == value["session_hash"] == "b" * 32
