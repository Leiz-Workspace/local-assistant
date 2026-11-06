"""Own the ADR-154 conditional CPU voice campaign while preserving passed application components."""

import argparse
import asyncio
import hashlib
import io
import itertools
import json
import logging
import os
import signal
import stat
import time
import wave
from pathlib import Path
from uuid import uuid4

import numpy as np

from benchmarks.scripts import vi_voice_preparation as assets
from benchmarks.scripts.d14_completion import OwnedServer, local_state
from scripts.asr_evaluation_assets import ROOT as ASR_ROOT, verify_file
from scripts.tts_evaluation import model_directory
from scripts.tts_evaluation_assets import (
    ROOT as TTS_ROOT,
    verify_models,
    verify_runtime_snapshot,
)
from src.application.ports.inference import CompletionResult
from src.application.ports.voice import VoiceSpeech, VoiceTranscript
from src.application.services.voice_pipeline import VoicePipeline
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.infrastructure.audio_normalizer import NativeAudioNormalizer
from apps.api.services.llama_gateway import LlamaGateway

LOGGER = logging.getLogger(__name__)
GIB = 1024**3
ROOT = assets.ROOT
PROJECT = assets.PROJECT
QUALIFICATION_TEXT = "Chị sẽ nhắc bạn vào sáng mai."
WORKERS = set()
FAILURES = []


def sha(raw):
    """Hash immutable byte payloads without exposing speech content in operational logs."""
    return hashlib.sha256(raw).hexdigest()


def verify_originals():
    """Require every retained application and protected evidence file to match the prior survey snapshot."""
    baseline = json.loads(
        (PROJECT / "data/backups/d74-vi-survey-20261103-prestate.json").read_text()
    )
    counts = {}
    for key in ["application_sha256", "protected_sha256"]:
        for name, expected in baseline[key].items():
            path = Path(name)
            if not path.is_absolute():
                path = PROJECT / path
            if assets.digest(path) != expected:
                raise ValueError("original_input_changed")
        counts[key] = len(baseline[key])
    LOGGER.info(
        "original_inputs_verified application=%d protected=%d", *counts.values()
    )
    return counts


def prepared_integrity(root):
    """Recheck all prepared SDK/source/model bytes before executing an approved frozen operator."""
    receipt = json.loads((root / "audit-completion-receipt.json").read_text())
    if receipt["status"] != "PREPARED_NOT_EXECUTED" or len(receipt["downloads"]) != 16:
        raise ValueError("campaign_preparation_incomplete")
    inventory = json.loads((root / "prepared-inventory.json").read_text())["files"]
    for name, info in inventory.items():
        path = root / name
        if "target" in info:
            if not path.is_symlink() or os.readlink(path) != info["target"]:
                raise ValueError("sdk_link_changed")
        elif (
            path.is_symlink()
            or path.stat().st_size != info["bytes"]
            or assets.digest(path) != info["sha256"]
        ):
            raise ValueError("sdk_or_asset_changed")
    for directory in ["sources", "venv", "models"]:
        current = assets.inventory(root / directory)
        expected = {
            name.removeprefix(directory + "/"): info
            for name, info in inventory.items()
            if name.startswith(directory + "/")
        }
        if current != expected:
            raise ValueError("prepared_inventory_addition_or_removal")
    assets.audit_sdk(root / "venv")
    LOGGER.info("prepared_integrity_verified entries=%d", len(inventory))


def pcm_wave(raw, rate):
    """Quantize a separate PCM16 WAV without gain changes, trimming or modifying native float bytes."""
    samples = np.frombuffer(raw, dtype="<f4")
    if (
        rate not in {16000, 22050, 48000}
        or not 1 <= len(samples) <= rate * 20
        or not np.isfinite(samples).all()
        or np.abs(samples).max() > 1
    ):
        raise ValueError("playback_conversion_bound")
    converted = (
        np.rint(np.where(samples < 0, samples * 32768, samples * 32767))
        .astype("<i2")
        .tobytes()
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(converted)
    return output.getvalue()


def read_native(directory, identity, result):
    """Independently verify exact private native float/WAV output and genuine generation completion."""
    from benchmarks.scripts.vi_voice_worker import native_bytes

    contents = []
    for suffix in ["f32", "wav"]:
        path = directory / (identity + "." + suffix)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_mode & 0o077
                or info.st_size > 16 * 1024**2
            ):
                raise ValueError("native_output_capability")
            contents.append(stream.read(16 * 1024**2 + 1))
    raw, wav = contents
    values = np.frombuffer(raw, dtype="<f4")
    expected_raw, expected_wav = native_bytes(values, result["sample_rate"])
    if (
        raw != expected_raw
        or wav != expected_wav
        or sha(raw) != result["native_sha256"]
        or sha(wav) != result["wav_sha256"]
        or len(values) != result["samples"]
        or result["channels"] != 1
        or result["dtype"] != "float32"
    ):
        raise ValueError("native_output_integrity")
    if result["generation_complete"] is not True:
        raise ValueError("native_generation_did_not_end")
    return raw


def process_tree(pid):
    """Sample descendants through procfs without touching unrelated host processes."""
    found, pending = set(), [pid]
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        try:
            for task in Path(f"/proc/{current}/task").iterdir():
                pending.extend(int(x) for x in (task / "children").read_text().split())
        except (FileNotFoundError, ProcessLookupError):
            pass
    return found


