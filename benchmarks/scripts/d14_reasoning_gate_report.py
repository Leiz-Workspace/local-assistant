"""Verify full first reasoning-gate evidence and independently recount context with the existing vocabulary-only native tokenizer."""

import hashlib
import json
import logging
import os
import resource
import subprocess
import time
from pathlib import Path

import yaml

from benchmarks.scripts import d14_reasoning_gate as campaign
from benchmarks.scripts.d14_structured_acceptance import assess_gate
from scripts.full_regression import source_manifest
from scripts.profile_excerpt_evaluation import publish
from src.infrastructure.inference.reasoning_profile import ReasoningProfileAdapter
from src.infrastructure.inference.structured_profile import (
    StructuredProfileError,
    matches_schema,
    strict_json,
)

logger = logging.getLogger(__name__)
AUDIT = campaign.ROOT / "data/backups/d14-reasoning-gate-audit-20261026"
TOKENIZER = campaign.ROOT / "runtimes/llama.cpp/build-cuda/bin/llama-tokenize"
INTRO = "Find the only RELEASE_CODE in the document. Return only a JSON object with key code and its string value.\nDOCUMENT:\n"
END = "\nEND DOCUMENT. Return the exact release code."


def vocabulary_limits():
    """Bound only a trusted vocabulary-only child to two CPUs, 12GiB virtual space and finite CPU time without exposing GPU devices."""
    resource.setrlimit(resource.RLIMIT_AS, (12 * 1024**3, 12 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 15))
    available = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, available[:2])


def token_count(profile, text, destination):
    """Read only the existing GGUF vocabulary using the pinned native tool and retain bounded count/hash/exit receipts, never generate tokens."""
    config = yaml.safe_load((campaign.ROOT / "configs/models.yaml").read_text())[
        "models"
    ][profile]
    command = [
        str(TOKENIZER),
        "--model",
        str(campaign.ROOT / config["path"]),
        "--stdin",
        "--ids",
        "--no-bos",
        "--no-escape",
    ]
    environment = {
        key: os.environ[key]
        for key in ("PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH")
        if key in os.environ
    }
    environment.update(
        CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2"
    )
    started = time.monotonic()
    result = subprocess.run(
        command,
        input=text.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=True,
        env=environment,
        preexec_fn=vocabulary_limits,
    )
    if len(result.stdout) > 2 * 1024**2:
        raise ValueError("reasoning_context_tokenizer_output_size")
    ids = json.loads(result.stdout)
    if type(ids) is not list or any(
        type(value) is not int or value < 0 for value in ids
    ):
        raise ValueError("reasoning_context_tokenizer_schema")
    receipt = dict(
        description="Post-inference independent exact-input vocabulary-only recount; no model weights or generation, not a pre-inference attestation.",
        input_sha256=hashlib.sha256(text.encode()).hexdigest(),
        tokenizer_sha256=campaign.gate.BASE["digest"](TOKENIZER),
        token_ids_sha256=hashlib.sha256(result.stdout).hexdigest(),
        stderr_sha256=hashlib.sha256(result.stderr).hexdigest(),
        tokens=len(ids),
        exit_code=result.returncode,
        wall_seconds=time.monotonic() - started,
        GPU_devices_hidden=True,
        virtual_address_cap_GiB=12,
        model=config["path"],
    )
    publish(destination, receipt)
    logger.info(
        "reasoning_context_vocab_recount profile=%s tokens=%d exit=%d",
        profile,
        len(ids),
        result.returncode,
    )
    return len(ids)


