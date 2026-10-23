"""Test the bounded specialist route with authored media and HTTP doubles, never real uploads, model weights or claimed listening results."""

import copy
import io
import json
import sys
from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import tts_speechjudge_review as specialist


def observation(winner="a"):
    """Author frontend-shaped score/rationale fixtures solely for transport and parser tests."""
    a, b = {"a": (8, 3), "b": (3, 8), "tie": (8, 8)}[winner]
    label = {"a": "Audio A Wins", "b": "Audio B Wins", "tie": "Tie"}[winner]
    summary = f"Result: {label}\nAudio A Avg Score: {a:.2f}\nAudio B Avg Score: {b:.2f}"
    raw = f"========== Generation 1/1 ==========\nScore A: {a}, Score B: {b}\nReasoning:\nAuthored fixture; not a real listening judgement. Output A: {a}, Output B: {b}.\n"
    return [dict(event="complete", data=[summary, raw])]


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    """Prepare eighteen temporary controls from two authored sine waves instead of accessing original smoke files."""
    project, root = tmp_path / "project", tmp_path / "owned"
    project.mkdir()
    root.mkdir()
    monkeypatch.setattr(specialist, "EXECUTION_ALLOWED", True)
    monkeypatch.setattr(specialist, "require_headroom", lambda: {})
    monkeypatch.setattr(specialist, "core_snapshot", lambda: dict(pid=1, start_ticks=1, command_sha256="authored"))
    monkeypatch.setattr(specialist, "inspect_interface", lambda: dict(description="Authored interface fixture, no HTTP"))
    for name in ["d70-qwen-smoke-first", "d70-piper-vi-smoke-first"]:
        directory = project / "data/backups" / name
        (directory / "generated").mkdir(parents=True)
        raw = (0.2 * np.sin(np.arange(16000) * 0.1)).astype("<f4").tobytes()
        (directory / "generated/source.f32").write_bytes(raw)
        (directory / "freeze.json").write_text(json.dumps(dict(request=dict(cases=[dict(id="authored", text="Neutral authored fixture.")]))))
        event = dict(id="authored", status="ok", audio=dict(raw_filename="source.f32", waveform_sha256=specialist.sha(raw), sample_count=16000, sample_rate=16000))
        (directory / "result.json").write_text(json.dumps(dict(events=[event])))
    for name in ["scripts/tts_speechjudge_review.py", "tests/test_tts_speechjudge_review.py", "scripts/tts_public_audio_review.py", "docs/ADR/105-proposed-specialist-public-auditory-review.md"]:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Authored frozen source fixture.")
    specialist.prepare_controls(root, project)
    packet = json.loads((root / "controls/packet.json").read_text())
    mapping = json.loads((root / "controls/parent-only.json").read_text())["cases"]
    return SimpleNamespace(root=root, project=project, packet=packet, mapping=mapping)


def fake_client(prepared, monkeypatch, mismatch=False):
    """Replace the network client with explicit first-result fixtures for stage retention/gate tests."""
    expected = {row["id"]: row["expected"] for row in prepared.mapping}

    class Client:
        """Emulate bounded raw SSE storage without creating a network connection."""

        def __init__(self, output):
            """Record the authored fixture client lifecycle with an empty initial stream."""
            self.raw_stream = b""
            self.output = output

        def compare(self, row, inputs):
            """Return one declared authored observation, optionally failing the very first control."""
            winner = expected[row["id"]]
            if mismatch:
                winner = "b" if winner == "a" else "a"
            events = observation(winner)
            self.raw_stream = ("event: complete\ndata: " + json.dumps(events[0]["data"]) + "\n\n").encode()
            specialist.publish_json(self.output / (row["id"] + ".receipt.json"), dict(description="Authored receipt fixture, no remote call.", event_id=specialist.sha(row["id"].encode())[:32], origin=specialist.ORIGIN))
            return specialist.parse_comparison(events)

    monkeypatch.setattr(specialist, "SpecialistDemo", Client)


