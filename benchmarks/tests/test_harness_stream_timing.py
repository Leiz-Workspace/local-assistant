"""Verify first-text timing and partial protocol evidence without network, GPU or model calls."""

import json

import httpx
import pytest

from benchmarks.harness_stream_timing import TimingError, measure


@pytest.mark.asyncio
async def test_first_text_excludes_null_role_chunks_and_requires_done():
    """Use a controlled clock to separate time to content from the final stream duration."""
    frames = [
        dict(choices=[dict(delta=dict(role="assistant", content=None))]),
        dict(choices=[dict(delta=dict(content="{"))]),
        dict(choices=[dict(delta=dict(content="}"), finish_reason="stop")]),
    ]
    stream = (
        "".join("data: " + json.dumps(frame) + "\n\n" for frame in frames)
        + "data: [DONE]\n\n"
    )
    ticks = iter([10, 10.25, 10.5])
    async with httpx.AsyncClient(
        base_url="http://fixture",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, text=stream, headers={"content-type": "text/event-stream"}
            )
        ),
    ) as client:
        result = await measure(
            client, dict(stream=True, max_tokens=512), clock=lambda: next(ticks)
        )
    assert result["status"] == "COMPLETE" and result["content"] == "{}"
    assert result["first_text_delta_seconds"] == 0.25 and result["total_seconds"] == 0.5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["missing_done", "length", "tool", "malformed", "empty"]
)
async def test_first_partial_stream_is_not_reported_complete(failure):
    """Keep raw partial events and timing for truncation, tool calls and malformed/incomplete streams."""
    delta = dict(content="partial")
    if failure == "tool":
        delta["tool_calls"] = [{"name": "shell"}]
    event = dict(
        choices=[
            dict(delta=delta, finish_reason="length" if failure == "length" else "stop")
        ]
    )
    body = (
        "data: "
        + ("bad-json" if failure == "malformed" else json.dumps(event))
        + "\n\n"
    )
    if failure != "missing_done":
        body += "data: [DONE]\n\n"
    if failure == "empty":
        body = "data: [DONE]\n\n"
    async with httpx.AsyncClient(
        base_url="http://fixture",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, text=body, headers={"content-type": "text/event-stream"}
            )
        ),
    ) as client:
        with pytest.raises(TimingError) as caught:
            await measure(client, dict(stream=True, max_tokens=512))
    assert caught.value.receipt["status"] == "INCOMPLETE"
    assert caught.value.receipt["total_seconds"] is not None


@pytest.mark.asyncio
async def test_eight_replays_keep_actual_snapshots_but_never_add_semantic_scores(
    tmp_path,
):
    """Run the complete benchmark replay against real workspace reads and a fake native streaming transport."""
    from uuid import uuid4
    from apps.api.core.model_config import get_model_profile
    from apps.api.services.workspaces import WorkspaceService
    from apps.harness.inference import ProductInference
    from benchmarks.harness_stream_timing import replay
    from benchmarks.tests.test_har008_maintenance import (
        fixture_panel,
        run_panel,
        FixtureSampler,
    )
    from src.application.services.workspace_policy import WorkspaceSpec
    from src.infrastructure.readonly_workspace import WorkspaceCatalog

    api, workspace, root, quality = fixture_panel(tmp_path)
    run_panel(api, workspace, root, quality)
    owner = uuid4()
    service = WorkspaceService(
        WorkspaceCatalog([WorkspaceSpec(owner, workspace, str(root), "timing-fixture")])
    )
    calls = []

    def respond(request):
        """Serve approved-profile preparation and a complete valid JSON stream without semantic correctness claims."""
        if request.url.path == "/v1/models":
            return httpx.Response(
                200, json={"data": [{"id": get_model_profile("core")["model_id"]}]}
            )
        if request.url.path == "/apply-template":
            return httpx.Response(200, json={"prompt": "prepared"})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2, 3]})
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["stream"] is True and payload["max_tokens"] == 512
        assert payload["response_format"]["json_schema"]["schema"]["anyOf"]
        calls.append(payload)
        event = dict(
            choices=[
                dict(
                    delta=dict(content='{"value":null,"quote":null}'),
                    finish_reason="stop",
                )
            ]
        )
        return httpx.Response(
            200,
            text="data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    try:
        result = await replay(
            ProductInference(transport=httpx.MockTransport(respond)),
            service,
            owner,
            workspace,
            root,
            quality,
            tmp_path / "timing",
            pid=42,
            sampler_factory=FixtureSampler,
            preflight=lambda pid: dict(pid=pid, start_ticks=7),
        )
    finally:
        await service.shutdown()
    assert (
        result["status"] == "MEASUREMENT_COMPLETE"
        and len(calls) == result["completed_attempts"] == 8
    )
    assert not result["semantic_scored"]
    assert len(list((tmp_path / "timing").glob("*-response.json"))) == 8
