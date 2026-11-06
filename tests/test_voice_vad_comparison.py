"""Verify held-out selection, exact gated source bytes, reference-free requests and unchanged sandbox mount boundaries."""

import struct
from pathlib import Path

import pytest

from scripts.voice_vad_comparison import gated_waveform, heldout_rows, replace_mount


def test_gating_copies_exact_original_spans_and_reports_subsecond_padding():
    """Retain the original samples without gain/trim repair and expose every zero added for an ASR minimum."""
    raw = b"".join(struct.pack("<f", index / 16000) for index in range(16000))
    output, retained, padding = gated_waveform(
        raw, [{"start": 1, "end": 20}, {"start": 100, "end": 120}]
    )
    assert output[: 39 * 4] == raw[4:80] + raw[400:480]
    assert retained == 39 and padding == 16000 - 39
    assert output[39 * 4 :] == b"\0" * (padding * 4)
    assert gated_waveform(raw, []) == (b"", 0, 0)


@pytest.mark.parametrize(
    "spans",
    [
        [{"start": 10, "end": 20}, {"start": 19, "end": 30}],
        [{"start": False, "end": 20}],
        [{"start": 0, "end": 16001}],
    ],
)
def test_impossible_or_overlapping_vad_results_are_not_repaired(spans):
    """Reject invalid original-clock intervals before creating any ASR input."""
    with pytest.raises(ValueError):
        gated_waveform(b"\0" * 64000, spans)


def test_only_one_known_sample_mount_can_change():
    """Preserve every original sandbox option and refuse ambiguous or absent mount substitutions."""
    assert replace_mount(
        ["bwrap", "--ro-bind", "/original", "/samples"], Path("/original"), Path("/new")
    ) == ["bwrap", "--ro-bind", "/new", "/samples"]
    for command in [["bwrap"], ["/original", "/original"]]:
        with pytest.raises(ValueError, match="mount_identity"):
            replace_mount(command, "/original", "/new")


def test_new_speech_subset_excludes_old_filenames_and_sentence_ids():
    """Freeze twenty new eligible utterance/sentence identities without outcome-dependent selection."""
    value = "\n".join(
        f"{index}\t{index}.wav\traw\ttext {index}\tunused\t16000\tMALE"
        for index in range(100)
    )
    old = [
        dict(
            language="en_us",
            kind="independent_public_speech",
            filename=f"{i}.wav",
            sentence_id=i,
        )
        for i in range(20)
    ]
    selected = heldout_rows(value, "en_us", old)
    assert [row["sentence_id"] for row in selected] == list(range(20, 40))
    assert len({row["filename"] for row in selected}) == 20
