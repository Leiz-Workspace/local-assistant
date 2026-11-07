"""Verify retained-panel declaration and truthful native acceptance rules without starting any model campaign."""

import base64

import pytest

from types import SimpleNamespace

from benchmarks.scripts.main_voice_integration import (
    CORE_RSS_STOP,
    FOREIGN_VRAM_LIMIT,
    SHUTDOWN_EVENTS,
    audit_summary,
    clean_worker_joins,
    graceful_web_exit,
    preflight,
    retain_audit,
    review_rows,
    verify_answer,
    verify_cleanup,
)


def test_panel_preserves_six_exact_existing_inputs():
    """Keep all four public VI speech and two original no-speech cases, their order and PCM bindings."""
    rows = review_rows()
    assert [x["id"] for x in rows] == [
        "heldout-vi_vn-0036",
        "heldout-vi_vn-0024",
        "heldout-vi_vn-0078",
        "heldout-vi_vn-0040",
        "negative-1",
        "negative-3",
    ]
    assert [x["expected_no_answer"] for x in rows] == [
        False,
        False,
        False,
        False,
        True,
        True,
    ]
    assert all(len(x["pcm_sha256"]) == 64 for x in rows)


@pytest.mark.parametrize(
    "change",
    [
        {"answer": "changed"},
        {"transcript": "changed"},
        {"audio_base64": base64.b64encode(b"changed").decode()},
        {"server_seconds": 4.001},
        {"server_seconds": float("nan")},
        {"server_seconds": True},
    ],
)
def test_actual_acceptance_refuses_wrong_output_or_clock(change):
    """Never relabel output drift or a failed complete-response threshold as an integration PASS."""
    old = dict(
        answer="neutral answer",
        transcript="neutral text",
        audio_base64=base64.b64encode(b"neutral audio").decode(),
    )
    actual = dict(old, server_seconds=3.0)
    verify_answer(actual, old, 3.1)
    with pytest.raises(ValueError):
        verify_answer(dict(actual, **change), old, 3.1)
    with pytest.raises(ValueError):
        verify_answer(actual, old, 4.001)


def test_preflight_records_desktop_gpu_and_core_headroom():
    """ADR176: proceed only with CORE headroom and small foreign GPU use, recording both."""
    rows = [
        SimpleNamespace(pid=10, usedGpuMemory=8 * 1024**3),
        SimpleNamespace(pid=20, usedGpuMemory=213 * 1024**2),
        SimpleNamespace(pid=21, usedGpuMemory=272 * 1024**2),
    ]
    assert preflight(2 * 1024**3, rows, {10}) == dict(
        core_rss_bytes=2 * 1024**3,
        foreign_gpu_processes=2,
        foreign_gpu_bytes=485 * 1024**2,
    )


@pytest.mark.parametrize(
    "core_rss, rows, code",
    [
        (CORE_RSS_STOP, [], "main_voice_preflight_core_rss"),
        (None, [], "main_voice_preflight_core_rss"),
        (
            1024**3,
            [SimpleNamespace(pid=30, usedGpuMemory=FOREIGN_VRAM_LIMIT + 1)],
            "main_voice_preflight_foreign_gpu",
        ),
        (
            1024**3,
            [SimpleNamespace(pid=30, usedGpuMemory=None)],
            "main_voice_preflight_foreign_gpu",
        ),
    ],
)
def test_preflight_stops_before_any_voice_model(core_rss, rows, code):
    """Stop with a finite code instead of spending the single panel on a known-bad host state."""
    with pytest.raises(ValueError, match=code):
        preflight(core_rss, rows, {10})


def line(level, logger, message):
    """Format one neutral audit line exactly like apps/api/core/logging_config.py."""
    return f"2026-11-06 17:46:20,868 {level} {logger} {message}"


def shutdown_audit(events=SHUTDOWN_EVENTS, extra=(), prefix=(), between=()):
    """Build a neutral application audit in the runtime log format without private evidence."""
    lines = [
        *prefix,
        line("INFO", "src.infrastructure.voice.core", "voice_borrowed_core_quiescent"),
        line(
            "WARNING",
            "src.application.services.voice_pipeline",
            "voice_operation_failed code=no_speech",
        ),
    ]
    for index, event in enumerate(events):
        lines.append(line("INFO", "module.name", event))
        if index == 1:
            lines += between
    return "\n".join([*lines, *extra]) + "\n"


