"""Verify frozen excerpt protocol construction, first-response retention and honest campaign accounting without live inference."""

import gzip
import hashlib
import json
import stat
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from apps.api.services.llama_gateway import GatewayError, LlamaGateway
from scripts import profile_excerpt_evaluation as evaluation
from src.application.ports.inference import CompletionResult
from src.application.services.profile_prompts import ProfilePromptRun, template_digest


def cases():
    """Load the unchanged authored corpus and host-only independent value/span oracles."""
    return json.loads(evaluation.CORPUS.read_text())["cases"]


class FixturePort:
    """Return controlled oracle-derived fixture replies solely for deterministic protocol tests."""

    def __init__(self, case, fault=None, model_id="fixture-core"):
        """Bind one test-local response transformation and count every attempted completion."""
        self.case, self.fault, self.calls, self.model_id = case, fault, 0, model_id

    async def complete(self, **request):
        """Assert the unchanged profile prompt and provide one fixed reply with optional test-only corruption."""
        self.calls += 1
        assert request["profile"] == "core" and request["max_tokens"] == 512
        body = dict(
            facts=self.case["expected_facts"],
            citations=[
                dict(source_id=row["source_id"], quote=row["expected_quote"])
                for row in self.case["sources"]
            ],
        )
        if self.fault == "long":
            body["citations"][0]["quote"] = self.case["sources"][0]["text"]
        elif self.fault == "value":
            body["facts"] = dict(body["facts"], invented="unsupported")
        elif self.fault == "duplicate":
            body["citations"][1] = body["citations"][0]
        elif self.fault == "quote":
            body["citations"][0]["quote"] = "not in the source"
        elif self.fault == "fail":
            raise RuntimeError("private diagnostic omitted")
        elif self.fault == "extra":
            body["tools"] = []
        return CompletionResult(
            json.dumps(body, ensure_ascii=False),
            self.model_id,
            "fast",
            "stop",
            320,
            180,
        )


@pytest.mark.parametrize("case", cases(), ids=lambda case: case["id"])
def test_frozen_oracles_are_unique_and_not_exposed_as_request_metadata(case):
    """Require distinct fresh facts/excerpts while sending only natural source evidence and requested keys to inference."""
    data = evaluation.payload(case)
    assert len(data["sources"]) == 3
    assert not {"expected_facts", "expected_quote", "excerpts", "offsets"} & set(data)
    assert all(set(row) == {"source_id", "text"} for row in data["sources"])
    assert "G-17" not in str(data) and "Atlas" not in str(data)
    guard = evaluation.policy(case, uuid4(), uuid4(), "fixture-core")
    assert len(guard.excerpts) == 3
    assert all(row["expected_quote"] not in data["request"] for row in case["sources"])
    assert all(
        value not in data["request"] for value in case["expected_facts"].values()
    )


@pytest.mark.parametrize("case", cases(), ids=lambda case: case["id"])
@pytest.mark.asyncio
async def test_each_frozen_case_composes_existing_prompt_and_guard_once(tmp_path, case):
    """Accept exact independent fixture values/spans while preserving original request/result artifacts and one-call limits."""
    port = FixturePort(case)
    result = await evaluation.evaluate(case, tmp_path, port, "fixture-core")
    assert (
        result["accepted"] and result["strict_excerpt_quotes"] == 3 and port.calls == 1
    )
    assert (tmp_path / "attempt.json").exists() and (
        tmp_path / "profile-result.json"
    ).exists()
    assert stat.S_IMODE((tmp_path / "score.json").stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        await evaluation.evaluate(case, tmp_path, port, "fixture-core")
    assert port.calls == 1


@pytest.mark.parametrize(
    "fault", ["long", "value", "duplicate", "quote", "fail", "extra"]
)
@pytest.mark.asyncio
async def test_first_errors_are_visible_and_never_repaired_or_retried(tmp_path, fault):
    """Keep literal-but-long quotes distinct from wrong values and retain every first failed observation without a second call."""
    port = FixturePort(cases()[0], fault)
    result = await evaluation.evaluate(cases()[0], tmp_path, port, "fixture-core")
    assert not result["accepted"] and port.calls == 1
    if fault == "long":
        assert (
            result["literal_unique_quotes"] == 3
            and result["strict_excerpt_quotes"] == 2
        )
        assert result["guard_error"] == "excerpt_mismatch"
    if fault == "value":
        assert result["guard_admitted"] and not result["facts_exact"]
    assert json.loads((tmp_path / "score.json").read_text())["accepted"] is False


@pytest.mark.asyncio
async def test_malformed_json_remains_unaccepted_without_source_oracle_repair():
    """Reject a model's malformed body without allowing the independent expected values to become generated answers."""
    case, owner, workspace = cases()[0], uuid4(), uuid4()
    run = ProfilePromptRun(
        owner,
        workspace,
        profile="core",
        model_id="fixture-core",
        template_sha256=template_digest("core"),
        inference=FixturePort(case),
    )
    try:
        reply = await run.complete(
            owner, workspace, evaluation.canonical(evaluation.payload(case))
        )
        from dataclasses import replace

        reply = replace(reply, result=replace(reply.result, content="not JSON"))
        score = evaluation.score(
            case, evaluation.policy(case, owner, workspace, "fixture-core"), reply
        )
        assert not score["accepted"] and score["guard_error"] == "invalid_json_or_shape"
    finally:
        await run.close()


@pytest.mark.parametrize(
    "status,body",
    [(200, b'{"choices":[]}'), (502, b"upstream failed"), (200, b"not JSON")],
)
@pytest.mark.asyncio
async def test_capture_preserves_first_raw_native_bytes_before_validation(
    tmp_path, status, body
):
    """Retain complete success/error/malformed response payloads and deny any second native chat attempt."""

    def handler(request):
        """Return exact fixture bytes without a real server or model."""
        return httpx.Response(status, content=body)

    transport = evaluation.RawCaptureTransport(tmp_path, httpx.MockTransport(handler))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8080"
    ) as client:
        response = await client.post("/v1/chat/completions", json=dict(model="fixture"))
        assert response.content == body
        with pytest.raises(ValueError, match="excerpt_attempt_limit"):
            await client.post("/v1/chat/completions", json={})
    assert (tmp_path / "native-response.bin").read_bytes() == body
    receipt = json.loads((tmp_path / "native-response-receipt.json").read_text())
    assert (
        receipt["complete_body_received"]
        and receipt["sha256"] == hashlib.sha256(body).hexdigest()
    )