def test_authored_control_balance_privacy_and_full_wav(prepared):
    """Verify all18controls, mirrored orientations, per-language ties, opaque fields and exact complete PCM16 receipt coverage."""
    assert Counter(row["expected"] for row in prepared.mapping) == Counter(a=8, b=8, tie=2)
    assert Counter(row["language"] for row in prepared.mapping) == Counter(en=9, vi=9)
    for row in prepared.packet["cases"]:
        assert set(row) == {"id", "text", "signals"}
        for signal in row["signals"]:
            raw = specialist.load_upload(signal, prepared.root / "controls/inputs")
            assert specialist.sha(raw) == signal["upload_sha256"]
    with pytest.raises(FileExistsError):
        specialist.prepare_controls(prepared.root, prepared.project)


@pytest.mark.parametrize("mutation", ["labels", "duplicate", "traversal", "text", "signal_id", "hash", "rate", "count", "coverage", "endpoint"])
def test_untrusted_packet_rejected(prepared, mutation):
    """Reject metadata leakage, traversal, unbounded text/media and caller-selected destination fields before transmission."""
    packet = copy.deepcopy(prepared.packet)
    row = packet["cases"][0]
    if mutation == "labels": row["expected"] = "a"
    elif mutation == "duplicate": packet["cases"][1] = copy.deepcopy(row)
    elif mutation == "traversal": row["signals"][0]["filename"] = "../private.wav"
    elif mutation == "text": row["text"] = "x" * 161
    elif mutation == "signal_id": row["signals"][0]["id"] = "other"
    elif mutation == "hash": row["signals"][0]["upload_sha256"] = "x" * 64
    elif mutation == "rate": row["signals"][0]["sample_rate"] = True
    elif mutation == "count": row["signals"][0]["sample_count"] = 10000000
    elif mutation == "coverage": packet["cases"].pop()
    else: packet["origin"] = "https://foreign.invalid"
    with pytest.raises(specialist.ReviewError):
        specialist.validate_packet(packet)


@pytest.mark.parametrize("winner", ["a", "b", "tie"])
def test_raw_first_rating_and_frontend_agree(winner):
    """Accept only consistent single-generation scores within the source-documented1to10range, never human MOS."""
    assert specialist.parse_comparison(observation(winner))["winner"] == winner


@pytest.mark.parametrize("mutation", ["error", "extra_complete", "generation", "score", "summary", "conclusion", "no_reason", "oversize"])
def test_repaired_incomplete_or_contradictory_output_rejected(mutation):
    """Refuse unbounded, contradictory, incomplete or multiple-generation results instead of choosing a favourable interpretation."""
    events = observation()
    if mutation == "error": events.append(dict(event="error", data="fixture"))
    elif mutation == "extra_complete": events.append(copy.deepcopy(events[0]))
    elif mutation == "generation": events[0]["data"][1] = events[0]["data"][1].replace("Generation 1/1", "Generation 1/5")
    elif mutation == "score": events[0]["data"][1] = events[0]["data"][1].replace("Score A: 8", "Score A: 11")
    elif mutation == "summary": events[0]["data"][0] = events[0]["data"][0].replace("Audio A Wins", "Audio B Wins")
    elif mutation == "conclusion": events[0]["data"][1] += "Output A: 2, Output B: 9."
    elif mutation == "no_reason": events[0]["data"][1] = events[0]["data"][1].replace("Reasoning:\n", "")
    else: events[0]["data"][1] = "x" * 60001
    with pytest.raises(specialist.ReviewError):
        specialist.parse_comparison(events)


def test_unapproved_route_blocks_before_paths_or_network(tmp_path, monkeypatch):
    """Block external evaluator execution without recipient consent even when a client object was retained earlier."""
    monkeypatch.setattr(specialist, "EXECUTION_ALLOWED", False)
    monkeypatch.setattr(sys, "argv", ["tts_speechjudge_review"])
    for action in [lambda: specialist.evaluate("controls", tmp_path, tmp_path), lambda: specialist.SpecialistDemo(tmp_path), lambda: specialist.main(), lambda: object.__new__(specialist.SpecialistDemo).open("POST", "/gradio_api/upload")]:
        with pytest.raises(specialist.ReviewError, match="specialist_campaign_not_approved"):
            action()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("controls_passed", [False, True])