@pytest.mark.parametrize("returncode", [0, -15])
def test_graceful_exit_accepts_clean_and_reraised_sigterm(returncode):
    """Accept uvicorn's re-raised SIGTERM only like a clean exit, after the complete ordered shutdown."""
    assert graceful_web_exit(returncode, shutdown_audit())


@pytest.mark.parametrize("returncode", [0, -15])
def test_graceful_exit_allows_other_loggers_between_shutdown_events(returncode):
    """Keep a real shutdown valid when legacy lifespan INFO or WARNING lines interleave the voice events."""
    between = [
        line(
            "INFO",
            "src.application.services.vision_chat",
            "image_chat_shutdown_complete",
        ),
        line("WARNING", "apps.api.storage.lifecycle", "neutral_warning"),
    ]
    assert graceful_web_exit(returncode, shutdown_audit(between=between))


@pytest.mark.parametrize("returncode", [1, -9, -2, 15, None, True, -15.0, "0"])
def test_graceful_exit_refuses_other_exit_codes(returncode):
    """Never treat a crash, kill, interrupt or non-integer code as a graceful application shutdown."""
    assert not graceful_web_exit(returncode, shutdown_audit())


@pytest.mark.parametrize(
    "audit",
    [
        "",
        shutdown_audit(SHUTDOWN_EVENTS[:-1]),
        shutdown_audit(SHUTDOWN_EVENTS[1:]),
        shutdown_audit(SHUTDOWN_EVENTS[::-1]),
        shutdown_audit((*SHUTDOWN_EVENTS, SHUTDOWN_EVENTS[0])),
        shutdown_audit(
            extra=[line("ERROR", "apps.api.voice", "voice_shutdown_quarantined")]
        ),
        shutdown_audit(extra=["Traceback (most recent call last):"]),
        shutdown_audit(extra=[line("ERROR", "module.name", "failure")]),
        shutdown_audit(extra=[line("CRITICAL", "module.name", "failure")]),
        shutdown_audit(extra=["ERROR:    Application shutdown failed. Exiting."]),
        shutdown_audit(prefix=[line("ERROR", "module.name", "failure")]),
        shutdown_audit(prefix=["Traceback (most recent call last):"]),
        shutdown_audit(prefix=["ERROR:    Exception in ASGI application"]),
        shutdown_audit().replace(" INFO ", " DEBUG "),
        shutdown_audit().replace(
            "voice_manifest_closed", "voice_manifest_closed extra"
        ),
    ],
)
def test_graceful_exit_requires_complete_error_free_shutdown(audit):
    """Refuse a missing, reordered, duplicated or failed shutdown anywhere in the audit, whatever the exit code."""
    assert not graceful_web_exit(-15, audit)
    assert not graceful_web_exit(0, audit)


def joins(*rows):
    """Format native worker join lines exactly as the IPC worker logs them."""
    return [
        line(
            "INFO",
            "src.infrastructure.voice.ipc",
            f"voice_native_worker_joined role={role} exit={code} forced={forced}",
        )
        for role, code, forced in rows
    ]


CLEAN_JOINS = joins(
    ("turbo", 0, False), ("qwen3-asr-0.6b", 0, False), ("vad", 0, False)
)


def test_clean_worker_joins_accepts_handshake_exits():
    """Accept three distinct workers that each closed by handshake and exited 0."""
    assert clean_worker_joins("\n".join(CLEAN_JOINS) + "\n")


@pytest.mark.parametrize(
    "rows",
    [
        [],
        CLEAN_JOINS[:2] + joins(("vad", 0, True)),
        CLEAN_JOINS[:2] + joins(("vad", -9, True)),
        CLEAN_JOINS[:2] + joins(("vad", 1, False)),
        CLEAN_JOINS[:2] + joins(("vad", -15, False)),
        CLEAN_JOINS[:2] + joins(("turbo", 0, False)),
        CLEAN_JOINS + ["voice_native_worker_joined role=vad exit=0 forced=False"],
        CLEAN_JOINS[:2] + [CLEAN_JOINS[2] + " extra"],
    ],
)
def test_clean_worker_joins_refuses_forced_failed_or_duplicate_joins(rows):
    """Never count a forced kill, nonzero exit, duplicate role or malformed join as a clean worker join."""
    assert not clean_worker_joins("\n".join(rows) + "\n")


