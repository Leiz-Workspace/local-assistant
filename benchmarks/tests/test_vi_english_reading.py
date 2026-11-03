"""Protect accepted date/prosody behavior while restoring real English terms and bounded comparison admission."""

import hashlib

import pytest

from benchmarks.scripts import vi_english_reading as english
from benchmarks.scripts.vi_speech_text import render_speech


@pytest.mark.parametrize(
    "source",
    [
        "Bạn muốn học Python hay dùng API của ứng dụng?",
        "Chị đang kiểm tra Python; API sẽ sẵn sàng sau ít phút.",
        "Nhắc lúc 09:15 ngày 14/11; hãy kiểm tra API.",
    ],
)
def test_remove_only_vietnamese_lexicon_substitution(source):
    """Keep English tokens and every previously accepted non-lexicon edit exactly unchanged."""
    original = render_speech(source, "clauses")
    fixed = english.render_english(source)
    assert fixed.source_text == original.source_text == source
    assert fixed.edits == tuple(
        edit for edit in original.edits if edit.kind != "lexicon"
    )
    assert "API" in fixed.speech_text and "ây pi ai" not in fixed.speech_text
    if "Python" in source:
        assert "Python" in fixed.speech_text and "pai thờn" not in fixed.speech_text
    assert fixed.source_sha256 == hashlib.sha256(source.encode()).hexdigest()
    assert fixed.speech_sha256 == hashlib.sha256(fixed.speech_text.encode()).hexdigest()


@pytest.mark.parametrize(
    "source",
    [
        "Hẹn lúc 09:15 ngày 14/11.",
        "Bạn đồng ý chứ?",
        "Tệp đã lưu; hãy kiểm tra bản sao.",
        "Giữ `API Python` và https://example.org/API/Python.",
    ],
)
def test_accepted_non_english_cases_remain_identical(source):
    """Prevent regression of the owner-accepted time/date, punctuation and protected-token rendering."""
    fixed = english.render_english(source)
    assert fixed.speech_text == render_speech(source, "clauses").speech_text
    assert fixed.render_seconds >= 0


def test_eight_preregistered_slots_keep_two_voices_and_no_guessing():
    """Freeze exactly four cases per voice without altering source spelling or selecting a model."""
    rows = english.rows()
    assert len(rows) == 8 and len({row["id"] for row in rows}) == 8
    assert {row["voice"] for row in rows} == {"Trúc Ly", "Ngọc Huyền"}
    assert all(
        row["profile"] == "clauses" and row["status"] == "UNATTEMPTED" for row in rows
    )
    assert all("API" in row["render"]["speech_text"] for row in rows)


def test_frontend_probe_exposes_text_tokenizer_without_neural_weights(tmp_path):
    """Keep the probe offline and mount only the already approved text tokenizer artifact."""
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    command = english.probe_command(output)
    mounts = [command[i + 2] for i, token in enumerate(command) if token == "--ro-bind"]
    assert "/approved-tokenizer.json" in mounts
    assert not {"/model", "/hf/hub", "/samples"} & set(mounts)
    assert command[-2] == "-c" and command[-1] == english.PROBE_SOURCE
    compile(english.PROBE_SOURCE, "english-probe", "exec")