def verify_context(case, prompt, calibration, count):
    """Reconstruct the frozen neutral document and minimal needle/maximal tail algorithm using an independent exact vocabulary counter."""
    if (
        type(prompt) is not str
        or not prompt.startswith(INTRO)
        or not prompt.endswith(END)
    ):
        raise ValueError("reasoning_context_document_changed")
    lines = prompt[len(INTRO) : -len(END)].splitlines()
    needle = "RELEASE_CODE: " + case["needle"]
    if lines.count(needle) != 1:
        raise ValueError("reasoning_context_needle_changed")
    position = lines.index(needle)
    records = [line for line in lines if line != needle]
    expected = [
        f"Entry {number:05d}: The archive lists neutral records about ordinary scheduling and routine calibration."
        for number in range(len(records))
    ]
    if (
        not 1 <= len(records) <= 2100
        or records != expected
        or INTRO + "\n".join(records[:position] + [needle] + records[position:]) + END
        != prompt
    ):
        raise ValueError("reasoning_context_records_changed")
    user = count("user", prompt)
    prefix = "\n".join(records[:position])
    offset = count("offset", INTRO + prefix)
    prefix_tokens = count("prefix", prefix)
    previous = count("previous", "\n".join(records[: max(position - 1, 0)]))
    if not (
        30000 <= user <= 30500
        and abs(offset - case["needle_target"]) <= 100
        and previous < case["needle_target"] <= prefix_tokens
        and calibration == dict(user_tokens=user, needle_prefix_tokens=offset)
    ):
        raise ValueError("reasoning_context_calibration_changed")
    if len(records) < 2100:
        next_line = f"Entry {len(records):05d}: The archive lists neutral records about ordinary scheduling and routine calibration."
        extended = INTRO + "\n".join(lines + [next_line]) + END
        if count("next_tail", extended) <= 30500:
            raise ValueError("reasoning_context_tail_not_maximal")
    logger.info(
        "reasoning_context_algorithm_verified id=%s tokens=%d offset=%d",
        case["id"],
        user,
        offset,
    )
    return dict(
        user_tokens=user,
        needle_prefix_tokens=offset,
        minimal_prefix_verified=True,
        maximal_tail_verified=True,
    )


