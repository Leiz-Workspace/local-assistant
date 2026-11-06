"""Check an unapproved local evaluator's shape-only storage feasibility using the existing sealed SDK, without weights, installation or generation."""

import json
import logging
import subprocess
from pathlib import Path


def meta_probe():
    """Count native Voxtral meta tensors only and distinguish parameter bytes from persistent checkpoint storage."""
    import torch
    from transformers import VoxtralConfig, VoxtralForConditionalGeneration

    config = VoxtralConfig.from_dict(json.loads(Path('/app/voxtral-config.json').read_text()))
    with torch.device('meta'):
        model = VoxtralForConditionalGeneration(config)
    assert model._keep_in_fp32_modules_strict == ['embed_positions']
    model.to(dtype=torch.bfloat16)
    model.audio_tower.embed_positions.to(dtype=torch.float32)
    tensors = list(model.parameters()) + list(model.buffers())
    assert tensors and all(tensor.is_meta for tensor in tensors)
    state = model.state_dict()
    print(json.dumps(dict(
        parameters=sum(tensor.numel() for tensor in model.parameters()),
        all_BF16_parameter_lower_bound=sum(tensor.numel() * 2 for tensor in model.parameters()),
        native_parameter_bytes=sum(tensor.numel() * tensor.element_size() for tensor in model.parameters()),
        native_persistent_state_bytes=sum(tensor.numel() * tensor.element_size() for tensor in state.values()),
        strict_FP32_position_bytes=model.audio_tower.embed_positions.weight.numel() * 4,
        state_tensors=len(state),
        all_tensors_meta=True,
        checkpoint_weights_loaded=False,
        neural_generation=False,
        measured_model_RAM=False,
    )), flush=True)


def test_native_voxtral_meta_matches_checkpoint_metadata(tmp_path):
    """Verify the architecture/index correspondence inside the original12GiB offline CPU namespace without claiming load or Vietnamese quality."""
    from scripts import tts_local_review as controller
    from scripts.tts_local_review_assets import PROJECT

    metadata = PROJECT / 'data/backups/d70-local-alternative-metadata-first'
    expected = json.loads((metadata / 'model.safetensors.index.json').read_text())['metadata']
    command = controller.sandbox('imports', tmp_path)
    index = command.index('--chdir')
    command[index:index] = [
        '--ro-bind', str(PROJECT / 'tests/test_tts_voxtral_meta.py'), '/app/voxtral_meta_probe.py',
        '--ro-bind', str(metadata / 'config.json'), '/app/voxtral-config.json',
    ]
    command[-1] = '/app/voxtral_meta_probe.py'
    result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    logging.getLogger(__name__).info('voxtral_meta_only_probe exit_code=%d stdout=%s stderr=%s', result.returncode, result.stdout.decode(), result.stderr.decode())
    assert result.returncode == 0, result.stderr.decode()
    counted = json.loads(result.stdout.splitlines()[-1])
    assert counted['parameters'] == expected['total_parameters']
    assert counted['native_persistent_state_bytes'] == expected['total_size']
    assert counted['strict_FP32_position_bytes'] == 1500 * 1280 * 4
    assert counted['native_persistent_state_bytes'] - counted['all_BF16_parameter_lower_bound'] == 1500 * 1280 * 2
    assert counted['native_persistent_state_bytes'] < 12 * 1024**3
    assert counted['all_tensors_meta'] and not counted['checkpoint_weights_loaded'] and not counted['neural_generation']


if __name__ == '__main__':
    meta_probe()
