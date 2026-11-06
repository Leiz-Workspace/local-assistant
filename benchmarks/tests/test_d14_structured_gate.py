"""Verify the fresh structured D14 corpus, answer-free schemas, exact first accounting and quality-versus-format gate distinction without model calls."""

import copy
import json
import runpy

import httpx
import pytest

from benchmarks.scripts.d14_structured_acceptance import PROVENANCE_IDS
from src.infrastructure.inference.structured_profile import (
    compile_schema,
    matches_schema,
)

MODULE = runpy.run_path("benchmarks/scripts/d14_structured_gate.py")


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """Build a complete authored test corpus in a private temporary root without touching real campaign artifacts."""
    globals_ = MODULE["make_corpus"].__globals__
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setitem(globals_, "ROOT", tmp_path)
    monkeypatch.setitem(globals_, "OUTPUT", output)
    return MODULE["make_corpus"]()


def test_fresh_corpus_has_fixed_denominators_and_only_free_structural_schemas(corpus):
    """Keep original category coverage and forbid embedding gold values, enum choices or source labels in native decoding."""
    assert len(corpus) == len({case["id"] for case in corpus}) == 42
    assert {
        name: sum(c["category"] == name for c in corpus)
        for name in [
            "reasoning",
            "coding",
            "agent",
            "vietnamese",
            "multimodal",
            "memory_context",
            "performance",
        ]
    } == dict(
        reasoning=8,
        coding=8,
        agent=8,
        vietnamese=6,
        multimodal=5,
        memory_context=4,
        performance=3,
    )
    for case in corpus:
        schema = json.loads(compile_schema(case["schema"]))
        assert matches_schema(case["expected"], schema)
        assert not any(
            key in json.dumps(schema)
            for key in ['"enum"', '"const"', '"default"', '"description"']
        )
        assert case["id"].startswith("fresh-")


