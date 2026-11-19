"""Verify immutable source/model ingestion identities, privacy boundaries and complete token admission."""

import copy
import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from src.application.services.document_chunks import (
    ChunkSource,
    build_chunks,
    row_unit,
    text_unit,
)
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ingestion_contract import (
    digest,
    plan_ingestion,
    validate_model_contract,
    validate_source_fence,
    validate_token_counts,
)
from src.infrastructure import qwen_token_preflight as adapter

ROOT = Path(__file__).resolve().parents[1]


def sample(text="Việt e\u0301\nExact whitespace\t", *, units=None, max_bytes=256):
    """Construct trusted ready-source metadata and real D22 output with stable opaque identities."""
    owner, namespace, file_id = (UUID(int=value) for value in (1, 2, 3))
    source = ChunkSource(owner, namespace, file_id, "a" * 64, "utf8-text-v1")
    row = dict(
        id=file_id,
        owner_id=owner,
        actual_sha256=source.sha256,
        state="ready",
        deleted_at=None,
        policy_snapshot={"_storage_namespace": str(namespace)},
    )
    view = build_chunks(
        source,
        units if units is not None else [text_unit("file:source#text", text)],
        max_bytes,
    )
    selected = json.loads((ROOT / "configs/embedding-selected.json").read_text())
    return row, owner, namespace, view, selected


