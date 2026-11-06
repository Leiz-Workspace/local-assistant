"""Validate the optional voice reading bridge with original SDK assets and zero neural dispatch."""

import argparse
import json
import logging
import os
import subprocess
import time
from dataclasses import asdict

from benchmarks.scripts import vi_ngoc_api_boundary_trial as previous
from benchmarks.scripts.vi_workflow_reading_policy import POLICY, prepare_answer

LOGGER = logging.getLogger(__name__)
Q = previous.Q
ROOT = Q.assets.ROOT / "workflow-reading-preparation-first"
SOURCES = (
    "benchmarks/scripts/vi_workflow_reading_policy.py",
    "benchmarks/scripts/vi_workflow_reading_bridge.py",
    "benchmarks/scripts/vi_workflow_reading_worker.py",
    "benchmarks/scripts/vi_workflow_reading_check.py",
    "benchmarks/tests/test_vi_workflow_reading_policy.py",
    "benchmarks/tests/test_vi_workflow_reading_bridge.py",
)
ADDITIONAL = (
    ("core-plain", "Đã rõ."),
    ("core-repeat-api", "Bạn có thể dùng API hoặc API của ứng dụng."),
    ("core-repeat-python", "Python và Python đều có thể gọi API."),
    ("core-terms-clause", "GitHub đã sẵn sàng; server vẫn hoạt động."),
    ("core-english", "I can use Python on this server."),
    ("core-date", "Tôi sẽ nhắc bạn lúc 18:30 ngày 05/12/2026."),
    ("core-all-terms", "API, Python, GitHub và server đã sẵn sàng."),
    ("core-thanks", "Cảm ơn bạn, chúc bạn một ngày tốt lành!"),
    ("core-question", "Bạn muốn thử API?"),
    ("core-substring", "Pythonic là cách viết theo phong cách Python."),
)


def verify_previous():
    """Preserve all46prior research source/test files and their original native audio/results."""
    previous.verify_previous()
    receipt = json.loads(
        (
            Q.assets.PROJECT / "docs/evidence/d74-ngoc-api-boundary-result.json"
        ).read_text()
    )
    for name, digest in receipt["source_sha256"].items():
        if Q.assets.digest(Q.assets.PROJECT / name) != digest:
            raise ValueError("workflow_reading_previous_source_changed")
    for name, digest in receipt["private_sha256"].items():
        if Q.assets.digest(previous.ROOT / name) != digest:
            raise ValueError("workflow_reading_previous_artifact_changed")
    LOGGER.info("workflow_reading_previous_verified research_files=46")


def cases():
    """Fix ten original accepted text controls and ten declared new CORE-style software inputs before probing."""
    original = previous.retained.retained.source_packet()
    selected = [(row["id"], row["source_text"]) for row in original] + list(ADDITIONAL)
    result = []
    for identity, source in selected:
        spoken, trace = prepare_answer(source)
        result.append(
            dict(
                id=identity, source_text=source, speech_text=spoken, trace=asdict(trace)
            )
        )
    LOGGER.info("workflow_reading_probe_packet_prepared cases=%d", len(result))
    return result


def command(output, scope=None, scope_sha=None):
    """Reuse sealed original CPU isolation, with model-free mode unless a native manifest is explicitly supplied."""
    probe = scope is None
    args = previous.retained.retained.command(
        output, probe=probe, frontend=scope, expected_sha=scope_sha
    )
    if not probe:
        target = args.index("/approved-validation.json")
        args[target] = "/approved-workflow.json"
    mounts = []
    for name in SOURCES:
        if name.endswith("_policy.py") or name.endswith("_worker.py"):
            mounts.extend(["--ro-bind", str(Q.assets.PROJECT / name), "/app/" + name])
    index = args.index("--remount-ro")
    args[index:index] = mounts
    start = args.index("/venv/bin/python")
    return (
        args[:start]
        + ["/venv/bin/python", "/app/benchmarks/scripts/vi_workflow_reading_worker.py"]
        + (["--probe"] if probe else ["--approved-manifest", scope_sha])
    )