def test_approved_main_reuses_first_packet_and_retires_scope(prepared, monkeypatch, controls_passed):
    """Reuse the already frozen local packet and run conditional review once without regeneration or further permission."""
    calls = []

    def forbidden_preparation():
        """Reject any attempt to regenerate the existing first control packet."""
        raise AssertionError("first_packet_must_be_reused")

    def evaluate_stage(kind):
        """Record the campaign sequence without transmitting audio or making provider requests."""
        calls.append(kind)
        return controls_passed

    def prepare_conditional():
        """Record conditional packet preparation without accessing original benchmark audio."""
        calls.append("prepare_review")

    monkeypatch.setattr(sys, "argv", ["tts_speechjudge_review"])
    monkeypatch.setattr(specialist, "ROOT", prepared.root)
    monkeypatch.setattr(specialist, "prepare_controls", forbidden_preparation)
    monkeypatch.setattr(specialist, "prepare_review", prepare_conditional)
    monkeypatch.setattr(specialist, "evaluate", evaluate_stage)
    monkeypatch.setattr(specialist.resource, "setrlimit", lambda *args: None)
    monkeypatch.setattr(specialist.os, "sched_setaffinity", lambda *args: None)
    specialist.main()
    assert calls == (["controls", "prepare_review", "review"] if controls_passed else ["controls"])
    assert specialist.EXECUTION_ALLOWED is False


@pytest.mark.parametrize("operation", ["main", "stage", "client", "retained_client"])
def test_consumed_actual_campaign_is_closed_by_current_policy(tmp_path, monkeypatch, operation):
    """Reject additional real campaign entry points under the retired default policy without monkeypatching its permission flag."""
    monkeypatch.setattr(sys, "argv", ["tts_speechjudge_review"])
    assert specialist.EXECUTION_ALLOWED is False
    actions = {
        "main": specialist.main,
        "stage": lambda: specialist.evaluate("controls", tmp_path, tmp_path),
        "client": lambda: specialist.SpecialistDemo(tmp_path),
        "retained_client": lambda: object.__new__(specialist.SpecialistDemo).open("POST", "/gradio_api/upload"),
    }
    with pytest.raises(specialist.ReviewError, match="campaign_not_approved"):
        actions[operation]()
    assert list(tmp_path.iterdir()) == []


def test_provider_error_inside_complete_event_is_not_a_quality_result(prepared, monkeypatch):
    """Retain a provider-shaped GPU failure wrapped in a complete SSE event without accepting it as a rating or invoking conditional review."""
    class Unavailable:
        """Emulate the public frontend's service-error envelope using authored local data only."""

        def __init__(self, output):
            """Store the owned evidence path and initialize the first raw buffer."""
            self.output, self.raw_stream = output, b""

        def compare(self, row, inputs):
            """Produce one source-shaped upstream error, not a listening judgement or network response."""
            events = [dict(event="complete", data=["System Error: 'GPU task aborted'", "Authored fixture: ZeroGPU worker error; no model score."])]
            self.raw_stream = ("event: complete\ndata: " + json.dumps(events[0]["data"]) + "\n\n").encode()
            specialist.publish_json(self.output / (row["id"] + ".receipt.json"), dict(description="Authored service-error fixture receipt, no network.", event_id="a" * 32, origin=specialist.ORIGIN))
            return specialist.parse_comparison(events)

    monkeypatch.setattr(specialist, "SpecialistDemo", Unavailable)
    assert not specialist.evaluate("controls", prepared.root, prepared.project)
    directory = prepared.root / "controls-first"
    result = json.loads((directory / "result.json").read_text())
    assert result["error_code"] == "specialist_first_generation" and result["observations"] == []
    assert result["controls_passed"] is False and specialist.EXECUTION_ALLOWED is False
    assert b"GPU task aborted" in (directory / "pair-01.sse").read_bytes()
    assert not (prepared.root / "review").exists()