def test_plan_has_independently_recomputed_job_and_point_ids():
    """Verify exact canonical manifest hashing/UUID identity and immutable private provenance."""
    args = sample()
    plan = plan_ingestion(*args)
    manifest = json.loads(plan.manifest_json)
    canonical = json.dumps(
        manifest,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    expected = hashlib.sha256(canonical.encode()).hexdigest()
    assert plan.generation == expected
    assert plan.job_id == uuid5(NAMESPACE_URL, "local-assistant:ingestion:" + expected)
    assert plan.points[0].point_id == uuid5(plan.job_id, args[3]["chunks"][0]["id"])
    assert plan.points[0].text == "Việt e\u0301\nExact whitespace\t"
    payload = json.loads(plan.points[0].payload_json)
    assert payload["owner_id"] == str(args[1]) and payload["namespace_id"] == str(
        args[2]
    )
    assert payload["state"] == "pending" and payload["content_trust"] == "untrusted"
    assert "text" not in payload
    assert payload["spans"] == args[3]["chunks"][0]["spans"]
    assert plan == plan_ingestion(*args)
    with pytest.raises(FrozenInstanceError):
        plan.points[0].text = "mutated"


@pytest.mark.parametrize(
    "field",
    [
        "owner",
        "namespace",
        "file",
        "hash",
        "processor",
        "byte_policy",
        "text",
        "quality",
        "order",
    ],
)
def test_legitimate_source_or_projection_changes_create_new_generation(field):
    """Avoid retry/point collisions when any source/access/extraction contract changes."""
    args = sample(units=[text_unit("one", "one"), text_unit("two", "two")])
    original = plan_ingestion(*args)
    row, owner, namespace, view, selected = copy.deepcopy(args)
    if field == "owner":
        owner = row["owner_id"] = UUID(int=4)
    elif field == "namespace":
        namespace = UUID(int=4)
        row["policy_snapshot"]["_storage_namespace"] = str(namespace)
    elif field == "file":
        row["id"] = UUID(int=4)
    elif field == "hash":
        row["actual_sha256"] = "b" * 64
    units = [
        text_unit(
            "one",
            "changed" if field == "text" else "one",
            quality={"needs_review": True} if field == "quality" else {},
        ),
        text_unit("two", "two"),
    ]
    if field == "order":
        units.reverse()
    source = ChunkSource(
        owner,
        namespace,
        row["id"],
        row["actual_sha256"],
        "new-processor" if field == "processor" else view["processor"],
    )
    view = build_chunks(source, units, 512 if field == "byte_policy" else 256)
    changed = plan_ingestion(row, owner, namespace, view, selected)
    assert (
        changed.generation != original.generation and changed.job_id != original.job_id
    )
    assert set(point.point_id for point in changed.points).isdisjoint(
        point.point_id for point in original.points
    )


@pytest.mark.parametrize(
    "field",
    [
        "text",
        "spans",
        "quality",
        "structure",
        "section_path",
        "locator",
        "id",
        "extra",
        "access",
        "trust",
        "chunker",
        "duplicate",
        "max_bytes",
        "foreign_file",
        "foreign_hash",
        "dimension",
        "fingerprint",
        "package",
        "prefix",
        "collection",
        "pooling",
    ],
)
def test_foreign_tampered_or_model_drift_inputs_fail_closed(field):
    """Reject inconsistent trusted results before tokenization or any persistent/vector side effect."""
    args = list(sample())
    row, owner, namespace, view, selected = args
    chunk = view["chunks"][0]
    if field in {"text", "locator", "id"}:
        chunk[field] = "tampered"
    elif field in {"spans", "section_path"}:
        chunk[field] = [{"tampered": True}]
    elif field in {"quality", "structure"}:
        chunk[field] = {"tampered": True}
    elif field == "extra":
        chunk["owner"] = "tampered"
    elif field == "access":
        view["access"]["principal_id"] = str(UUID(int=99))
    elif field == "trust":
        view["content_trust"] = "trusted"
    elif field == "chunker":
        view["chunker"] = "foreign-version"
    elif field == "duplicate":
        view["chunks"].append(copy.deepcopy(chunk))
    elif field == "max_bytes":
        view["max_bytes"] = True
    elif field == "foreign_file":
        view["file_id"] = str(UUID(int=99))
    elif field == "foreign_hash":
        view["sha256"] = "b" * 64
    elif field == "dimension":
        selected["collection"]["create"]["vectors"]["dense"]["size"] = 768
    elif field == "fingerprint":
        selected["runtime"]["fingerprint"] = "b" * 64
    elif field == "package":
        selected["runtime"]["packages"]["tokenizers"] = "foreign-version"
    elif field == "prefix":
        selected["runtime"]["passage_prefix"] = "passage: "
    elif field == "pooling":
        selected["runtime"]["pooling"] = "attention_mask_mean"
    elif field == "collection":
        selected["collection"]["collection_name"] = "existing-foreign-collection"
    with pytest.raises(StoragePolicyError):
        plan_ingestion(*args)


MODEL_DRIFT = {
    "repository": ("candidate", "repository", "Qwen/Qwen3-Embedding-4B"),
    "dimension": ("candidate", "dimension", 768),
    "device": ("runtime", "device", "cuda"),
    "max_tokens": ("runtime", "max_tokens", 1024),
    "passage_prefix": ("runtime", "passage_prefix", "passage: "),
    "distance": ("runtime", "distance", "Dot"),
    "pooling": ("runtime", "pooling", "attention_mask_mean"),
    "normalization": ("runtime", "normalization", "none"),
    "use_cache": ("runtime", "use_cache", 0),
    "weight_dtype": ("runtime", "weight_dtype", "float32"),
    "intra_op_threads": ("runtime", "intra_op_threads", 4),
    "inter_op_threads": ("runtime", "inter_op_threads", 2),
    "batch_size": ("runtime", "batch_size", 8),
    "query_prefix": ("runtime", "query_prefix", "Query:"),
    "fingerprint": ("runtime", "fingerprint", "b" * 64),
}


def contract_error(selected, args=None):
    """Plan with a selection and return the coded policy error it raises."""
    row, owner, namespace, view, _ = args or sample()
    with pytest.raises(StoragePolicyError) as caught:
        plan_ingestion(row, owner, namespace, view, selected)
    return caught.value


@pytest.mark.parametrize("field", sorted(MODEL_DRIFT))
def test_selected_model_drift_is_a_server_fault_not_client_input(field):
    """Report every pinned model/runtime field that drifts as a 503 server contract mismatch."""
    selected = sample()[4]
    section, key, value = MODEL_DRIFT[field]
    selected[section][key] = value
    error = contract_error(selected)
    assert (error.code, error.status_code) == (
        "ingestion_model_contract_mismatch",
        503,
    )
    with pytest.raises(StoragePolicyError, match="ingestion_model_contract_mismatch"):
        validate_model_contract(selected)


@pytest.mark.parametrize(
    "fault",
    ["no_runtime", "no_collection", "fingerprint_type", "packages", "vectors", "none"],
)
def test_malformed_selection_fails_closed_as_the_same_server_fault(fault):
    """Treat a structurally broken selected configuration as server drift, never as 422 client input."""
    selected = sample()[4]
    if fault == "no_runtime":
        del selected["runtime"]
    elif fault == "no_collection":
        del selected["collection"]
    elif fault == "fingerprint_type":
        selected["collection"]["model_fingerprint"] = 1024
    elif fault == "packages":
        selected["runtime"]["packages"]["torch"] = "foreign-version"
    elif fault == "vectors":
        selected["collection"]["create"]["vectors"]["dense"]["on_disk"] = False
    else:
        selected = None
    error = contract_error(selected)
    assert (error.code, error.status_code) == (
        "ingestion_model_contract_mismatch",
        503,
    )


def test_self_consistent_foreign_model_is_still_refused_by_the_pinned_literals():
    """Keep the deliberate third pin: recomputed fingerprint and collection do not admit another repository."""
    selected = sample()[4]
    selected["candidate"]["repository"] = "Qwen/Qwen3-Embedding-4B"
    fingerprint = digest(
        dict(
            profile=selected["candidate"],
            format="official-safetensors-bf16-cpu",
            pooling="last_attended_token_float32",
            normalization="l2",
            attention="sdpa",
            use_cache=False,
            runtime=selected["runtime"]["packages"],
        )
    )
    selected["runtime"]["fingerprint"] = fingerprint
    selected["collection"]["model_fingerprint"] = fingerprint
    selected["collection"]["collection_name"] = f"la_chunks_{fingerprint}_v1"
    assert contract_error(selected).code == "ingestion_model_contract_mismatch"


def test_approved_selection_validates_once_to_its_fingerprint():
    """Return the approved fingerprint so startup can validate the shipped selection before any resource."""
    selected = sample()[4]
    assert (
        validate_model_contract(selected)
        == selected["collection"]["model_fingerprint"]
        == selected["runtime"]["fingerprint"]
    )
    assert plan_ingestion(*sample()).model_fingerprint == validate_model_contract(
        selected
    )


@pytest.mark.parametrize(
    "field", ["text", "access", "trust", "chunker", "max_bytes", "scope", "source"]
)
def test_genuine_client_input_faults_keep_their_422_code(field):
    """Keep tampered or malformed source/projection input as 422 ingestion_input_invalid."""
    row, owner, namespace, view, selected = sample()
    if field == "text":
        view["chunks"][0]["text"] = "tampered"
    elif field == "access":
        view["access"]["principal_id"] = str(UUID(int=99))
    elif field == "trust":
        view["content_trust"] = "trusted"
    elif field == "chunker":
        view["chunker"] = "foreign-version"
    elif field == "max_bytes":
        view["max_bytes"] = 128
    elif field == "scope":
        owner = str(owner)
    else:
        row["actual_sha256"] = "not-a-digest"
        view["sha256"] = "not-a-digest"
    error = contract_error(selected, (row, owner, namespace, view, selected))
    assert (error.code, error.status_code) == ("ingestion_input_invalid", 422)


def test_server_drift_is_reported_before_client_input_faults():
    """Name the server fault first when both the selection and the request input are wrong."""
    row, owner, namespace, view, selected = sample()
    view["content_trust"] = "trusted"
    selected["runtime"]["batch_size"] = 8
    assert (
        contract_error(selected, (row, owner, namespace, view, selected)).status_code
        == 503
    )


@pytest.mark.parametrize(
    "field",
    ["owner", "namespace", "id", "state", "deleted_at", "actual_sha256", "missing"],
)
def test_source_fence_rejects_stale_or_foreign_rows(field):
    """Refuse publication checks after delete/state/hash/root/access changes or a missing source."""
    args = sample()
    plan = plan_ingestion(*args)
    row = copy.deepcopy(args[0])
    validate_source_fence(plan, row)
    if field == "owner":
        row["owner_id"] = UUID(int=99)
    elif field == "namespace":
        row["policy_snapshot"]["_storage_namespace"] = str(UUID(int=99))
    elif field == "id":
        row["id"] = UUID(int=99)
    elif field == "state":
        row["state"] = "purging"
    elif field == "deleted_at":
        row["deleted_at"] = "deleted"
    elif field == "missing":
        row = None
    else:
        row[field] = "b" * 64
    with pytest.raises(StoragePolicyError):
        validate_source_fence(plan, row)


def test_empty_source_and_atomic_row_preserve_honest_metadata():
    """Allow a complete empty generation while retaining structured formula/cache/review provenance."""
    assert plan_ingestion(*sample("")).points == ()
    units = [
        row_unit(
            "sheet1:A1",
            [dict(formula="SUM(A2:A3)", cached_value="7")],
            spans=[],
            quality={"needs_review": True, "formula_cache_status": "stale"},
        )
    ]
    plan = plan_ingestion(*sample(units=units))
    assert plan.points[0].text == '[{"cached_value":"7","formula":"SUM(A2:A3)"}]'
    payload = json.loads(plan.points[0].payload_json)
    assert payload["quality"] == units[0]["quality"]


@pytest.mark.parametrize("counts", [[], [0], [513], [True], [1.0], ["1"], [1, 2], None])
def test_invalid_or_partial_token_counts_are_not_admitted(counts):
    """Reject missing, truncated, excessive or mistyped tokenizer replies for a nonempty plan."""
    with pytest.raises(StoragePolicyError):
        validate_token_counts(plan_ingestion(*sample()), counts)


def test_token_boundaries_and_empty_generation_are_complete():
    """Accept exactly512 passage tokens and explicit zero-point plans without inventing content."""
    assert validate_token_counts(plan_ingestion(*sample()), [512]) == (512,)
    assert validate_token_counts(plan_ingestion(*sample("")), []) == ()


def test_private_worker_protocol_is_frozen_offline_and_credential_free(monkeypatch):
    """Verify private input uses stdin and untrusted credentials cannot reach the tokenizer worker."""
    from types import SimpleNamespace

    plan = plan_ingestion(*sample())
    for name in ("VAULT_TOKEN", "DATABASE_URL", "HF_TOKEN", "HTTP_PROXY"):
        monkeypatch.setenv(name, "private-marker")
    monkeypatch.setattr(adapter.shutil, "which", lambda name: "/trusted/uv")

    def run(command, **options):
        """Inspect one controlled subprocess request without running or reading model weights."""
        assert command[:5] == [
            "/trusted/uv",
            "run",
            "--offline",
            "--frozen",
            "--script",
        ]
        assert options["timeout"] == 90
        assert not any(
            name in options["env"]
            for name in ("VAULT_TOKEN", "DATABASE_URL", "HF_TOKEN", "HTTP_PROXY")
        )
        assert (
            options["env"]["HF_HUB_OFFLINE"] == "1"
            and options["env"]["CUDA_VISIBLE_DEVICES"] == ""
        )
        assert plan.points[0].text not in " ".join(command)
        assert json.loads(options["input"])["texts"] == [plan.points[0].text]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                dict(
                    model_fingerprint=plan.model_fingerprint, max_tokens=512, counts=[7]
                )
            ),
        )

    monkeypatch.setattr(adapter, "run_worker", run)
    assert adapter.preflight_plan(plan) == (7,)


