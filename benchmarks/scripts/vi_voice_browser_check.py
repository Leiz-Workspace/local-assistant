"""Verify six retained public voice inputs through the real local HTTP surface without accessing a microphone."""

import asyncio
import base64
import json
import logging
import time
from uuid import uuid4

import httpx

from apps.voice_trial.audio import encode_wave
from apps.voice_trial.native import AUDIT_ROOT, cuda, original

LOGGER = logging.getLogger(__name__)
ORIGIN = "http://127.0.0.1:8092"


def verify_answer(value, transcript, answer, pcm):
    """Require exact prior ASR/CORE/playback bytes and finite measured HTTP completion within the unchanged maximum."""
    if (
        value.get("transcript") != transcript
        or value.get("answer") != answer
        or base64.b64decode(value["audio_base64"], validate=True) != encode_wave(pcm)
        or type(value.get("server_seconds")) not in (int, float)
        or not 0 < value["server_seconds"] <= 4
    ):
        raise ValueError("voice_HTTP_exact_output_or_latency")
    LOGGER.info("voice_HTTP_answer_verified")


async def run():
    """Perform one explicit preparation and six first public requests, preserving failures and joining release."""
    root = AUDIT_ROOT / "http-native-first"
    root.mkdir(mode=0o700)
    packet = json.loads(original.assets.PACKET.read_text())
    sources = original.retained_sources(original.ROOT, packet)
    prior = cuda.PROJECT / "data/backups/d74-cuda-root-guard-confirmation-first"
    old = json.loads((prior / "result.json").read_text())
    rows = [
        dict(
            id=x["id"], expected_no_answer=x["expected_no_answer"], status="UNATTEMPTED"
        )
        for x in packet["workflow_sources"]
    ]
    receipt = dict(
        description="Actual public-source HTTP preflight; no physical microphone/speaker acceptance or private owner media.",
        rows=rows,
        retries=0,
        physical_first_audible="UNVERIFIED",
        status="NOT_PASS",
    )
    headers = {"Origin": ORIGIN, "X-Voice-Submit": "1"}
    async with httpx.AsyncClient(base_url=ORIGIN, timeout=90) as client:
        assert (await client.get("/")).status_code == 200
        try:
            result = await client.post("/api/prepare", headers=headers)
            if result.status_code != 202:
                raise ValueError("voice_HTTP_prepare")
            deadline = time.monotonic() + 180
            while True:
                state = (await client.get("/api/status")).json()["state"]
                if state == "ready":
                    break
                if state != "preparing" or time.monotonic() >= deadline:
                    raise ValueError("voice_HTTP_not_ready")
                await asyncio.sleep(1)
            for i, row in enumerate(rows):
                raw = encode_wave(sources[row["id"]]["audio"].pcm_s16le)
                operation = str(uuid4())
                started = time.monotonic()
                response = await client.post(
                    "/api/turn",
                    headers=dict(
                        headers,
                        **{"Content-Type": "audio/wav", "X-Voice-ID": operation},
                    ),
                    content=raw,
                )
                row["client_roundtrip_seconds"] = time.monotonic() - started
                value = response.json()
                original.assets.publish(
                    root / f"response-{i}.json",
                    dict(
                        description="First public-source HTTP response only; no credentials or private microphone data.",
                        status_code=response.status_code,
                        body=value,
                    ),
                )
                if row["expected_no_answer"]:
                    if response.status_code != 422 or value != {"code": "no_speech"}:
                        raise ValueError("voice_HTTP_negative")
                    row["status"] = "CORRECT_NO_SPEECH"
                else:
                    if response.status_code != 200 or value.get("id") != operation:
                        raise ValueError("voice_HTTP_speech_response")
                    old_row = next(x for x in old["rows"] if x["source"] == row["id"])
                    directory = prior / "results" / old_row["id"]
                    transcript = json.loads(
                        (directory / "asr-result.json").read_text()
                    )["asr"]["text"]
                    answer = json.loads((directory / "core-response.json").read_text())[
                        "response"
                    ]["choices"][0]["message"]["content"]
                    verify_answer(
                        value,
                        transcript,
                        answer,
                        (directory / "playback.s16le").read_bytes(),
                    )
                    row.update(
                        status="EXACT_COMPLETE_PCM",
                        server_seconds=value["server_seconds"],
                        stages=value["stages"],
                        playback_sha256=original.sha(
                            base64.b64decode(value["audio_base64"])
                        ),
                    )
                LOGGER.info(
                    "voice_HTTP_row_completed index=%d status=%s", i, row["status"]
                )
            receipt["status"] = "PASS"
            receipt["server_status_before_release"] = (
                await client.get("/api/status")
            ).json()
        finally:
            await client.post("/api/release", headers=headers)
            receipt["server_status_after_release"] = (
                await client.get("/api/status")
            ).json()
            original.assets.publish(root / "result.json", receipt)
    LOGGER.info("voice_HTTP_first_preflight_completed")


def main():
    """Run only the fixed local six-input HTTP check with existing data and zero automatic retries."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
