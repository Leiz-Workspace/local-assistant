"""Measure first nonempty native text delta on explicit benchmark replays without changing product streaming."""

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path

import httpx

from apps.api.runtime.presets import build_generation_params, calculate_budget
from apps.api.services.workspace_tools import WorkspaceToolRun
from benchmarks.har008 import ROOT, SKILLS, save_json
from benchmarks.har008_maintenance import load_panel, task_text
from benchmarks.harness_resources import ResourceSampler, process_memory
from src.application.services.skill_contract import parse_manifest
from src.application.services.source_output_contract import (
    NAME,
    quote_catalog,
    response_schema,
    validate_completion,
)

LOGGER = logging.getLogger(__name__)
REPLAY_CASES = (
    "approved-retry-delay",
    "long-maintenance-2",
    "review-safe-cancellation",
    "review-caller-stale-token",
)


class TimingError(Exception):
    """Retain bounded partial streaming evidence while exposing only a finite failure category."""

    def __init__(self, receipt):
        """Keep first partial events available to the owner-private measurement runner."""
        self.receipt = receipt
        super().__init__("stream_timing_failed")


async def measure(client, payload, *, clock=time.monotonic):
    """Time actual streamed text arrival, ignoring role/null chunks and requiring a complete terminal sentinel."""
    if payload.get("stream") is not True or payload.get("max_tokens") != 512:
        raise ValueError("finite_streaming_payload_required")
    start = clock()
    receipt = dict(
        status="INCOMPLETE",
        first_text_delta_seconds=None,
        total_seconds=None,
        events=[],
        content="",
        bytes=0,
    )
    finish = None
    try:
        async with asyncio.timeout(120):
            async with client.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as response:
                response.raise_for_status()
                if "text/event-stream" not in response.headers.get("content-type", ""):
                    raise ValueError("stream_content_type")
                async for line in response.aiter_lines():
                    receipt["bytes"] += len(line.encode())
                    if receipt["bytes"] > 262144 or len(line.encode()) > 65536:
                        raise ValueError("stream_bytes")
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw == "[DONE]":
                        if (
                            finish != "stop"
                            or receipt["first_text_delta_seconds"] is None
                        ):
                            raise ValueError("stream_finish")
                        receipt["total_seconds"] = round(clock() - start, 6)
                        receipt["status"] = "COMPLETE"
                        LOGGER.info(
                            "harness_stream_timing_completed events=%d",
                            len(receipt["events"]),
                        )
                        return receipt
                    event = json.loads(raw)
                    if type(event) is not dict or len(receipt["events"]) >= 1024:
                        raise ValueError("stream_event")
                    receipt["events"].append(event)
                    choices = event.get("choices")
                    if choices == [] and "usage" in event:
                        continue
                    if type(choices) is not list or len(choices) != 1:
                        raise ValueError("stream_choices")
                    choice = choices[0]
                    delta = choice.get("delta", {})
                    if (
                        type(delta) is not dict
                        or delta.get("tool_calls")
                        or delta.get("function_call")
                    ):
                        raise ValueError("stream_tool_call")
                    content = delta.get("content")
                    if content is not None and type(content) is not str:
                        raise ValueError("stream_text")
                    if content:
                        if receipt["first_text_delta_seconds"] is None:
                            receipt["first_text_delta_seconds"] = round(
                                clock() - start, 6
                            )
                        receipt["content"] += content
                    if choice.get("finish_reason") is not None:
                        finish = choice["finish_reason"]
        raise ValueError("stream_missing_done")
    except Exception:
        receipt["total_seconds"] = round(clock() - start, 6)
        LOGGER.warning("harness_stream_timing_failed events=%d", len(receipt["events"]))
        raise TimingError(receipt) from None