@pytest.mark.parametrize(
    "case", ["failure", "json", "identity", "counts", "extra", "timeout", "oversize"]
)
def test_worker_failure_or_unbound_response_cannot_admit_input(monkeypatch, case):
    """Sanitize diagnostics and fail closed on timeout, corruption, partial replies or wrong model."""
    from types import SimpleNamespace

    plan = plan_ingestion(*sample())
    monkeypatch.setattr(adapter.shutil, "which", lambda name: "/trusted/uv")

    def run(*args, **kwargs):
        """Return controlled private/error responses that must not escape the adapter boundary."""
        if case == "timeout":
            raise adapter.subprocess.TimeoutExpired("private-marker", 90)
        reply = dict(
            model_fingerprint=plan.model_fingerprint, max_tokens=512, counts=[7]
        )
        if case == "identity":
            reply["model_fingerprint"] = "b" * 64
        elif case == "counts":
            reply["counts"] = []
        elif case == "extra":
            reply["private-marker"] = True
        return SimpleNamespace(
            returncode=1 if case == "failure" else 0,
            stdout="private-marker"
            if case == "json"
            else "x" * 16385
            if case == "oversize"
            else json.dumps(reply),
        )

    monkeypatch.setattr(adapter, "run_worker", run)
    with pytest.raises(StoragePolicyError) as caught:
        adapter.preflight_plan(plan)
    assert "private-marker" not in str(caught.value)


