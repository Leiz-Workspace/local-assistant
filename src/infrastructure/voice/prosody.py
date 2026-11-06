"""Preserve question punctuation through the original CPU engine's phoneme API in isolated research."""

import hashlib
import logging

LOGGER = logging.getLogger(__name__)


def preserving_chunks(text, normalize, split, pack, classify, max_chars=256):
    """Normalize with punctuation preservation and use original sentence packing without forced short-question periods."""
    if (
        type(text) is not str
        or not text.strip()
        or len(text.encode()) > 4096
        or (max_chars != 256)
    ):
        raise ValueError("prosody_text_or_chunk_bound")
    sentences = [normalize(sentence, punc_norm=False) for sentence in split(text)]
    chunks = []
    for sentence in sentences:
        if len(sentence) > max_chars:
            raise ValueError("prosody_clause_too_long")
        packed = pack([sentence], max_chars=max_chars)
        if packed != [sentence.strip()]:
            raise ValueError("prosody_sentence_packing_changed")
        chunks.extend(packed)
    if not chunks or len(chunks) > 8 or any((not chunk.strip() for chunk in chunks)):
        raise ValueError("prosody_chunk_count")
    chunks = [
        chunk
        if chunk[-1] in ".,!?;:"
        else chunk + ("," if index < len(chunks) - 1 else ".")
        for index, chunk in enumerate(chunks)
    ]
    gaps = [classify(chunk) for chunk in chunks[:-1]]
    LOGGER.info("prosody_chunks_preserved chunks=%d", len(chunks))
    return (chunks, gaps)


class ProsodyAdapter:
    """Use existing speaker presets, sampling, frame caps, codec and joining with explicit question-preserving phonemes."""

    def __init__(self, wrapper, dependencies=None):
        """Bind the existing loaded SDK wrapper without changing any weights, files or global SDK functions."""
        if dependencies is None:
            from sea_g2p import Normalizer, G2P
            from vieneu_utils.core_utils import (
                split_into_sentences,
                pack_sentences_into_chunks,
                _classify_gap,
                gaps_to_silence,
                join_audio_chunks,
                max_expected_frames,
            )
            from vieneu._v3_turbo_engine.rep_history import DEFAULT_REP_WINDOW

            dependencies = dict(
                normalize=Normalizer(lang="vi").normalize,
                phonemize=G2P(lang="vi").convert,
                split=split_into_sentences,
                pack=pack_sentences_into_chunks,
                classify=_classify_gap,
                pauses=gaps_to_silence,
                join=join_audio_chunks,
                frame_cap=max_expected_frames,
                repetition_window=DEFAULT_REP_WINDOW,
            )
        self.wrapper, self.dependencies = (wrapper, dependencies)
        self.last_trace, self.last_chunks = (None, ())
        LOGGER.info("question_preserving_adapter_bound deployment=False")

    def infer(self, text, *, voice):
        """Generate each ordered chunk once through the original engine and retain native parts before original joining."""
        if voice not in {"Trúc Ly", "Ngọc Huyền"}:
            raise ValueError("prosody_preset")
        deps = self.dependencies
        chunks, gaps = preserving_chunks(
            text, deps["normalize"], deps["split"], deps["pack"], deps["classify"]
        )
        speaker, codes = self.wrapper._resolve_ref(voice, None, True, True)
        phonemes = [deps["phonemize"](chunk, punc_norm=False) for chunk in chunks]
        wavs = []
        for ph in phonemes:
            wavs.append(
                self.wrapper.engine.infer(
                    phonemes=ph,
                    speaker_emb=speaker,
                    ref_codes=codes,
                    use_ref_codes=True,
                    temperature=0.8,
                    top_k=25,
                    top_p=0.95,
                    max_new_frames=min(300, deps["frame_cap"](ph)),
                    repetition_penalty=1.2,
                    repetition_window=deps["repetition_window"],
                )
            )
        self.last_chunks = tuple(wavs)
        self.last_trace = dict(
            chunks=chunks,
            gaps=gaps,
            phonemes=phonemes,
            native_chunk_sha256=[
                hashlib.sha256(wav.tobytes()).hexdigest() for wav in wavs
            ],
            short_question_punctuation_preserved=True,
            phoneme_api=True,
            original_joining=True,
            sampling_unchanged=True,
            frame_caps_unchanged=True,
        )
        result = deps["join"](
            wavs, self.wrapper.sample_rate, silence_ps=deps["pauses"](gaps)
        )
        LOGGER.info("question_preserving_synthesis_returned chunks=%d", len(wavs))
        return self.wrapper._apply_watermark(result)
