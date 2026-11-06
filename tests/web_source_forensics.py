"""Inspect bounded exception types and known code-frame names without retaining source/page bytes, diagnostics, locals or credentials."""

import logging
from pathlib import Path

from web_observation_diagnostics import FiniteSourceObserver

from src.application.services.web_fetch_policy import ERROR_CODES

logger = logging.getLogger(__name__)
TYPES = frozenset(
    {
        "WebFetchError",
        "WebEvidenceError",
        "AttributeError",
        "TypeError",
        "ValueError",
        "KeyError",
        "RuntimeError",
        "UnicodeError",
        "SSLError",
        "ProtocolError",
        "TimeoutError",
        "OSError",
        "NameError",
    }
)
FILES = frozenset(
    {
        "public_https.py",
        "web_fetch.py",
        "static_web_text.py",
        "web_fetch_policy.py",
        "evidence_metadata.py",
        "web_evidence_source.py",
    }
)


def exception_metadata(error):
    """Retain at most eight original exception-type/finite-code/known-frame summaries while excluding raw messages and frame locals."""
    records, seen = [], set()
    while error is not None and len(records) < 8 and id(error) not in seen:
        seen.add(id(error))
        name, code = type(error).__name__, getattr(error, "code", None)
        frames, frame = [], error.__traceback__
        while frame is not None and len(frames) < 16:
            basename = Path(frame.tb_frame.f_code.co_filename).name
            if basename in FILES:
                frames.append(
                    dict(
                        module=basename,
                        function=frame.tb_frame.f_code.co_name,
                        line=frame.tb_lineno,
                    )
                )
            frame = frame.tb_next
        records.append(
            dict(
                type=name if name in TYPES else "other_exception",
                code=code if type(code) is str and code in ERROR_CODES else None,
                frames=frames,
            )
        )
        error = error.__context__
    logger.info("web_source_exception_chain_observed length=%d", len(records))
    return records


class ForensicSourceObserver(FiniteSourceObserver):
    """Extend the already bounded source observer with exception-context metadata before original redaction."""

    async def read(self, url, mode):
        """Delegate the unchanged source call and preserve only bounded original exception metadata on failure."""
        try:
            return await super().read(url, mode)
        except Exception as error:
            self.records[-1]["exception_chain"] = exception_metadata(error)
            raise
