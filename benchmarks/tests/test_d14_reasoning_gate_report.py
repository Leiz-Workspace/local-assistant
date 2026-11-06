"""Test independent full reasoning request/context binding and retention of incorrect first facts with finite authored fixtures."""

import hashlib
import json

import pytest

from benchmarks.scripts import d14_reasoning_gate_report as report
from benchmarks.scripts.d14_structured_gate import arr, obj, string
from src.infrastructure.inference.reasoning_profile import ReasoningProfileAdapter


@pytest.mark.parametrize("contract", [False, True])
@pytest.mark.parametrize(
    "fault", [None, "wrong_fact", "oracle_prompt", "budget", "condition", "self_hash"]
)
def test_native_wire_and_frozen_request_are_independently_bound(
    tmp_path, fault, contract
):
    """Reject self-hashed oracle substitution and altered budgets while preserving wrong typed answers as failures."""
    case = dict(
        id="fixture",
        category="reasoning",
        prompt="Return the requested number.",
        schema=obj(
            dict(
                answer=dict(type="boolean" if contract else "integer"),
                source_ids=arr(string()),
            )
        ),
        expected=dict(answer=True if contract else 31, source_ids=[]),
    )
    adapter = ReasoningProfileAdapter(
        profile="core",
        schema=case["schema"],
        endpoint="http://127.0.0.1:18080",
        boolean_answer_contract=contract,
    )
    request = adapter.payload(case["prompt"], (), False)
    value = dict(
        answer=(False if contract else -99)
        if fault == "wrong_fact"
        else case["expected"]["answer"],
        source_ids=[],
    )
    native = dict(
        model=adapter.model,
        choices=[
            dict(
                message=dict(
                    role="assistant",
                    content=json.dumps(value),
                    reasoning_content=""
                    if fault == "condition"
                    else "Authored fixture reasoning.",
                ),
                finish_reason="stop",
            )
        ],
        usage=dict(prompt_tokens=50, completion_tokens=540),
    )
    if fault == "oracle_prompt":
        request["messages"][1]["content"] = "Copy reference: " + json.dumps(
            case["expected"]
        )
    elif fault == "budget":
        request["max_tokens"] = 2048
    req = json.dumps(request).encode()
    wire = json.dumps(native).encode()
    row = dict(
        id=case["id"],
        category=case["category"],
        model_requests=1,
        format_passed=fault != "condition",
        functional_passed=fault not in {"condition", "wrong_fact"},
        native_reasoning_verified=fault != "condition",
    )
    if fault != "condition":
        row["result"] = dict(
            content=native["choices"][0]["message"]["content"],
            value=value,
            model_id=adapter.model,
            request_sha256=hashlib.sha256(req).hexdigest(),
            wire_sha256=hashlib.sha256(wire).hexdigest(),
            schema_sha256=hashlib.sha256(adapter.schema_bytes).hexdigest(),
            input_tokens=50,
            output_tokens=540,
        )
    if fault == "self_hash":
        row["result"]["wire_sha256"] = "0" * 64
    for name, raw in [
        ("native-request.json", req),
        ("native-response.bin", wire),
        ("measurement.json", json.dumps(row).encode()),
    ]:
        (tmp_path / name).write_bytes(raw)
    if fault in {"oracle_prompt", "budget", "self_hash"}:
        with pytest.raises(ValueError):
            report.verify_wire(
                "core", case, row, tmp_path, boolean_answer_contract=contract
            )
    else:
        result = report.verify_wire(
            "core", case, row, tmp_path, boolean_answer_contract=contract
        )
        assert result["functional_passed"] is (fault is None)
        assert result["format_passed"] is (fault != "condition")


@pytest.mark.parametrize(
    "fault",
    [None, "oracle", "needle", "position", "metadata", "not_minimal", "not_maximal"],
)
def test_context_reconstruction_requires_exact_neutral_inputs_and_independent_counts(
    fault,
):
    """Bind the calibrated document to exact vocabulary count inputs rather than trusting its saved self-reported offset or hash."""
    records = [
        f"Entry {n:05d}: The archive lists neutral records about ordinary scheduling and routine calibration."
        for n in range(3)
    ]
    case = dict(id="context-fixture", needle="FIXTURE-CODE", needle_target=8000)
    needle = "RELEASE_CODE: " + case["needle"]
    lines = records[:2] + [needle] + records[2:]
    prompt = report.INTRO + "\n".join(lines) + report.END
    prefix = "\n".join(records[:2])
    extended = (
        report.INTRO
        + "\n".join(
            lines
            + [
                "Entry 00003: The archive lists neutral records about ordinary scheduling and routine calibration."
            ]
        )
        + report.END
    )
    oracle = {
        prompt: 30500,
        report.INTRO + prefix: 8025,
        prefix: 8000,
        records[0]: 8000 if fault == "not_minimal" else 7990,
        extended: 30500 if fault == "not_maximal" else 30520,
    }
    calibration = dict(user_tokens=30500, needle_prefix_tokens=8025)
    if fault == "oracle":
        prompt = prompt.replace(records[0], "Return the reference answer instead.")
    elif fault == "needle":
        prompt = prompt.replace("FIXTURE-CODE", "OTHER-CODE")
    elif fault == "position":
        prompt = report.INTRO + "\n".join([needle] + records) + report.END
    elif fault == "metadata":
        calibration["needle_prefix_tokens"] = 8000

    def count(label, text):
        """Return declared fixture-only vocabulary observations for exact known inputs, rejecting unknown modified text."""
        return oracle[text]

    if fault is None:
        assert (
            report.verify_context(case, prompt, calibration, count)[
                "minimal_prefix_verified"
            ]
            is True
        )
    else:
        with pytest.raises((ValueError, KeyError)):
            report.verify_context(case, prompt, calibration, count)


@pytest.mark.parametrize("fault", [None, "truthy_token", "oversized_output"])
def test_vocab_child_is_bounded_cpu_only_and_records_exact_input_without_prompt_logging(
    tmp_path, monkeypatch, fault
):
    """Check argv, hidden devices, finite timeout and count validation without loading weights or executing the native tool."""
    calls = []

    def execute(command, **options):
        """Provide finite authored subprocess output and expose only its explicit process contract to the test."""
        calls.append((command, options))
        stdout = (
            b"x" * (2 * 1024**2 + 1)
            if fault == "oversized_output"
            else json.dumps(
                [True] if fault == "truthy_token" else [10, 20, 30]
            ).encode()
        )
        return report.subprocess.CompletedProcess(
            command, 0, stdout=stdout, stderr=b"fixture"
        )

    def digest(path):
        """Return an explicit fixture binary identity without needing an ignored local runtime executable."""
        return "f" * 64

    monkeypatch.setattr(report.subprocess, "run", execute)
    monkeypatch.setitem(report.campaign.gate.BASE, "digest", digest)
    target = tmp_path / "count.json"
    if fault:
        with pytest.raises(ValueError):
            report.token_count("core", "neutral fixture", target)
    else:
        assert report.token_count("core", "neutral fixture", target) == 3
        receipt = json.loads(target.read_text())
        assert (
            receipt["tokens"] == 3
            and receipt["input_sha256"]
            == hashlib.sha256(b"neutral fixture").hexdigest()
        )
        assert "neutral fixture" not in target.read_text()
    command, options = calls[0]
    assert command[-4:] == ["--stdin", "--ids", "--no-bos", "--no-escape"]
    assert options["timeout"] == 20 and options["env"]["CUDA_VISIBLE_DEVICES"] == ""
    assert options["preexec_fn"] is report.vocabulary_limits