@pytest.mark.asyncio
async def test_decoded_gzip_payload_is_not_decompressed_twice(tmp_path):
    """Preserve original JSON payload bytes while replacing stale content-encoding/length headers during replay."""
    raw = b'{"message":"first response"}'

    def handler(request):
        """Serve one gzip-encoded authored response through the deterministic transport."""
        return httpx.Response(
            200, content=gzip.compress(raw), headers={"content-encoding": "gzip"}
        )

    async with httpx.AsyncClient(
        transport=evaluation.RawCaptureTransport(tmp_path, httpx.MockTransport(handler))
    ) as client:
        response = await client.post(
            "http://127.0.0.1:8080/v1/chat/completions", json={}
        )
        assert response.content == raw and "content-encoding" not in response.headers
    assert (tmp_path / "native-response.bin").read_bytes() == raw


@pytest.mark.asyncio
async def test_oversized_native_body_keeps_bounded_prefix_and_incomplete_receipt(
    tmp_path,
):
    """Retain a maximum64KiB first response prefix and fail without accepting or reading a second response."""

    def handler(request):
        """Produce a deterministic oversized body rather than allocating any model resources."""
        return httpx.Response(200, content=b"x" * 65537)

    async with httpx.AsyncClient(
        transport=evaluation.RawCaptureTransport(tmp_path, httpx.MockTransport(handler))
    ) as client:
        with pytest.raises(ValueError, match="excerpt_native_response_limit"):
            await client.post("http://127.0.0.1:8080/v1/chat/completions", json={})
    assert (tmp_path / "native-response.bin").stat().st_size == 65536
    assert not json.loads((tmp_path / "native-response-receipt.json").read_text())[
        "complete_body_received"
    ]