def rss_bytes(pid):
    """Return sampled resident bytes for one process, treating an already retired child as zero."""
    try:
        return next(
            int(line.split()[1]) * 1024
            for line in Path(f"/proc/{pid}/status").read_text().splitlines()
            if line.startswith("VmRSS:")
        )
    except (FileNotFoundError, StopIteration, ProcessLookupError):
        return 0


def mem_available():
    """Read the current available host RAM without implying reservation or substituting free VRAM."""
    return next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )


def namespace(candidate, output, root=ROOT):
    """Expose only the selected model, SDK, neutral packet and one owned output inside an offline CPU namespace."""
    if candidate not in {"turbo", "piper-vi", "qwen3-asr-0.6b", "whisper-small-ct2"}:
        raise ValueError("namespace_candidate")
    if (
        output.is_symlink()
        or not output.is_dir()
        or any(output.iterdir())
        or output.stat().st_mode & 0o077
    ):
        raise ValueError("namespace_output")
    if candidate == "turbo":
        venv, source = root / "venv", root / "sources/src"
        model = (
            root
            / "models/models--pnnbao-ump--VieNeu-TTS-v3-Turbo/snapshots/61b85e3d937fbbacb387714180e8182823512523"
        )
    elif candidate == "piper-vi":
        venv, source, model = (
            TTS_ROOT / "venv",
            TTS_ROOT / "runtime-source/piper-curated",
            model_directory("piper-vi"),
        )
    else:
        plan = json.loads(
            (PROJECT / "configs/asr-evaluation-candidates.json").read_text()
        )
        selected = next(x for x in plan["candidates"] if x["id"] == candidate)
        venv, source, model = (
            ASR_ROOT / "venv",
            ASR_ROOT
            / "runtime-source"
            / (
                "qwen-backend-source"
                if candidate == "qwen3-asr-0.6b"
                else "faster-whisper-source"
            ),
            ASR_ROOT / "models" / candidate / selected["revision"],
        )
    command = [
        "/usr/bin/taskset",
        "--cpu-list",
        "0,1",
        "/usr/bin/bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
    ]
    for host, guest in [
        (venv, "/venv"),
        (source, "/sources"),
        (model, "/model"),
        (root / "samples", "/samples"),
        (root / "identity/passwd", "/etc/passwd"),
        (root / "identity/group", "/etc/group"),
    ]:
        command += ["--ro-bind", str(host), guest]
    for name in [
        "tts_evaluation_worker.py",
        "tts_waveform.py",
        "asr_evaluation_worker.py",
    ]:
        command += [
            "--ro-bind",
            str(PROJECT / "scripts" / name),
            "/app/scripts/" + name,
        ]
    command += [
        "--ro-bind",
        str(PROJECT / "benchmarks/scripts/vi_voice_worker.py"),
        "/app/worker.py",
    ]
    if candidate == "turbo":
        command += ["--ro-bind", str(root / "models"), "/hf/hub"]
    command += [
        "--bind",
        str(output),
        "/output",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        str(128 * 1024**2),
        "--tmpfs",
        "/tmp",
        "--chdir",
        "/app",
    ]
    environment = dict(
        PATH="/venv/bin:/usr/bin",
        PYTHONPATH="/app:/sources",
        HOME="/tmp",
        USER="asr-evaluation",
        LOGNAME="asr-evaluation",
        LANG="C.UTF-8",
        PYTHONDONTWRITEBYTECODE="1",
        CUDA_VISIBLE_DEVICES="",
        HF_HOME="/hf",
        HF_HUB_CACHE="/hf/hub",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
        OPENBLAS_NUM_THREADS="2",
        NUMBA_NUM_THREADS="2",
        RAYON_NUM_THREADS="2",
        TOKENIZERS_PARALLELISM="false",
        NUMBA_CACHE_DIR="/tmp/numba",
    )
    for name, value in environment.items():
        command += ["--setenv", name, value]
    return command + [
        "--remount-ro",
        "/",
        "--",
        "/usr/bin/prlimit",
        "--as=8589934592",
        "--cpu=1200:1201",
        "--nofile=128",
        "--fsize=16777216",
        "--core=0",
        "--",
        "/venv/bin/python",
        "/app/worker.py",
        candidate,
    ]


