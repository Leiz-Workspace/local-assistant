"""Verify complete Qwen encoding, private vector payloads and owned generation-only Qdrant operations."""

import asyncio
import copy
import json
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from test_ingestion_contract import sample

from src.application.services.document_chunks import row_unit
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ingestion_contract import plan_ingestion
from src.infrastructure import qwen_embedding as encoder
from src.infrastructure.qdrant_ingestion import (
    QdrantIngestion,
    generation_scope,
    vector_payload,
)


def encoded(plan):
    """Provide independent exact unit-axis vectors with complete bounded token counts."""
    return encoder.EncodedBatch(
        plan.model_fingerprint,
        tuple(3 for _ in plan.points),
        tuple(tuple([1.0] + [0.0] * 1023) for _ in plan.points),
    )


def reply(plan):
    """Build a complete worker reply without executing a model or downloading assets."""
    batch = encoded(plan)
    return dict(
        model_fingerprint=batch.model_fingerprint,
        counts=list(batch.counts),
        vectors=[list(row) for row in batch.vectors],
    )


@pytest.mark.parametrize(
    "case",
    [
        "fingerprint",
        "count",
        "dimension",
        "nan",
        "infinity",
        "zero",
        "norm",
        "string",
        "bool",
        "missing",
        "extra",
        "partial",
    ],
)
def test_invalid_or_mixed_encodings_fail_closed(case):
    """Reject foreign, malformed, nonfinite, incomplete or non-unit vectors before any write."""
    plan = plan_ingestion(*sample())
    data = reply(plan)
    if case == "fingerprint":
        data["model_fingerprint"] = "b" * 64
    elif case == "count":
        data["counts"] = []
    elif case == "dimension":
        data["vectors"][0].pop()
    elif case in {"nan", "infinity", "zero", "norm", "string", "bool"}:
        data["vectors"][0][0] = {
            "nan": float("nan"),
            "infinity": float("inf"),
            "zero": 0,
            "norm": 2,
            "string": "1",
            "bool": True,
        }[case]
    elif case == "missing":
        data.pop("vectors")
    elif case == "extra":
        data["untrusted"] = True
    else:
        data["vectors"] = []
    with pytest.raises(StoragePolicyError):
        encoder.validate_encoding(plan, data)


def test_complete_and_empty_encoding_preserves_full_point_count():
    """Accept complete unit vectors and honest zero-point generations without fabricating a vector."""
    plan = plan_ingestion(*sample())
    assert encoder.validate_encoding(plan, reply(plan)) == encoded(plan)
    empty = plan_ingestion(*sample(""))
    assert (
        encoder.validate_encoding(
            empty,
            dict(model_fingerprint=empty.model_fingerprint, counts=[], vectors=[]),
        ).vectors
        == ()
    )


def test_vector_payload_does_not_copy_private_rows_or_source_text():
    """Hash source/provenance while keeping structured row text and uncertainty out of raw vector payload."""
    units = [
        row_unit(
            "sheet:one",
            [dict(value="private-table-marker")],
            spans=[],
            quality={"needs_review": True},
        )
    ]
    plan = plan_ingestion(*sample(units=units))
    payload = vector_payload(plan.points[0])
    assert "private-table-marker" not in json.dumps(payload)
    assert "structure" not in payload and "text" not in payload
    assert payload["quality_present"] and payload["content_trust"] == "untrusted"
    assert (
        len(payload["chunk_content_sha256"]) == len(payload["provenance_sha256"]) == 64
    )
    scope = {
        item["key"]: item["match"]["value"] for item in generation_scope(plan)["must"]
    }
    assert set(scope) == {
        "owner_id",
        "namespace_id",
        "file_id",
        "source_sha256",
        "model_fingerprint",
        "index_generation",
    }


