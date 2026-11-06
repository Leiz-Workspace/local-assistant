"""Prepare parent-only held-out factual controls and reexport pure audit helpers; this module must never be mounted in the worker."""

import hashlib
import logging
from pathlib import Path

from scripts.tts_local_review_diagnostic_runtime import MAX_TOKENS, QUESTION
from scripts.tts_local_review_diagnostic_runtime import audit_events as audit_events
from scripts.tts_local_review_diagnostic_runtime import parse_answer as parse_answer

logger = logging.getLogger(__name__)
SOURCES = {
    "en_us-0001": (126720, "ba28baf3162a91509342ddbd17f5dc906e664c65dfa0693bd55aa4fcd3ad5273"),
    "vi_vn-0001": (148800, "8cf49bc6f5f2e54188db71944091fd25ebf09eb1d3aeeadd6ff8412a301d4d15"),
}


def prepare_packet(root, project, publish):
    """Create a separate fixed blind packet only after explicit diagnostic permission and complete held-out source checks."""
    from scripts.asr_evaluation_corpus import save_bytes
    from scripts.tts_local_review_worker import require_execution_permission

    require_execution_permission("prepare-diagnose")
    import numpy as np

    directory = Path(project) / "data/backups/d68-asr-evaluation/prepared"
    signals, provenance = [], []
    for identity, (count, expected_hash) in SOURCES.items():
        source = directory / (identity + ".f32")
        raw = source.read_bytes()
        if len(raw) != count * 4 or hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError("local_diagnostic_heldout_source")
        signals.append(np.frombuffer(raw, dtype="<f4"))
        provenance.append(dict(source=str(source), sha256=expected_hash, expected="yes", transform=None))
    signals.extend([np.zeros(60000, dtype="<f4"), np.random.default_rng(102).normal(0, 0.05, 60000).astype("<f4")])
    provenance.extend([dict(source="authored_exact_zeros", expected="no", sample_count=60000), dict(source="authored_Gaussian_noise", expected="no", seed=102, mean=0, standard_deviation=0.05, sample_count=60000)])
    if any(not np.isfinite(values).all() or float(np.abs(values).max()) > 1 for values in signals):
        raise ValueError("local_diagnostic_source_values")
    packet = Path(root) / "diagnostic-103"
    packet.mkdir(mode=0o700, exist_ok=False)
    inputs = packet / "inputs"
    inputs.mkdir(mode=0o700)
    rows, mapping = [], []
    for index in np.random.default_rng(103).permutation(4):
        raw = signals[int(index)].tobytes()
        identity = f"clip-{len(rows) + 1:02d}"
        save_bytes(inputs / (identity + ".f32"), raw)
        rows.append(dict(id=identity, sample_count=len(raw) // 4, sha256=hashlib.sha256(raw).hexdigest()))
        mapping.append(dict(id=identity, **provenance[int(index)]))
    publish(packet / "request.json", dict(mode="diagnose", cases=rows))
    publish(packet / "parent-only.json", dict(description="Held-out factual diagnostic only. Expected answers and source identities are never mounted in the worker; no naturalness labels or reviewer qualification.", order_seed=103, question=QUESTION, maximum_new_tokens=MAX_TOKENS, mapping=mapping))
    logger.info("local_audio_presence_diagnostic_packet_frozen cases=4 original_sources_unchanged=True")
