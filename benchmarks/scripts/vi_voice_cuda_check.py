"""Qualify unchanged ASR checkpoints on CUDA against retained CPU quality, then measure bounded native voice latency."""

import argparse
import asyncio
import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

from benchmarks.scripts import vi_voice_resident_check as resident
from scripts.asr_evaluation_metrics import score
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
original = resident.original
old = resident.old
PROJECT = resident.PROJECT
ROOT = PROJECT / "data/backups/d74-cuda-asr-first"
SDK = PROJECT / "data/backups/d74-cuda-asr-sdk-first"
WORKER = "benchmarks/scripts/vi_voice_cuda_worker.py"
SOURCES = (
    WORKER,
    "benchmarks/scripts/vi_voice_cuda_check.py",
    "benchmarks/tests/test_vi_voice_cuda_worker.py",
    "benchmarks/tests/test_vi_voice_cuda_check.py",
)
ADR = "docs/ADR/171-same-checkpoint-cuda-asr-latency-qualification.md"


def quality_pass(cpu, gpu):
    """Require full same-reference coverage and no worse word or character edits in either language."""
    if (
        cpu.get("coverage_complete") is not True
        or gpu.get("coverage_complete") is not True
        or cpu.get("expected_cases") != 40
        or gpu.get("expected_cases") != 40
        or set(cpu["languages"]) != {"vi_vn", "en_us"}
        or set(gpu["languages"]) != {"vi_vn", "en_us"}
    ):
        return False
    for lang in ("vi_vn", "en_us"):
        a, b = cpu["languages"][lang], gpu["languages"][lang]
        if any(
            type(v) is not int or v < 0
            for row in (a, b)
            for v in (row["word_edits"], row["character_edits"])
        ):
            return False
        if (
            a["observed_speech_cases"] != 20
            or b["observed_speech_cases"] != 20
            or any(
                a[x] != b[x] or a[x] <= 0
                for x in ("reference_words", "reference_characters")
            )
            or b["word_edits"] > a["word_edits"]
            or b["character_edits"] > a["character_edits"]
        ):
            return False
    LOGGER.info("cuda_quality_noninferiority_verified")
    return True


