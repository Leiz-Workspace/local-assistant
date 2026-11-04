"""Verify bounded non-whitelisted reading plans, original native dependencies and sealed model-free validation."""

import copy
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.scripts import vi_workflow_reading_check as check
from benchmarks.scripts import vi_workflow_reading_policy as policy
from benchmarks.scripts import vi_workflow_reading_worker as worker


class Tokenizer:
    """Provide an independent character roundtrip fixture without SDK assets or weights."""

    def encode(self, text, **kwargs):
        """Encode fixture characters without changing their exact sequence."""
        return SimpleNamespace(ids=[ord(char) for char in text])

    def decode(self, ids, **kwargs):
        """Recover the fixture string exactly from observed code points."""
        return "".join(chr(value) for value in ids)

    def token_to_id(self, value):
        """Reserve zero as the unknown-token fixture."""
        return 0


def test_prepare_keeps_original_English_and_accepted_dates_clauses_without_exposing_content(
    caplog,
):
    """Preserve display hashes and produce hashed edit provenance rather than Vietnamese term respellings."""
    caplog.set_level("INFO")
    original = "private-answer lúc 09:15 ngày 14/11/2026; Python dùng API?"
    spoken, trace = policy.prepare_answer(original)
    assert "chín giờ mười lăm phút" in spoken and "tháng mười một" in spoken
    assert ";" not in spoken and "Python dùng API?" in spoken
    assert trace.original_sha256 == policy.sha(
        original
    ) and trace.spoken_sha256 == policy.sha(spoken)
    assert (
        trace.original_sha256 != trace.spoken_sha256 and trace.policy == policy.POLICY
    )
    assert {edit[2] for edit in trace.edits} == {"clock", "date", "clause_boundary"}
    assert "private-answer" not in caplog.text and "private-answer" not in repr(trace)


@pytest.mark.parametrize(
    "text",
    [
        "Đọc `API`.",
        "Xem https://example.test/API.",
        "Dùng API_KEY.",
        "Chạy my_Python_client.",
        "Đọc Python-CLI.",
        "<en>API</en>",
        "<|emotion_happy|>hello",
        "",
        "x\x00y",
        "x" * 2049,
    ],
)
def test_protected_target_controls_and_invalid_answers_refuse_before_dispatch(text):
    """Reject unsupported protected target mappings without mutating identifiers or loading a model."""
    with pytest.raises(ValueError):
        policy.prepare_answer(text)


def test_zero_multiple_repeated_terms_and_substrings_keep_exact_phone_scope():
    """Handle arbitrary declared counts while preserving unrelated phones and unknown terms."""
    source, target = policy.TERMS["python"]
    raw = (
        source + " " + source + " " + policy.API_SOURCE + " " + policy.API_SOURCE + "?"
    )
    result = policy.plan_chunk("python python <en>a p i a p i</en>?", raw, len)
    assert (
        result["phones"]
        == target
        + " "
        + target
        + " "
        + policy.API_TARGET
        + " "
        + policy.API_TARGET
        + "?"
    )
    assert len(result["edits"]) == 4 and result["shared_cap"] <= min(
        result["original_cap"], result["reading_cap"]
    )
    assert policy.plan_chunk("pythonic", source + "ɪk", len)["phones"] == source + "ɪk"
    assert policy.plan_chunk("I", "ˈaɪ", len)["phones"] == "ˈaɪ"
    assert policy.plan_chunk("python", target, len)["edits"] == []
    with pytest.raises(ValueError, match="ambiguous"):
        policy.plan_chunk("python", source + "ɪk", len)
    with pytest.raises(ValueError, match="ambiguous"):
        policy.plan_chunk("python python", source, len)
    with pytest.raises(ValueError, match="ambiguous"):
        policy.plan_chunk(" ".join(["python"] * 17), " ".join([source] * 17), len)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_nonpositive_or_noninteger_cap_cannot_admit_generation(value):
    """Keep original finite integer duration budgets without coercing invalid metadata."""
    with pytest.raises(ValueError, match="invalid_cap"):
        policy.plan_chunk("hello", "həloʊ", lambda text: value)