async def replay(
    inference,
    workspace_service,
    owner,
    workspace,
    workspace_root,
    quality_directory,
    output,
    *,
    pid,
    sampler_factory=ResourceSampler,
    preflight=process_memory,
    clock=time.monotonic,
):
    """Replay eight predeclared warm native streams with actual snapshots, no semantic regrading and no product changes."""
    quality_directory, output = Path(quality_directory), Path(output)
    quality = json.loads((quality_directory / "frozen-inputs.json").read_text())
    cases = {case["id"]: case for case in load_panel(json.dumps(quality["corpus"]))}
    if quality["workspace_id"] != str(workspace) or any(
        identifier not in cases for identifier in REPLAY_CASES
    ):
        raise ValueError("replay_workspace_or_cases")
    root = Path(workspace_root)
    native = preflight(pid)
    if (native["pid"], native["start_ticks"]) != (
        quality["native_process"]["pid"],
        quality["native_process"]["start_ticks"],
    ):
        raise ValueError("replay_native_process_changed")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    frozen = {
        "description": "Eight predeclared warm streaming timing replays; no semantic score or product streaming claim.",
        "quality_manifest_sha256": hashlib.sha256(
            (quality_directory / "frozen-inputs.json").read_bytes()
        ).hexdigest(),
        "quality": quality,
        "cases": REPLAY_CASES,
        "native_process": native,
        "source_files_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), ROOT / "benchmarks/harness_resources.py")
        },
        "options": dict(
            preset="fast",
            max_tokens=512,
            output_contract=NAME,
            stream=True,
            attempts=8,
            retries=0,
            seconds=1000,
        ),
    }
    save_json(output / "frozen-inputs.json", frozen)
    rows, completed = [], False
    deadline = clock() + 1000
    try:
        for index, identifier in enumerate(REPLAY_CASES):
            case = cases[identifier]
            paths = [
                f"{quality['source_folder']}/{identifier}/{source['path']}"
                for source in case["sources"]
            ]
            for path in paths:
                relative = path.removeprefix(quality["source_folder"] + "/")
                if (
                    hashlib.sha256((root / path).read_bytes()).hexdigest()
                    != quality["source_sha256"][relative]
                ):
                    raise ValueError("replay_source_drift")
            for skill_enabled in (False, True) if index % 2 == 0 else (True, False):
                if clock() >= deadline:
                    raise TimeoutError("replay_deadline")
                reader = WorkspaceToolRun(workspace_service, owner, workspace)
                try:
                    evidence = [
                        await reader.execute(
                            json.dumps(
                                dict(name="workspace.read", arguments=dict(path=path))
                            ).encode()
                        )
                        for path in paths
                    ]
                finally:
                    await reader.close()
                raw_skill = SKILLS[case["skill"]].read_bytes()
                if (
                    hashlib.sha256(raw_skill).hexdigest()
                    != quality["skill_sha256"][case["skill"]]
                ):
                    raise ValueError("replay_skill_drift")
                skill = parse_manifest(raw_skill) if skill_enabled else None
                gateway, fitted, context = await inference.prepare(
                    [dict(role="user", content=task_text(case, paths))],
                    preset="fast",
                    max_tokens=512,
                    skill=skill,
                    evidence=evidence,
                    context_strategy="strict",
                    output_contract=NAME,
                )
                if len(context["included_evidence"]) != len(paths):
                    raise ValueError("replay_omitted_evidence")
                catalog = quote_catalog(evidence, context["included_evidence"])
                plan = calculate_budget(
                    preset="fast",
                    input_tokens=context["input_tokens"],
                    requested_max_tokens=512,
                )
                payload = build_generation_params(plan)
                payload.update(
                    model=gateway.model_id,
                    messages=fitted,
                    temperature=0.7,
                    stream=True,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"schema": response_schema(catalog)},
                    },
                )
                attempt = len(rows) + 1
                save_json(output / f"{attempt:02d}-request.json", payload)
                row = dict(
                    case_id=identifier,
                    arm="constrained_skill"
                    if skill_enabled
                    else "constrained_baseline",
                    input_tokens=context["input_tokens"],
                    semantic_scored=False,
                    context=context,
                    status="INCOMPLETE",
                )
                telemetry = None
                try:
                    with sampler_factory(
                        pid, expected_start=native["start_ticks"]
                    ) as telemetry:
                        async with httpx.AsyncClient(
                            base_url=gateway.base_url,
                            transport=inference.transport,
                            timeout=gateway._timeout(),
                            trust_env=False,
                        ) as client:
                            row["native"] = await measure(client, payload, clock=clock)
                    row["contract"] = validate_completion(
                        dict(
                            choices=[
                                dict(
                                    finish_reason="stop",
                                    message=dict(
                                        role="assistant",
                                        content=row["native"]["content"],
                                    ),
                                )
                            ]
                        ),
                        catalog,
                    )
                    row["status"] = "COMPLETE"
                except TimingError as error:
                    row["native"] = error.receipt
                    raise
                finally:
                    if telemetry is not None and telemetry.thread is not None:
                        row["resources"] = telemetry.report()
                    save_json(output / f"{attempt:02d}-response.json", row)
                rows.append(row)
                LOGGER.info(
                    "harness_stream_replay_completed attempt=%d arm=%s",
                    attempt,
                    row["arm"],
                )
        for name, expected in {
            **quality["source_files_sha256"],
            **frozen["source_files_sha256"],
        }.items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("replay_code_config_drift")
        completed = True
    finally:
        summary = dict(
            status="MEASUREMENT_COMPLETE" if completed else "INCOMPLETE",
            expected_attempts=8,
            completed_attempts=len(rows),
            semantic_scored=False,
            rows=[
                dict(
                    case_id=row["case_id"],
                    arm=row["arm"],
                    input_tokens=row["input_tokens"],
                    first_text_delta_seconds=row["native"]["first_text_delta_seconds"],
                    total_seconds=row["native"]["total_seconds"],
                    resource_status=row["resources"]["status"],
                )
                for row in rows
            ],
            scope="Warm native streaming replay, not task API TTFT or a semantic retry.",
        )
        save_json(output / "summary.json", summary)
    return summary
