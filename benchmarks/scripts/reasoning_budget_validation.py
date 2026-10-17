
"""
Reasoning budget validation for pinned llama.cpp.

Run:
    uv run python benchmarks/scripts/reasoning_budget_validation.py

Directly tests llama-server, without FastAPI.
Produces a machine-readable JSON report.

Important:
- A naturally short reasoning trace cannot prove a hard cap.
- Tokenizing reasoning_content is an approximation.
- Do not claim hard-cap PASS solely from HTTP 200 or metadata.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


BASE_URL = "http://127.0.0.1:8080"
MODEL_ID = "qwen3.5-9b-core"
OUTPUT = Path(
    "benchmarks/results/runtime/reasoning-budget.json"
)

BUDGETS = [64, 256, 512, 4096, 8192]

PROMPT = (
    "Analyze the following complex software design problem "
    "carefully before answering. A distributed task engine "
    "has 12 workers, at-least-once message delivery, "
    "intermittent network partitions, duplicate tool calls, "
    "non-idempotent payments, versioned shared state, "
    "crash recovery, and an append-only audit log. "
    "Develop a correctness argument addressing safety, "
    "liveness, exactly-once business effects, retries, "
    "fencing tokens, durable transactions, ordering, "
    "checkpoint consistency, and concurrent updates. "
    "Consider counterexamples and revise the proposed "
    "design wherever the invariants fail. "
    "Conclude with the five most important invariants."
)


def count_visible_tokens(client, text):
    """Approximate reasoning token count using /tokenize."""
    if not text:
        return 0

    response = client.post(
        "/tokenize",
        json={
            "content": text,
            "add_special": False,
        },
    )
    response.raise_for_status()
    return len(response.json()["tokens"])


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    results = []

    with httpx.Client(
        base_url=BASE_URL,
        timeout=httpx.Timeout(
            connect=5,
            read=900,
            write=60,
            pool=5,
        ),
        trust_env=False,
    ) as client:

        models = client.get("/v1/models")
        models.raise_for_status()

        loaded = [
            item["id"]
            for item in models.json().get("data", [])
        ]

        if MODEL_ID not in loaded:
            raise RuntimeError(
                f"Expected {MODEL_ID}, loaded {loaded}"
            )

        for budget in BUDGETS:
            print(
                f"\n=== REASONING BUDGET {budget} ===",
                flush=True,
            )

            payload = {
                "model": MODEL_ID,
                "messages": [
                    {
                        "role": "user",
                        "content": PROMPT,
                    }
                ],
                "temperature": 0,
                "stream": False,
                "max_tokens": budget + 1024,
                "chat_template_kwargs": {
                    "enable_thinking": True,
                },
                "thinking_budget_tokens": budget,
            }

            started = time.perf_counter()

            try:
                response = client.post(
                    "/v1/chat/completions",
                    json=payload,
                )

                elapsed = time.perf_counter() - started
                response.raise_for_status()
                data = response.json()

                choice = data["choices"][0]
                message = choice["message"]

                reasoning = (
                    message.get("reasoning_content") or ""
                )
                answer = message.get("content") or ""

                visible_tokens = count_visible_tokens(
                    client, reasoning
                )

                # Visible-token overage is a warning, not
                # conclusive proof about internal counters.
                near_cap = (
                    visible_tokens >= budget * 0.8
                )

                row = {
                    "budget": budget,
                    "http": response.status_code,
                    "elapsed_seconds": round(elapsed, 2),
                    "finish_reason": choice.get(
                        "finish_reason"
                    ),
                    "completion_tokens": (
                        data.get("usage", {})
                        .get("completion_tokens")
                    ),
                    "reasoning_visible_tokens": (
                        visible_tokens
                    ),
                    "reasoning_characters": len(reasoning),
                    "has_final_answer": bool(answer.strip()),
                    "near_budget": near_cap,
                    "answer_preview": answer[:250],
                }

                results.append(row)

                for key, value in row.items():
                    print(f"{key}: {value}", flush=True)

            except (
                httpx.HTTPError,
                ValueError,
                KeyError,
                IndexError,
                TypeError,
            ) as exc:
                row = {
                    "budget": budget,
                    "error": str(exc),
                }
                results.append(row)
                print("ERROR:", exc, flush=True)

            # Save after every case so an interrupted run
            # still preserves completed measurements.
            OUTPUT.write_text(
                json.dumps(
                    {
                        "model": MODEL_ID,
                        "timestamp": datetime.now(
                            timezone.utc
                        ).isoformat(),
                        "results": results,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    print("\nSAVED:", OUTPUT)


if __name__ == "__main__":
    main()