def test_local_controls_need_no_external_recipient_permission(prepared, monkeypatch):
    """Allow reversible local control copies while proving no client is constructed and all outbound authority remains disabled."""
    def forbidden(*args, **kwargs):
        """Fail if local preparation creates a network client or requests an external interface."""
        raise AssertionError("local_preparation_must_not_contact_provider")
    monkeypatch.setattr(specialist, "EXECUTION_ALLOWED", False)
    monkeypatch.setattr(specialist, "SpecialistDemo", forbidden)
    monkeypatch.setattr(specialist, "inspect_interface", forbidden)
    root = prepared.root / "local_only"
    assert not root.exists()
    specialist.prepare_controls(root, prepared.project)
    packet = json.loads((root / "controls/packet.json").read_text())
    assert len(packet["cases"]) == 18 and specialist.EXECUTION_ALLOWED is False
    assert root.stat().st_mode & 0o777 == 0o700
    specialist.verify_prepared_controls(root)
    with pytest.raises(specialist.ReviewError, match="campaign_not_approved"):
        specialist.evaluate("controls", root, prepared.project)


def test_local_preparation_cannot_be_changed_before_first_request(prepared, monkeypatch):
    """Bind the later approved stage to the first local-only preparation rather than silently adopting changed target text."""
    path = prepared.root / "controls/packet.json"
    packet = json.loads(path.read_text())
    packet["cases"][0]["text"] = "A different authored fixture."
    path.write_text(json.dumps(packet))
    with pytest.raises(specialist.ReviewError, match="prepared_control_changed"):
        specialist.evaluate("controls", prepared.root, prepared.project)
    assert not (prepared.root / "controls-first").exists()


def test_first_control_failure_stops_and_retains_raw(prepared, monkeypatch):
    """Stop at the first wrong comparison, retain its raw SSE, leave common inputs absent and refuse first-directory reuse."""
    fake_client(prepared, monkeypatch, mismatch=True)
    assert not specialist.evaluate("controls", prepared.root, prepared.project)
    result = json.loads((prepared.root / "controls-first/result.json").read_text())
    assert result["error_code"] == "specialist_control_mismatch" and len(result["observations"]) == 1
    assert len(list((prepared.root / "controls-first").glob("*.sse"))) == 1
    with pytest.raises(specialist.ReviewError, match="qualification_gate"):
        specialist.require_qualification(prepared.root, prepared.project)
    assert specialist.EXECUTION_ALLOWED is False
    with pytest.raises(specialist.ReviewError, match="qualification_gate"):
        specialist.prepare_review(prepared.root, prepared.project)
    assert not (prepared.root / "review").exists()
    with pytest.raises(specialist.ReviewError, match="campaign_not_approved"):
        specialist.evaluate("controls", prepared.root, prepared.project)


@pytest.mark.parametrize("mutation", ["source", "packet", "flag", "raw"])
def test_first_gate_recomputed_before_common_access(prepared, monkeypatch, mutation):
    """Recompute all18first responses and immutable source/packet/parent bindings instead of trusting a stored positive flag."""
    fake_client(prepared, monkeypatch)
    assert specialist.evaluate("controls", prepared.root, prepared.project)
    specialist.require_qualification(prepared.root, prepared.project)
    if mutation == "source": (prepared.project / "scripts/tts_speechjudge_review.py").write_text("changed")
    elif mutation == "packet": (prepared.root / "controls/parent-only.json").write_text("{}")
    else:
        path = prepared.root / "controls-first/result.json"
        result = json.loads(path.read_text())
        if mutation == "flag": result["controls_passed"] = False
        else: result["observations"][0]["events"] = observation("a" if prepared.mapping[0]["expected"] != "a" else "b")
        path.write_text(json.dumps(result))
    with pytest.raises((specialist.ReviewError, KeyError)):
        specialist.require_qualification(prepared.root, prepared.project)


