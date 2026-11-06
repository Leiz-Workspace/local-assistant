"""Prepare private held-out quality controls and gate blind original-output review; never mount this parent-only module in a worker."""

import hashlib
import json
import logging
from collections import Counter
from pathlib import Path

from scripts.tts_local_review_quality_runtime import audit_events, validate_request
from scripts.tts_local_review_worker import require_execution_permission

logger = logging.getLogger(__name__)
SOURCES = {
    "en_us-0002": (94080, "5666c569fbad40208b387286b812cfc2161f604532023dabd30fc9adad79db1c"),
    "vi_vn-0002": (138240, "933ee308dcc8a81cb74687643d99183066e15f79d2051c8c45d05d9a6d017536"),
}


def sha(raw):
    """Fingerprint full source, request and evidence bytes without logging private labels or waveform contents."""
    return hashlib.sha256(raw).hexdigest()


def publish_packet(packet, mode, items, save_bytes, publish):
    """Publish shuffled opaque copies and separate private provenance exclusively, retaining full input timelines."""
    import numpy as np

    packet.mkdir(mode=0o700, exist_ok=False)
    inputs = packet / "inputs"
    inputs.mkdir(mode=0o700)
    rows, mapping = [], []
    for number, index in enumerate(np.random.default_rng(104).permutation(len(items)), start=1):
        item = items[int(index)]
        identity, signals = f"clip-{number:02d}", []
        for position, values in enumerate(item["values"]):
            raw = np.asarray(values, dtype="<f4").tobytes()
            if not 6400 <= len(raw) <= 1280000 or not np.isfinite(values).all() or float(np.abs(values).max()) > 1:
                raise ValueError("quality_source_values")
            signal_id = identity + "-" + "ab"[position]
            save_bytes(inputs / (signal_id + ".f32"), raw)
            signals.append(dict(id=signal_id, sample_count=len(raw) // 4, sha256=sha(raw)))
        rows.append(dict(id=identity, task=item["task"], signals=signals))
        mapping.append(dict(id=identity, **{key: value for key, value in item.items() if key != "values"}))
    request = dict(mode=mode, cases=rows)
    validate_request(request)
    publish(packet / "request.json", request)
    publish(packet / "parent-only.json", dict(description="Private source identities, transformations and expectations; never mounted in the worker. No human MOS or candidate selection.", order_seed=104, mapping=mapping))
    logger.info("quality_packet_frozen mode=%s cases=%d parent_labels_unmounted=True", mode, len(rows))


def prepare_controls(root, project, save_bytes, publish):
    """Freeze twelve new controls with balanced corruption orientations and identical ties after explicit campaign authorization."""
    require_execution_permission("prepare-quality")
    import numpy as np

    items, sources = [], []
    for identity, (count, expected) in SOURCES.items():
        path = Path(project) / "data/backups/d68-asr-evaluation/prepared" / (identity + ".f32")
        raw = path.read_bytes()
        if len(raw) != count * 4 or sha(raw) != expected:
            raise ValueError("quality_heldout_source")
        values = np.frombuffer(raw, dtype="<f4")
        sources.append((identity, values))
        items.append(dict(task="presence", values=[values], expected="yes", source=identity, source_sha256=expected, transform=None))
        items.append(dict(task="language", values=[values], expected="english" if identity.startswith("en_") else "vietnamese", source=identity, source_sha256=expected, transform=None))
    for language_index, (identity, values) in enumerate(sources):
        damaged = [np.clip(values * 40, -1, 1).astype("<f4"), values.copy()]
        damaged[1][len(values) // 4:3 * len(values) // 4] = 0
        for defect_index, altered in enumerate(damaged):
            if np.array_equal(values, altered):
                raise ValueError("quality_ineffective_control")
            first = (language_index + defect_index) % 2 == 0
            items.append(dict(task="comparison", values=[altered, values] if first else [values, altered], expected="first" if first else "second", source=identity, source_sha256=SOURCES[identity][1], transform="clip(40*x,-1,1)" if defect_index == 0 else "middle_half_exact_zeros", damaged_position=1 if first else 2))
        items.append(dict(task="comparison", values=[values, values], expected="equal", source=identity, source_sha256=SOURCES[identity][1], transform="identical_pair"))
    items.extend([
        dict(task="presence", values=[np.zeros(64000, dtype="<f4")], expected="no", source="authored_exact_zeros", transform=None),
        dict(task="presence", values=[np.random.default_rng(104).normal(0, 0.05, 64000).astype("<f4")], expected="no", source="authored_Gaussian_noise", seed=104, standard_deviation=0.05, transform=None),
    ])
    publish_packet(Path(root) / "quality-104-controls", "qualify-quality", items, save_bytes, publish)


def qualification_checks(request, events, mapping):
    """Require every predeclared factual, language, corruption and tie answer without tuning labels or treating control success as naturalness truth."""
    if request.get("mode") != "qualify-quality" or not audit_events(request, events) or type(mapping) is not list or len(mapping) != 12:
        return False
    rows = [event for event in events if event.get("event") == "quality"]
    if Counter(item.get("expected") for item in mapping if item.get("task") == "comparison") != Counter(first=2, second=2, equal=2):
        return False
    passed = all(row["id"] == expected.get("id") and row["task"] == expected.get("task") and row["answer"] == expected.get("expected") for row, expected in zip(rows, mapping, strict=True))
    logger.info("quality_control_gate passed=%s cases=12 human_naturalness_certified=False", passed)
    return passed


def require_qualification(root, project):
    """Recompute the exact first qualification and source/runtime/packet binding before accessing any common candidate audio."""
    root, project = Path(root), Path(project)
    run = root / "quality-104-controls-first"
    frozen_raw = (run / "freeze.json").read_bytes()
    frozen = json.loads(frozen_raw)
    result = json.loads((run / "result.json").read_text())
    packet = root / "quality-104-controls"
    parent_raw = (packet / "parent-only.json").read_bytes()
    request_raw = (packet / "request.json").read_bytes()
    if result.get("freeze_sha256") != sha(frozen_raw) or result.get("observation_complete") is not True or result.get("quality_controls_passed") is not True or result.get("process", {}).get("exit_code") != 0 or result["process"].get("timed_out") is not False:
        raise ValueError("quality_first_qualification_gate")
    if frozen.get("parent_metadata_sha256") != sha(parent_raw) or frozen["request"] != json.loads(request_raw) or frozen.get("packet_request_sha256") != sha(request_raw):
        raise ValueError("quality_parent_binding")
    if not qualification_checks(frozen["request"], result["events"], json.loads(parent_raw)["mapping"]):
        raise ValueError("quality_qualification_recompute")
    if any(sha((project / name).read_bytes()) != value for name, value in frozen["source_sha256"].items()) or frozen["runtime_inventory_sha256"] != sha((root / "runtime-integrity.json").read_bytes()):
        raise ValueError("quality_protocol_changed")
    for row in frozen["request"]["cases"]:
        for signal in row["signals"]:
            raw = (packet / "inputs" / (signal["id"] + ".f32")).read_bytes()
            if sha(raw) != signal["sha256"] or len(raw) != signal["sample_count"] * 4:
                raise ValueError("quality_qualification_signal_changed")
    logger.info("quality_first_qualification_verified common_review_gate=True")


def prepare_review(root, project, save_bytes, publish):
    """Copy all twenty-four original complete diagnostic signals into two fixed blind tasks each after the new strict control gate."""
    require_execution_permission("prepare-quality-review")
    require_qualification(root, project)
    import numpy as np

    original = Path(project) / "data/backups/d70-common-audio-diagnostics-first"
    rows = [row for row in json.loads((original / "result.json").read_text())["events"] if row["event"] == "transformed"]
    if len(rows) != 24 or len({row["id"] for row in rows}) != 24:
        raise ValueError("quality_original_coverage")
    items = []
    for row in rows:
        raw = (original / "generated" / (row["id"] + ".f32")).read_bytes()
        if sha(raw) != row["asr"]["waveform_sha256"] or len(raw) != row["asr"]["sample_count"] * 4:
            raise ValueError("quality_original_signal_hash")
        for task in ["naturalness", "notes"]:
            items.append(dict(task=task, values=[np.frombuffer(raw, dtype="<f4")], original_id=row["id"], original_diagnostic=row["asr"]))
    publish_packet(Path(root) / "quality-104-review", "review-quality", items, save_bytes, publish)
