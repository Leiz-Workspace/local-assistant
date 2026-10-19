"""Read bounded owned dense candidates using server-derived tenant filters without vector mutations."""

import logging
import math
from uuid import UUID

import numpy as np

from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)


def search_options(query, top_k, file_ids=None):
    """Validate complete query bytes and bounded UUID-only scope narrowing without accepting caller filters."""
    try:
        query_bytes = len(query.encode()) if isinstance(query, str) else 0
    except UnicodeError:
        raise StoragePolicyError("retrieval_input_invalid", 422) from None
    if (
        not isinstance(query, str)
        or not query.strip()
        or query_bytes > 4096
        or type(top_k) is not int
        or not 1 <= top_k <= 10
        or file_ids is not None
        and (
            not isinstance(file_ids, (list, tuple))
            or not 1 <= len(file_ids) <= 16
            or any(not isinstance(value, UUID) for value in file_ids)
            or len(set(file_ids)) != len(file_ids)
        )
    ):
        raise StoragePolicyError("retrieval_input_invalid", 422)
    return max(20, top_k * 5)


class QdrantRetrieval:
    """Treat owned Qdrant results only as bounded untrusted source/generation candidates."""

    def __init__(self, vectors):
        """Reuse the ingestion-owned client/schema identity without owning or creating any resources."""
        self.vectors = vectors

    async def search(self, owner, namespace, vector, *, top_k, file_ids=None):
        """Apply trusted conjunctive ACL predicates and reject malformed or foreign server results safely."""
        limit = search_options("validation", top_k, file_ids)
        try:
            if not isinstance(owner, UUID) or not isinstance(namespace, UUID):
                raise ValueError("scope")
            if (
                not isinstance(vector, (tuple, list))
                or len(vector) != 1024
                or any(type(value) not in (int, float) for value in vector)
            ):
                raise ValueError("vector")
            values = np.asarray(vector, dtype=np.float32)
            if not np.isfinite(values).all() or abs(np.linalg.norm(values) - 1) > 1e-5:
                raise ValueError("vector")
            if await self.vectors.owned() is None:
                raise ValueError("collection_missing")
            scope = dict(
                owner_id=str(owner),
                namespace_id=str(namespace),
                model_fingerprint=self.vectors.model,
                visibility="private",
                content_trust="untrusted",
                state="active",
            )
            must = [
                dict(key=key, match=dict(value=value)) for key, value in scope.items()
            ]
            if file_ids is not None:
                must.append(
                    dict(
                        key="file_id",
                        match=dict(any=[str(value) for value in file_ids]),
                    )
                )
            reply = await self.vectors.request(
                "POST",
                self.vectors.path + "/points/query",
                dict(
                    query=list(vector),
                    using="dense",
                    filter=dict(must=must),
                    limit=limit,
                    with_payload=True,
                    with_vector=False,
                ),
            )
            points = reply["result"]["points"]
            if not isinstance(points, list) or len(points) > limit:
                raise ValueError("points")
            seen = set()
            for point in points:
                identifier = UUID(point["id"])
                payload, score = point["payload"], point["score"]
                if (
                    identifier in seen
                    or type(score) not in (int, float)
                    or not math.isfinite(score)
                    or not -1.0001 <= score <= 1.0001
                    or not isinstance(payload, dict)
                    or any(payload.get(key) != value for key, value in scope.items())
                    or file_ids is not None
                    and UUID(payload["file_id"]) not in file_ids
                ):
                    raise ValueError("point")
                UUID(payload["file_id"])
                seen.add(identifier)
            logger.info("retrieval_candidates_received count=%d", len(points))
            return points
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            logger.warning("retrieval_candidates_rejected")
            raise StoragePolicyError("retrieval_candidates_invalid", 503) from None
