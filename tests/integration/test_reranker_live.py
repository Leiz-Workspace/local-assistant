"""Verify actual pinned CPU reranker comparison, tokenizer boundaries and owned process/resource failure cleanup."""

import asyncio
import json
import multiprocessing
import os
import signal
import time
from pathlib import Path

import pytest

from scripts.reranker_comparison import RerankerEvaluation, build_request, compare_reply


@pytest.fixture(autouse=True)
def require_actual_reranker():
    """Require the existing explicit model-evaluation flag without introducing credential-based acceptance skips."""
    if os.environ.get("LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE") != "1":
        pytest.skip("explicit actual CPU model evaluation flag required")


@pytest.mark.asyncio
async def test_actual_pinned_reranker_paired_comparison():
    """Retain complete actual scores/resources and every failed gate without asserting that the candidate wins."""
    request = build_request()
    reply = await RerankerEvaluation().run(request)
    result = compare_reply(request, reply)
    path = Path("data/backups/d27-t02-latest-comparison.json")
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(json.dumps(result, indent=2) + "\n")
    assert result["complete"] and result["rankings_stable"]
    assert result["all_resource_gates_met"]
    assert len(result["runs"]) == 3 and len(result["actual_worker"]["rounds"][0]) == 36
    assert (
        not result["adoption_authorized"]
        and not result["production_configuration_changed"]
    )


def group_members(group):
    """Inspect only live members/RSS of the explicitly owned acceptance process group."""
    result = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) == group and fields[0] != "Z":
                pages = int((entry / "statm").read_text().split()[1])
                result.append((int(entry.name), pages * os.sysconf("SC_PAGE_SIZE")))
        except (OSError, ValueError, IndexError):
            pass
    return result


@pytest.mark.parametrize("mode", ["cancel", "timeout"])
@pytest.mark.asyncio
async def test_actual_candidate_cancel_or_timeout_reaps_group(monkeypatch, mode):
    """Exercise actual isolated worker interruption and join owned uv/model processes before admission release."""
    from scripts import reranker_comparison as module

    original = asyncio.create_subprocess_exec
    launched = asyncio.Event()
    children = []

    async def capture(*args, **kwargs):
        """Retain the real process handle without altering its environment or executable."""
        child = await original(*args, **kwargs)
        children.append(child)
        launched.set()
        return child

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", capture)
    adapter = RerankerEvaluation(timeout=0.05 if mode == "timeout" else 600)
    task = asyncio.create_task(adapter.run(build_request()))
    await launched.wait()
    if mode == "cancel":
        task.cancel()
    with pytest.raises((ValueError, asyncio.CancelledError)):
        await task
    assert children[0].returncode is not None and not adapter.admission.locked()
    assert not group_members(children[0].pid)


def candidate_parent(connection):
    """Run a real candidate API-side parent and expose only its owned process-group PID to the kill test."""
    from scripts import reranker_comparison as module

    async def run():
        """Launch the actual locked worker and preserve its exact parent supervision contract."""
        original = asyncio.create_subprocess_exec

        async def capture(*args, **kwargs):
            """Report only the actual process identifier after the owned session starts."""
            child = await original(*args, **kwargs)
            connection.send(child.pid)
            return child

        module.asyncio.create_subprocess_exec = capture
        await RerankerEvaluation().run(build_request())

    asyncio.run(run())


@pytest.mark.asyncio
async def test_actual_parent_sigkill_stops_candidate_group():
    """Kill an API-side parent during actual model initialization and verify no live orphan candidate remains."""
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=candidate_parent, args=(child,))
    process.start()
    child.close()
    group = None
    try:
        assert await asyncio.to_thread(parent.poll, 10)
        group = parent.recv()
        for _ in range(200):
            if any(rss > 64 * 1024**2 for pid, rss in group_members(group)):
                break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError("candidate did not reach supervised initialization")
        os.kill(process.pid, signal.SIGKILL)
        await asyncio.to_thread(process.join, 5)
        assert process.exitcode == -signal.SIGKILL
        for _ in range(100):
            if not group_members(group):
                break
            await asyncio.sleep(0.05)
        assert not group_members(group)
    finally:
        if process.is_alive():
            process.kill()
            await asyncio.to_thread(process.join, 5)
        if group is not None:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        parent.close()


def rss_probe():
    """Run only the watchdog with a deliberately tiny fault-test budget to prove physical kill enforcement."""
    from scripts.qwen_reranker_worker import supervise_rss

    supervise_rss(1)
    time.sleep(5)


def query_deadline_probe(request):
    """Block a fake pair computation under the actual per-query watchdog without loading any model."""
    from scripts import qwen_reranker_runtime as runtime
    from scripts.qwen_reranker_worker import measure

    original = runtime.profile

    def configuration():
        """Apply only a short fault-test deadline in the isolated child process."""
        result = original()
        result["max_query_seconds"] = 0.05
        return result

    class BlockedModel:
        """Represent an unresponsive computation for watchdog testing only, never quality measurement."""

        def __init__(self, profile):
            """Avoid loading weights for a pure deadline enforcement fault."""
            pass

        def reference_parity(self, query, document):
            """Avoid model work for an isolated timer-only fault fixture."""
            return dict(exact=True, reference_logits=[0, 0], optimized_logits=[0, 0])

        def score_batch(self, query, documents):
            """Block long enough that the real timer must terminate this process."""
            time.sleep(5)

    runtime.profile = configuration
    runtime.QwenRerankerCpu = BlockedModel
    measure(request)


@pytest.mark.parametrize("kind", ["rss", "query"])
def test_actual_watchdogs_kill_budget_violation(kind):
    """Verify real OS termination for controlled RAM/query deadline faults without allocating4GiB or waiting60s."""
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=rss_probe if kind == "rss" else query_deadline_probe,
        args=() if kind == "rss" else (build_request(),),
    )
    process.start()
    try:
        process.join(5)
        assert not process.is_alive() and process.exitcode == -signal.SIGKILL
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)


def test_actual_complete_tokenizer_512_513_boundary():
    """Count real pinned token IDs across the complete official prefix/pair/suffix and reject513 without truncation."""
    from tokenizers import Tokenizer

    from scripts.embedding_runtime import artifact_path, digest_file
    from scripts.qwen_reranker_runtime import pair_tokens, profile

    configuration = profile()
    artifact = next(
        a for a in configuration["artifacts"] if a["local"] == "tokenizer.json"
    )
    path = artifact_path(configuration, artifact)
    assert digest_file(path) == artifact["sha256"]
    tokenizer = Tokenizer.from_file(str(path))

    class Adapter:
        """Expose the exact pinned fast tokenizer without importing Torch into the test process."""

        def encode(self, text, **options):
            """Require complete untruncated tokenization with no extra special-token insertion."""
            assert options == dict(add_special_tokens=False, truncation=False)
            return tokenizer.encode(text, add_special_tokens=False).ids

    boundary = None
    for count in range(350, 513):
        if (
            len(pair_tokens(Adapter(), " x" * count, "document", max_tokens=4096))
            == 512
        ):
            boundary = count
            break
    assert boundary is not None
    assert len(pair_tokens(Adapter(), " x" * boundary, "document")) == 512
    with pytest.raises(ValueError, match="reranker_pair_token_limit"):
        pair_tokens(Adapter(), " x" * (boundary + 1), "document")