@pytest.mark.asyncio
async def test_existing_gateway_rejects_length_but_raw_first_reply_survives(tmp_path):
    """Verify actual unchanged Fast gateway rejection occurs only after the first native response has been saved."""
    native = dict(
        model="qwen3.5-9b-core",
        choices=[dict(message=dict(content="unfinished"), finish_reason="length")],
        usage=dict(prompt_tokens=20, completion_tokens=512),
    )

    def handler(request):
        """Emulate only existing model verification, chat-template/tokenization and one incomplete completion."""
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=dict(data=[dict(id="qwen3.5-9b-core")]))
        if request.url.path == "/apply-template":
            return httpx.Response(200, json=dict(prompt="fixture"))
        if request.url.path == "/tokenize":
            return httpx.Response(200, json=dict(tokens=[1] * 20))
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json=native)

    gateway = LlamaGateway(
        "http://127.0.0.1:8080",
        "qwen3.5-9b-core",
        transport=evaluation.RawCaptureTransport(
            tmp_path, httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(GatewayError):
        await gateway.complete(
            messages=[dict(role="user", content="fixture")],
            max_tokens=512,
            preset="fast",
        )
    assert json.loads((tmp_path / "native-response.bin").read_bytes()) == native


@pytest.mark.parametrize(
    "config",
    [
        dict(model_id="other", base_url="http://127.0.0.1:8080"),
        dict(model_id="qwen3.5-9b-core", base_url="https://example.org"),
    ],
)
def test_recorded_port_cannot_select_another_model_or_endpoint(tmp_path, config):
    """Refuse any profile or network target outside the retained original CORE loopback configuration."""
    with pytest.raises(ValueError, match="excerpt_core_scope"):
        evaluation.RecordedCorePort(tmp_path, config)


@pytest.mark.asyncio
async def test_failed_campaign_stops_after_one_inference_failure_and_retains_result(
    tmp_path, monkeypatch
):
    """Keep incomplete coverage explicitly false without starting remaining cases or retrying a failed native request."""
    root = tmp_path / "data/backups"
    root.mkdir(parents=True)
    monkeypatch.setattr(evaluation, "ROOT", tmp_path)
    monkeypatch.setattr(evaluation, "source_manifest", lambda: {"fixed": "a" * 64})
    identity = dict(pid=37256, start_ticks=63900, command_sha256="test")
    monkeypatch.setattr(evaluation, "core_identity", lambda: identity)
    monkeypatch.setattr(evaluation, "core_snapshot", lambda: identity)
    ports = []

    def factory(path, config):
        """Return one fixture failure port and observe any forbidden second case construction."""
        port = FixturePort(cases()[0], "fail")
        ports.append(port)
        return port

    monkeypatch.setattr(evaluation, "RecordedCorePort", factory)
    result = await evaluation.campaign(root / "first")
    assert not result["complete"] and not result["all_six_cases_accepted"]
    assert len(ports) == 1 and ports[0].calls == 1
    assert (root / "first/result.json").exists()
    with pytest.raises(FileExistsError):
        await evaluation.campaign(root / "first")
    assert len(ports) == 1


@pytest.mark.asyncio
async def test_campaign_refuses_arbitrary_output_location_before_inference(tmp_path):
    """Prevent command-line artifact output from overwriting a source directory or existing benchmark."""
    with pytest.raises(ValueError, match="excerpt_private_output_root"):
        await evaluation.campaign(tmp_path / "output")


@pytest.mark.parametrize("changed_source", [False, True])
@pytest.mark.asyncio
async def test_full_campaign_retains_all_six_first_attempts_and_checks_final_freeze(
    tmp_path, monkeypatch, changed_source
):
    """Exercise complete accounting and final source integrity with six fixture ports rather than live model requests."""
    root = tmp_path / "data/backups"
    root.mkdir(parents=True)
    monkeypatch.setattr(evaluation, "ROOT", tmp_path)
    manifests = iter(
        [{"fixed": "before"}, {"fixed": "after" if changed_source else "before"}]
    )
    monkeypatch.setattr(evaluation, "source_manifest", lambda: next(manifests))
    identity = dict(pid=37256, start_ticks=63900, command_sha256="test")
    monkeypatch.setattr(evaluation, "core_identity", lambda: identity)
    monkeypatch.setattr(evaluation, "core_snapshot", lambda: identity)
    ports = []

    def factory(path, config):
        """Select each fixed test case exactly once and return the explicit expected model identity."""
        port = FixturePort(cases()[len(ports)], model_id="qwen3.5-9b-core")
        ports.append(port)
        return port

    monkeypatch.setattr(evaluation, "RecordedCorePort", factory)
    if changed_source:
        with pytest.raises(ValueError, match="excerpt_campaign_integrity"):
            await evaluation.campaign(root / "first")
    else:
        result = await evaluation.campaign(root / "first")
        assert result["complete"] and result["all_six_cases_accepted"]
    result = json.loads((root / "first/result.json").read_text())
    assert result["source_bytes_unchanged"] is not changed_source
    assert (
        result["accepted"] == 6
        and len(ports) == 6
        and all(port.calls == 1 for port in ports)
    )


@pytest.mark.parametrize("disk_failure", [False, True])
@pytest.mark.asyncio
async def test_response_stream_is_closed_even_when_capture_or_transport_fails(
    tmp_path, monkeypatch, disk_failure
):
    """Join stream cleanup and retain the available first-response prefix without requiring successful disk publication."""
    closed = []

    class Stream(httpx.AsyncByteStream):
        """Expose a partial first response and controlled transport failure with observable closure."""

        async def __aiter__(self):
            """Emit one bounded prefix before simulating a failed read."""
            yield b"first prefix"
            raise RuntimeError("fixture read failure")

        async def aclose(self):
            """Record actual closure rather than asserting only that a cleanup method exists."""
            closed.append(True)

    def handler(request):
        """Return a lazy stream so capture must own its failure and final close."""
        return httpx.Response(200, stream=Stream())

    original_publish = evaluation.publish

    def failing_publish(path, value):
        """Fail only response artifact publication after the request was durably recorded."""
        if disk_failure and Path(path).name == "native-response.bin":
            raise OSError("fixture disk full")
        return original_publish(path, value)

    monkeypatch.setattr(evaluation, "publish", failing_publish)
    async with httpx.AsyncClient(
        transport=evaluation.RawCaptureTransport(tmp_path, httpx.MockTransport(handler))
    ) as client:
        with pytest.raises((OSError, RuntimeError)):
            await client.post("http://127.0.0.1:8080/v1/chat/completions", json={})
    assert closed
    if not disk_failure:
        assert (tmp_path / "native-response.bin").read_bytes() == b"first prefix"
        assert not json.loads((tmp_path / "native-response-receipt.json").read_text())[
            "complete_body_received"
        ]
