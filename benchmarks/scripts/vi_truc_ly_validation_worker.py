"""Validate new Truc Ly contexts with the frozen accepted term/API policy and original clause runtime."""

import contextlib
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

from benchmarks.scripts.vi_api_stress_worker import SOURCE as API_SOURCE
from benchmarks.scripts.vi_speech_prosody import ProsodyAdapter, preserving_chunks
from benchmarks.scripts.vi_speech_worker import configure_runtime
from benchmarks.scripts.vi_us_terms_worker import TERMS, TermsAdapter, phone_plan
from benchmarks.scripts.vi_voice_worker import emit, native_bytes, validate_message

LOGGER = logging.getLogger(__name__)


def chunk_plan(text, raw, cap):
    """Apply only the frozen term edits and API rule to one original normalized chunk."""
    api = text.count("<en>a p i</en>")
    if api > 1 or raw.count(API_SOURCE) != api:
        raise ValueError("truc_validation_api_marker_binding")
    wanted = []
    counts = {}
    for term, (before, after) in TERMS.items():
        count = raw.count(before) + raw.count(after)
        if count > 1:
            raise ValueError("truc_validation_ambiguous_term")
        counts[term] = count
        if before in raw:
            wanted.append(term)
    # The old planner uses this metadata only to assert API presence; it is never spoken.
    metadata = dict(
        id="validation-chunk", text="API" if api else "", terms=wanted, controls=[]
    )
    plan = phone_plan(raw, metadata, cap)
    plan.update(lexical_counts=counts, normalized_chunk=text)
    LOGGER.info(
        "truc_validation_chunk_planned edits=%d api=%d", len(plan["edits"]), api
    )
    return plan


def validate_entries(rows):
    """Check fixed semantics, lexical counts, I/English references and conservative caps before model loading."""
    if len(rows) != 10 or len({row["id"] for row in rows}) != 10:
        raise ValueError("truc_validation_case_coverage")
    for row in rows:
        plans = row["phone_plans"]
        if (
            row["unknown_tokens"]
            or not 1 <= len(plans) <= 8
            or len(row["chunks"]) != len(plans)
            or len(row["gaps"]) != len(plans) - 1
        ):
            raise ValueError("truc_validation_chunk_or_token_coverage")
        actual = {term: sum(p["lexical_counts"][term] for p in plans) for term in TERMS}
        if (
            any(actual[term] != row["expected_terms"].get(term, 0) for term in TERMS)
            or sum(p["api_replacements"] for p in plans) != row["expected_api"]
        ):
            raise ValueError("truc_validation_declared_term_counts")
        normalized = " ".join(row["chunks"]).lower()
        if any(piece not in normalized for piece in row["required_pieces"]):
            raise ValueError("truc_validation_spoken_semantics")
        phones = " ".join(p["us"] for p in plans)
        simple = phones.replace("ˈ", "").replace("ˌ", "")
        if row["initial_i"] and simple.split()[0] != "aɪ":
            raise ValueError("truc_validation_initial_I")
        if row["question"] and (
            not row["chunks"][-1].endswith("?") or not plans[-1]["us"].endswith("?")
        ):
            raise ValueError("truc_validation_question_lost")
        if set(row["reference_phones"]) != set(row["references"]) or any(
            ph.replace("ˈ", "").replace("ˌ", "") not in simple
            for ph in row["reference_phones"].values()
        ):
            raise ValueError("truc_validation_english_reference_missing")
        for index, plan in enumerate(plans):
            if plan["normalized_chunk"] != row["chunks"][index] or not 1 <= plan[
                "shared_cap"
            ] <= min(plan["baseline_original_cap"], plan["us_original_cap"], 300):
                raise ValueError("truc_validation_original_cap_or_order")
    if sum(len(r["phone_plans"]) for r in rows) > 16:
        raise ValueError("truc_validation_inner_chunk_ceiling")
    LOGGER.info(
        "truc_validation_frontend_verified cases=10 chunks=%d",
        sum(len(r["phone_plans"]) for r in rows),
    )


