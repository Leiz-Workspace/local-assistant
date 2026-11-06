"""Measure one explicit existing CORE text stream with honest client first-content timing and optional native server timing provenance."""

import asyncio
import hashlib
import json
import logging
import math
import time

import httpx

from apps.api.core.model_config import get_model_profile
from apps.api.services.llama_gateway import LlamaGateway
from src.application.services.workspace_requests import parse_workspace_json

logger = logging.getLogger(__name__)


class TimingError(Exception):
    """Expose a finite streaming probe failure without copying model/server/request contents."""

    def __init__(self):
        """Keep timing probe failure diagnostics content-free and recognizable in audit logs."""
        super().__init__("stream_timing_invalid")
        logger.warning("stream_timing_rejected")


async def measure(lines, *, model_id, started, clock=time.perf_counter):
    """Consume finite complete SSE text while retaining only content hashes, client timing and verified native usage counters."""
    if type(started) not in (float, int) or not math.isfinite(started) or started < 0:
        raise TimingError()
    first, last, usage, native, finished, done = None, None, None, None, False, False
    content_hash = hashlib.sha256()
    size, chunks = 0, 0
    try:
        async for line in lines:
            size += len(line.encode("utf-8"))
            if size > 65536:
                raise TimingError()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data: ") or done:
                raise TimingError()
            data = line[6:]
            if data == "[DONE]":
                done = True
                break
            value = parse_workspace_json(data.encode())
            if value.get("model") != model_id:
                raise TimingError()
            choices = value.get("choices")
            if type(choices) is not list or len(choices) > 1:
                raise TimingError()
            if choices:
                choice = choices[0]
                if (
                    type(choice) is not dict
                    or type(choice.get("index")) is not int
                    or choice["index"] != 0
                ):
                    raise TimingError()
                delta = choice.get("delta")
                if type(delta) is not dict or any(
                    key not in {"role", "content"} for key in delta
                ):
                    raise TimingError()
                content = delta.get("content")
                if content is not None and type(content) is not str:
                    raise TimingError()
                if content:
                    if finished:
                        raise TimingError()
                    point = clock()
                    if (
                        type(point) not in (float, int)
                        or not math.isfinite(point)
                        or point < started
                        or (last is not None and point < last)
                    ):
                        raise TimingError()
                    first = point if first is None else first
                    last = point
                    chunks += 1
                    content_hash.update(content.encode("utf-8"))
                reason = choice.get("finish_reason")
                if reason is not None:
                    if reason != "stop" or finished:
                        raise TimingError()
                    finished = True
            if value.get("usage") is not None:
                if usage is not None:
                    raise TimingError()
                candidate = value["usage"]
                if type(candidate) is not dict or any(
                    type(candidate.get(key)) is not int or candidate[key] < 0
                    for key in ("prompt_tokens", "completion_tokens")
                ):
                    raise TimingError()
                usage = {
                    key: candidate[key]
                    for key in ("prompt_tokens", "completion_tokens")
                }
            if value.get("timings") is not None:
                candidate = value["timings"]
                if type(candidate) is not dict:
                    raise TimingError()
                rate = candidate.get("predicted_per_second")
                if rate is not None:
                    if (
                        type(rate) not in (int, float)
                        or not math.isfinite(rate)
                        or rate <= 0
                    ):
                        raise TimingError()
                    native = float(rate)
        end = clock()
        if (
            not done
            or not finished
            or first is None
            or usage is None
            or usage["completion_tokens"] <= 0
            or type(end) not in (int, float)
            or not math.isfinite(end)
            or end < last
        ):
            raise TimingError()
        result = dict(
            description="Client observed first nonempty text content, not first SSE event. Buffered/chunked transport and network overhead included.",
            model_id=model_id,
            finish_reason="stop",
            content_sha256=content_hash.hexdigest(),
            content_chunks=chunks,
            input_tokens=usage["prompt_tokens"],
            output_tokens=usage["completion_tokens"],
            client_ttft_ms=(first - started) * 1000,
            client_total_ms=(end - started) * 1000,
            client_end_to_end_tokens_per_second=usage["completion_tokens"]
            / (end - started)
            if end > started
            else None,
            native_reported_decode_tokens_per_second=native,
            native_rate_availability="server_reported"
            if native is not None
            else "not_provided",
            client_decode_tokens_per_second=None,
            client_decode_availability="token_boundaries_not_observed",
        )
        logger.info(
            "stream_timing_complete chunks=%d native_rate_available=%s",
            chunks,
            native is not None,
        )
        return result
    except TimingError:
        raise
    except Exception:
        raise TimingError() from None


async def probe():
    """Verify the already loaded original CORE model and perform one bounded neutral stream without model/default changes."""
    config = get_model_profile("core")
    gateway = LlamaGateway(base_url=config["base_url"], model_id=config["model_id"])
    async with httpx.AsyncClient(
        base_url=config["base_url"], timeout=30, trust_env=False, follow_redirects=False
    ) as client:
        await gateway._verify_model(client)
        payload = dict(
            model=config["model_id"],
            messages=[
                dict(
                    role="user",
                    content="Write one short sentence saying that the Cedar fixture is blue.",
                )
            ],
            temperature=0,
            max_tokens=512,
            stream=True,
            stream_options=dict(include_usage=True),
            chat_template_kwargs=dict(enable_thinking=False),
        )
        async with asyncio.timeout(30):
            started = time.perf_counter()
            async with client.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as response:
                response.raise_for_status()
                if (
                    response.headers.get("content-type", "").split(";", 1)[0]
                    != "text/event-stream"
                ):
                    raise TimingError()
                return await measure(
                    response.aiter_lines(), model_id=config["model_id"], started=started
                )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(asyncio.run(probe()), sort_keys=True))
