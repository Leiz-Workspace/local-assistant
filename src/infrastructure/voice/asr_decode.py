"""Run one qualified official CPU ASR backend on sealed reference-free waveforms inside an offline readonly evaluation namespace."""

import hashlib
import logging
import os
import stat
import time
from pathlib import Path

logger = logging.getLogger(__name__)
CANDIDATES = {"qwen3-asr-0.6b", "whisper-small-ct2"}


def load_waveform(case, root=Path("/samples")):
    """Read exact bounded finite float32 bytes, rejecting symlinks and digest/count drift before a model receives them."""
    import numpy as np

    path = root / case["filename"]
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("asr_waveform_type")
        raw = stream.read(320000 * 4 + 1)
    if (
        len(raw) != case["sample_count"] * 4
        or hashlib.sha256(raw).hexdigest() != case["waveform_sha256"]
    ):
        raise ValueError("asr_waveform_integrity")
    waveform = np.frombuffer(raw, dtype="<f4").copy()
    if not np.isfinite(waveform).all() or float(np.abs(waveform).max()) > 1:
        raise ValueError("asr_waveform_range")
    logger.info("asr_worker_waveform_verified samples=%d", len(waveform))
    return waveform


def qwen_prompt(processor, language):
    """Use the official empty-context audio chat template and forced-language suffix without references, extra instructions or transcript repair."""
    messages = [
        dict(role="system", content=""),
        dict(role="user", content=[dict(type="audio", audio="")]),
    ]
    return (
        processor.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False
        )
        + f"language {language}<asr_text>"
    )


class Runtime:
    """Import and load exactly one official candidate backend with explicit CPU/thread/precision/generation controls."""

    def transcribe(self, waveform, language):
        """Materialize the entire bounded inference output, retain raw decoding and identify potential generation-limit exhaustion."""
        started = time.perf_counter()
        if self.candidate == "qwen3-asr-0.6b":
            name = {"vi_vn": "Vietnamese", "en_us": "English"}[language]
            with self.torch.inference_mode():
                inputs = self.processor(
                    text=[qwen_prompt(self.processor, name)],
                    audio=[waveform],
                    return_tensors="pt",
                    padding=True,
                )
                inputs = inputs.to(self.model.device).to(self.model.dtype)
                generated = self.model.generate(
                    **inputs, max_new_tokens=256, do_sample=False
                )
                tokens = generated.sequences[:, inputs["input_ids"].shape[1] :]
                text = self.processor.batch_decode(
                    tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False
                )[0]
                token_count = int(tokens.shape[1])
                eos = self.model.generation_config.eos_token_id
                eos = [eos] if isinstance(eos, int) else eos
                capped = token_count >= 256 and int(tokens[0, -1]) not in (eos or [])
                extra = dict(
                    generated_tokens=token_count,
                    output_cap_reached=capped,
                    text_postprocessing="raw_decode_no_repetition_repair",
                )
        else:
            iterator, info = self.model.transcribe(
                waveform,
                language={"vi_vn": "vi", "en_us": "en"}[language],
                beam_size=5,
                temperature=0.0,
                condition_on_previous_text=False,
                initial_prompt=None,
                vad_filter=False,
                word_timestamps=False,
                without_timestamps=True,
                max_new_tokens=256,
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,
                compression_ratio_threshold=2.4,
            )
            segments = list(iterator)
            text = "".join((part.text for part in segments))
            counts = [len(part.tokens) for part in segments]
            extra = dict(
                segment_token_counts=counts,
                output_cap_reached=any((count >= 256 for count in counts)),
                duration_seconds=info.duration,
                duration_after_vad_seconds=info.duration_after_vad,
                text_postprocessing="raw_materialized_segments_no_host_repair",
            )
        if type(text) is not str or len(text) > 8192:
            raise ValueError("asr_output_bound")
        return dict(text=text, wall_seconds=time.perf_counter() - started, **extra)
