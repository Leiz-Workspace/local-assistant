"""Verify the context retention panel freezes inputs and reports incomplete campaigns without answer-quality claims."""

import json
import logging

import pytest

from benchmarks.context_policy_probe import probe
from src.application.services.context_composer import compose_context
from tests.test_context_reduction import count

LOGGER = logging.getLogger(__name__)


class Preparation:
    """Emulate tokenizer preparation through the real composer without model completions."""

    def __init__(self, fail=False):
        """Optionally interrupt before the first case to test partial retention and cleanup."""
        self.fail = fail

    async def prepare(self, messages, **options):
        """Run the production context composer with deterministic counts and no inference endpoint."""
        if self.fail:
            raise RuntimeError("fixture_interruption")
        options["strategy"] = options.pop("context_strategy", "evidence-first")
        fitted, report = await compose_context(messages, count_tokens=count, **options)
        return None, fitted, report


@pytest.mark.asyncio
async def test_panel_retains_all_eight_mechanic_observations(tmp_path):
    """Freeze the fixed first panel and distinguish controlled packing from semantic/model testing."""
    output = tmp_path / "first"
    result = await probe(Preparation(), output)
    assert result["status"] == "PACKING_AS_EXPECTED"
    assert len(result["results"]) == 8
    assert result["completion_calls"] == 0 and not result["semantic_quality_measured"]
    frozen = json.loads((output / "frozen-inputs.json").read_text())
    assert frozen["source_sha256"] == result["source_sha256"]
    assert json.loads((output / "observations.json").read_text())["raw_cache_cleared"]
    with pytest.raises(FileExistsError):
        await probe(Preparation(), output)
    LOGGER.info("test_context_policy_panel_receipts_verified")


@pytest.mark.asyncio
async def test_interruption_retains_first_failure_without_retry(tmp_path):
    """Preserve incomplete observations and joined cache cleanup when native preparation cannot continue."""
    output = tmp_path / "partial"
    with pytest.raises(RuntimeError, match="fixture_interruption"):
        await probe(Preparation(fail=True), output)
    result = json.loads((output / "observations.json").read_text())
    assert (
        not result["complete"]
        and result["raw_cache_cleared"]
        and result["results"] == []
    )
