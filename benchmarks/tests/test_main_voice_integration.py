"""Verify retained-panel declaration and truthful native acceptance rules without starting any model campaign."""

import base64

import pytest

from types import SimpleNamespace

from benchmarks.scripts.main_voice_integration import (
    CORE_RSS_STOP,
    FOREIGN_VRAM_LIMIT,
    preflight,
    review_rows,
    verify_answer,
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
