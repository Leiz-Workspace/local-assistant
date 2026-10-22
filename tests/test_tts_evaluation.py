"""Independently test TTS namespace authority, native audio evidence and exact corpus coverage without neural inference or production writes."""

import copy
import os

import numpy as np
import pytest

from scripts.tts_evaluation import (
    cases,
    read_output,
    sandbox,
    sha,
    verify_outputs,
    worker_request,
)
from scripts.tts_waveform import OutputStore


def observation(tmp_path):
    """Publish one authored native waveform and its minimal request-bound observation for independent corruption tests."""
    request = worker_request("piper-en", "smoke", {})
    case = request["cases"][0]
    audio = OutputStore(tmp_path).save(
        np.array([0.0, 0.25, -0.5], dtype="<f4"), 22050, case["id"]
    )
    row = dict(
        event="observation",
        id=case["id"],
        text_sha256=sha(case["text"].encode()),
        language="en",
        variant="explicit",
        status="ok",
        audio=audio,
        generation_complete=True,
        first_available_audio_seconds=0.1,
        full_call_seconds=0.2,
    )
    return request, [row, dict(event="complete")]


def test_fixed_corpus_is_bounded_unique_and_not_human_truth():
    """Retain six different scenarios per language with no placeholder independent-human ratings."""
    corpus = cases()
    assert len(corpus) == len({row["id"] for row in corpus}) == 12
    assert len({row["kind"] for row in corpus}) == 6
    assert all(0 < len(row["text"].encode()) <= 160 for row in corpus)


@pytest.mark.parametrize("candidate", ["qwen3-tts-0.6b", "piper-en", "piper-vi"])
def test_namespace_has_one_owned_output_and_no_production_network_credentials(
    tmp_path, candidate
):
    """Keep only one empty private RW mount and CPU caps while all selected model/source/runtime files are readonly."""
    command = sandbox(candidate, tmp_path)
    assert command.count("--bind") == 1
    index = command.index("--bind")
    assert command[index + 1 : index + 3] == [str(tmp_path), "/output"]
    assert "--unshare-all" in command and "--clearenv" in command
    assert "--as=12884901888" in command and "--cpu=3600:3601" in command
    assert not any(
        ".env" in item or "vault" in item.lower() or "nvidia" in item or "d68-" in item
        for item in command
    )
    assert (
        "/sources" in command
        if candidate.startswith("piper")
        else "/sources" not in command
    )


def test_output_authority_requires_empty_private_directory(tmp_path):
    """Refuse reusing a directory containing foreign results or adopting a permissive root."""
    (tmp_path / "foreign").touch()
    with pytest.raises(ValueError):
        sandbox("piper-en", tmp_path)
    (tmp_path / "foreign").unlink()
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError):
        sandbox("piper-en", tmp_path)


def test_parent_recomputes_native_audio_and_does_not_claim_naturalness(tmp_path):
    """Verify actual sample bits/WAV independently while leaving the auditory review criterion explicitly open."""
    request, events = observation(tmp_path)
    result = verify_outputs(tmp_path, request, events)
    assert result["observations_complete"] and result["successful_waveforms"] == 1
    assert result["actual_audio_inspection_complete"] is False
    assert result["model_selected"] is None


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "metric",
        "text",
        "id",
        "duplicate",
        "first_time",
        "incomplete",
        "sample_bits",
        "wav_bits",
        "unexpected",
        "unsupported",
    ],
)
def test_parent_rejects_unbound_or_forged_output_evidence(tmp_path, mutation):
    """Refuse forged metrics, source identity, natural-audio success, timestamps, file bytes and unsupported-language relabelling."""
    request, events = observation(tmp_path)
    row = events[0]
    if mutation == "hash":
        row["audio"]["waveform_sha256"] = "0" * 64
    elif mutation == "metric":
        row["audio"]["RMS"] = 0.0
    elif mutation == "text":
        row["text_sha256"] = "0" * 64
    elif mutation == "id":
        row["id"] = "foreign"
    elif mutation == "duplicate":
        events.append(copy.deepcopy(row))
    elif mutation == "first_time":
        row["first_available_audio_seconds"] = 3.0
    elif mutation == "incomplete":
        row["generation_complete"] = False
    elif mutation in {"sample_bits", "wav_bits"}:
        key = "raw_filename" if mutation == "sample_bits" else "wav_filename"
        path = tmp_path / row["audio"][key]
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
    elif mutation == "unexpected":
        (tmp_path / "unaccounted").touch()
    else:
        row["status"] = "unsupported_language"
    with pytest.raises(ValueError):
        verify_outputs(tmp_path, request, events)


def test_missing_observations_are_partial_not_full_acceptance(tmp_path):
    """Keep a process that emitted no requested waveform incomplete without fabricating a zero-error score."""
    request = worker_request("piper-en", "smoke", {})
    result = verify_outputs(tmp_path, request, [dict(event="complete")])
    assert not result["observations_complete"] and result["successful_waveforms"] == 0


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "last_token",
        "frames",
        "sequence_tokens",
        "max_tokens",
        "asynchronous",
        "wrong_rate",
    ],
)
def test_parent_recomputes_qwen_generation_end_and_synchronous_audio_timing(
    tmp_path, fault
):
    """Require real EOS/frame correspondence and native24k synchronous timing independently of a worker success flag."""
    request = worker_request("qwen3-tts-0.6b", "smoke", {})
    case = request["cases"][0]
    audio = OutputStore(tmp_path).save(
        np.zeros(1920, dtype="<f4"),
        24000 if fault != "wrong_rate" else 22050,
        case["id"],
    )
    row = dict(
        event="observation",
        id=case["id"],
        text_sha256=sha(case["text"].encode()),
        language="en",
        variant="explicit",
        status="ok",
        audio=audio,
        generation_complete=True,
        first_available_audio_seconds=0.2,
        full_call_seconds=0.2,
        inner_generations=[
            dict(sequence_tokens=2, last_token=2150, ended_with_eos=True)
        ],
        codec_frames=[1],
        maximum_new_tokens=192,
    )
    if fault == "last_token":
        row["inner_generations"][0]["last_token"] = 2151
    elif fault == "frames":
        row["codec_frames"] = [2]
    elif fault == "sequence_tokens":
        row["inner_generations"][0]["sequence_tokens"] = 193
    elif fault == "max_tokens":
        row["maximum_new_tokens"] = 2048
    elif fault == "asynchronous":
        row["first_available_audio_seconds"] = 0.1
    events = [row, dict(event="complete")]
    if fault is None:
        assert verify_outputs(tmp_path, request, events)["successful_waveforms"] == 1
    else:
        with pytest.raises(ValueError):
            verify_outputs(tmp_path, request, events)


@pytest.mark.parametrize("kind", ["symlink", "fifo", "wide_permissions", "traversal"])
def test_parent_will_not_read_links_special_files_or_foreign_paths(tmp_path, kind):
    """Avoid both unauthorized file reads and blocking on a special file supplied as audio evidence."""
    filename = "audio.f32"
    path = tmp_path / filename
    if kind == "symlink":
        path.symlink_to("missing")
    elif kind == "fifo":
        os.mkfifo(path, 0o600)
    elif kind == "wide_permissions":
        path.touch(mode=0o644)
    else:
        filename = "../foreign"
    with pytest.raises((ValueError, OSError)):
        read_output(tmp_path, filename)
