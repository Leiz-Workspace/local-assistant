"""Prepare and audit one explicitly gated held-out audio-presence diagnostic without granting naturalness or reviewer qualification."""

import hashlib
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)
QUESTION = "Does this audio contain any intelligible human speech? Answer exactly yes, no, or uncertain."
MAX_TOKENS = 16
SOURCES = {
    "en_us-0001": (126720, "ba28baf3162a91509342ddbd17f5dc906e664c65dfa0693bd55aa4fcd3ad5273"),
    "vi_vn-0001": (148800, "8cf49bc6f5f2e54188db71944091fd25ebf09eb1d3aeeadd6ff8412a301d4d15"),
}


def parse_answer(raw):
    """Accept exact lowercase factual labels without repairing JSON, prose, punctuation or uncertain answers into success."""
    if type(raw) is not str or raw.strip() not in {"yes", "no", "uncertain"}:
        raise ValueError("local_diagnostic_answer")
    return raw.strip()


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


def audit_events(request, events):
    """Require complete source-bound factual responses and genuine termination while never conferring naturalness qualification."""
    rows = [event for event in events if event.get("event") == "diagnostic"]
    if len(request["cases"]) != 4 or [row.get("id") for row in rows] != [row["id"] for row in request["cases"]]:
        return False
    if any(sum(event.get("event") == name for event in events) != 1 for name in ["ready", "complete"]):
        return False
    if any(event.get("event") == "review" for event in events):
        return False
    for source, event in zip(request["cases"], rows, strict=True):
        expected = dict(source_sha256=source["sha256"], sample_count=source["sample_count"], sample_rate=16000, generation_complete=True, question=QUESTION, maximum_new_tokens=MAX_TOKENS)
        if any(event.get(key) != value for key, value in expected.items()):
            return False
        tokens = event.get("generated_token_ids", [])
        if type(tokens) is not list or not tokens or len(tokens) > MAX_TOKENS or any(type(token) is not int or token < 0 for token in tokens) or tokens[-1] != 151645 or event.get("audio_tokens", 0) <= 0 or event.get("feature_frames", 0) <= 0:
            return False
        feature_hash = event.get("feature_sha256")
        shape = event.get("feature_shape")
        if type(feature_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", feature_hash) is None or type(shape) is not list or len(shape) != 3 or shape[:2] != [1, 128] or type(shape[2]) is not int or shape[2] < event["feature_frames"]:
            return False
        if event.get("generation_complete") is not True or event.get("parse_error") is not None:
            return False
        try:
            if parse_answer(event.get("raw_text")) != event.get("answer"):
                return False
        except ValueError:
            return False
    logger.info("local_audio_presence_diagnostic_observations_verified cases=4 naturalness_qualification=False")
    return True