def verify_observations(rows, packet, accepted):
    """Require exact original ten-case phones/chunks/caps and preserve every new-case outcome without a quality claim."""
    if len(rows) != len(packet) or [row["id"] for row in rows] != [
        row["id"] for row in packet
    ]:
        raise ValueError("workflow_reading_probe_order")
    lookup = {row["id"]: row for row in accepted}
    for row, source in zip(rows, packet, strict=True):
        if row["spoken_sha256"] != source["trace"]["spoken_sha256"]:
            raise ValueError("workflow_reading_probe_source")
        if row["id"] in lookup:
            old = lookup[row["id"]]
            if (
                row["status"] != "PLANNED"
                or row["chunks"] != old["chunks"]
                or row["gaps"] != old["gaps"]
                or [plan["phones"] for plan in row["plans"]]
                != [plan["us"] for plan in old["phone_plans"]]
                or [plan["shared_cap"] for plan in row["plans"]]
                != [plan["shared_cap"] for plan in old["phone_plans"]]
            ):
                raise ValueError("workflow_reading_accepted_policy_drift")
    LOGGER.info(
        "workflow_reading_observations_verified accepted_controls=%d", len(accepted)
    )


def probe(root=ROOT):
    """Run one bounded genuine SDK inspection without model mounts, weights, audio synthesis or workflow recovery."""
    verify_previous()
    before = Q.lifecycle.local_state()
    packet = cases()
    root.mkdir(mode=0o700)
    directory = root / "probe"
    directory.mkdir(mode=0o700)
    output = directory / "native"
    output.mkdir(mode=0o700)
    raw = json.dumps(
        [dict(id=row["id"], speech_text=row["speech_text"]) for row in packet],
        ensure_ascii=False,
    ).encode()
    args = command(output)
    Q.assets.publish(
        directory / "request.json",
        dict(
            description="Twenty fixed public software/frontend cases; original answer and rendered text separately bound.",
            rows=packet,
        ),
    )
    Q.assets.publish(
        directory / "launch.json",
        dict(
            description="Original pinned SDK/tokenizer only, no model mounts or neural dispatch.",
            command=args,
            source_sha256={
                name: Q.assets.digest(Q.assets.PROJECT / name) for name in SOURCES
            },
        ),
    )
    started, peak = time.monotonic(), 0
    with (
        (directory / "stdout.log").open("xb") as stdout,
        (directory / "stderr.log").open("xb") as stderr,
    ):
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        try:
            process.stdin.write(raw)
            process.stdin.close()
            while process.poll() is None:
                peak = max(
                    peak,
                    sum(
                        Q.lifecycle.rss_bytes(pid)
                        for pid in Q.lifecycle.process_tree(process.pid)
                    ),
                )
                if peak > 2 * Q.lifecycle.GIB or time.monotonic() - started > 60:
                    raise ValueError("workflow_reading_probe_resource")
                Q.assets.budget(Q.assets.ROOT)
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("workflow_reading_probe_failed")
        finally:
            Q.assets.terminate(process)
            Q.assets.publish(
                directory / "retirement.json",
                dict(
                    description="Joined non-neural SDK probe, no native model requests.",
                    returncode=process.returncode,
                    peak_sampled_rss_bytes=peak,
                    wall_seconds=time.monotonic() - started,
                    model_calls=0,
                ),
            )
    observed = json.loads((output / "frontend.json").read_text())
    if observed.get("model_calls") != 0 or observed.get("reading_policy") != POLICY:
        raise ValueError("workflow_reading_probe_profile")
    accepted = json.loads(
        (previous.retained.retained.ROOT / "probe/native/frontend.json").read_text()
    )["rows"]
    verify_observations(observed["rows"], packet, accepted)
    after = Q.lifecycle.local_state()
    Q.assets.publish(
        root / "result.json",
        dict(
            description="Model-free reading bridge parity and authored CORE-style planning results, not an acoustic or workflow latency benchmark.",
            rows=observed["rows"],
            old_controls_verified=len(accepted),
            planned=sum(row["status"] == "PLANNED" for row in observed["rows"]),
            refused=sum(row["status"] == "REFUSED" for row in observed["rows"]),
            model_calls=0,
            native_recovery_executed=False,
            baseline_preserved=before == after,
        ),
    )


def main():
    """Run only the explicitly requested no-weights preparation check, never native workflow dispatch."""
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    probe()


if __name__ == "__main__":
    main()