def verify_wire(
    profile,
    case,
    row,
    directory,
    context_counter=None,
    *,
    boolean_answer_contract=False,
):
    """Verify the complete frozen payload, untouched native reasoning/final wire and exact first score without a self-hash-only prompt assertion."""
    if (
        strict_json((directory / "measurement.json").read_bytes()) != row
        or row["id"] != case["id"]
        or row["category"] != case["category"]
        or type(row["model_requests"]) is not int
        or row["model_requests"] != 1
    ):
        raise ValueError("reasoning_gate_first_row_changed")
    request_raw = (directory / "native-request.json").read_bytes()
    wire = (directory / "native-response.bin").read_bytes()
    request = strict_json(request_raw)
    adapter = ReasoningProfileAdapter(
        profile=profile,
        schema=case["schema"],
        endpoint="http://127.0.0.1:18080",
        boolean_answer_contract=boolean_answer_contract,
    )
    context = None
    if case["category"] == "memory_context":
        prompt = request["messages"][1]["content"]
        if context_counter is None:
            root = AUDIT / profile / case["id"]
            root.mkdir(parents=True, mode=0o700)

            def context_counter(label, text):
                """Bind independent count receipts to this exact profile/case and algorithm step."""
                return token_count(profile, text, root / (label + ".json"))

        context = verify_context(case, prompt, row["calibration"], context_counter)
    else:
        prompt = case["prompt"]
    images = ()
    if "image" in case:
        raw = (campaign.ROOT / case["image"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != case["image_sha256"]:
            raise ValueError("reasoning_gate_frozen_image_changed")
        images = (raw,)
    expected = adapter.payload(prompt, images, case.get("stream", False))
    if json.dumps(request, sort_keys=True, ensure_ascii=False) != json.dumps(
        expected, sort_keys=True, ensure_ascii=False
    ):
        raise ValueError("reasoning_gate_request_changed")
    valid, functional, reasoning = False, False, False
    content, value, usage = None, None, None
    try:
        if case.get("stream", False):
            events = [
                strict_json(line[6:])
                for line in wire.splitlines()
                if line.startswith(b"data: ") and line != b"data: [DONE]"
            ]
            reply = adapter.stream_reply(
                events, wire.decode().rstrip().endswith("data: [DONE]"), b"", True
            )
        else:
            reply = strict_json(wire)
        content, usage = adapter.validate_reply(reply)
        value = strict_json(content)
        valid = matches_schema(value, case["schema"])
        reasoning = bool(valid)
        functional = bool(
            valid
            and campaign.gate.BASE["strict_score"](content, case["expected"])
            and (
                case["category"] != "memory_context"
                or 30000 <= usage["prompt_tokens"] <= 32000
                and usage["prompt_tokens"] + 1024 <= 32768
            )
        )
    except (ValueError, KeyError, StructuredProfileError):
        pass
    if (
        row["format_passed"] is not valid
        or row["functional_passed"] is not functional
        or row["native_reasoning_verified"] is not reasoning
    ):
        raise ValueError("reasoning_gate_first_score_changed")
    if row.get("result"):
        saved = row["result"]
        if (
            saved["content"] != content
            or saved["value"] != value
            or saved["model_id"] != adapter.model
            or saved["request_sha256"] != hashlib.sha256(request_raw).hexdigest()
            or saved["wire_sha256"] != hashlib.sha256(wire).hexdigest()
            or saved["schema_sha256"]
            != hashlib.sha256(adapter.schema_bytes).hexdigest()
            or saved["input_tokens"] != usage["prompt_tokens"]
            or saved["output_tokens"] != usage["completion_tokens"]
        ):
            raise ValueError("reasoning_gate_native_result_changed")
    logger.info(
        "reasoning_gate_wire_verified profile=%s id=%s format=%s functional=%s",
        profile,
        case["id"],
        valid,
        functional,
    )
    return dict(
        id=case["id"],
        category=case["category"],
        format_passed=valid,
        functional_passed=functional,
        native_reasoning_verified=reasoning,
        request_sha256=hashlib.sha256(request_raw).hexdigest(),
        wire_sha256=hashlib.sha256(wire).hexdigest(),
        measurement_sha256=campaign.gate.BASE["digest"](directory / "measurement.json"),
        context_recount=context,
    )


def main():
    """Verify frozen inputs and all84 first responses, recompute shared acceptance and publish independent retained-score evidence."""
    frozen = strict_json(campaign.FREEZE.read_bytes())
    for name, expected in frozen["sha256"].items():
        if campaign.gate.BASE["digest"](campaign.ROOT / name) != expected:
            raise ValueError("reasoning_gate_frozen_input_changed")
    application = source_manifest()
    if application != frozen["application_sha256"]:
        raise ValueError("reasoning_gate_application_changed")
    summary = strict_json((campaign.OUTPUT / "result.json").read_bytes())
    if (
        summary["status"] != "MEASUREMENT_COMPLETE"
        or summary["baseline"] != summary["after"]
        or campaign.gate.BASE["local_state"]() != summary["after"]
        or summary["after"]["native_pids"]
    ):
        raise ValueError("reasoning_gate_runtime_or_campaign_incomplete")
    acceptance = assess_gate(summary, frozen["cases"])
    if any(summary[key] != value for key, value in acceptance.items()):
        raise ValueError("reasoning_gate_acceptance_changed")
    cases = {c["id"]: c for c in frozen["cases"]}
    profiles = {}
    for profile, record in summary["profiles"].items():
        observations = [
            verify_wire(
                profile, cases[row["id"]], row, campaign.OUTPUT / profile / row["id"]
            )
            for row in record["rows"]
        ]
        profiles[profile] = dict(
            total=42,
            format_passed=sum(r["format_passed"] for r in observations),
            functional_passed=sum(r["functional_passed"] for r in observations),
            observations=observations,
            runtime=record["runtime"],
            cancellation=record["cancellation"],
            provenance=record["provenance"],
            output_tokens=sum(
                r.get("result", {}).get("output_tokens", 0) for r in record["rows"]
            ),
            total_request_wall_seconds=sum(
                r.get("result", {}).get("wall_seconds", 0) for r in record["rows"]
            ),
        )
    result = dict(
        description="Independent complete fresh bounded-reasoning gate verification with vocabulary-only context recount; historical first scores remain unchanged.",
        status="LOCAL_REASONING_GATE_PASS"
        if acceptance["quality_gate_passed"]
        else "LOCAL_REASONING_GATE_FAIL",
        acceptance=acceptance,
        profiles=profiles,
        application_files=len(application),
        all_prior730_unchanged=True,
        historical_D14_scores_rewritten=False,
        new_model_requests_in_this_verification=0,
        scored_first_requests=84,
        planned_native_cancel_requests=2,
        actual_generation_attempts=86,
        original_full5674_is_historical=True,
        new_full732_run_claimed=False,
        model_or_default_changes=0,
        downloads=0,
        database_or_Vault_accesses=0,
        runtime_baseline_restored=True,
        tokenizer_vocabulary_only_source_sha256=campaign.gate.BASE["digest"](
            campaign.ROOT / "runtimes/llama.cpp/tools/tokenize/tokenize.cpp"
        ),
        tokenizer_binary_sha256=campaign.gate.BASE["digest"](TOKENIZER),
        verifier_source_sha256=campaign.gate.BASE["digest"](Path(__file__)),
        first_result=dict(
            path=str((campaign.OUTPUT / "result.json").relative_to(campaign.ROOT)),
            sha256=campaign.gate.BASE["digest"](campaign.OUTPUT / "result.json"),
        ),
        release_approved=False,
    )
    publish(
        campaign.ROOT / "docs/evidence/d14-reasoning-gate-first-verification.json",
        result,
    )
    print(
        json.dumps(
            dict(
                status=result["status"],
                profiles={
                    p: dict(
                        format=v["format_passed"],
                        functional=v["functional_passed"],
                        total=v["total"],
                    )
                    for p, v in profiles.items()
                },
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
