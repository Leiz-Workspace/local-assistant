"""Test offline source-bound provider remediation with authored source fixtures, never model imports, downloads, deployment or inference."""

import ast
import copy
import json
import subprocess

import pytest

from scripts import tts_speechjudge_source_remediation as remediation


@pytest.fixture
def sources(monkeypatch):
    """Bind the recipe to small authored source fixtures instead of executing any retained third-party application."""
    app = b'''import spaces
from transformers import Qwen2_5OmniForConditionalGeneration
# --- Global Variables for Model Caching ---
MODEL = None
def load_model_globally():
    global MODEL
    # ZeroGPU: outdated authored fixture comment.
    MODEL = Qwen2_5OmniForConditionalGeneration.from_pretrained(
        "authored_fixture", torch_dtype="unchanged", attn_implementation="unchanged",
    )
    MODEL.eval()
@spaces.GPU(duration=30)
def compare_wavs(target_text, wav_path_a, wav_path_b, num_of_generation=5):
    # Authored fixture transfer, never actually called.
    MODEL.to("cuda")
    result_list = []
    text_ids = MODEL.generate(max_new_tokens=1024, do_sample=True, return_audio=False)
    return result_list, text_ids
def gradio_handler(target_text, audio_path_a, audio_path_b, num_generations):
    """Keep the authored public API signature intact."""
    return compare_wavs(target_text, audio_path_a, audio_path_b, num_generations)
'''
    utils = b'''def download_speechjudge_grm(local_dir):
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id="RMSnow/SpeechJudge-GRM",
        local_dir=local_dir,
    )
def build_cot_conversation(target_text, wav_path_a, wav_path_b):
    """Keep an authored rubric fixture intact."""
    return {"rubric": "authored unchanged fixture", "audio": [wav_path_a, wav_path_b]}
'''
    values = {"app.py": app, "infer/utils.py": utils}
    monkeypatch.setattr(remediation, "SOURCE_HASHES", {name: remediation.sha(raw) for name, raw in values.items()})
    return values


def function(raw, name):
    """Inspect one function's AST without importing or executing the candidate application."""
    return next(node for node in ast.parse(raw.decode()).body if isinstance(node, ast.FunctionDef) and node.name == name)


def calls(node, attribute):
    """Find call structure for independent semantic checks without relying on formatted source substrings."""
    return [item for item in ast.walk(node) if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr == attribute]


def test_cuda_placement_and_duration_move_without_decoder_or_rubric_changes(sources):
    """Move CUDA transfer out of the request body and adjust only the provider budget while preserving model and scoring inputs."""
    candidate = remediation.build_candidates(sources)
    load = function(candidate['app.py'], 'load_model_globally')
    compare = function(candidate['app.py'], 'compare_wavs')
    assert len(calls(load, 'to')) == 1 and calls(load, 'to')[0].args[0].value == 'cuda'
    assert not calls(compare, 'to')
    decorator = compare.decorator_list[0]
    assert decorator.keywords[0].arg == 'duration' and decorator.keywords[0].value.value == 120
    original = function(sources['app.py'], 'compare_wavs')
    assert ast.dump(calls(compare, 'generate')[0]) == ast.dump(calls(original, 'generate')[0])
    assert ast.dump(function(candidate['app.py'], 'gradio_handler')) == ast.dump(function(sources['app.py'], 'gradio_handler'))
    assert ast.dump(function(candidate['infer/utils.py'], 'build_cot_conversation')) == ast.dump(function(sources['infer/utils.py'], 'build_cot_conversation'))
    assert ast.get_docstring(load) and ast.get_docstring(compare)


def test_weight_revision_is_pinned_without_a_download(sources):
    """Verify the proposed fetch instruction binds the same inspected research checkpoint without calling its downloader."""
    candidate = remediation.build_candidates(sources)
    downloader = function(candidate['infer/utils.py'], 'download_speechjudge_grm')
    call = next(node for node in ast.walk(downloader) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'snapshot_download')
    kwargs = {item.arg: item.value.value if isinstance(item.value, ast.Constant) else None for item in call.keywords}
    assert kwargs['repo_id'] == 'RMSnow/SpeechJudge-GRM' and kwargs['revision'] == remediation.MODEL_REVISION


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'altered', 'wrong_type', 'oversize', 'nul'])
def test_unexpected_source_rejected_before_output_publication(sources, tmp_path, mutation):
    """Reject source drift and malformed coverage before any candidate directory is created."""
    changed = dict(sources)
    if mutation == 'missing':
        changed.pop('infer/utils.py')
    elif mutation == 'extra':
        changed['other.py'] = b''
    elif mutation == 'altered':
        changed['app.py'] += b'\n# changed\n'
    elif mutation == 'wrong_type':
        changed['app.py'] = changed['app.py'].decode()
    elif mutation == 'oversize':
        changed['app.py'] = b'x' * 65537
    else:
        changed['app.py'] += b'\0'
    output = tmp_path / 'not_created'
    with pytest.raises(ValueError):
        remediation.publish_candidate(changed, output)
    assert not output.exists()


def test_full_source_and_patch_match_after_actual_temporary_application(sources, tmp_path):
    """Apply the proposed diff to authored temporary files and require exact full candidate bytes, hashes, permissions and closed deployment state."""
    output = tmp_path / 'candidate'
    manifest = remediation.publish_candidate(sources, output)
    original = tmp_path / 'original'
    original.mkdir()
    (original / 'infer').mkdir()
    for name, raw in sources.items():
        (original / name).write_bytes(raw)
    patch = (output / 'remediation.patch').read_bytes()
    checked = subprocess.run(['git', 'apply', '--check', '-'], input=patch, cwd=original, capture_output=True)
    assert checked.returncode == 0, checked.stderr.decode()
    applied = subprocess.run(['git', 'apply', '-'], input=patch, cwd=original, capture_output=True)
    assert applied.returncode == 0, applied.stderr.decode()
    for name, expected in manifest['candidate_sha256'].items():
        assert (original / name).read_bytes() == (output / name).read_bytes()
        assert remediation.sha((output / name).read_bytes()) == expected
        assert (output / name).stat().st_mode & 0o777 == 0o600
    assert output.stat().st_mode & 0o777 == 0o700
    assert json.loads((output / 'manifest.json').read_text()) == manifest
    assert not manifest['deployed'] and not manifest['candidate_executed'] and not manifest['weights_downloaded']
    assert manifest['inference_requests'] == 0 and not manifest['D70_complete'] and not manifest['D71_started']
    with pytest.raises(FileExistsError):
        remediation.publish_candidate(sources, output)


def test_modified_candidate_cannot_be_packaged_as_the_frozen_recipe(sources):
    """Refuse a source patch that quietly adds a decoder, context, prompt or model change after candidate creation."""
    candidates = remediation.build_candidates(sources)
    changed = copy.deepcopy(candidates)
    changed['app.py'] = changed['app.py'].replace(b'max_new_tokens=1024', b'max_new_tokens=16')
    with pytest.raises(ValueError, match='candidate_changed'):
        remediation.build_patch(sources, changed)


def test_output_symlink_and_ambiguous_replacement_are_rejected(sources, tmp_path):
    """Keep output publication exclusive and reject guessed edits when a structural anchor is not unique."""
    target = tmp_path / 'target'
    target.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match='output_symlink'):
        remediation.publish_candidate(sources, link)
    assert list(target.iterdir()) == []
    for text in ['absent', 'duplicate duplicate']:
        with pytest.raises(ValueError, match='source_structure'):
            remediation.replace_once(text, 'duplicate', 'changed')
