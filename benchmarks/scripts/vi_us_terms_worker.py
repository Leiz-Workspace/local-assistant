"""Compare declared US term phonemes using the original voice, clause and accepted API boundaries."""

import contextlib
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

from benchmarks.scripts.vi_api_stress_worker import replace_api
from benchmarks.scripts.vi_speech_prosody import ProsodyAdapter, preserving_chunks
from benchmarks.scripts.vi_speech_worker import configure_runtime
from benchmarks.scripts.vi_voice_worker import emit, native_bytes, validate_message

LOGGER = logging.getLogger(__name__)
TERMS = {
    "python": ("pˈaɪθən", "pˈaɪθɑːn"),
    "github": ("ɡˈɪt hˈʌb", "ɡˈɪthʌb"),
    "server": ("sˈɜːvɚ", "sˈɜːɹvɚ"),
}
CONTROLS = {"docker": "dˈɑːkɚ", "browser": "bɹˈaʊzɚ", "database": "dˈeɪɾəbˌeɪs"}
CASES = (
    dict(
        id="python-vi",
        text="Bạn muốn học Python hay dùng API của ứng dụng?",
        terms=["python"],
        controls=[],
    ),
    dict(
        id="python-en",
        text="I write code in Python every day.",
        terms=["python"],
        controls=[],
    ),
    dict(
        id="docker",
        text="Chị sẽ dùng Docker để chạy ứng dụng.",
        terms=[],
        controls=["docker"],
    ),
    dict(
        id="github",
        text="Mã nguồn được lưu trên GitHub của dự án.",
        terms=["github"],
        controls=[],
    ),
    dict(
        id="browser",
        text="Mở browser để kiểm tra trang web của ứng dụng.",
        terms=[],
        controls=["browser"],
    ),
    dict(
        id="server-database",
        text="Server đang kết nối với database của ứng dụng.",
        terms=["server"],
        controls=["database"],
    ),
)


def phone_plan(raw, case, cap):
    """Freeze exact term spans and a common conservative frame allowance without changing other phones."""
    baseline, api_count = replace_api(raw)
    if api_count != int("API" in case["text"]):
        raise ValueError("us_terms_api_binding")
    changed, edits = baseline, []
    for term in case["terms"]:
        before, after = TERMS[term]
        if changed.count(before) != 1:
            raise ValueError("us_terms_missing_or_ambiguous_term")
        start = changed.index(before)
        edits.append(dict(term=term, start=start, before=before, after=after))
        changed = changed[:start] + after + changed[start + len(before) :]
    for term in case["controls"]:
        if baseline.count(CONTROLS[term]) != 1 or changed.count(CONTROLS[term]) != 1:
            raise ValueError("us_terms_control_changed")
    base_cap, us_cap = min(300, cap(baseline)), min(300, cap(changed))
    if min(base_cap, us_cap) < 1:
        raise ValueError("us_terms_invalid_frame_allowance")
    LOGGER.info(
        "us_term_phone_plan case=%s edits=%d api=%d", case["id"], len(edits), api_count
    )
    return dict(
        raw=raw,
        baseline=baseline,
        us=changed,
        edits=edits,
        api_replacements=api_count,
        baseline_original_cap=base_cap,
        us_original_cap=us_cap,
        shared_cap=min(base_cap, us_cap),
        same_input=baseline == changed,
    )


class TermsAdapter(ProsodyAdapter):
    """Change only declared term phones while reusing original clause, voice, sampling and joining code."""

    def __init__(self, wrapper, mode, dependencies=None):
        """Bind one explicit role and retain the original dependency objects and resolver."""
        if mode not in {"baseline", "us"}:
            raise ValueError("us_terms_mode")
        super().__init__(wrapper, dependencies)
        self.mode = mode
        self.original = dict(self.dependencies)
        self.dependencies = dict(
            self.dependencies, phonemize=self.phonemize, frame_cap=self.frame_cap
        )
        self.original_resolver = wrapper._resolve_ref
        wrapper._resolve_ref = self.resolve
        self.plan = None
        self.binding = None
        self.case = None
        LOGGER.info("us_terms_adapter_bound mode=%s", mode)

    def resolve(self, voice, reference, denoise, use_codes):
        """Audit genuine original speaker/reference objects without changing their identity or values."""
        if denoise is not True or use_codes is not True or reference is not None:
            raise ValueError("us_terms_reference_policy")
        speaker, codes = self.original_resolver(voice, reference, denoise, use_codes)
        if codes is None:
            raise ValueError("us_terms_reference_codes_missing")
        self.binding = dict(
            speaker_sha256=hashlib.sha256(speaker.tobytes()).hexdigest(),
            reference_codes_sha256=hashlib.sha256(codes.tobytes()).hexdigest(),
        )
        LOGGER.info("us_terms_voice_bound voice=%s mode=%s", voice, self.mode)
        return speaker, codes

    def phonemize(self, text, punc_norm):
        """Plan the one frozen chunk before any generation and preserve the accepted API phones."""
        if self.plan is not None or self.case is None:
            raise ValueError("us_terms_expected_single_chunk")
        raw = self.original["phonemize"](text, punc_norm=punc_norm)
        self.plan = phone_plan(raw, self.case, self.original["frame_cap"])
        return self.plan[self.mode]

    def frame_cap(self, phonemes):
        """Apply the same non-increased per-pair frame budget to both modes."""
        if self.plan is None or phonemes != self.plan[self.mode]:
            raise ValueError("us_terms_frame_binding")
        return self.plan["shared_cap"]

    def infer(self, text, *, voice):
        """Admit only the declared source sentence and delegate original generation and joining exactly once."""
        self.case = next((case for case in CASES if case["text"] == text), None)
        if self.case is None:
            raise ValueError("us_terms_unlisted_sentence")
        self.plan, self.binding = None, None
        result = super().infer(text, voice=voice)
        if self.plan is None or self.binding is None or len(self.last_chunks) != 1:
            raise ValueError("us_terms_actual_binding")
        self.last_trace.update(
            us_terms=self.plan, voice_binding=self.binding, term_mode=self.mode
        )
        LOGGER.info(
            "us_terms_request_complete mode=%s case=%s", self.mode, self.case["id"]
        )
        return result


