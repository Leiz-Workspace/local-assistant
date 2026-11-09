"""Own explicit video bytes and anonymous output until isolated FFmpeg frame sampling fully exits or times out."""

import json
import logging
import subprocess
import tempfile

from src.application.services.video_contract import (
    ERRORS,
    MAX_OUTPUT,
    VideoError,
    resolve_video,
    video_input,
)
from src.application.services.vision_chat_policy import strict_json
from src.infrastructure.file_verifier import sandbox_command
from src.infrastructure.native_input import rewind_native_input
from src.infrastructure.sandbox_process import run_sandbox

logger = logging.getLogger(__name__)
WALL_SECONDS = 40


class NativeVideoSampler:
    """Provide a synchronous local explicit-byte video capability without file lookup, URLs, model inference or persistence."""

    def sample(self, raw, targets=(0,)):
        """Keep all descriptors private and join the namespace before validating a complete timestamped frame response."""
        source_sha = video_input(raw, targets)
        try:
            with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
                source.write(raw)
                source.flush()
                rewind_native_input(source)
                result = run_sandbox(
                    sandbox_command(
                        [
                            "/venv/bin/python",
                            "-m",
                            "src.infrastructure.video_worker",
                            json.dumps(targets),
                        ]
                    ),
                    stdin=source,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    timeout=WALL_SECONDS,
                    env={},
                    close_fds=True,
                    start_new_session=True,
                )
                output.seek(0)
                data = output.read(MAX_OUTPUT + 1)
        except subprocess.TimeoutExpired:
            raise VideoError("video_processing_timeout") from None
        except OSError:
            raise VideoError("video_processing_unavailable") from None
        if result.returncode:
            raise VideoError("video_processing_unavailable")
        try:
            value = strict_json(data, MAX_OUTPUT)
        except Exception:
            raise VideoError("video_invalid_result") from None
        if (
            type(value) is dict
            and set(value) == {"error"}
            and type(value["error"]) is str
            and value["error"] in ERRORS
        ):
            raise VideoError(value["error"])
        answer = resolve_video(value, source_sha, targets)
        logger.info("native_video_sampling_complete frames=%d", len(answer.frames))
        return answer
