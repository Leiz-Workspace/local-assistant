"""Expose model-free reading validation and a separately manifest-authorized fixed Truc Ly research worker."""

import contextlib
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

from benchmarks.scripts.vi_speech_prosody import preserving_chunks
from benchmarks.scripts.vi_speech_worker import configure_runtime
from benchmarks.scripts.vi_voice_worker import emit, native_bytes, validate_message
from benchmarks.scripts.vi_workflow_reading_policy import (
    MODEL,
    POLICY,
    VOICE,
    WorkflowReadingAdapter,
    check_text,
    plan_chunk,
)

LOGGER = logging.getLogger(__name__)


def manifest(value):
    """Refuse an unapproved scope, altered policy/model/preset or unbounded request count before loading weights."""
    if (
        type(value) is not dict
        or value.get("native_authorized") is not True
        or value.get("policy") != POLICY
        or value.get("model") != MODEL
        or value.get("voice") != VOICE
        or type(value.get("max_requests")) is not int
        or not 1 <= value["max_requests"] <= 24
        or type(value.get("scope_sha256")) is not str
        or len(value["scope_sha256"]) != 64
        or any(char not in "0123456789abcdef" for char in value["scope_sha256"])
    ):
        raise ValueError("workflow_reading_native_not_authorized")
    LOGGER.info(
        "workflow_reading_manifest_verified max_requests=%d", value["max_requests"]
    )
    return value


def inspect_rows(rows, dependencies, tokenizer):
    """Plan bounded public speech cases without model calls and retain refused cases instead of silently dropping them."""
    if (
        type(rows) is not list
        or not 1 <= len(rows) <= 24
        or len({row["id"] for row in rows}) != len(rows)
    ):
        raise ValueError("workflow_reading_probe_coverage")
    result = []
    for row in rows:
        observed = dict(
            id=row["id"],
            spoken_sha256=hashlib.sha256(row["speech_text"].encode()).hexdigest(),
        )
        try:
            check_text(row["speech_text"], 4096)
            chunks, gaps = preserving_chunks(
                row["speech_text"],
                dependencies["normalize"],
                dependencies["split"],
                dependencies["pack"],
                dependencies["classify"],
            )
            plans = [
                plan_chunk(
                    chunk,
                    dependencies["phonemize"](chunk, punc_norm=False),
                    dependencies["frame_cap"],
                )
                for chunk in chunks
            ]
            ids = [
                tokenizer.encode(plan["phones"], add_special_tokens=False).ids
                for plan in plans
            ]
            if any(tokenizer.token_to_id("<|unk|>") in group for group in ids) or any(
                tokenizer.decode(group, skip_special_tokens=False) != plan["phones"]
                for group, plan in zip(ids, plans, strict=True)
            ):
                raise ValueError("workflow_reading_token_roundtrip")
            observed.update(
                status="PLANNED",
                chunks=chunks,
                gaps=gaps,
                plans=plans,
                unknown_tokens=0,
            )
        except ValueError as error:
            observed.update(status="REFUSED", code=str(error))
        result.append(observed)
    LOGGER.info("workflow_reading_probe_planned cases=%d", len(result))
    return result


def probe():
    """Load only the original SDK dictionary/tokenizer and export real normalization and phone plans."""
    from sea_g2p import G2P, Normalizer
    from tokenizers import Tokenizer
    from vieneu_utils.core_utils import (
        _classify_gap,
        max_expected_frames,
        pack_sentences_into_chunks,
        split_into_sentences,
    )

    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError("workflow_reading_probe_bound")
    deps = dict(
        normalize=Normalizer(lang="vi").normalize,
        phonemize=G2P(lang="vi").convert,
        split=split_into_sentences,
        pack=pack_sentences_into_chunks,
        classify=_classify_gap,
        frame_cap=max_expected_frames,
    )
    rows = inspect_rows(
        json.loads(raw), deps, Tokenizer.from_file("/approved-tokenizer.json")
    )
    with Path("/output/frontend.json").open("x") as stream:
        json.dump(
            dict(
                description="Model-free accepted-reading workflow plans; refusals retained without neural dispatch.",
                reading_policy=POLICY,
                rows=rows,
                model_calls=0,
            ),
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")


def serve(expected_sha):
    """Load only after an exact approved manifest and serve bounded fixed-preset first attempts without retry."""
    raw = Path("/approved-workflow.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("workflow_reading_manifest_sha")
    scope = manifest(json.loads(raw))
    with contextlib.redirect_stdout(sys.stderr):
        runtime = configure_runtime("clauses", adapter_factory=WorkflowReadingAdapter)
    emit(
        "ready",
        candidate="turbo",
        profile="workflow-reading",
        reading_policy=POLICY,
        voice=VOICE,
        manifest_sha256=expected_sha,
        execution=runtime.execution,
    )
    seen = set()
    for _ in range(scope["max_requests"] + 1):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("workflow_reading_message_bound")
        message = json.loads(raw)
        validate_message(message)
        if message["op"] == "close":
            emit("closed", calls=len(seen))
            return
        if (
            message["op"] != "synthesize"
            or message.get("voice") != VOICE
            or message["id"] in seen
            or len(seen) >= scope["max_requests"]
        ):
            raise ValueError("workflow_reading_request_scope")
        check_text(message["text"], 4096)
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
    raise ValueError("workflow_reading_request_ceiling")


def main():
    """Keep model-free inspection separate from a separately scope-authorized native entry point."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if sys.argv[1:] == ["--probe"]:
        probe()
    elif len(sys.argv) == 3 and sys.argv[1] == "--approved-manifest":
        serve(sys.argv[2])
    else:
        raise ValueError("workflow_reading_mode")


if __name__ == "__main__":
    main()