@pytest.mark.parametrize("mutation", ["summary_only", "judgement_only", "raw_stream", "receipt_origin", "duplicate_event", "observation_file", "artifact_coverage"])
def test_first_raw_receipts_and_summary_are_cross_checked(prepared, monkeypatch, mutation):
    """Reject stale or altered first evidence even when categorical winners and the stored positive control flag still agree."""
    fake_client(prepared, monkeypatch)
    assert specialist.evaluate("controls", prepared.root, prepared.project)
    directory = prepared.root / "controls-first"
    path = directory / "result.json"
    result = json.loads(path.read_text())
    first, second = prepared.packet["cases"][:2]
    identity = first["id"]
    if mutation == "summary_only":
        result["observations"][0]["events"][0]["data"][1] = result["observations"][0]["events"][0]["data"][1].replace("Authored fixture", "Changed fixture")
    elif mutation == "judgement_only":
        result["observations"][0]["judgement"]["raw_log"] += "Changed retained judgement."
    elif mutation == "raw_stream":
        (directory / (identity + ".sse")).write_bytes(b"event: complete\ndata: null\n\n")
    elif mutation in {"receipt_origin", "duplicate_event"}:
        receipt_name = (identity if mutation == "receipt_origin" else second["id"]) + ".receipt.json"
        receipt_path = directory / receipt_name
        receipt = json.loads(receipt_path.read_text())
        if mutation == "receipt_origin":
            receipt["origin"] = "https://foreign.invalid"
        else:
            receipt["event_id"] = specialist.sha(identity.encode())[:32]
        receipt_path.write_text(json.dumps(receipt))
        result["first_artifact_sha256"][receipt_name] = specialist.sha(receipt_path.read_bytes())
    elif mutation == "observation_file":
        observation_path = directory / (identity + ".json")
        retained = json.loads(observation_path.read_text())
        retained["judgement"]["raw_log"] += "Changed separate observation."
        observation_path.write_text(json.dumps(retained))
        result["first_artifact_sha256"][observation_path.name] = specialist.sha(observation_path.read_bytes())
    else:
        result["first_artifact_sha256"].pop(identity + ".sse")
    path.write_text(json.dumps(result))
    with pytest.raises(specialist.ReviewError):
        specialist.require_qualification(prepared.root, prepared.project)
    assert not (prepared.root / "review").exists()


def test_partial_first_stream_failure_retains_evidence_and_closes_scope(prepared, monkeypatch):
    """Preserve an interrupted stream before any parsed observation and block subsequent stages instead of retrying."""
    class Interrupted:
        """Emulate a first stream timeout without creating a socket or contacting the provider."""

        def __init__(self, output):
            """Start with an empty authored event buffer."""
            self.raw_stream = b""

        def compare(self, row, inputs):
            """Retain one incomplete generating event and simulate a transport timeout."""
            self.raw_stream = b"event: generating\ndata: null\n\n"
            raise TimeoutError("Authored timeout fixture, no network")

    monkeypatch.setattr(specialist, "SpecialistDemo", Interrupted)
    assert not specialist.evaluate("controls", prepared.root, prepared.project)
    directory = prepared.root / "controls-first"
    result = json.loads((directory / "result.json").read_text())
    assert result["error_code"] == "TimeoutError" and result["observations"] == []
    filename = prepared.packet["cases"][0]["id"] + ".sse"
    assert (directory / filename).read_bytes() == b"event: generating\ndata: null\n\n"
    assert result["first_artifact_sha256"][filename] == specialist.sha((directory / filename).read_bytes())
    assert specialist.EXECUTION_ALLOWED is False


def test_native_bf16_lower_bound_and_invalid_metadata():
    """Check analytic text-only storage accounting and prove the proposed7BnativeBF16text parameters alone exceed12GiB without weights."""
    config = dict(model_type="qwen2_5_omni_text", hidden_size=3584, intermediate_size=18944, vocab_size=152064, num_hidden_layers=28, num_attention_heads=28, num_key_value_heads=4, tie_word_embeddings=False)
    result = specialist.native_text_bf16_bound(config)
    assert result["text_parameters"] == 7615616512 and result["BF16_parameter_bytes"] == 15231233024
    assert result["BF16_parameter_bytes"] > 12 * 1024**3 and not result["measured_RAM"]
    for key, value in [("hidden_size", True), ("num_attention_heads", 27), ("tie_word_embeddings", None)]:
        with pytest.raises(specialist.ReviewError):
            specialist.native_text_bf16_bound(dict(config, **{key: value}))


