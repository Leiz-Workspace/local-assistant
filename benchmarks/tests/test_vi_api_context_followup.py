"""Test separately declared carrier controls, original actual-budget preservation and paired input/speaker invariants."""

import copy
import base64
import json

import pytest

from benchmarks.scripts import vi_api_context_followup as context
from benchmarks.tests.test_vi_speech_review import MediaParser


def frontend():
    """Create public complete-sentence fixtures rather than retrying the failed short-letter case."""
    return dict(
        reference_api="ˈeɪ pˈiː ˈaɪ",
        rows=[
            dict(
                id=identity,
                source_text=text,
                phonemes="context ˈeɪ pˈiː ˈaɪ.",
                decoded="context ˈeɪ pˈiː ˈaɪ.",
                syllables=6,
                original_frame_cap=100,
                unknown_tokens=0,
            )
            for identity, text in context.CASES
        ],
    )


def test_new_contexts_preserve_eight_slot_denominator_and_original_caps():
    """Reject short or changed controls before any new native call."""
    rows = context.packet(frontend())
    assert len(rows) == 8 and len({row["id"] for row in rows}) == 8
    assert not {"letter-a", "api-spaced", "api-compact"} & {row["case"] for row in rows}
    for field, value in [
        ("syllables", 4),
        ("original_frame_cap", 13),
        ("unknown_tokens", 1),
        ("source_text", "changed"),
    ]:
        bad = frontend()
        bad["rows"][0][field] = value
        with pytest.raises(ValueError):
            context.packet(bad)


def test_pair_check_rejects_changed_text_or_speaker():
    """Prevent a ref-code ablation from silently becoming a different input or speaker comparison."""
    rows = context.packet(frontend())
    for row in rows:
        enabled = row["mode"] == "with_reference"
        row.update(
            status="NATIVE_COMPLETE_AWAITING_OWNER_REVIEW",
            native=dict(
                reference_trace=dict(
                    phonemes=row["phonemes"],
                    token_ids=[44, 45],
                    speaker_embedding_sha256="s",
                    projected_anchor_sha256="a",
                    prompt_text_ids=[16, 3, 44, 45, 4],
                    use_ref_codes=enabled,
                    reference_rows=2 if enabled else 0,
                )
            ),
        )
    context.verify_pairs(rows)
    bad = copy.deepcopy(rows)
    bad[-1]["native"]["reference_trace"]["projected_anchor_sha256"] = "other"
    with pytest.raises(ValueError, match="pair_changed"):
        context.verify_pairs(bad)


def test_review_keeps_missing_slots_and_original_native_bytes():
    """Publish only supplied unchanged media with no capture, script or network capability."""
    rows = context.packet(frontend())
    audio = {row["id"]: row["id"].encode() for row in rows}
    page = context.render_page(rows, audio)
    parser = MediaParser()
    parser.feed(page)
    assert len(parser.media) == 8 and not parser.forbidden
    assert {
        base64.b64decode(row["src"].split(",", 1)[1]) for row in parser.media
    } == set(audio.values())
    assert (
        context.render_page(rows, {}).count("Chưa có clip hoàn chỉnh: UNATTEMPTED") == 8
    )
    compile(context.PROBE, "context-probe", "exec")


@pytest.mark.asyncio
async def test_completed_context_cohort_cannot_retry(tmp_path):
    """Reject a retained marker before reading private assets or loading any model."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    with pytest.raises(ValueError, match="already_attempted"):
        await context.run(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_controller_preserves_combined_ceiling_and_first_failure(
    tmp_path, monkeypatch, failure
):
    """Exercise exact eight-context admission and original-plus-followup accounting without model access."""
    project = tmp_path / "project"
    evidence = project / "docs/evidence"
    evidence.mkdir(parents=True)
    (evidence / "d74-api-context-authorization.json").write_text('{"authorized":true}')
    paths = [
        "benchmarks/scripts/vi_api_context_followup.py",
        "benchmarks/tests/test_vi_api_context_followup.py",
    ]
    hashes = {}
    for name in paths:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((context.Q.assets.PROJECT / name).read_bytes())
        hashes[name] = context.Q.assets.digest(path)
    old = tmp_path / "old"
    old.mkdir()
    (old / "campaign-result.json").write_text('{"tts_attempts":5}')
    root = tmp_path / "new"
    (root / "probe/native").mkdir(parents=True)
    (root / "probe/native/frontend.json").write_text(json.dumps(frontend()))
    (root / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", source_sha256=hashes))
    )
    monkeypatch.setattr(context.Q.assets, "PROJECT", project)
    monkeypatch.setattr(context.Q.assets, "ROOT", root)
    monkeypatch.setattr(context.original, "ROOT", old)
    monkeypatch.setattr(context, "predecessors", lambda: {"tts_attempts": 5})
    monkeypatch.setattr(context.Q.lifecycle, "prepared_integrity", lambda root: None)
    monkeypatch.setattr(context.Q.lifecycle, "verify_originals", lambda: {"fixture": 1})
    monkeypatch.setattr(context.Q.lifecycle, "local_state", lambda: {"native_pids": []})
    calls, closed = [], []

    class Worker:
        """Supply fake actual input traces without any local model dependency."""

        def __init__(self, mode, directory, deadline):
            """Bind one reference condition with a retained failure marker."""
            self.mode, self.failure = mode, None

        async def start(self):
            """Represent readiness without starting a process."""
            return self

        async def call(self, message):
            """Return a paired first-attempt result or the sole failing attempt."""
            calls.append(message)
            if failure:
                self.failure = "fixture"
                raise ValueError(self.failure)
            enabled = self.mode == "with_reference"
            return dict(
                reference_trace=dict(
                    mode=self.mode,
                    voice=message["voice"],
                    phonemes=message["text"],
                    token_ids=[44],
                    speaker_embedding_sha256="s",
                    projected_anchor_sha256="a",
                    prompt_text_ids=[16, 3, 44, 4],
                    use_ref_codes=enabled,
                    reference_rows=2 if enabled else 0,
                )
            )

        async def close(self, force):
            """Retain exact fake lifecycle retirement coverage."""
            closed.append(self.mode)

    monkeypatch.setattr(context.original, "ReferenceWorker", Worker)
    result = await context.run(root)
    assert len(result["rows"]) == 8 and result["asr_calls"] == result["core_calls"] == 0
    assert result["tts_attempts"] == len(calls) == (1 if failure else 8)
    assert result["combined_actual_attempts"] == (6 if failure else 13)
    assert result["unattempted"] == (7 if failure else 0)
    assert result["status"] == (
        "STOPPED_NO_RETRY" if failure else "CARRIER_PAIRS_COMPLETE_QUALITY_UNVERIFIED"
    )


def test_prior_actual_budget_cannot_be_silently_extended(tmp_path, monkeypatch):
    """Reject a follow-up that would exceed sixteen actual requests before loading or verifying any model."""
    (tmp_path / "campaign-result.json").write_text(
        '{"status":"STOPPED_NO_RETRY","tts_attempts":9}'
    )
    monkeypatch.setattr(context.original, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="budget"):
        context.predecessors()
