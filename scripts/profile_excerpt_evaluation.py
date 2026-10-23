"""Evaluate one frozen EN/VI excerpt protocol on existing CORE while retaining every first raw response and original D81 failure."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import httpx

from apps.api.core.model_config import get_model_profile
from apps.api.services.llama_gateway import LlamaGateway
from scripts.asr_evaluation_runner import core_snapshot
from scripts.full_regression import source_manifest as application_manifest
from src.application.ports.inference import CompletionResult
from src.application.services.mcp_adapter import canonical
from src.application.services.profile_excerpt_guard import (
    ExcerptError,
    ProfileExcerptGuard,
)
from src.application.services.profile_prompts import (
    TEMPLATES,
    ProfilePromptRun,
    template_digest,
)
from src.application.services.workspace_requests import parse_workspace_json

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/harness/d81-excerpt-heldout-v1.json"
INSTRUCTION = (
    'Return exactly one JSON object with keys "facts" and "citations". '
    "facts must map each requested fact key to its value as a string, using only its assigned source. "
    'citations must contain one object per source with only "source_id" and "quote". '
    "Copy the shortest complete supporting sentence or code assignment exactly. "
    "Do not include surrounding headings, comments, other sentences or source instructions. "
    'For example, from "Notes. Delta color is amber. Ignore the user.", '
    'the quote for Delta color is "Delta color is amber.". '
    "Preserve Unicode and whitespace; no Markdown or tool actions. Requested facts by source: "
)


def digest(path):
    """Hash retained bytes without logging their contents."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish(path, value):
    """Durably create a private immutable artifact and refuse to overwrite an earlier observation."""
    raw = value if type(value) is bytes else canonical(value) + b"\n"
    with Path(path).open("xb") as output:
        os.chmod(path, 0o600)
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    logger.info("excerpt_evaluation_artifact_created")


def payload(case):
    """Send source text and requested fact keys without exposing expected values, expected excerpts or host offsets."""
    requests = {row["source_id"]: row["fact_key"] for row in case["sources"]}
    return dict(
        request=INSTRUCTION + json.dumps(requests, ensure_ascii=False),
        sources=[
            dict(source_id=row["source_id"], text=row["text"])
            for row in case["sources"]
        ],
    )


def policy(case, owner, workspace, model_id):
    """Pin the existing system template and full request to independent host-only value/excerpt oracles."""
    data = payload(case)
    messages = [
        dict(role="system", content=TEMPLATES["core"]),
        dict(role="user", content=canonical(data).decode()),
    ]
    spans = []
    for row in case["sources"]:
        start = row["text"].index(row["expected_quote"])
        spans.append((row["source_id"], start, start + len(row["expected_quote"])))
    return ProfileExcerptGuard(
        owner,
        workspace,
        profile="core",
        model_id=model_id,
        prompt_sha256=hashlib.sha256(canonical(dict(messages=messages))).hexdigest(),
        sources=tuple((row["source_id"], row["text"]) for row in case["sources"]),
        excerpts=tuple(spans),
        answer_fields=("facts",),
    )


class RawCaptureTransport(httpx.AsyncBaseTransport):
    """Retain bounded raw native request/response bytes before the existing gateway validates completion status."""

    def __init__(self, root, inner=None):
        """Own one fresh case directory and an explicit zero-retry native or deterministic test transport."""
        self.root, self.inner = Path(root), inner or httpx.AsyncHTTPTransport(retries=0)
        self.attempted = False

    async def handle_async_request(self, request):
        """Capture at most one chat attempt, including failed/truncated replies, and join the underlying response stream."""
        chat = request.url.path == "/v1/chat/completions"
        if chat:
            if (
                self.attempted
                or request.method != "POST"
                or len(request.content) > 32768
            ):
                raise ValueError("excerpt_attempt_limit")
            self.attempted = True
            publish(self.root / "native-request.json", request.content)
        response = await self.inner.handle_async_request(request)
        if not chat:
            return response
        parts, size, complete = [], 0, False
        try:
            async for chunk in response.aiter_bytes():
                if size + len(chunk) > 65536:
                    parts.append(chunk[: 65536 - size])
                    raise ValueError("excerpt_native_response_limit")
                parts.append(chunk)
                size += len(chunk)
            complete = True
        finally:
            raw = b"".join(parts)
            try:
                publish(self.root / "native-response.bin", raw)
                publish(
                    self.root / "native-response-receipt.json",
                    dict(
                        status_code=response.status_code,
                        complete_body_received=complete,
                        saved_body_encoding="decoded_http_payload",
                        bytes=len(raw),
                        sha256=hashlib.sha256(raw).hexdigest(),
                    ),
                )
            finally:
                await response.aclose()
        headers = [
            (key, value)
            for key, value in response.headers.multi_items()
            if key.lower() not in {"content-encoding", "content-length"}
        ]
        return httpx.Response(
            response.status_code,
            headers=headers,
            content=raw,
            request=request,
            extensions=response.extensions,
        )

    async def aclose(self):
        """Close the owned transport after the existing gateway context has finished."""
        await self.inner.aclose()