class Worker:
    """Own one nonqueued research process with bounded stdout, resource sampling and joined shutdown."""

    def __init__(self, candidate, directory, deadline, root=ROOT, core_pid=None):
        """Bind a unique process/output capability and approved global deadline before startup."""
        self.candidate, self.directory, self.deadline, self.root, self.core_pid = (
            candidate,
            directory,
            deadline,
            root,
            core_pid,
        )
        self.process, self.log, self.started, self.ready = None, None, None, None
        self.peak_rss, self.samples, self.busy = 0, 0, False
        self.wall_limit = 600 if candidate in {"turbo", "piper-vi"} else 900
        self.failure = None

    def check(self):
        """Enforce wall, sampled per-worker/aggregate RAM, log and total root bounds."""
        now = time.monotonic()
        if now > self.deadline or now - self.started > self.wall_limit:
            raise TimeoutError("campaign_or_worker_wall")
        own = sum(rss_bytes(pid) for pid in process_tree(self.process.pid))
        self.peak_rss = max(self.peak_rss, own)
        self.samples += 1
        if self.candidate in {"turbo", "piper-vi"} and own > 2 * GIB:
            raise ValueError("tts_sampled_rss_ceiling")
        aggregate = sum(
            sum(rss_bytes(pid) for pid in process_tree(w.process.pid))
            for w in WORKERS
            if w.process is not None and w.process.returncode is None
        )
        if self.core_pid:
            aggregate += sum(rss_bytes(pid) for pid in process_tree(self.core_pid))
        if aggregate > 8 * GIB:
            raise ValueError("aggregate_sampled_rss_ceiling")
        if (self.directory / "stderr.log").stat().st_size > 8 * 1024**2:
            raise ValueError("worker_stderr_bound")

    async def receive(self):
        """Await one event while keeping all active workers guarded and cancellation joined by the caller."""
        task = asyncio.create_task(self.process.stdout.readline())
        last_budget = 0
        try:
            while not task.done():
                for worker in list(WORKERS):
                    worker.check()
                if time.monotonic() - last_budget > 1:
                    assets.budget(self.root)
                    last_budget = time.monotonic()
                await asyncio.wait({task}, timeout=0.05)
            raw = task.result()
            if not raw or len(raw) > 65536 or not raw.endswith(b"\n"):
                raise ValueError("worker_event_bound_or_exit")
            value = json.loads(raw)
            with (self.directory / "events.jsonl").open("ab") as stream:
                stream.write(raw)
            return value
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def start(self):
        """Load a fresh offline CPU worker only with approved headroom and retain its readiness event."""
        if (
            self.process is not None
            or mem_available() < 14 * GIB
            or not {0, 1} <= os.sched_getaffinity(0)
        ):
            self.failure = "worker_preflight"
            FAILURES.append(self.failure)
            raise ValueError("worker_preflight")
        self.directory.mkdir(mode=0o700)
        output = self.directory / "native"
        output.mkdir(mode=0o700)
        self.started = time.monotonic()
        self.log = (self.directory / "stderr.log").open("xb")
        command = namespace(self.candidate, output, self.root)
        assets.publish(
            self.directory / "launch.json",
            dict(
                description="Isolated CPU original runtime launch; no retry.",
                command=command,
                available_ram=mem_available(),
            ),
        )
        self.process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=self.log,
            start_new_session=True,
            limit=65537,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        assets.publish(
            self.directory / "process-identity.json",
            dict(
                description="Exact owned namespace process identity for audit and joined retirement.",
                pid=self.process.pid,
            ),
        )
        WORKERS.add(self)
        try:
            self.ready = await self.receive()
            if (
                self.ready.get("event") != "ready"
                or self.ready.get("candidate") != self.candidate
            ):
                raise ValueError("worker_ready_binding")
            LOGGER.info("campaign_worker_ready candidate=%s", self.candidate)
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            FAILURES.append(self.failure)
            await self.close(force=True)
            raise
        return self

    async def call(self, message):
        """Admit exactly one complete request and retain it before awaiting a matching first result."""
        from benchmarks.scripts.vi_voice_worker import validate_message

        validate_message(message)
        if self.busy or self.process is None or self.process.returncode is not None:
            raise ValueError("worker_busy_or_closed")
        self.busy = True
        try:
            assets.publish(
                self.directory / (message["id"] + "-request.json"),
                dict(
                    description="One uncached public/synthetic request; no reference transcript or negative label.",
                    **message,
                ),
            )
            self.process.stdin.write(
                json.dumps(message, ensure_ascii=False).encode() + b"\n"
            )
            await self.process.stdin.drain()
            result = await self.receive()
            if (
                result.get("event") != "result"
                or result.get("id") != message["id"]
                or result.get("operation") != message["op"]
            ):
                raise ValueError("worker_result_binding")
            if message["op"] == "synthesize":
                read_native(self.directory / "native", message["id"], result)
            return result
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            FAILURES.append(self.failure)
            await self.close(force=True)
            raise
        finally:
            self.busy = False

    async def close(self, force=False):
        """Close admission and join the owned namespace, escalating only this process group on failure."""
        if self.process is None:
            return
        if not force and self.process.returncode is None:
            try:
                self.process.stdin.write(b'{"op":"close"}\n')
                await self.process.stdin.drain()
                event = await asyncio.wait_for(self.receive(), timeout=3)
                if event.get("event") != "closed":
                    raise ValueError("worker_close_event")
                await asyncio.wait_for(self.process.wait(), timeout=3)
            except BaseException as error:
                self.failure = self.failure or type(error).__name__ + ":" + str(error)
                force = True
        if self.process.returncode is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3)
            except TimeoutError:
                os.killpg(self.process.pid, signal.SIGKILL)
                await asyncio.wait_for(self.process.wait(), timeout=5)
        WORKERS.discard(self)
        self.log.close()
        if not (self.directory / "retirement.json").exists():
            assets.publish(
                self.directory / "retirement.json",
                dict(
                    description="Joined owned namespace; sampled RSS is not reserved RAM.",
                    pid=self.process.pid,
                    returncode=self.process.returncode,
                    peak_sampled_rss_bytes=self.peak_rss,
                    resource_samples=self.samples,
                    wall_seconds=time.monotonic() - self.started,
                    failure=self.failure,
                    forced=force,
                ),
            )
        LOGGER.info(
            "campaign_worker_retired candidate=%s exit=%s",
            self.candidate,
            self.process.returncode,
        )
        if not force and (self.process.returncode or self.failure):
            raise ValueError("worker_cleanup_failed")


