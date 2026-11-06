"""Guard nominated TTS repository/path pins and source-only Piper curation without downloading or executing any actual voice/model."""

import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest

from scripts.tts_evaluation_assets import (
    OMITTED_NEURAL,
    candidate_url,
    curate_piper,
    verify_runtime_snapshot,
)


@pytest.mark.parametrize("fault", [None, "bits", "extra", "missing", "link"])
def test_complete_original_runtime_snapshot_rejects_drift(tmp_path, fault):
    """Refuse changed SDK/source bytes, inventory additions/deletions or adopted symlinks before a scored model load."""
    (tmp_path / "venv").mkdir(mode=0o700)
    path = tmp_path / "venv/package.py"
    path.write_bytes(b"original")
    (tmp_path / "runtime-source/piper-curated").mkdir(mode=0o700, parents=True)
    snapshot = dict(
        files={
            "venv/package.py": dict(
                kind="file", bytes=8, sha256=hashlib.sha256(b"original").hexdigest()
            )
        }
    )
    (tmp_path / "runtime-integrity.json").write_text(json.dumps(snapshot))
    if fault == "bits":
        path.write_bytes(b"changed!")
    elif fault == "extra":
        (tmp_path / "venv/foreign.py").touch()
    elif fault == "missing":
        path.unlink()
    elif fault == "link":
        path.unlink()
        path.symlink_to("foreign")
    if fault is None:
        verify_runtime_snapshot(tmp_path)
    else:
        with pytest.raises(ValueError):
            verify_runtime_snapshot(tmp_path)


def candidate():
    """Return the exact nominated original Qwen checkpoint identity for pure URL-scope tests."""
    return dict(
        id="qwen3-tts-0.6b",
        repository="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        revision="85e237c12c027371202489a0ec509ded67b5e4b5",
    )


def test_required_included_codec_uses_the_same_pinned_checkpoint_without_substitution():
    """Keep the required codec a named component of the approved evaluation artifact rather than another repository/model."""
    url = candidate_url(candidate(), dict(path="speech_tokenizer/model.safetensors"))
    assert url.endswith(
        "85e237c12c027371202489a0ec509ded67b5e4b5/speech_tokenizer/model.safetensors"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "other_repo",
        "new_revision",
        "new_variant",
        "python",
        "traversal",
        "url",
        "aligner",
    ],
)
def test_repository_variant_revision_and_artifact_scope_cannot_be_widened(fault):
    """Refuse unexpected model/code/remote paths before the existing downloader can perform a request."""
    model, artifact = candidate(), dict(path="model.safetensors")
    if fault == "other_repo":
        model["repository"] = "Qwen/Another-Model"
    elif fault == "new_revision":
        model["revision"] = "main"
    elif fault == "new_variant":
        model["id"] = "qwen-1.7b"
    elif fault == "python":
        artifact["path"] = "modeling.py"
    elif fault == "traversal":
        artifact["path"] = "../model.safetensors"
    elif fault == "url":
        artifact["path"] = "https://example.com/model.safetensors"
    elif fault == "aligner":
        artifact["path"] = "aligner/model.safetensors"
    with pytest.raises(ValueError):
        candidate_url(model, artifact)


def authored_wheel(path, fault=None):
    """Construct a tiny authored source-archive fixture, with placeholder unused neural bytes that are never executed."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("piper/voice.py", b'"""Authored unit fixture only."""\n')
        archive.writestr(
            "piper/espeakbridge.so", b"authored native placeholder, never loaded"
        )
        archive.writestr(
            "piper_tts-1.8.0.dist-info/COPYING", b"authored license placeholder"
        )
        for name in OMITTED_NEURAL:
            archive.writestr(name, b"authored unused neural placeholder")
        if fault == "new_model":
            archive.writestr("piper/extra.onnx", b"other")
        elif fault == "traversal":
            archive.writestr("../outside", b"bad")
        elif fault == "duplicate":
            archive.writestr("piper/voice.py", b"duplicate")
        elif fault == "symlink":
            item = zipfile.ZipInfo("piper/link")
            item.create_system = 3
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(item, b"/etc/passwd")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_curated_source_preserves_exact_code_and_native_bytes_but_no_unused_weights(
    tmp_path,
):
    """Exclude optional models before installation while retaining source/license provenance and refusing a second output publication."""
    wheel, destination = tmp_path / "official-fixture.whl", tmp_path / "runtime"
    sha = authored_wheel(wheel)
    receipt = curate_piper(wheel, destination, sha)
    assert set(receipt["omitted_neural_members"]) == OMITTED_NEURAL
    assert not list(destination.rglob("*.onnx"))
    assert (
        destination / "piper/voice.py"
    ).read_bytes() == b'"""Authored unit fixture only."""\n'
    assert not list(destination.glob("*.dist-info"))
    assert (
        destination / "archived-distribution-metadata/piper_tts-1.8.0.dist-info/COPYING"
    ).exists()
    for record in receipt["files"]:
        assert (
            hashlib.sha256((destination / record["path"]).read_bytes()).hexdigest()
            == record["sha256"]
        )
    with pytest.raises(FileExistsError):
        curate_piper(wheel, destination, sha)


@pytest.mark.parametrize(
    "fault", ["new_model", "traversal", "duplicate", "symlink", "hash"]
)
def test_corrupt_or_unexpected_archive_is_rejected_before_any_runtime_file_is_written(
    tmp_path, fault
):
    """Prevent ZipSlip, code replacement, symlink adoption and hidden extra-model extraction."""
    wheel, destination = tmp_path / "source.whl", tmp_path / "runtime"
    sha = authored_wheel(wheel, fault)
    with pytest.raises(ValueError):
        curate_piper(wheel, destination, "0" * 64 if fault == "hash" else sha)
    assert not destination.exists()


def test_frozen_candidate_plan_contains_only_original_family_and_expected_language_voice_instances():
    """Catch accidental candidate/default/variant drift independently from metadata-fetch code."""
    plan = json.loads(Path("configs/tts-evaluation-candidates.json").read_text())
    assert plan["selected_model"] is None
    assert [model["id"] for model in plan["candidates"]] == [
        "qwen3-tts-0.6b",
        "piper-en",
        "piper-vi",
    ]
    assert plan["candidates"][0]["Vietnamese_officially_documented"] is False
    for model in plan["candidates"]:
        for artifact in model["artifacts"]:
            candidate_url(model, artifact)