def test_order_disagreement_is_retained_not_averaged():
    """Identify an original-output preference reversal across AB/BA without repairing scores or forcing a winner."""
    observations, mapping = [], []
    for number in range(12):
        a, b = f"original-a-{number}", f"original-b-{number}"
        for reverse in [False, True]:
            identity = f"pair-{len(mapping)+1:02d}"
            mapping.append(dict(id=identity, originals=[dict(original_id=value) for value in ([b, a] if reverse else [a, b])]))
            observations.append(dict(id=identity, judgement=dict(winner="b" if reverse else "a")))
    assert specialist.order_consistency(observations, mapping)["consistent_original_pairs"] == 12
    observations[1]["judgement"]["winner"] = "a"
    result = specialist.order_consistency(observations, mapping)
    assert result["consistent_original_pairs"] == 11 and result["inconsistent_original_pairs"] == [["original-a-0", "original-b-0"]]
    assert not result["scores_repaired_or_averaged"]


def test_exact_origin_transport_and_single_generation(prepared, monkeypatch):
    """Exercise the real multipart/simple-call/SSE client using bounded HTTP doubles with no external network."""
    output = prepared.root / "transport"
    output.mkdir()
    client = specialist.SpecialistDemo(output)
    requests = []

    class Opener:
        """Emulate only the normal fixed-origin upload/call/event paths and record exact request metadata."""

        def open(self, request, timeout):
            """Return source-shaped anonymous receipts and first-result SSE without credentials, redirects or model calls."""
            requests.append(request)
            assert request.full_url.startswith(specialist.ORIGIN + "/gradio_api/")
            assert "Authorization" not in request.headers and timeout == 20
            if request.full_url.endswith("/upload"):
                position = "a" if b'filename="clip-a.wav"' in request.data else "b"
                return io.BytesIO(json.dumps(["/tmp/gradio/opaque/clip-" + position + ".wav"]).encode())
            if request.get_method() == "POST":
                payload = json.loads(request.data)
                assert set(payload) == {"data"} and payload["data"][-1] == 1 and len(payload["data"]) == 4
                return io.BytesIO(b'{"event_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')
            return io.BytesIO(("event: complete\ndata: " + json.dumps(observation()[0]["data"]) + "\n\n").encode())

    client.opener = Opener()
    assert client.compare(prepared.packet["cases"][0], prepared.root / "controls/inputs")["winner"] == "a"
    assert len(requests) == 4
    for method, path in [("POST", "https://foreign.invalid"), ("GET", "/gradio_api/upload"), ("POST", "/queue/join"), ("GET", "/gradio_api/call/gradio_handler/../../private")]:
        with pytest.raises(specialist.ReviewError, match="endpoint_scope"):
            client.open(method, path)