class VectorServer:
    """Simulate installed-server metadata, deterministic points and generation filters independently of the adapter."""

    def __init__(self, selection):
        """Track owned schema, point storage, requests and controlled API corruption."""
        self.selection = selection
        self.collection = None
        self.points = {}
        self.calls = []
        self.fail_ack = False
        self.corrupt = False
        self.delete_noop = False

    def matches(self, point, scope):
        """Apply every trusted filter conjunct instead of matching only file or generation identity."""
        return all(
            point["payload"].get(entry["key"]) == entry["match"]["value"]
            for entry in scope["must"]
        )

    def handle(self, request):
        """Implement the narrow REST contract without leaking a test credential into responses."""
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body))
        if path.endswith("/index"):
            schema = body["field_schema"]
            self.collection["payload_schema"][body["field_name"]] = dict(
                data_type=schema if isinstance(schema, str) else schema["type"],
                **({} if isinstance(schema, str) else dict(params=schema)),
            )
            return httpx.Response(200, json=dict(result=True))
        if "/points" not in path:
            if request.method == "GET":
                return (
                    httpx.Response(404, json=dict(result=None))
                    if self.collection is None
                    else httpx.Response(200, json=dict(result=self.collection))
                )
            assert request.method == "PUT"
            assert self.collection is None
            self.collection = dict(
                config=dict(
                    metadata=body["metadata"], params=dict(vectors=body["vectors"])
                ),
                payload_schema={},
            )
            return httpx.Response(200, json=dict(result=True))
        if request.method == "PUT":
            assert (
                request.url.params["wait"] == "true"
                and request.url.params["ordering"] == "strong"
            )
            for point in body["points"]:
                self.points[point["id"]] = copy.deepcopy(point)
            return httpx.Response(
                200,
                json=dict(
                    result=dict(status="acknowledged" if self.fail_ack else "completed")
                ),
            )
        if path.endswith("/delete"):
            if not self.delete_noop:
                self.points = {
                    key: value
                    for key, value in self.points.items()
                    if not self.matches(value, body["filter"])
                }
            return httpx.Response(200, json=dict(result=dict(status="completed")))
        values = [
            copy.deepcopy(point)
            for point in self.points.values()
            if self.matches(point, body["filter"])
        ]
        if path.endswith("/count"):
            return httpx.Response(200, json=dict(result=dict(count=len(values))))
        assert path.endswith("/scroll")
        if self.corrupt and values:
            values[0]["payload"]["owner_id"] = str(uuid4())
        return httpx.Response(
            200, json=dict(result=dict(points=values, next_page_offset=None))
        )


@pytest.fixture
def vector_context():
    """Build a scoped plan, independent server and injectable async transport without live-service calls."""
    args = sample()
    plan = plan_ingestion(*args)
    selection = args[-1]
    server = VectorServer(selection)
    client = httpx.AsyncClient(
        base_url="http://127.0.0.1:6333", transport=httpx.MockTransport(server.handle)
    )
    adapter = QdrantIngestion(
        selection, uuid4(), client=client, physical_name="la_d25_probe_" + uuid4().hex
    )
    return args, plan, server, client, adapter


@pytest.mark.asyncio
async def test_owned_retry_upsert_and_exact_generation_delete_preserve_other_points(
    vector_context,
):
    """Verify deterministic retries and scoped deletion without mutating a foreign generation."""
    args, plan, server, client, adapter = vector_context
    async with client:
        await adapter.ensure()
        assert await adapter.upsert(plan, encoded(plan)) == [
            point.point_id for point in plan.points
        ]
        await adapter.upsert(plan, encoded(plan))
        assert len(server.points) == 1
        foreign = copy.deepcopy(next(iter(server.points.values())))
        foreign["id"] = str(uuid4())
        foreign["payload"]["index_generation"] = "b" * 64
        server.points[foreign["id"]] = foreign
        await adapter.delete(plan)
        await adapter.delete(plan)
        assert list(server.points) == [foreign["id"]]
        assert not any(method == "DELETE" for method, path, body in server.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["owner", "model", "schema", "metadata_missing"])