@pytest.mark.asyncio
async def test_completed_trial_never_repeats(tmp_path, monkeypatch):
    """Reject a previously frozen trial before reading private assets or starting a model."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    monkeypatch.setattr(
        english, "verify_preferred_code", lambda: pytest.fail("must not execute")
    )
    with pytest.raises(ValueError, match="already_attempted"):
        await english.run(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True, "probe_mismatch"])
async def test_actual_controller_preserves_eight_slots_and_stops_first_failure(
    tmp_path, monkeypatch, failure
):
    """Exercise actual admission/freeze/retirement with public fixture responses and no model or private data access."""
    import json

    original_project = english.quality.assets.PROJECT
    project = tmp_path / "project"
    evidence = project / "docs/evidence"
    evidence.mkdir(parents=True)
    (evidence / "d74-english-reading-authorization.json").write_text(
        '{"authorized":true}'
    )
    hashes = {}
    for name in [
        "benchmarks/scripts/vi_english_reading.py",
        "benchmarks/tests/test_vi_english_reading.py",
    ]:
        p = project / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((original_project / name).read_bytes())
        hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    root = tmp_path / "root"
    (root / "probe/native").mkdir(parents=True)
    (root / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", operator_sha256=hashes))
    )
    (root / "probe/native/frontend.json").write_text(
        json.dumps(
            dict(
                rows=[
                    dict(
                        speech_text=row["render"]["speech_text"],
                        unknown_tokens=0,
                        english_references_present={"API": True},
                    )
                    for row in english.rows()
                ]
            )
        )
    )
    monkeypatch.setattr(english.quality.assets, "PROJECT", project)
    monkeypatch.setattr(english.quality.assets, "ROOT", root)
    monkeypatch.setattr(english, "verify_preferred_code", lambda: {})
    monkeypatch.setattr(
        english.quality.lifecycle, "prepared_integrity", lambda root: None
    )
    monkeypatch.setattr(
        english.quality.lifecycle, "verify_originals", lambda: {"fixture": 1}
    )
    monkeypatch.setattr(
        english.quality.lifecycle, "local_state", lambda: {"native_pids": []}
    )
    calls, closed = [], []

    class Worker:
        """Provide bounded first-response fixtures without any native backend."""

        def __init__(self, profile, directory, deadline):
            """Require the owner-preferred profile and initialize a failure marker."""
            assert profile == "clauses"
            self.failure = None

        async def start(self):
            """Represent readiness of a public fixture only."""
            return self

        async def call(self, message):
            """Observe actual English input dispatch or inject the first failure."""
            calls.append(message)
            assert "API" in message["text"] and "ây pi ai" not in message["text"]
            if failure:
                self.failure = "fixture_failure"
                raise ValueError(self.failure)
            return dict(generation_complete=True)

        async def close(self, force):
            """Record joined retirement without stopping any real process."""
            closed.append(force)

    monkeypatch.setattr(english.quality, "QualityWorker", Worker)
    if failure == "probe_mismatch":
        path = root / "probe/native/frontend.json"
        mismatched = json.loads(path.read_text())
        mismatched["rows"][0]["speech_text"] = "Changed API input"
        path.write_text(json.dumps(mismatched))
        with pytest.raises(ValueError, match="probe_input_changed"):
            await english.run(root)
        assert calls == closed == [] and not (root / "execution-freeze.json").exists()
        return
    result = await english.run(root)
    assert len(result["rows"]) == 8 and result["asr_calls"] == result["core_calls"] == 0
    assert result["baseline_restored"] and len(closed) == 1
    assert result["tts_attempts"] == len(calls) == (1 if failure else 8)
    assert result["unattempted"] == (7 if failure else 0)
    assert result["status"] == (
        "STOPPED_NO_RETRY"
        if failure
        else "ENGLISH_CANDIDATES_COMPLETE_QUALITY_UNVERIFIED"
    )


def test_english_page_has_exact_original_media_and_no_remote_or_capture_capabilities():
    """Preserve candidate/baseline bytes and escape hostile labels without scripting or uploads."""
    import base64
    from benchmarks.tests.test_vi_speech_review import MediaParser

    rows = english.rows()
    audio = {row["id"]: b"new:" + row["id"].encode() for row in rows}
    baselines = {
        row["id"]: b"old:" + row["id"].encode()
        for row in rows
        if row["case"] in {"english-01", "english-02"}
    }
    rows[0]["render"]["source_text"] = "<script>bad()</script>"
    page = english.render_review(rows, audio, baselines)
    parser = MediaParser()
    parser.feed(page)
    assert len(parser.media) == 12 and not parser.forbidden
    assert "https://" not in page and "<script>bad()" not in page
    decoded = {base64.b64decode(item["src"].split(",", 1)[1]) for item in parser.media}
    assert decoded == set(audio.values()) | set(baselines.values())
    with pytest.raises(ValueError):
        english.render_review(rows[:-1], audio, baselines)


def test_missing_candidates_remain_visible():
    """Keep all eight unattempted slots visible without inventing candidate audio or successful outcomes."""
    page = english.render_review(english.rows(), {}, {})
    assert page.count("Chưa có clip hoàn chỉnh: UNATTEMPTED") == 8