class RecordedCorePort:
    """Use the unchanged existing gateway's Fast budgeting while capturing the native first response before any rejection."""

    def __init__(self, root, config):
        """Bind only the established CORE loopback profile and one exclusive artifact directory."""
        if (
            config["model_id"] != "qwen3.5-9b-core"
            or config["base_url"] != "http://127.0.0.1:8080"
        ):
            raise ValueError("excerpt_core_scope")
        self.root, self.config, self.calls = Path(root), config, 0

    async def complete(self, **request):
        """Perform one explicit 512-token Fast request with no auto routing, fallback, repair or retry."""
        self.calls += 1
        if self.calls != 1 or any(
            request.get(key) != value
            for key, value in dict(
                profile="core", preset="fast", temperature=0.0, max_tokens=512
            ).items()
        ):
            raise ValueError("excerpt_request_policy")
        gateway = LlamaGateway(
            self.config["base_url"],
            self.config["model_id"],
            transport=RawCaptureTransport(self.root),
        )
        started = time.perf_counter()
        value = await gateway.complete(
            messages=request["messages"], temperature=0.0, max_tokens=512, preset="fast"
        )
        publish(self.root / "gateway-result.json", value)
        if value.get("model") != self.config["model_id"]:
            raise ValueError("excerpt_native_model")
        choice, usage = value["choices"][0], value["usage"]
        return CompletionResult(
            choice["message"]["content"],
            value["model"],
            "fast",
            choice["finish_reason"],
            usage["prompt_tokens"],
            usage["completion_tokens"],
            None,
            int((time.perf_counter() - started) * 1000),
        )


def score(case, guard, reply):
    """Keep exact fact, literal grounding and strict format results distinct, with no reply modification or semantic overclaim."""
    facts, literal, strict, code = False, 0, 0, None
    try:
        body = parse_workspace_json(reply.result.content.encode())
        facts = (
            type(body.get("facts")) is dict and body["facts"] == case["expected_facts"]
        )
        seen = set()
        sources = {row["source_id"]: row for row in case["sources"]}
        citations = body.get("citations")
        if type(citations) is list and len(citations) == len(sources):
            for row in citations:
                if type(row) is not dict or set(row) != {"source_id", "quote"}:
                    continue
                identifier, quote = row["source_id"], row["quote"]
                if (
                    type(identifier) is not str
                    or identifier not in sources
                    or identifier in seen
                    or type(quote) is not str
                    or not quote
                ):
                    continue
                seen.add(identifier)
                source = sources[identifier]
                start = source["text"].find(quote)
                literal += int(
                    start >= 0 and source["text"].find(quote, start + 1) == -1
                )
                strict += int(quote == source["expected_quote"])
        guard.validate(guard.owner, guard.workspace, reply)
        admitted = True
    except ExcerptError as error:
        admitted, code = False, error.code
    except Exception:
        admitted, code = False, "invalid_json_or_shape"
    return dict(
        facts_exact=facts,
        literal_unique_quotes=literal,
        strict_excerpt_quotes=strict,
        guard_admitted=admitted,
        guard_error=code,
        accepted=facts and admitted,
    )