def make_adapter(bad_second=False, bad_tokenizer=False):
    """Create two real adapter chunks with observable original native objects and no neural engine."""
    chunks = ["python <en>a p i</en>.", "bạn muốn <en>a p i</en>?"]
    raw = [
        policy.TERMS["python"][0] + " " + policy.API_SOURCE + ".",
        "bˈa6n " + policy.API_SOURCE + "?",
    ]
    if bad_second:
        raw[1] = "unmapped"
    calls, joined = [], []
    waves = [np.array([0.1], dtype=np.float32), np.array([0.2], dtype=np.float32)]
    speaker, codes = np.array([0.1], dtype=np.float32), np.array([[1]], dtype=np.int64)

    def infer(**kwargs):
        """Capture exact original sampling/reference arguments and return native fixture arrays."""
        calls.append(kwargs)
        return waves[len(calls) - 1]

    def resolve(voice, reference, denoise, use_codes):
        """Require the preserved Truc Ly reference path."""
        assert (
            voice == policy.VOICE and reference is None and denoise is use_codes is True
        )
        return speaker, codes

    def join(values, rate, silence_ps):
        """Require exact native objects and original ordered joining semantics."""
        assert (
            all(a is b for a, b in zip(values, waves, strict=True))
            and rate == 48000
            and silence_ps == [0.2]
        )
        joined.append(True)
        return np.concatenate(values)

    tokenizer = Tokenizer()
    if bad_tokenizer:
        tokenizer.decode = lambda *args, **kwargs: "wrong"
    wrapper = SimpleNamespace(
        engine=SimpleNamespace(infer=infer, tokenizer=tokenizer),
        _resolve_ref=resolve,
        _apply_watermark=lambda value: value,
        sample_rate=48000,
    )
    deps = dict(
        normalize=lambda text, **kw: text,
        split=lambda text: chunks,
        pack=lambda values, **kw: values,
        classify=lambda text: "sentence",
        phonemize=lambda text, **kw: raw[chunks.index(text)],
        frame_cap=lambda phones: 100,
        repetition_window=64,
        pauses=lambda gaps: [0.2],
        join=join,
    )
    return policy.WorkflowReadingAdapter(wrapper, deps), calls, joined, speaker, codes


def test_native_adapter_preserves_every_original_dependency_and_verifies_all_chunks_first():
    """Keep speaker/reference/sampling and question phones across non-whitelisted multi-chunk replies."""
    adapter, calls, joined, speaker, codes = make_adapter()
    wave = adapter.infer("A new arbitrary CORE answer.", voice=policy.VOICE)
    assert (
        wave.tolist() == pytest.approx([0.1, 0.2])
        and len(calls) == 2
        and joined == [True]
    )
    for call in calls:
        assert (
            call["speaker_emb"] is speaker
            and call["ref_codes"] is codes
            and call["use_ref_codes"] is True
        )
        assert (
            call["temperature"],
            call["top_k"],
            call["top_p"],
            call["repetition_penalty"],
            call["max_new_frames"],
        ) == (0.8, 25, 0.95, 1.2, 100)
    assert adapter.last_trace["reading_policy"] == policy.POLICY and adapter.last_trace[
        "phonemes"
    ][-1].endswith("?")
    assert len(adapter.last_trace["reading_tokens"]) == 2
    with pytest.raises(ValueError, match="voice"):
        adapter.infer("new answer", voice="Ngọc Huyền")


@pytest.mark.parametrize("kind", ["plan", "tokens"])
def test_late_chunk_or_token_failure_prevents_even_first_generation(kind):
    """Avoid partial synthesis when an arbitrary later sentence has an unapproved phone mapping."""
    adapter, calls, joined, _, _ = make_adapter(
        bad_second=kind == "plan", bad_tokenizer=kind == "tokens"
    )
    with pytest.raises(ValueError):
        adapter.infer("new answer", voice=policy.VOICE)
    assert not calls and not joined


