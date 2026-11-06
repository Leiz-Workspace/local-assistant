"""Prepare and execute one owner-approved retained six-input main-app voice integration campaign without retries."""

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx

from apps.voice_trial.native import NativeRuntime as PriorRuntime
from apps.voice_trial.native import cuda, original
from benchmarks.scripts.d14_completion import (
    OwnedServer,
    command as core_command,
    local_state,
)
from src.infrastructure.voice.audio import encode_wave
from src.infrastructure.voice.core import process_identity
from src.infrastructure.voice.manifest import PINS, file_sha
from src.infrastructure.voice.ipc import FOREIGN_VRAM_LIMIT, Monitor, foreign_compute
from src.infrastructure.voice.resources import joined_io, process_tree, rss_bytes

LOGGER = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / "data/backups/d74-main-integration-first"
URL = "http://127.0.0.1:18092"
GIB = 1024**3
# ADR176: CORE alone must leave room for the voice workers inside the unchanged 8 GiB cap.
CORE_RSS_STOP = 6 * GIB


def publish(path, value):
    """Create one private audit record without overwriting any earlier attempt or exposing credentials."""
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    Path(path).chmod(0o600)
    LOGGER.info("main_voice_evidence_written name=%s", Path(path).name)


def inventory(directory):
    """Bind all existing files/symlinks under a selected runtime tree without downloading or changing artifacts."""
    result = {}
    for path in sorted(Path(directory).rglob("*")):
        name = str(path.relative_to(directory))
        if path.is_symlink():
            result[name] = {"target": os.readlink(path)}
        elif path.is_file():
            result[name] = {"bytes": path.stat().st_size, "sha256": file_sha(path)}
    return result


def source_snapshot():
    """Bind original application/qualified inputs and every new production/operator/test file before native execution."""
    paths = set()
    for pattern in (
        "apps/**/*.py",
        "apps/web/voice/*",
        "src/**/*.py",
        "tests/test_main_voice*",
        "tests/main_voice*",
        "benchmarks/scripts/main_voice_integration.py",
        "benchmarks/tests/test_main_voice_integration.py",
    ):
        paths.update(p for p in PROJECT.glob(pattern) if p.is_file())
    paths.update(
        PROJECT / name
        for name in (
            "configs/models.yaml",
            "configs/embedding-selected.json",
            "docs/ADR/174-proposed-opt-in-authenticated-voice-integration.md",
            "docs/ADR/175-optional-main-voice-composition-and-entrypoint-binding.md",
            "docs/ADR/176-bounded-foreign-gpu-tolerance-and-b3-preflight.md",
        )
    )
    return {str(p.relative_to(PROJECT)): file_sha(p) for p in sorted(paths)}


def assert_sources(expected):
    """Refuse execution when any frozen source/configuration has drifted since its software verification."""
    for name, digest in expected.items():
        if file_sha(PROJECT / name) != digest:
            raise ValueError("main_voice_source_changed")


def review_rows():
    """Reuse exactly the six previously frozen public source identities and PCM hashes in their original order."""
    path = (
        PROJECT
        / "data/backups/d74-voice-browser-trial-first/http-execution-freeze.json"
    )
    rows = json.loads(path.read_text())["native_rows"]
    if (
        len(rows) != 6
        or sum(not x["expected_no_answer"] for x in rows) != 4
        or len({x["id"] for x in rows}) != 6
    ):
        raise ValueError("main_voice_fixed_panel")
    return rows