def probe():
    """Inspect the six fixed paired phone plans with only existing SDK/tokenizer and no model weights."""
    from sea_g2p import Normalizer, G2P
    from tokenizers import Tokenizer
    from vieneu_utils.core_utils import (
        split_into_sentences,
        pack_sentences_into_chunks,
        _classify_gap,
        max_expected_frames,
    )

    request = sys.stdin.buffer.read(16385)
    if len(request) > 16384 or json.loads(request) != list(CASES):
        raise ValueError("us_terms_probe_packet")
    normalizer, g2p = Normalizer(lang="vi"), G2P(lang="vi")
    tokenizer = Tokenizer.from_file("/approved-tokenizer.json")
    if g2p.convert("<en>github</en>", punc_norm=False) != TERMS["github"][1]:
        raise ValueError("us_terms_github_dictionary_changed")
    rows = []
    for case in CASES:
        chunks, gaps = preserving_chunks(
            case["text"],
            normalizer.normalize,
            split_into_sentences,
            pack_sentences_into_chunks,
            _classify_gap,
        )
        if len(chunks) != 1 or gaps:
            raise ValueError("us_terms_single_chunk_probe")
        plan = phone_plan(
            g2p.convert(chunks[0], punc_norm=False), case, max_expected_frames
        )
        for role in ("baseline", "us"):
            phones = plan[role]
            ids = tokenizer.encode(phones, add_special_tokens=False).ids
            if (
                tokenizer.token_to_id("<|unk|>") in ids
                or tokenizer.decode(ids, skip_special_tokens=False) != phones
            ):
                raise ValueError("us_terms_unknown_or_roundtrip")
        rows.append(
            dict(
                id=case["id"],
                source_text=case["text"],
                chunks=chunks,
                gaps=gaps,
                phone_plan=plan,
                unknown_tokens=0,
            )
        )
    with Path("/output/frontend.json").open("x") as stream:
        json.dump(
            dict(
                description="Paired same-text US phone plans, unchanged API policy and shared non-increased caps; no neural calls.",
                rows=rows,
                model_calls=0,
            ),
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")
    LOGGER.info("us_terms_probe_complete rows=6 model_calls=0")


def serve(mode):
    """Serve at most twelve first attempts per role through the unchanged offline CPU runtime."""

    def factory(wrapper):
        """Inject the explicit research role into the original runtime factory."""
        return TermsAdapter(wrapper, mode)

    with contextlib.redirect_stdout(sys.stderr):
        runtime = configure_runtime("clauses", adapter_factory=factory)
    emit(
        "ready",
        candidate="turbo",
        profile="us-terms",
        mode=mode,
        execution=runtime.execution,
    )
    seen = set()
    for _ in range(13):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("us_terms_message_bound")
        message = json.loads(raw)
        validate_message(message)
        if message["op"] == "close":
            emit("closed", calls=len(seen))
            return
        if message["op"] != "synthesize" or message["id"] in seen or len(seen) >= 12:
            raise ValueError("us_terms_request_ceiling")
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
    raise ValueError("us_terms_request_ceiling")


def main():
    """Select only the fixed model-free probe or one of two declared research roles."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if sys.argv[1:] == ["--probe"]:
        probe()
    elif len(sys.argv) == 2 and sys.argv[1] in {"baseline", "us"}:
        serve(sys.argv[1])
    else:
        raise ValueError("us_terms_mode")


if __name__ == "__main__":
    main()