class Ledger:
    """Record attempted native requests before dispatch and prevent hidden retries or count overruns."""

    def __init__(self, root):
        """Bind a fresh exclusive ledger and campaign-wide request ceilings."""
        self.path = root / "calls.jsonl"
        self.path.touch(mode=0o600, exist_ok=False)
        self.counts = dict(tts=0, asr=0, core=0)
        self.seen = set()

    def admit(self, kind, identity):
        """Consume one approved attempt before dispatch, including requests that later fail."""
        if (
            kind not in self.counts
            or identity in self.seen
            or self.counts[kind] >= dict(tts=74, asr=48, core=50)[kind]
        ):
            raise ValueError("campaign_call_ceiling_or_duplicate")
        self.seen.add(identity)
        self.counts[kind] += 1
        with self.path.open("a") as stream:
            stream.write(
                json.dumps(dict(kind=kind, id=identity, monotonic=time.monotonic()))
                + "\n"
            )
        LOGGER.info(
            "campaign_call_admitted kind=%s count=%d id=%s",
            kind,
            self.counts[kind],
            identity,
        )


def prepare_samples(root, packet):
    """Retain explicit port quantization separately from six unchanged D72 source waveforms and references."""
    directory = root / "samples"
    directory.mkdir(mode=0o700)
    result = {}
    for case in packet["workflow_sources"]:
        raw = (PROJECT / case["waveform_path"]).read_bytes()
        if sha(raw) != case["waveform_sha256"] or len(raw) != case["sample_count"] * 4:
            raise ValueError("workflow_source_changed")
        started = time.perf_counter()
        audio = NativeAudioNormalizer().normalize(pcm_wave(raw, 16000))
        floats = (
            (
                np.frombuffer(audio.pcm_s16le, dtype="<i2").astype(np.float32)
                / np.float32(32768)
            )
            .astype("<f4")
            .tobytes()
        )
        path = directory / (case["id"] + ".f32")
        with path.open("xb") as stream:
            stream.write(floats)
        result[case["id"]] = dict(
            audio=audio,
            request=dict(
                filename=path.name,
                sample_count=audio.sample_count,
                waveform_sha256=sha(floats),
            ),
            source_sha256=sha(raw),
            port_quantization_seconds=time.perf_counter() - started,
        )
    return result


class ResearchASR:
    """Bind a research worker to the original pipeline source/owner fences without reference-label input."""

    def __init__(self, candidate, worker, slot, source, ledger, deadline, core_pid):
        """Bind one turn to a fixed ASR lane and either a resident or fresh worker."""
        self.candidate, self.worker, self.slot, self.source, self.ledger = (
            candidate,
            worker,
            slot,
            source,
            ledger,
        )
        self.deadline, self.core_pid, self.owned = deadline, core_pid, worker is None

    async def transcribe(self, owner, audio, language):
        """Perform exactly one original prediction and preserve empty/refused or unedited capped output."""
        if audio.pcm_sha256 != self.source["audio"].pcm_sha256 or language != "vi":
            raise ValueError("asr_source_fence")
        if self.worker is None:
            self.worker = await Worker(
                self.candidate, self.slot / "asr", self.deadline, core_pid=self.core_pid
            ).start()
        self.ledger.admit("asr", self.slot.name + "-asr")
        result = await self.worker.call(
            dict(op="transcribe", id=self.slot.name + "-asr", **self.source["request"])
        )
        assets.publish(
            self.slot / "asr-result.json",
            dict(
                description="Original unedited ASR output; retained references are outside worker mounts.",
                **result,
            ),
        )
        if self.owned:
            await self.worker.close()
        prediction = result["asr"]
        return VoiceTranscript(
            owner,
            audio.source_sha256,
            audio.pcm_sha256,
            language,
            prediction["text"],
            self.candidate,
            not prediction["output_cap_reached"],
        )