def prepare(root=ROOT):
    """Verify retained artifacts and preregister complete inputs/manifests without starting or invoking any model."""
    if (root / "preparation.json").exists() or (
        root / "campaign-started.json"
    ).exists():
        raise ValueError("main_voice_prepare_already_recorded")
    software = json.loads((root / "software-verification.json").read_text())
    if software["status"] != "PASS":
        raise ValueError("main_voice_software_gate")
    assert_sources(software["source_sha256"])
    previous = PriorRuntime()
    previous.verify_lane()
    packet = json.loads(original.assets.PACKET.read_text())
    sources = original.retained_sources(original.ROOT, packet)
    (root / "public-inputs").mkdir(mode=0o700)
    rows = review_rows()
    for index, row in enumerate(rows):
        audio = sources[row["id"]]["audio"]
        if (
            hashlib.sha256(audio.pcm_s16le).hexdigest() != row["pcm_sha256"]
            or audio.sample_count != row["sample_count"]
        ):
            raise ValueError("main_voice_input_binding")
        path = root / "public-inputs" / f"{index}.wav"
        path.write_bytes(encode_wave(audio.pcm_s16le))
        path.chmod(0o600)
        row["wave_sha256"] = file_sha(path)
    tts = original.ROOT
    asr = PROJECT / "data/backups/d68-asr-evaluation"
    vad = PROJECT / "data/backups/d69-vad-evaluation"
    paths = dict(
        tts_venv=tts / "venv",
        tts_sources=tts / "sources/src",
        tts_cache=tts / "models",
        tts_model=tts
        / "models/models--pnnbao-ump--VieNeu-TTS-v3-Turbo/snapshots"
        / PINS["TTS"],
        asr_venv=asr / "venv",
        asr_sources=asr / "runtime-source/qwen-backend-source",
        asr_model=asr / "models/qwen3-asr-0.6b" / PINS["ASR"],
        cuda_venv=cuda.SDK / "venv",
        vad_venv=vad / "venv",
        vad_official=vad / "official",
    )
    trees = [
        tts / "sources",
        tts / "venv",
        tts / "models",
        asr / "venv",
        asr / "runtime-source/qwen-backend-source",
        paths["asr_model"],
        cuda.SDK / "venv",
        vad / "venv",
        vad / "official",
    ]
    template = dict(
        description="Owner-approved ADR174/175 isolated integration evaluation; no production activation.",
        purpose="integration_evaluation",
        production_activation=False,
        pins=PINS,
        paths={k: str(v) for k, v in paths.items()},
        inventory={str(p): inventory(p) for p in trees},
        source_sha256=source_snapshot(),
        reading_binding=previous.binding,
    )
    publish(root / "manifest-template.json", template)
    publish(
        root / "preparation.json",
        dict(
            description="Model-free exact existing artifact/input preparation before the single approved campaign.",
            status="PREPARED_NOT_EXECUTED",
            source_sha256=source_snapshot(),
            rows=rows,
            manifest_template_sha256=file_sha(root / "manifest-template.json"),
            software_sha256=file_sha(root / "software-verification.json"),
            CORE_command=core_command("core"),
            caps=dict(VAD=6, ASR=4, CORE=4, TTS=4, readiness=1, retries=0),
            model_calls=0,
            downloads=0,
        ),
    )


def verify_answer(value, previous, client_seconds):
    """Require exact prior complete outputs and both measured HTTP clocks below the unchanged four-second ceiling."""
    if (
        value.get("transcript") != previous["transcript"]
        or value.get("answer") != previous["answer"]
        or base64.b64decode(value["audio_base64"], validate=True)
        != base64.b64decode(previous["audio_base64"], validate=True)
        or type(value.get("server_seconds")) not in (int, float)
        or not 0 < value["server_seconds"] <= 4
        or not 0 < client_seconds <= 4
    ):
        raise ValueError("main_voice_exact_output_or_latency")


def preflight(core_rss, rows, core_pids):
    """Decide before any voice model loads whether the single panel may start (ADR176)."""
    count, total = foreign_compute(rows, core_pids)
    if type(core_rss) is not int or core_rss >= CORE_RSS_STOP:
        raise ValueError("main_voice_preflight_core_rss")
    if total > FOREIGN_VRAM_LIMIT:
        raise ValueError("main_voice_preflight_foreign_gpu")
    return dict(
        core_rss_bytes=core_rss,
        foreign_gpu_processes=count,
        foreign_gpu_bytes=total,
    )


async def wait_status(client, expected):
    """Wait only for finite declared startup readiness without performing inference or retrying preparation."""
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        response = await client.get("/ui/voice/status")
        if response.status_code != 200:
            raise ValueError("main_voice_status_denied")
        state = response.json()["state"]
        if state == expected:
            return response.json()
        if state != "preparing":
            raise ValueError("main_voice_prepare_fault")
        await asyncio.sleep(0.25)
    raise TimeoutError("main_voice_readiness_deadline")


