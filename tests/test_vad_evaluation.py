"""Verify VAD artifact provenance, authored corpus/sample clocks, error coverage and state replay analysis without acquiring or executing a model."""

import copy
import hashlib
import json

import numpy as np
import pytest

from scripts.vad_evaluation import (
    analyze,
    digest,
    overlap,
    prepare,
    verify_artifact,
    worker_request,
)


def test_artifact_validation_uses_complete_git_blob_not_only_a_file_digest():
    """Establish exact source/model publication integrity independently from the provisioning receipt."""
    raw = b"authored model boundary"
    expected = hashlib.sha1(b"blob 23\0" + raw).hexdigest()
    assert len(raw) == 23
    assert (
        verify_artifact(raw, dict(bytes=23, git_blob_sha1=expected))
        == hashlib.sha256(raw).hexdigest()
    )


@pytest.mark.parametrize("change", ["short", "long", "bytes"])
def test_incomplete_or_substituted_artifact_cannot_reuse_an_expected_source_identity(
    change,
):
    """Refuse length/hash mismatches before any official helper is imported or model instantiated."""
    raw = b"original"
    spec = dict(
        bytes=len(raw), git_blob_sha1=hashlib.sha1(b"blob 8\0" + raw).hexdigest()
    )
    changed = (
        raw[:-1]
        if change == "short"
        else raw + b"x"
        if change == "long"
        else b"changed!"
    )
    with pytest.raises(ValueError):
        verify_artifact(changed, spec)


@pytest.fixture
def authored_sources(tmp_path):
    """Build forty distinct one-second authored waveform fixtures, deliberately separate from actual FLEURS/model evidence."""
    source = tmp_path / "asr"
    (source / "prepared").mkdir(parents=True)
    cases = []
    for language in ["vi_vn", "en_us"]:
        for index in range(20):
            identity = f"{language}-{index:04d}"
            value = 0.01 + index / 1000 + (0.1 if language == "en_us" else 0)
            raw = np.full(16000, value, dtype="<f4").tobytes()
            path = source / "prepared" / (identity + ".f32")
            path.write_bytes(raw)
            cases.append(
                dict(
                    id=identity,
                    language=language,
                    kind="independent_public_speech",
                    waveform_path=str(path),
                    waveform_sha256=digest(raw),
                    sample_count=16000,
                    source_sha256=digest((identity + "-source").encode()),
                    sentence_id=index,
                    reference="authored unit placeholder only",
                )
            )
    for identity, raw in [
        ("silence", np.zeros(80000, dtype="<f4").tobytes()),
        (
            "seed7-noise",
            np.random.default_rng(7).normal(0, 0.02, 80000).astype("<f4").tobytes(),
        ),
    ]:
        path = source / "prepared" / (identity + ".f32")
        path.write_bytes(raw)
        cases.append(
            dict(
                id=identity + "-en_us",
                kind="authored_no_speech",
                waveform_path=str(path),
                waveform_sha256=digest(raw),
            )
        )
    (source / "prepared/corpus.json").write_text(
        json.dumps(
            dict(
                description="Authored corpus construction unit fixtures only, no actual labels or model predictions.",
                cases=cases,
            )
        )
    )
    destination = tmp_path / "vad"
    destination.mkdir()
    return source, destination


def test_prepared_corpus_preserves_speech_bits_source_mapping_unique_controls_and_parent_only_labels(
    authored_sources,
):
    """Check exact selected source order and padded sample clocks without needing any private artifact or model runtime."""
    source, destination = authored_sources
    prepare(destination, source)
    corpus = json.loads((destination / "corpus.json").read_text())
    cases = corpus["cases"]
    assert len(cases) == 47 and len({row["waveform_sha256"] for row in cases}) == 47
    assert sum(row["kind"] == "known_non_speech" for row in cases) == 5
    assert sum(row["kind"] == "public_speech_presence" for row in cases) == 40
    assert corpus["planned_passes"] == ["forward", "reverse"]
    for row in cases[:40]:
        assert (destination / "samples" / row["filename"]).read_bytes() == (
            source / "prepared" / row["filename"]
        ).read_bytes()
    for row in cases[-2:]:
        raw = (destination / "samples" / row["filename"]).read_bytes()
        assert (
            row["embedded_start_sample"] == 80000
            and row["embedded_end_sample"] == 96000
        )
        assert row["timeline_origin_samples"] == 32000 and len(raw) == 176000 * 4
        assert raw[: 80000 * 4] == raw[-80000 * 4 :] == bytes(80000 * 4)
        assert (
            digest(raw[80000 * 4 : 96000 * 4]) == row["embedded_source_waveform_sha256"]
        )
    request = worker_request("predict", cases)
    assert "reference" not in json.dumps(request) and "embedded" not in json.dumps(
        request
    )


def test_prepare_refuses_prior_outputs_instead_of_overwriting_selected_corpus(
    authored_sources,
):
    """Protect first inputs from an outcome-dependent rerun/replacement."""
    source, destination = authored_sources
    prepare(destination, source)
    previous = (destination / "corpus.json").read_bytes()
    with pytest.raises(FileExistsError):
        prepare(destination, source)
    assert (destination / "corpus.json").read_bytes() == previous


def test_corrupted_source_is_not_substituted_with_a_different_successful_recording(
    authored_sources,
):
    """Refuse original waveform drift before corpus selection can silently favor an easier sample."""
    source, destination = authored_sources
    (source / "prepared/vi_vn-0000.f32").write_bytes(b"wrong")
    with pytest.raises(ValueError, match="vad_corpus_original_integrity"):
        prepare(destination, source)


