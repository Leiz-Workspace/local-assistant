"""Complete the remaining D14 measurement domains on sequential existing GPU profiles without changing application defaults, model artifacts or historical scores."""

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.full_regression import source_manifest, verify_manifest
from scripts.profile_excerpt_evaluation import publish
from src.application.services.profile_prompts import TEMPLATES

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/backups/d14-completion-20261026"
FREEZE = ROOT / "docs/evidence/d14-completion-pre-inference-freeze.json"
ENDPOINT = "http://127.0.0.1:18080"
WEIGHTS = dict(multimodal=10, performance=10, memory_context=5, provenance=5)


def digest(path):
    """Hash exact complete artifact bytes in bounded blocks without changing or copying model weights."""
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def local_state():
    """Capture non-secret boot, native-process and original container identities without opening Vault or a database."""
    native = []
    for path in Path("/proc").glob("[0-9]*/comm"):
        try:
            if path.read_text().strip() == "llama-server":
                native.append(int(path.parent.name))
        except OSError:
            continue
    containers = subprocess.check_output(
        [
            "docker",
            "ps",
            "--no-trunc",
            "--format",
            "{{.ID}} {{.Names}} {{.Image}} {{.Ports}}",
        ],
        text=True,
        timeout=10,
    )
    LOGGER.info("d14_readonly_runtime_inventory native=%d", len(native))
    return dict(
        boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        native_pids=sorted(native),
        containers=sorted(containers.splitlines()),
    )


def resources(pid=None):
    """Sample host RAM, whole-child RSS and per-process GPU allocation while exposing that these guards do not reserve memory."""
    available = next(
        int(line.split()[1])
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    gpu = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        text=True,
        timeout=5,
    )
    allocations = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_memory",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=5,
    )
    used = 0
    for line in allocations.splitlines():
        fields = [item.strip() for item in line.split(",")]
        if len(fields) == 2 and fields[0] == str(pid):
            used += int(fields[1])
    rss = 0
    if pid is not None:
        status = Path(f"/proc/{pid}/status").read_text()
        rss = next(
            int(line.split()[1])
            for line in status.splitlines()
            if line.startswith("VmRSS:")
        )
    return dict(
        available_RAM_KiB=available,
        GPU_free_MiB=int(gpu.splitlines()[0]),
        owned_RSS_KiB=rss,
        owned_GPU_MiB=used,
    )


def require_free_port(port=18080):
    """Reject a live listener while allowing native SO_REUSEADDR rebinding after owned connections enter TIME_WAIT."""
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))
    LOGGER.info("d14_owned_loopback_port_available")


def command(profile):
    """Select only the exact configured existing profile, projector and runtime with identical sequential GPU settings."""
    if profile not in {"core", "unrestricted"}:
        raise ValueError("d14_profile_invalid")
    model = yaml.safe_load((ROOT / "configs/models.yaml").read_text())["models"][
        profile
    ]
    if (
        model["inference"]["context_size"] != 32768
        or model["inference"]["reasoning"] != "off"
    ):
        raise ValueError("d14_configuration_changed")
    return [
        str(ROOT / "runtimes/llama.cpp/build-cuda/bin/llama-server"),
        "--model",
        str(ROOT / model["path"]),
        "--mmproj",
        str(ROOT / model["mmproj_path"]),
        "--alias",
        model["name"],
        "--host",
        "127.0.0.1",
        "--port",
        "18080",
        "--n-gpu-layers",
        "99",
        "--ctx-size",
        "32768",
        "--parallel",
        "1",
        "--reasoning",
        "off",
        "--threads",
        "2",
        "--threads-batch",
        "2",
        "--threads-http",
        "2",
        "--batch-size",
        "512",
        "--ubatch-size",
        "128",
        "--offline",
        "--no-warmup",
        "--no-webui",
        "--slots",
    ]