class ResearchTTS:
    """Bind one fixed experimental voice to the original full-output pipeline without changing defaults."""

    def __init__(self, candidate, worker, slot, ledger, deadline, core_pid):
        """Bind the predetermined voice and optional resident worker before receiving CORE output."""
        self.candidate, self.worker, self.slot, self.ledger = (
            candidate,
            worker,
            slot,
            ledger,
        )
        self.deadline, self.core_pid, self.owned = deadline, core_pid, worker is None
        self.model_id = "vieneu-v3-turbo-truc-ly" if candidate == "turbo" else candidate

    async def synthesize(self, owner, answer, language):
        """Retain complete native output before separately converting it into bounded mono16k playback PCM."""
        if language != "vi":
            raise ValueError("tts_language_fence")
        if self.worker is None:
            self.worker = await Worker(
                self.candidate, self.slot / "tts", self.deadline, core_pid=self.core_pid
            ).start()
        identity = self.slot.name + "-tts"
        self.ledger.admit("tts", identity)
        result = await self.worker.call(
            dict(
                op="synthesize",
                id=identity,
                text=answer,
                voice="Trúc Ly" if self.candidate == "turbo" else "piper-vi",
            )
        )
        started = time.perf_counter()
        raw = read_native(self.worker.directory / "native", identity, result)
        normalized = NativeAudioNormalizer().normalize(
            pcm_wave(raw, result["sample_rate"])
        )
        conversion_seconds = time.perf_counter() - started
        assets.publish(
            self.slot / "playback-conversion.json",
            dict(
                description="Separate unchanged native output and mono16k playback conversion; no physical audibility measurement.",
                native_sha256=sha(raw),
                native_sample_rate=result["sample_rate"],
                playback_sha256=normalized.pcm_sha256,
                conversion_seconds=conversion_seconds,
                sample_count=normalized.sample_count,
            ),
        )
        with (self.slot / "playback.s16le").open("xb") as stream:
            stream.write(normalized.pcm_s16le)
        if self.owned:
            await self.worker.close()
        return VoiceSpeech(
            owner,
            sha(answer.encode()),
            language,
            self.model_id,
            normalized.pcm_s16le,
            normalized.sample_count,
        )


class ResearchCORE:
    """Use the original gateway Fast512 contract on the owned original CORE endpoint without result caching."""

    def __init__(self, slot, ledger):
        """Bind one exclusive workflow request receipt and the campaign-wide CORE ledger."""
        self.slot, self.ledger = slot, ledger

    async def complete(self, **kwargs):
        """Forward the unchanged pipeline request through the existing verified gateway and retain the first full response."""
        if (
            kwargs["profile"] != "core"
            or kwargs["preset"] != "fast"
            or kwargs["max_tokens"] != 512
            or kwargs["temperature"] != 0
        ):
            raise ValueError("core_contract_changed")
        self.ledger.admit("core", self.slot.name + "-core")
        assets.publish(
            self.slot / "core-request.json",
            dict(
                description="Original VoicePipeline short-answer/Fast512 request on retained public audio only.",
                **kwargs,
            ),
        )
        gateway = LlamaGateway(
            base_url="http://127.0.0.1:18080", model_id="qwen3.5-9b-core"
        )
        result = await gateway.complete(
            messages=kwargs["messages"], temperature=0, max_tokens=512, preset="fast"
        )
        assets.publish(
            self.slot / "core-response.json",
            dict(
                description="First complete original CORE gateway response, including invalid or unfinished outcomes.",
                response=result,
            ),
        )
        first = result["choices"][0]
        meta = result["local_assistant"]
        selected = meta.get("preset_selected") or meta.get("preset")
        if meta.get("status") != "PASS" or selected != "fast":
            FAILURES.append("core_gateway_metadata_contract")
            raise ValueError("core_gateway_metadata_contract")
        if first["finish_reason"] != "stop":
            raise ValueError("core_incomplete_or_contract_mismatch")
        return CompletionResult(
            first["message"]["content"], "qwen3.5-9b-core", "fast", "stop"
        )


def matrix(packet):
    """Preregister every workflow slot without selecting a voice or ASR lane from measured outcomes."""
    return [
        dict(
            id=f"turn-{index:02d}",
            asr=asr,
            tts=tts,
            state=state,
            source=case["id"],
            expected_no_answer=case["expected_no_answer"],
            status="UNATTEMPTED",
        )
        for index, (asr, tts, state, case) in enumerate(
            itertools.product(
                ("qwen3-asr-0.6b", "whisper-small-ct2"),
                ("piper-vi", "turbo"),
                ("fresh", "resident"),
                packet["workflow_sources"],
            )
        )
    ]


