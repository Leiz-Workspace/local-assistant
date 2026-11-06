"""Test complete resident scope, maximum-latency scoring, source binding and owned worker retirement without model loads."""

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from benchmarks.scripts import vi_voice_resident_check as target
from benchmarks.tests.test_vi_voice_presence import audio
from src.application.ports.inference import CompletionResult
from src.application.ports.voice import VoiceTranscript, VoiceSpeech
from src.application.services.voice_pipeline import VoicePipeline, digest


@pytest.fixture(autouse=True)
def isolate_owned_state(monkeypatch):
    """Keep failure/worker ownership local to each software control rather than affecting unrelated suites."""
    monkeypatch.setattr(target.original, "WORKERS", set())
    monkeypatch.setattr(target.original, "FAILURES", [])


def packet():
    """Declare four authored speech and two negative identities without using private recordings."""
    return dict(
        workflow_sources=[
            dict(id=("s" if i < 4 else "negative-") + str(i), expected_no_answer=i >= 4)
            for i in range(6)
        ]
    )


def test_all36slots_keep_original_order_and_both_models():
    """Freeze all6sources per2/4/8profile and retain negative slots instead of selecting only fast speech."""
    rows = target.matrix(packet())
    assert len(rows) == 36 and sum(x["expected_no_answer"] for x in rows) == 12
    assert [x["threads"] for x in rows[:18]] == [2] * 6 + [4] * 6 + [8] * 6
    assert [x["source"] for x in rows[:6]] == [
        x["id"] for x in packet()["workflow_sources"]
    ]


@pytest.mark.parametrize(
    "maximum,expected", [(4.0, True), (4.0000001, False), (8.0, False)]
)
def test_gate_uses_maximum_not_average_or_negative_time(maximum, expected):
    """Require every speech output within4seconds even when the other turns or negative refusals are fast."""
    rows = target.matrix(packet())
    for row in rows:
        row.update(
            status="CORRECT_NO_SPEECH" if row["expected_no_answer"] else "COMPLETE_PCM",
            buffered_latency_seconds=0.01 if row["expected_no_answer"] else 1.0,
        )
    rows[0]["buffered_latency_seconds"] = maximum
    gates = target.latency_gates(rows)
    assert gates[0]["compute_proxy_within4"] == expected
    assert gates[0]["maximum_complete_pcm_seconds"] == maximum
    assert all(x["physical_first_audible"] == "UNVERIFIED" for x in gates)


@pytest.mark.parametrize("bad", [None, True, float("nan"), float("inf"), 0, -1])
def test_missing_or_invalid_timings_cannot_pass(bad):
    """Keep incomplete/nonfinite or pseudo-numeric measurements outside performance acceptance."""
    rows = target.matrix(packet())
    for row in rows:
        row.update(
            status="CORRECT_NO_SPEECH" if row["expected_no_answer"] else "COMPLETE_PCM",
            buffered_latency_seconds=1.0,
        )
    rows[0]["buffered_latency_seconds"] = bad
    assert target.latency_gates(rows)[0]["compute_proxy_within4"] is False


@pytest.mark.parametrize(
    "role,threads",
    [
        ("vad", 2),
        ("turbo", 2),
        ("turbo", 4),
        ("turbo", 8),
        ("whisper-small-ct2", 4),
        ("qwen3-asr-0.6b", 8),
    ],
)
def test_namespace_changes_only_explicit_cpu_fields_and_entrypoint(
    monkeypatch, tmp_path, role, threads
):
    """Keep original memory/offline controls while exposing only declared thread allocation and readonly source capability."""

    def base(*args, **kwargs):
        """Provide an authored isolated command blueprint without touching private SDK files."""
        result = [
            "/usr/bin/taskset",
            "--cpu-list",
            "0,1",
            "/usr/bin/bwrap",
            "--unshare-all",
            "--setenv",
            "OMP_NUM_THREADS",
            "2",
            "--setenv",
            "PYTHONPATH",
            "/app:/sources",
            "--setenv",
            "CUDA_VISIBLE_DEVICES",
            "",
            "--remount-ro",
            "/",
            "--",
            "/usr/bin/prlimit",
            "--as=8589934592",
            "--",
            "/venv/bin/python",
            "/app/worker.py",
            "role",
        ]
        if len(args) == 3:
            i = result.index("--remount-ro")
            result[i:i] = ["--ro-bind", str(args[1]), "/approved-workflow.json"]
        return result

    def vad():
        """Provide the original detector's stricter address-space and network-disabled shape."""
        return [
            "/usr/bin/bwrap",
            "--unshare-all",
            "--ro-bind",
            str(target.old.VAD_ROOT / "samples"),
            "/samples",
            "--setenv",
            "PYTHONPATH",
            "/official",
            "--remount-ro",
            "/",
            "--",
            "/usr/bin/prlimit",
            "--as=3221225472",
            "--",
            "/venv/bin/python",
            "/app/worker.py",
        ]

    monkeypatch.setattr(target.original, "namespace", base)
    monkeypatch.setattr(target.reading.prepared, "command", base)
    monkeypatch.setattr(target.old, "sandbox", vad)
    result = target.command(
        role,
        tmp_path / "out",
        tmp_path / "scope.json",
        "a" * 64,
        threads,
        tmp_path / "samples",
    )
    assert result[result.index("--cpu-list") + 1] == ",".join(
        str(x) for x in range(threads)
    )
    assert ("--as=3221225472" if role == "vad" else "--as=8589934592") in result
    assert "--unshare-all" in result and result[-2:] == [
        "/app/" + target.WORKER,
        "a" * 64,
    ]
    assert str(tmp_path / "scope.json") in result