class Monitor:
    """Read NVML process allocation directly without spawning latency-distorting polling commands."""

    def __init__(self, sdk=SDK):
        """Load the isolated pinned monitoring client without altering any application environment."""
        path = Path(sdk) / "venv/lib/python3.12/site-packages/pynvml.py"
        spec = importlib.util.spec_from_file_location("_voice_cuda_nvml", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous
        module.nvmlInit()
        self.module = module
        self.device = module.nvmlDeviceGetHandleByIndex(0)
        LOGGER.info("cuda_monitor_initialized")

    def sample(self, pids=()):
        """Return only owned-process GPU allocation and actual device-free bytes, leaving all other processes untouched."""
        processes = self.module.nvmlDeviceGetComputeRunningProcesses_v3(self.device)
        used = sum(int(x.usedGpuMemory) for x in processes if x.pid in pids)
        return used, int(self.module.nvmlDeviceGetMemoryInfo(self.device).free)

    def close(self):
        """Release only the read-only NVML client handle without resetting a device or shared service."""
        self.module.nvmlShutdown()
        LOGGER.info("cuda_monitor_closed")


def command(role, output, manifest, manifest_sha, samples, *, mode):
    """Expose original readonly ASR data plus a separate CUDA SDK/device and explicit virtual-address profile."""
    if role not in ("whisper-small-ct2", "qwen3-asr-0.6b"):
        raise ValueError("cuda_command_role")
    if mode not in ("probe", "quality", "voice"):
        raise ValueError("cuda_command_mode")
    samples = original.ROOT / "samples" if mode == "voice" else Path(samples)
    LOGGER.info("cuda_asr_samples_bound mode=%s original_pcm=%s", mode, mode == "voice")
    args = list(original.namespace(role, output))
    index = args.index("--cpu-list")
    args[index + 1] = "0,1,2,3,4,5,6,7"
    for i, x in enumerate(args):
        if x == str(original.ROOT / "samples"):
            args[i] = str(samples)
        if x == "--as=8589934592":
            args[i] = "--as=68719476736"
        if i and args[i - 1] == "--setenv":
            if x in (
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "NUMBA_NUM_THREADS",
                "RAYON_NUM_THREADS",
            ):
                args[i + 1] = "8"
            if x == "CUDA_VISIBLE_DEVICES":
                args[i + 1] = "0"
    mounts = []
    for name in (WORKER, "benchmarks/scripts/vi_voice_worker.py"):
        mounts += ["--ro-bind", str(PROJECT / name), "/app/" + name]
    mounts += [
        "--ro-bind",
        str(SDK / "venv"),
        "/cuda-venv",
        "--ro-bind",
        str(manifest),
        "/approved-workflow.json",
    ]
    for device in ("/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-uvm"):
        if not Path(device).exists():
            raise ValueError("cuda_device_missing")
        mounts += ["--dev-bind", device, device]
    libs = ":".join(
        "/cuda-venv/lib/python3.12/site-packages/nvidia/" + x + "/lib"
        for x in (
            "cublas",
            "cuda_runtime",
            "cudnn",
            "nvjitlink",
            "cusparse",
            "cusolver",
        )
    )
    mounts += [
        "--setenv",
        "LD_LIBRARY_PATH",
        libs + ":/usr/lib/x86_64-linux-gnu",
        "--setenv",
        "CUBLAS_WORKSPACE_CONFIG",
        ":4096:8",
        "--setenv",
        "NVIDIA_TF32_OVERRIDE",
        "0",
    ]
    index = args.index("--remount-ro")
    args[index:index] = mounts
    index = args.index("/venv/bin/python")
    return args[:index] + ["/cuda-venv/bin/python", "/app/" + WORKER, manifest_sha]


class Worker(resident.Worker):
    """Own one CUDA ASR lifetime while retaining the original aggregate physical-memory and cleanup guards."""

    def __init__(
        self,
        role,
        directory,
        deadline,
        core_pid,
        scope,
        threads,
        samples,
        monitor,
        mode="voice",
        *,
        root=ROOT,
    ):
        """Bind an explicit CUDA-only scope and separate quality/native request count."""
        value = json.loads(Path(scope).read_text())
        value.update(
            mode=mode,
            execution_backend="cuda-original-precision",
            max_requests=40 if mode == "quality" else 4,
        )
        gpu_scope = Path(scope).with_name(Path(scope).stem + "-cuda.json")
        old.publish(gpu_scope, value)
        super().__init__(
            role, directory, deadline, core_pid, gpu_scope, 8, samples, root=root
        )
        self.monitor, self.mode = monitor, mode
        self.peak_vram = 0
        self.minimum_free = None

    def check(self):
        """Keep physical RAM guards and enforce owned ASR VRAM/global headroom without changing CORE allocation."""
        super().check()
        used, free = self.monitor.sample(original.process_tree(self.process.pid))
        self.peak_vram = max(self.peak_vram, used)
        self.minimum_free = (
            free if self.minimum_free is None else min(self.minimum_free, free)
        )
        if used > int(4.5 * 1024**3) or free < int(1.25 * 1024**3):
            raise ValueError("cuda_vram_or_free_guard")

    async def start(self):
        """Validate device/host headroom and actual CUDA precision before admitting any inference request."""
        if (
            self.process is not None
            or original.mem_available() < 14 * 1024**3
            or self.monitor.sample()[1] < 6 * 1024**3
        ):
            raise ValueError("cuda_worker_preflight")
        self.directory.mkdir(mode=0o700)
        output = self.directory / "native"
        output.mkdir(mode=0o700)
        self.started = time.monotonic()
        self.log = (self.directory / "stderr.log").open("xb")
        try:
            args = command(
                self.candidate,
                output,
                self.scope_path,
                self.scope_sha,
                self.samples_path,
                mode=self.mode,
            )
            old.publish(
                self.directory / "launch.json",
                dict(
                    description="Original checkpoint CUDA scope;64GiB virtual is not physical RAM.",
                    command=args,
                    available_RAM=original.mem_available(),
                    gpu_free=self.monitor.sample()[1],
                ),
            )
            self.process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=self.log,
                start_new_session=True,
                limit=65537,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            )
            original.WORKERS.add(self)
            old.publish(
                self.directory / "process-identity.json",
                dict(
                    description="Exact owned CUDA namespace identity.",
                    pid=self.process.pid,
                ),
            )
            self.ready = await self.receive()
            execution = self.ready.get("execution", {})
            if (
                self.ready.get("event"),
                self.ready.get("candidate"),
                self.ready.get("manifest_sha256"),
                execution.get("execution_backend"),
            ) != (
                "ready",
                self.candidate,
                self.scope_sha,
                "cuda-original-precision",
            ) or self.ready.get("readiness", {}).get("model_calls") != 1:
                raise ValueError("cuda_ready_binding")
            if self.candidate == "qwen3-asr-0.6b" and (
                execution.get("device") != "cuda:0"
                or execution.get("parameter_dtype") != "torch.float32"
                or execution.get("tf32") is not False
            ):
                raise ValueError("cuda_ready_precision")
            if self.candidate == "whisper-small-ct2" and (
                execution.get("device") != "cuda"
                or execution.get("engine_compute_type") != "int8_float32"
            ):
                raise ValueError("cuda_ready_precision")
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            original.FAILURES.append(self.failure)
            if self.process is not None:
                await finish_owned(spawn_owned(self.close(force=True)))
            else:
                self.log.close()
            raise
        LOGGER.info("cuda_worker_ready role=%s mode=%s", self.candidate, self.mode)
        return self

    async def predict(self, message):
        """Admit a single reference-free bilingual quality request without refunding or retrying its first outcome."""
        if self.mode != "quality" or self.busy:
            raise ValueError("cuda_quality_scope")
        self.busy = True
        try:
            old.publish(
                self.directory / (message["id"] + "-request.json"),
                dict(
                    description="First GPUquality input, no reference label.", **message
                ),
            )
            self.process.stdin.write(json.dumps(message).encode() + b"\n")
            await self.process.stdin.drain()
            result = await self.receive()
            if (result.get("event"), result.get("id"), result.get("operation")) != (
                "result",
                message["id"],
                "transcribe",
            ):
                raise ValueError("cuda_quality_result")
            return result["asr"]
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            original.FAILURES.append(self.failure)
            await finish_owned(spawn_owned(self.close(force=True)))
            raise
        finally:
            self.busy = False

    async def close(self, force=False):
        """Join the exact owned CUDA child before publishing its observed GPU-memory usage."""
        await super().close(force=force)
        path = self.directory / "gpu-usage.json"
        if not path.exists():
            old.publish(
                path,
                dict(
                    description="Sampled owned ASR GPUallocation; CPU/CORE limits unchanged.",
                    peak_VRAM_bytes=self.peak_vram,
                    minimum_global_free_bytes=self.minimum_free,
                ),
            )


