"""Measure deterministic history retention and recall with the approved native tokenizer, never grading generated answers."""

import argparse
import asyncio
import hashlib
import json
import logging
from pathlib import Path
from uuid import uuid4

from apps.harness.inference import ProductInference
from benchmarks.context_priority_probe import write_receipt
from src.application.ports.inference import InferenceFailure
from src.application.services.context_reduction import ContextError, encode
from src.infrastructure.context_archive import ContextArchive

LOGGER = logging.getLogger(__name__)
SOURCES = (
    "src/application/services/context_composer.py",
    "src/application/services/context_reduction.py",
    "src/infrastructure/context_archive.py",
    "apps/harness/inference.py",
    "apps/harness/service.py",
    "apps/harness/routes.py",
    "apps/harness/main.py",
    "apps/cli/main.py",
    "benchmarks/context_policy_probe.py",
    "benchmarks/tests/test_context_policy_probe.py",
    "tests/test_context_reduction.py",
    "tests/test_context_archive.py",
    "tests/test_product_context_policy.py",
    "configs/models.yaml",
    "apps/api/runtime/presets.py",
)


def corpus():
    """Return fixed synthetic old-fact, pressure and mandatory-overflow inputs without private conversation data."""
    history = [
        dict(role="user", content="Which Atlas restore snapshot is required?"),
        dict(
            role="assistant",
            content="Atlas release 2.4 requires snapshot G-17; G-18 belongs to release 2.5.",
        ),
    ]
    for number in range(2, 15):
        history += [
            dict(role="user", content=f"Unrelated task {number}."),
            dict(role="assistant", content="Acknowledged unrelated material."),
        ]
    current = dict(
        role="user",
        content="Which Atlas restore snapshot is required? Use exact evidence.",
    )
    pressure = history[:2]
    for _ in range(3):
        pressure += [
            dict(role="user", content="a " * 10000),
            dict(role="assistant", content="b " * 10000),
        ]
    return dict(
        history=history + [current],
        pressure=pressure + [current],
        overflow=[dict(role="user", content="stone " * 40000)],
    )


async def probe(inference, output):
    """Freeze all inputs before eight preparation-only scenarios and retain first observations including failures."""
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    inputs = corpus()
    frozen = dict(
        schema_version=1,
        corpus=inputs,
        source_sha256={
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in SOURCES
        },
        options=dict(preset="fast", max_tokens=512),
        completion_calls=0,
    )
    write_receipt(output / "frozen-inputs.json", frozen)
    owner, store = uuid4(), ContextArchive()
    rows = []

    def archive(raw):
        """Use the actual owner-bound memory cache for all synthetic offloads."""
        return store.put(owner, raw)

    def recall(identifier):
        """Resolve only explicit same-owner references within this one probe process."""
        return store.get(owner, identifier)

    async def prepare(name, messages, **options):
        """Retain each first native preparation result without hidden retries or completion generation."""
        try:
            _, fitted, report = await inference.prepare(
                messages, preset="fast", max_tokens=512, **options
            )
            row = dict(
                name=name,
                report=report,
                fitted_sha256=hashlib.sha256(encode(fitted)).hexdigest(),
                old_fact_present="G-17" in encode(fitted).decode(),
                current_task_present=messages[-1]["content"] in fitted[-1]["content"],
                error=None,
            )
        except (InferenceFailure, ContextError) as error:
            row = dict(
                name=name,
                error=error.code,
                status=getattr(error, "status_code", getattr(error, "status", None)),
            )
        rows.append(row)
        write_receipt(output / (name + ".json"), row)
        return row

    try:
        await prepare("legacy", inputs["history"])
        await prepare("sliding", inputs["history"], history_policy=dict(window_turns=3))
        await prepare(
            "pinned",
            inputs["history"],
            history_policy=dict(window_turns=3, pinned_turns=[1]),
        )
        compact = await prepare(
            "compact",
            inputs["history"],
            history_policy=dict(mode="extractive-compact", window_turns=3),
            archive=archive,
        )
        handle = (
            compact["report"]["history_policy"]["archive"]["id"]
            if compact.get("report")
            else None
        )
        if handle is None:
            raise RuntimeError("context_probe_missing_archive")
        await prepare(
            "recall",
            [inputs["history"][-1]],
            history_policy=dict(mode="extractive-compact", recall_ids=[handle]),
            archive=archive,
            recall=recall,
        )
        await prepare(
            "pressure",
            inputs["pressure"],
            history_policy=dict(mode="extractive-compact", pinned_turns=[1]),
            archive=archive,
        )
        await prepare(
            "strict",
            inputs["history"],
            history_policy=dict(window_turns=3),
            context_strategy="strict",
        )
        await prepare(
            "mandatory-overflow",
            inputs["overflow"],
            history_policy=dict(window_turns=3),
        )
        matched = (
            len(rows) == 8
            and [row.get("old_fact_present") for row in rows[:6]]
            == [False, False, True, True, True, True]
            and all(row.get("current_task_present") for row in rows[:6])
            and rows[5]["report"]["input_tokens"] <= 32000
            and bool(rows[5]["report"]["history_policy"]["evicted_turns"])
            and rows[6]["error"] == "strict_context_would_trim"
            and rows[7]["error"] == "context_overflow"
        )
        result = dict(
            schema_version=1,
            status="PACKING_AS_EXPECTED" if matched else "PACKING_UNEXPECTED",
            frozen_sha256=hashlib.sha256(
                (output / "frozen-inputs.json").read_bytes()
            ).hexdigest(),
            source_sha256=frozen["source_sha256"],
            results=rows,
            completion_calls=0,
            semantic_quality_measured=False,
            peak_memory_measured=False,
        )
        write_receipt(output / "summary.json", result)
        return result
    finally:
        store.close()
        write_receipt(
            output / "observations.json",
            dict(
                results=rows,
                complete=len(rows) == 8,
                completion_calls=0,
                raw_cache_cleared=not store.entries,
            ),
        )
        LOGGER.info("context_policy_probe_closed cases=%d", len(rows))


def main():
    """Run one exclusive preparation-only panel against the already approved CORE model and configuration."""
    parser = argparse.ArgumentParser(
        description="Measure explicit context retention with native token counts, without answer generation."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = asyncio.run(probe(ProductInference(), args.output))
    print(
        json.dumps(
            dict(
                status=result["status"],
                cases=len(result["results"]),
                completion_calls=0,
            )
        )
    )
    return 0 if result["status"] == "PACKING_AS_EXPECTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
