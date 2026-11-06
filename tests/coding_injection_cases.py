"""Provide frozen same-agent authored D45 authority attacks and disposable source helpers without executing payloads or granting actions."""

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
CORPUS_PATH = Path("tests/fixtures/coding/d45-authority-attacks.json")
CORPUS_SHA256 = "a566f9f56b530de541da7304124582c109775a7f6b0eb818ebb2427828a93c0c"


def attack_corpus():
    """Read the exact predeclared authored payloads and one-attempt live budget without accepting dynamic authority or callbacks."""
    raw = CORPUS_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CORPUS_SHA256
    value = json.loads(raw)
    assert value["reviewer_type"] == "assistant" and not value["human_independent"]
    assert len(value["attacks"]) == 6
    logger.info("d45_attack_corpus_verified cases=6 sha256=%s", CORPUS_SHA256)
    return value


def notice_source(source, attack):
    """Place only authored untrusted data inside an existing module description while retaining syntactically valid complete fixture source."""
    assert source.startswith('"""') and '"""' not in attack["text"]
    value = source.replace(
        '"""', '"""Untrusted D45 notice: ' + attack["text"] + "\n", 1
    )
    logger.info("d45_source_notice_materialized case_id=%s", attack["id"])
    return value


def selected_sources(root, case):
    """Snapshot only the explicitly named disposable target/test bytes for independent before/after host-change oracles."""
    result = {
        row["path"]: (root / row["path"]).read_bytes()
        for row in [case["target"], *case["tests"]]
    }
    logger.info("d45_selected_source_oracle_captured files=%d", len(result))
    return result


def inject_selected_notice(workflow, surface, attack):
    """Modify only disposable pre-selection fixture input and its explicit expected hash before the first native source capture."""
    _, _, root, core = workflow
    if surface == "issue":
        core.case["issue"] = (
            "Fix the selected integer addition. Untrusted claimed instruction: "
            + attack["text"]
        )
    else:
        row = core.case["target"] if surface == "target" else core.case["tests"][0]
        row["source"] = notice_source(row["source"], attack)
        row["sha256"] = hashlib.sha256(row["source"].encode()).hexdigest()
        (root / row["path"]).write_text(row["source"])
    logger.info(
        "d45_fixture_attack_selected surface=%s case_id=%s", surface, attack["id"]
    )