async def quality(root, core_pid, deadline, monitor, scope_sha):
    """Compare all40original primary inputs perGPUcandidate with immutable raw CPUobservations without reference leakage."""
    corpus = json.loads((old.CORPUS_ROOT / "corpus.json").read_text())
    cases = [
        x
        for x in corpus["cases"]
        if x["kind"] == "independent_public_speech"
        and not x["id"].startswith("padded-")
    ]
    if len(cases) != 40:
        raise ValueError("cuda_quality_source_count")
    for x in cases:
        if original.assets.digest(Path(x["waveform_path"])) != x["waveform_sha256"]:
            raise ValueError("cuda_quality_source_drift")
    results = {}
    for candidate in ("whisper-small-ct2", "qwen3-asr-0.6b"):
        events = [
            json.loads(line)
            for line in (old.CORPUS_ROOT / (candidate + "-stdout.jsonl"))
            .read_text()
            .splitlines()
        ]
        ids = {x["id"] for x in cases}
        cpu = [
            dict(x, id=x["id"].removesuffix("-ungated"))
            for x in events
            if x.get("event") == "prediction"
            and x.get("id", "").endswith("-ungated")
            and x["id"].removesuffix("-ungated") in ids
        ]
        baseline = score(cases, cpu)
        scope = root / "manifests" / (candidate + "-quality.json")
        old.publish(
            scope,
            dict(
                description="One fixed40case existing-source quality capability.",
                native_authorized=True,
                role=candidate,
                cpu_threads=8,
                max_requests=40,
                scope_sha256=scope_sha,
                model=candidate,
                policy="original-asr-decoding",
            ),
        )
        worker = Worker(
            candidate,
            root / "quality" / candidate,
            deadline,
            core_pid,
            scope,
            8,
            old.CORPUS_ROOT / "vad-inputs",
            monitor,
            "quality",
            root=root,
        )
        predictions = []
        try:
            await worker.start()
            for case in cases:
                payload = dict(
                    op="transcribe",
                    id=case["id"],
                    filename=Path(case["waveform_path"]).name,
                    sample_count=case["sample_count"],
                    waveform_sha256=case["waveform_sha256"],
                    language=case["language"],
                )
                value = await worker.predict(payload)
                predictions.append(
                    dict(
                        id=case["id"],
                        status="error" if value["output_cap_reached"] else "ok",
                        text=value["text"],
                        wall_seconds=value["wall_seconds"],
                    )
                )
        finally:
            await finish_owned(spawn_owned(worker.close(force=bool(worker.failure))))
        gpu = score(cases, predictions)
        result = dict(
            description="Same-source historical CPUbaseline versus first GPUoutputs; no model selection.",
            candidate=candidate,
            cpu=baseline,
            gpu=gpu,
            passed=quality_pass(baseline, gpu),
            exact_text_matches=sum(
                a["prediction"] == b["prediction"]
                for a, b in zip(baseline["cases"], gpu["cases"], strict=True)
                if a["status"] == b["status"] == "ok"
            ),
        )
        results[candidate] = result
        old.publish(root / "quality" / (candidate + "-result.json"), result)
    return results