async def workflow(root, packet, sources, ledger, deadline, rows):
    """Run declared fresh/resident slots using the unchanged VoicePipeline and joined research-only adapters."""
    core_dir = root / "results/core"
    core_dir.mkdir(mode=0o700)
    server = OwnedServer("core", core_dir)
    try:
        await server.start()
        for (asr, tts, state), group in itertools.groupby(
            rows, key=lambda r: (r["asr"], r["tts"], r["state"])
        ):
            resident_asr = resident_tts = None
            try:
                if state == "resident":
                    group_dir = root / "results" / f"resident-{asr}-{tts}"
                    group_dir.mkdir(mode=0o700)
                    resident_asr = await Worker(
                        asr, group_dir / "asr", deadline, core_pid=server.process.pid
                    ).start()
                    resident_tts = await Worker(
                        tts, group_dir / "tts", deadline, core_pid=server.process.pid
                    ).start()
                for row in group:
                    if server.failure or time.monotonic() > deadline:
                        raise ValueError("core_guard_or_campaign_wall")
                    slot = root / "results" / row["id"]
                    slot.mkdir(mode=0o700)
                    asr_adapter = ResearchASR(
                        asr,
                        resident_asr,
                        slot,
                        sources[row["source"]],
                        ledger,
                        deadline,
                        server.process.pid,
                    )
                    tts_adapter = ResearchTTS(
                        tts, resident_tts, slot, ledger, deadline, server.process.pid
                    )
                    service = VoicePipeline(
                        asr=asr_adapter,
                        llm=ResearchCORE(slot, ledger),
                        tts=tts_adapter,
                        asr_model=asr,
                        llm_model="qwen3.5-9b-core",
                        tts_model=tts_adapter.model_id,
                        timeout=180,
                    )
                    started = time.monotonic()
                    row["status"] = "ATTEMPTED"
                    try:
                        result = await service.complete(
                            uuid4(),
                            sources[row["source"]]["audio"],
                            "vi",
                            explicit_submission=True,
                        )
                        row.update(
                            status="NEGATIVE_HALLUCINATION"
                            if row["expected_no_answer"]
                            else "COMPLETE_PCM_PROXY_ONLY",
                            buffered_latency_seconds=time.monotonic() - started,
                            stage_seconds=result.stage_seconds,
                            complete_pcm_within_4s=time.monotonic() - started <= 4,
                            physical_first_audible="UNVERIFIED",
                        )
                    except asyncio.CancelledError:
                        row.update(
                            status="CANCELLED",
                            elapsed_seconds=time.monotonic() - started,
                        )
                        raise
                    except Exception as error:
                        row.update(
                            status="CORRECT_NO_SPEECH"
                            if getattr(error, "code", None) == "no_speech"
                            and row["expected_no_answer"]
                            else "FAILED",
                            error_class=type(error).__name__,
                            code=getattr(error, "code", None),
                            elapsed_seconds=time.monotonic() - started,
                        )
                        if FAILURES or any(
                            w.failure
                            for w in (asr_adapter.worker, tts_adapter.worker)
                            if w is not None
                        ):
                            raise ValueError(
                                "native_worker_failure_stops_campaign"
                            ) from error
                    finally:
                        await service.shutdown()
                        for adapter in (asr_adapter, tts_adapter):
                            if adapter.owned and adapter.worker is not None:
                                await adapter.worker.close(
                                    force=bool(adapter.worker.failure)
                                )
                        assets.publish(
                            slot / "result.json",
                            dict(
                                description="One declared workflow slot; physical audibility never inferred from PCM timing.",
                                **row,
                            ),
                        )
            finally:
                for worker in (resident_asr, resident_tts):
                    if worker is not None:
                        await worker.close(force=bool(worker.failure))
    finally:
        await finish_owned(spawn_owned(server.stop()))
        assets.publish(
            core_dir / "retirement.json",
            dict(
                description="Original owned CORE lifecycle, no shared service restart.",
                **server.receipt(),
            ),
        )


async def monitor_campaign(root, deadline, actor):
    """Guard resident idle periods and CORE waits, cancelling admission on the first resource breach."""
    last_budget = 0
    try:
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("campaign_wall")
            for worker in list(WORKERS):
                worker.check()
            if time.monotonic() - last_budget > 1:
                assets.budget(root)
                last_budget = time.monotonic()
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        raise
    except BaseException as error:
        FAILURES.append(type(error).__name__ + ":" + str(error))
        LOGGER.exception("campaign_watchdog_stopped_admission")
        actor.cancel()


