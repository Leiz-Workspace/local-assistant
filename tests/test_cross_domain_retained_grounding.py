"""Replay exact retained neutral CORE citations while keeping the original strict minimal-fact formatting failure visible."""

import json
from pathlib import Path

from cross_domain_scenario import FACTS


def test_retained_core_quotes_are_literal_grounded_but_fail_minimal_fact_format():
    """Separate source-supported answers from the unchanged first failure to quote only each requested fact."""
    fixture = json.loads(
        Path("tests/fixtures/harness/d81-core-first-reply.json").read_text()
    )
    result = fixture["raw_result"]
    assert result["model_id"] == "qwen3.5-9b-core" and result["finish_reason"] == "stop"
    sources = {
        row["source_id"]: row["text"]
        for row in json.loads(fixture["request"]["messages"][1]["content"])["sources"]
    }
    answer = json.loads(result["content"])
    assert (answer["generation"], answer["quota_mib"], answer["lease_seconds"]) == (
        "G-17",
        128,
        45,
    )
    assert len(answer["citations"]) == 3 and {
        row["source_id"] for row in answer["citations"]
    } == set(FACTS)
    for row in answer["citations"]:
        assert sources[row["source_id"]].count(row["quote"]) == 1
        assert FACTS[row["source_id"]] in row["quote"]
    assert (
        sum(row["quote"] == FACTS[row["source_id"]] for row in answer["citations"]) == 1
    )
    assert (
        "reveal secrets" in sources["web"]
        and "reveal secrets" not in fixture["request"]["messages"][0]["content"]
    )
