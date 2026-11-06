"""Verify fixed paired VAD scope, original-audio projection and immutable quality failures without private models."""

import json
from dataclasses import asdict

import pytest

from benchmarks.scripts import vi_voice_view_check as target
from benchmarks.scripts.vi_voice_detector_view import detector_view
from benchmarks.tests.test_vi_voice_presence import audio
from benchmarks.tests.test_vi_voice_presence_check import events


@pytest.mark.asyncio
@pytest.mark.parametrize("admitted", [False, True])
async def test_native_normalized_view_is_bound_before_sentinel_forwarding(admitted):
    """Do not mistake the detector-view hash for the raw PCM hash in the original ASR gate."""
    value = audio()
    view = detector_view(value)
    event = dict(
        waveform_sha256=view.waveform_sha256,
        segments=[dict(start=0, end=1000)] if admitted else [],
    )
    result = await target.replay(dict(language="vi"), value, event)
    assert result["asr_sentinel_calls"] == int(admitted)
    assert result["trace"]["pcm_sha256"] == value.pcm_sha256
    assert result["trace"]["detector_waveform_sha256"] == view.waveform_sha256
    assert result["trace"]["first_pts"] == value.first_pts


@pytest.mark.asyncio
async def test_wrong_native_view_cannot_publish_a_pipeline_result():
    """Refuse output rebinding even if the model reports apparently valid speech intervals."""
    with pytest.raises(Exception, match="dependency_failed"):
        await target.replay(
            dict(language="vi"), audio(), dict(waveform_sha256="b" * 64, segments=[])
        )


def setup(monkeypatch, root, negative=False):
    """Construct a complete synthetic100row/two-view study with no private artifacts or native inference."""
    source = root / "source.py"
    source.write_text("test source")
    monkeypatch.setattr(target, "PROJECT", root)
    monkeypatch.setattr(target, "SOURCES", ("source.py",))
    monkeypatch.setattr(target.old, "verify_snapshot", lambda value: None)
    monkeypatch.setattr(target.old, "verify_provision", lambda: None)
    monkeypatch.setattr(target.old.prior, "local_state", lambda: {})
    for name in ("samples", "pcm", "rows"):
        (root / name).mkdir()
    value = audio()
    view = detector_view(value)
    rows = []
    for i in range(100):
        identity = "c" + str(i)
        row = dict(
            id=identity,
            group="regression" if i < 47 else ("validation" if i < 94 else "repair"),
            kind="synthetic_speech",
            language="vi",
            expected_speech=not (negative and i == 99),
            sample_count=value.sample_count,
            waveform_sha256=target.old.sha(target.old.floats(value)),
            view_sha256=view.waveform_sha256,
            gain=view.gain,
            audio={k: v for k, v in asdict(value).items() if k != "pcm_s16le"},
        )
        rows.append(row)
        (root / "pcm" / (identity + ".s16le")).write_bytes(value.pcm_s16le)
        for variant, payload in (
            ("raw", target.old.floats(value)),
            ("boost", view.waveform_f32),
        ):
            (root / "samples" / (variant + "-" + identity + ".f32")).write_bytes(
                payload
            )
    batches = []
    for group in ("regression", "validation", "repair"):
        selected = [x for x in rows if x["group"] == group]
        for chunk in [[x] for x in selected] if group == "repair" else [selected]:
            for variant in ("raw", "boost"):
                requests = []
                for row in chunk:
                    identity = variant + "-" + row["id"]
                    requests.append(
                        dict(
                            id=identity,
                            filename=identity + ".f32",
                            sample_count=value.sample_count,
                            waveform_sha256=target.old.prior.assets.digest(
                                root / "samples" / (identity + ".f32")
                            ),
                        )
                    )
                batches.append(dict(variant=variant, group=group, requests=requests))
    source_sha = target.old.prior.assets.digest(source)
    target.old.publish(
        root / "execution-freeze.json",
        dict(
            source_sha256={"source.py": source_sha},
            previous_sha256={},
            before={},
            rows=rows,
            batches=batches,
        ),
    )
    target.old.publish(
        root / "software-verification.json",
        dict(status="PASS", source_sha256={"source.py": source_sha}),
    )
    return batches