def test_fresh_arithmetic_and_python_references_are_independently_computed(corpus):
    """Verify authored hard-reference math, list-alias, slicing, short-circuit and comprehension cases without executing model code."""
    cases = {case["id"]: case for case in corpus}
    references = [
        126 * 37,
        90 - 90 * 2 // 5 + 8,
        (89 + 19) // 6,
        False,
        "09:43",
        True,
        6 * 13,
        60,
    ]
    assert [
        cases[f"fresh-reasoning-{n}"]["expected"]["answer"] for n in range(1, 9)
    ] == references
    a = [3, 7]
    b = a
    b.append(11)
    x = [4, 8]
    y = x[:]
    y[1] = 15
    references = [
        a,
        sum(n if n % 2 else -n for n in [2, 3, 4, 5]),
        list(range(3, 14, 4)),
        sorted({"z": 2, "m": 8, "r": 1}),
        x,
        [n * n for n in range(7) if n % 2],
        {"v": 0}.get("v", 13),
        True or (1 / 0),
    ]
    assert [
        cases[f"fresh-coding-{n}"]["expected"]["answer"] for n in range(1, 9)
    ] == references


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "wrong_fact",
    [
        False,
        True,
        "compatibility_good",
        "compatibility_fact",
        "compatibility_format",
        "compatibility_lifecycle",
        "provenance",
    ],
)
async def test_actual_controller_retains_first_values_and_never_promotes_shape_only_success(
    corpus, tmp_path, monkeypatch, wrong_fact
):
    """Run all84 native-shaped model dispatches through the real adapter while an incorrect typed answer still fails functional quality."""
    globals_ = MODULE["run"].__globals__
    freeze = tmp_path / "freeze.json"
    compatibility = (
        [
            dict(
                id=f"compatibility-{n}",
                category="performance",
                prompt=f"Return object with answer {n} and source_ids [].",
                schema=corpus[0]["schema"],
                expected=dict(answer=n, source_ids=[]),
                stream=True,
            )
            for n in range(3)
        ]
        if isinstance(wrong_fact, str) and wrong_fact.startswith("compatibility")
        else []
    )
    freeze.write_text(
        json.dumps(
            dict(
                sha256={},
                application_sha256={"fixture": "source"},
                cases=corpus,
                fresh_stream_compatibility_cases=compatibility,
            )
        )
    )
    active = {"profile": None}
    counters = dict(core=0, unrestricted=0)
    retired = []

    class Server:
        """Expose an explicitly fake native lifecycle without claiming real model or resource measurements."""

        def __init__(self, profile, root):
            """Bind only the next declared profile and deterministic test lifecycle state."""
            self.profile, self.failure, self.exit_code = profile, None, None
            self.compatibility = root.name == "core-stream-compatibility"

        async def start(self):
            """Make only this fixture's alias available to native-shaped discovery."""
            active["profile"] = self.profile

        async def stop(self):
            """Retire the exact simulated profile after all its first observations finish."""
            self.exit_code = 0
            retired.append(self.profile)

        def receipt(self):
            """Return only authored fixture retirement facts without a fabricated memory benchmark."""
            return dict(
                reaped=not (
                    self.compatibility and wrong_fact == "compatibility_lifecycle"
                ),
                exit_code=0,
                guard_failure=None,
                fixture_only=True,
            )

    async def calibrate(client, case):
        """Provide declared long-context fixture metadata without tokenizer or model traffic."""
        return "fixture context " + case["needle"], dict(
            user_tokens=30500, needle_prefix_tokens=case["needle_target"]
        )

    async def cancel(client, profile, root):
        """Represent a fixture-only native retirement signal without claiming an actual cancellation experiment."""
        return dict(native_slot_retired=True, fixture_only=True)

    def state():
        """Provide identical authored process/container metadata for deterministic lifecycle checks."""
        return dict(native_pids=[], boot_id="fixture", containers=[])

    def resources():
        """Provide sufficient synthetic headroom without reading or reserving actual RAM/VRAM."""
        return dict(GPU_free_MiB=15000, available_RAM_KiB=20 * 1024**2)

    def manifest():
        """Return the exact small authored source manifest used by this controller fixture."""
        return {"fixture": "source"}

    def verify(value):
        """Require that the controller still verifies the exact expected authored source freeze."""
        assert value == {"fixture": "source"}

    def provenance(profile):
        """Return five distinct non-model fixture observations for quality-gate control flow."""
        return [
            dict(id=key, passed=wrong_fact != "provenance")
            for key in sorted(PROVENANCE_IDS)
        ]

    def handler(request):
        """Serve actual adapter discovery and bounded native wire results while counting each first model generation."""
        model = "qwen3.5-9b-" + active["profile"]
        if request.method == "GET":
            return httpx.Response(
                200,
                json=dict(
                    data=[
                        dict(
                            id=model,
                            architecture=dict(input_modalities=["text", "image"]),
                        )
                    ]
                ),
            )
        profile = active["profile"]
        case = (corpus + compatibility if profile == "core" else corpus)[
            counters[profile]
        ]
        counters[profile] += 1
        value = copy.deepcopy(case["expected"])
        if (wrong_fact is True and case["id"] == "fresh-reasoning-1") or (
            wrong_fact == "compatibility_fact"
            and case["id"].startswith("compatibility-")
        ):
            value["answer"] = -999
        content = (
            "[]"
            if wrong_fact == "compatibility_format"
            and case["id"].startswith("compatibility-")
            else json.dumps(value, ensure_ascii=False)
        )
        usage = dict(
            prompt_tokens=30550 if case["category"] == "memory_context" else 100,
            completion_tokens=32,
        )
        payload = json.loads(request.content)
        assert payload["response_format"]["schema"] == case["schema"]
        if payload["stream"]:
            parts = [
                dict(
                    model=model,
                    choices=[
                        dict(index=0, delta=dict(content=content), finish_reason=None)
                    ],
                ),
                dict(
                    model=model,
                    choices=[dict(index=0, delta={}, finish_reason="stop")],
                    usage=usage,
                ),
            ]
            raw = (
                "".join("data: " + json.dumps(part) + "\n\n" for part in parts)
                + "data: [DONE]\n\n"
            )
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=raw.encode()
            )
        return httpx.Response(
            200,
            json=dict(
                model=model,
                choices=[
                    dict(
                        message=dict(role="assistant", content=content),
                        finish_reason="stop",
                    )
                ],
                usage=usage,
            ),
        )

    original = httpx.AsyncClient

    def client_factory(**options):
        """Redirect only this fixture's HTTP client to the finite native-shaped transport without replacing actual result validation."""
        return original(
            base_url="http://localhost", transport=httpx.MockTransport(handler)
        )

    monkeypatch.setitem(globals_, "FREEZE", freeze)
    monkeypatch.setitem(globals_, "source_manifest", manifest)
    monkeypatch.setitem(globals_, "verify_manifest", verify)
    for key, value in [
        ("OwnedServer", Server),
        ("local_state", state),
        ("resources", resources),
        ("context_prompt", calibrate),
        ("cancellation_probe", cancel),
        ("provenance", provenance),
    ]:
        monkeypatch.setitem(MODULE["BASE"], key, value)
    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await MODULE["run"]()
    assert counters == dict(core=42 + len(compatibility), unrestricted=42)
    assert retired == ["core", "unrestricted"] + (["core"] if compatibility else [])
    assert result["format_gate_passed"] is (wrong_fact != "compatibility_format")
    assert result["quality_gate_passed"] is (
        wrong_fact is False or wrong_fact == "compatibility_good"
    )
    assert result["functional_gate_passed"] is (
        wrong_fact is not True
        and wrong_fact not in {"compatibility_fact", "compatibility_format"}
    )
    assert all(
        p["functional_passed"] == (41 if wrong_fact is True else 42)
        for p in result["profiles"].values()
    )


@pytest.mark.parametrize(
    "fault", [None, "old_case", "already_loaded", "incomplete_core", "unsettled"]
)
def test_suffix_cannot_retry_or_replace_first_profile_quality_failures(fault):
    """Admit only an unattempted suffix, retaining every failed first CORE row rather than using outcome-based resampling."""
    prior = dict(
        status="INCOMPLETE",
        runtime_baseline_restored=True,
        profiles=dict(
            core=dict(
                rows=[
                    dict(id=str(n), model_requests=1, functional_passed=False)
                    for n in range(42)
                ],
                runtime=dict(exit_code=0, reaped=True),
                cancellation=dict(native_slot_retired=True),
            ),
            unrestricted=dict(rows=[], runtime=dict(pid=None)),
        ),
    )
    if fault == "old_case":
        prior["profiles"]["unrestricted"]["rows"] = [dict(model_requests=1)]
    if fault == "already_loaded":
        prior["profiles"]["unrestricted"]["runtime"]["pid"] = 1
    if fault == "incomplete_core":
        prior["profiles"]["core"]["rows"].pop()
    if fault == "unsettled":
        prior["profiles"]["core"]["runtime"]["reaped"] = False
    if fault is None:
        assert (
            MODULE["validate_unmeasured_suffix"](prior)["rows"][0]["functional_passed"]
            is False
        )
    else:
        with pytest.raises(ValueError):
            MODULE["validate_unmeasured_suffix"](prior)
