"""Own explicit audio/video source bytes and anonymous output until bounded isolated PCM normalization fully exits."""

import logging
import subprocess
import tempfile

from src.application.services.audio_contract import (
    ERRORS,
    MAX_OUTPUT,
    AudioError,
    audio_input,
    resolve_audio,
)
from src.application.services.vision_chat_policy import strict_json
from src.infrastructure.file_verifier import sandbox_command
from src.infrastructure.native_input import rewind_native_input
from src.infrastructure.sandbox_process import run_sandbox

logger = logging.getLogger(__name__)
WALL_SECONDS = 40


class NativeAudioNormalizer:
    """Normalize supported local explicit media to private PCM without microphone, user path, remote URL, ASR or persistence."""

    def normalize(self, raw):
        """Retain source/output descriptors and join all namespace work before accepting a complete source-clock-bound PCM reply."""
        source_sha = audio_input(raw)
        try:
            with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
                source.write(raw)
                source.flush()
                rewind_native_input(source)
                result = run_sandbox(
                    sandbox_command(
                        ["/venv/bin/python", "-m", "src.infrastructure.audio_worker"]
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
            raise AudioError("audio_processing_timeout") from None
        except OSError:
            raise AudioError("audio_processing_unavailable") from None
        if result.returncode:
            raise AudioError("audio_processing_unavailable")
        try:
            value = strict_json(data, MAX_OUTPUT)
        except Exception:
            raise AudioError("audio_invalid_result") from None
        if (
            type(value) is dict
            and set(value) == {"error"}
            and type(value["error"]) is str
            and value["error"] in ERRORS
        ):
            raise AudioError(value["error"])
        result = resolve_audio(value, source_sha)
        logger.info(
            "native_audio_normalization_complete samples=%d", result.sample_count
        )
        return result