async def run(root=ROOT):
    """Spend one isolated no-retry campaign and preserve every failed or unattempted input plus verified cleanup."""
    prepared = json.loads((root / "preparation.json").read_text())
    assert_sources(prepared["source_sha256"])
    if (
        file_sha(root / "manifest-template.json")
        != prepared["manifest_template_sha256"]
        or file_sha(root / "software-verification.json") != prepared["software_sha256"]
    ):
        raise ValueError("main_voice_preparation_changed")
    before = local_state()
    if before["native_pids"]:
        raise ValueError("main_voice_test_slot_busy")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 18092))
    publish(
        root / "campaign-started.json",
        dict(
            description="One owner-approved ADR174/175/176 campaign, no retries.",
            before=before,
            source_sha256=prepared["source_sha256"],
        ),
    )
    rows = [dict(x, status="UNATTEMPTED") for x in prepared["rows"]]
    result = dict(
        description="Actual main application HTTP voice integration; public retained inputs, no physical microphone/speaker claim.",
        rows=rows,
        status="NOT_PASS",
        retries=0,
        physical_first_audible="UNVERIFIED",
        production_activation=False,
        panel_consumed=False,
    )
    core_dir = root / "owned-core"
    core_dir.mkdir(mode=0o700)
    server = OwnedServer("core", core_dir)
    web = None
    log = None
    temporary = None
    ram = None
    try:
        async with asyncio.timeout(600):
            await server.start()
            if core_command("core") != prepared["CORE_command"]:
                raise ValueError("main_voice_core_command_changed")
            # Let llama.cpp release load-time mappings, then check headroom before any voice model.
            await asyncio.sleep(5)
            core_pids = set(process_tree(server.process.pid))
            paths = json.loads((root / "manifest-template.json").read_text())["paths"]
            monitor = Monitor(paths["cuda_venv"])
            try:
                gpu_rows = monitor.module.nvmlDeviceGetComputeRunningProcesses_v3(
                    monitor.device
                )
            finally:
                monitor.close()
            result["preflight"] = preflight(
                sum(rss_bytes(pid) for pid in core_pids), gpu_rows, core_pids
            )
            publish(root / "preflight.json", result["preflight"])
            temporary = tempfile.TemporaryDirectory(
                prefix="main-voice-eval-", dir="/dev/shm"
            )
            ram = Path(temporary.name)
            os.chmod(ram, 0o700)
            template = json.loads((root / "manifest-template.json").read_text())
            cmd = prepared["CORE_command"]
            model = cmd[cmd.index("--model") + 1]
            template["core"] = dict(
                URL="http://127.0.0.1:18080",
                identity=process_identity(server.process.pid),
                executable_sha256=file_sha(cmd[0]),
                model_path=model,
                model_sha256=PINS["CORE_GGUF"],
            )
            manifest = ram / "manifest.json"
            manifest.write_text(json.dumps(template))
            manifest.chmod(0o600)
            token = secrets.token_urlsafe(48)
            principal = str(uuid4())
            auth = ram / "auth.json"
            auth.write_text(
                json.dumps(
                    {
                        "principals": [
                            dict(
                                id=principal,
                                token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                            )
                        ]
                    }
                )
            )
            auth.chmod(0o600)
            env = dict(
                PATH="/usr/bin:/bin",
                LANG="C.UTF-8",
                TMPDIR="/dev/shm",
                PYTHONDONTWRITEBYTECODE="1",
                PYTHONPYCACHEPREFIX=str(ram / "pycache"),
                ASSISTANT_AUTH_FILE=str(auth),
                ASSISTANT_VOICE_ENABLED="1",
                ASSISTANT_VOICE_PURPOSE="integration_evaluation",
                ASSISTANT_VOICE_MANIFEST=str(manifest),
                WEB_CONCURRENCY="1",
            )
            log = (ram / "app.log").open("w+b")
            web = subprocess.Popen(
                [
                    str(PROJECT / ".venv/bin/python"),
                    "-m",
                    "uvicorn",
                    "apps.api.voice:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "18092",
                    "--no-proxy-headers",
                    "--no-access-log",
                    "--log-level",
                    "warning",
                ],
                cwd=PROJECT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            async with httpx.AsyncClient(
                base_url=URL, trust_env=False, timeout=90
            ) as client:
                deadline = time.monotonic() + 30
                while True:
                    try:
                        response = await client.get("/voice")
                        if response.status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    if web.poll() is not None or time.monotonic() > deadline:
                        raise ValueError("main_voice_web_start_failed")
                    await asyncio.sleep(0.1)
                if (await client.get("/ui/voice/status")).status_code != 401:
                    raise ValueError("main_voice_anonymous_access")
                grant = await client.post(
                    "/api/v1/voice/pairing",
                    headers={"Authorization": "Bearer " + token},
                )
                grant.raise_for_status()
                headers = {"Origin": URL, "X-Voice-Submit": "1"}
                paired = await client.post(
                    "/ui/voice/pair",
                    headers=headers,
                    json={"code": grant.json()["code"]},
                )
                paired.raise_for_status()
                try:
                    start = time.monotonic()
                    result["panel_consumed"] = True
                    response = await client.post("/ui/voice/prepare", headers=headers)
                    if response.status_code != 202:
                        raise ValueError("main_voice_prepare_denied")
                    await wait_status(client, "ready")
                    result["prepare_seconds"] = time.monotonic() - start
                    for index, row in enumerate(rows):
                        path = root / "public-inputs" / f"{index}.wav"
                        if file_sha(path) != row["wave_sha256"]:
                            raise ValueError("main_voice_input_changed")
                        row["status"] = "ATTEMPTING"
                        operation = str(uuid4())
                        started = time.monotonic()
                        response = await client.post(
                            "/ui/voice/turn",
                            headers={
                                **headers,
                                "Content-Type": "audio/wav",
                                "X-Voice-ID": operation,
                            },
                            content=path.read_bytes(),
                        )
                        elapsed = time.monotonic() - started
                        value = response.json()
                        publish(
                            root / f"HTTP-response-{index}.json",
                            dict(
                                description="Retained public input response only, no credentials or owner recording.",
                                status_code=response.status_code,
                                body=value,
                            ),
                        )
                        row["client_seconds"] = elapsed
                        if row["expected_no_answer"]:
                            if response.status_code != 422 or value != {
                                "code": "no_speech"
                            }:
                                raise ValueError("main_voice_negative_failure")
                            row["status"] = "CORRECT_NO_SPEECH"
                        else:
                            if (
                                response.status_code != 200
                                or value.get("id") != operation
                            ):
                                raise ValueError("main_voice_speech_failure")
                            previous = json.loads(
                                (
                                    PROJECT
                                    / "data/backups/d74-voice-browser-trial-first/http-native-first"
                                    / f"response-{index}.json"
                                ).read_text()
                            )["body"]
                            verify_answer(value, previous, elapsed)
                            row.update(
                                status="EXACT_COMPLETE_PCM",
                                server_seconds=value["server_seconds"],
                                stages=value["stages"],
                                playback_sha256=hashlib.sha256(
                                    base64.b64decode(value["audio_base64"])
                                ).hexdigest(),
                            )
                        publish(root / f"row-{index}.json", row)
                    result["status"] = "PASS"
                finally:
                    response = await client.post("/ui/voice/release", headers=headers)
                    result["release_HTTP_status"] = response.status_code
                    result["status_after_release"] = (
                        await client.get("/ui/voice/status")
                    ).json()
            web.send_signal(signal.SIGTERM)
            await joined_io(web.wait, timeout=20)
            log.flush()
            audit = (ram / "app.log").read_text()
            log.close()
            log = None
            if token in audit or grant.json()["code"] in audit:
                raise ValueError("main_voice_credential_logged")
            (root / "app-audit.log").write_text(audit)
            result["counts"] = {
                kind: len(
                    re.findall("main_voice_stage_admitted stage=" + kind + " ", audit)
                )
                for kind in ("vad", "asr", "core", "tts")
            }
            result["readiness"] = audit.count("voice_readiness_verified model_calls=1")
            result["workers_joined"] = len(
                re.findall("voice_native_worker_joined role=", audit)
            )
            result["web_exit"] = web.returncode
            if (
                result["counts"] != dict(vad=6, asr=4, core=4, tts=4)
                or result["readiness"] != 1
                or result["workers_joined"] != 3
                or web.returncode != 0
            ):
                raise ValueError("main_voice_call_budget_or_cleanup")
            if server.reap() is not None or server.failure:
                raise ValueError("main_voice_borrowed_core_not_preserved")
            result["CORE_alive_after_application_shutdown"] = True
    except BaseException as error:
        result["status"] = (
            "NOT_PASS" if result["panel_consumed"] else "PREFLIGHT_STOPPED"
        )
        result["failure_type"] = type(error).__name__
        if isinstance(error, ValueError) and re.fullmatch(
            r"[a-z_0-9]{1,80}", str(error)
        ):
            result["failure_code"] = str(error)
        for row in rows:
            if row["status"] == "ATTEMPTING":
                row["status"] = "FAILED"
        LOGGER.error("main_voice_campaign_stopped type=%s", type(error).__name__)
        raise
    finally:
        if web is not None and web.poll() is None:
            web.send_signal(signal.SIGTERM)
            try:
                await joined_io(web.wait, timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(web.pid, signal.SIGKILL)
                await joined_io(web.wait, timeout=5)
        if log:
            log.close()
        if (
            ram is not None
            and (ram / "app.log").exists()
            and not (root / "app-audit.log").exists()
        ):
            (root / "app-audit.log").write_bytes((ram / "app.log").read_bytes())
        if temporary is not None:
            temporary.cleanup()
        await server.stop()
        result["owned_CORE"] = server.receipt()
        result["after"] = local_state()
        result["sources_unchanged"] = source_snapshot() == prepared["source_sha256"]
        publish(root / "result.json", result)


def main():
    """Run explicit model-free preparation or the sole already-approved conditional native campaign."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="evidence directory under data/backups (one campaign per directory)",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_relative_to(PROJECT / "data/backups") or not root.is_dir():
        raise ValueError("main_voice_root_invalid")
    logging.basicConfig(level=logging.INFO)
    os.umask(0o077)
    if args.action == "prepare":
        prepare(root)
    else:
        asyncio.run(run(root))


if __name__ == "__main__":
    main()