@pytest.mark.asyncio
async def test_detector_port_checks_exact_view_and_no_source_repair():
    """Reject a mismatched copy before dispatch and keep complete original timeline spans on a valid result."""
    view = target.detector_view(audio())
    calls = []

    async def detect(message):
        """Return authored original-model-shaped evidence bound to the request."""
        calls.append(message)
        return dict(
            waveform_sha256=view.waveform_sha256,
            sample_count=view.sample_count,
            source_samples_modified=False,
            external_recording_resets=1,
            segments=[dict(start=100, end=500)],
        )

    expected = dict(
        filename="one.f32",
        waveform_sha256=view.waveform_sha256,
        sample_count=view.sample_count,
    )
    backend = target.Backend(SimpleNamespace(detect=detect), {"id": "one"}, expected)
    result = await backend.observe(view)
    assert result.segments == ((100, 500),) and len(calls) == 1
    with pytest.raises(ValueError, match="binding"):
        await backend.observe(view)


def test_aggregate_memory_guard_includes_resident_detector(monkeypatch, tmp_path):
    """Do not evade the original8GiB limit by omitting the newly resident VAD process."""
    scope = tmp_path / "scope.json"
    scope.write_text("{}")
    worker = target.Worker(
        "whisper-small-ct2", tmp_path, time.monotonic() + 100, 9, scope, 2, tmp_path
    )
    worker.process = SimpleNamespace(pid=1, returncode=None)
    worker.started = time.monotonic()
    (tmp_path / "stderr.log").write_text("")
    monkeypatch.setattr(target.original, "WORKERS", {worker})

    class VAD:
        """Expose only the live detector identity needed by the aggregate guard."""

        process = SimpleNamespace(pid=2, returncode=None)

    target.original.WORKERS.add(VAD())
    monkeypatch.setattr(target.original, "process_tree", lambda pid: {pid})
    monkeypatch.setattr(
        target.original, "rss_bytes", lambda pid: {1: 6, 2: 2, 9: 1}[pid] * 1024**3
    )
    with pytest.raises(ValueError, match="aggregate_sampled_rss"):
        worker.check()
    assert worker.samples == 1


def test_worker_disk_budget_binds_current_campaign_root(tmp_path):
    """Keep polling/output limits scoped to the current campaign rather than the inherited historical root."""
    scope = tmp_path / "scope.json"
    scope.write_text("{}")
    root = tmp_path / "current-campaign"
    worker = target.Worker(
        "vad",
        tmp_path / "worker",
        time.monotonic() + 100,
        9,
        scope,
        2,
        tmp_path / "views",
        root=root,
    )
    assert worker.root == root and worker.root != target.original.ROOT


