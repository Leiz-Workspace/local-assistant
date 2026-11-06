"""Verify strict retrieval scope, hostile candidate replies and byte-exact approved query formatting."""

import copy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.qdrant_retrieval import QdrantRetrieval, search_options
from src.infrastructure.qwen_embedding import EncodedBatch
from src.infrastructure.qwen_query import QwenQueryEmbedding

VECTOR = tuple([1.0] + [0.0] * 1023)


class VectorFixture:
    """Record independent query bodies and provide controlled hostile server candidates without writes."""

    def __init__(self):
        """Create isolated trusted scope and one independent candidate payload."""
        self.model, self.path = "a" * 64, "/collections/test"
        self.owner, self.namespace, self.file = uuid4(), uuid4(), uuid4()
        self.point = dict(
            id=str(uuid4()),
            score=0.9,
            payload=dict(
                owner_id=str(self.owner),
                namespace_id=str(self.namespace),
                file_id=str(self.file),
                model_fingerprint=self.model,
                visibility="private",
                content_trust="untrusted",
                state="active",
            ),
        )
        self.points = [self.point]
        self.present = True
        self.calls = []

    async def owned(self):
        """Return only a controlled ownership presence with no schema creation."""
        return {} if self.present else None

    async def request(self, method, path, body):
        """Capture only the read query and return the test-local candidate list."""
        self.calls.append((method, path, body))
        return dict(result=dict(points=self.points))


@pytest.mark.parametrize(
    "query,k,ids",
    [
        ("", 1, None),
        (" ", 1, None),
        ("x", True, None),
        ("x", 0, None),
        ("x", 11, None),
        ("é" * 2049, 1, None),
        ("x", 1, []),
        ("x", 1, ["caller"]),
        ("x", 1, [uuid4()] * 2),
    ],
)
def test_reject_invalid_search_options(query, k, ids):
    """Reject blank, oversized, coercible or arbitrary ACL-narrowing inputs before any service work."""
    with pytest.raises(StoragePolicyError) as error:
        search_options(query, k, ids)
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_server_acl_filter_is_conjunctive_and_read_only():
    """Assert exact trusted filter intersection and bounded dense query with no returned vectors."""
    fixture = VectorFixture()
    result = await QdrantRetrieval(fixture).search(
        fixture.owner, fixture.namespace, VECTOR, top_k=3, file_ids=[fixture.file]
    )
    assert result == [fixture.point]
    method, path, body = fixture.calls[0]
    assert method == "POST" and path.endswith("/points/query")
    assert (
        body["using"] == "dense"
        and body["limit"] == 20
        and body["with_vector"] is False
    )
    predicates = {row["key"]: row["match"] for row in body["filter"]["must"]}
    assert predicates == dict(
        owner_id=dict(value=str(fixture.owner)),
        namespace_id=dict(value=str(fixture.namespace)),
        model_fingerprint=dict(value=fixture.model),
        visibility=dict(value="private"),
        content_trust=dict(value="untrusted"),
        state=dict(value="active"),
        file_id=dict(any=[str(fixture.file)]),
    )


@pytest.mark.parametrize(
    "case",
    [
        "owner",
        "namespace",
        "model",
        "visibility",
        "trust",
        "state",
        "file",
        "id",
        "duplicate",
        "score_nan",
        "score_bool",
        "score_string",
        "score_range",
        "payload",
        "oversized",
        "missing_collection",
        "vector_nan",
        "vector_dimension",
        "vector_bool",
        "vector_norm",
    ],
)
@pytest.mark.asyncio
async def test_hostile_candidates_and_vectors_fail_closed(case):
    """Refuse malformed or foreign server data without leaking untrusted text or private diagnostic values."""
    fixture = VectorFixture()
    vector = VECTOR
    scope_fields = dict(
        owner="owner_id",
        namespace="namespace_id",
        model="model_fingerprint",
        visibility="visibility",
        trust="content_trust",
        state="state",
    )
    if case in scope_fields:
        fixture.point["payload"][scope_fields[case]] = "private-hostile-marker"
    elif case == "file":
        fixture.point["payload"]["file_id"] = str(uuid4())
    elif case == "id":
        fixture.point["id"] = "private-hostile-marker"
    elif case == "duplicate":
        fixture.points.append(copy.deepcopy(fixture.point))
    elif case.startswith("score_"):
        fixture.point["score"] = {
            "score_nan": float("nan"),
            "score_bool": True,
            "score_string": "private-hostile-marker",
            "score_range": 2,
        }[case]
    elif case == "payload":
        fixture.point["payload"] = None
    elif case == "oversized":
        fixture.points *= 21
    elif case == "missing_collection":
        fixture.present = False
    elif case == "vector_nan":
        vector = (float("nan"),) + VECTOR[1:]
    elif case == "vector_dimension":
        vector = VECTOR[:2]
    elif case == "vector_bool":
        vector = (True,) + VECTOR[1:]
    elif case == "vector_norm":
        vector = tuple([0.0] * 1024)
    with pytest.raises(StoragePolicyError) as error:
        await QdrantRetrieval(fixture).search(
            fixture.owner, fixture.namespace, vector, top_k=1, file_ids=[fixture.file]
        )
    assert error.value.status_code == 503 and "private-hostile-marker" not in str(
        error.value
    )


@pytest.mark.asyncio
async def test_query_instruction_exact_bytes_and_shared_encoder(monkeypatch):
    """Encode exact original query with the approved instruction and require matching full token counts."""
    from src.infrastructure import qwen_query

    calls = []

    def preflight(plan):
        """Capture instructed private bytes and return complete injected protocol counts."""
        calls.append(plan)
        return (23,)

    class Encoder:
        """Record reuse of the provided ingestion encoder with no new model runtime."""

        async def encode(self, plan):
            """Return one independently declared complete unit vector for protocol testing."""
            assert plan is calls[0]
            return EncodedBatch(plan.model_fingerprint, (23,), (VECTOR,))

    monkeypatch.setattr(qwen_query, "preflight_plan", preflight)
    adapter = QwenQueryEmbedding(Encoder(), "a" * 64)
    query = "  tài liệu\nnguyên bản  "
    assert await adapter.encode(query) == VECTOR
    profile = json.loads(
        (qwen_query.ROOT / "configs/embedding-qwen-evaluation.json").read_text()
    )
    assert calls[0].points[0].text == profile["query_prefix"] + query


@pytest.mark.asyncio
async def test_query_count_drift_is_rejected(monkeypatch):
    """Reject a model response whose complete instructed input count differs from token preflight."""
    from src.infrastructure import qwen_query

    def preflight(plan):
        """Provide an explicit token count without model execution."""
        return (23,)

    async def encode(plan):
        """Inject a valid vector with mismatched count to exercise the boundary."""
        return EncodedBatch(plan.model_fingerprint, (24,), (VECTOR,))

    monkeypatch.setattr(qwen_query, "preflight_plan", preflight)
    with pytest.raises(StoragePolicyError):
        await QwenQueryEmbedding(SimpleNamespace(encode=encode), "a" * 64).encode(
            "query"
        )
