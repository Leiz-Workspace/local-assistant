"""Compare preset reference conditioning on fixed English phonemes without changing weights or speaker anchors."""

import argparse
import contextlib
import hashlib
import json
import logging
import os
import sys
import time

from benchmarks.scripts.vi_voice_worker import Runtime, emit, validate_message

LOGGER = logging.getLogger(__name__)
MODES = {"with_reference": True, "without_reference": False}


class ReferenceAdapter:
    """Change only reference-code admission while preserving the exact speaker embedding and original decoding controls."""

    def __init__(self, wrapper, mode, frame_cap=None, repetition_window=None):
        """Bind a fixed declared ablation and retain the original loaded CPU wrapper."""
        if mode not in MODES:
            raise ValueError("reference_mode")
        if frame_cap is None:
            from vieneu_utils.core_utils import max_expected_frames
            from vieneu._v3_turbo_engine.rep_history import DEFAULT_REP_WINDOW

            frame_cap, repetition_window = max_expected_frames, DEFAULT_REP_WINDOW
        self.wrapper, self.mode, self.frame_cap, self.window = (
            wrapper,
            mode,
            frame_cap,
            repetition_window,
        )
        self.last_trace = None
        LOGGER.info("reference_adapter_bound mode=%s", mode)

    def infer(self, phonemes, *, voice):
        """Audit exact prompt tokens/anchor before one original first-attempt engine call, with no audio repair."""
        if (
            voice not in {"Trúc Ly", "Ngọc Huyền"}
            or type(phonemes) is not str
            or not phonemes.strip()
            or len(phonemes.encode()) > 1024
        ):
            raise ValueError("reference_input")
        use_reference = MODES[self.mode]
        speaker, codes = self.wrapper._resolve_ref(voice, None, True, use_reference)
        if use_reference != (codes is not None):
            raise ValueError("reference_resolver_binding")
        engine = self.wrapper.engine
        encoding = engine.tokenizer.encode(phonemes, add_special_tokens=False)
        ids = encoding.ids
        decoded = engine.tokenizer.decode(ids, skip_special_tokens=False)
        unknown = engine.tokenizer.token_to_id("<|unk|>")
        if unknown in ids or decoded != phonemes:
            raise ValueError("reference_token_roundtrip")
        style = engine._resolve_style_id()
        prompt = engine._build_rows(phonemes, codes, style)
        expected = [style, engine.tps] + ids + [engine.tpe]
        if prompt[:, 0].tolist()[: len(expected)] != expected:
            raise ValueError("reference_prompt_text_ids")
        if not use_reference and len(prompt) != len(expected):
            raise ValueError("reference_unexpected_audio_rows")
        if use_reference and len(prompt) <= len(expected):
            raise ValueError("reference_missing_audio_rows")
        anchor = engine._speaker_anchor(speaker)
        self.last_trace = dict(
            mode=self.mode,
            voice=voice,
            phonemes=phonemes,
            token_ids=ids,
            decoded_exact=True,
            unknown_tokens=0,
            speaker_embedding_sha256=hashlib.sha256(speaker.tobytes()).hexdigest(),
            projected_anchor_sha256=hashlib.sha256(anchor.tobytes()).hexdigest(),
            prompt_text_ids=expected,
            prompt_rows=len(prompt),
            reference_rows=len(prompt) - len(expected),
            prompt_sha256=hashlib.sha256(prompt.tobytes()).hexdigest(),
            use_ref_codes=use_reference,
            extra_neural_forwards=0,
            generation_attempts=1,
        )
        wav = engine.infer(
            phonemes=phonemes,
            speaker_emb=speaker,
            ref_codes=codes,
            use_ref_codes=use_reference,
            temperature=0.8,
            top_k=25,
            top_p=0.95,
            max_new_frames=min(300, self.frame_cap(phonemes)),
            repetition_penalty=1.2,
            repetition_window=self.window,
        )
        LOGGER.info("reference_synthesis_returned mode=%s voice=%s", self.mode, voice)
        return self.wrapper._apply_watermark(wav)


def serve(mode):
    """Serve at most eight controlled requests in one sealed original CPU runtime without retries."""
    with contextlib.redirect_stdout(sys.stderr):
        runtime = Runtime("turbo")
        adapter = ReferenceAdapter(runtime.engine, mode)
        runtime.engine.infer = adapter.infer
    emit(
        "ready",
        candidate="turbo",
        mode=mode,
        import_seconds=runtime.import_seconds,
        load_seconds=runtime.load_seconds,
        execution=dict(
            runtime.execution,
            reference_mode=mode,
            direct_phoneme_control=True,
            original_text_normalization=False,
        ),
    )
    seen = set()
    for _ in range(9):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("reference_message_bound")
        message = json.loads(raw)
        validate_message(message)
        if message["op"] == "close":
            emit("closed", calls=len(seen))
            return
        if message["op"] != "synthesize" or message["id"] in seen or len(seen) >= 8:
            raise ValueError("reference_operation_duplicate_or_ceiling")
        seen.add(message["id"])
        started = time.perf_counter()
        with contextlib.redirect_stdout(sys.stderr):
            result = runtime.predict(message)
        emit(
            "result",
            id=message["id"],
            operation="synthesize",
            worker_wall_seconds=time.perf_counter() - started,
            reference_trace=adapter.last_trace,
            **result,
        )
    raise ValueError("reference_call_ceiling")


def main():
    """Select one explicit reference condition without exposing model, voice or generation overrides."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    serve(args.mode)


if __name__ == "__main__":
    main()