@pytest.mark.parametrize("outcome", ["success", "wrong_ready", "cancel", "headroom"])
@pytest.mark.asyncio
async def test_resident_start_binds_readiness_and_joins_failed_load(
    monkeypatch, tmp_path, outcome
):
    """Reject mismatched metadata or insufficient memory and join a started child on cancellation before admission."""
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps({"fixture": True}))
    worker = target.Worker(
        "whisper-small-ct2",
        tmp_path / "worker",
        time.monotonic() + 10,
        99,
        scope,
        4,
        tmp_path / "samples",
    )
    created = []
    closed = []
    entered = asyncio.Event()

    async def create(*args, **kwargs):
        """Return a fake owned process while checking isolation flags on the real start path."""
        assert kwargs["start_new_session"] is True
        created.append(True)
        return SimpleNamespace(pid=123456, returncode=None)

    async def receive():
        """Supply source-bound readiness or expose an interrupted loading operation."""
        entered.set()
        if outcome == "cancel":
            await asyncio.Event().wait()
        return dict(
            event="ready",
            candidate="whisper-small-ct2",
            manifest_sha256=worker.scope_sha,
            execution=dict(
                cpu_threads=3 if outcome == "wrong_ready" else 4,
                logical_CPU_affinity=[0, 1, 2, 3],
            ),
        )

    async def close(force=False):
        """Record exact retirement and close the real audit stream without touching host processes."""
        closed.append(force)
        worker.process.returncode = -9 if force else 0
        target.original.WORKERS.discard(worker)
        worker.log.close()

    monkeypatch.setattr(
        target.original,
        "mem_available",
        lambda: (13 if outcome == "headroom" else 20) * 1024**3,
    )
    monkeypatch.setattr(target, "command", lambda *args: ["fixed-worker"])
    monkeypatch.setattr(target.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(worker, "receive", receive)
    monkeypatch.setattr(worker, "close", close)
    if outcome == "cancel":
        task = asyncio.create_task(worker.start())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif outcome != "success":
        with pytest.raises(ValueError):
            await worker.start()
    else:
        assert await worker.start() is worker
        await worker.close()
    assert created == ([] if outcome == "headroom" else [True])
    assert closed == ([] if outcome == "headroom" else [outcome != "success"])
    assert not target.original.WORKERS


@pytest.mark.parametrize("fail_group", [False, True])
@pytest.mark.asyncio
async def test_resident_groups_join_every_worker_and_keep_unattempted_rows(
    monkeypatch, tmp_path, fail_group
):
    """Run actual original pipeline controls with fake stages and stop after the first resident-load fault."""
    for name in ("results", "samples", "manifests"):
        (tmp_path / name).mkdir()
    rows = target.matrix(packet())
    value = audio()
    all_workers = []
    stops = []

    class Server:
        """Provide an owned CORE lifecycle without native loading or network traffic."""

        failure = None

        def __init__(self, *args):
            """Record only a synthetic process identity for the test."""
            self.process = SimpleNamespace(pid=99)

        async def start(self):
            """Expose readiness without issuing model requests."""
            return self

        async def stop(self):
            """Record joined retirement for success and failure paths."""
            stops.append(True)

        def receipt(self):
            """Return finite authored lifecycle metadata."""
            return dict(exit_code=0, reaped=True)

    class Worker:
        """Stand in for a fixed model lifetime while exercising real pipeline admission."""

        def __init__(
            self, role, directory, deadline, pid, scope, threads, samples, *, root
        ):
            """Retain a per-group identity and finite state without subprocesses."""
            self.role, self.threads = role, threads
            assert root == tmp_path
            self.failure = None
            self.closed = False
            self.ready = {}
            all_workers.append(self)

        async def start(self):
            """Optionally fail the second group's final load and retire that failed owned worker."""
            if fail_group and self.threads == 4 and self.role == "turbo":
                self.closed = True
                raise ValueError("load fault")
            return self

        async def close(self, force=False):
            """Close the exact owned fake model before the next group can begin."""
            self.closed = True

        async def detect(self, message):
            """Return valid negative/speech evidence according to authored source identity only."""
            return dict(
                waveform_sha256=message["waveform_sha256"],
                sample_count=message["sample_count"],
                source_samples_modified=False,
                external_recording_resets=1,
                segments=[]
                if message["filename"].startswith("negative-")
                else [dict(start=1, end=500)],
            )

    def compose(asr, tts, state, aw, tw, slot, source, ledger, *args):
        """Keep the original VoicePipeline while replacing neural dependencies with explicit sentinels."""

        async def transcribe(owner, audio, language):
            """Count one actual-shaped ASR operation only after speech is admitted."""
            ledger.admit("asr", slot.name + "-asr")
            return VoiceTranscript(
                owner, audio.source_sha256, audio.pcm_sha256, language, "speech", asr
            )

        async def complete(**kwargs):
            """Count one CORE operation with the original complete-response contract."""
            ledger.admit("core", slot.name + "-core")
            return CompletionResult("answer", "qwen3.5-9b-core", "fast", "stop")

        async def synthesize(owner, text, language):
            """Count one complete authored speech output without invoking TTS."""
            ledger.admit("tts", slot.name + "-tts")
            return VoiceSpeech(
                owner,
                digest(text.encode()),
                language,
                target.reading.MODEL,
                b"\0\0" * 16000,
                16000,
            )

        asr_port = SimpleNamespace(transcribe=transcribe)
        pipeline = VoicePipeline(
            asr=asr_port,
            llm=SimpleNamespace(complete=complete),
            tts=SimpleNamespace(synthesize=synthesize),
            asr_model=asr,
            llm_model="qwen3.5-9b-core",
            tts_model=target.reading.MODEL,
        )
        return pipeline, asr_port, None

    monkeypatch.setattr(target.original, "OwnedServer", Server)
    monkeypatch.setattr(target, "Worker", Worker)
    monkeypatch.setattr(target.reading, "make_service", compose)
    sources = {x["id"]: dict(audio=value) for x in packet()["workflow_sources"]}
    view = target.detector_view(value)
    expected = {
        x: dict(
            filename=x + ".f32",
            sample_count=value.sample_count,
            waveform_sha256=view.waveform_sha256,
        )
        for x in sources
    }
    ledger = target.Ledger(tmp_path)
    if fail_group:
        with pytest.raises(ValueError, match="load fault"):
            await target.workflow(
                tmp_path,
                rows,
                sources,
                ledger,
                time.monotonic() + 10,
                {},
                "a" * 64,
                expected,
            )
        assert all(x["status"] == "UNATTEMPTED" for x in rows[6:])
    else:
        await target.workflow(
            tmp_path,
            rows,
            sources,
            ledger,
            time.monotonic() + 10,
            {},
            "a" * 64,
            expected,
        )
        assert ledger.counts == dict(asr=24, core=24, tts=24)
        assert sum(x["status"] == "CORRECT_NO_SPEECH" for x in rows) == 12
    assert stops == [True] and all(w.closed for w in all_workers)