@pytest.mark.parametrize(
    "change",
    [
        {"native_authorized": False},
        {"max_requests": 0},
        {"max_requests": True},
        {"max_requests": 25},
        {"voice": "Ngọc Huyền"},
        {"model": "another-model"},
        {"policy": "raw"},
    ],
)
def test_manifest_cannot_load_an_unapproved_or_changed_lane(change):
    """Keep the unapproved native campaign locked while allowing model-free preparation."""
    scope = dict(
        native_authorized=True,
        policy=policy.POLICY,
        model=policy.MODEL,
        voice=policy.VOICE,
        max_requests=6,
        scope_sha256="a" * 64,
    )
    assert worker.manifest(scope) == scope
    with pytest.raises(ValueError, match="not_authorized"):
        worker.manifest(dict(scope, **change))


def test_unapproved_manifest_is_rejected_before_runtime_factory(tmp_path, monkeypatch):
    """Prove the native entry point cannot load weights merely because preparation code exists."""
    path = tmp_path / "scope.json"
    raw = json.dumps(dict(native_authorized=False)).encode()
    path.write_bytes(raw)
    monkeypatch.setattr(worker, "Path", lambda value: path)

    def forbidden(*args, **kwargs):
        """Fail if an unapproved manifest reaches a model runtime constructor."""
        pytest.fail("Runtime must not load")

    monkeypatch.setattr(worker, "configure_runtime", forbidden)
    with pytest.raises(ValueError, match="not_authorized"):
        worker.serve(hashlib.sha256(raw).hexdigest())


def test_namespace_keeps_probe_without_weights_and_native_manifest_read_only(tmp_path):
    """Keep the original CPU/no-network mounts while separating frontend testing from native scope."""
    output = tmp_path / "out"
    output.mkdir(mode=0o700)
    args = check.command(output)
    mounts = {
        args[index + 2] for index, value in enumerate(args) if value == "--ro-bind"
    }
    assert (
        "/model" not in mounts
        and "/hf/hub" not in mounts
        and "/approved-workflow.json" not in mounts
    )
    assert args[-1] == "--probe" and "--unshare-all" in args
    scope = tmp_path / "scope.json"
    scope.write_text("{}")
    args = check.command(output, scope, "a" * 64)
    assert "/approved-workflow.json" in args and args[-2:] == [
        "--approved-manifest",
        "a" * 64,
    ]


def test_probe_retains_refusals_and_acceptance_parity_rejects_drift():
    """Keep bad cases visible and refuse mismatched accepted phones instead of altering old expected outcomes."""
    rows = [
        dict(id="good", speech_text="hello"),
        dict(id="bad", speech_text="<en>API</en>"),
    ]
    deps = dict(
        normalize=lambda text, **kw: text,
        split=lambda text: [text],
        pack=lambda values, **kw: values,
        classify=lambda text: "sentence",
        phonemize=lambda text, **kw: "həloʊ.",
        frame_cap=lambda phones: 100,
    )
    observed = worker.inspect_rows(rows, deps, Tokenizer())
    assert [row["status"] for row in observed] == ["PLANNED", "REFUSED"]
    packet = [dict(id="good", trace=dict(spoken_sha256=observed[0]["spoken_sha256"]))]
    accepted = [
        dict(
            id="good",
            chunks=observed[0]["chunks"],
            gaps=[],
            phone_plans=[dict(us="həloʊ.", shared_cap=100)],
        )
    ]
    check.verify_observations(observed[:1], packet, accepted)
    bad = copy.deepcopy(observed[:1])
    bad[0]["plans"][0]["phones"] = "different"
    with pytest.raises(ValueError, match="policy_drift"):
        check.verify_observations(bad, packet, accepted)
