"""Test the offline GGUF special-literal generator on synthetic vocabularies (ADR-195 commit A)."""

import hashlib
import struct

import pytest

from scripts import core_special_literals as generator

MODULE_TEMPLATE = '"""Pinned list."""\n\nBEFORE = 1\n\n{block}\nAFTER = 2\n'


def gguf_string(text):
    """Encode one GGUF string."""
    data = text.encode("utf-8")
    return struct.pack("<Q", len(data)) + data


def write_gguf(path, tokens, types, version=3, extra=True):
    """Write a minimal GGUF file with a vocabulary and a few unrelated keys of other types."""
    entries = []
    if extra:
        entries.append(
            gguf_string("general.name") + struct.pack("<I", 8) + gguf_string("tiny")
        )
        entries.append(
            gguf_string("general.alignment")
            + struct.pack("<I", 4)
            + struct.pack("<I", 32)
        )
        entries.append(
            gguf_string("tokenizer.ggml.merges")
            + struct.pack("<I", 9)
            + struct.pack("<IQ", 8, 2)
            + gguf_string("a b")
            + gguf_string("c d")
        )
        entries.append(
            gguf_string("tokenizer.ggml.scores")
            + struct.pack("<I", 9)
            + struct.pack("<IQ", 6, 2)
            + struct.pack("<ff", 0.5, 1.5)
        )
    entries.append(
        gguf_string("tokenizer.ggml.tokens")
        + struct.pack("<I", 9)
        + struct.pack("<IQ", 8, len(tokens))
        + b"".join(gguf_string(token) for token in tokens)
    )
    entries.append(
        gguf_string("tokenizer.ggml.token_type")
        + struct.pack("<I", 9)
        + struct.pack("<IQ", 5, len(types))
        + b"".join(struct.pack("<i", value) for value in types)
    )
    header = (
        b"GGUF"
        + struct.pack("<I", version)
        + struct.pack("<Q", 0)
        + struct.pack("<Q", len(entries))
    )
    path.write_bytes(header + b"".join(entries))
    return hashlib.sha256(path.read_bytes()).hexdigest()


VOCAB = [
    ("hello", 1),
    ("<|im_start|>", 3),
    ("<think>", 4),
    ("<unk>", 2),
    ("<|im_end|>", 1),
    ("<|channel|>", 1),
    ("[PAD000001]", 5),
    ("<0x0A>", 6),
    ("<|fim_pad|>", 5),
]


def make_setup(tmp_path, core_vocab=VOCAB, unrestricted_vocab=VOCAB):
    """Create both GGUF files, a models.yaml and a module with an empty generated block."""
    core_sha = write_gguf(tmp_path / "core.gguf", *zip(*core_vocab))
    unrestricted_sha = write_gguf(tmp_path / "unr.gguf", *zip(*unrestricted_vocab))
    config = tmp_path / "models.yaml"
    config.write_text(
        "models:\n"
        f"  core:\n    path: core.gguf\n    sha256: {core_sha}\n"
        f"  unrestricted:\n    path: unr.gguf\n    sha256: {unrestricted_sha}\n",
        encoding="utf-8",
    )
    module = tmp_path / "special_literals.py"
    module.write_text(
        MODULE_TEMPLATE.format(block=generator.BEGIN + generator.END), encoding="utf-8"
    )
    return config, module


def run(tmp_path, config, module, *extra):
    """Call the generator entry point."""
    return generator.main(
        [
            "--config",
            str(config),
            "--module",
            str(module),
            "--root",
            str(tmp_path),
            *extra,
        ]
    )


def test_reader_skips_other_keys_and_returns_the_vocabulary(tmp_path):
    write_gguf(tmp_path / "v.gguf", ["a", "<b>"], [1, 3])
    assert generator.read_vocab(tmp_path / "v.gguf") == (["a", "<b>"], [1, 3])
    write_gguf(tmp_path / "v2.gguf", ["a"], [1], version=2, extra=False)
    assert generator.read_vocab(tmp_path / "v2.gguf") == (["a"], [1])


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda data: b"GGML" + data[4:], "gguf_magic"),
        (lambda data: data[:4] + struct.pack("<I", 1) + data[8:], "gguf_version"),
        (lambda data: data[:-3], "gguf_truncated"),
    ],
)
def test_reader_refuses_malformed_files(tmp_path, mutate, reason):
    path = tmp_path / "bad.gguf"
    write_gguf(path, ["a", "<b>"], [1, 3])
    path.write_bytes(mutate(path.read_bytes()))
    with pytest.raises(generator.LiteralError, match=reason):
        generator.read_vocab(path)


