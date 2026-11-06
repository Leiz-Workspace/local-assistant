"""Verify exact native matrix authority, first-attempt budgets, manifest/readiness guards and joined campaign cleanup."""

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from benchmarks.scripts import vi_workflow_reading_native as trial
from benchmarks.scripts.vi_workflow_reading_policy import POLICY, VOICE
from benchmarks.scripts.vi_workflow_reading_worker import manifest
from src.application.services.voice_pipeline import VoiceError


def packet():
    """Declare four authored speech sources and two negatives without private audio or model assets."""
    return dict(
        workflow_sources=[
            dict(id=f"source-{index}", expected_no_answer=index >= 4)
            for index in range(6)
        ]
    )


def test_exact48matrix_preserves_all_sources_lanes_and_predeclared_order():
    """Keep every higher-RAM row visible while measuring the fixed lower-RAM reading lane first."""
    rows = trial.matrix(packet())
    assert len(rows) == len({row["id"] for row in rows}) == 48
    assert sum(row["expected_no_answer"] for row in rows) == 16
    assert (rows[0]["asr"], rows[0]["tts"], rows[0]["state"]) == (
        "whisper-small-ct2",
        "turbo",
        "fresh",
    )
    assert (rows[24]["asr"], rows[24]["tts"], rows[24]["state"]) == (
        "qwen3-asr-0.6b",
        "turbo",
        "fresh",
    )
    assert all(row["reading_policy"] == POLICY for row in rows if row["tts"] == "turbo")
    assert {row["source"] for row in rows} == {f"source-{index}" for index in range(6)}
    with pytest.raises(ValueError, match="coverage"):
        trial.matrix(dict(workflow_sources=packet()["workflow_sources"][:-1]))


def test_attempt_ceiling_has_no_standalone_allowance_and_does_not_refund_failure(
    tmp_path,
):
    """Consume exactly48first attempts for each kind and reject duplicate or extra dispatch before appending."""
    ledger = trial.Ledger(tmp_path)
    for kind in ("asr", "core", "tts"):
        for index in range(48):
            ledger.admit(kind, f"{kind}-{index}")
        with pytest.raises(ValueError):
            ledger.admit(kind, f"{kind}-extra")
        with pytest.raises(ValueError):
            ledger.admit(kind, f"{kind}-0")
    assert ledger.counts == dict(asr=48, core=48, tts=48)
    assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 144


def test_authority_binds_exact_limits_policy_and_unchanged_plan(tmp_path, monkeypatch):
    """Refuse scope drift rather than reusing a generic approval or changing the historical ADR155 entrypoint."""
    path = tmp_path / trial.AUTHORITY
    path.parent.mkdir(parents=True)
    decision = tmp_path / "decision.md"
    decision.write_text("Fixed owner-reviewed scope")
    monkeypatch.setattr(trial.original, "PROJECT", tmp_path)
    good = dict(
        authorized=True,
        slots=48,
        policy=POLICY,
        limits=dict(
            asr=48,
            core=48,
            tts=48,
            optional_recovery_core=2,
            retries=0,
            wall_seconds=3600,
        ),
        bindings={"decision.md": trial.original.assets.digest(decision)},
    )
    path.write_text(json.dumps(good))
    assert trial.authority() == path
    for changed in [
        dict(authorized=False),
        dict(slots=49),
        dict(policy="raw"),
        dict(limits={}),
    ]:
        path.write_text(json.dumps(dict(good, **changed)))
        with pytest.raises(ValueError):
            trial.authority()
    path.write_text(json.dumps(good))
    decision.write_text("Different scope")
    with pytest.raises(ValueError, match="drift"):
        trial.authority()


@pytest.mark.asyncio
async def test_headroom_failure_prevents_child_start_and_sets_fatal_guard(
    tmp_path, monkeypatch
):
    """Stop the whole matrix before dispatch if a reading worker cannot satisfy the original memory protection."""
    path = tmp_path / "manifest.json"
    path.write_text("{}")
    monkeypatch.setattr(trial.original, "FAILURES", [])
    monkeypatch.setattr(
        trial.original, "mem_available", lambda: 13 * trial.original.GIB
    )
    worker = trial.ReadingWorker(tmp_path / "worker", time.monotonic() + 60, 1, path)
    with pytest.raises(ValueError, match="preflight"):
        await worker.start()
    assert worker.process is None and trial.original.FAILURES == [
        "reading_workflow_worker_preflight"
    ]
    assert not (tmp_path / "worker").exists()