async def test_collection_collision_never_mutates_or_adopts_foreign_state(
    vector_context, case
):
    """Reject incompatible preexisting collections before schema/index/vector writes."""
    args, plan, server, client, adapter = vector_context
    async with client:
        await adapter.ensure()
        server.calls.clear()
        if case == "owner":
            server.collection["config"]["metadata"]["owner_id"] = str(uuid4())
        elif case == "model":
            server.collection["config"]["metadata"]["model_fingerprint"] = "b" * 64
        elif case == "schema":
            server.collection["config"]["params"]["vectors"]["dense"]["size"] = 768
        else:
            server.collection["config"].pop("metadata")
        with pytest.raises(StoragePolicyError, match="not_owned"):
            await adapter.ensure()
        assert all(method == "GET" for method, path, body in server.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["ack", "payload", "delete"])
async def test_incomplete_ack_corrupt_verification_and_nonempty_delete_fail(
    vector_context, case
):
    """Require actual stored identity and zero scoped points rather than trusting successful HTTP alone."""
    args, plan, server, client, adapter = vector_context
    async with client:
        await adapter.ensure()
        if case == "ack":
            server.fail_ack = True
        if case == "payload":
            server.corrupt = True
        if case in {"ack", "payload"}:
            with pytest.raises(StoragePolicyError):
                await adapter.upsert(plan, encoded(plan))
        else:
            await adapter.upsert(plan, encoded(plan))
            server.delete_noop = True
            with pytest.raises(StoragePolicyError, match="delete_incomplete"):
                await adapter.delete(plan)


@pytest.mark.asyncio
async def test_parent_encoder_protocol_is_private_frozen_and_credential_free(
    monkeypatch,
):
    """Send exact text only through stdin to an offline fresh process group and validate its reply."""
    plan = plan_ingestion(*sample())
    for key in ("VAULT_TOKEN", "DATABASE_URL", "HF_TOKEN", "HTTP_PROXY"):
        monkeypatch.setenv(key, "private-marker")
    monkeypatch.setattr(encoder.shutil, "which", lambda value: "/trusted/uv")

    class Child:
        """Return one complete controlled worker encoding without starting a process."""

        pid = 12345
        returncode = None

        async def communicate(self, body):
            """Verify private body and complete the synthetic process atomically."""
            assert json.loads(body)["texts"] == [plan.points[0].text]
            self.returncode = 0
            return json.dumps(reply(plan)).encode(), b""

    async def launch(*args, **kwargs):
        """Inspect launch constraints and ensure secrets never reach the model process."""
        assert args[:5] == ("/trusted/uv", "run", "--offline", "--frozen", "--script")
        assert kwargs["start_new_session"] is True
        assert (
            kwargs["env"]["HF_HUB_OFFLINE"] == "1"
            and kwargs["env"]["CUDA_VISIBLE_DEVICES"] == ""
        )
        assert not any(
            key in kwargs["env"]
            for key in ("VAULT_TOKEN", "DATABASE_URL", "HF_TOKEN", "HTTP_PROXY")
        )
        return Child()

    monkeypatch.setattr(encoder.asyncio, "create_subprocess_exec", launch)
    assert await encoder.QwenEmbedding().encode(plan) == encoded(plan)


@pytest.mark.asyncio
async def test_cancellation_kills_and_joins_child_before_releasing_admission(
    monkeypatch,
):
    """Fence model-process lifetime before a cancelled caller can admit another job."""
    plan = plan_ingestion(*sample())
    started, terminated = asyncio.Event(), asyncio.Event()
    events = []
    monkeypatch.setattr(encoder.shutil, "which", lambda value: "/trusted/uv")

    class Child:
        """Hold controlled pipe work until process-group termination is requested."""

        pid = 12345
        returncode = None

        async def communicate(self, body=None):
            """Wait for termination and record that the process was joined."""
            started.set()
            await terminated.wait()
            self.returncode = -9
            events.append("joined")
            return b"", b""

    async def launch(*args, **kwargs):
        """Return the controlled owned process."""
        return Child()

    def kill(pid, sig):
        """Terminate only the expected process group before its pipe join."""
        assert pid == 12345 and sig == encoder.signal.SIGKILL
        events.append("killed")
        terminated.set()

    monkeypatch.setattr(encoder.asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr(encoder.os, "killpg", kill)
    adapter = encoder.QwenEmbedding()
    work = asyncio.create_task(adapter.encode(plan))
    await started.wait()
    with pytest.raises(StoragePolicyError, match="encoder_busy"):
        await adapter.encode(plan)
    work.cancel()
    with pytest.raises(asyncio.CancelledError):
        await work
    assert events == ["killed", "joined"] and not adapter.admission.locked()


@pytest.mark.asyncio
async def test_forged_scope_point_cannot_write(vector_context):
    """Reject altered point identity before invoking a Qdrant write."""
    args, plan, server, client, adapter = vector_context
    async with client:
        await adapter.ensure()
        server.calls.clear()
        changed = replace(plan, points=(replace(plan.points[0], point_id=uuid4()),))
        with pytest.raises(StoragePolicyError, match="scope_invalid"):
            await adapter.upsert(changed, encoded(changed))
        assert server.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["json", "status", "oversize", "result", "redirect"])
