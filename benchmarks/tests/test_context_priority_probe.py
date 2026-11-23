"""Verify the fixed context probe freezes inputs and never confuses packing with semantic or memory qualification."""

import json
import logging

import pytest

from benchmarks.context_priority_probe import probe

LOGGER = logging.getLogger(__name__)


class FixturePreparation:
    """Provide controlled packing observations without a model, tokenizer or completion implementation."""

    def __init__(self, output, fail=False):
        """Keep the output location and optional second-observation fault for receipt verification."""
        self.output, self.fail, self.calls = output, fail, 0

    async def prepare(self, messages, *, evidence, context_strategy, **options):
        """Assert preflight freeze and provide only the expected policy-specific presence facts."""
        assert (self.output / "frozen-inputs.json").exists()
        assert options == {"preset": "fast", "max_tokens": 512}
        self.calls += 1
        if self.fail and self.calls == 2:
            raise RuntimeError("synthetic_preparation_failure")
        source = context_strategy == "evidence-first"
        fitted = [{"role": "user", "content": "R-752" if source else "H-286"}]
        return (
            None,
            fitted,
            {
                "source_priority": context_strategy,
                "input_tokens": 10000 if source else 24000,
            },
        )


@pytest.mark.asyncio
async def test_probe_freezes_and_reports_only_packing(tmp_path):
    """Keep all policies/options fixed and avoid falsely reporting semantic answers or peak resource measurement."""
    output = tmp_path / "probe"
    inference = FixturePreparation(output)
    result = await probe(inference, output)
    assert result["status"] == "PACKING_AS_EXPECTED" and inference.calls == 3
    assert (
        not result["semantic_quality_measured"] and not result["peak_memory_measured"]
    )
    assert result["completion_calls"] == 0
    with pytest.raises(FileExistsError):
        await probe(inference, output)
    LOGGER.info("test_context_probe_scope_verified")


@pytest.mark.asyncio
async def test_probe_keeps_partial_observations_and_never_retries(tmp_path):
    """Retain the first result when preparation fails rather than replacing or retrying the input panel."""
    output = tmp_path / "probe"
    inference = FixturePreparation(output, fail=True)
    with pytest.raises(RuntimeError):
        await probe(inference, output)
    result = json.loads((output / "observations.json").read_text())
    assert (
        len(result["results"]) == 1 and not result["complete"] and inference.calls == 2
    )
