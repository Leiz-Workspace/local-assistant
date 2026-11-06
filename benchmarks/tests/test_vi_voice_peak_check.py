"""Test the separately fixed v2scope, first-failure retention and complete quality scoring without private inference."""

import json

import pytest

from benchmarks.scripts import vi_voice_peak_check as target
from benchmarks.tests.test_vi_voice_presence import audio
from benchmarks.tests.test_vi_voice_presence_check import events


@pytest.mark.asyncio
@pytest.mark.parametrize("accept", [False, True])
async def test_v2_native_projection_preserves_original_pcm_and_audit(accept):
    """Exercise the actual v2adapter with native-shaped evidence and explicit downstream sentinels."""
    value = audio()
    view = target.peak.detector_view(value)
    result = await target.replay(
        dict(language="en"),
        value,
        dict(
            waveform_sha256=view.waveform_sha256,
            segments=[dict(start=1, end=500)] if accept else [],
        ),
    )
    assert result["asr_sentinel_calls"] == int(accept)
    assert result["trace"]["pcm_sha256"] == value.pcm_sha256
    assert result["trace"]["detector_waveform_sha256"] == view.waveform_sha256


def setup(monkeypatch, root):
    """Build147fixed authored software rows and9native-shaped batches without any model assets."""
    (root / "samples").mkdir()
    (root / "rows").mkdir()
    source = root / "source.py"
    source.write_text("source")
    monkeypatch.setattr(target, "PROJECT", root)
    monkeypatch.setattr(target, "SOURCES", ("source.py",))
    monkeypatch.setattr(target.old, "verify_snapshot", lambda value: None)
    monkeypatch.setattr(target.old, "verify_provision", lambda: None)
    monkeypatch.setattr(target.old.prior, "local_state", lambda: {})
    monkeypatch.setattr(target, "load_audio", lambda root, row: audio())
    value = audio()
    view = target.peak.detector_view(value)
    rows = []
    batches = []
    for i in range(147):
        group = (
            "regression"
            if i < 47
            else ("validation" if i < 94 else ("fresh" if i < 141 else "repair"))
        )
        identity = "c" + str(i)
        rows.append(
            dict(
                id=identity,
                group=group,
                kind="synthetic_speech",
                language="vi",
                expected_speech=True,
                view_sha256=view.waveform_sha256,
            )
        )
        (root / "samples" / ("peak-" + identity + ".f32")).write_bytes(
            view.waveform_f32
        )
    for group in ("regression", "validation", "fresh", "repair"):
        selected = [x for x in rows if x["group"] == group]
        for chunk in [[x] for x in selected] if group == "repair" else [selected]:
            batches.append(
                [
                    dict(
                        id="peak-" + x["id"],
                        filename="peak-" + x["id"] + ".f32",
                        sample_count=value.sample_count,
                        waveform_sha256=view.waveform_sha256,
                    )
                    for x in chunk
                ]
            )
    sha = target.old.prior.assets.digest(source)
    target.old.publish(
        root / "execution-freeze.json",
        dict(
            source_sha256={"source.py": sha},
            previous_sha256={},
            before={},
            rows=rows,
            batches=batches,
        ),
    )
    target.old.publish(
        root / "software-verification.json",
        dict(status="PASS", source_sha256={"source.py": sha}),
    )


@pytest.mark.parametrize("failure", [None, "quality", "runtime"])
def test_fixed_scope_never_hides_failures_or_retries(monkeypatch, tmp_path, failure):
    """Keep all147decisions and distinguish quality failure from a completed native program."""
    setup(monkeypatch, tmp_path)
    calls = []

    def native(root, identity, request, **kwargs):
        """Generate deterministic software evidence while retaining every first native admission."""
        calls.append(request)
        if failure == "runtime":
            raise ValueError("first failure")
        result = events(request["cases"], reverse=len(request["cases"]) == 47)
        if failure == "quality":
            for x in result:
                if x.get("id") == "peak-c0":
                    x["segments"] = []
        d = root / identity
        d.mkdir()
        (d / "stdout.jsonl").write_text("".join(json.dumps(x) + "\n" for x in result))
        return result, {}

    monkeypatch.setattr(target.old, "run_vad", native)
    if failure == "runtime":
        with pytest.raises(ValueError, match="first failure"):
            target.execute(tmp_path)
        assert len(calls) == 1 and not (tmp_path / "quality.json").exists()
    else:
        target.execute(tmp_path)
        q = json.loads((tmp_path / "quality.json").read_text())
        assert q["total"] == 147 and q["boost_correct"] == (
            146 if failure == "quality" else 147
        )
        assert q["status"] == (
            "LOCAL_DETECTOR_GATES_FAIL"
            if failure == "quality"
            else "LOCAL_DETECTOR_GATES_PASS"
        )
        assert [len(x["cases"]) for x in calls] == [47] * 3 + [1] * 6
        assert (
            json.loads((tmp_path / "retirement.json").read_text())["observations"]
            == 288
        )
    before = len(calls)
    with pytest.raises(FileExistsError):
        target.execute(tmp_path)
    assert len(calls) == before