def full_audit():
    """Combine budgeted stage admissions, readiness, clean joins and the ordered shutdown."""
    calls = dict(vad=6, asr=4, core=4, tts=4)
    lines = [
        line(
            "INFO",
            "src.infrastructure.voice.native",
            f"main_voice_stage_admitted stage={kind} count={index + 1}",
        )
        for kind, total in calls.items()
        for index in range(total)
    ]
    lines.append(
        line(
            "INFO",
            "src.infrastructure.voice.native",
            "voice_readiness_verified model_calls=1",
        )
    )
    return "\n".join([*lines, *CLEAN_JOINS]) + "\n" + shutdown_audit()


class Core:
    """Record whether the borrowed CORE check is reached and report its state."""

    def __init__(self, exit_code=None, failure=None):
        self.exit_code, self.failure, self.reaped = exit_code, failure, False

    def reap(self):
        self.reaped = True
        return self.exit_code


def campaign(audit=None, returncode=-15, **changes):
    """Build the post-panel result exactly as run() assembles it before verify_cleanup."""
    result = dict(
        release_HTTP_status=200,
        status_after_release=dict(
            state="idle", remaining=18, preparations_remaining=2, error=None
        ),
    )
    result.update(audit_summary(full_audit() if audit is None else audit, returncode))
    result.update(changes)
    return result


@pytest.mark.parametrize("returncode", [0, -15])
def test_cleanup_accepts_graceful_exit_and_then_checks_core(returncode):
    """Let uvicorn's re-raised SIGTERM pass cleanup so the borrowed-CORE survival check is evaluated."""
    core = Core()
    result = campaign(returncode=returncode)
    assert result["web_shutdown_graceful"] and result["workers_joined_clean"]
    verify_cleanup(result, core)
    assert core.reaped


@pytest.mark.parametrize("core", [Core(exit_code=0), Core(failure="core_exited")])
def test_cleanup_refuses_lost_borrowed_core_after_graceful_exit(core):
    """Report a dead or failed borrowed CORE after a graceful shutdown as not preserved."""
    with pytest.raises(ValueError, match="main_voice_borrowed_core_not_preserved"):
        verify_cleanup(campaign(), core)


@pytest.mark.parametrize(
    "result",
    [
        campaign(returncode=-9),
        campaign(returncode=1),
        campaign(audit=full_audit().replace("voice_manifest_closed", "x")),
        campaign(
            audit=full_audit().replace("exit=0 forced=False", "exit=-9 forced=True", 1)
        ),
        campaign(audit=full_audit().replace("stage=tts count=4", "stage=x count=4")),
        campaign(audit=full_audit() + full_audit().splitlines()[0] + "\n"),
        campaign(
            audit=full_audit().replace("voice_readiness_verified model_calls=1", "x")
        ),
        campaign(release_HTTP_status=409),
        campaign(status_after_release=dict(state="ready", error=None)),
        campaign(status_after_release=dict(state="idle", error="dependency_failed")),
        campaign(status_after_release=None),
    ],
)
def test_cleanup_refuses_budget_worker_release_or_exit_failures_before_core(result):
    """Stop at the cleanup criterion without consulting CORE for any over-budget, unclean or non-graceful run."""
    core = Core()
    with pytest.raises(ValueError, match="main_voice_call_budget_or_cleanup"):
        verify_cleanup(result, core)
    assert not core.reaped


def test_retained_audit_redacts_run_credentials(tmp_path):
    """Never persist the bearer token or pairing code when a failed run keeps the raw application log."""
    source, target = tmp_path / "app.log", tmp_path / "app-audit.log"
    source.write_bytes(
        "start token-value-123 pair-456 token-value-123 tiếng Việt\n".encode()
    )
    retain_audit(source, target, ["token-value-123", "pair-456"])
    kept = target.read_bytes()
    assert b"token-value-123" not in kept and b"pair-456" not in kept
    assert kept.count(b"[REDACTED_CREDENTIAL]") == 3
    assert "tiếng Việt".encode() in kept
