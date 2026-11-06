"""Prepare a pinned public FLEURS subset as exact uncompressed mono16k float32 waveforms without widening production media policies."""

import argparse
import hashlib
import json
import logging
import os
import re
import struct
import tarfile
from pathlib import Path

import numpy as np

from scripts.asr_evaluation_assets import ROOT, verify_file

logger = logging.getLogger(__name__)
MAX_WAV = 32 * 1024**2


class CorpusError(Exception):
    """Expose finite public evaluation input failures without transcript text, raw signal or decoder diagnostics."""

    def __init__(self, code="asr_corpus_invalid"):
        """Log only a controlled corpus failure rather than creating a model prediction or benchmark score."""
        self.code = (
            code
            if code in {"asr_corpus_invalid", "asr_corpus_limits", "asr_corpus_missing"}
            else "asr_corpus_invalid"
        )
        super().__init__(self.code)
        logger.warning("asr_corpus_rejected code=%s", self.code)


def sha(raw):
    """Fingerprint complete public waveform/source bytes without logging signal or label content."""
    return hashlib.sha256(raw).hexdigest()


def float_wav(raw):
    """Read only bounded uncompressed IEEEfloat32 mono16k RIFF data, verifying all lengths/counts and finite samples without codec decoding."""
    if (
        type(raw) is not bytes
        or not 44 <= len(raw) <= MAX_WAV
        or raw[:4] != b"RIFF"
        or raw[8:12] != b"WAVE"
        or struct.unpack_from("<I", raw, 4)[0] + 8 != len(raw)
    ):
        raise CorpusError()
    offset, chunks, format_seen, payload, fact = 12, 0, False, None, None
    while offset < len(raw):
        if chunks >= 32 or offset + 8 > len(raw):
            raise CorpusError()
        kind = raw[offset : offset + 4]
        size = struct.unpack_from("<I", raw, offset + 4)[0]
        start = offset + 8
        end = start + size
        if end > len(raw):
            raise CorpusError()
        if kind == b"fmt ":
            if (
                format_seen
                or size not in (16, 18)
                or struct.unpack_from("<HHIIHH", raw, start)
                != (3, 1, 16000, 64000, 4, 32)
                or size == 18
                and struct.unpack_from("<H", raw, start + 16)[0] != 0
            ):
                raise CorpusError()
            format_seen = True
        elif kind == b"data":
            if not format_seen or payload is not None or size % 4:
                raise CorpusError()
            payload = raw[start:end]
        elif kind == b"fact":
            if fact is not None or size != 4:
                raise CorpusError()
            fact = struct.unpack_from("<I", raw, start)[0]
        # RIFF chunk lengths exclude their optional odd-byte alignment padding.
        offset = end + (size & 1)
        chunks += 1
    if (
        offset != len(raw)
        or not format_seen
        or payload is None
        or not 1 <= len(payload) // 4 <= 480000
        or fact is not None
        and fact != len(payload) // 4
    ):
        raise CorpusError()
    values = np.frombuffer(payload, dtype="<f4")
    if not np.isfinite(values).all() or float(np.abs(values).max()) > 16:
        raise CorpusError()
    logger.info("asr_float_wav_verified samples=%d", len(values))
    return payload, dict(
        source_codec="wav_ieee_float32",
        source_sample_rate=16000,
        source_channels=1,
        sample_count=len(values),
        waveform_sha256=sha(payload),
        peak_absolute_amplitude=float(np.abs(values).max()),
        amplitude_or_sample_transform=False,
    )


def select_rows(text, language, count=20):
    """Select first eligible original TSV rows using the upstream literal-tab schema, preserving every unselected row and reason."""
    if (
        type(text) is not str
        or len(text.encode()) > 2 * 1024**2
        or language not in {"vi_vn", "en_us"}
        or type(count) is not int
        or not 1 <= count <= 100
    ):
        raise CorpusError()
    selected, unselected, seen = [], [], set()
    for index, line in enumerate(text.removesuffix("\n").split("\n")):
        line = line.removesuffix("\r")
        fields = line.split("\t")
        if len(fields) != 7:
            raise CorpusError()
        identity, filename, raw_reference, reference, _, samples, gender = fields
        if (
            not identity.isdecimal()
            or re.fullmatch("[0-9]+\\.wav", filename) is None
            or not samples.isdecimal()
            or gender not in {"MALE", "FEMALE", "OTHER"}
            or filename in seen
        ):
            raise CorpusError()
        seen.add(filename)
        reason = None
        if not 16000 <= int(samples) <= 320000:
            reason = "outside_common_1_to_20_second_budget"
        elif not reference.strip() or len(reference.encode()) > 2048:
            reason = "missing_or_overlong_reference"
        elif len(selected) >= count:
            reason = "outside_predeclared_first_eligible_subset"
        if reason:
            unselected.append(
                dict(
                    row_index=index,
                    sentence_id=int(identity),
                    filename=filename,
                    reason=reason,
                )
            )
            continue
        selected.append(
            dict(
                id=f"{language}-{index:04d}",
                language=language,
                row_index=index,
                sentence_id=int(identity),
                filename=filename,
                reference=reference,
                raw_reference=raw_reference,
                upstream_num_samples=int(samples),
                gender=gender,
                kind="independent_public_speech",
            )
        )
    if len(selected) != count:
        raise CorpusError("asr_corpus_missing")
    logger.info(
        "asr_source_rows_selected language=%s selected=%d unselected=%d",
        language,
        len(selected),
        len(unselected),
    )
    return selected, unselected