async def run(root=ROOT):
    """Own the fixed quality-then-native CUDA experiment and retain every failing or unattempted gate."""
    root = Path(root)
    software = json.loads((root / "software-verification.json").read_text())
    hashes = {n: original.assets.digest(PROJECT / n) for n in (*SOURCES, ADR)}
    if software.get("status") != "PASS" or software.get("source_sha256") != {
        n: hashes[n] for n in SOURCES
    }:
        raise ValueError("cuda_software_gate")
    cpu_software = json.loads(
        (resident.ROOT / "software-verification.json").read_text()
    )
    for name, expected_hash in cpu_software["source_sha256"].items():
        if original.assets.digest(PROJECT / name) != expected_hash:
            raise ValueError("cuda_cpu_dependency_changed")
        hashes[name] = expected_hash
    hashes[resident.ADR] = original.assets.digest(PROJECT / resident.ADR)
    probe = json.loads((SDK / "cuda-probe.json").read_text())
    if (
        probe.get("model_calls") != 0
        or probe.get("model_loads") != 0
        or probe.get("event") != "cuda_probe"
        or probe.get("torch_version") != "2.10.0+cu128"
        or probe.get("cuda_version") != "12.8"
    ):
        raise ValueError("cuda_preflight_probe")
    preserved = old.previous_snapshot()
    for directory in (resident.ROOT, resident.previous.ROOT):
        for path in directory.rglob("*"):
            if path.is_file():
                preserved[str(path.relative_to(PROJECT))] = original.assets.digest(path)
    binding, _ = resident.reading.verify_previous()
    original.verify_originals()
    original.verify_models()
    original.verify_runtime_snapshot()
    old.verify_provision()
    checkpoints = json.loads(
        (resident.previous.ROOT / "asr-checkpoint-post-run.json").read_text()
    )["sha256"]
    for n, h in checkpoints.items():
        if original.assets.digest(PROJECT / n) != h:
            raise ValueError("cuda_checkpoint_drift")
    before = original.local_state()
    if before["native_pids"]:
        raise ValueError("cuda_existing_core")
    for name in ("results", "manifests", "samples", "quality"):
        (root / name).mkdir(mode=0o700)
    packet = json.loads(original.assets.PACKET.read_text())
    sources = original.retained_sources(original.ROOT, packet)
    rows = [
        dict(
            id=f"cuda-turn-{i:02d}",
            asr=asr,
            threads=8,
            source=x["id"],
            expected_no_answer=x["expected_no_answer"],
            status="UNATTEMPTED",
            asr_execution="cuda",
        )
        for i, (asr, x) in enumerate(
            (
                (a, x)
                for a in ("whisper-small-ct2", "qwen3-asr-0.6b")
                for x in packet["workflow_sources"]
            )
        )
    ]
    expected = {}
    for identity, value in sources.items():
        view = resident.detector_view(value["audio"])
        filename = identity + ".f32"
        old.save_bytes(root / "samples" / filename, view.waveform_f32)
        expected[identity] = dict(
            filename=filename,
            sample_count=view.sample_count,
            waveform_sha256=view.waveform_sha256,
        )
    quality_cases = [
        x
        for x in json.loads((old.CORPUS_ROOT / "corpus.json").read_text())["cases"]
        if x["kind"] == "independent_public_speech"
        and not x["id"].startswith("padded-")
    ]
    if len(quality_cases) != 40:
        raise ValueError("cuda_frozen_quality_count")
    freeze = dict(
        description="Fixed80quality+up-to12native CUDAtrial with unchanged checkpoints/decoding;4declared zero-input readiness calls maximum.",
        source_sha256=hashes,
        previous_sha256=preserved,
        asr_checkpoint_sha256=checkpoints,
        before=before,
        rows=rows,
        quality_sources=[
            {k: x[k] for k in ("id", "language", "sample_count", "waveform_sha256")}
            for x in quality_cases
        ],
        limits=dict(
            quality_asr=80,
            native_asr=8,
            readiness_asr=4,
            vad=12,
            core=8,
            tts=8,
            retries=0,
            wall_seconds=1800,
        ),
    )
    old.publish(root / "execution-freeze.json", freeze)
    scope_sha = original.assets.digest(root / "execution-freeze.json")
    monitor = Monitor()
    quality_server = original.OwnedServer("core", root / "quality/core")
    (root / "quality/core").mkdir(mode=0o700)
    original.FAILURES.clear()
    started = time.monotonic()
    failure = None
    quality_result = {}
    ledger = resident.Ledger(root)
    try:
        try:
            await quality_server.start()
            quality_result = await quality(
                root, quality_server.process.pid, started + 1800, monitor, scope_sha
            )
        finally:
            await finish_owned(spawn_owned(quality_server.stop()))
            old.publish(
                root / "quality/core/retirement.json",
                dict(
                    description="Owned COREco-residency quality phase retired.",
                    **quality_server.receipt(),
                ),
            )
        qualified = {k for k, v in quality_result.items() if v["passed"]}
        for row in rows:
            if row["asr"] not in qualified:
                row["status"] = "NOT_RUN_QUALITY_FAILED"
        native_rows = [x for x in rows if x["asr"] in qualified]
        if native_rows:
            factory = resident.Worker

            def selected(role, *args, **kwargs):
                """Select only CUDA ASR, retaining original qualified CPUVAD/TTS factories and settings."""
                return (
                    Worker(role, *args, monitor=monitor, **kwargs)
                    if role in qualified
                    else factory(role, *args, **kwargs)
                )

            resident.Worker = selected
            try:
                await resident.workflow(
                    root,
                    native_rows,
                    sources,
                    ledger,
                    started + 1800,
                    binding,
                    scope_sha,
                    expected,
                )
            finally:
                resident.Worker = factory
    except BaseException as error:
        failure = type(error).__name__
        raise
    finally:
        monitor.close()
        after = original.local_state()
        old.verify_snapshot(preserved)
        original.verify_originals()
        gates = []
        for candidate in ("whisper-small-ct2", "qwen3-asr-0.6b"):
            subset = [x for x in rows if x["asr"] == candidate]
            speech = [x for x in subset if not x["expected_no_answer"]]
            complete = all(
                x["status"]
                == ("CORRECT_NO_SPEECH" if x["expected_no_answer"] else "COMPLETE_PCM")
                for x in subset
            )
            gates.append(
                dict(
                    candidate=candidate,
                    quality_passed=quality_result.get(candidate, {}).get(
                        "passed", False
                    ),
                    native_complete=complete,
                    maximum_complete_pcm_seconds=max(
                        x["buffered_latency_seconds"] for x in speech
                    )
                    if complete
                    else None,
                    compute_proxy_within4=complete
                    and all(x["buffered_latency_seconds"] <= 4 for x in speech),
                    physical_first_audible="UNVERIFIED",
                )
            )
        old.publish(
            root / "result.json",
            dict(
                description="Actual fixed CUDAquality/native outcomes; no automatic product/default/physical acceptance.",
                rows=rows,
                gates=gates,
                calls=ledger.counts,
                failure=failure,
                guard_failures=original.FAILURES,
                baseline_preserved=before == after,
                after=after,
                wall_seconds=time.monotonic() - started,
                product_activation=False,
            ),
        )
    LOGGER.info("cuda_trial_completed")


def main():
    """Dispatch only this source-tested bounded CUDA qualification without shared-service or model changes."""
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