@pytest.mark.asyncio
async def test_wrong_ready_manifest_is_fatal_and_owned_child_is_joined(
    tmp_path, monkeypatch
):
    """Reject a raw/wrong-scope worker before any speech call and preserve fatal startup state."""
    path = tmp_path / "manifest.json"
    path.write_text("{}")
    monkeypatch.setattr(trial.original, "FAILURES", [])
    monkeypatch.setattr(trial.original, "WORKERS", set())
    monkeypatch.setattr(
        trial.original, "mem_available", lambda: 20 * trial.original.GIB
    )
    monkeypatch.setattr(trial.os, "sched_getaffinity", lambda pid: {0, 1})
    closed = []

    async def spawn(*args, **kwargs):
        """Provide an authored process identity without executing a command."""
        return SimpleNamespace(pid=123, returncode=0)

    async def receive(self):
        """Return a deliberately wrong scope despite matching other readiness fields."""
        return dict(
            event="ready",
            candidate="turbo",
            profile="workflow-reading",
            voice=VOICE,
            reading_policy=POLICY,
            manifest_sha256="wrong",
        )

    async def close(self, force=False):
        """Confirm disposal of the only owned child and its log after startup rejection."""
        closed.append(force)
        trial.original.WORKERS.discard(self)
        self.log.close()

    monkeypatch.setattr(trial.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(trial.ReadingWorker, "receive", receive)
    monkeypatch.setattr(trial.ReadingWorker, "close", close)
    worker = trial.ReadingWorker(tmp_path / "worker", time.monotonic() + 60, 1, path)
    with pytest.raises(ValueError, match="readiness_binding"):
        await worker.start()
    assert closed == [True] and trial.original.FAILURES and not trial.original.WORKERS


@pytest.mark.asyncio
async def test_manifest_factory_only_admits_one_or_six_bound_requests(
    tmp_path, monkeypatch
):
    """Keep cold and resident worker capabilities finite, policy-fixed and tied to the actual frozen scope."""
    (tmp_path / "manifests").mkdir()
    captured = []

    class FakeWorker:
        """Observe the exact published capability without loading a model."""

        def __init__(self, directory, deadline, core_pid, path):
            """Validate the actual manifest produced by the campaign factory."""
            captured.append(manifest(json.loads(path.read_text())))

        async def start(self):
            """Represent readiness without creating a process."""
            return self

    monkeypatch.setattr(trial, "ReadingWorker", FakeWorker)
    for maximum in (1, 6):
        await trial.reading_worker(
            tmp_path, tmp_path / f"role-{maximum}" / "tts", 100, 1, "a" * 64, maximum
        )
    with pytest.raises(ValueError):
        await trial.reading_worker(
            tmp_path, tmp_path / "other" / "tts", 100, 1, "a" * 64, 2
        )
    assert [row["max_requests"] for row in captured] == [1, 6]
    assert all(row["scope_sha256"] == "a" * 64 for row in captured)


@pytest.mark.parametrize("failure", [None, "quality", "resource", "cancel"])
@pytest.mark.asyncio
async def test_actual_orchestrator_preserves48or_first_failure_and_joins_all_owners(
    tmp_path, monkeypatch, failure
):
    """Exercise fixed grouping, negative short-circuiting, finite counters and fatal first-outcome cleanup with authored stages."""
    (tmp_path / "results").mkdir()
    (tmp_path / "manifests").mkdir()
    rows = trial.matrix(packet())
    sources = {
        row["id"]: dict(audio=row["id"], negative=row["expected_no_answer"])
        for row in packet()["workflow_sources"]
    }
    ledger = trial.Ledger(tmp_path)
    events, closed_services, scopes = [], [], []
    monkeypatch.setattr(trial.original, "FAILURES", [])

    class Worker:
        """Record original-model role lifecycle without native inference."""

        def __init__(self, candidate, directory, deadline, core_pid=None):
            """Retain the fixed candidate and initially clean state."""
            self.candidate, self.failure = candidate, None

        async def start(self):
            """Record one owned startup and return the same object."""
            events.append(("start", self.candidate))
            return self

        async def close(self, force=False):
            """Record joined cleanup for fresh or resident role ownership."""
            events.append(("close", self.candidate))

    class Server:
        """Supply the owned CORE interface without an HTTP endpoint or model process."""

        def __init__(self, *args):
            """Initialize one explicit owner identity and clean guard."""
            self.failure, self.process = None, SimpleNamespace(pid=1)

        async def start(self):
            """Record the owned server startup."""
            events.append(("server", "start"))

        async def stop(self):
            """Record final joined server cleanup under every outcome."""
            events.append(("server", "stop"))

        def receipt(self):
            """Expose an authored zero-failure retirement observation."""
            return dict(reaped=True, exit_code=0)

    async def reading(root, directory, deadline, core_pid, sha, maximum):
        """Observe fixed one-or-six reading capabilities without touching real assets."""
        scopes.append(maximum)
        return await Worker("turbo", directory, deadline).start()

    def service_factory(
        asr,
        tts,
        state,
        resident_asr,
        resident_tts,
        slot,
        source,
        count,
        deadline,
        pid,
        factory,
        binding,
    ):
        """Build authored stages while exercising the actual campaign loop and dependency ownership."""
        a = SimpleNamespace(worker=resident_asr, owned=resident_asr is None)
        t = SimpleNamespace(worker=resident_tts, owned=resident_tts is None)

        class Service:
            """Represent source/model-bound stage ordering without claiming native results."""

            async def complete(self, *args, **kwargs):
                """Consume actual attempt ledger entries and preserve first quality/resource/cancel outcomes."""
                if a.worker is None:
                    a.worker = await Worker(asr, slot / "asr", deadline).start()
                count.admit("asr", slot.name + "-asr")
                if slot.name == rows[0]["id"] and failure:
                    if failure == "resource":
                        a.worker.failure = "fixture-resource"
                        trial.original.FAILURES.append("fixture-resource")
                    if failure == "cancel":
                        raise asyncio.CancelledError()
                    raise VoiceError("dependency_failed")
                if source["negative"]:
                    raise VoiceError("no_speech")
                count.admit("core", slot.name + "-core")
                if t.worker is None:
                    t.worker = (
                        await factory(slot / "tts", deadline, pid)
                        if tts == "turbo"
                        else await Worker(tts, slot / "tts", deadline).start()
                    )
                count.admit("tts", slot.name + "-tts")
                return SimpleNamespace(
                    stage_seconds=(("asr", 0.1), ("llm", 0.1), ("tts", 0.1))
                )

            async def shutdown(self):
                """Record per-slot service shutdown before owned dependencies are released."""
                closed_services.append(slot.name)

        return Service(), a, t

    monkeypatch.setattr(trial.original, "Worker", Worker)
    monkeypatch.setattr(trial.original, "OwnedServer", Server)
    monkeypatch.setattr(trial, "reading_worker", reading)
    monkeypatch.setattr(trial, "make_service", service_factory)
    if failure in {"resource", "cancel"}:
        with pytest.raises(
            asyncio.CancelledError if failure == "cancel" else ValueError
        ):
            await trial.workflow(
                tmp_path, sources, ledger, time.monotonic() + 60, rows, "a" * 64, {}
            )
        assert (
            len(closed_services) == 1
            and sum(row["status"] == "UNATTEMPTED" for row in rows) == 47
        )
        assert ledger.counts == dict(asr=1, core=0, tts=0)
    else:
        await trial.workflow(
            tmp_path, sources, ledger, time.monotonic() + 60, rows, "a" * 64, {}
        )
        assert (
            len(closed_services) == 48
            and sum(row["status"] == "CORRECT_NO_SPEECH" for row in rows) == 16
        )
        assert ledger.counts == dict(
            asr=48, core=31 if failure else 32, tts=31 if failure else 32
        )
        assert sum(row["status"] == "FAILED" for row in rows) == (1 if failure else 0)
        assert scopes.count(6) == 2 and all(value in {1, 6} for value in scopes)
    assert events[-1] == ("server", "stop")
    assert sum(kind == "start" for kind, _ in events) == sum(
        kind == "close" for kind, _ in events
    )


@pytest.mark.asyncio
async def test_consumed_campaign_cannot_dispatch_or_request_new_authority(tmp_path):
    """Refuse replay before any model asset or approval inspection."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    with pytest.raises(ValueError, match="already_attempted"):
        await trial.run(tmp_path)


@pytest.mark.asyncio
async def test_run_preserves_first_failure_counts_freeze_and47unattempted(
    tmp_path, monkeypatch
):
    """Exercise the actual run wrapper's immutable freeze, stop-without-retry and baseline accounting without native work."""
    project = tmp_path / "project"
    project.mkdir()
    authority = project / "authority.json"
    authority.write_text("{}")
    hashes = {}
    for name in trial.SOURCES:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""Fixture."""\n')
        hashes[name] = trial.original.assets.digest(path)
    source = project / "packet.json"
    source.write_text(json.dumps(packet()))
    (tmp_path / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", source_sha256=hashes))
    )
    monkeypatch.setattr(trial.original, "PROJECT", project)
    monkeypatch.setattr(trial.original.assets, "PACKET", source)
    monkeypatch.setattr(trial.original, "WORKERS", set())
    monkeypatch.setattr(trial.original, "FAILURES", [])
    monkeypatch.setattr(trial, "authority", lambda: authority)
    monkeypatch.setattr(trial, "verify_previous", lambda: ({}, {}))
    monkeypatch.setattr(trial.original, "prepared_integrity", lambda root: None)
    monkeypatch.setattr(trial.original, "verify_originals", lambda: {"fixture": 1})
    monkeypatch.setattr(trial.original, "local_state", lambda: {"native_pids": []})
    monkeypatch.setattr(trial.original, "verify_models", lambda: None)
    monkeypatch.setattr(trial.original, "verify_runtime_snapshot", lambda: None)
    monkeypatch.setattr(trial.original, "retained_sources", lambda *args: {})

    async def failed(root, sources, ledger, deadline, rows, scope, binding):
        """Consume one first ASR attempt and expose a fatal native failure without repair."""
        rows[0]["status"] = "FAILED"
        ledger.admit("asr", rows[0]["id"] + "-asr")
        raise ValueError("fixture-native-failure")

    monkeypatch.setattr(trial, "workflow", failed)
    result = await trial.run(tmp_path)
    assert result["status"] == "STOPPED_NO_RETRY" and result["unattempted"] == 47
    assert result["calls"] == dict(asr=1, core=0, tts=0) and result["baseline_restored"]
    assert (tmp_path / "execution-freeze.json").exists() and (
        tmp_path / "campaign-result.json"
    ).exists()