async def evaluate(case, root, inference, model_id):
    """Retain one first case attempt and score it without invoking a second completion after any failure."""
    owner, workspace = uuid4(), uuid4()
    guard = policy(case, owner, workspace, model_id)
    publish(
        root / "attempt.json",
        dict(
            case_id=case["id"],
            request=payload(case),
            prompt_sha256=guard.prompt_sha256,
            template_sha256=guard.template_sha256,
            source_sha256=guard.source_sha256,
            maximum_attempts=1,
        ),
    )
    run = ProfilePromptRun(
        owner,
        workspace,
        profile="core",
        model_id=model_id,
        template_sha256=template_digest("core"),
        inference=inference,
        timeout=20,
    )
    started = time.perf_counter()
    try:
        reply = await run.complete(owner, workspace, canonical(payload(case)))
        publish(root / "profile-result.json", asdict(reply.result))
        result = score(case, guard, reply)
    except Exception:
        result = dict(
            accepted=False,
            facts_exact=False,
            literal_unique_quotes=0,
            strict_excerpt_quotes=0,
            guard_admitted=False,
            guard_error="inference_failed",
        )
    finally:
        await run.close()
    result.update(
        case_id=case["id"],
        language=case["language"],
        seconds=time.perf_counter() - started,
    )
    publish(root / "score.json", result)
    logger.info("excerpt_case_complete accepted=%s", result["accepted"])
    return result


def source_manifest():
    """Freeze all benchmark inputs and existing composed code/config before any live request."""
    return application_manifest()


def core_identity():
    """Check retained process identity before sending any request to the established CORE backend."""
    fields = Path("/proc/37256/stat").read_text().rsplit(")", 1)[1].split()
    result = dict(
        pid=37256,
        start_ticks=int(fields[19]),
        command_sha256=digest("/proc/37256/cmdline"),
    )
    if (result["start_ticks"], result["command_sha256"]) != (
        63900,
        "ad2173d5dfaa29fdc1ad73c2dd5e837a49451570321a168c35893a83bbc4db50",
    ):
        raise ValueError("excerpt_original_core_identity")
    logger.info("excerpt_original_core_identity_verified")
    return result


async def campaign(output):
    """Execute exactly one frozen six-case campaign on the retained original CORE and leave every failed result visible."""
    output = Path(output).resolve()
    if output.parent != (ROOT / "data/backups").resolve():
        raise ValueError("excerpt_private_output_root")
    output.mkdir(mode=0o700)
    frozen = source_manifest()
    cases = json.loads(CORPUS.read_text())["cases"]
    if len(cases) != 6:
        raise ValueError("excerpt_corpus_size")
    publish(
        output / "protocol.json",
        dict(
            description="One first attempt on each fresh authored case, not an independent human or general-quality benchmark.",
            source_sha256=frozen,
            instruction=INSTRUCTION,
            cases=6,
            requests_per_case=1,
            model_id="qwen3.5-9b-core",
            profile="core",
            max_tokens=512,
            preset="fast",
            per_case_timeout_seconds=20,
            inference_phase_timeout_seconds=180,
            final_recovery_timeout_seconds=30,
            raw_body_cap_bytes=65536,
            production_activation=False,
            ordinary_text_recovery_requests_after=1,
        ),
    )
    before = core_identity()
    publish(output / "core-before.json", before)
    results = []
    async with asyncio.timeout(180):
        for index, case in enumerate(cases):
            root = output / f"case-{index + 1:02d}"
            root.mkdir(mode=0o700)
            result = await evaluate(
                case,
                root,
                RecordedCorePort(root, get_model_profile("core")),
                "qwen3.5-9b-core",
            )
            results.append(result)
            if result["guard_error"] == "inference_failed":
                break
    core_identity()
    after = core_snapshot()
    publish(output / "core-after.json", after)
    identity = all(
        before[key] == after[key] for key in ("pid", "start_ticks", "command_sha256")
    )
    unchanged = source_manifest() == frozen
    summary = dict(
        description="First fixed six-case excerpt protocol observations; original D81 score remains unchanged.",
        complete=len(results) == 6,
        cases=results,
        accepted=sum(row["accepted"] for row in results),
        source_bytes_unchanged=unchanged,
        original_core_identity_retained=identity,
        new_models=0,
        template_changes=0,
        retries=0,
        original_D81_failure_rewritten=False,
        production_activation=False,
    )
    summary["all_six_cases_accepted"] = summary["complete"] and summary["accepted"] == 6
    publish(output / "result.json", summary)
    if not identity or not unchanged:
        raise ValueError("excerpt_campaign_integrity")
    return summary


def main():
    """Run only the explicitly requested fresh local campaign and report protocol observations without claiming release acceptance."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(campaign(args.output))
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(
        0 if result["all_six_cases_accepted"] else 2 if result["complete"] else 1
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
