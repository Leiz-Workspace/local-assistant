"""Verify paired frozen extraction scoring, refusal controls and campaign scope with deterministic native transports only."""

import json

import httpx
import pytest

from scripts import structured_excerpt_evaluation as evaluation


def corpus():
    """Read immutable fresh paired cases and separate missing-evidence controls."""
    return json.loads(evaluation.CORPUS.read_text())


def install_transport(monkeypatch, case, fault=None):
    """Wrap deterministic native responses in the actual first-byte capture transport and observe generation requests."""
    capture, calls = evaluation.RawCaptureTransport, []

    def handler(request):
        """Serve existing discovery/template/tokenizer endpoints and one controlled first completion per mode."""
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=dict(data=[dict(id="qwen3.5-9b-core")]))
        if request.url.path == "/apply-template":
            return httpx.Response(200, json=dict(prompt="fixture"))
        if request.url.path == "/tokenize":
            return httpx.Response(200, json=dict(tokens=[1] * 50))
        assert request.url.path == "/v1/chat/completions"
        calls.append(json.loads(request.content))
        if case.get("expected_refusal") or fault == "refusal":
            body = dict(facts=None, citations=[])
        else:
            body = dict(
                facts=dict(case["expected_facts"]),
                citations=[
                    dict(source_id=row["source_id"], quote=row["expected_quote"])
                    for row in case["sources"]
                ],
            )
        if fault == "value":
            body["facts"][case["sources"][1]["fact_key"]] = 999
        elif fault == "paragraph":
            body["citations"][0]["quote"] = case["sources"][0]["text"]
        elif fault == "duplicate":
            body["citations"][1] = body["citations"][0]
        native = dict(
            model="qwen3.5-9b-core",
            choices=[
                dict(
                    message=dict(content=json.dumps(body, ensure_ascii=False)),
                    finish_reason="length" if fault == "incomplete" else "stop",
                )
            ],
            usage=dict(prompt_tokens=50, completion_tokens=120),
        )
        return httpx.Response(503 if fault == "http" else 200, json=native)

    def transport(root):
        """Capture real fixture wire payloads before local model/result validation for either mode."""
        return capture(root, httpx.MockTransport(handler))

    monkeypatch.setattr(evaluation, "RawCaptureTransport", transport)
    return calls


@pytest.mark.parametrize("case", corpus()["cases"], ids=lambda case: case["id"])
@pytest.mark.asyncio
async def test_fixed_pairs_have_identical_messages_and_only_response_format_differs(
    tmp_path, monkeypatch, case
):
    """Exercise both actual port/controller paths with independent fixture oracle output and no feedback or expected-value injection."""
    calls = install_transport(monkeypatch, case)
    baseline = await evaluation.evaluate(case, tmp_path / "baseline", enabled=False)
    candidate = await evaluation.evaluate(case, tmp_path / "schema", enabled=True)
    assert baseline["accepted"] and candidate["accepted"] and len(calls) == 2
    with_schema = dict(calls[1])
    schema = with_schema.pop("response_format")
    assert with_schema == calls[0] and schema["type"] == "json_object"
    data = evaluation.payload(case)
    assert all(set(row) == {"source_id", "text"} for row in data["sources"])
    assert all(row["expected_quote"] not in data["request"] for row in case["sources"])
    assert (tmp_path / "baseline/native-response.bin").exists() and (
        tmp_path / "schema/native-response.bin"
    ).exists()
    with pytest.raises(FileExistsError):
        await evaluation.evaluate(case, tmp_path / "schema", enabled=True)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "case", corpus()["negative_cases"], ids=lambda case: case["id"]
)
@pytest.mark.asyncio
async def test_missing_or_instruction_only_source_requires_actual_refusal(
    tmp_path, monkeypatch, case
):
    """Retain the native null response and withhold typed answer publication on both predeclared negative controls."""
    calls = install_transport(monkeypatch, case)
    result = await evaluation.evaluate(case, tmp_path / "negative", enabled=True)
    assert (
        result["accepted"]
        and result["explicit_refusal"]
        and not result["port_published"]
    )
    assert result["port_error"] == "insufficient_evidence" and len(calls) == 1
    raw = json.loads((tmp_path / "negative/native-response.bin").read_bytes())
    assert json.loads(raw["choices"][0]["message"]["content"]) == dict(
        facts=None, citations=[]
    )


