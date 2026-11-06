"""Check native loader buffers, audio cache routing and encoder SDPA using authored random fixtures without original models or recordings."""

import argparse
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def tiny_config():
    """Create a bounded fixture preserving GQA, unequal projection widths, four-frame audio grouping and the retained RoPE base."""
    from transformers import VoxtralConfig

    return VoxtralConfig(
        audio_config=dict(model_type="voxtral_encoder", hidden_size=8, intermediate_size=32, num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=2, head_dim=4, num_mel_bins=4, max_source_positions=8),
        text_config=dict(model_type="llama", hidden_size=12, intermediate_size=24, num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2, head_dim=4, vocab_size=64, max_position_embeddings=128, rope_theta=100000000.0),
        hidden_size=12, vocab_size=64, audio_token_id=24,
    )


def random_model():
    """Initialize fewer than twenty thousand authored random parameters with native BF16 and FP32 audio positions."""
    import torch
    from transformers import VoxtralForConditionalGeneration

    config = tiny_config()
    config._attn_implementation = "eager"
    model = VoxtralForConditionalGeneration(config).to(dtype=torch.bfloat16).eval()
    model.audio_tower.embed_positions.to(dtype=torch.float32)
    assert sum(t.numel() for t in model.parameters()) < 20000
    return model


def buffer_probe():
    """Compare standard and retained pread loaders on identical tiny checkpoint bytes, including nonpersistent RoPE buffers and logits."""
    import torch
    import worker
    from safetensors.torch import save_file
    from transformers import VoxtralForConditionalGeneration

    authored = random_model()
    state = authored.state_dict()
    directory = Path("/tmp/authored-checkpoint")
    directory.mkdir()
    (directory / "config.json").write_text(authored.config.to_json_string())
    names = sorted(state)
    parts = [names[:len(names) // 2], names[len(names) // 2:]]
    mapping = {}
    for number, keys in enumerate(parts, 1):
        name = f"model-{number:05d}-of-00002.safetensors"
        save_file({key: state[key] for key in keys}, directory / name)
        mapping.update({key: name for key in keys})
    (directory / "model.safetensors.index.json").write_text(json.dumps(dict(metadata=dict(total_size=sum(t.numel() * t.element_size() for t in state.values())), weight_map=mapping)))
    reference = VoxtralForConditionalGeneration.from_pretrained(directory, dtype=torch.bfloat16, attn_implementation="eager", local_files_only=True).eval()
    events = []

    def record(event, **fields):
        """Retain fixture-only load receipts without exposing checkpoint paths or invoking the original guarded CLI."""
        events.append(dict(event=event, **fields))

    actual = worker.load_native(directory, record)
    expected_buffers, actual_buffers = dict(reference.named_buffers()), dict(actual.named_buffers())
    assert expected_buffers and set(expected_buffers) == set(actual_buffers)
    buffers = []
    for name, value in expected_buffers.items():
        other = actual_buffers[name]
        assert value.dtype == other.dtype and torch.isfinite(other).all() and torch.equal(value, other)
        buffers.append(dict(name=name, dtype=str(value.dtype), shape=list(value.shape), equal=True, persistent=name in reference.state_dict()))
    assert any(not row["persistent"] and "inv_freq" in row["name"] for row in buffers)
    assert torch.equal(reference.language_model.model.rotary_emb.original_inv_freq, actual.language_model.model.rotary_emb.original_inv_freq)
    ids = torch.tensor([[1, 24, 24, 5, 6]])
    features = torch.randn(1, 4, 16, dtype=torch.bfloat16)
    with torch.inference_mode():
        expected = reference(input_ids=ids, input_features=features, use_cache=False).logits
        observed = actual(input_ids=ids, input_features=features, use_cache=False).logits
    assert torch.isfinite(observed).all()
    torch.testing.assert_close(expected, observed, rtol=0, atol=0)
    logger.info("voxtral_synthetic_buffers_verified buffers=%d exact_logits=True", len(buffers))
    return dict(buffers=buffers, maximum_logit_difference=float((expected - observed).abs().max()), parameters=sum(t.numel() for t in actual.parameters()), tensors=len(state), loader_events=[row["event"] for row in events])


def cache_probe():
    """Verify eager and SDPA audio forwarding with cached versus full recomputation on identical authored inputs."""
    import torch

    model = random_model()
    ids = torch.tensor([[1, 24, 24, 5, 6]])
    features = torch.randn(1, 4, 16, dtype=torch.bfloat16)
    calls = []

    def record(module, arguments):
        """Count actual tiny audio-encoder invocations without replacing native embedding or generation behavior."""
        calls.append(list(arguments[0].shape))

    hook = model.audio_tower.register_forward_pre_hook(record)
    observations = []
    try:
        with torch.inference_mode():
            for backend in ["eager", "sdpa"]:
                model.set_attn_implementation(backend)
                calls.clear()
                cached = model.generate(input_ids=ids, input_features=features, attention_mask=torch.ones_like(ids), do_sample=False, max_new_tokens=4, eos_token_id=None, pad_token_id=11, bos_token_id=1, use_cache=True, logits_to_keep=1)
                cached_calls = len(calls)
                calls.clear()
                uncached = model.generate(input_ids=ids, input_features=features, attention_mask=torch.ones_like(ids), do_sample=False, max_new_tokens=4, eos_token_id=None, pad_token_id=11, bos_token_id=1, use_cache=False, logits_to_keep=1)
                assert cached_calls == 1 and len(calls) == 4
                assert cached.shape[1] == ids.shape[1] + 4 and torch.equal(cached, uncached)
                observations.append(dict(backend=backend, cached_audio_encoder_calls=cached_calls, uncached_audio_encoder_calls=len(calls), generated_tokens=4, cached_and_uncached_tokens_equal=True))
    finally:
        hook.remove()
    logger.info("voxtral_synthetic_cache_verified backends=2 cached_audio_calls=1 uncached_audio_calls=4")
    return dict(backends=observations)


def mel_probe():
    """Compare native Whisper features with independently assembled Mistral filter-bank/STFT math on four authored signals."""
    import numpy as np
    import torch
    from mistral_common.audio import mel_filter_bank
    from transformers import WhisperFeatureExtractor

    native = WhisperFeatureExtractor(feature_size=128, sampling_rate=16000, hop_length=160, n_fft=400, chunk_length=30, dither=0)
    bank = mel_filter_bank(201, 128, 0, 8000, 16000)
    np.testing.assert_allclose(bank, native.mel_filters, rtol=1e-12, atol=1e-14)
    phase = np.arange(32000) / 16000
    signals = dict(silence=np.zeros(64000, dtype="<f4"), two_tones=(0.1 * np.sin(2 * np.pi * 440 * phase) + 0.03 * np.sin(2 * np.pi * 1234 * phase)).astype("<f4"), noise=np.random.default_rng(110).normal(0, 0.05, 64000).astype("<f4"), step=np.r_[np.full(16000, 0.1), np.full(16000, -0.1)].astype("<f4"))
    observations = []
    for name, signal in signals.items():
        padded = np.pad(signal, (0, 480000 - len(signal)))
        observed = native([padded], sampling_rate=16000, return_tensors="pt").input_features[0]
        spectrum = torch.stft(torch.from_numpy(padded), 400, hop_length=160, window=torch.hann_window(400), return_complex=True)
        powers = spectrum[:, :-1].abs().square()
        logarithm = (torch.from_numpy(bank).to(torch.float32).T @ powers).clamp(min=1e-10).log10()
        reference = (torch.maximum(logarithm, logarithm.max() - 8.0) + 4.0) / 4.0
        assert observed.shape == reference.shape == (128, 3000) and torch.isfinite(observed).all()
        torch.testing.assert_close(observed, reference, rtol=1e-5, atol=2e-6)
        if name == "silence":
            assert torch.equal(observed, torch.full_like(observed, -1.5))
        observations.append(dict(signal=name, samples=len(signal), padded_samples=len(padded), maximum_absolute_feature_difference=float((observed - reference).abs().max())))
    logger.info("voxtral_synthetic_mel_verified signals=4 bank_shape=201x128 frames=3000")
    return dict(filter_bank_maximum_difference=float(np.abs(bank - native.mel_filters).max()), signals=observations)


def attention_probe():
    """Compare native eager and SDPA on one random original-width audio-attention block at the actual encoder sequence length."""
    import torch
    from transformers import VoxtralEncoderConfig
    from transformers.models.voxtral.modeling_voxtral import VoxtralAttention

    config = VoxtralEncoderConfig(hidden_size=1280, num_attention_heads=20, max_source_positions=1500)
    config._attn_implementation = "eager"
    block = VoxtralAttention(embed_dim=1280, num_heads=20, config=config).to(dtype=torch.bfloat16).eval()
    inputs = torch.randn(1, 1500, 1280, dtype=torch.bfloat16) * 0.25
    altered = inputs.clone()
    altered[:, 750:] += 0.5
    with torch.inference_mode():
        expected = block(inputs)[0]
        config._attn_implementation = "sdpa"
        actual = block(inputs)[0]
        future_changed = block(altered)[0]
    assert torch.isfinite(actual).all() and block.is_causal is False
    torch.testing.assert_close(expected, actual, rtol=0.1, atol=0.01)
    assert not torch.equal(actual[:, :750], future_changed[:, :750])
    logger.info("voxtral_synthetic_attention_verified length=1500 heads=20 bidirectional=True")
    return dict(sequence_length=1500, hidden_size=1280, heads=20, head_dim=64, dtype="torch.bfloat16", maximum_absolute_difference=float((expected - actual).abs().max()), bidirectional_future_influence=True, is_causal=False, random_attention_parameters=sum(t.numel() for t in block.parameters()))


def main():
    """Run only fixed synthetic probes in the sealed CPU namespace with no original model or recorded-audio mounts."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", choices=["buffers", "cache", "attention", "mel"])
    args = parser.parse_args()
    assert not Path("/model").exists() and not Path("/samples").exists()
    assert os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("CUDA_VISIBLE_DEVICES") == ""
    os.sched_setaffinity(0, {0, 1})
    import torch

    assert torch.version.cuda is None
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(110)
    result = {"buffers": buffer_probe, "cache": cache_probe, "attention": attention_probe, "mel": mel_probe}[args.probe]()
    print(json.dumps(dict(description=__doc__, probe=args.probe, original_weights_mounted=False, recorded_audio_mounted=False, original_weight_predictions=0, **result)), flush=True)


if __name__ == "__main__":
    main()