def authored_observations():
    """Create three explicitly authored pure-analysis cases; these are unit data, never real VAD accuracy evidence."""
    cases = [
        dict(
            id="speech",
            kind="public_speech_presence",
            sample_count=16000,
            waveform_sha256="a" * 64,
            timeline_origin_samples=0,
        ),
        dict(
            id="silence",
            kind="known_non_speech",
            sample_count=16000,
            waveform_sha256="b" * 64,
            timeline_origin_samples=0,
        ),
        dict(
            id="padded",
            kind="padded_source_composite",
            sample_count=176000,
            waveform_sha256="c" * 64,
            timeline_origin_samples=32000,
            embedded_start_sample=80000,
            embedded_end_sample=96000,
        ),
    ]
    events = []
    for pass_name in ["forward", "reverse"]:
        for case in cases if pass_name == "forward" else reversed(cases):
            samples = case["sample_count"]
            probabilities = [0.25] * ((samples + 511) // 512)
            segments = (
                []
                if case["id"] == "silence"
                else [dict(start=0, end=10000)]
                if case["id"] == "speech"
                else [dict(start=79000, end=97000)]
            )
            events.append(
                dict(
                    event="observation",
                    pass_name=pass_name,
                    id=case["id"],
                    status="ok",
                    sample_count=samples,
                    waveform_sha256=case["waveform_sha256"],
                    source_samples_modified=False,
                    segments=segments,
                    window_probabilities=probabilities,
                    model_windows=len(probabilities),
                    probability_sha256=digest(
                        np.asarray(probabilities, dtype="<f4").tobytes()
                    ),
                    padded_final_window_samples=(-samples) % 512,
                    external_recording_resets=1,
                    wall_seconds=0.01,
                )
            )
    return cases, events


def test_analysis_preserves_real_bounds_padding_tolerance_and_exact_timeline_offsets():
    """Distinguish whole-clip presence, known padding errors and sample-coordinate mapping without claiming word accuracy."""
    cases, events = authored_observations()
    result = analyze(cases, events)
    assert result["measurement_complete"] and result["exact_replayed_inputs"] == 3
    assert (
        result["speech_presence_detected"] == 1
        and result["known_negative_false_positive_inputs"] == 0
    )
    padded = result["cases"][-1]
    assert padded["known_padding_false_positive_samples_beyond_62ms_tolerance"] == 16
    assert padded["absolute_sample_intervals"] == [dict(start=111000, end=129000)]
    assert padded["detected_inside_embedded_source"] is True
    assert result["selected_model"] is None


@pytest.mark.parametrize("fault", ["missing", "failed", "replay_changed"])
def test_incomplete_or_state_dependent_observation_does_not_become_a_complete_evaluation(
    fault,
):
    """Retain failed/missing coverage and exact forward/reverse disagreement instead of retrying or zero-filling it."""
    cases, events = authored_observations()
    if fault == "missing":
        events.pop()
    elif fault == "failed":
        events[-1] = dict(
            event="observation", pass_name="reverse", id="speech", status="error"
        )
    else:
        events[-1]["segments"] = [dict(start=1, end=10000)]
    result = analyze(cases, events)
    assert not result["measurement_complete"] and result["exact_replayed_inputs"] == 2


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "waveform",
        "reset",
        "probability_count",
        "nan",
        "probability_hash",
        "overlap",
        "zero_timing",
        "modified_audio",
        "tail_padding",
    ],
)
def test_analysis_refuses_corrupt_source_state_probability_or_clock_claims(fault):
    """Reject tampered observations at the parent boundary even when their status claims successful native inference."""
    cases, events = authored_observations()
    row = events[0]
    if fault == "duplicate":
        events.append(copy.deepcopy(row))
    elif fault == "waveform":
        row["waveform_sha256"] = "d" * 64
    elif fault == "reset":
        row["external_recording_resets"] = 0
    elif fault == "probability_count":
        row["window_probabilities"].pop()
    elif fault == "nan":
        row["window_probabilities"][0] = float("nan")
    elif fault == "probability_hash":
        row["probability_sha256"] = "e" * 64
    elif fault == "overlap":
        row["segments"].append(dict(start=9000, end=12000))
    elif fault == "zero_timing":
        row["wall_seconds"] = 0
    elif fault == "modified_audio":
        row["source_samples_modified"] = True
    elif fault == "tail_padding":
        row["padded_final_window_samples"] = 0
    with pytest.raises(ValueError):
        analyze(cases, events)


def test_known_negative_false_speech_is_reported_without_relabeling_it_as_speech():
    """Keep an authored false positive visible while allowing evaluation completion distinct from candidate quality approval."""
    cases, events = authored_observations()
    for row in events:
        if row["id"] == "silence":
            row["segments"] = [dict(start=0, end=10000)]
    result = analyze(cases, events)
    assert (
        result["measurement_complete"]
        and result["known_negative_false_positive_inputs"] == 1
    )
    assert result["known_negatives_observed"] == 1 and result["selected_model"] is None


@pytest.mark.parametrize(
    "bounds,expected",
    [((0, 10, 10, 20), 0), ((0, 11, 10, 20), 1), ((10, 30, 15, 20), 5)],
)
def test_sample_intersection_is_half_open_without_rounding(bounds, expected):
    """Establish padding false-positive duration arithmetic independently from the corpus and model."""
    assert overlap(*bounds) == expected
