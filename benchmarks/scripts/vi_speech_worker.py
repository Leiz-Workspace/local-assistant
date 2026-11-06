"""Probe pinned Vietnamese normalization or synthesize explicitly labelled speech-text variants offline."""

import argparse
import contextlib
import functools
import json
import logging
import os
import sys
import time
from pathlib import Path

from benchmarks.scripts.vi_speech_text import render_speech
from benchmarks.scripts.vi_speech_prosody import ProsodyAdapter, preserving_chunks
from benchmarks.scripts.vi_voice_worker import Runtime, emit, validate_message

LOGGER = logging.getLogger(__name__)
PROFILES = {"raw": 256, "reading": 256, "clauses": 256}


def probe_rows(
    texts, normalizer, chunker, phonemizer, clause_chunker=None, clause_phonemizer=None
):
    """Expose normalizer, chunk boundaries and phonemes without constructing or loading any neural runtime."""
    if type(texts) is not list or not 1 <= len(texts) <= 16:
        raise ValueError("probe_text_count")
    rows = []
    for index, text in enumerate(texts):
        if type(text) is not str or len(text.encode()) > 512:
            raise ValueError("probe_text_bound")
        for profile, limit in PROFILES.items():
            rendered = render_speech(text, profile)
            selected_chunker = (
                clause_chunker
                if profile == "clauses" and clause_chunker is not None
                else chunker
            )
            selected_phonemizer = (
                clause_phonemizer
                if profile == "clauses" and clause_phonemizer is not None
                else phonemizer
            )
            chunks, gaps = selected_chunker(rendered.speech_text, max_chars=limit)
            rows.append(
                dict(
                    index=index,
                    profile=profile,
                    source=text,
                    speech_text=rendered.speech_text,
                    normalized=normalizer.normalize(
                        rendered.speech_text, punc_norm=False
                    ),
                    chunks=chunks,
                    gaps=gaps,
                    phonemes=[selected_phonemizer(chunk) for chunk in chunks],
                    max_chars=limit,
                )
            )
    LOGGER.info("non_neural_normalization_probed rows=%d", len(rows))
    return rows


def probe():
    """Read one public packet and save a model-free diagnostic in the sole writable output directory."""
    from sea_g2p import Normalizer, G2P
    from vieneu_utils.core_utils import (
        split_into_sentences,
        pack_sentences_into_chunks,
        _classify_gap,
    )
    from vieneu_utils.phonemize_text import (
        normalize_to_chunks_v3_with_gaps,
        phonemize_text_with_emotions,
    )

    raw = sys.stdin.buffer.read(32769)
    if len(raw) > 32768:
        raise ValueError("probe_request_bound")
    normalizer, g2p = Normalizer(lang="vi"), G2P(lang="vi")

    def clause_chunker(text, max_chars):
        """Use the same punctuation-preserving research chunker as the native profile."""
        return preserving_chunks(
            text,
            normalizer.normalize,
            split_into_sentences,
            pack_sentences_into_chunks,
            _classify_gap,
            max_chars,
        )

    def clause_phonemizer(text):
        """Preserve question punctuation in the same original G2P used for generation."""
        return g2p.convert(text, punc_norm=False)

    rows = probe_rows(
        json.loads(raw),
        normalizer,
        normalize_to_chunks_v3_with_gaps,
        phonemize_text_with_emotions,
        clause_chunker,
        clause_phonemizer,
    )
    path = Path("/output/normalizer-probe.json")
    with path.open("x") as stream:
        json.dump(
            dict(
                description="Pinned SDK normalization/phoneme diagnostic only; no model mounts, loads or inference.",
                rows=rows,
                model_calls=0,
            ),
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")
    emit("probe_complete", rows=len(rows), model_calls=0)


def configure_runtime(profile, factory=Runtime, adapter_factory=ProsodyAdapter):
    """Bind existing weights to the original path or the explicit question-preserving phoneme adapter."""
    if profile not in PROFILES:
        raise ValueError("quality_profile")
    runtime = factory("turbo")
    runtime.prosody_adapter = None
    if profile == "clauses":
        runtime.prosody_adapter = adapter_factory(runtime.engine)
        runtime.engine.infer = runtime.prosody_adapter.infer
    else:
        runtime.engine.infer = functools.partial(
            runtime.engine.infer, max_chars=PROFILES[profile]
        )
    runtime.execution = dict(
        runtime.execution,
        research_profile=profile,
        max_chars=PROFILES[profile],
        product_response_unchanged=True,
        original_text_normalization=profile != "clauses",
        sampling_unchanged=True,
        speed_or_style_override=False,
        question_preserving_phoneme_api=profile == "clauses",
        chunk_policy="one_sentence_no_word_split"
        if profile == "clauses"
        else "original_packing",
    )
    LOGGER.info(
        "quality_runtime_configured profile=%s max_chars=%d", profile, PROFILES[profile]
    )
    return runtime


def serve(profile):
    """Admit bounded first-attempt requests to one fixed experimental profile without caching or retries."""
    with contextlib.redirect_stdout(sys.stderr):
        runtime = configure_runtime(profile)
    emit(
        "ready",
        candidate="turbo",
        profile=profile,
        import_seconds=runtime.import_seconds,
        load_seconds=runtime.load_seconds,
        execution=runtime.execution,
    )
    seen = set()
    for _ in range(17):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("quality_request_bound_or_eof")
        message = json.loads(raw)
        validate_message(message)
        if message["op"] == "close":
            emit("closed", calls=len(seen))
            return
        if message["op"] != "synthesize" or message["id"] in seen or len(seen) >= 16:
            raise ValueError("quality_operation_duplicate_or_ceiling")
        seen.add(message["id"])
        started = time.perf_counter()
        with contextlib.redirect_stdout(sys.stderr):
            result = runtime.predict(message)
            if runtime.prosody_adapter is not None:
                result["prosody_trace"] = runtime.prosody_adapter.last_trace
                from benchmarks.scripts.vi_voice_worker import native_bytes

                for index, chunk in enumerate(runtime.prosody_adapter.last_chunks):
                    raw_chunk, wav_chunk = native_bytes(chunk, 48000)
                    for suffix, content in [("f32", raw_chunk), ("wav", wav_chunk)]:
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
    raise ValueError("quality_call_ceiling")


def main():
    """Run one sealed model-free probe or one explicitly selected CPU profile with audit logs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if args.probe:
        probe()
    else:
        serve(args.profile)


if __name__ == "__main__":
    main()
