"""Build offline worker commands from explicit verified existing paths and unchanged resource profiles."""

import logging
from pathlib import Path

from src.infrastructure.voice.manifest import PROJECT

LOGGER = logging.getLogger(__name__)


def command(settings, role, output, samples, scope, scope_sha):
    """Expose only qualified SDK/model/source trees, RAM samples/output and exact CPU/CUDA limits."""
    if (
        role not in {"vad", "turbo", "qwen3-asr-0.6b"}
        or output.is_symlink()
        or not output.is_dir()
        or any(output.iterdir())
        or output.stat().st_mode & 0o077
    ):
        raise ValueError("voice_namespace_output_or_role")
    paths = settings.paths
    cuda = role == "qwen3-asr-0.6b"
    prefix = "tts" if role == "turbo" else "asr" if cuda else "vad"
    threads = 2 if role == "vad" else 8
    args = [
        "/usr/bin/taskset",
        "--cpu-list",
        ",".join(str(x) for x in range(threads)),
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
    mounts = [
        (paths[prefix + "_venv"], "/venv"),
        (samples, "/samples"),
        (scope, "/approved-workflow.json"),
        (PROJECT / "src/infrastructure/voice", "/app/src/infrastructure/voice"),
    ]
    if role == "vad":
        mounts.append((paths["vad_official"], "/official"))
    else:
        mounts.extend(
            [
                (paths[prefix + "_sources"], "/sources"),
                (paths[prefix + "_model"], "/model"),
            ]
        )
    if role == "turbo":
        mounts.append((paths["tts_cache"], "/hf/hub"))
    if cuda:
        mounts.append((paths["cuda_venv"], "/cuda-venv"))
    for host, guest in mounts:
        args += ["--ro-bind", str(host), guest]
    args += [
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
        "--dir",
        "/etc",
        "--ro-bind",
        str(scope.parent / "passwd"),
        "/etc/passwd",
        "--ro-bind",
        str(scope.parent / "group"),
        "/etc/group",
        "--chdir",
        "/app",
    ]
    env = dict(
        PATH="/venv/bin:/usr/bin",
        PYTHONPATH="/app:/sources:/official",
        HOME="/tmp",
        USER="asr-evaluation",
        LOGNAME="asr-evaluation",
        LANG="C.UTF-8",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPYCACHEPREFIX="/tmp/pycache",
        CUDA_VISIBLE_DEVICES="0" if cuda else "",
        HF_HOME="/hf",
        HF_HUB_CACHE="/hf/hub",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        TOKENIZERS_PARALLELISM="false",
        NUMBA_CACHE_DIR="/tmp/numba",
    )
    for name in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMBA_NUM_THREADS",
        "RAYON_NUM_THREADS",
    ):
        env[name] = str(threads)
    if cuda:
        for device in ("/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-uvm"):
            if not Path(device).exists():
                raise ValueError("voice_cuda_device_missing")
            args += ["--dev-bind", device, device]
        env["LD_LIBRARY_PATH"] = (
            ":".join(
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
            + ":/usr/lib/x86_64-linux-gnu"
        )
        env.update(CUBLAS_WORKSPACE_CONFIG=":4096:8", NVIDIA_TF32_OVERRIDE="0")
    for name, value in env.items():
        args += ["--setenv", name, value]
    virtual = 64 * 1024**3 if cuda else (3 if role == "vad" else 8) * 1024**3
    cpu = "180:181" if role == "vad" else "1200:1201"
    LOGGER.info("voice_offline_command_bound role=%s threads=%d", role, threads)
    return args + [
        "--remount-ro",
        "/",
        "--",
        "/usr/bin/prlimit",
        f"--as={virtual}",
        f"--cpu={cpu}",
        "--nofile=128",
        "--fsize=16777216",
        "--core=0",
        "--",
        "/cuda-venv/bin/python" if cuda else "/venv/bin/python",
        "-m",
        "src.infrastructure.voice.worker",
        scope_sha,
    ]
