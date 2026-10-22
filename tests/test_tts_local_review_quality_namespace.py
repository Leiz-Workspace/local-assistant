"""Probe the real sealed quality namespace and native two-audio processor using authored signals, without model loading or neural generation."""

import importlib.util
import json
import logging
import subprocess
from pathlib import Path


def processor_probe():
    """Check parent metadata absence and genuine multi-audio token/features with existing local processor assets only."""
    import numpy as np
    import torch
    from transformers import Qwen2_5OmniProcessor

    from scripts import tts_local_review_quality_runtime as runtime

    assert importlib.util.find_spec("scripts.tts_local_review_quality") is None
    assert not Path("/app/scripts/tts_local_review_quality.py").exists()
    assert not hasattr(runtime, "SOURCES") and not hasattr(runtime, "prepare_controls")
    assert not Path("/samples/parent-only.json").exists()
    assert not Path("/home/korosaki-ryukai/Workspace/Server/ai").exists()
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    processor = Qwen2_5OmniProcessor.from_pretrained("/model", local_files_only=True, trust_remote_code=False)
    values = [(0.1 * np.sin(np.arange(count) * 0.1)).astype("<f4") for count in [16000, 32000]]
    content = [dict(type="text", text="First audio:"), dict(type="audio", audio="opaque-a"), dict(type="text", text="Second audio:"), dict(type="audio", audio="opaque-b"), dict(type="text", text=runtime.TASKS["comparison"][0])]
    text = processor.apply_chat_template([dict(role="user", content=content)], add_generation_prompt=True, tokenize=False)
    inputs = processor(text=text, audio=values, sampling_rate=16000, return_tensors="pt", padding=True)
    frames = inputs["feature_attention_mask"].sum(dim=1).tolist()
    assert inputs["input_features"].shape[:2] == (2, 128)
    assert frames == [100, 200]
    audio_tokens = int((inputs["input_ids"] == processor.tokenizer.convert_tokens_to_ids("<|AUDIO|>")).sum())
    expected_tokens = sum(((int(frame) - 1) // 2 + 1 - 2) // 2 + 1 for frame in frames)
    assert audio_tokens == expected_tokens and audio_tokens > 0
    print(json.dumps(dict(parent_metadata_unmounted=True, native_processor_only=True, original_model_loaded=False, neural_generation=False, feature_shape=list(inputs["input_features"].shape), feature_frames=frames, audio_tokens=audio_tokens)), flush=True)


def test_native_two_audio_processor_and_namespace(tmp_path):
    """Exercise the actual bwrap mount layout and original processor rather than claiming model pairwise ability from mocks."""
    from scripts import tts_local_review as controller
    from scripts.tts_local_review_assets import PROJECT

    command = controller.sandbox("imports", tmp_path)
    position = command.index("--chdir")
    command[position:position] = ["--ro-bind", str(PROJECT / "tests/test_tts_local_review_quality_namespace.py"), "/app/probe.py"]
    command[-1] = "/app/probe.py"
    result = subprocess.run(command, capture_output=True, timeout=45, check=False)
    logging.getLogger(__name__).info("quality_processor_namespace_probe exit_code=%d stdout=%s stderr=%s", result.returncode, result.stdout.decode(), result.stderr.decode())
    assert result.returncode == 0, result.stderr.decode()
    evidence = json.loads(result.stdout.splitlines()[-1])
    assert evidence["parent_metadata_unmounted"] and evidence["native_processor_only"]
    assert not evidence["original_model_loaded"] and not evidence["neural_generation"]


if __name__ == "__main__":
    processor_probe()
