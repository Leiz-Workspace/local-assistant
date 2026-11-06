"""Prepare and gate a specialist public audio-review campaign without downloading weights, replacing project models or waiving D70 acceptance."""

import argparse
import hashlib
import json
import logging
import math
import os
import re
import resource
import secrets
import time
import urllib.request
from pathlib import Path, PurePosixPath

import numpy as np

from scripts.asr_evaluation_corpus import save_bytes
from scripts.asr_evaluation_runner import core_snapshot
from scripts.tts_local_review import publish_json, require_headroom
from scripts.tts_public_audio_review import (
    NoRedirect,
    ReviewError,
    load_upload,
    parse_events,
    pcm_wave,
    wall_limit,
)

logger = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "data/backups/d70-speechjudge-specialist"
ORIGIN = "https://den4ikai-speechjudge-grm.hf.space"
SPACE_REVISION = "e16fd85d230ac043091476eb78faa6c2e24c5c66"
MODEL_REVISION = "8d4ce4ddf54c5e7ac0b457fc7b561cec1bd784c1"
EXECUTION_ALLOWED = False


def require_scope():
    """Reject retained clients and all external media requests until this distinct evaluator recipient is approved."""
    if not EXECUTION_ALLOWED:
        logger.warning("speechjudge_execution_blocked reason=campaign_not_approved")
        raise ReviewError("specialist_campaign_not_approved")


def sha(raw):
    """Bind complete metadata, source, signal or response bytes without exposing their contents in logs."""
    return hashlib.sha256(raw).hexdigest()


