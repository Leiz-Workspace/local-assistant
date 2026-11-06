"""Serve one fixed Ngoc Huyen context validation with unchanged retained pronunciation and native generation."""

import contextlib
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

from benchmarks.scripts.vi_speech_prosody import ProsodyAdapter
from benchmarks.scripts.vi_speech_worker import configure_runtime
from benchmarks.scripts.vi_truc_ly_validation_worker import (
    ValidationAdapter,
    validate_entries,
)
from benchmarks.scripts.vi_voice_worker import emit, native_bytes, validate_message

LOGGER = logging.getLogger(__name__)
VOICE = "Ngọc Huyền"


class NgocHuyenAdapter(ValidationAdapter):
    """Reuse frozen chunk planning and reference audit while admitting only the existing Ngoc Huyen preset."""

    def infer(self, text, *, voice):
        """Admit one frozen rendered sentence and delegate every original chunk exactly once."""
        if voice != "Ngọc Huyền":
            raise ValueError("ngoc_validation_voice_only")
        self.current = next((r for r in self.rows if r["rendered_text"] == text), None)
        if self.current is None:
            raise ValueError("ngoc_validation_unapproved_text")
        self.plans = []
        self.binding = None
        result = ProsodyAdapter.infer(self, text, voice=voice)
        if self.binding is None or len(self.last_chunks) != len(
            self.current["phone_plans"]
        ):
            raise ValueError("ngoc_validation_actual_chunk_binding")
        self.last_trace.update(
            validation_case=self.current["id"],
            validation_plans=self.plans,
            voice_binding=self.binding,
            term_mode="us",
        )
        LOGGER.info(
            "ngoc_validation_request_complete case=%s chunks=%d",
            self.current["id"],
            len(self.plans),
        )
        return result


def validate_packet(packet):
    """Require the declared Ngoc Huyen voice and original ten-case semantic plan before loading weights."""
    rows = packet["rows"]
    if packet.get("voice") != VOICE or any(row.get("voice") != VOICE for row in rows):
        raise ValueError("ngoc_validation_packet_voice")
    validate_entries(rows)
    LOGGER.info("ngoc_validation_packet_verified cases=10")
    return rows


def admit(message, rows, seen):
    """Bind each first request to its fixed ID, text and actual voice before neural dispatch."""
    validate_message(message)
    if message["op"] == "close":
        return
    row = next((row for row in rows if row["id"] == message.get("id")), None)
    if (
        message["op"] != "synthesize"
        or row is None
        or message["id"] in seen
        or len(seen) >= 10
        or message.get("voice") != VOICE
        or message.get("text") != row["rendered_text"]
    ):
        raise ValueError("ngoc_validation_request_binding")
    LOGGER.info("ngoc_validation_request_admitted id=%s", message["id"])


def serve(expected_sha):
    """Load the retained runtime once and preserve complete first outcomes under the fixed packet and budget."""
    raw = Path("/approved-validation.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("ngoc_validation_packet_sha")
    rows = validate_packet(json.loads(raw))

    def factory(wrapper):
        """Attach the voice-specific boundary while reusing every retained synthesis dependency."""
        return NgocHuyenAdapter(wrapper, rows)

    with contextlib.redirect_stdout(sys.stderr):
        runtime = configure_runtime("clauses", adapter_factory=factory)
    emit(
        "ready",
        candidate="turbo",
        profile="ngoc-validation",
        voice=VOICE,
        packet_sha256=expected_sha,
        execution=runtime.execution,
    )
    seen = set()
    for _ in range(11):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("ngoc_validation_message_bound")
        message = json.loads(raw)
        admit(message, rows, seen)
        if message["op"] == "close":
            emit("closed", calls=len(seen))
            return
        seen.add(message["id"])
        started = time.perf_counter()
        with contextlib.redirect_stdout(sys.stderr):
            result = runtime.predict(message)
            result["prosody_trace"] = runtime.prosody_adapter.last_trace
            for index, chunk in enumerate(runtime.prosody_adapter.last_chunks):
                for suffix, content in zip(
                    ("f32", "wav"), native_bytes(chunk, 48000), strict=True
                ):
                    with (
                        Path("/output") / f"{message['id']}-chunk-{index}.{suffix}"
                    ).open("xb") as stream:
                        stream.write(content)
        emit(
            "result",
            id=message["id"],
            operation="synthesize",
            worker_wall_seconds=time.perf_counter() - started,
            **result,
        )
    raise ValueError("ngoc_validation_request_ceiling")


def main():
    """Accept only an explicit SHA-bound single offline campaign entry point."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if len(sys.argv) != 3 or sys.argv[1] != "--run":
        raise ValueError("ngoc_validation_mode")
    serve(sys.argv[2])


if __name__ == "__main__":
    main()
