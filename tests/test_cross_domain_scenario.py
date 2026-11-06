"""Verify cross-domain source/plan/profile composition with real disposable filesystem reads and authored web transport data."""

import json

import pytest
from cross_domain_scenario import FACTS, scenario

from src.application.ports.inference import CompletionResult


class Port:
    """Return controlled grounded JSON while asserting source injection remains untrusted user content."""

    def __init__(self, fault=None):
        """Select only a test-local citation or value corruption, never an execution capability."""
        self.fault = fault

    async def complete(self, **request):
        """Require exact explicit CORE text settings and all three actual captured source records."""
        assert request["profile"] == "core" and request["max_tokens"] == 512
        data = json.loads(request["messages"][1]["content"])
        assert {row["source_id"] for row in data["sources"]} == set(FACTS)
        assert "run shell" in next(
            row["text"] for row in data["sources"] if row["source_id"] == "web"
        )
        assert (
            "run shell" not in request["messages"][0]["content"]
            and "tools" not in request
        )
        answer = dict(
            generation="G-17",
            quota_mib=128,
            lease_seconds=45,
            citations=[
                dict(source_id=key, quote=value) for key, value in FACTS.items()
            ],
        )
        if self.fault == "quote":
            answer["citations"][0]["quote"] = "invented"
        if self.fault == "value":
            answer["lease_seconds"] = 999
        if self.fault == "missing":
            answer["citations"].pop()
        if self.fault == "duplicate":
            answer["citations"][2] = answer["citations"][0]
        return CompletionResult(json.dumps(answer), "fixture-core", "fast", "stop")


@pytest.mark.asyncio
async def test_native_file_code_and_bounded_web_plan_composes_without_actions(tmp_path):
    """Verify three real native source steps, checkpoint completion and exact citations with unchanged owned fixture files."""
    result = await scenario(tmp_path / "scenario", Port(), "fixture-core")
    assert result["status"] == "COMPLETE" and result["attempts"] == 3
    assert (
        len(result["native_source_receipts"]) == 2
        and not result["real_web_network_called"]
    )
    assert (
        result["original_fixture_files_unchanged"]
        and not result["action_approvals_created"]
    )


@pytest.mark.parametrize("fault", ["quote", "value", "missing", "duplicate"])
@pytest.mark.asyncio
async def test_corrupted_grounding_cannot_pass_the_cross_domain_scenario(
    tmp_path, fault
):
    """Reject unsupported values, invented quotes and missing/duplicated domain citations as failed evaluation evidence."""
    with pytest.raises(AssertionError):
        await scenario(tmp_path / fault, Port(fault), "fixture-core")


@pytest.mark.asyncio
async def test_host_relative_fixture_root_is_normalized_before_native_admission(
    tmp_path, monkeypatch
):
    """Resolve the trusted runner's relative output directory without relaxing the native absolute-root policy."""
    from pathlib import Path

    monkeypatch.chdir(tmp_path)
    result = await scenario(Path("relative-owned-root"), Port(), "fixture-core")
    assert result["status"] == "COMPLETE"