class ValidationAdapter(TermsAdapter):
    """Extend the retained term policy to a read-only frozen multi-clause packet, only for Truc Ly."""

    def __init__(self, wrapper, rows, dependencies=None):
        """Reuse original speaker/reference audit and all underlying generation dependencies."""
        super().__init__(wrapper, "us", dependencies)
        validate_entries(rows)
        self.rows = rows
        self.current = None
        self.plans = []

    def phonemize(self, text, punc_norm):
        """Reject any plan drift against the frozen probe before the first affected chunk is synthesized."""
        index = len(self.plans)
        if (
            self.current is None
            or index >= len(self.current["chunks"])
            or text != self.current["chunks"][index]
        ):
            raise ValueError("truc_validation_unapproved_chunk")
        raw = self.original["phonemize"](text, punc_norm=punc_norm)
        plan = chunk_plan(text, raw, self.original["frame_cap"])
        if plan != self.current["phone_plans"][index]:
            raise ValueError("truc_validation_native_plan_drift")
        self.plans.append(plan)
        return plan["us"]

    def frame_cap(self, phonemes):
        """Use only an approved conservative budget after every chunk has been verified."""
        if self.current is None or len(self.plans) != len(self.current["phone_plans"]):
            raise ValueError("truc_validation_incomplete_plan")
        caps = {p["shared_cap"] for p in self.plans if p["us"] == phonemes}
        if len(caps) != 1:
            raise ValueError("truc_validation_frame_binding")
        return caps.pop()

    def infer(self, text, *, voice):
        """Admit one frozen rendered sentence and delegate every original chunk exactly once."""
        if voice != "Trúc Ly":
            raise ValueError("truc_validation_voice_only")
        self.current = next((r for r in self.rows if r["rendered_text"] == text), None)
        if self.current is None:
            raise ValueError("truc_validation_unapproved_text")
        self.plans = []
        self.binding = None
        result = ProsodyAdapter.infer(self, text, voice=voice)
        if self.binding is None or len(self.last_chunks) != len(
            self.current["phone_plans"]
        ):
            raise ValueError("truc_validation_actual_chunk_binding")
        self.last_trace.update(
            validation_case=self.current["id"],
            validation_plans=self.plans,
            voice_binding=self.binding,
            term_mode="us",
        )
        LOGGER.info(
            "truc_validation_request_complete case=%s chunks=%d",
            self.current["id"],
            len(self.plans),
        )
        return result


def probe():
    """Inspect genuine original SDK chunks/phones/token roundtrip for the declared rendered packet without weights."""
    from sea_g2p import Normalizer, G2P
    from tokenizers import Tokenizer
    from vieneu_utils.core_utils import (
        split_into_sentences,
        pack_sentences_into_chunks,
        _classify_gap,
        max_expected_frames,
    )

    raw = sys.stdin.buffer.read(32769)
    rows = json.loads(raw)
    if len(raw) > 32768 or len(rows) != 10:
        raise ValueError("truc_validation_probe_bound")
    n, g = Normalizer(lang="vi"), G2P(lang="vi")
    t = Tokenizer.from_file("/approved-tokenizer.json")
    for row in rows:
        chunks, gaps = preserving_chunks(
            row["rendered_text"],
            n.normalize,
            split_into_sentences,
            pack_sentences_into_chunks,
            _classify_gap,
        )
        plans = [
            chunk_plan(chunk, g.convert(chunk, punc_norm=False), max_expected_frames)
            for chunk in chunks
        ]
        unknown = 0
        for plan in plans:
            ids = t.encode(plan["us"], add_special_tokens=False).ids
            unknown += ids.count(t.token_to_id("<|unk|>"))
            if t.decode(ids, skip_special_tokens=False) != plan["us"]:
                raise ValueError("truc_validation_roundtrip")
        row.update(
            chunks=chunks,
            gaps=gaps,
            phone_plans=plans,
            unknown_tokens=unknown,
            reference_phones={
                word: g.convert("<en>" + word + "</en>", punc_norm=False)
                for word in row["references"]
            },
        )
    with Path("/output/frontend.json").open("x") as f:
        json.dump(
            dict(
                description="Original SDK observations for a declared new Truc Ly corpus; no new lexical target or neural calls.",
                rows=rows,
                model_calls=0,
                voice="Trúc Ly",
            ),
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")
    validate_entries(rows)
    LOGGER.info("truc_validation_probe_complete model_calls=0")


def serve(expected_sha):
    """Load only after verifying the read-only approved packet, then serve at most ten first attempts."""
    raw = Path("/approved-validation.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("truc_validation_packet_sha")
    rows = json.loads(raw)["rows"]
    validate_entries(rows)

    def factory(wrapper):
        """Inject only the frozen validation packet into the retained clause runtime."""
        return ValidationAdapter(wrapper, rows)

    with contextlib.redirect_stdout(sys.stderr):
        runtime = configure_runtime("clauses", adapter_factory=factory)
    emit(
        "ready",
        candidate="turbo",
        profile="truc-validation",
        packet_sha256=expected_sha,
        execution=runtime.execution,
    )
    seen = set()
    for _ in range(11):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("truc_validation_message_bound")
        message = json.loads(raw)
        validate_message(message)
        if message["op"] == "close":
            emit("closed", calls=len(seen))
            return
        if message["op"] != "synthesize" or message["id"] in seen or len(seen) >= 10:
            raise ValueError("truc_validation_request_ceiling")
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
                    ).open("xb") as f:
                        f.write(content)
        emit(
            "result",
            id=message["id"],
            operation="synthesize",
            worker_wall_seconds=time.perf_counter() - started,
            **result,
        )
    raise ValueError("truc_validation_request_ceiling")


def main():
    """Run the fixed no-weights probe or a SHA-bound original-policy Truc Ly worker."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if sys.argv[1:] == ["--probe"]:
        probe()
    elif len(sys.argv) == 3 and sys.argv[1] == "--run":
        serve(sys.argv[2])
    else:
        raise ValueError("truc_validation_mode")


if __name__ == "__main__":
    main()
