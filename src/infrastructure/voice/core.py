"""Borrow an attested loopback CORE without starting, killing, resetting or adopting shared processes."""

import asyncio
import hashlib
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from src.infrastructure.voice.manifest import PINS, file_sha

LOGGER = logging.getLogger(__name__)


def process_identity(pid):
    """Identify a same-user native process by boot, start clock, executable and complete command bytes."""
    base = Path("/proc") / str(pid)
    fields = (base / "stat").read_text().rpartition(") ")[2].split()
    return dict(
        pid=pid,
        start_ticks=int(fields[19]),
        uid=base.stat().st_uid,
        boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        executable=os.readlink(base / "exe"),
        command_sha256=hashlib.sha256((base / "cmdline").read_bytes()).hexdigest(),
    )


class BorrowedCore:
    """Validate exact CORE identity and bounded idle slots while retaining external lifecycle ownership."""

    def __init__(self, settings, transport=None):
        """Bind approved attestation and an optional controlled transport without backend activity."""
        self.settings, self.transport = settings, transport
        self.pid = settings["identity"]["pid"]
        parsed = urlsplit(settings["URL"])
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or not parsed.port
        ):
            raise ValueError("core_not_ready")
        self.port = parsed.port

    def check(self):
        """Reject PID reuse, changed runtime flags or a listener not owned by the attested same-user process."""
        if (
            process_identity(self.pid) != self.settings["identity"]
            or self.settings["identity"]["uid"] != os.geteuid()
        ):
            raise ValueError("core_not_ready")
        cmd = (
            (Path("/proc") / str(self.pid) / "cmdline")
            .read_bytes()
            .decode()
            .strip("\0")
            .split("\0")
        )
        required = {
            "--host": "127.0.0.1",
            "--port": str(self.port),
            "--ctx-size": "32768",
            "--parallel": "1",
            "--alias": "qwen3.5-9b-core",
            "--reasoning": "off",
            "--model": self.settings["model_path"],
        }
        for flag, value in required.items():
            if cmd.count(flag) != 1 or cmd[cmd.index(flag) + 1] != value:
                raise ValueError("core_not_ready")
        if "--slots" not in cmd or "--offline" not in cmd:
            raise ValueError("core_not_ready")
        sockets = set()
        for path in (Path("/proc") / str(self.pid) / "fd").iterdir():
            try:
                sockets.add(os.readlink(path))
            except OSError:
                continue
        rows = Path("/proc/net/tcp").read_text().splitlines()[1:]
        if not any(
            row.split()[1] == f"0100007F:{self.port:04X}"
            and row.split()[3] == "0A"
            and "socket:[" + row.split()[9] + "]" in sockets
            for row in rows
        ):
            raise ValueError("core_not_ready")

    async def verify(self):
        """Verify actual binary/model binding and advertised alias/context without sending user content."""
        self.check()
        if (
            file_sha(self.settings["identity"]["executable"])
            != self.settings["executable_sha256"]
            or self.settings["model_sha256"] != PINS["CORE_GGUF"]
        ):
            raise ValueError("core_not_ready")
        async with httpx.AsyncClient(
            base_url=self.settings["URL"],
            trust_env=False,
            transport=self.transport,
            timeout=2,
        ) as client:
            models = await client.get("/v1/models")
            models.raise_for_status()
            props = await client.get("/props")
            props.raise_for_status()
            if [x.get("id") for x in models.json()["data"]] != [
                "qwen3.5-9b-core"
            ] or props.json()["default_generation_settings"]["n_ctx"] != 32768:
                raise ValueError("core_not_ready")
        await self.quiesce()
        LOGGER.info("voice_borrowed_core_verified")

    async def quiesce(self):
        """Require two bounded consecutive idle-slot observations before releasing shared CORE admission."""
        async with asyncio.timeout(5):
            idle = 0
            async with httpx.AsyncClient(
                base_url=self.settings["URL"],
                trust_env=False,
                transport=self.transport,
                timeout=1,
            ) as client:
                while idle < 2:
                    self.check()
                    response = await client.get("/slots")
                    response.raise_for_status()
                    rows = response.json()
                    if (
                        type(rows) is not list
                        or len(rows) != 1
                        or type(rows[0].get("is_processing")) is not bool
                    ):
                        raise ValueError("core_retirement_unverified")
                    idle = idle + 1 if rows[0]["is_processing"] is False else 0
                    await asyncio.sleep(0.05)
        LOGGER.info("voice_borrowed_core_quiescent")