def test_conditional_review_preserves_every_original_and_both_orders(prepared, monkeypatch):
    """Prepare all24outputs in24mirrored comparisons only after first18control success, retaining native and full diagnostic hashes."""
    fake_client(prepared, monkeypatch)
    assert specialist.evaluate("controls", prepared.root, prepared.project)
    original = prepared.project / "data/backups/d70-common-audio-diagnostics-first"
    (original / "generated").mkdir(parents=True)
    pending_directory = prepared.project / "data/backups/d70-tts-listening-review"
    pending_directory.mkdir()
    events, pending, expected = [], [], {}
    for language in ["en", "vi"]:
        for group in range(6):
            for candidate in ["candidate_a", "candidate_b"]:
                identity = f"{language}-{group}-{candidate}"
                raw = np.full(16000, (group + 1) / 100, dtype="<f4").tobytes()
                digest = specialist.sha(raw)
                expected[identity] = digest
                (original / "generated" / (identity + ".f32")).write_bytes(raw)
                events.append(dict(event="transformed", id=identity, asr=dict(waveform_sha256=digest, sample_count=16000, source_waveform_sha256=digest)))
                pending.append(dict(id=identity, candidate=candidate, language=language, authored_text=f"Neutral authored test {language} {group}.", native_waveform_sha256=digest, has_actually_listened=False, naturalness_judgement=None))
    (original / "result.json").write_text(json.dumps(dict(events=events)))
    pending_path = pending_directory / "review.pending.json"
    pending_path.write_text(json.dumps(dict(items=pending)))
    unchanged = pending_path.read_bytes()
    specialist.prepare_review(prepared.root, prepared.project)
    directory = prepared.root / "review"
    packet = json.loads((directory / "packet.json").read_text())
    mapping = json.loads((directory / "parent-only.json").read_text())["cases"]
    assert len(packet["cases"]) == 24
    assert Counter(row["original_id"] for pair in mapping for row in pair["originals"]) == Counter({identity: 2 for identity in expected})
    for row, parent in zip(packet["cases"], mapping, strict=True):
        for signal, source in zip(row["signals"], parent["originals"], strict=True):
            assert signal["source_float32_sha256"] == expected[source["original_id"]]
    assert pending_path.read_bytes() == unchanged

    class CommonClient:
        """Exercise the complete conditional review with authored consistent preferences and no external model."""

        def __init__(self, output):
            """Store the owned output location and initialize an empty raw event buffer."""
            self.output, self.raw_stream = output, b""

        def compare(self, row, inputs):
            """Prefer one fixed original identity in either orientation and retain a unique authored request receipt."""
            source = next(item for item in mapping if item["id"] == row["id"])
            winner = "a" if source["originals"][0]["original_id"].endswith("candidate_a") else "b"
            events = observation(winner)
            self.raw_stream = ("event: complete\ndata: " + json.dumps(events[0]["data"]) + "\n\n").encode()
            specialist.publish_json(self.output / (row["id"] + ".receipt.json"), dict(description="Authored review receipt, no remote call.", event_id=specialist.sha(row["id"].encode())[:32], origin=specialist.ORIGIN))
            return specialist.parse_comparison(events)

    monkeypatch.setattr(specialist, "SpecialistDemo", CommonClient)
    assert specialist.evaluate("review", prepared.root, prepared.project)
    result = json.loads((prepared.root / "review-first/result.json").read_text())
    assert result["review_complete"] and len(result["observations"]) == 24
    assert result["order_consistency"]["consistent_original_pairs"] == 12
    assert not result["D70_complete"] and not result["D71_started"]
    assert specialist.EXECUTION_ALLOWED is False and pending_path.read_bytes() == unchanged


def test_public_metadata_drift_fails_before_audio_network(monkeypatch):
    """Validate published parameter order and refuse changed revisions or runtime failures using authored metadata responses."""
    values = {
        "space": dict(sha=specialist.SPACE_REVISION, host=specialist.ORIGIN, runtime=dict(stage="RUNNING", sha=specialist.SPACE_REVISION)),
        "config": dict(version="6.26.0", api_prefix="/gradio_api"),
        "info": dict(named_endpoints={"/gradio_handler": dict(parameters=[dict(parameter_name=name) for name in ["target_text", "audio_path_a", "audio_path_b", "num_generations"]], returns=[{}, {}], api_visibility="public")}),
    }

    class Metadata:
        """Expose only three bounded GET metadata bodies without credentials or media operations."""

        def open(self, request, timeout):
            """Select authored metadata by exact public URL suffix and assert no POST body exists."""
            assert request.data is None and timeout == 15
            name = "space" if request.full_url.startswith("https://huggingface.co/api/spaces/") else "config" if request.full_url.endswith("/config") else "info"
            return io.BytesIO(json.dumps(values[name]).encode())

    monkeypatch.setattr(specialist.urllib.request, "build_opener", lambda *args: Metadata())
    assert specialist.inspect_interface()["space_revision"] == specialist.SPACE_REVISION
    values["space"]["sha"] = "changed"
    with pytest.raises(specialist.ReviewError, match="interface_drift"):
        specialist.inspect_interface()
    values["space"]["sha"] = specialist.SPACE_REVISION
    values["space"]["runtime"]["sha"] = "different_deployed_code"
    with pytest.raises(specialist.ReviewError, match="interface_drift"):
        specialist.inspect_interface()
    values["space"]["runtime"]["sha"] = specialist.SPACE_REVISION
    values["info"]["named_endpoints"]["/gradio_handler"]["parameters"].reverse()
    with pytest.raises(specialist.ReviewError, match="endpoint_schema"):
        specialist.inspect_interface()
