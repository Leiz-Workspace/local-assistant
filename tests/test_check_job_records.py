"""Reject malformed or widened check-job journal observations without accepting printed child success as authority."""

import base64
from copy import deepcopy
from uuid import uuid4

import pytest

from src.application.services.check_policy import execution_policy
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.check_job_records import (
    decode_record,
    encode_record,
    sha256,
    validate_journal,
    validate_observation,
)
from src.infrastructure.check_runner import NativeChecks


@pytest.fixture
def observation_context():
    """Provide server-shaped schema-only observations without launching a program or fabricating benchmark evidence."""
    identifier = uuid4()
    policy = execution_policy(0)
    core = dict(job_id=str(identifier), profile="python_unittest", policy=policy)
    value = NativeChecks(3, 4, "python_unittest", 0, identifier).observation
    return core, deepcopy(value)


def test_exact_arbitrary_output_bytes_are_validated_without_quality_inference(
    observation_context,
):
    """Require exact encoded bytes/hash/size while retaining explicit no-quality/no-source-write authority."""
    core, value = observation_context
    raw = b"\xff\x00TESTS_PASSED"
    value.update(
        started_acknowledged=True,
        outcome="exited",
        exit_code=0,
        stdout_base64=base64.b64encode(raw).decode(),
        stdout_bytes=len(raw),
        stdout_sha256=sha256(raw),
        stdout_complete=True,
        stderr_complete=True,
    )
    validate_observation(value, core)
    assert not value["quality_evaluated"]
    assert decode_record(encode_record(value)) == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("quality_evaluated", True),
        ("host_source_write_capability", True),
        ("started_acknowledged", 0),
        ("elapsed_seconds", float("nan")),
        ("elapsed_seconds", True),
        ("exit_code", True),
        ("stdout_base64", "@@invalid@@"),
        ("stdout_bytes", True),
        ("stdout_sha256", "0" * 64),
        ("outcome", "PASSED"),
        ("policy", {"network": True}),
    ],
)
def test_untrusted_or_corrupt_observations_cannot_widen_result_authority(
    observation_context, field, value
):
    """Reject forged success/permissions, ambiguous types, malformed bytes and changed resource policy."""
    core, observation = observation_context
    observation[field] = value
    with pytest.raises((ValueError, WorkspaceAccessError)):
        validate_observation(observation, core)


def test_observed_state_requires_a_real_grant_identity_and_complete_observation(
    observation_context,
):
    """Keep intent metadata separate from an acknowledged native outcome without fabricating completion on restart."""
    core, value = observation_context
    journal = dict(
        description="Controlled schema-only private journal.",
        job_id=core["job_id"],
        manifest_sha256="a" * 64,
        state="starting",
        approval_id=str(uuid4()),
        observation=None,
        error_code=None,
    )
    validate_journal(journal, core, "a" * 64)
    journal["state"] = "observed"
    with pytest.raises(WorkspaceAccessError):
        validate_journal(journal, core, "a" * 64)
    journal["observation"] = value
    validate_journal(journal, core, "a" * 64)
    journal["approval_id"] = None
    with pytest.raises(WorkspaceAccessError):
        validate_journal(journal, core, "a" * 64)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b"[]", b"\xff"])
def test_private_job_json_rejects_ambiguous_or_nonfinite_records(raw):
    """Fail malformed private record parsing with a stable code and no payload echo."""
    with pytest.raises(WorkspaceAccessError) as caught:
        decode_record(raw)
    assert caught.value.code == "checks_record_invalid"
