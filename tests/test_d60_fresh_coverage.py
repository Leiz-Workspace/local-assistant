"""Verify frozen bilingual coverage accounting and URL authority boundaries without private artifacts or actual provider/model requests."""

import copy
import json

import pytest

from scripts.d60_fresh_coverage import load_corpus, observation, source_route, summarize
from src.application.ports.search import SearchBatch, SearchHit


def panel(corpus):
    """Build complete authored official-hit observations in the exact frozen order."""
    rows = []
    for q in corpus["queries"]:
        ref = corpus["references"][q["topic"]]
        hit = SearchHit(
            "Untrusted title",
            "https://" + ref["hosts"][0] + ref["direct_paths"][0],
            "Untrusted snippet",
        )
        rows.append(observation(q, ref, SearchBatch("searxng", (hit,)), None, 0.1))
    return rows


def test_fixed_bilingual_panel_and_direct_separation():
    """Require eight correct fixed labels and keep publisher-route presence distinct from direct URI presence."""
    corpus = load_corpus()
    rows = panel(corpus)
    q = corpus["queries"][2]
    ref = corpus["references"]["rfc"]
    rows[2] = observation(
        q,
        ref,
        SearchBatch(
            "searxng",
            (SearchHit("RFC", "https://www.rfc-editor.org/info/rfc9111", "Locator"),),
        ),
        None,
        0.2,
    )
    result = summarize(corpus, rows)
    assert result["accepted"] is True
    assert result["primary_route_present"] == 8
    assert result["literal_direct_present"] == 7
    assert result["verified_freshness"] is None
    assert result["semantic_relevance_evaluated"] is False
    assert "Untrusted snippet" not in json.dumps(rows)


@pytest.mark.parametrize("missing", [(0, 1, 2), (0, 1), (2, 3), (4, 5), (6, 7)])
def test_fixed_denominators_and_topic_thresholds(missing):
    """Keep every miss in the denominator and reject omitted topics even with six successful questions."""
    corpus = load_corpus()
    rows = panel(corpus)
    for index in missing:
        q = corpus["queries"][index]
        rows[index] = observation(
            q, corpus["references"][q["topic"]], SearchBatch("searxng", ()), None, 0.1
        )
    assert summarize(corpus, rows)["accepted"] is False


def test_six_hits_across_all_topics_is_accepted():
    """Accept exactly the preregistered minimum when both languages and every topic remain covered."""
    corpus = load_corpus()
    rows = panel(corpus)
    for i in [0, 3]:
        q = corpus["queries"][i]
        rows[i] = observation(
            q, corpus["references"][q["topic"]], SearchBatch("searxng", ()), None, 0.1
        )
    assert summarize(corpus, rows)["accepted"] is True


def test_error_stops_are_not_valid_empty_responses():
    """Refuse acceptance for backend errors and unattempted rows despite seven official hits."""
    corpus = load_corpus()
    rows = panel(corpus)
    for code in ["provider_failed", "not_run_after_error"]:
        q = corpus["queries"][-1]
        rows[-1] = observation(q, corpus["references"][q["topic"]], None, code, 0.0)
        assert summarize(corpus, rows)["accepted"] is False


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.searxng.org/dev/search_api.html",
        "https://docs.searxng.org.evil.test/dev/search_api.html",
        "https://user@docs.searxng.org/dev/search_api.html",
        "https://docs.searxng.org/dev/search_api.html?command=run",
        "https://docs.searxng.org/dev/search_api.html#execute",
        "https://docs.searxng.org:444/dev/search_api.html",
        "https://127.0.0.1/dev/search_api.html",
        "https://docs.searxng.org/unknown",
    ],
)
def test_unknown_authority_is_not_official_coverage(url):
    """Deny scheme, host, credentials, parameter, port, private-host and wrong-path substitutions."""
    assert source_route(url, load_corpus()["references"]["searxng"]) is None


def test_changed_labels_missing_rows_and_duplicate_corpus_are_rejected(tmp_path):
    """Reject changed query identity or language, incomplete outcomes and duplicate preregistered questions."""
    corpus = load_corpus()
    rows = panel(corpus)
    with pytest.raises(ValueError):
        summarize(corpus, rows[:-1])
    rows[0]["language"] = "vi"
    with pytest.raises(ValueError):
        summarize(corpus, rows)
    changed = copy.deepcopy(corpus)
    changed["queries"][-1] = changed["queries"][0]
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError):
        load_corpus(path)