async def test_server_protocol_errors_do_not_expose_body_or_key(case, caplog):
    """Reject malformed or hostile REST responses with fixed diagnostics and bounded reply bytes."""
    args = sample()
    key = "private-key-marker"

    def handle(request):
        """Return a controlled malformed response without forwarding to any live endpoint."""
        if case == "json":
            return httpx.Response(200, text="private-body-marker")
        if case == "status":
            return httpx.Response(500, text="private-body-marker")
        if case == "oversize":
            return httpx.Response(200, content=b"x" * (2 * 1024**2 + 1))
        if case == "result":
            return httpx.Response(200, json=dict(secret="private-body-marker"))
        return httpx.Response(
            302, headers={"location": "http://foreign.invalid/private-body-marker"}
        )

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:6333",
        headers={"api-key": key},
        transport=httpx.MockTransport(handle),
    ) as client:
        adapter = QdrantIngestion(args[-1], uuid4(), client=client)
        with pytest.raises(StoragePolicyError) as error:
            await adapter.request("GET", adapter.path)
        assert "private-body-marker" not in str(error.value) and key not in caplog.text


@pytest.mark.asyncio
async def test_lost_create_acknowledgement_resumes_only_matching_owner(vector_context):
    """Reconcile an ambiguous creation through persisted ownership metadata without adopting a collision."""
    args, plan, server, client, adapter = vector_context
    original = server.handle
    failed = False

    def lost_ack(request):
        """Apply one owned creation but hide its acknowledgement to simulate a real transport gap."""
        nonlocal failed
        result = original(request)
        if (
            request.method == "PUT"
            and "/points" not in request.url.path
            and not request.url.path.endswith("/index")
            and not failed
        ):
            failed = True
            raise httpx.ReadTimeout("private-body-marker")
        return result

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:6333", transport=httpx.MockTransport(lost_ack)
    ) as transport:
        adapter.client = transport
        with pytest.raises(StoragePolicyError):
            await adapter.ensure()
        await adapter.ensure()
        assert (
            sum(
                method == "PUT" and not path.endswith("/index")
                for method, path, body in server.calls
            )
            == 1
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_read_verification_rejects_foreign_model_before_request(vector_context):
    """Bind direct verification to the encoded model rather than only trusting identical vector numbers."""
    args, plan, server, client, adapter = vector_context
    async with client:
        with pytest.raises(StoragePolicyError):
            await adapter.verify(
                plan, replace(encoded(plan), model_fingerprint="b" * 64)
            )
        assert server.calls == []


@pytest.mark.asyncio
async def test_pipe_failure_is_sanitized_and_admission_reusable(monkeypatch):
    """Avoid replacing a safe worker failure with a private pipe exception during final cleanup."""
    plan = plan_ingestion(*sample())
    monkeypatch.setattr(encoder.shutil, "which", lambda value: "/trusted/uv")

    class Child:
        """Expose a completed process whose private pipe result failed."""

        pid = 12345
        returncode = 1

        async def communicate(self, body):
            """Simulate a transport failure without emitting any document or credential."""
            raise OSError("private-pipe-marker")

    async def launch(*args, **kwargs):
        """Return only the controlled failed process."""
        return Child()

    monkeypatch.setattr(encoder.asyncio, "create_subprocess_exec", launch)
    adapter = encoder.QwenEmbedding()
    with pytest.raises(StoragePolicyError) as error:
        await adapter.encode(plan)
    assert (
        "private-pipe-marker" not in str(error.value) and not adapter.admission.locked()
    )


@pytest.mark.asyncio
async def test_cancellation_during_launch_still_joins_owned_child(monkeypatch):
    """Retain admission when cancellation arrives before subprocess creation returns its handle."""
    plan = plan_ingestion(*sample())
    launching, release, killed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    events = []
    monkeypatch.setattr(encoder.shutil, "which", lambda value: "/trusted/uv")

    class Child:
        """Represent a process created after the caller already requested cancellation."""

        pid = 12345
        returncode = None

        async def communicate(self, body=None):
            """Record the completed join after process-group termination."""
            await killed.wait()
            self.returncode = -9
            events.append("joined")
            return b"", b""

    async def launch(*args, **kwargs):
        """Delay returning the child handle while keeping its creation shielded."""
        launching.set()
        await release.wait()
        return Child()

    def kill(pid, sig):
        """Signal only the newly owned process group."""
        assert pid == 12345
        events.append("killed")
        killed.set()

    monkeypatch.setattr(encoder.asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr(encoder.os, "killpg", kill)
    adapter = encoder.QwenEmbedding()
    work = asyncio.create_task(adapter.encode(plan))
    await launching.wait()
    work.cancel()
    await asyncio.sleep(0)
    assert adapter.admission.locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await work
    assert events == ["killed", "joined"] and not adapter.admission.locked()


@pytest.mark.asyncio
async def test_vector_scroll_cannot_loop_on_empty_cyclic_pages(vector_context):
    """Bound verification even if a malformed server emits advancing cursors without any expected points."""
    args, plan, server, client, adapter = vector_context
    async with client:
        await adapter.ensure()
    cursors = []
    original = server.handle

    def empty_pages(request):
        """Return controlled empty pages that would otherwise keep a verifier waiting forever."""
        if request.url.path.endswith("/scroll"):
            cursors.append(len(cursors))
            return httpx.Response(
                200, json=dict(result=dict(points=[], next_page_offset=str(uuid4())))
            )
        return original(request)

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:6333", transport=httpx.MockTransport(empty_pages)
    ) as transport:
        adapter.client = transport
        with pytest.raises(StoragePolicyError, match="verification_failed"):
            await adapter.verify(plan, encoded(plan))
    assert len(cursors) == 2


@pytest.mark.asyncio
async def test_encoder_timeout_kills_and_joins_before_safe_error(monkeypatch):
    """Enforce the declared wall bound and retain no live child when the timeout path returns."""
    plan = plan_ingestion(*sample())
    terminated = asyncio.Event()
    events = []
    monkeypatch.setattr(encoder.shutil, "which", lambda value: "/trusted/uv")

    class Child:
        """Hold one model process until the timeout path explicitly terminates its group."""

        pid = 12345
        returncode = None

        async def communicate(self, body=None):
            """Join the controlled process after termination."""
            await terminated.wait()
            self.returncode = -9
            events.append("joined")
            return b"", b""

    async def launch(*args, **kwargs):
        """Return the synthetic process without touching model files."""
        return Child()

    async def timeout(awaitable, *, timeout):
        """Fail only the encoder's actual wall wait with the configured bound."""
        assert timeout == 600
        await asyncio.sleep(0)
        raise asyncio.TimeoutError()

    def kill(pid, sig):
        """Record termination of the exact owned group."""
        assert pid == 12345
        events.append("killed")
        terminated.set()

    monkeypatch.setattr(encoder.asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr(encoder.asyncio, "wait_for", timeout)
    monkeypatch.setattr(encoder.os, "killpg", kill)
    adapter = encoder.QwenEmbedding()
    with pytest.raises(StoragePolicyError, match="encoding_failed"):
        await adapter.encode(plan)
    assert events == ["killed", "joined"] and not adapter.admission.locked()