def strict_score(content, expected):
    """Compare complete typed strict JSON without coercion, extraction, duplicate keys, response repair or normalization."""

    def pairs(items):
        """Reject duplicate object keys rather than accepting last-value overwrite."""
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate_key")
            value[key] = item
        return value

    def invalid(value):
        """Reject nonfinite JSON constants instead of treating them as ordinary answers."""
        raise ValueError("nonfinite_json")

    try:
        actual = json.loads(content, object_pairs_hook=pairs, parse_constant=invalid)
        options = dict(
            sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        return json.dumps(actual, **options) == json.dumps(expected, **options)
    except (ValueError, TypeError, RecursionError):
        return False


def fixtures(root):
    """Create five neutral deterministic raster oracles without reusing observed vision cases or modifying existing fixtures."""
    root.mkdir(mode=0o700)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
    cases = []
    definitions = [
        (
            "ocr",
            "Read the image. Return only JSON with keys code and amount; both values strings.",
            {"code": "KITE-482", "amount": "73.50"},
        ),
        (
            "table",
            "Read both rows in order. Return only JSON with key rows, each row [name, quantity].",
            {"rows": [["MIRA", 14], ["LUMA", 29]]},
        ),
        (
            "chart",
            "Read the labeled bar values. Return only JSON mapping A, B and C to their numeric values.",
            {"A": 20, "B": 50, "C": 30},
        ),
        (
            "shapes",
            "Read left to right. Return only JSON with keys left and right, each value a color and shape string.",
            {"left": "blue circle", "right": "orange rectangle"},
        ),
        (
            "vietnamese",
            "Đọc đúng nội dung ảnh. Chỉ trả JSON với khóa destination và quantity; destination là chuỗi, quantity là số nguyên.",
            {"destination": "Đà Nẵng", "quantity": 18},
        ),
    ]
    for name, prompt, expected in definitions:
        image = Image.new("RGB", (800, 450), "white")
        draw = ImageDraw.Draw(image)
        if name == "ocr":
            draw.text((45, 95), "CODE: KITE-482", font=font, fill="black")
            draw.text((45, 195), "AMOUNT: 73.50", font=font, fill="black")
        elif name == "table":
            for y, text in [
                (70, "NAME                 QUANTITY"),
                (170, "MIRA                  14"),
                (270, "LUMA                  29"),
            ]:
                draw.text((40, y), text, font=font, fill="black")
            for y in [130, 230, 330]:
                draw.line((30, y, 760, y), fill="black", width=2)
        elif name == "chart":
            for x, label, value in [(100, "A", 20), (320, "B", 50), (540, "C", 30)]:
                top = 350 - value * 5
                draw.rectangle((x, top, x + 100, 350), fill="steelblue")
                draw.text((x + 20, top - 45), str(value), font=font, fill="black")
                draw.text((x + 35, 365), label, font=font, fill="black")
        elif name == "shapes":
            draw.ellipse((90, 120, 290, 320), fill="blue")
            draw.rectangle((480, 150, 720, 300), fill="orange")
        else:
            draw.text((50, 100), "Điểm đến: Đà Nẵng", font=font, fill="black")
            draw.text((50, 210), "Số lượng: 18", font=font, fill="black")
        path = root / (name + ".png")
        image.save(path)
        os.chmod(path, 0o600)
        cases.append(
            dict(
                id="media-" + name,
                category="multimodal",
                prompt=prompt,
                expected=expected,
                image=str(path.relative_to(ROOT)),
                image_sha256=digest(path),
            )
        )
    LOGGER.info("d14_five_fresh_raster_oracles_created")
    return cases


def source_binding(item, directory):
    """Resolve only an exact old path or known flattened upstream copy with the original complete hash, retaining stale-path disclosure."""
    original = ROOT / item["file"]
    candidate = original
    if not original.is_file() and original.parent == directory / "upstream_reference":
        candidate = directory / (
            "UPSTREAM_LICENSE" if original.name == "LICENSE" else original.name
        )
    verified = (
        candidate.is_file()
        and not candidate.is_symlink()
        and digest(candidate) == item["sha256"]
    )
    LOGGER.info(
        "d14_local_source_binding_checked relocated=%s verified=%s",
        candidate != original,
        verified,
    )
    return dict(
        recorded_path=item["file"],
        actual_path=str(candidate.relative_to(ROOT)),
        original_path_exists=original.is_file(),
        relocated_copy=candidate != original,
        complete_sha256_matches=verified,
        original_sha256=item["sha256"],
    )


def provenance(profile):
    """Check five locally evidenced provenance properties, preserving missing paths and distinguishing declarations from remote or legal verification."""
    config = yaml.safe_load((ROOT / "configs/models.yaml").read_text())["models"][
        profile
    ]
    directory = (ROOT / config["path"]).parent
    source = json.loads((directory / "metadata-sources.json").read_text())
    cached = (
        (
            directory
            / ".cache/huggingface/download"
            / (Path(config["path"]).name + ".metadata")
        )
        .read_text()
        .splitlines()
    )
    checks = []
    checks.append(
        dict(
            id="model_pin",
            passed=bool(
                len(cached) == 3
                and re.fullmatch("[a-f0-9]{40}", cached[0])
                and cached[1] == config["sha256"] == digest(ROOT / config["path"])
            ),
            local_repository=config["repository"],
            local_declared_revision=cached[0],
        )
    )
    projectors = [
        item for item in source["files"] if item["file"] == config["mmproj_path"]
    ]
    checks.append(
        dict(
            id="projector_pin",
            passed=bool(
                len(projectors) == 1
                and projectors[0]["repository"] == config["repository"]
                and re.fullmatch("[a-f0-9]{40}", projectors[0]["revision"])
                and digest(ROOT / config["mmproj_path"]) == projectors[0]["sha256"]
            ),
        )
    )
    bindings = [source_binding(item, directory) for item in source["files"]]
    checks.append(
        dict(
            id="complete_local_source_manifest",
            passed=all(item["complete_sha256_matches"] for item in bindings),
            bindings=bindings,
            original_manifest_paths_all_present=all(
                item["original_path_exists"] for item in bindings
            ),
        )
    )
    original = json.loads(
        (ROOT / "docs/evidence/d90-candidate-model-runtime-snapshot.json").read_text()
    )
    revision = subprocess.check_output(
        ["git", "-C", str(ROOT / "runtimes/llama.cpp"), "rev-parse", "HEAD"], text=True
    ).strip()
    checks.append(
        dict(
            id="runtime_pin",
            passed=revision == original["runtime_git_commit"]
            and all(
                digest(ROOT / path) == item["sha256"]
                for path, item in original["runtime_files"].items()
            ),
        )
    )
    licenses = [
        item for item in source["files"] if Path(item["file"]).name == "LICENSE"
    ]
    checks.append(
        dict(
            id="pinned_license_copy",
            passed=bool(licenses)
            and all(
                source_binding(item, directory)["complete_sha256_matches"]
                for item in licenses
            ),
            legal_clearance=False,
            remote_attestation=False,
        )
    )

    LOGGER.info(
        "d14_local_provenance_checked profile=%s passed=%d",
        profile,
        sum(row["passed"] for row in checks),
    )
    return checks


class OwnedServer:
    """Own one sequential native GPU child and bounded guard/retirement lifecycle without touching unrelated processes or containers."""

    def __init__(self, profile, root):
        """Bind the selected existing profile and fresh output directory without loading a model."""
        self.profile, self.root = profile, root
        self.process, self.monitor_task, self.log = None, None, None
        self.failure, self.usage, self.exit_code = None, None, None
        self.peak_rss, self.peak_gpu = 0, 0
        self.minimum_free_gpu, self.minimum_available_ram = None, None
        self.before = None

    def reap(self):
        """Reap only the exact owned PID and retain native wait4 peak RAM and CPU accounting."""
        if self.process is None or self.exit_code is not None:
            return self.exit_code
        pid, status, usage = os.wait4(self.process.pid, os.WNOHANG)
        if pid:
            self.exit_code = os.waitstatus_to_exitcode(status)
            self.process.returncode = self.exit_code
            self.usage = dict(
                peak_RSS_RAM_KiB=usage.ru_maxrss,
                user_CPU_seconds=usage.ru_utime,
                system_CPU_seconds=usage.ru_stime,
            )
        return self.exit_code

    async def monitor(self):
        """Stop the owned group on sampled RAM/VRAM uncertainty, resource exhaustion or unexpected native-server overlap."""
        try:
            while self.reap() is None:
                current_native = []
                for path in Path("/proc").glob("[0-9]*/comm"):
                    try:
                        if path.read_text().strip() == "llama-server":
                            current_native.append(int(path.parent.name))
                    except OSError:
                        continue
                if set(current_native) != {self.process.pid}:
                    raise ValueError("d14_unexpected_native_overlap")
                sample = resources(self.process.pid)
                self.peak_rss = max(self.peak_rss, sample["owned_RSS_KiB"])
                self.peak_gpu = max(self.peak_gpu, sample["owned_GPU_MiB"])
                self.minimum_free_gpu = min(
                    self.minimum_free_gpu or sample["GPU_free_MiB"],
                    sample["GPU_free_MiB"],
                )
                self.minimum_available_ram = min(
                    self.minimum_available_ram or sample["available_RAM_KiB"],
                    sample["available_RAM_KiB"],
                )
                if (
                    sample["owned_RSS_KiB"] > 12 * 1024**2
                    or sample["owned_GPU_MiB"] > 14 * 1024
                    or sample["available_RAM_KiB"] < 4 * 1024**2
                    or sample["GPU_free_MiB"] < 512
                ):
                    raise ValueError("d14_sampled_resource_guard")
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.failure = (
                str(exc)
                if isinstance(exc, ValueError)
                else "d14_resource_monitor_uncertain"
            )
            LOGGER.warning("d14_owned_guard_stopping profile=%s", self.profile)
            if self.reap() is None:
                os.killpg(self.process.pid, signal.SIGTERM)

    async def start(self):
        """Require an empty native/GPU test slot, launch exact existing artifacts and verify alias, context and multimodal readiness."""
        if self.process is not None:
            raise ValueError("d14_server_already_started")
        self.before = local_state()
        if self.before["native_pids"]:
            raise ValueError("d14_native_runtime_busy")
        sample = resources()
        publish(self.root / "preflight.json", sample)
        if (
            sample["available_RAM_KiB"] < 14 * 1024**2
            or sample["GPU_free_MiB"] < 14 * 1024
        ):
            raise ValueError("d14_preflight_headroom")
        require_free_port()
        environment = {
            key: os.environ[key]
            for key in ["PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH"]
            if key in os.environ
        }
        environment.update(
            OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2"
        )
        self.log = (self.root / "server.log").open("xb")
        os.chmod(self.root / "server.log", 0o600)
        self.process = subprocess.Popen(
            command(self.profile),
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        publish(
            self.root / "launch.json",
            dict(
                command=command(self.profile),
                pid=self.process.pid,
                state_before=self.before,
                preflight_resources=sample,
                address_space_cap=None,
                memory_guard="sampled_not_reserved_not_a_hard_cgroup_limit",
            ),
        )
        self.monitor_task = asyncio.create_task(self.monitor())
        deadline = time.monotonic() + 240
        async with httpx.AsyncClient(
            base_url=ENDPOINT, trust_env=False, timeout=3
        ) as client:
            while time.monotonic() < deadline:
                if self.failure or self.reap() is not None:
                    raise ValueError("d14_native_start_failed")
                try:
                    health = await client.get("/health")
                    if health.status_code == 200:
                        models, props = (
                            (await client.get("/v1/models")).json(),
                            (await client.get("/props")).json(),
                        )
                        alias = "qwen3.5-9b-" + self.profile
                        if {item["id"] for item in models["data"]} != {alias} or props[
                            "default_generation_settings"
                        ]["n_ctx"] != 32768:
                            raise ValueError("d14_runtime_identity_mismatch")
                        publish(
                            self.root / "ready.json", dict(models=models, props=props)
                        )
                        LOGGER.info("d14_native_ready profile=%s", self.profile)
                        return
                except (httpx.ConnectError, httpx.ReadTimeout):
                    pass
                await asyncio.sleep(0.5)
        raise ValueError("d14_native_start_timeout")

    async def stop(self):
        """Join the monitor and terminate/reap only this owned group with a finite TERM/KILL retirement boundary."""
        if self.monitor_task is not None:
            self.monitor_task.cancel()
            await asyncio.gather(self.monitor_task, return_exceptions=True)
        if self.process is not None and self.reap() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            deadline = time.monotonic() + 20
            while self.reap() is None and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            if self.reap() is None:
                os.killpg(self.process.pid, signal.SIGKILL)
                deadline = time.monotonic() + 10
                while self.reap() is None and time.monotonic() < deadline:
                    await asyncio.sleep(0.1)
                if self.exit_code is None:
                    raise ValueError("d14_native_retirement_uncertain")
        if self.log is not None:
            self.log.close()
        LOGGER.info(
            "d14_owned_native_retired profile=%s exit=%s", self.profile, self.exit_code
        )

    def receipt(self):
        """Expose native whole-process RAM/CPU and sampled GPU peaks separately from virtual address space and model-only costs."""
        return dict(
            profile=self.profile,
            pid=self.process.pid if self.process else None,
            exit_code=self.exit_code,
            reaped=self.exit_code is not None,
            native_wait4_usage=self.usage,
            sampled_peak_VRAM_MiB=self.peak_gpu,
            sampled_peak_RSS_KiB=self.peak_rss,
            sampled_min_GPU_free_MiB=self.minimum_free_gpu,
            sampled_min_MemAvailable_KiB=self.minimum_available_ram,
            guard_failure=self.failure,
        )


async def token_count(client, text):
    """Count native user-content tokens during deterministic calibration without generating a model response."""
    response = await client.post(
        "/tokenize", json=dict(content=text, add_special=False)
    )
    response.raise_for_status()
    tokens = response.json()["tokens"]
    if type(tokens) is not list:
        raise ValueError("d14_tokenizer_schema")
    return len(tokens)


async def context_prompt(client, case):
    """Place a frozen needle at a calibrated prefix in a near-full 32K document without observing or tuning against answers."""
    lines = [
        f"Entry {number:05d}: The archive lists neutral records about ordinary scheduling and routine calibration."
        for number in range(2100)
    ]
    low, high = 0, len(lines)
    while low < high:
        mid = (low + high) // 2
        if await token_count(client, "\n".join(lines[:mid])) < case["needle_target"]:
            low = mid + 1
        else:
            high = mid
    position = low
    prefix = lines[:position]
    tail = lines[position:]
    intro = "Find the only RELEASE_CODE in the document. Return only a JSON object with key code and its string value.\nDOCUMENT:\n"
    needle = "RELEASE_CODE: " + case["needle"]
    end = "\nEND DOCUMENT. Return the exact release code."
    low, high = 0, len(tail)
    while low < high:
        mid = (low + high + 1) // 2
        text = intro + "\n".join(prefix + [needle] + tail[:mid]) + end
        if await token_count(client, text) <= 30500:
            low = mid
        else:
            high = mid - 1
    prompt = intro + "\n".join(prefix + [needle] + tail[:low]) + end
    count = await token_count(client, prompt)
    offset = await token_count(client, intro + "\n".join(prefix))
    if not 30000 <= count <= 30500 or abs(offset - case["needle_target"]) > 100:
        raise ValueError("d14_context_calibration_invalid")
    LOGGER.info(
        "d14_context_calibrated id=%s tokens=%d offset=%d", case["id"], count, offset
    )
    return prompt, dict(user_tokens=count, needle_prefix_tokens=offset)


def decode_stream(raw, expected_model):
    """Decode complete SSE events while requiring actual native model identity, one choice and terminal DONE before trusting a completion."""
    content, finish, usage = [], None, None
    lines = raw.decode("utf-8").splitlines()
    if not lines or raw.decode().rstrip().splitlines()[-1] != "data: [DONE]":
        raise ValueError("d14_stream_incomplete")
    for line in lines:
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        item = json.loads(line[6:])
        if item.get("model") != expected_model:
            raise ValueError("d14_stream_model_mismatch")
        if item.get("usage"):
            usage = item["usage"]
        if len(item.get("choices", [])) > 1:
            raise ValueError("d14_stream_multiple_choices")
        for choice in item.get("choices", []):
            if choice.get("index") != 0:
                raise ValueError("d14_stream_foreign_choice")
            text = choice.get("delta", {}).get("content", "")
            if text:
                if type(text) is not str:
                    raise ValueError("d14_stream_content_invalid")
                content.append(text)
            if choice.get("finish_reason"):
                if finish is not None:
                    raise ValueError("d14_stream_duplicate_finish")
                finish = choice["finish_reason"]
    return dict(
        model=expected_model,
        choices=[dict(message=dict(content="".join(content)), finish_reason=finish)],
        usage=usage,
    )


async def first_request(
    client, profile, case, root, *, content=None, stream=False, calibration=None
):
    """Spend one request slot and retain bounded native bytes before strict scoring; never repair, retry or regenerate a failed answer."""
    directory = root / case["id"]
    directory.mkdir(mode=0o700)
    messages = [
        dict(role="system", content=TEMPLATES[profile]),
        dict(role="user", content=content if content is not None else case["prompt"]),
    ]
    request = dict(
        model="qwen3.5-9b-" + profile,
        messages=messages,
        temperature=0,
        max_tokens=256,
        stream=stream,
        cache_prompt=False,
        chat_template_kwargs=dict(enable_thinking=False),
    )
    if stream:
        request["stream_options"] = dict(include_usage=True)
    publish(directory / "request.json", request)
    start, raw, first_token, response = time.monotonic(), bytearray(), None, None
    pending_frame = bytearray()
    result = dict(
        id=case["id"],
        category=case["category"],
        model_requests=1,
        passed=False,
        response_contract_passed=False,
        stream=stream,
        calibration=calibration,
    )
    try:
        async with asyncio.timeout(90 if case["category"] == "memory_context" else 60):
            async with client.stream(
                "POST", "/v1/chat/completions", json=request
            ) as wire:
                result["http_status"] = wire.status_code
                async for block in wire.aiter_bytes():
                    raw.extend(block)
                    if len(raw) > 262144:
                        raise ValueError("d14_response_limit")
                    if stream:
                        pending_frame.extend(block)
                        while b"\n" in pending_frame:
                            line, _, tail = pending_frame.partition(b"\n")
                            pending_frame[:] = tail
                            if line.startswith(b"data: ") and line != b"data: [DONE]":
                                event = json.loads(line[6:])
                                if first_token is None and any(
                                    choice.get("delta", {}).get("content")
                                    for choice in event.get("choices", [])
                                ):
                                    first_token = time.monotonic() - start
                if wire.status_code != 200:
                    raise ValueError("d14_native_http_failure")
        publish(directory / "native-response.bin", bytes(raw))
        if stream:
            response = decode_stream(bytes(raw), request["model"])
        else:
            response = json.loads(raw)
        choice, usage = response["choices"][0], response["usage"]
        result["reply"] = response
        valid = (
            response["model"] == request["model"]
            and choice["finish_reason"] == "stop"
            and type(usage["prompt_tokens"]) is int
            and type(usage["completion_tokens"]) is int
            and usage["prompt_tokens"] > 0
            and usage["completion_tokens"] > 0
        )
        if case["category"] == "memory_context":
            valid = valid and 30000 <= usage["prompt_tokens"] <= 32000
        if stream:
            valid = (
                valid
                and bytes(raw).decode().rstrip().endswith("data: [DONE]")
                and first_token is not None
            )
        result.update(
            response_contract_passed=bool(valid),
            passed=bool(
                valid and strict_score(choice["message"]["content"], case["expected"])
            ),
        )
    except BaseException as exc:
        result.update(
            error_type=type(exc).__name__,
            error_code=str(exc)
            if isinstance(exc, ValueError)
            else "d14_first_request_failure",
        )
        if not (directory / "native-response.bin").exists():
            publish(directory / "native-response.bin", bytes(raw))
        if isinstance(exc, asyncio.CancelledError):
            raise
    finally:
        result.update(
            wall_seconds=time.monotonic() - start,
            first_content_frame_seconds=first_token if stream else None,
            native_response_sha256=hashlib.sha256(raw).hexdigest(),
        )
        publish(directory / "measurement.json", result)
        LOGGER.info(
            "d14_first_case_recorded profile=%s id=%s passed=%s",
            profile,
            case["id"],
            result["passed"],
        )
    return result


async def cancellation_probe(client, profile, root):
    """Start one planned neutral stream, close after real content and require native slot retirement without another generation or retry."""
    request = dict(
        model="qwen3.5-9b-" + profile,
        messages=[
            dict(role="system", content=TEMPLATES[profile]),
            dict(
                role="user",
                content="Count positive integers in order, separated by commas, starting from 1 and continuing until 100000. Do not summarize.",
            ),
        ],
        temperature=0,
        max_tokens=2048,
        stream=True,
        cache_prompt=False,
        chat_template_kwargs=dict(enable_thinking=False),
    )
    publish(root / "cancel-request.json", request)
    receipt = dict(
        model_requests=1,
        status="FAILED",
        first_content_observed=False,
        client_stream_closed=False,
        native_slot_retired=False,
    )
    captured, pending = bytearray(), bytearray()
    try:
        async with asyncio.timeout(30):
            async with client.stream(
                "POST", "/v1/chat/completions", json=request
            ) as response:
                response.raise_for_status()
                async for block in response.aiter_bytes():
                    captured.extend(block)
                    pending.extend(block)
                    if len(captured) > 131072:
                        raise ValueError("d14_cancel_capture_limit")
                    while b"\n" in pending:
                        line, _, tail = pending.partition(b"\n")
                        pending[:] = tail
                        if line.startswith(b"data: ") and line != b"data: [DONE]":
                            frame = json.loads(line[6:])
                            if frame.get("model") != request["model"]:
                                raise ValueError("d14_cancel_model_mismatch")
                            if any(
                                choice.get("delta", {}).get("content")
                                for choice in frame.get("choices", [])
                            ):
                                receipt["first_content_observed"] = True
                    if receipt["first_content_observed"]:
                        break
            receipt["client_stream_closed"] = True
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                response = await client.get("/slots")
                response.raise_for_status()
                slots = response.json()
                if (
                    type(slots) is list
                    and len(slots) == 1
                    and slots[0].get("is_processing") is False
                ):
                    receipt.update(
                        native_slot_retired=True,
                        status="PASS_PLANNED_CANCEL_AND_NATIVE_SLOT_RETIREMENT",
                    )
                    break
                await asyncio.sleep(0.2)
            if receipt["status"] != "PASS_PLANNED_CANCEL_AND_NATIVE_SLOT_RETIREMENT":
                raise ValueError("d14_cancel_slot_uncertain")
    except BaseException as exc:
        receipt.update(
            error_type=type(exc).__name__,
            error_code=str(exc)
            if isinstance(exc, ValueError)
            else "d14_cancel_probe_failure",
        )
        if isinstance(exc, asyncio.CancelledError):
            raise
    finally:
        publish(root / "cancel-response-prefix.bin", bytes(captured))
        publish(root / "cancel-receipt.json", receipt)
        LOGGER.info(
            "d14_planned_cancel_recorded profile=%s status=%s",
            profile,
            receipt["status"],
        )
    return receipt


def weighted(text_points, rows, checks):
    """Apply original weights to explicit domain criteria while retaining every first failure and marking the result as a mixed-date local scorecard."""
    categories = {}
    for name in ["multimodal", "performance", "memory_context"]:
        selected = [row for row in rows if row["category"] == name]
        expected = dict(multimodal=5, performance=3, memory_context=4)[name]
        if (
            len(selected) != expected
            or len({row["id"] for row in selected}) != expected
        ):
            raise ValueError("d14_incomplete_domain_accounting")
        categories[name] = dict(
            passed=sum(row["passed"] for row in selected),
            total=expected,
            weight=WEIGHTS[name],
        )
    categories["provenance"] = dict(
        passed=sum(row["passed"] for row in checks), total=5, weight=5
    )
    if len(checks) != 5 or len({row["id"] for row in checks}) != 5:
        raise ValueError("d14_incomplete_provenance_accounting")
    if type(text_points) not in (int, float) or not 0 <= text_points <= 70:
        raise ValueError("d14_text_weight_invalid")
    for value in categories.values():
        value["earned"] = value["weight"] * value["passed"] / value["total"]
    LOGGER.info("d14_weighted_local_score_computed")
    return dict(
        categories=categories,
        retained_text_points=text_points,
        local_composite_points=text_points
        + sum(item["earned"] for item in categories.values()),
        covered_weight=100,
        universal_model_capability_score=False,
        quality_acceptance_inferred=False,
    )


def validate_continuation(prior):
    """Allow only the never-loaded UNRESTRICTED suffix while retaining the complete first CORE cohort and rejecting any replayed request."""
    core = prior.get("profiles", {}).get("core", {})
    other = prior.get("profiles", {}).get("unrestricted", {})
    if (
        prior.get("status") != "INCOMPLETE"
        or prior.get("runtime_baseline_restored") is not True
        or len(core.get("rows", [])) != 12
        or len({row.get("id") for row in core["rows"]}) != 12
        or any(row.get("model_requests") != 1 for row in core["rows"])
        or core.get("runtime", {}).get("reaped") is not True
        or core["runtime"].get("exit_code") != 0
        or core["runtime"].get("guard_failure") is not None
        or core.get("cancellation", {}).get("model_requests") != 1
        or core["cancellation"].get("native_slot_retired") is not True
        or other.get("rows") != []
        or other.get("runtime", {}).get("pid") is not None
        or other["runtime"].get("reaped") is not False
    ):
        raise ValueError("d14_continuation_not_unmeasured_suffix")
    LOGGER.info("d14_never_loaded_unrestricted_suffix_eligibility_verified")
    return core


async def run():
    """Execute one frozen sequential two-profile campaign, retaining first observations and always retiring only owned test processes."""
    frozen = json.loads(FREEZE.read_text())
    for name, expected in frozen["sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("d14_frozen_input_changed")
    source = source_manifest()
    if source != frozen["application_sha256"]:
        raise ValueError("d14_application_changed")
    before = local_state()
    if before["native_pids"]:
        raise ValueError("d14_original_runtime_busy")
    publish(OUTPUT / "execution-freeze.json", frozen)
    summary = dict(
        description="Actual D14 missing-domain observations; original text first scores and every failure remain retained. Mixed-date/backend local engineering scorecard, not universal model superiority or release approval.",
        status="INCOMPLETE",
        profiles={},
        baseline=before,
        automatic_retries=0,
        model_or_default_changes=0,
        downloads=0,
    )
    if "retained_prior_result" in frozen:
        prior_path = ROOT / frozen["retained_prior_result"]["path"]
        prior = json.loads(prior_path.read_text())
        if digest(prior_path) != frozen["retained_prior_result"]["sha256"] or list(
            (prior_path.parent / "unrestricted").iterdir()
        ):
            raise ValueError("d14_prior_suffix_changed")
        summary["profiles"]["core"] = validate_continuation(prior)
        summary["retained_prior_result"] = frozen["retained_prior_result"]
        summary["profile_artifact_roots"] = dict(
            core=str(prior_path.parent / "core"),
            unrestricted=str(OUTPUT / "unrestricted"),
        )
    try:
        async with asyncio.timeout(2400):
            for profile in frozen.get("profiles_to_execute", ["core", "unrestricted"]):
                root = OUTPUT / profile
                root.mkdir(mode=0o700)
                server = OwnedServer(profile, root)
                rows = []
                summary["profiles"][profile] = dict(rows=rows)
                try:
                    await server.start()
                    async with httpx.AsyncClient(
                        base_url=ENDPOINT, trust_env=False, timeout=100
                    ) as client:
                        for case in frozen["media"]:
                            raw = (ROOT / case["image"]).read_bytes()
                            content = [
                                dict(type="text", text=case["prompt"]),
                                dict(
                                    type="image_url",
                                    image_url=dict(
                                        url="data:image/png;base64,"
                                        + base64.b64encode(raw).decode()
                                    ),
                                ),
                            ]
                            rows.append(
                                await first_request(
                                    client, profile, case, root, content=content
                                )
                            )
                        for case in frozen["context"]:
                            prompt, calibration = await context_prompt(client, case)
                            rows.append(
                                await first_request(
                                    client,
                                    profile,
                                    case,
                                    root,
                                    content=prompt,
                                    calibration=calibration,
                                )
                            )
                        for case in frozen["performance"]:
                            rows.append(
                                await first_request(
                                    client, profile, case, root, stream=True
                                )
                            )
                        cancel = await cancellation_probe(client, profile, root)
                    checks = provenance(profile)
                    score = weighted(
                        frozen["retained_text_points"][profile], rows, checks
                    )
                    summary["profiles"][profile] = dict(
                        rows=rows, provenance=checks, score=score, cancellation=cancel
                    )
                finally:
                    await server.stop()
                    summary["profiles"].setdefault(profile, {})["runtime"] = (
                        server.receipt()
                    )
                    if server.failure or (
                        server.exit_code is not None
                        and server.exit_code not in (0, -15)
                    ):
                        raise ValueError("d14_native_guard_or_exit_failure")
            summary["status"] = "MEASUREMENT_COMPLETE_QUALITY_FINDINGS_RETAINED"
    except BaseException as exc:
        summary.update(
            error_type=type(exc).__name__,
            error_code=str(exc)
            if isinstance(exc, ValueError)
            else "d14_campaign_interrupted",
        )
    finally:
        summary["after"] = local_state()
        summary["runtime_baseline_restored"] = summary["after"] == before
        try:
            verify_manifest(source)
            summary["application_files_unchanged"] = True
        except Exception:
            summary.update(
                status="INCOMPLETE",
                application_files_unchanged=False,
                error_code="d14_application_drift",
            )
        publish(OUTPUT / "result.json", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--continue-unmeasured", action="store_true")
    options = parser.parse_args()
    if options.continue_unmeasured:
        OUTPUT = ROOT / "data/backups/d14-completion-20261026-unrestricted-first"
        FREEZE = ROOT / "docs/evidence/d14-completion-unmeasured-suffix-freeze.json"
    if not options.execute:
        print(
            "Dry run: freeze protocol, test controls and use --execute for one owned sequential campaign."
        )
    else:
        result = asyncio.run(run())
        print(
            json.dumps(
                dict(
                    status=result["status"],
                    baseline_restored=result["runtime_baseline_restored"],
                    scores={
                        key: value.get("score")
                        for key, value in result["profiles"].items()
                    },
                ),
                sort_keys=True,
            )
        )
        raise SystemExit(
            0
            if result["status"] == "MEASUREMENT_COMPLETE_QUALITY_FINDINGS_RETAINED"
            and result["runtime_baseline_restored"]
            else 1
        )
