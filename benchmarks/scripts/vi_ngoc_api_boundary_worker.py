"""Test only native-dictionary API grouping for one retained Ngoc Huyen sentence in an offline worker."""

import contextlib
import copy
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

from benchmarks.scripts.vi_ngoc_huyen_validation_worker import (
    NgocHuyenAdapter,
    VOICE,
    admit,
    validate_packet,
)
from benchmarks.scripts.vi_speech_worker import configure_runtime
from benchmarks.scripts.vi_truc_ly_validation_worker import chunk_plan
from benchmarks.scripts.vi_voice_worker import emit, native_bytes

LOGGER = logging.getLogger(__name__)
SELECTED = "mixed-api"
SOURCE = "ˌeɪ pˌiː ˈaɪ"
TARGET = "ˌeɪpˌiːˈaɪ"


def compact_plan(original, frame_cap):
    """Remove only two internal API spaces and require an unchanged matched retained frame allowance."""
    before = original["us"]
    if before.count(SOURCE) != 1 or TARGET in before:
        raise ValueError("api_boundary_exact_span")
    after = before.replace(SOURCE, TARGET, 1)
    cap = min(300, frame_cap(after))
    if min(cap, original["shared_cap"]) != original["shared_cap"]:
        raise ValueError("api_boundary_retained_cap_mismatch")
    result = dict(
        copy.deepcopy(original),
        us=after,
        us_original_cap=cap,
        api_boundary=dict(
            before=before,
            after=after,
            removed_internal_spaces=2,
            retained_shared_cap=original["shared_cap"],
        ),
    )
    LOGGER.info(
        "api_boundary_plan_created removed_spaces=2 shared_cap=%d", result["shared_cap"]
    )
    return result


class BoundaryAdapter(NgocHuyenAdapter):
    """Restrict synthesis to one exact sentence and reuse all original voice/sampling/chunk/join behavior."""

    def infer(self, text, *, voice):
        """Reject every other frozen metadata row before it could become a synthesis request."""
        selected = next(row for row in self.rows if row["id"] == SELECTED)
        if text != selected["rendered_text"]:
            raise ValueError("api_boundary_selected_text_only")
        return super().infer(text, voice=voice)

    def phonemize(self, text, punc_norm):
        """Build the genuine original plan and exact compact candidate before its only generation call."""
        if self.current is None or self.current["id"] != SELECTED or self.plans:
            raise ValueError("api_boundary_one_chunk_only")
        if len(self.current["chunks"]) != 1 or text != self.current["chunks"][0]:
            raise ValueError("api_boundary_chunk_binding")
        raw = self.original["phonemize"](text, punc_norm=punc_norm)
        original = chunk_plan(text, raw, self.original["frame_cap"])
        planned = compact_plan(original, self.original["frame_cap"])
        if planned != self.current["phone_plans"][0]:
            raise ValueError("api_boundary_actual_plan_drift")
        self.plans.append(planned)
        return planned["us"]


def admit_boundary(message, rows, seen):
    """Admit only the declared first API request or explicit close, never the other metadata rows."""
    admit(message, rows, seen)
    if message["op"] != "close" and (message["id"] != SELECTED or seen):
        raise ValueError("api_boundary_one_request_only")
    LOGGER.info("api_boundary_admission_checked op=%s", message["op"])


def probe():
    """Check real pinned dictionary, conservative caps and both token roundtrips without exposing weights."""
    from sea_g2p import G2P
    from tokenizers import Tokenizer
    from vieneu_utils.core_utils import max_expected_frames

    raw = sys.stdin.buffer.read(16385)
    row = json.loads(raw)
    if len(raw) > 16384 or row["id"] != SELECTED or len(row["chunks"]) != 1:
        raise ValueError("api_boundary_probe_input")
    g2p = G2P(lang="vi")
    dictionary = g2p.convert("API.", punc_norm=False)
    if dictionary != TARGET + ".":
        raise ValueError("api_boundary_native_dictionary_changed")
    original = chunk_plan(
        row["chunks"][0],
        g2p.convert(row["chunks"][0], punc_norm=False),
        max_expected_frames,
    )
    if original != row["phone_plans"][0]:
        raise ValueError("api_boundary_retained_frontend_drift")
    planned = compact_plan(original, max_expected_frames)
    tokenizer = Tokenizer.from_file("/approved-tokenizer.json")
    ids = [
        tokenizer.encode(ph, add_special_tokens=False).ids
        for ph in (original["us"], planned["us"])
    ]
    if any(tokenizer.token_to_id("<|unk|>") in tokens for tokens in ids):
        raise ValueError("api_boundary_unknown_token")
    if any(
        tokenizer.decode(tokens, skip_special_tokens=False) != ph
        for tokens, ph in zip(ids, (original["us"], planned["us"]), strict=True)
    ):
        raise ValueError("api_boundary_token_roundtrip")
    with Path("/output/frontend.json").open("x") as stream:
        json.dump(
            dict(
                description="Original dictionary API compact form and one same-context candidate checked without model calls.",
                selected_id=SELECTED,
                original_row=row,
                native_dictionary=dictionary,
                candidate_plan=planned,
                token_ids=ids,
                unknown_tokens=0,
                model_calls=0,
            ),
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")
    LOGGER.info("api_boundary_probe_complete model_calls=0")


def serve(expected_sha):
    """Load the retained runtime once and preserve complete first outcomes under the fixed packet and budget."""
    raw = Path("/approved-validation.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("api_boundary_packet_sha")
    packet = json.loads(raw)
    rows = validate_packet(packet)
    if packet.get("selected_id") != SELECTED:
        raise ValueError("api_boundary_selected_packet")

    def factory(wrapper):
        """Attach the voice-specific boundary while reusing every retained synthesis dependency."""
        return BoundaryAdapter(wrapper, rows)

    with contextlib.redirect_stdout(sys.stderr):
        runtime = configure_runtime("clauses", adapter_factory=factory)
    emit(
        "ready",
        candidate="turbo",
        profile="ngoc-api-boundary",
        voice=VOICE,
        packet_sha256=expected_sha,
        execution=runtime.execution,
    )
    seen = set()
    for _ in range(2):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("api_boundary_message_bound")
        message = json.loads(raw)
        admit_boundary(message, rows, seen)
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
    raise ValueError("api_boundary_request_ceiling")


def main():
    """Run only an explicit no-weights probe or one SHA-bound candidate worker."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if sys.argv[1:] == ["--probe"]:
        probe()
    elif len(sys.argv) == 3 and sys.argv[1] == "--run":
        serve(sys.argv[2])
    else:
        raise ValueError("api_boundary_mode")


if __name__ == "__main__":
    main()