async def run(root=ROOT):
    """Execute one frozen campaign, stop on the first integrity/resource failure and retain all unattempted rows."""
    root = Path(root)
    FAILURES.clear()
    prepared_integrity(root)
    original = verify_originals()
    verify_models()
    verify_runtime_snapshot()
    packet = json.loads(assets.PACKET.read_text())
    for candidate in json.loads(
        (PROJECT / "configs/asr-evaluation-candidates.json").read_text()
    )["candidates"]:
        model = ASR_ROOT / "models" / candidate["id"] / candidate["revision"]
        for item in candidate["artifacts"]:
            verify_file(model / item["filename"], item)
    identity = root / "identity"
    identity.mkdir(mode=0o700)
    for name in ["passwd", "group"]:
        (identity / name).write_bytes((TTS_ROOT / "runtime-source" / name).read_bytes())
    sources = prepare_samples(root, packet)
    before = local_state()
    if before["native_pids"]:
        raise ValueError("preexisting_core_must_not_be_replaced")
    rows = matrix(packet)
    ledger = Ledger(root)
    source_files = [
        *PROJECT.glob("benchmarks/scripts/vi_voice_*.py"),
        *PROJECT.glob("benchmarks/tests/test_vi_voice_*.py"),
    ]
    freeze = dict(
        description="Owner-approved ADR-154 exact execution freeze before any native import/load/prediction. Physical audibility/listening are separate unresolved gates.",
        owner_approval_sha256=assets.digest(
            PROJECT / "docs/evidence/d74-adr154-owner-approval-20261103.json"
        ),
        manifest_sha256=assets.digest(assets.MANIFEST),
        packet_sha256=assets.digest(assets.PACKET),
        operator_sha256={
            str(p.relative_to(PROJECT)): assets.digest(p) for p in source_files
        },
        prepared_inventory_sha256=assets.digest(root / "prepared-inventory.json"),
        lock_sha256=assets.digest(root / "requirements.lock"),
        original_counts=original,
        state_before=before,
        qualification_text=QUALIFICATION_TEXT,
        workflow_slots=rows,
        software_tests=json.loads((root / "software-verification.json").read_text()),
        input_conversion={
            key: {k: v for k, v in value.items() if k != "audio"}
            for key, value in sources.items()
        },
        limits=dict(
            root_bytes=8 * GIB,
            tts_AS_bytes=8 * GIB,
            tts_sampled_RSS_bytes=2 * GIB,
            aggregate_sampled_RSS_bytes=8 * GIB,
            headroom_bytes=14 * GIB,
            cpu_affinity=[0, 1],
            cpu_threads=2,
            tts_worker_wall=600,
            asr_worker_wall=900,
            campaign_wall=3600,
            turn_deadline=180,
            tts_calls=74,
            asr_calls=48,
            core_calls=50,
            retries=0,
        ),
    )
    if (
        freeze["manifest_sha256"] != assets.MANIFEST_SHA
        or freeze["packet_sha256"] != assets.PACKET_SHA
        or freeze["software_tests"]["status"] != "PASS"
        or freeze["software_tests"].get("operator_sha256") != freeze["operator_sha256"]
    ):
        raise ValueError("execution_freeze_inputs")
    assets.publish(root / "execution-freeze.json", freeze)
    started = time.monotonic()
    observations = [
        dict(
            id=label + "-" + case["id"],
            voice=voice,
            case=case["id"],
            status="UNATTEMPTED",
        )
        for voice, label in [
            ("piper-vi", "piper-vi"),
            ("Trúc Ly", "truc-ly"),
            ("Ngọc Huyền", "ngoc-huyen"),
        ]
        for case in packet["tts_cases"]
    ]
    deadline = started + 3600
    outcome = dict(
        description="One ADR-154 campaign; no product model selection or physical first-audible PASS.",
        status="STARTED",
        standalone=observations,
        workflow=rows,
    )
    actor = asyncio.current_task()
    watchdog = asyncio.create_task(monitor_campaign(root, deadline, actor))
    try:
        for candidate in ["turbo", "piper-vi"]:
            worker = Worker(
                candidate, root / "results" / ("qualification-" + candidate), deadline
            )
            try:
                await worker.start()
                name = "qualification-" + candidate
                ledger.admit("tts", name)
                result = await worker.call(
                    dict(
                        op="synthesize",
                        id=name,
                        text=QUALIFICATION_TEXT,
                        voice="Trúc Ly" if candidate == "turbo" else "piper-vi",
                    )
                )
                assets.publish(
                    worker.directory / "qualification.json",
                    dict(
                        description="First qualification output; no voice quality judgment.",
                        result=result,
                    ),
                )
            finally:
                await worker.close(force=bool(worker.failure))
        for candidate, voice, label in [
            ("piper-vi", "piper-vi", "piper-vi"),
            ("turbo", "Trúc Ly", "truc-ly"),
            ("turbo", "Ngọc Huyền", "ngoc-huyen"),
        ]:
            worker = Worker(
                candidate, root / "results" / ("standalone-" + label), deadline
            )
            try:
                await worker.start()
                for case in packet["tts_cases"]:
                    name = label + "-" + case["id"]
                    ledger.admit("tts", name)
                    observation = next(r for r in observations if r["id"] == name)
                    observation["status"] = "ATTEMPTED"
                    try:
                        result = await worker.call(
                            dict(
                                op="synthesize", id=name, text=case["text"], voice=voice
                            )
                        )
                        observation.update(
                            status="NATIVE_COMPLETE_AWAITING_LISTENING", result=result
                        )
                    except BaseException as error:
                        observation.update(
                            status="FAILED",
                            error=type(error).__name__ + ":" + str(error),
                        )
                        raise
            finally:
                await worker.close(force=bool(worker.failure))
        await workflow(root, packet, sources, ledger, deadline, rows)
        outcome["status"] = "BOUNDED_CAMPAIGN_COMPLETED_PRODUCT_GATES_OPEN"
    except BaseException as error:
        outcome["status"], outcome["error"] = (
            "STOPPED_NO_RETRY",
            type(error).__name__ + ":" + str(error),
        )
        LOGGER.exception("approved_campaign_stopped")
    finally:
        watchdog.cancel()
        await asyncio.gather(watchdog, return_exceptions=True)
        for worker in list(WORKERS):
            await worker.close(force=True)
        outcome.update(
            calls=ledger.counts,
            total_wall_seconds=time.monotonic() - started,
            state_after=local_state(),
            originals_after=verify_originals(),
            unattempted_workflow=sum(r["status"] == "UNATTEMPTED" for r in rows),
            unattempted_standalone=sum(
                r["status"] == "UNATTEMPTED" for r in observations
            ),
            guard_failures=list(FAILURES),
            physical_first_audible="UNVERIFIED",
            owner_voice_selection=None,
        )
        if outcome["state_after"] != before:
            outcome["cleanup_error"] = "native_or_container_baseline_changed"
            outcome["status"] = "STOPPED_CLEANUP_BASELINE_CHANGED"
        assets.publish(root / "campaign-result.json", outcome)
    return outcome


def require_recovery_approval(plan, approval_path):
    """Require a new explicit owner decision bound to the concrete recovery plan before any live retry."""
    if not approval_path.is_file():
        raise ValueError("adr155_owner_approval_required")
    approval = json.loads(approval_path.read_text())
    if approval.get("approved") is not True or approval.get(
        "plan_sha256"
    ) != assets.digest(plan):
        raise ValueError("adr155_approval_binding")
    return json.loads(plan.read_text())


