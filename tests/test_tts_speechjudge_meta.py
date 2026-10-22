"""Verify architecture-only BF16 lower bounds against native meta tensors without loading checkpoint weights or generating audio judgements."""

import json
import logging
import subprocess


def meta_probe():
    """Count a native text skeleton on the meta device using authored tiny modality branches and public7Btext dimensions only."""
    import torch
    from transformers import (
        Qwen2_5OmniThinkerConfig,
        Qwen2_5OmniThinkerForConditionalGeneration,
    )

    text = dict(model_type="qwen2_5_omni_text", hidden_size=3584, intermediate_size=18944, vocab_size=152064, num_hidden_layers=28, num_attention_heads=28, num_key_value_heads=4, tie_word_embeddings=False)
    config = Qwen2_5OmniThinkerConfig(
        audio_config=dict(d_model=8, encoder_layers=1, encoder_attention_heads=2, encoder_ffn_dim=16, num_mel_bins=4, max_source_positions=16, output_dim=3584),
        vision_config=dict(depth=1, hidden_size=8, intermediate_size=16, num_heads=2, patch_size=2, spatial_merge_size=1, out_hidden_size=3584),
        text_config=text,
    )
    with torch.device("meta"):
        native = Qwen2_5OmniThinkerForConditionalGeneration(config)
    parameters = list(native.model.parameters()) + list(native.lm_head.parameters())
    assert all(parameter.device.type == "meta" for parameter in parameters)
    count = sum(parameter.numel() for parameter in parameters)
    print(json.dumps(dict(text_parameters=count, BF16_parameter_bytes=count * 2, all_tensors_meta=True, checkpoint_weights_loaded=False, neural_generation=False)), flush=True)


def test_native_meta_count_matches_analytic_bound(tmp_path):
    """Run the genuine SDK under the retained12GiBnamespace and compare native parameter counting with the metadata estimator."""
    from scripts import tts_local_review as controller
    from scripts import tts_speechjudge_review as specialist
    from scripts.tts_local_review_assets import PROJECT

    command = controller.sandbox("imports", tmp_path)
    index = command.index("--chdir")
    command[index:index] = ["--ro-bind", str(PROJECT / "tests/test_tts_speechjudge_meta.py"), "/app/meta_probe.py"]
    command[-1] = "/app/meta_probe.py"
    result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    logging.getLogger(__name__).info("specialist_meta_only_probe exit_code=%d stdout=%s stderr=%s", result.returncode, result.stdout.decode(), result.stderr.decode())
    assert result.returncode == 0, result.stderr.decode()
    counted = json.loads(result.stdout.splitlines()[-1])
    text = dict(model_type="qwen2_5_omni_text", hidden_size=3584, intermediate_size=18944, vocab_size=152064, num_hidden_layers=28, num_attention_heads=28, num_key_value_heads=4, tie_word_embeddings=False)
    expected = specialist.native_text_bf16_bound(text)
    assert counted["text_parameters"] == expected["text_parameters"]
    assert counted["BF16_parameter_bytes"] > 12 * 1024**3
    assert counted["all_tensors_meta"] and not counted["checkpoint_weights_loaded"] and not counted["neural_generation"]


if __name__ == "__main__":
    meta_probe()