def native_text_bf16_bound(config):
    """Calculate a native Qwen2.5 text-parameter lower bound from architecture metadata, excluding audio, vision, activations and runtime RAM."""
    keys = ["hidden_size", "intermediate_size", "vocab_size", "num_hidden_layers", "num_attention_heads", "num_key_value_heads"]
    if type(config) is not dict or config.get("model_type") != "qwen2_5_omni_text" or any(type(config.get(key)) is not int or not 1 <= config[key] <= 1000000 for key in keys):
        raise ReviewError("specialist_architecture_metadata")
    h, intermediate, vocab, layers, heads, kv_heads = [config[key] for key in keys]
    if h % heads or kv_heads > heads or heads % kv_heads or type(config.get("tie_word_embeddings")) is not bool:
        raise ReviewError("specialist_architecture_relationship")
    kv = kv_heads * (h // heads)
    # Native Qwen attention has biased Q/K/V and an unbiased output; each decoder has three MLP matrices and two RMS norms.
    per_layer = 2 * h * h + 2 * h * kv + h + 2 * kv + 3 * h * intermediate + 2 * h
    parameters = vocab * h + layers * per_layer + h + (0 if config["tie_word_embeddings"] else vocab * h)
    result = dict(text_parameters=parameters, BF16_parameter_bytes=parameters * 2, measured_RAM=False, original_weights_loaded=False)
    logger.info("speechjudge_native_text_lower_bound parameters=%d BF16_bytes=%d actual_RAM_measured=False", parameters, parameters * 2)
    return result


def inspect_interface():
    """Read only fixed public metadata and refuse runtime, revision or interface drift before any media is transmitted."""
    urls = {
        "space": "https://huggingface.co/api/spaces/Den4ikAI/SpeechJudge-GRM",
        "config": ORIGIN + "/config",
        "info": ORIGIN + "/gradio_api/info",
    }
    opener = urllib.request.build_opener(NoRedirect())
    values, hashes = {}, {}
    for name, url in urls.items():
        with opener.open(urllib.request.Request(url, headers={"User-Agent": "D70-specialist-interface/1"}), timeout=15) as response:
            raw = response.read(1024**2 + 1)
        if len(raw) > 1024**2:
            raise ReviewError("specialist_metadata_bound")
        values[name], hashes[name] = json.loads(raw), sha(raw)
    space, config, info = values["space"], values["config"], values["info"]
    if space.get("sha") != SPACE_REVISION or space.get("runtime", {}).get("sha") != SPACE_REVISION or space.get("runtime", {}).get("stage") != "RUNNING" or space.get("host") != ORIGIN or config.get("version") != "6.26.0" or config.get("api_prefix") != "/gradio_api":
        raise ReviewError("specialist_interface_drift")
    endpoint = info.get("named_endpoints", {}).get("/gradio_handler", {})
    if [row.get("parameter_name") for row in endpoint.get("parameters", [])] != ["target_text", "audio_path_a", "audio_path_b", "num_generations"] or len(endpoint.get("returns", [])) != 2 or endpoint.get("api_visibility") != "public":
        raise ReviewError("specialist_endpoint_schema")
    logger.info("speechjudge_interface_reverified revision=%s no_media_transmitted=True", SPACE_REVISION)
    return dict(description="Public metadata identity/interface check only; not an attestation of remote weights, decoder, capacity or data deletion.", space_revision=SPACE_REVISION, metadata_sha256=hashes)


def validate_packet(packet):
    """Require exact opaque pairs, full bounded WAV receipts, neutral transcripts and fixed campaign coverage without caller-selected endpoints."""
    if type(packet) is not dict or set(packet) != {"description", "kind", "cases"} or packet.get("kind") not in {"controls", "review"}:
        raise ReviewError("specialist_packet_scope")
    if type(packet["cases"]) is not list or len(packet["cases"]) != (18 if packet["kind"] == "controls" else 24):
        raise ReviewError("specialist_packet_coverage")
    seen = set()
    for row in packet["cases"]:
        if type(row) is not dict or set(row) != {"id", "text", "signals"} or type(row["id"]) is not str or re.fullmatch(r"pair-[0-9]{2}", row["id"]) is None or row["id"] in seen:
            raise ReviewError("specialist_pair_identity")
        if type(row["text"]) is not str or not row["text"].strip() or len(row["text"].encode()) > 160 or any(ord(char) < 32 for char in row["text"]):
            raise ReviewError("specialist_reference_text")
        if type(row["signals"]) is not list or len(row["signals"]) != 2:
            raise ReviewError("specialist_signal_coverage")
        for index, signal in enumerate(row["signals"]):
            identity = row["id"] + "-" + "ab"[index]
            if type(signal) is not dict or set(signal) != {"id", "filename", "upload_sha256", "source_float32_sha256", "sample_rate", "sample_count"} or signal["id"] != identity or signal["filename"] != identity + ".wav":
                raise ReviewError("specialist_signal_fields")
            if any(type(signal[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", signal[key]) is None for key in ["upload_sha256", "source_float32_sha256"]):
                raise ReviewError("specialist_signal_hash")
            if type(signal["sample_rate"]) is not int or signal["sample_rate"] not in {16000, 22050, 24000} or type(signal["sample_count"]) is not int or not 1600 <= signal["sample_count"] <= 20 * signal["sample_rate"]:
                raise ReviewError("specialist_signal_bounds")
        seen.add(row["id"])
    logger.info("speechjudge_packet_verified kind=%s pairs=%d", packet["kind"], len(seen))


def freeze_packet(directory, kind, items):
    """Publish one exclusive shuffled blind PCM16 packet and keep source identities and expected preferences parent-side."""
    directory.mkdir(mode=0o700, exist_ok=False)
    inputs = directory / "inputs"
    inputs.mkdir(mode=0o700)
    cases, mapping = [], []
    for number, index in enumerate(np.random.default_rng(105).permutation(len(items)), start=1):
        item = items[int(index)]
        identity, signals = f"pair-{number:02d}", []
        for position, (values, rate) in enumerate(item["signals"]):
            signal_id = identity + "-" + "ab"[position]
            raw = pcm_wave(values, rate)
            save_bytes(inputs / (signal_id + ".wav"), raw)
            signals.append(dict(id=signal_id, filename=signal_id + ".wav", upload_sha256=sha(raw), source_float32_sha256=sha(values.tobytes()), sample_rate=rate, sample_count=len(values)))
        cases.append(dict(id=identity, text=item["text"], signals=signals))
        mapping.append(dict(id=identity, **{key: value for key, value in item.items() if key not in {"signals", "text"}}))
    packet = dict(description="Neutral authored test speech only; opaque pair identities; no user recordings, candidate names or expected labels transmitted. Full timeline PCM16 conversion only.", kind=kind, cases=cases)
    validate_packet(packet)
    publish_json(directory / "packet.json", packet)
    publish_json(directory / "parent-only.json", dict(description="Private provenance and preregistered preferences; never transmitted to the reviewer.", order_seed=105, cases=mapping))
    logger.info("speechjudge_packet_frozen kind=%s pairs=%d", kind, len(cases))


def prepare_controls(root=ROOT, project=PROJECT):
    """Preregister eighteen source-bound distortion/gap/no-speech/reversed/tie comparisons from two separate existing neutral TTS smokes."""
    require_headroom()
    items = []
    for language, name in [("en", "d70-qwen-smoke-first"), ("vi", "d70-piper-vi-smoke-first")]:
        directory = Path(project) / "data/backups" / name
        result = json.loads((directory / "result.json").read_text())
        frozen = json.loads((directory / "freeze.json").read_text())
        observed = next(row for row in result["events"] if row.get("status") == "ok")
        source = observed["audio"]
        text = next(row["text"] for row in frozen["request"]["cases"] if row["id"] == observed["id"])
        filename = source["raw_filename"]
        if type(filename) is not str or Path(filename).name != filename:
            raise ReviewError("specialist_smoke_filename")
        raw = (directory / "generated" / filename).read_bytes()
        if sha(raw) != source["waveform_sha256"] or len(raw) != source["sample_count"] * 4:
            raise ReviewError("specialist_smoke_hash")
        values, rate = np.frombuffer(raw, dtype="<f4"), source["sample_rate"]
        gap = values.copy()
        gap[len(values) // 4:3 * len(values) // 4] = 0
        damaged = [np.clip(values * 40, -1, 1).astype("<f4"), gap, np.zeros(len(values), dtype="<f4"), np.random.default_rng(105).normal(0, 0.05, len(values)).astype("<f4")]
        for transform, altered in zip(["hard_clipping_40x", "middle_half_zero", "exact_zeros", "Gaussian_noise_seed105_std0.05"], damaged, strict=True):
            if np.array_equal(values, altered):
                raise ReviewError("specialist_ineffective_control")
            for reverse in [False, True]:
                signals = [(values, rate), (altered, rate)]
                items.append(dict(text=text, signals=signals[::-1] if reverse else signals, expected="b" if reverse else "a", language=language, source_waveform_sha256=sha(raw), transform=transform, reversed=reverse))
        items.append(dict(text=text, signals=[(values, rate), (values, rate)], expected="tie", language=language, source_waveform_sha256=sha(raw), transform="identical_pair", reversed=False))
    root = Path(root)
    if root.is_symlink():
        raise ReviewError("specialist_owned_root_symlink")
    root.mkdir(mode=0o700, exist_ok=True)
    freeze_packet(root / "controls", "controls", items)
    directory = Path(root) / "controls"
    publish_json(Path(root) / "controls-prepared.json", dict(description="First local-only control preparation; complete38filehashes before external-recipient consent, no upload or inference.", sha256={str(path.relative_to(root)): sha(path.read_bytes()) for path in sorted(directory.rglob("*")) if path.is_file()}, external_execution_allowed=EXECUTION_ALLOWED, media_uploaded=False))


def verify_prepared_controls(root):
    """Reject any change to the first locally prepared control packet before constructing a provider client or trusting its subsequent qualification."""
    root = Path(root)
    packet = json.loads((root / "controls/packet.json").read_text())
    validate_packet(packet)
    frozen = json.loads((root / "controls-prepared.json").read_text())["sha256"]
    required = {"controls/packet.json", "controls/parent-only.json"} | {"controls/inputs/" + signal["filename"] for row in packet["cases"] for signal in row["signals"]}
    if type(frozen) is not dict or set(frozen) != required or any(sha((root / name).read_bytes()) != value for name, value in frozen.items()):
        raise ReviewError("specialist_prepared_control_changed")
    logger.info("speechjudge_local_first_packet_verified files=%d", len(frozen))


def parse_comparison(events):
    """Cross-check one first raw score pair with the frontend summary, rejecting repairs, averaging, errors and contradictory winners."""
    complete = [row for row in events if row.get("event") == "complete"]
    if len(complete) != 1 or any(row.get("event") == "error" for row in events):
        raise ReviewError("specialist_incomplete_event")
    data = complete[0].get("data")
    if type(data) is not list or len(data) != 2 or any(type(value) is not str or len(value.encode()) > 60000 for value in data):
        raise ReviewError("specialist_output_shape")
    summary, raw = data
    scores = re.findall(r"^Score A: ([0-9]+(?:\.[0-9]+)?), Score B: ([0-9]+(?:\.[0-9]+)?)$", raw, re.MULTILINE)
    if len(scores) != 1 or len(re.findall(r"Generation 1/1", raw)) != 1 or "[Error]" in raw or "Reasoning:\n" not in raw:
        raise ReviewError("specialist_first_generation")
    a, b = map(float, scores[0])
    if any(not math.isfinite(value) or not 1 <= value <= 10 for value in [a, b]):
        raise ReviewError("specialist_score_bounds")
    conclusions = re.findall(r"Output A: (\d+(?:\.\d+)?).*?Output B: (\d+(?:\.\d+)?)", raw.split("Reasoning:\n", 1)[1].replace("**", ""), re.DOTALL)
    if len(conclusions) != 1 or tuple(map(float, conclusions[0])) != (a, b):
        raise ReviewError("specialist_raw_rating_contradiction")
    winner = "a" if a > b else "b" if b > a else "tie"
    label = {"a": "Audio A Wins", "b": "Audio B Wins", "tie": "Tie"}[winner]
    lines = summary.splitlines()
    if len(lines) != 3 or not lines[0].endswith("Result: " + label) or lines[1:] != [f"Audio A Avg Score: {a:.2f}", f"Audio B Avg Score: {b:.2f}"] or not raw.split("Reasoning:\n", 1)[1].strip():
        raise ReviewError("specialist_summary_contradiction")
    logger.info("speechjudge_first_comparison_parsed winner=%s human_MOS=False", winner)
    return dict(winner=winner, score_a=a, score_b=b, raw_summary=summary, raw_log=raw)


class SpecialistDemo:
    """Use one fixed community demo's ordinary anonymous public interface without credentials, arbitrary origins, retries or local model loading."""

    def __init__(self, output):
        """Keep private first receipts and partial SSE evidence after enforcing distinct external-review approval."""
        require_scope()
        self.output = Path(output)
        self.opener = urllib.request.build_opener(NoRedirect())
        self.raw_stream = bytearray()

    def open(self, method, path, data=None, content_type=None):
        """Restrict all transmissions to the approved HTTPS origin and exact upload/simple-call/event paths."""
        require_scope()
        valid = method == "POST" and path in {"/gradio_api/upload", "/gradio_api/call/gradio_handler"} or method == "GET" and re.fullmatch(r"/gradio_api/call/gradio_handler/[a-f0-9]{32}", path) is not None
        if not valid:
            raise ReviewError("specialist_endpoint_scope")
        headers = {"User-Agent": "LocalAssistant-D70-SpecialistQualification/1"}
        if content_type:
            headers["Content-Type"] = content_type
        logger.info("speechjudge_request method=%s operation=%s", method, "upload" if path.endswith("upload") else "prediction_event")
        return self.opener.open(urllib.request.Request(ORIGIN + path, data=data, headers=headers, method=method), timeout=20)

    def json_request(self, path, raw, content_type):
        """Read one finite receipt while rejecting response-selected endpoint authority."""
        with self.open("POST", path, raw, content_type) as response:
            body = response.read(65537)
        if len(body) > 65536:
            raise ReviewError("specialist_receipt_bound")
        return json.loads(body)

    def upload(self, raw, position):
        """Upload a full validated WAV using only a generated opaque filename and validate the returned temporary leaf."""
        require_scope()
        if type(raw) is not bytes or not 44 <= len(raw) <= 1024**2 or position not in {"a", "b"}:
            raise ReviewError("specialist_upload_bounds")
        boundary, filename = "D70" + secrets.token_hex(16), "clip-" + position + ".wav"
        body = f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{filename}"\r\nContent-Type: audio/wav\r\n\r\n'.encode() + raw + f"\r\n--{boundary}--\r\n".encode()
        receipt = self.json_request("/gradio_api/upload", body, "multipart/form-data; boundary=" + boundary)
        if type(receipt) is not list or len(receipt) != 1 or type(receipt[0]) is not str or not receipt[0].startswith("/tmp/gradio/") or len(receipt[0]) > 512 or ".." in PurePosixPath(receipt[0]).parts or "\x00" in receipt[0] or not receipt[0].endswith("/" + filename):
            raise ReviewError("specialist_upload_receipt")
        return dict(path=receipt[0], orig_name=filename, mime_type="audio/wav", meta={"_type": "gradio.FileData"})

    def compare(self, row, inputs):
        """Retain a single-generation audio-conditioned response with bounded transport and no outcome-dependent retries."""
        require_scope()
        self.raw_stream.clear()
        values = [load_upload(signal, inputs) for signal in row["signals"]]
        with wall_limit(180):
            a, b = [self.upload(raw, position) for raw, position in zip(values, "ab", strict=True)]
            payload = dict(data=[row["text"], a, b, 1])
            receipt = self.json_request("/gradio_api/call/gradio_handler", json.dumps(payload).encode(), "application/json")
            if type(receipt) is not dict or type(receipt.get("event_id")) is not str or re.fullmatch(r"[0-9a-f]{32}", receipt["event_id"]) is None:
                raise ReviewError("specialist_event_receipt")
            publish_json(self.output / (row["id"] + ".receipt.json"), dict(description="First public simple-call receipt; no claim of remote cancellation/deletion.", event_id=receipt["event_id"], origin=ORIGIN))
            with self.open("GET", "/gradio_api/call/gradio_handler/" + receipt["event_id"]) as response:
                while line := response.readline(65537):
                    self.raw_stream.extend(line)
                    if len(line) > 65536 or len(self.raw_stream) > 2 * 1024**2:
                        raise ReviewError("specialist_event_bound")
                    if not line.strip() and any(event["event"] in {"complete", "error"} for event in parse_events(bytes(self.raw_stream))):
                        break
        return parse_comparison(parse_events(bytes(self.raw_stream)))


def require_qualification(root=ROOT, project=PROJECT):
    """Recompute the exact first complete eighteen-control outcome and frozen protocol/packet bindings before common review."""
    root, project = Path(root), Path(project)
    verify_prepared_controls(root)
    result = json.loads((root / "controls-first/result.json").read_text())
    frozen = json.loads((root / "controls-first/freeze.json").read_text())
    packet = json.loads((root / "controls/packet.json").read_text())
    mapping = json.loads((root / "controls/parent-only.json").read_text())["cases"]
    validate_packet(packet)
    if result.get("controls_passed") is not True or result.get("error_code") is not None or result.get("freeze_sha256") != sha((root / "controls-first/freeze.json").read_bytes()) or frozen["packet"] != packet or len(result.get("observations", [])) != 18:
        raise ReviewError("specialist_qualification_gate")
    required_artifacts = {"freeze.json", "interface.json"} | {row["id"] + suffix for row in packet["cases"] for suffix in [".receipt.json", ".json", ".sse"]}
    artifact_hashes = result.get("first_artifact_sha256")
    if type(artifact_hashes) is not dict or set(artifact_hashes) != required_artifacts:
        raise ReviewError("specialist_first_artifact_coverage")
    if any(sha((root / "controls-first" / name).read_bytes()) != value for name, value in artifact_hashes.items()):
        raise ReviewError("specialist_first_artifact_changed")
    seen_event_ids = set()
    for observation, expected, request in zip(result["observations"], mapping, packet["cases"], strict=True):
        identity = request["id"]
        recorded = json.loads((root / "controls-first" / (identity + ".json")).read_text())
        raw = (root / "controls-first" / (identity + ".sse")).read_bytes()
        receipt = json.loads((root / "controls-first" / (identity + ".receipt.json")).read_text())
        event_id = receipt.get("event_id")
        if receipt.get("origin") != ORIGIN or type(event_id) is not str or re.fullmatch(r"[a-f0-9]{32}", event_id) is None or event_id in seen_event_ids:
            raise ReviewError("specialist_first_receipt_identity")
        seen_event_ids.add(event_id)
        if observation != recorded or observation["events"] != parse_events(raw) or observation["judgement"] != parse_comparison(observation["events"]):
            raise ReviewError("specialist_first_observation_contradiction")
        if observation["id"] != expected["id"] or observation["id"] != identity or observation["signals"] != request["signals"] or observation["judgement"]["winner"] != expected["expected"]:
            raise ReviewError("specialist_qualification_recompute")
    for name, expected in frozen["source_sha256"].items():
        if sha((project / name).read_bytes()) != expected:
            raise ReviewError("specialist_source_changed")
    for name, expected in frozen["packet_sha256"].items():
        if sha((root / name).read_bytes()) != expected:
            raise ReviewError("specialist_packet_changed")
    logger.info("speechjudge_first_qualification_verified controls=18")


def order_consistency(observations, mapping):
    """Report whether both frozen orientations prefer the same original output, retaining disagreements rather than repairing or averaging scores."""
    groups = {}
    for observation, source in zip(observations, mapping, strict=True):
        if observation["id"] != source["id"]:
            raise ReviewError("specialist_review_mapping")
        identities = [row["original_id"] for row in source["originals"]]
        if len(identities) != 2 or identities[0] == identities[1]:
            raise ReviewError("specialist_review_originals")
        winner = observation["judgement"]["winner"]
        preferred = None if winner == "tie" else identities[0 if winner == "a" else 1]
        groups.setdefault(tuple(sorted(identities)), []).append(preferred)
    if len(groups) != 12 or any(len(values) != 2 for values in groups.values()):
        raise ReviewError("specialist_review_order_coverage")
    inconsistent = [list(identities) for identities, values in groups.items() if values[0] != values[1]]
    logger.info("speechjudge_order_consistency checked_pairs=12 inconsistent=%d", len(inconsistent))
    return dict(checked_original_pairs=12, consistent_original_pairs=12 - len(inconsistent), inconsistent_original_pairs=inconsistent, scores_repaired_or_averaged=False)


def prepare_review(root=ROOT, project=PROJECT):
    """Pair all24 retained outputs by identical authored text and freeze both orientations after the new specialist control gate."""
    require_qualification(root, project)
    require_headroom()
    project = Path(project)
    directory = project / "data/backups/d70-common-audio-diagnostics-first"
    sources = {row["id"]: row for row in json.loads((directory / "result.json").read_text())["events"] if row.get("event") == "transformed"}
    originals = json.loads((project / "data/backups/d70-tts-listening-review/review.pending.json").read_text())["items"]
    if len(sources) != 24 or len(originals) != 24 or {row["id"] for row in originals} != set(sources):
        raise ReviewError("specialist_original_coverage")
    groups = {}
    for item in originals:
        groups.setdefault((item["language"], item["authored_text"]), []).append(item)
    if len(groups) != 12 or any(len(rows) != 2 or len({row["candidate"] for row in rows}) != 2 for rows in groups.values()):
        raise ReviewError("specialist_original_pairing")
    pairs = []
    for (language, text), rows in sorted(groups.items()):
        signals, provenance = [], []
        for row in rows:
            metadata = sources[row["id"]]["asr"]
            raw = (directory / "generated" / (row["id"] + ".f32")).read_bytes()
            if sha(raw) != metadata["waveform_sha256"] or len(raw) != metadata["sample_count"] * 4 or metadata["source_waveform_sha256"] != row["native_waveform_sha256"]:
                raise ReviewError("specialist_original_hash")
            signals.append((np.frombuffer(raw, dtype="<f4"), 16000))
            provenance.append(dict(original_id=row["id"], original_diagnostic=metadata))
        for reverse in [False, True]:
            pairs.append(dict(text=text, signals=signals[::-1] if reverse else signals, originals=provenance[::-1] if reverse else provenance, language=language, reversed=reverse))
    freeze_packet(Path(root) / "review", "review", pairs)


def evaluate(kind, root=ROOT, project=PROJECT):
    """Run one exclusive finite campaign stage, stop at the first failed control/transport, and preserve partial raw evidence and CORE recovery."""
    global EXECUTION_ALLOWED
    require_scope()
    root, project = Path(root), Path(project)
    if kind not in {"controls", "review"}:
        raise ReviewError("specialist_stage")
    if kind == "review":
        require_qualification(root, project)
    else:
        verify_prepared_controls(root)
    require_headroom()
    directory, output = root / kind, root / (kind + "-first")
    packet = json.loads((directory / "packet.json").read_text())
    validate_packet(packet)
    if packet["kind"] != kind:
        raise ReviewError("specialist_stage_packet")
    mapping = json.loads((directory / "parent-only.json").read_text())["cases"]
    if len(mapping) != len(packet["cases"]) or [row["id"] for row in mapping] != [row["id"] for row in packet["cases"]]:
        raise ReviewError("specialist_parent_coverage")
    for row in packet["cases"]:
        for signal in row["signals"]:
            load_upload(signal, directory / "inputs")
    output.mkdir(mode=0o700, exist_ok=False)
    source_names = ["scripts/tts_speechjudge_review.py", "tests/test_tts_speechjudge_review.py", "scripts/tts_public_audio_review.py", "docs/ADR/105-proposed-specialist-public-auditory-review.md"]
    frozen = dict(description="Source-bound first specialist stage; public model runtime/seed/dtype/provenance cannot be independently attested.", origin=ORIGIN, inspected_space_revision=SPACE_REVISION, intended_model_revision=MODEL_REVISION, packet=packet, source_sha256={name: sha((project / name).read_bytes()) for name in source_names}, packet_sha256={str(path.relative_to(root)): sha(path.read_bytes()) for path in sorted(directory.rglob("*")) if path.is_file()}, maximum_generations_per_call=1, maximum_call_wall_seconds=180, total_stage_wall_seconds=1800)
    publish_json(output / "freeze.json", frozen)
    before, observations, error_code = core_snapshot(), [], None
    client = SpecialistDemo(output)
    started = time.monotonic()
    try:
        publish_json(output / "interface.json", inspect_interface())
        for row, expected in zip(packet["cases"], mapping, strict=True):
            if time.monotonic() - started > 1620:
                raise ReviewError("specialist_stage_time_budget")
            try:
                judgement = client.compare(row, directory / "inputs")
            finally:
                save_bytes(output / (row["id"] + ".sse"), bytes(client.raw_stream))
            events = parse_events(bytes(client.raw_stream))
            observations.append(dict(id=row["id"], signals=row["signals"], events=events, judgement=judgement))
            publish_json(output / (row["id"] + ".json"), observations[-1])
            if kind == "controls" and judgement["winner"] != expected.get("expected"):
                raise ReviewError("specialist_control_mismatch")
    except (ReviewError, OSError, ValueError) as error:
        error_code = error.code if isinstance(error, ReviewError) else type(error).__name__
        logger.warning("speechjudge_stage_stopped kind=%s retained=%d code=%s", kind, len(observations), error_code)
    after = core_snapshot()
    if any(before[key] != after[key] for key in ["pid", "start_ticks", "command_sha256"]):
        error_code = "specialist_CORE_identity_changed"
    if any(sha((project / name).read_bytes()) != value for name, value in frozen["source_sha256"].items()) or any(sha((root / name).read_bytes()) != value for name, value in frozen["packet_sha256"].items()):
        error_code = "specialist_frozen_bytes_changed"
    complete = error_code is None and len(observations) == len(packet["cases"])
    result = dict(description="First source-bound external AI comparisons, not human MOS, production model selection or automatic D70 acceptance.", stage=kind, observations=observations, error_code=error_code, controls_passed=complete if kind == "controls" else None, review_complete=complete if kind == "review" else None, core_before=before, core_after=after, freeze_sha256=sha((output / "freeze.json").read_bytes()), remote_cancellation_deletion_verified=False, D70_complete=False, D71_started=False)
    if kind == "review" and complete:
        result["order_consistency"] = order_consistency(observations, mapping)
    result["first_artifact_sha256"] = {path.name: sha(path.read_bytes()) for path in sorted(output.iterdir()) if path.is_file()}
    publish_json(output / "result.json", result)
    if not complete or kind == "review":
        EXECUTION_ALLOWED = False
    logger.info("speechjudge_stage_retired kind=%s complete=%s observations=%d", kind, complete, len(observations))
    return complete


def main():
    """Execute the separately approved eighteen-control and conditional24comparison campaign as one bounded sequence without further permission between stages."""
    global EXECUTION_ALLOWED
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-controls", action="store_true", help="Prepare local control copies only; never upload audio or invoke the provider.")
    args = parser.parse_args()
    if not args.prepare_controls:
        require_scope()
    resource.setrlimit(resource.RLIMIT_AS, (12 * 1024**3, 12 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (1200, 1201))
    os.sched_setaffinity(0, {0, 1})
    if args.prepare_controls:
        prepare_controls()
        return
    try:
        if not (ROOT / "controls").exists():
            prepare_controls()
        if evaluate("controls"):
            prepare_review()
            evaluate("review")
    finally:
        EXECUTION_ALLOWED = False


if __name__ == "__main__":
    main()