def retained_sources(root, packet):
    """Rebind the exact prior source/PCM quantization without rewriting or repairing retained waveforms."""
    frozen = json.loads((root / "execution-freeze.json").read_text())[
        "input_conversion"
    ]
    result = {}
    for case in packet["workflow_sources"]:
        raw = (PROJECT / case["waveform_path"]).read_bytes()
        if sha(raw) != case["waveform_sha256"]:
            raise ValueError("retained_source_changed")
        audio = NativeAudioNormalizer().normalize(pcm_wave(raw, 16000))
        info = frozen[case["id"]]
        if (
            assets.digest(root / "samples" / info["request"]["filename"])
            != info["request"]["waveform_sha256"]
        ):
            raise ValueError("retained_port_input_changed")
        result[case["id"]] = dict(audio=audio, request=info["request"])
    return result


async def run_workflow_recovery(root=ROOT):
    """Run one separately approved replacement workflow campaign without repeating qualification or standalone TTS."""
    root = Path(root)
    plan_path = (
        PROJECT / "docs/evidence/d74-adr155-proposed-workflow-recovery-20261103.json"
    )
    approval_path = PROJECT / "docs/evidence/d74-adr155-owner-approval-20261103.json"
    plan = require_recovery_approval(plan_path, approval_path)
    for name, expected in plan["operator_sha256"].items():
        if assets.digest(PROJECT / name) != expected:
            raise ValueError("recovery_operator_changed")
    software = json.loads((root / "software-verification-recovery.json").read_text())
    if (
        software["status"] != "PASS"
        or software["operator_sha256"] != plan["operator_sha256"]
    ):
        raise ValueError("recovery_software_freeze_changed")
    prepared_integrity(root)
    original = verify_originals()
    if (
        assets.digest(root / "campaign-result.json") != plan["prior_result_sha256"]
        or assets.digest(root / "execution-freeze.json") != plan["prior_freeze_sha256"]
    ):
        raise ValueError("recovery_prior_changed")
    before = local_state()
    initial = json.loads((root / "execution-freeze.json").read_text())["state_before"]
    if before != initial or before["native_pids"]:
        raise ValueError("recovery_baseline_changed")
    verify_models()
    verify_runtime_snapshot()
    packet = json.loads(assets.PACKET.read_text())
    sources = retained_sources(root, packet)
    campaign_root = root / "workflow-recovery-first"
    campaign_root.mkdir(mode=0o700)
    (campaign_root / "results").mkdir(mode=0o700)
    ledger = Ledger(campaign_root)
    rows = matrix(packet)
    freeze = dict(
        description="ADR155 replacement workflow only; historical six invalid slots and 24 valid standalone clips remain immutable.",
        plan_sha256=assets.digest(plan_path),
        approval_sha256=assets.digest(approval_path),
        software=software,
        original_counts=original,
        state_before=before,
        workflow=rows,
    )
    assets.publish(campaign_root / "execution-freeze.json", freeze)
    FAILURES.clear()
    started, actor = time.monotonic(), asyncio.current_task()
    deadline = started + 3600
    watchdog = asyncio.create_task(monitor_campaign(root, deadline, actor))
    outcome = dict(
        description="Separately authorized replacement workflow; never physical-audibility or owner-voice acceptance.",
        status="STARTED",
        workflow=rows,
    )
    try:
        await workflow(campaign_root, packet, sources, ledger, deadline, rows)
        outcome["status"] = "REPLACEMENT_WORKFLOW_COMPLETED_PRODUCT_GATES_OPEN"
    except BaseException as error:
        outcome["status"], outcome["error"] = (
            "STOPPED_NO_RETRY",
            type(error).__name__ + ":" + str(error),
        )
        LOGGER.exception("replacement_workflow_stopped")
    finally:
        watchdog.cancel()
        await asyncio.gather(watchdog, return_exceptions=True)
        for worker in list(WORKERS):
            await finish_owned(spawn_owned(worker.close(force=True)))
        outcome.update(
            calls=ledger.counts,
            total_wall_seconds=time.monotonic() - started,
            state_after=local_state(),
            originals_after=verify_originals(),
            unattempted=sum(r["status"] == "UNATTEMPTED" for r in rows),
            guard_failures=list(FAILURES),
            physical_first_audible="UNVERIFIED",
            owner_voice_selection=None,
        )
        if outcome["state_after"] != before:
            outcome["cleanup_error"] = "native_or_container_baseline_changed"
            outcome["status"] = "STOPPED_CLEANUP_BASELINE_CHANGED"
        assets.publish(campaign_root / "campaign-result.json", outcome)
    return outcome


def main():
    """Execute only the single explicitly approved campaign using the original frozen packet and caps."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-recovery", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    result = asyncio.run(run_workflow_recovery() if args.workflow_recovery else run())
    if result["status"] not in {
        "BOUNDED_CAMPAIGN_COMPLETED_PRODUCT_GATES_OPEN",
        "REPLACEMENT_WORKFLOW_COMPLETED_PRODUCT_GATES_OPEN",
    }:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
