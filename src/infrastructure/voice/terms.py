"""Retain accepted term spellings and preset reference binding without evaluation corpora."""

import hashlib
import logging
from src.infrastructure.voice.prosody import ProsodyAdapter

LOGGER = logging.getLogger(__name__)
TERMS = {
    "python": ("pˈaɪθən", "pˈaɪθɑːn"),
    "github": ("ɡˈɪt hˈʌb", "ɡˈɪthʌb"),
    "server": ("sˈɜːvɚ", "sˈɜːɹvɚ"),
}
SOURCE = "ˈeɪ pˈiː ˈaɪ"
TARGET = "ˌeɪ pˌiː ˈaɪ"


class TermsAdapter(ProsodyAdapter):
    """Change only declared term phones while reusing original clause, voice, sampling and joining code."""

    def __init__(self, wrapper, mode, dependencies=None):
        """Bind one explicit role and retain the original dependency objects and resolver."""
        if mode not in {"baseline", "us"}:
            raise ValueError("us_terms_mode")
        super().__init__(wrapper, dependencies)
        self.mode = mode
        self.original = dict(self.dependencies)
        self.dependencies = dict(
            self.dependencies, phonemize=self.phonemize, frame_cap=self.frame_cap
        )
        self.original_resolver = wrapper._resolve_ref
        wrapper._resolve_ref = self.resolve
        self.plan = None
        self.binding = None
        self.case = None
        LOGGER.info("us_terms_adapter_bound mode=%s", mode)

    def resolve(self, voice, reference, denoise, use_codes):
        """Audit genuine original speaker/reference objects without changing their identity or values."""
        if denoise is not True or use_codes is not True or reference is not None:
            raise ValueError("us_terms_reference_policy")
        speaker, codes = self.original_resolver(voice, reference, denoise, use_codes)
        if codes is None:
            raise ValueError("us_terms_reference_codes_missing")
        self.binding = dict(
            speaker_sha256=hashlib.sha256(speaker.tobytes()).hexdigest(),
            reference_codes_sha256=hashlib.sha256(codes.tobytes()).hexdigest(),
        )
        LOGGER.info("us_terms_voice_bound voice=%s mode=%s", voice, self.mode)
        return (speaker, codes)
