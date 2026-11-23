"""Measure fixed long-context packing with the real tokenizer without generating or grading model answers."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path

from apps.harness.inference import ProductInference

LOGGER = logging.getLogger(__name__)


def write_receipt(path, value):
    """Retain one exclusive finite JSON receipt without overwriting an earlier probe."""
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "w"
    ) as output:
        json.dump(value, output, indent=2, ensure_ascii=False, allow_nan=False)
    LOGGER.info("context_priority_receipt_written artifact=%s", path.name)


async def probe(inference, output):
    """Freeze one fixed packing collision and compare three policies without any completion call."""
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    messages = [
        {
            "role": "user",
            "content": "Historical identifier: H-286. " + "stone " * 12000,
        },
        {"role": "assistant", "content": "leaf " * 12000},
        {
            "role": "user",
            "content": "Preserve the available historical and source identifiers; do not infer missing evidence.",
        },
    ]
    evidence = ("Source identifier: R-752. " + "river " * 10000).encode()
    options = {"preset": "fast", "max_tokens": 512}
    frozen = {
        "description": "Fixed synthetic long-context packing panel, no model answer generation or semantic-quality claim.",
        "messages": messages,
        "evidence": evidence.decode(),
        "options": options,
    }
    write_receipt(output / "frozen-inputs.json", frozen)
    results = []
    try:
        for strategy in ("evidence-first", "recent-turns", "strict"):
            start = time.monotonic()
            _, fitted, report = await inference.prepare(
                messages, evidence=[evidence], context_strategy=strategy, **options
            )
            content = "\n".join(item["content"] for item in fitted)
            row = {
                "strategy": strategy,
                "report": report,
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "history_fact_present": "H-286" in content,
                "source_fact_present": "R-752" in content,
                "fitted_sha256": hashlib.sha256(
                    json.dumps(fitted, sort_keys=True).encode()
                ).hexdigest(),
            }
            results.append(row)
            write_receipt(output / (strategy + ".json"), row)
        expected = [(False, True), (True, False), (True, False)]
        matched = [
            (row["history_fact_present"], row["source_fact_present"]) for row in results
        ] == expected
        return {
            "status": "PACKING_AS_EXPECTED" if matched else "PACKING_UNEXPECTED",
            "results": results,
            "completion_calls": 0,
            "semantic_quality_measured": False,
            "peak_memory_measured": False,
        }
    finally:
        write_receipt(
            output / "observations.json",
            {
                "description": "All completed native tokenizer/preparation observations, including partial failures.",
                "results": results,
                "completion_calls": 0,
                "complete": len(results) == 3,
            },
        )


def main():
    """Run only the approved CORE tokenizer against one new output directory and fixed synthetic inputs."""
    parser = argparse.ArgumentParser(
        description="Probe real-tokenizer long-context packing without text generation."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = asyncio.run(probe(ProductInference(), args.output))
    write_receipt(args.output / "summary.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