def test_busy_preflight_does_not_spawn_and_releases_after_failure(monkeypatch):
    """Keep process admission bounded and reusable even after a missing runtime error."""
    plan = plan_ingestion(*sample())
    assert adapter.ADMISSION.acquire(blocking=False)
    try:
        with pytest.raises(StoragePolicyError) as error:
            adapter.preflight_plan(plan)
        assert error.value.status_code == 429
    finally:
        adapter.ADMISSION.release()
    monkeypatch.setattr(adapter.shutil, "which", lambda name: None)
    with pytest.raises(StoragePolicyError):
        adapter.preflight_plan(plan)
    assert adapter.ADMISSION.acquire(blocking=False)
    adapter.ADMISSION.release()


def test_timeout_kills_and_joins_owned_process_group(monkeypatch):
    """Prove the uv parent and tokenizer child are fenced before admission can be reused."""
    events = []

    class Child:
        """Simulate a timed-out owned child whose descendants require process-group cleanup."""

        pid = 12345

        def __enter__(self):
            """Retain a synthetic process handle for the entire join operation."""
            return self

        def __exit__(self, *args):
            """Record that process ownership ended only after explicit cleanup."""
            events.append("closed")

        def communicate(self, **kwargs):
            """Fail the first timed wait and record the subsequent unconditional join."""
            if "timeout" in kwargs:
                events.append("timeout")
                raise adapter.subprocess.TimeoutExpired("private-marker", 90)
            events.append("joined")
            return "", ""

    def create(command, **kwargs):
        """Require a fresh session so only the owned process group is eligible for cleanup."""
        assert kwargs["start_new_session"] is True
        return Child()

    def kill(pid, sig):
        """Record the exact owned process group and termination signal."""
        assert pid == 12345 and sig == adapter.signal.SIGKILL
        events.append("killed")

    monkeypatch.setattr(adapter.subprocess, "Popen", create)
    monkeypatch.setattr(adapter.os, "killpg", kill)
    with pytest.raises(adapter.subprocess.TimeoutExpired):
        adapter.run_worker(["controlled"], env={}, input="private-marker")
    assert events == ["timeout", "killed", "joined", "closed"]