@pytest.mark.parametrize("failure", [None, "quality", "runtime"])
def test_all_fixed_rows_are_scored_or_retained_without_retry(
    monkeypatch, tmp_path, failure
):
    """Do not drop wrong decisions, silently retry failed workers or confuse complete coverage with quality PASS."""
    batches = setup(monkeypatch, tmp_path, negative=failure == "quality")
    called = []

    def native(root, identity, request, **kwargs):
        """Emit native-shaped receipts while recording every attempted batch exactly once."""
        called.append(request)
        if failure == "runtime":
            raise ValueError("native first failure")
        rows = events(request["cases"], reverse=len(request["cases"]) == 47)
        directory = root / identity
        directory.mkdir()
        (directory / "stdout.jsonl").write_text(
            "".join(json.dumps(x) + "\n" for x in rows)
        )
        return rows, {}

    monkeypatch.setattr(target.old, "run_vad", native)
    if failure == "runtime":
        with pytest.raises(ValueError, match="native first failure"):
            target.execute(tmp_path)
        assert len(called) == 1 and not (tmp_path / "quality.json").exists()
    else:
        target.execute(tmp_path)
        assert len(called) == 16
        quality = json.loads((tmp_path / "quality.json").read_text())
        assert quality["total"] == 100 and quality["boost_correct"] == (
            99 if failure == "quality" else 100
        )
        assert quality["status"] == (
            "LOCAL_DETECTOR_GATES_FAIL"
            if failure == "quality"
            else "LOCAL_DETECTOR_GATES_PASS"
        )
        assert (
            quality["actual_neural_asr_core_tts_calls"] == 0
            and not quality["product_activation"]
        )
        assert [len(x["cases"]) for x in called] == [47] * 4 + [1] * 12
        assert all(
            x["cases"] == batch["requests"]
            for x, batch in zip(called, batches, strict=True)
        )
    before = len(called)
    with pytest.raises(FileExistsError):
        target.execute(tmp_path)
    assert len(called) == before


def test_changed_view_is_refused_before_loading(monkeypatch, tmp_path):
    """Bind each native request to frozen detector bytes rather than trusting only metadata."""
    setup(monkeypatch, tmp_path)
    (tmp_path / "samples/raw-c0.f32").write_bytes(b"changed")
    with pytest.raises(ValueError, match="view_model_input_changed"):
        target.execute(tmp_path)
    assert not (tmp_path / "quality.json").exists()


def test_software_gate_prevents_loading_and_consumption(monkeypatch, tmp_path):
    """Require successful tests of the exact current implementation before any new worker is admitted."""
    setup(monkeypatch, tmp_path)
    (tmp_path / "software-verification.json").write_text('{"status":"FAIL"}')
    with pytest.raises(ValueError, match="view_software_gate"):
        target.execute(tmp_path)
    assert not (tmp_path / "run-start.json").exists()