def test_reader_requires_the_vocabulary(tmp_path):
    path = tmp_path / "novocab.gguf"
    path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, 0))
    with pytest.raises(generator.LiteralError, match="gguf_vocab_missing"):
        generator.read_vocab(path)


def test_runtime_attribute_rules_follow_the_pinned_llama_cpp():
    tokens, types = zip(*VOCAB)
    assert generator.special_tokens(tokens, types) == [
        (1, "control", "<|im_start|>"),
        (2, "user_defined", "<think>"),
        (3, "unknown", "<unk>"),
        (4, "control", "<|im_end|>"),
        (5, "user_defined", "<|channel|>"),
        (8, "control", "<|fim_pad|>"),
    ]


@pytest.mark.parametrize("bad", ["<a<b>", "x<y>", "<a\\b>"])
def test_special_tokens_with_an_unsafe_shape_are_refused(bad):
    with pytest.raises(generator.LiteralError, match="literal_shape"):
        generator.special_tokens(["a", bad], [1, 3])


def test_write_then_check_is_current_and_keeps_the_rest_of_the_module(tmp_path):
    config, module = make_setup(tmp_path)
    assert run(tmp_path, config, module, "--check") == 1
    assert run(tmp_path, config, module, "--write") == 0
    text = module.read_text(encoding="utf-8")
    assert text.startswith('"""Pinned list."""\n\nBEFORE = 1\n\n') and text.endswith(
        "\nAFTER = 2\n"
    )
    assert (
        '(1, "control", "<|im_start|>"),' in text
        and '(5, "user_defined", "<|channel|>"),' in text
    )
    assert run(tmp_path, config, module, "--check") == 0
    namespace = {}
    exec(compile(text, "special_literals.py", "exec"), namespace)
    assert [entry[2] for entry in namespace["CORE_SPECIAL_TOKENS"]] == [
        "<|im_start|>",
        "<think>",
        "<unk>",
        "<|im_end|>",
        "<|channel|>",
        "<|fim_pad|>",
    ]
    assert set(namespace["BOUND_MODEL_SHA256"]) == {"core", "unrestricted"}


def test_differing_vocabularies_are_refused(tmp_path, capsys):
    config, module = make_setup(tmp_path, unrestricted_vocab=VOCAB[:-1])
    assert run(tmp_path, config, module, "--write") == 2
    assert "reason=special_lists_differ" in capsys.readouterr().err


def test_hash_mismatch_is_refused_unless_skipped(tmp_path, capsys):
    config, module = make_setup(tmp_path)
    (tmp_path / "core.gguf").write_bytes((tmp_path / "core.gguf").read_bytes() + b"\0")
    assert run(tmp_path, config, module, "--check") == 2
    assert "reason=gguf_sha256_mismatch_core" in capsys.readouterr().err
    assert run(tmp_path, config, module, "--write", "--skip-hash") == 0


def test_missing_markers_and_missing_files_are_refused(tmp_path, capsys):
    config, module = make_setup(tmp_path)
    module.write_text("no markers\n", encoding="utf-8")
    assert run(tmp_path, config, module, "--write") == 2
    assert "reason=module_markers" in capsys.readouterr().err
    (tmp_path / "unr.gguf").unlink()
    assert run(tmp_path, config, module, "--check") == 2
    assert "reason=gguf_missing_unrestricted" in capsys.readouterr().err


def test_render_output_is_stable_python():
    block = generator.render(
        [(7, "control", '<a"b>')], {"core": "a" * 64, "unrestricted": "b" * 64}
    )
    namespace = {}
    exec(block, namespace)
    assert namespace["CORE_SPECIAL_TOKENS"] == ((7, "control", '<a"b>'),)
