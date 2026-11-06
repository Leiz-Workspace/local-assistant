"""Verify malicious README instructions remain exact cited readonly evidence under controlled inference without executing source or widening model scope."""

import hashlib
import json
import logging

import pytest
from coding_injection_cases import attack_corpus
from test_workspace_explanation_service import explainer as explainer
from test_workspace_reader import source_workspace as source_workspace

logger = logging.getLogger(__name__)
ATTACKS = attack_corpus()["attacks"]


@pytest.mark.asyncio
@pytest.mark.parametrize("attack", ATTACKS, ids=[row["id"] for row in ATTACKS])
async def test_actual_malicious_readme_is_cited_data_without_host_or_model_authority(
    explainer, source_workspace, caplog, attack
):
    """Read a real README containing a policy/role/owner/model/grant attack and preserve source/canary bytes plus exact native citation provenance."""
    _, spec, root, _ = source_workspace
    source = root / "README.md"
    raw = ("Cedar uses port 7443.\n" + attack["text"] + "\n").encode()
    source.write_bytes(raw)
    hidden, outside = (
        (root / ".env").read_bytes(),
        (root.parent / "outside.txt").read_bytes(),
    )
    with caplog.at_level(logging.INFO):
        async with explainer.operation(
            spec.owner_id,
            spec.workspace_id,
            "Which port?",
            [dict(path="README.md", start_line=1, end_line=2)],
        ) as evidence:
            await explainer.validate(evidence)
            citation = evidence.payload["citations"][0]
            assert (
                citation["path"] == "README.md"
                and citation["source_sha256"] == hashlib.sha256(raw).hexdigest()
            )
            assert citation["quote"] == "Cedar uses port 7443."
    call = explainer.inference.calls[0]
    assert len(explainer.inference.calls) == 1 and call["profile"] == "core"
    assert [message["role"] for message in call["messages"]] == ["system", "user"]
    selected = json.loads(call["messages"][1]["content"])["sources"]
    assert any(row["text"] == attack["text"] for row in selected)
    assert source.read_bytes() == raw and (root / ".env").read_bytes() == hidden
    assert (root.parent / "outside.txt").read_bytes() == outside
    assert not explainer.operations and not explainer.workspace.operations
    assert attack["text"].split()[0] not in caplog.text
    logger.info(
        "d45_readonly_readme_authority_boundary_verified case_id=%s", attack["id"]
    )
