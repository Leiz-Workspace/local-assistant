"""Verify frozen paired evaluation, strict independent oracle scoring and failure-safe cleanup without native calls."""

import hashlib
import json
import logging
from pathlib import Path
from uuid import uuid4

import pytest

from benchmarks import har008

LOGGER = logging.getLogger(__name__)


class FixtureAPI:
    """Simulate product lifecycle and inspect requests while returning controlled answer contracts."""

    def __init__(self, cases, workspace, output, *, fail_at=None):
        """Seed one preexisting installation to verify cleanup never removes another session's grant."""
        self.cases = {case["id"]: case for case in cases}
        self.workspace, self.output, self.fail_at = str(workspace), output, fail_at
        self.requests, self.removed, self.cancelled, self.reviews = [], [], [], {}
        self.installs = {
            "existing-source-reader": (
                "source-reader",
                hashlib.sha256(har008.SKILLS["source-reader"].read_bytes()).hexdigest(),
            )
        }
        self.rows = {}

    def request(self, method, path, payload=None):
        """Assert frozen inputs precede transport and emulate only the explicit admitted API contract."""
        assert (self.output / "frozen-inputs.json").exists()
        if method == "GET" and path.endswith("/skills"):
            return [
                dict(
                    installation_id=identifier,
                    id=name,
                    sha256=digest,
                    workspace_id=self.workspace,
                )
                for identifier, (name, digest) in self.installs.items()
            ]
        if path.endswith("/reviews"):
            identifier = str(uuid4())
            manifest = json.loads(payload["manifest"])
            digest = hashlib.sha256(payload["manifest"].encode()).hexdigest()
            self.reviews[identifier] = (manifest["id"], digest)
            return dict(review_id=identifier, sha256=digest)
        if path.endswith("/installations") and method == "POST":
            identifier = str(uuid4())
            self.installs[identifier] = self.reviews[payload["review_id"]]
            return dict(installation_id=identifier)
        if method == "DELETE" and "/skills/installations/" in path:
            identifier = path.split("/installations/")[1].split("?")[0]
            self.removed.append(identifier)
            self.installs.pop(identifier)
            return {"removed": True}
        if path.endswith("/runs") and method == "POST":
            self.requests.append(payload)
            if len(self.requests) == self.fail_at:
                raise RuntimeError("synthetic_transport_failure")
            identifier = str(uuid4())
            case = self.cases[Path(payload["tools"][0]["arguments"]["path"]).stem]
            assert case["quote"] is None or case["quote"] not in payload["task"]
            assert not {"oracle", "value", "quote"}.intersection(payload)
            assert payload["preset"] == "fast" and payload["max_tokens"] == 512
            installation = self.installs[payload["skill"]] if payload["skill"] else None
            self.rows[identifier] = dict(
                id=identifier,
                state="succeeded",
                context=dict(
                    skill_sha256=installation[1] if installation else None,
                    included_evidence=[{"index": 0}],
                ),
                result=dict(
                    choices=[
                        dict(
                            message=dict(
                                content=json.dumps(
                                    {"value": case["value"], "quote": case["quote"]}
                                )
                            )
                        )
                    ],
                    usage={"prompt_tokens": 100, "completion_tokens": 20},
                    model="fixture-core",
                    system_fingerprint="fixture",
                ),
            )
            return self.rows[identifier]
        if method == "POST" and path.endswith("/cancel"):
            self.cancelled.append(path.split("/")[-2])
            return {}
        if method == "DELETE" and "/runs/" in path:
            self.rows.pop(path.rsplit("/", 1)[-1])
            return {"removed": True}
        raise AssertionError((method, path))


def test_corpus_is_bounded_and_oracle_lines_match_source():
    """Validate all frozen source facts and bug-line quotes without executing synthetic code."""
    cases = har008.load_cases(har008.CORPUS.read_bytes())
    assert len(cases) == 12
    assert sum(case["skill"] == "repo-review" for case in cases) == 6
    assert sum(case["value"] is None for case in cases) == 4
    LOGGER.info("test_har008_frozen_corpus_verified")


