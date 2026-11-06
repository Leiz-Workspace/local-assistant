"""Build a reviewable offline provider-source patch without deploying a Space, downloading weights or invoking an evaluator."""

import ast
import difflib
import hashlib
import json
import logging
from pathlib import Path

from scripts.asr_evaluation_corpus import save_bytes
from scripts.tts_local_review import publish_json

logger = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "data/backups/d70-reviewer-route-metadata-first"
OUTPUT = PROJECT / "data/backups/d70-speechjudge-remediation-first"
SOURCE_REVISION = "e16fd85d230ac043091476eb78faa6c2e24c5c66"
MODEL_REVISION = "8d4ce4ddf54c5e7ac0b457fc7b561cec1bd784c1"
SOURCE_HASHES = {
    "app.py": "5048833ee621a8e6d1e2cb670d622d4b0c12d1aab1ee0f3f4b33334a048d439c",
    "infer/utils.py": "7cb63ec183efb59e53cf3b6d814f67d2dc47afec1f8fec05a183a831361a5a64",
}


def sha(raw):
    """Hash complete source or patch bytes without executing or logging source contents."""
    return hashlib.sha256(raw).hexdigest()


def replace_once(text, old, new):
    """Refuse unexpected source structure instead of guessing where a remediation should be applied."""
    if text.count(old) != 1:
        logger.warning("speechjudge_remediation_rejected reason=source_structure")
        raise ValueError("remediation_source_structure")
    return text.replace(old, new, 1)


def verify_sources(sources):
    """Accept only the two exact retained source files before any patch construction or filesystem mutation."""
    if type(sources) is not dict or set(sources) != set(SOURCE_HASHES):
        raise ValueError("remediation_source_coverage")
    for name, raw in sources.items():
        if type(raw) is not bytes or len(raw) > 65536 or b"\x00" in raw or sha(raw) != SOURCE_HASHES[name]:
            logger.warning("speechjudge_remediation_rejected reason=source_hash name=%s", name)
            raise ValueError("remediation_source_hash")
        ast.parse(raw.decode("utf-8"), filename=name)
    logger.info("speechjudge_remediation_sources_verified files=2 revision=%s", SOURCE_REVISION)


def build_candidates(sources):
    """Prepare CUDA placement, GPU-duration and immutable weight-revision changes while preserving the rubric, generation options and four-parameter API."""
    verify_sources(sources)
    app = sources["app.py"].decode("utf-8")
    utils = sources["infer/utils.py"].decode("utf-8")
    app = '"""Serve the proposed pinned research evaluator; this candidate has not been deployed or qualified."""\n\nimport logging\n' + app
    app = replace_once(app, "# --- Global Variables for Model Caching ---", "logger = logging.getLogger(__name__)\nlogging.basicConfig(level=logging.INFO)\n\n# --- Global Variables for Model Caching ---")
    app = replace_once(app, "def load_model_globally():\n", 'def load_model_globally():\n    """Initialize the pinned model and place it on CUDA before request-time GPU allocation."""\n')
    start = app.index("    # ZeroGPU:")
    stop = app.index("    MODEL = Qwen2_5OmniForConditionalGeneration.from_pretrained(", start)
    app = app[:start] + "    # ZeroGPU emulates startup CUDA placement; avoid transfers within the request budget.\n" + app[stop:]
    app = replace_once(app, "    MODEL.eval()\n", '    MODEL.to("cuda")\n    MODEL.eval()\n    logger.info("speechjudge_startup_cuda_placement_complete")\n')
    app = replace_once(app, "@spaces.GPU(duration=30)", "@spaces.GPU(duration=120)")
    start = app.index("):\n", app.index("def compare_wavs(")) + len("):\n")
    stop = app.index("    result_list = []", start)
    app = app[:start] + '    """Compare complete supplied audio with the unchanged naturalness rubric and generation settings."""\n    logger.info("speechjudge_comparison_started generations=%d", num_of_generation)\n' + app[stop:]
    utils = '"""Build original SpeechJudge inputs and fetch only the explicitly pinned research checkpoint."""\n\nimport logging\n\nlogger = logging.getLogger(__name__)\n\n' + utils
    utils = replace_once(utils, "def download_speechjudge_grm(local_dir):\n", 'def download_speechjudge_grm(local_dir):\n    """Fetch the exact research checkpoint revision only when this undeployed candidate is explicitly run."""\n    logger.info("speechjudge_pinned_checkpoint_requested revision=%s", "' + MODEL_REVISION + '")\n')
    utils = replace_once(utils, '        repo_id="RMSnow/SpeechJudge-GRM",\n', '        repo_id="RMSnow/SpeechJudge-GRM",\n        revision="' + MODEL_REVISION + '",\n')
    candidates = {"app.py": app.encode(), "infer/utils.py": utils.encode()}
    for name, raw in candidates.items():
        ast.parse(raw.decode("utf-8"), filename=name)
    logger.info("speechjudge_remediation_built source_executed=False deployed=False model_invoked=False")
    return candidates


def build_patch(sources, candidates):
    """Create a standard reviewable unified diff while rejecting any candidate outside the deterministic source-bound recipe."""
    if candidates != build_candidates(sources):
        raise ValueError("remediation_candidate_changed")
    parts = []
    for name in sorted(sources):
        parts.extend(difflib.unified_diff(sources[name].decode().splitlines(keepends=True), candidates[name].decode().splitlines(keepends=True), fromfile="a/" + name, tofile="b/" + name))
    logger.info("speechjudge_remediation_patch_created files=2")
    return "".join(parts).encode()


def publish_candidate(sources, directory):
    """Publish complete candidate files, a patch and a first manifest exclusively inside a new local directory without network or deployment."""
    candidates = build_candidates(sources)
    patch = build_patch(sources, candidates)
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("remediation_output_symlink")
    directory.mkdir(mode=0o700, exist_ok=False)
    (directory / "infer").mkdir(mode=0o700)
    for name, raw in candidates.items():
        save_bytes(directory / name, raw)
    save_bytes(directory / "remediation.patch", patch)
    manifest = dict(
        description="Offline, undeployed provider-source proposal; static/software verification is not GPU compatibility, a proven root-cause fix or audio-quality evidence.",
        source_revision=SOURCE_REVISION,
        source_sha256={name: sha(raw) for name, raw in sources.items()},
        candidate_sha256={name: sha(raw) for name, raw in candidates.items()},
        patch_sha256=sha(patch),
        intended_model_revision=MODEL_REVISION,
        GPU_duration_seconds=120,
        max_new_tokens=1024,
        API_parameters=["target_text", "audio_path_a", "audio_path_b", "num_generations"],
        weights_downloaded=False,
        candidate_executed=False,
        deployed=False,
        inference_requests=0,
        D70_complete=False,
        D71_started=False,
    )
    publish_json(directory / "manifest.json", manifest)
    logger.info("speechjudge_remediation_published directory=%s deployment_approved=False", directory)
    return manifest


def main():
    """Build only local remediation artifacts from the two previously retained exact source snapshots."""
    logging.basicConfig(level=logging.INFO)
    sources = {"app.py": (SOURCE / "speechjudge-copy-app.txt").read_bytes(), "infer/utils.py": (SOURCE / "speechjudge-copy-utils.txt").read_bytes()}
    manifest = publish_candidate(sources, OUTPUT)
    logger.info("speechjudge_remediation_finished manifest=%s", json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
