"""Exercise shared-candidate native semantic orchestration with actual fixture reads and a fake model transport."""

import json
import re
from uuid import uuid4

import httpx
import pytest

from apps.api.core.model_config import get_model_profile
from apps.api.services.workspaces import WorkspaceService
from apps.harness.inference import ProductInference
from benchmarks.semantic_review_cases import cases
from benchmarks.semantic_review_run import evaluate
from benchmarks.semantic_review_run import verify_source
from benchmarks.tests.test_semantic_review import correct_answer
from benchmarks.tests.test_har008_maintenance import FixtureSampler
from src.application.services.workspace_policy import WorkspaceSpec
from src.infrastructure.readonly_workspace import WorkspaceCatalog


@pytest.mark.parametrize("damage", [None, "hash", "line", "text"])
def test_registered_gold_is_bound_to_exact_native_evidence(damage):
    """Reject a valid-shaped snapshot whose source provenance or text differs from the registered oracle."""
    import hashlib
    from tests.test_source_output_contract import source_bytes

    case = cases()[0]
    packet = json.loads(source_bytes())
    packet["data"]["lines"] = [
        dict(
            path="subject.py",
            source_sha256=hashlib.sha256(case["source"].encode()).hexdigest(),
            line_number=index,
            line_text=text,
            content_trust="untrusted",
        )
        for index, text in enumerate(case["source"].splitlines(), 1)
    ]
    if damage == "hash":
        packet["data"]["lines"][0]["source_sha256"] = "b" * 64
    elif damage == "line":
        packet["data"]["lines"][0]["line_number"] = 7
    elif damage == "text":
        packet["data"]["lines"][0]["line_text"] = "changed"
    raw = json.dumps(packet).encode()
    if damage:
        with pytest.raises(ValueError, match="semantic_source_gold_mismatch"):
            verify_source(case, raw, "subject.py")
    else:
        verify_source(case, raw, "subject.py")


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_at", [None, 3, "http"])
async def test_shared_candidates_have_one_planned_check_without_gold_feedback(
    tmp_path, fail_at
):
    """Preserve each first raw draw and stop uncertain transport calls without any retry or source execution."""
    root = tmp_path / "workspace"
    root.mkdir()
    owner, workspace = uuid4(), uuid4()
    service = WorkspaceService(
        WorkspaceCatalog(
            [WorkspaceSpec(owner, workspace, str(root), "semantic-fixture")]
        )
    )
    panel = {case["id"]: case for case in cases()}
    calls = []

    def respond(request):
        """Provide only fake native preparation/completions and inspect that no private gold table is sent."""
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
        assert (
            payload["max_tokens"] == 512
            and not payload["chat_template_kwargs"]["enable_thinking"]
        )
        assert (tmp_path / "out" / "frozen-inputs.json").exists()
        text = payload["messages"][-1]["content"]
        assert "accepted_lines" not in text and "trusted_probe_tables" not in text
        identifier = re.search(r"semantic-\d\d", text).group()
        calls.append(payload)
        if fail_at == "http" and len(calls) == 3:
            return httpx.Response(400, json={"error": "CONTROL_FAILURE"})
        if len(calls) == fail_at:
            raise httpx.ConnectError("finite_fixture_failure")
        content = json.dumps(correct_answer(panel[identifier]))
        return httpx.Response(
            200,
            json=dict(
                choices=[
                    dict(
                        finish_reason="stop",
                        message=dict(role="assistant", content=content),
                    )
                ]
            ),
        )

    try:
        args = dict(
            pid=42,
            sampler_factory=FixtureSampler,
            preflight=lambda pid: dict(pid=pid, start_ticks=7),
        )
        if fail_at:
            with pytest.raises(
                httpx.HTTPStatusError if fail_at == "http" else httpx.ConnectError
            ):
                await evaluate(
                    ProductInference(transport=httpx.MockTransport(respond)),
                    service,
                    owner,
                    workspace,
                    root,
                    tmp_path / "out",
                    **args,
                )
            summary = json.loads((tmp_path / "out" / "summary.json").read_text())
            assert (
                summary["status"] == "INCOMPLETE"
                and len(calls) == 3
                and summary["completed_calls"] == 2
            )
            assert (
                json.loads((tmp_path / "out" / "03-response.json").read_text())[
                    "status"
                ]
                == "INCOMPLETE"
            )
            if fail_at == "http":
                assert json.loads((tmp_path / "out" / "03-response.json").read_text())[
                    "native"
                ] == {"error": "CONTROL_FAILURE"}
        else:
            summary = await evaluate(
                ProductInference(transport=httpx.MockTransport(respond)),
                service,
                owner,
                workspace,
                root,
                tmp_path / "out",
                **args,
            )
            assert len(calls) == summary["completed_calls"] == 48
            assert (
                summary["resource_status"] == "COMPLETE"
                and summary["promotion"] == "NOT_QUALIFIED"
            )
            assert all(row["passed"] == 12 for row in summary["arms"].values())
            records = [
                json.loads(path.read_text())
                for path in sorted((tmp_path / "out").glob("*-response.json"))
            ]
            for first, checked in zip(records[::2], records[1::2], strict=True):
                assert checked["shared_candidate_sha256"] == first["raw_content_sha256"]
                assert checked["workflow_seconds"] >= first["seconds"]
    finally:
        await service.shutdown()