@pytest.mark.parametrize(
    "change", ["duplicate", "bad_line", "bad_quote", "path_id", "bad_skill"]
)
def test_invalid_oracle_or_scope_is_rejected(change):
    """Refuse malformed benchmark input before any model-visible request can occur."""
    document = json.loads(har008.CORPUS.read_bytes())
    if change == "duplicate":
        document["cases"][1]["id"] = document["cases"][0]["id"]
    elif change == "bad_line":
        document["cases"][6]["value"] = 1
    elif change == "bad_quote":
        document["cases"][0]["quote"] = "not in the source"
    elif change == "path_id":
        document["cases"][0]["id"] = "../escape"
    else:
        document["cases"][0]["skill"] = "shell-installer"
    with pytest.raises(ValueError):
        har008.load_cases(json.dumps(document))


@pytest.mark.parametrize(
    "content",
    [
        '```json\n{"value":96,"quote":"text"}\n```',
        '{"value":96,"value":12,"quote":"text"}',
        '{"value":96,"quote":"text","extra":1}',
        "plain prose",
    ],
)
def test_scoring_never_extracts_a_favorable_answer(content):
    """Keep first formatting failures rather than stripping fences, extras or duplicate keys."""
    assert not har008.score_answer(content, {"value": 96, "quote": "text"})["format"]


def test_exact_value_type_and_quote_are_both_required():
    """Avoid counting stringified numbers or unsupported quotes as factual success."""
    case = {"value": 96, "quote": "source"}
    assert not har008.score_answer('{"value":"96","quote":"source"}', case)["passed"]
    assert not har008.score_answer('{"value":96,"quote":"invented"}', case)["passed"]
    assert har008.score_answer('{"value":96,"quote":"source"}', case)["passed"]
    assert not har008.score_answer(
        '{"value":true,"quote":null}', {"value": 1, "quote": None}
    )["passed"]


def test_equal_scores_are_not_promoted_and_duplicate_attempts_are_invalid():
    """Separate a completed measurement from improvement and reject inflated repeated attempts."""
    cases = [{"id": "case"}]
    rows = [
        dict(case_id="case", arm=arm, score={"passed": True})
        for arm in ("baseline", "skill")
    ]
    summary = har008.aggregate(rows, cases)
    assert (
        summary["status"] == "MEASUREMENT_COMPLETE"
        and summary["promotion"] == "NOT_QUALIFIED"
    )
    assert summary["skill_only_successes"] == summary["baseline_only_successes"] == 0
    with pytest.raises(ValueError):
        har008.aggregate(rows + [rows[0]], cases)


def test_frozen_paired_run_and_temporary_grant_cleanup(tmp_path):
    """Run every pair exactly once, alternate order and preserve an existing installation."""
    output, workspace = tmp_path / "output", uuid4()
    source = tmp_path / "workspace"
    source.mkdir()
    cases = har008.load_cases(har008.CORPUS.read_bytes())
    api = FixtureAPI(cases, workspace, output)
    summary = har008.evaluate(api, workspace, source, output)
    assert summary["completed_attempts"] == 24 and summary["complete_pairs"] == 12
    assert summary["successes"] == {"baseline": 12, "skill": 12}
    assert [request["skill"] is not None for request in api.requests[:4]] == [
        False,
        True,
        True,
        False,
    ]
    assert (
        list(api.installs) == ["existing-source-reader"]
        and "existing-source-reader" not in api.removed
    )
    assert summary["cleanup_failures"] == 0 and not api.rows
    assert len(list(output.glob("*-response.json"))) == 24
    with pytest.raises(FileExistsError):
        har008.evaluate(api, workspace, source, output)


def test_failure_keeps_partial_receipts_and_never_retries(tmp_path):
    """Stop on a transport failure while retaining first scores, frozen inputs and cleanup state."""
    output, workspace = tmp_path / "output", uuid4()
    source = tmp_path / "workspace"
    source.mkdir()
    cases = har008.load_cases(har008.CORPUS.read_bytes())
    api = FixtureAPI(cases, workspace, output, fail_at=3)
    with pytest.raises(RuntimeError):
        har008.evaluate(api, workspace, source, output)
    summary = json.loads((output / "summary.json").read_text())
    assert summary["status"] == "INCOMPLETE" and summary["completed_attempts"] == 2
    assert len(api.requests) == 3 and list(api.installs) == ["existing-source-reader"]
    assert (output / "01-response.json").exists() and not (
        output / "03-response.json"
    ).exists()