@pytest.mark.parametrize(
    "fault", ["value", "paragraph", "duplicate", "incomplete", "http", "refusal"]
)
@pytest.mark.asyncio
async def test_first_backend_or_contract_failures_remain_failed_without_retries(
    tmp_path, monkeypatch, fault
):
    """Score raw first failures after withheld publication while retaining their original native payload and finite failure kind."""
    case = corpus()["cases"][0]
    calls = install_transport(monkeypatch, case, fault)
    result = await evaluation.evaluate(case, tmp_path / "first", enabled=True)
    assert not result["accepted"] and not result["port_published"] and len(calls) == 1
    assert (tmp_path / "first/native-response.bin").exists()
    if fault == "paragraph":
        assert result["literal_unique_quotes"] == 3 and result["exact_excerpts"] == 2
    if fault == "incomplete":
        assert result["facts_exact"] and result["exact_excerpts"] == 3
    if fault == "http":
        assert result["fatal_backend_failure"]


@pytest.mark.parametrize(
    "mode", ["success", "negative_failed", "source_changed", "backend_failed"]
)
@pytest.mark.asyncio
async def test_campaign_conditions_and_first_request_budgets_are_fixed(
    tmp_path, monkeypatch, mode
):
    """Gate the historical native regression on all fresh candidates/negatives, preserve failures and never exceed the fixed scope."""
    root = tmp_path / "data/backups"
    root.mkdir(parents=True)
    monkeypatch.setattr(evaluation, "ROOT", tmp_path)
    values = iter(
        [
            {"source": "before"},
            {"source": "after" if mode == "source_changed" else "before"},
        ]
    )
    monkeypatch.setattr(evaluation, "source_manifest", lambda: next(values))
    identity = dict(pid=37256, start_ticks=63900, command_sha256="fixture")
    monkeypatch.setattr(evaluation, "core_identity", lambda: identity)
    monkeypatch.setattr(evaluation, "core_snapshot", lambda: identity)
    calls, regressions = [], []

    async def evaluate(case, root, *, enabled):
        """Record each planned mode once and optionally reject one negative or fail the first backend attempt."""
        calls.append((case["id"], enabled))
        failed = mode == "backend_failed" or (
            mode == "negative_failed" and case.get("expected_refusal")
        )
        return dict(
            case_id=case["id"],
            schema_enabled=enabled,
            accepted=not failed,
            fatal_backend_failure=mode == "backend_failed",
        )

    async def scenario(root, port, model_id):
        """Observe the conditional legacy-fixture phase without starting any real native process or model."""
        regressions.append(True)
        return dict(status="COMPLETE")

    monkeypatch.setattr(evaluation, "evaluate", evaluate)
    monkeypatch.setattr(
        evaluation.runpy,
        "run_path",
        lambda path: dict(REQUEST="fixture", scenario=scenario),
    )
    monkeypatch.setattr(
        evaluation,
        "RawCaptureTransport",
        lambda root: httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    result = await evaluation.campaign(root / "first")
    assert result["candidate_qualified"] is (mode == "success")
    assert len(calls) <= 14 and len(set(calls)) == len(calls)
    assert len(regressions) == (1 if mode in {"success", "source_changed"} else 0)
    if mode == "backend_failed":
        assert len(calls) == 1 and not result["complete"]
    assert (root / "first/result.json").exists()


@pytest.mark.asyncio
async def test_arbitrary_output_is_rejected_before_any_request(tmp_path):
    """Refuse an output outside the explicitly owned private benchmark root without creating it."""
    with pytest.raises(ValueError, match="structured_output_scope"):
        await evaluation.campaign(tmp_path / "not-owned")
