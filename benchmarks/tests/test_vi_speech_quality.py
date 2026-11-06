"""Test quality comparison denominators, protected operator reuse and model-free namespace boundaries."""

import time

import pytest

from benchmarks.scripts import vi_speech_quality as quality


def test_quality_panel_has_exact48_slots_and_preserves_display_text():
    """Keep fixed voices and each raw/reading/prosody input in its own immutable comparison lane."""
    rows = quality.packet_rows()
    assert len(rows) == 48 and len({r["id"] for r in rows}) == 48
    assert {r["voice"] for r in rows} == {"Trúc Ly", "Ngọc Huyền"}
    assert all(r["status"] == "UNATTEMPTED" for r in rows)
    source = dict(quality.CASES)
    for row in rows:
        assert row["render"]["source_text"] == source[row["case"]]
        if row["profile"] == "raw":
            assert row["render"]["speech_text"] == source[row["case"]]
    assert len([r for r in rows if r["profile"] == "clauses"]) == 16


def test_probe_namespace_cannot_access_any_model_or_audio_mount(tmp_path):
    """Remove all neural checkpoints and unused samples while retaining sealed CPU resource limits."""
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    command = quality.command(output, "raw", probe=True)
    mounts = [command[i + 2] for i, token in enumerate(command) if token == "--ro-bind"]
    assert not {"/model", "/hf/hub", "/samples"} & set(mounts)
    assert "--unshare-all" in command and "--as=8589934592" in command
    assert command[-1] == "--probe"
    assert (
        str(quality.assets.PROJECT / "benchmarks/scripts/vi_speech_worker.py")
        in command
    )


def test_native_quality_namespace_reuses_exact_original_model(tmp_path):
    """Keep offline CPU parameters and pinned payloads without executing the old recovery entry point."""
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    command = quality.command(output, "clauses")
    assert "/model" in command and "/hf/hub" in command
    assert "/samples" not in command and "--share-net" not in command
    assert command[-2:] == ["/app/benchmarks/scripts/vi_speech_worker.py", "clauses"]
    assert "--cpu=1200:1201" in command and "--clearenv" in command
    with pytest.raises(ValueError):
        quality.command(output, "unreviewed")


@pytest.mark.asyncio
async def test_quality_worker_never_loads_without_headroom(tmp_path, monkeypatch):
    """Reject insufficient RAM before constructing the native namespace or any output directory."""
    monkeypatch.setattr(quality.lifecycle, "mem_available", lambda: 0)
    worker = quality.QualityWorker("raw", tmp_path / "worker", time.monotonic() + 10)
    with pytest.raises(ValueError, match="preflight"):
        await worker.start()
    assert worker.process is None and not worker.directory.exists()


@pytest.mark.asyncio
async def test_existing_campaign_is_never_retried(tmp_path, monkeypatch):
    """Reject an existing execution freeze before authorization scans or model loading."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    monkeypatch.setattr(
        quality.lifecycle,
        "prepared_integrity",
        lambda root: pytest.fail("must not load"),
    )
    with pytest.raises(ValueError, match="already_attempted"):
        await quality.run(tmp_path)


@pytest.mark.asyncio
async def test_profile_mismatch_joins_owned_fixture(tmp_path, monkeypatch):
    """Reject a wrong readiness profile and join the actual local process without model loading."""
    import sys

    code = 'import json,time; print(json.dumps(dict(event="ready",candidate="turbo",profile="wrong")),flush=True);time.sleep(30)'
    monkeypatch.setattr(quality, "command", lambda *args: [sys.executable, "-c", code])
    monkeypatch.setattr(
        quality.lifecycle, "mem_available", lambda: 20 * quality.lifecycle.GIB
    )
    monkeypatch.setattr(quality.os, "sched_getaffinity", lambda pid: {0, 1})
    monkeypatch.setattr(quality.assets, "budget", lambda *args: 0)
    worker = quality.QualityWorker("raw", tmp_path / "worker", time.monotonic() + 10)
    with pytest.raises(ValueError, match="ready_binding"):
        await worker.start()
    assert worker.process.returncode is not None
    assert worker not in quality.lifecycle.WORKERS
    assert (worker.directory / "retirement.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_full_fake_panel_preserves48_denominator_and_stops_first_failure(
    tmp_path, monkeypatch, failure
):
    """Exercise the actual controller/freeze lifecycle with public fake events and zero model dependencies."""
    import json

    project = tmp_path / "project"
    evidence = project / "docs/evidence"
    evidence.mkdir(parents=True)
    (evidence / "d74-reading-quality-owner-authorization.json").write_text(
        '{"authorized":true}'
    )
    (evidence / "d74-adr155-proposed-workflow-recovery-20261103.json").write_text(
        '{"operator_sha256":{}}'
    )
    root = tmp_path / "root"
    root.mkdir()
    probe = root / "sentence-preserving-probe/native"
    probe.mkdir(parents=True)
    (probe / "normalizer-probe.json").write_text("{}")
    (root / "software-verification.json").write_text(
        '{"status":"PASS","operator_sha256":{}}'
    )
    monkeypatch.setattr(quality.assets, "PROJECT", project)
    monkeypatch.setattr(quality.assets, "ROOT", root)
    monkeypatch.setattr(quality.lifecycle, "prepared_integrity", lambda root: None)
    monkeypatch.setattr(quality.lifecycle, "verify_originals", lambda: {"fixture": 1})
    monkeypatch.setattr(quality.lifecycle, "local_state", lambda: {"native_pids": []})
    calls, retired = [], []

    class FakeWorker:
        """Return deterministic fake native events without importing any neural backend."""

        def __init__(self, profile, directory, deadline):
            """Bind the expected fixed profile and joined lifecycle state."""
            self.profile, self.failure = profile, None

        async def start(self):
            """Represent successful readiness without starting a process."""
            return self

        async def call(self, message):
            """Record the first attempt or inject the sole permitted failure."""
            calls.append(message)
            if failure:
                self.failure = "fixture_failure"
                raise ValueError(self.failure)
            return dict(generation_complete=True)

        async def close(self, force):
            """Record retirement of each admitted fake profile."""
            retired.append(self.profile)

    monkeypatch.setattr(quality, "QualityWorker", FakeWorker)
    result = await quality.run(root)
    assert result["asr_calls"] == 0 and result["core_calls"] == 0
    assert len(result["rows"]) == 48 and result["baseline_restored"] is True
    if failure:
        assert (
            len(calls) == 1
            and result["tts_attempts"] == 1
            and result["unattempted"] == 47
        )
        assert result["status"] == "STOPPED_NO_RETRY" and retired == ["raw"]
    else:
        assert (
            len(calls) == 48
            and result["tts_attempts"] == 48
            and result["unattempted"] == 0
        )
        assert result["status"] == "NATIVE_PANEL_COMPLETE_QUALITY_UNVERIFIED"
        assert retired == ["raw", "reading", "clauses"]
        assert {row["id"] for row in calls} == {row["id"] for row in result["rows"]}
    assert (
        json.loads((root / "campaign-result.json").read_text())["model_selection"]
        is None
    )