def test_preparation_fixes_disjoint_validation_derivatives_and_pair_order(
    monkeypatch, tmp_path
):
    """Keep corpus selection, exact gains, complete rows and raw-first pairing independent of model outcomes."""
    from types import SimpleNamespace

    project = tmp_path / "project"
    project.mkdir()
    old_root = project / "old"
    old_root.mkdir()
    (old_root / "pcm").mkdir()
    d72 = project / "d72"
    d72.mkdir()
    (d72 / "corpus.json").write_text(
        json.dumps(
            dict(
                cases=[
                    dict(language=lang, sentence_id=i)
                    for lang in ("vi_vn", "en_us")
                    for i in range(20, 40)
                ]
            )
        )
    )
    value = audio()
    old_rows = []
    for i in range(53):
        identity = "old-" + str(i)
        (old_root / "pcm" / (identity + ".s16le")).write_bytes(value.pcm_s16le)
        old_rows.append(
            dict(
                id=identity,
                kind="independent_public_speech"
                if i < 40
                else ("authored_no_speech" if i < 45 else "derived_quiet_recording"),
                language="vi" if i < 20 else "en",
                expected_speech=not 40 <= i < 45,
                sample_count=value.sample_count,
                waveform_sha256=target.old.sha(target.old.floats(value)),
                audio={k: v for k, v in asdict(value).items() if k != "pcm_s16le"},
            )
        )
    (old_root / "execution-freeze.json").write_text(json.dumps(dict(cases=old_rows)))
    corpus_root = project / "data/backups/d68-asr-evaluation/prepared"
    corpus_root.mkdir(parents=True)
    corpus = []
    for lang in ("vi_vn", "en_us"):
        for i in range(12):
            path = corpus_root / (lang + str(i) + ".f32")
            path.write_bytes(target.old.floats(value))
            corpus.append(
                dict(
                    id=lang + str(i),
                    language=lang,
                    sentence_id=i,
                    kind="independent_public_speech",
                    waveform_path=str(path),
                    waveform_sha256=target.old.sha(path.read_bytes()),
                )
            )
    (corpus_root / "corpus.json").write_text(json.dumps(dict(cases=corpus)))
    for name in (
        "docs/evidence/d74-whole-clip-presence-result.json",
        "docs/ADR/166-whole-clip-presence-with-original-pcm.md",
        "fixture.md",
    ):
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    monkeypatch.setattr(target, "PROJECT", project)
    monkeypatch.setattr(target, "SOURCES", ())
    monkeypatch.setattr(target, "ADR", "fixture.md")
    monkeypatch.setattr(target.old, "ROOT", old_root)
    monkeypatch.setattr(target.old, "CORPUS_ROOT", d72)
    monkeypatch.setattr(target.old, "previous_snapshot", lambda: {})
    monkeypatch.setattr(target.old.prior, "local_state", lambda: {})
    monkeypatch.setattr(
        target.old.prior,
        "NativeAudioNormalizer",
        lambda: SimpleNamespace(normalize=lambda raw: value),
    )
    freeze = target.prepare(project / "new")
    assert len(freeze["rows"]) == 100 and len(freeze["batches"]) == 16
    assert [len(x["requests"]) for x in freeze["batches"]] == [47] * 4 + [1] * 12
    assert [x["variant"] for x in freeze["batches"]] == ["raw", "boost"] * 8
    validation = [x for x in freeze["rows"] if x["group"] == "validation"]
    assert len(validation) == 47
    assert sum(x["kind"] == "disjoint_original_speech" for x in validation) == 20
    assert sum(x["kind"] == "derived_quiet_recording" for x in validation) == 20
    assert sum(not x["expected_speech"] for x in validation) == 5
    assert all(
        "10" not in x["parent"] and "11" not in x["parent"]
        for x in validation
        if x["kind"] == "disjoint_original_speech"
    )
    assert all(1 <= x["gain"] <= 32 for x in freeze["rows"])
    assert (old_root / "pcm/old-0.s16le").read_bytes() == value.pcm_s16le
    assert (
        target.load_audio(project / "new", freeze["rows"][0]).pcm_s16le
        == value.pcm_s16le
    )
    with pytest.raises(FileExistsError):
        target.prepare(project / "new")


def test_storage_reconstruction_is_exact_for_every_signed16_bit_value(tmp_path):
    """Prove the storage reduction preserves all65536PCM code points rather than only quiet fixture samples."""
    import numpy as np
    from dataclasses import replace

    pcm = np.arange(-32768, 32768, dtype="<i2").tobytes()
    value = replace(
        audio(),
        pcm_s16le=pcm,
        pcm_sha256=target.old.sha(pcm),
        sample_count=65536,
        source_sample_count=65536,
    )
    raw = target.old.floats(value)
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples/raw-all.f32").write_bytes(raw)
    row = dict(
        id="all",
        sample_count=value.sample_count,
        waveform_sha256=target.old.sha(raw),
        audio={k: v for k, v in asdict(value).items() if k != "pcm_s16le"},
    )
    assert target.load_audio(tmp_path, row) == value


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.1, 1.0])
def test_non_pcm_float_storage_is_not_repaired(tmp_path, bad):
    """Refuse NaN, fractions and overflow instead of silently rounding a changed source waveform."""
    import numpy as np

    raw = np.full(32000, bad, dtype="<f4").tobytes()
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples/raw-invalid.f32").write_bytes(raw)
    row = dict(
        id="invalid", sample_count=32000, waveform_sha256=target.old.sha(raw), audio={}
    )
    with pytest.raises(ValueError, match="view_pcm_not_exactly_representable"):
        target.load_audio(tmp_path, row)