def selected_audio(archive_path, rows):
    """Read selected regular WAV members without filesystem extraction, path traversal, duplicate adoption or unbounded expansion."""
    wanted = {row["filename"] for row in rows}
    found = {}
    members = total = 0
    with tarfile.open(archive_path, "r|gz") as archive:
        for item in archive:
            members += 1
            total += max(0, item.size)
            if members > 10000 or total > 4 * 1024**3:
                raise CorpusError("asr_corpus_limits")
            name = item.name.removeprefix("./")
            parts = name.split("/")
            if name.startswith("/") or "\\" in name or ".." in parts:
                raise CorpusError()
            filename = parts[-1]
            if filename not in wanted:
                continue
            if (
                name != "test/" + filename
                or not item.isfile()
                or not 1 <= item.size <= MAX_WAV
                or filename in found
            ):
                raise CorpusError()
            source = archive.extractfile(item)
            if source is None:
                raise CorpusError()
            raw = source.read(item.size + 1)
            if len(raw) != item.size:
                raise CorpusError()
            found[filename] = raw
    if set(found) != wanted:
        raise CorpusError("asr_corpus_missing")
    logger.info(
        "asr_selected_archive_members_read selected=%d scanned_members=%d",
        len(found),
        members,
    )
    return found


def save_bytes(path, raw):
    """Create private complete evaluation data once without following links or overwriting an existing corpus/benchmark input."""
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def prepare(root=ROOT):
    """Create a frozen common forty-speech/four-request corpus before any candidate prediction or result-dependent selection."""
    root = Path(root)
    provision = json.loads((root / "corpus-provisioned.json").read_text())
    for record in provision["results"]:
        path = (
            root / "corpus" / record["language"] / record["expected_spec"]["filename"]
        )
        verify_file(path, record["expected_spec"])
    destination = root / "prepared"
    destination.mkdir(mode=0o700, exist_ok=True)
    cases, excluded = [], {}
    for language in ["vi_vn", "en_us"]:
        directory = root / "corpus" / language
        rows, unselected = select_rows((directory / "test.tsv").read_text(), language)
        originals = selected_audio(directory / "test.tar.gz", rows)
        for row in rows:
            raw = originals[row["filename"]]
            waveform, metadata = float_wav(raw)
            if metadata["sample_count"] != row["upstream_num_samples"]:
                raise CorpusError()
            path = destination / (row["id"] + ".f32")
            save_bytes(path, waveform)
            cases.append(
                dict(row, source_sha256=sha(raw), waveform_path=str(path), **metadata)
            )
        excluded[language] = unselected
    silence = np.zeros(80000, dtype="<f4").tobytes()
    noise = np.random.default_rng(7).normal(0, 0.02, 80000).astype("<f4").tobytes()
    for name, raw in [("silence", silence), ("seed7-noise", noise)]:
        path = destination / (name + ".f32")
        save_bytes(path, raw)
        for language in ["en_us", "vi_vn"]:
            cases.append(
                dict(
                    id=name + "-" + language,
                    language=language,
                    kind="authored_no_speech",
                    reference="",
                    raw_reference="",
                    source_sha256=sha(raw),
                    waveform_path=str(path),
                    source_codec="authored_float32",
                    source_sample_rate=16000,
                    source_channels=1,
                    sample_count=80000,
                    waveform_sha256=sha(raw),
                    amplitude_or_sample_transform=False,
                )
            )
    manifest = dict(
        description="Pinned original-order FLEURS test subset:20VI/20EN independent public speech plus4requests/2unique authored no-speech waveforms. No ASR predictions/selection; source WAV is mono16k IEEEfloat32, waveform bytes unchanged, no production parser widening. Literal tab columns follow upstream historical schema2de94963bc53758e33898d0b8fa3c2c71939cdef; actual corpus revision70bb2e84b976b7e960aa89f1c648e09c59f894dd.",
        cases=cases,
        unselected_rows=excluded,
        selected_speech_cases=40,
        no_speech_requests=4,
        unique_no_speech_waveforms=2,
        ASR_evaluated=False,
        model_selection=None,
    )
    save_bytes(
        destination / "corpus.json",
        (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(),
    )
    logger.info(
        "asr_common_corpus_prepared speech=40 control_requests=4 selected_models=0"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    argparse.ArgumentParser(description=__doc__).parse_args()
    prepare()
