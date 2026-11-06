"""Test only API stress marks through the unchanged clause adapter in a sealed offline worker."""

import contextlib
import json
import logging
import os
import sys
import time
from pathlib import Path

from benchmarks.scripts.vi_speech_prosody import ProsodyAdapter, preserving_chunks
from benchmarks.scripts.vi_speech_worker import configure_runtime
from benchmarks.scripts.vi_voice_worker import emit, native_bytes, validate_message

LOGGER = logging.getLogger(__name__)
SOURCE = "ˈeɪ pˈiː ˈaɪ"
TARGET = "ˌeɪ pˌiː ˈaɪ"


def replace_api(phonemes):
    """Change at most one exact acronym stress pattern without modifying any other phoneme."""
    count = phonemes.count(SOURCE)
    if count > 1 or TARGET in phonemes:
        raise ValueError("api_stress_ambiguous_or_already_changed")
    changed = phonemes.replace(SOURCE, TARGET, 1)
    if len(changed) != len(phonemes):
        raise ValueError("api_stress_length_changed")
    LOGGER.info("api_stress_span_checked replacements=%d", count)
    return changed, count


class ApiStressAdapter(ProsodyAdapter):
    """Inject only an audited phonemizer dependency into the retained original clause adapter."""

    def __init__(self, wrapper, dependencies=None):
        """Retain every original dependency except the explicit acronym stress wrapper."""
        super().__init__(wrapper, dependencies)
        self.dependencies = dict(self.dependencies)
        self.original_phonemizer = self.dependencies["phonemize"]
        self.dependencies["phonemize"] = self.phonemize
        self.api_trace = []

    def phonemize(self, text, punc_norm):
        """Record exact original and candidate phones and reject any frame-cap drift."""
        before = self.original_phonemizer(text, punc_norm=punc_norm)
        after, count = replace_api(before)
        original_cap = self.dependencies["frame_cap"](before)
        if self.dependencies["frame_cap"](after) != original_cap:
            raise ValueError("api_stress_frame_cap_changed")
        self.api_trace.append(
            dict(before=before, after=after, replacements=count, frame_cap=original_cap)
        )
        return after

    def infer(self, text, *, voice):
        """Delegate unchanged chunking, references, decoding and joining, requiring one API edit."""
        self.api_trace = []
        result = super().infer(text, voice=voice)
        if sum(row["replacements"] for row in self.api_trace) != 1:
            raise ValueError("api_stress_exact_one_required")
        self.last_trace["api_stress"] = list(self.api_trace)
        LOGGER.info("api_stress_request_complete chunks=%d", len(self.api_trace))
        return result


def probe():
    """Verify the exact two rendered sentences with existing SDK/tokenizer and no neural weights."""
    from sea_g2p import G2P, Normalizer
    from tokenizers import Tokenizer
    from vieneu_utils.core_utils import (
        _classify_gap,
        max_expected_frames,
        pack_sentences_into_chunks,
        split_into_sentences,
        syllable_count,
    )

    request = sys.stdin.buffer.read(16385)
    texts = json.loads(request)
    if len(request) > 16384 or type(texts) is not list or len(texts) != 2:
        raise ValueError("api_stress_probe_bound")
    normalizer, g2p = Normalizer(lang="vi"), G2P(lang="vi")
    tokenizer = Tokenizer.from_file("/approved-tokenizer.json")
    if g2p.convert("API.", punc_norm=False) != "ˌeɪpˌiːˈaɪ.":
        raise ValueError("api_stress_native_dictionary_changed")
    rows = []
    for text in texts:
        chunks, gaps = preserving_chunks(
            text,
            normalizer.normalize,
            split_into_sentences,
            pack_sentences_into_chunks,
            _classify_gap,
        )
        traces = []
        for chunk in chunks:
            before = g2p.convert(chunk, punc_norm=False)
            after, count = replace_api(before)
            ids = [
                tokenizer.encode(ph, add_special_tokens=False).ids
                for ph in (before, after)
            ]
            if any(tokenizer.token_to_id("<|unk|>") in group for group in ids):
                raise ValueError("api_stress_unknown_token")
            if any(
                tokenizer.decode(group, skip_special_tokens=False) != ph
                for group, ph in zip(ids, (before, after), strict=True)
            ):
                raise ValueError("api_stress_roundtrip")
            if syllable_count(before) != syllable_count(after) or max_expected_frames(
                before
            ) != max_expected_frames(after):
                raise ValueError("api_stress_original_duration_bounds_changed")
            traces.append(
                dict(
                    before=before,
                    after=after,
                    replacements=count,
                    frame_cap=max_expected_frames(before),
                )
            )
        if sum(row["replacements"] for row in traces) != 1:
            raise ValueError("api_stress_probe_exact_one")
        rows.append(dict(speech_text=text, chunks=chunks, gaps=gaps, api_stress=traces))
    with Path("/output/frontend.json").open("x") as stream:
        json.dump(
            dict(
                description="Same-sentence API stress probe, no neural inference.",
                rows=rows,
                model_calls=0,
            ),
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")
    LOGGER.info("api_stress_probe_complete rows=2 model_calls=0")


def serve():
    """Serve four first attempts with original clause runtime and genuine native chunk export."""
    with contextlib.redirect_stdout(sys.stderr):
        runtime = configure_runtime("clauses", adapter_factory=ApiStressAdapter)
    emit("ready", candidate="turbo", profile="api-stress", execution=runtime.execution)
    seen = set()
    for _ in range(5):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("api_stress_message_bound")
        message = json.loads(raw)
        validate_message(message)
        if message["op"] == "close":
            emit("closed", calls=len(seen))
            return
        if message["op"] != "synthesize" or message["id"] in seen or len(seen) >= 4:
            raise ValueError("api_stress_request_bound")
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
    raise ValueError("api_stress_request_ceiling")


def main():
    """Run a model-free probe or the explicitly selected same-text stress experiment."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if sys.argv[1:] == ["--probe"]:
        probe()
    elif sys.argv[1:] == ["api-stress"]:
        serve()
    else:
        raise ValueError("api_stress_mode")


if __name__ == "__main__":
    main()
