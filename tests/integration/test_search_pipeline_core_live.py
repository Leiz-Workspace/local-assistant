"""Retain one frozen authored Brave-shaped fixture through the actual unchanged CORE, never claiming external search acceptance."""

import hashlib
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import pytest
from coding_mvp_cases import save_artifact
from test_brave_search import adapter_fixture

from src.application.ports.search import SearchHit
from src.application.services.search_pipeline import SearchPipeline, search_messages
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter

logger = logging.getLogger(__name__)
CASE_PATH = Path("tests/fixtures/search/d47-search-core.json")
SOURCE_PATHS = (
    "src/application/ports/search.py",
    "src/application/services/search_pipeline.py",
    "src/infrastructure/brave_search.py",
    "tests/test_search_pipeline.py",
    "tests/test_brave_search.py",
    "tests/integration/test_search_pipeline_core_live.py",
    str(CASE_PATH),
)


class ObservedExistingCore:
    """Observe the original adapter's one application-port call without changing configuration or prompts."""

    def __init__(self):
        """Bind the unchanged adapter and empty local observations without inference."""
        self.adapter = LlamaInferenceAdapter()
        self.calls = []
        self.completion = None

    async def complete(self, **options):
        """Retain exact selected prompt/options and the actual completion for private evidence."""
        self.calls.append(options)
        self.completion = await self.adapter.complete(**options)
        return self.completion


@pytest.mark.asyncio
async def test_actual_existing_core_with_frozen_authored_search_snippets():
    """Measure one existing CORE response and preserve both success and failure without a provider claim."""
    assert os.environ.get("LOCAL_ASSISTANT_LIVE_E2E") == "1"
    case = json.loads(CASE_PATH.read_text())
    adapter, requests, stream = adapter_fixture(body=case["response"])
    core = ObservedExistingCore()
    directory = Path.cwd() / "data/backups" / ("d47-search-core-" + uuid4().hex)
    directory.mkdir(mode=0o700)
    freeze = save_artifact(
        directory,
        "freeze.json",
        dict(
            description="Exact authored fixture and new sources frozen before the first actual CORE call; no live external search.",
            case=case,
            source_sha256={
                name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                for name in SOURCE_PATHS
            },
        ),
    )
    report = dict(
        description="Actual original CORE over one authored mock-provider fixture; same-agent synthetic evidence only.",
        artifact=str(directory),
        freeze=freeze,
        status="FAILED",
        actual_core_port_attempts=0,
        external_provider_requests=0,
        human_independent=False,
        automatic_retries=0,
    )
    try:
        service = SearchPipeline(provider_id="brave", provider=adapter, inference=core)
        result = await service.run(case["query"])
        report["result"] = result
        assert len(core.calls) == len(requests) == 1 and stream.closed
        assert "fixture-private-key" not in json.dumps(core.calls)
        options = core.calls[0]
        assert options["profile"] == "core" and options["preset"] == "fast"
        assert options["temperature"] == 0 and options["max_tokens"] == 768
        expected = search_messages(
            case["query"],
            tuple(
                SearchHit(row["title"], row["url"], row["description"])
                for row in case["response"]["web"]["results"]
            ),
        )
        assert options["messages"] == expected
        report["prompt_sha256"] = hashlib.sha256(
            json.dumps(expected, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        oracle = case["oracle"]
        assert result["status"] == oracle["status"]
        assert oracle["answer_contains"] in result["answer"]
        assert [row["source_id"] for row in result["citations"]] == oracle[
            "citation_ids"
        ]
        assert result["citations"][0]["url"] == oracle["citation_url"]
        assert result["semantic_validation"] is False
        report["status"] = "PASS_AUTHORED_SEARCH_CORE_FIXTURE"
        logger.info("search_core_fixture_oracle_passed")
    except BaseException as exc:
        report["error_type"] = type(exc).__name__
        raise
    finally:
        report["actual_core_port_attempts"] = len(core.calls)
        report["mock_provider_requests"] = len(requests)
        report["provider_stream_closed"] = stream.closed
        report["actual_completion"] = (
            asdict(core.completion) if core.completion is not None else None
        )
        save_artifact(directory, "summary.json", report)
        logger.info("search_core_fixture_evidence_retained")
