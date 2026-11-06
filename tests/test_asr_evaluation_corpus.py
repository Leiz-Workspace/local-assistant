"""Protect literal FLEURS label selection, exact float waveform bounds and safe archive-member extraction without model inference."""

import io
import struct
import tarfile

import numpy as np
import pytest

from scripts.asr_evaluation_corpus import (
    CorpusError,
    float_wav,
    select_rows,
    selected_audio,
)


def wav(values):
    """Construct a complete authored IEEEfloat32 mono16k RIFF fixture independently of the parser under test."""
    data = np.asarray(values, dtype="<f4").tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, 16000, 64000, 4, 32)
    body = (
        b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"fact"
        + struct.pack("<II", 4, len(values))
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_exact_float_waveform_is_unchanged_and_contains_no_metadata_payload():
    """Preserve all original float32 sample bits without quantization, resampling, amplitude clipping or a native codec call."""
    values = np.array([0, 0.5, -0.5, 1.001], dtype="<f4")
    raw = wav(values)
    payload, metadata = float_wav(raw)
    assert (
        payload == values.tobytes()
        and metadata["sample_count"] == 4
        and metadata["amplitude_or_sample_transform"] is False
    )


@pytest.mark.parametrize(
    "fault",
    ["truncated", "trailing", "codec", "rate", "channels", "fact", "nan", "inf"],
)
def test_invalid_float_wav_bounds_format_counts_and_nonfinite_samples_refuse(fault):
    """Reject a corrupted complete source rather than silently decoding, clipping or zero-filling unsupported data."""
    raw = bytearray(wav([0, 0.5, -0.5]))
    if fault == "truncated":
        raw = raw[:-1]
    elif fault == "trailing":
        raw += b"tail"
    elif fault == "codec":
        struct.pack_into("<H", raw, 20, 1)
    elif fault == "rate":
        struct.pack_into("<I", raw, 24, 8000)
    elif fault == "channels":
        struct.pack_into("<H", raw, 22, 2)
    elif fault == "fact":
        struct.pack_into("<I", raw, 44, 99)
    elif fault == "nan":
        raw = wav([float("nan")])
    elif fault == "inf":
        raw = wav([float("inf")])
    with pytest.raises(CorpusError):
        float_wav(bytes(raw))


def test_literal_tabs_preserve_opening_quotes_and_choose_normalized_upstream_reference_column():
    """Avoid CSV quote interpretation that would merge TSV rows or substitute the raw/character reference field."""
    text = '1\t111.wav\t"Raw quote\t"normalized quote\tcharacters\t32000\tMALE\n2\t222.wav\tRaw two\tnormalized two\tcharacters\t48000\tFEMALE\n'
    selected, unselected = select_rows(text, "vi_vn", 1)
    assert (
        selected[0]["reference"] == '"normalized quote'
        and selected[0]["raw_reference"] == '"Raw quote'
    )
    assert (
        unselected[0]["filename"] == "222.wav"
        and unselected[0]["reason"] == "outside_predeclared_first_eligible_subset"
    )


def test_unicode_line_separator_inside_label_is_not_a_tsv_record_boundary():
    """Preserve a complete upstream label containing Unicode separators rather than reinterpreting it as another TSV row."""
    text = "1\t111.wav\tRaw\tfirst\u2028second\tchars\t32000\tMALE\n"
    selected, _ = select_rows(text, "en_us", 1)
    assert selected[0]["reference"] == "first\u2028second"


@pytest.mark.parametrize(
    "fault", ["columns", "traversal", "duplicate", "samples", "missing"]
)
def test_bad_metadata_is_not_silently_replaced_with_favorable_cases(fault):
    """Refuse malformed/ambiguous source metadata before any candidate sees audio or a reference label."""
    text = "1\t111.wav\tRaw\tnormal\tchars\t32000\tMALE\n"
    if fault == "columns":
        text = text.replace("\tchars", "")
    elif fault == "traversal":
        text = text.replace("111.wav", "../111.wav")
    elif fault == "duplicate":
        text += text
    elif fault == "samples":
        text = text.replace("32000", "bad")
    elif fault == "missing":
        text = text.replace("32000", "999999")
    with pytest.raises(CorpusError):
        select_rows(text, "en_us", 1)


def archive(path, entries):
    """Write a bounded authored archive with explicit member types for extraction-boundary tests."""
    with tarfile.open(path, "w:gz") as output:
        for name, raw, kind in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.size = len(raw) if kind == tarfile.REGTYPE else 0
            output.addfile(item, io.BytesIO(raw) if item.size else None)


def test_selected_archive_reads_only_exact_regular_members_without_extracting_paths(
    tmp_path,
):
    """Return complete requested bytes and leave the filesystem free of archive-created source paths."""
    path = tmp_path / "source.tar.gz"
    archive(
        path,
        [
            ("test/111.wav", b"wave", tarfile.REGTYPE),
            ("test/222.wav", b"other", tarfile.REGTYPE),
        ],
    )
    assert selected_audio(path, [dict(filename="111.wav")]) == {"111.wav": b"wave"}
    assert not (tmp_path / "test").exists()


@pytest.mark.parametrize(
    "kind", ["traversal", "absolute", "symlink", "duplicate", "missing"]
)
def test_archive_ambiguity_or_unsafe_member_cannot_be_adopted_as_selected_waveform(
    tmp_path, kind
):
    """Reject path tricks, links and duplicate/missing source files instead of adopting a different waveform under a trusted ID."""
    path = tmp_path / "source.tar.gz"
    entries = [("test/111.wav", b"wave", tarfile.REGTYPE)]
    if kind == "traversal":
        entries = [("../111.wav", b"wave", tarfile.REGTYPE)]
    elif kind == "absolute":
        entries = [("/test/111.wav", b"wave", tarfile.REGTYPE)]
    elif kind == "symlink":
        entries = [("test/111.wav", b"", tarfile.SYMTYPE)]
    elif kind == "duplicate":
        entries *= 2
    elif kind == "missing":
        entries = []
    archive(path, entries)
    with pytest.raises(CorpusError):
        selected_audio(path, [dict(filename="111.wav")])
