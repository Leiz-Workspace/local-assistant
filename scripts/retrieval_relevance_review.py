"""Freeze score-blind relevance packets and validate complete human review before new evaluation."""

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
MAX_BYTES = 2 * 1024 * 1024


def canonical(value):
    """Encode stable UTF-8 bytes for packet identity and independent review binding."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def digest(value):
    """Hash the complete canonical public evaluation object."""
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition, error):
    """Reject incomplete or misleading evaluation evidence with a sanitized reason."""
    if not condition:
        logger.warning("relevance_review_rejected reason=%s", error)
        raise ValueError(error)


def validate_corpus(corpus):
    """Accept only bounded unlabeled source/query records with unique textual identities."""
    require(
        isinstance(corpus, dict)
        and set(corpus) == {"description", "version", "documents", "queries"},
        "corpus_shape_invalid",
    )
    require(
        all(
            isinstance(corpus[key], str) and corpus[key].strip()
            for key in ("description", "version")
        ),
        "corpus_metadata_invalid",
    )
    require(len(canonical(corpus)) <= MAX_BYTES, "corpus_size_invalid")
    for kind in ("documents", "queries"):
        rows = corpus[kind]
        require(
            isinstance(rows, list) and 1 <= len(rows) <= 100, "corpus_count_invalid"
        )
        require(
            all(isinstance(row, dict) and set(row) == {"id", "text"} for row in rows),
            "corpus_row_invalid",
        )
        require(
            all(
                all(
                    isinstance(row[key], str)
                    and row[key].strip()
                    and len(row[key].encode()) <= (128 if key == "id" else 16384)
                    for key in ("id", "text")
                )
                for row in rows
            ),
            "corpus_text_invalid",
        )
        require(
            len({row["id"] for row in rows}) == len(rows), "corpus_identity_invalid"
        )
    logger.info(
        "relevance_corpus_verified documents=%d queries=%d",
        len(corpus["documents"]),
        len(corpus["queries"]),
    )


def build_packet(corpus):
    """Create deterministic score-free ordering and pending labels for every source/query pair."""
    validate_corpus(corpus)
    source_sha = digest(corpus)
    queries = []
    for query in sorted(corpus["queries"], key=lambda row: row["id"]):
        ordered = sorted(
            corpus["documents"],
            key=lambda row: digest([source_sha, query["id"], row["id"]]),
        )
        queries.append(
            {
                "id": query["id"],
                "text": query["text"],
                "documents": [
                    {
                        "id": row["id"],
                        "text": row["text"],
                        "relevant": None,
                        "reason": "",
                    }
                    for row in ordered
                ],
            }
        )
    packet = {
        "description": "Agent-authored challenge data awaiting independent human review; no model scores, inferred relevance or adoption approval.",
        "version": "d27-human-review-v1",
        "corpus_sha256": source_sha,
        "queries": queries,
    }
    logger.info(
        "relevance_packet_built queries=%d pairs=%d",
        len(queries),
        len(queries) * len(corpus["documents"]),
    )
    return packet


def review_template(packet):
    """Create an explicitly unreviewed response without claiming a human supplied any label."""
    return {
        "description": "Pending human relevance judgments; true means this source directly supports answering the query, false means it does not. No supporting source is allowed.",
        "packet_sha256": digest(packet),
        "reviewer": "",
        "reviewed_at": "",
        "attestation": "",
        "queries": [
            {
                "id": query["id"],
                "documents": [
                    {"id": row["id"], "relevant": None, "reason": ""}
                    for row in query["documents"]
                ],
            }
            for query in packet["queries"]
        ],
    }


def validate_review(corpus, packet, review):
    """Bind every binary judgment and rationale to frozen content without inferring human identity."""
    require(packet == build_packet(corpus), "packet_content_changed")
    require(
        isinstance(review, dict)
        and set(review)
        == {
            "description",
            "packet_sha256",
            "reviewer",
            "reviewed_at",
            "attestation",
            "queries",
        },
        "review_shape_invalid",
    )
    require(review["packet_sha256"] == digest(packet), "review_packet_changed")
    require(
        all(
            isinstance(review[key], str)
            and review[key].strip()
            and len(review[key]) <= 512
            for key in ("description", "reviewer", "reviewed_at")
        ),
        "review_metadata_missing",
    )
    try:
        timestamp = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
    except ValueError:
        timestamp = None
    require(
        timestamp is not None and timestamp.utcoffset() is not None,
        "review_timestamp_invalid",
    )
    require(
        review["attestation"]
        == "I independently reviewed every query and document without viewing model rankings or scores.",
        "review_attestation_missing",
    )
    queries = review["queries"]
    require(
        isinstance(queries, list) and len(queries) == len(packet["queries"]),
        "review_queries_incomplete",
    )
    require(
        all(
            isinstance(row, dict)
            and set(row) == {"id", "documents"}
            and isinstance(row["id"], str)
            for row in queries
        ),
        "review_query_invalid",
    )
    indexed = {row["id"]: row for row in queries}
    require(
        len(indexed) == len(queries)
        and set(indexed) == {row["id"] for row in packet["queries"]},
        "review_query_identity_invalid",
    )
    labels = []
    for query in packet["queries"]:
        rows = indexed[query["id"]]["documents"]
        expected = {row["id"] for row in query["documents"]}
        require(
            isinstance(rows, list) and len(rows) == len(expected),
            "review_pairs_incomplete",
        )
        require(
            all(
                isinstance(row, dict)
                and set(row) == {"id", "relevant", "reason"}
                and isinstance(row["id"], str)
                for row in rows
            ),
            "review_pair_invalid",
        )
        require(
            len({row["id"] for row in rows}) == len(rows)
            and {row["id"] for row in rows} == expected,
            "review_pair_identity_invalid",
        )
        require(
            all(
                type(row["relevant"]) is bool
                and isinstance(row["reason"], str)
                and 1 <= len(row["reason"].strip()) <= 2048
                for row in rows
            ),
            "review_labels_pending_or_invalid",
        )
        labels.append(
            {
                "id": query["id"],
                "relevant": sorted(row["id"] for row in rows if row["relevant"]),
            }
        )
    result = {
        "description": "Structurally validated reviewer-supplied judgments, not proof of reviewer independence, benchmark quality or owner adoption.",
        "status": "STRUCTURALLY_VALIDATED_ONLY",
        "corpus_sha256": digest(corpus),
        "packet_sha256": digest(packet),
        "review_sha256": digest(review),
        "reviewer": review["reviewer"],
        "reviewed_at": review["reviewed_at"],
        "queries": labels,
        "absent_answer_queries": sum(not row["relevant"] for row in labels),
        "benchmark_executed": False,
        "adoption_approved": False,
    }
    logger.info(
        "relevance_review_structure_validated queries=%d absent_answer_queries=%d",
        len(labels),
        result["absent_answer_queries"],
    )
    return result


def read_json(path):
    """Read bounded evaluation JSON without accepting duplicate object keys or nonfinite constants."""

    def unique(pairs):
        """Reject duplicate keys that could silently replace evidence in JSON objects."""
        result = {}
        for key, value in pairs:
            require(key not in result, "json_duplicate_key")
            result[key] = value
        return result

    def invalid_constant(value):
        """Reject JavaScript numeric extensions in retained review artifacts."""
        raise ValueError("json_nonfinite_value")

    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "json_size_invalid")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


def write_new(path, value):
    """Exclusively create a private artifact and preserve all existing frozen evidence."""
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(raw)
    logger.info(
        "relevance_artifact_created sha256=%s", hashlib.sha256(raw.encode()).hexdigest()
    )


def main(argv=None):
    """Build an unreviewed packet or validate an explicitly supplied human response offline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("packet", "validate"))
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--packet", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        corpus = read_json(args.corpus)
        if args.action == "packet":
            packet = build_packet(corpus)
            require(
                not Path(args.packet).exists()
                and not Path(args.review).exists()
                and Path(args.packet).resolve() != Path(args.review).resolve(),
                "output_already_exists",
            )
            write_new(args.packet, packet)
            write_new(args.review, review_template(packet))
        else:
            require(args.output is not None, "output_required")
            result = validate_review(
                corpus, read_json(args.packet), read_json(args.review)
            )
            write_new(args.output, result)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        logger.error("relevance_command_failed category=%s", type(exc).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
