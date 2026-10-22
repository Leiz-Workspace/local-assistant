"""Test blind local audio-review request bounds, complete waveform integrity and honest first-response parsing without model inference."""

import hashlib
import json

import numpy as np
import pytest

from scripts.tts_local_review_worker import parse_judgement, validate_request, waveform


def judgement():
    """Provide an authored schema fixture, never a claimed real listening result."""
    return dict(presence="speech", language="english", naturalness="uncertain", confidence="medium", artifacts=[], prosody="Authored fixture", notes="No inference")


def request():
    """Provide nine opaque bounded control identities without references or expected labels."""
    return dict(mode="qualify", cases=[dict(id=f"clip-{i+1:02d}", sample_count=16000, sha256="a"*64) for i in range(9)])


@pytest.mark.parametrize("change", ["reference", "duplicate", "count", "path", "boolean", "hash", "mode"])
def test_untrusted_request_rejected(change):
    """Refuse text leakage, duplicate coverage, traversal and unbounded or noncanonical requests before neural imports."""
    value = request()
    if change == "reference":
        value["cases"][0]["reference"] = "secret label"
    elif change == "duplicate":
        value["cases"][1]["id"] = "clip-01"
    elif change == "count":
        value["cases"].pop()
    elif change == "path":
        value["cases"][0]["id"] = "../private"
    elif change == "boolean":
        value["cases"][0]["sample_count"] = True
    elif change == "hash":
        value["cases"][0]["sha256"] = "a"*63
    else:
        value["mode"] = "arbitrary"
    with pytest.raises(ValueError):
        validate_request(value)


def test_valid_blind_request_and_strict_response():
    """Accept exact declared fields while refusing prose, fabricated flags and invalid observation categories."""
    validate_request(request())
    value = judgement()
    assert parse_judgement(json.dumps(value)) == value
    assert parse_judgement("```json\n" + json.dumps(value) + "\n```") == value
    for bad in ["Heard speech", json.dumps(dict(value, actually_listened=True)), json.dumps(dict(value, naturalness="excellent")), json.dumps(dict(value, artifacts="none"))]:
        with pytest.raises(ValueError):
            parse_judgement(bad)


def test_original_full_timeline_waveform_and_corruption_guards(tmp_path):
    """Read unchanged full float32 inputs and reject mismatches, nonfinite samples and symlink aliases."""
    values = np.zeros(16000, dtype="<f4")
    raw = values.tobytes()
    path = tmp_path / "clip-01.f32"
    path.write_bytes(raw)
    row = dict(id="clip-01", sample_count=16000, sha256=hashlib.sha256(raw).hexdigest())
    assert np.array_equal(waveform(row, tmp_path), values)
    path.write_bytes(raw[:-4])
    with pytest.raises(ValueError):
        waveform(row, tmp_path)
    path.unlink()
    target = tmp_path / "other"
    target.write_bytes(raw)
    path.symlink_to(target)
    with pytest.raises(OSError):
        waveform(row, tmp_path)
