"""Validate and observe fixed blind auditory tasks without parent-only source identities, transformations or expected answers."""

import hashlib
import logging
import re
import time
from collections import Counter

logger = logging.getLogger(__name__)
TASKS = {
    "presence": ("Does this audio contain any intelligible human speech? Answer exactly yes, no, or uncertain.", 16, {"yes", "no", "uncertain"}),
    "language": ("Which language is spoken in this audio? Answer exactly english, vietnamese, other, or uncertain.", 16, {"english", "vietnamese", "other", "uncertain"}),
    "comparison": ("Which audio has more audible distortion or unnatural interruptions? Answer exactly first, second, equal, or uncertain.", 16, {"first", "second", "equal", "uncertain"}),
    "naturalness": ("Does the actual speech sound natural in pronunciation, rhythm, pauses and continuity? Answer exactly natural, unnatural, uncertain, or not_applicable. Use uncertain when unable to assess, and not_applicable only for no speech.", 16, {"natural", "unnatural", "uncertain", "not_applicable"}),
    "notes": ("Describe only audible pronunciation, rhythm, pauses, continuity or distortion in at most forty English words. State uncertainty where necessary. Do not invent a transcript, score or human listening claim.", 96, None),
}
COUNTS = {
    "qualify-quality": Counter(presence=4, language=2, comparison=6),
    "review-quality": Counter(naturalness=24, notes=24),
}


def validate_request(request):
    """Reject extra metadata, arbitrary paths, prompt overrides and incomplete task or signal coverage before input access."""
    if type(request) is not dict or set(request) != {"mode", "cases"} or type(request["mode"]) is not str or request["mode"] not in COUNTS:
        raise ValueError("quality_request")
    rows = request["cases"]
    if type(rows) is not list or len(rows) != sum(COUNTS[request["mode"]].values()):
        raise ValueError("quality_coverage")
    seen, tasks = set(), Counter()
    for row in rows:
        if type(row) is not dict or set(row) != {"id", "task", "signals"}:
            raise ValueError("quality_case_fields")
        identity, task, signals = row["id"], row["task"], row["signals"]
        if type(identity) is not str or re.fullmatch(r"clip-[0-9]{2}", identity) is None or identity in seen:
            raise ValueError("quality_identity")
        if type(task) is not str or task not in COUNTS[request["mode"]] or type(signals) is not list or len(signals) != (2 if task == "comparison" else 1):
            raise ValueError("quality_task")
        for index, signal in enumerate(signals):
            if type(signal) is not dict or set(signal) != {"id", "sample_count", "sha256"} or signal["id"] != identity + "-" + "ab"[index]:
                raise ValueError("quality_signal_fields")
            if type(signal["sample_count"]) is not int or not 1600 <= signal["sample_count"] <= 320000:
                raise ValueError("quality_signal_count")
            if type(signal["sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", signal["sha256"]) is None:
                raise ValueError("quality_signal_hash")
        if task == "comparison" and signals[0]["sample_count"] != signals[1]["sample_count"]:
            raise ValueError("quality_pair_duration")
        seen.add(identity)
        tasks[task] += 1
    if tasks != COUNTS[request["mode"]]:
        raise ValueError("quality_task_coverage")
    logger.info("quality_request_verified mode=%s cases=%d", request["mode"], len(rows))


def parse_answer(task, raw):
    """Accept exact declared labels or bounded notes without repairing model prose into categorical answers."""
    if task not in TASKS or type(raw) is not str:
        raise ValueError("quality_answer")
    text = raw.strip()
    choices = TASKS[task][2]
    if choices is not None and text not in choices:
        raise ValueError("quality_answer_label")
    if choices is None and (not text or len(text) > 2048 or len(text.split()) > 40 or any(ord(character) < 32 and character not in "\n\t" for character in text)):
        raise ValueError("quality_answer_notes")
    return text


def observe(runtime, row, waveform, emit, system):
    """Record one source-bound native multimodal response with per-signal conditioning and genuine EOS, using an already authorized runtime."""
    started = time.perf_counter()
    values = [waveform(signal) for signal in row["signals"]]
    question, maximum, _ = TASKS[row["task"]]
    content = []
    for index, signal in enumerate(row["signals"]):
        if len(values) == 2:
            content.append(dict(type="text", text=("First audio:" if index == 0 else "Second audio:")))
        content.append(dict(type="audio", audio="/samples/" + signal["id"] + ".f32"))
    content.append(dict(type="text", text=question))
    conversation = [dict(role="system", content=[dict(type="text", text=system)]), dict(role="user", content=content)]
    text = runtime.processor.apply_chat_template(conversation, add_generation_prompt=True, tokenize=False)
    inputs = runtime.processor(text=text, audio=values, sampling_rate=16000, return_tensors="pt", padding=True)
    features, masks = inputs["input_features"], inputs["feature_attention_mask"]
    frames = [int(value) for value in masks.sum(dim=1).tolist()]
    tokens = int((inputs["input_ids"] == runtime.model.config.audio_token_index).sum())
    if features.shape[0] != len(values) or len(frames) != len(values) or any(value <= 0 for value in frames) or tokens <= 0:
        raise ValueError("quality_conditioning_missing")
    feature_hash = hashlib.sha256(features.numpy().tobytes()).hexdigest()
    inputs = inputs.to("cpu", dtype=runtime.torch.bfloat16)
    with runtime.torch.inference_mode():
        result = runtime.model.generate(**inputs, **runtime.boundaries, do_sample=False, num_beams=1, max_new_tokens=maximum)
    generated = result[0, inputs["input_ids"].shape[1]:].tolist()
    raw = runtime.processor.decode(generated, skip_special_tokens=True, clean_up_tokenization_spaces=False)
    answer, error = None, None
    try:
        answer = parse_answer(row["task"], raw)
    except ValueError as failure:
        error = str(failure)
    emit("quality", id=row["id"], task=row["task"], signals=row["signals"], sample_rate=16000, question=question, maximum_new_tokens=maximum, feature_sha256=feature_hash, feature_shape=list(features.shape), feature_frames=frames, audio_tokens=tokens, generated_token_ids=generated, generation_complete=bool(generated and generated[-1] == runtime.boundaries["eos_token_id"]), raw_text=raw, answer=answer, parse_error=error, seconds=time.perf_counter() - started)


def audit_events(request, events):
    """Verify complete first observations and raw evidence without claiming the model's subjective judgements are ground truth."""
    try:
        validate_request(request)
        rows = [event for event in events if event.get("event") == "quality"]
        if [row.get("id") for row in rows] != [row["id"] for row in request["cases"]] or any(sum(event.get("event") == name for event in events) != 1 for name in ["ready", "complete"]):
            return False
        if any(event.get("event") in {"review", "diagnostic"} for event in events):
            return False
        if next(event for event in events if event.get("event") == "complete").get("cases") != len(rows):
            return False
        for source, event in zip(request["cases"], rows, strict=True):
            task = source["task"]
            question, maximum, _ = TASKS[task]
            expected = dict(task=task, signals=source["signals"], sample_rate=16000, question=question, maximum_new_tokens=maximum, generation_complete=True, parse_error=None)
            if any(event.get(key) != value for key, value in expected.items()):
                return False
            tokens, shape, frames = event.get("generated_token_ids"), event.get("feature_shape"), event.get("feature_frames")
            if type(tokens) is not list or not 1 <= len(tokens) <= maximum or any(type(token) is not int or token < 0 for token in tokens) or tokens[-1] != 151645:
                return False
            if type(shape) is not list or len(shape) != 3 or shape[:2] != [len(source["signals"]), 128] or type(shape[2]) is not int:
                return False
            if type(frames) is not list or len(frames) != len(source["signals"]) or any(type(frame) is not int or not 0 < frame <= shape[2] for frame in frames):
                return False
            if type(event.get("audio_tokens")) is not int or event["audio_tokens"] <= 0 or type(event.get("feature_sha256")) is not str or re.fullmatch(r"[0-9a-f]{64}", event["feature_sha256"]) is None:
                return False
            if parse_answer(task, event.get("raw_text")) != event.get("answer"):
                return False
    except (ValueError, TypeError, KeyError):
        return False
    logger.info("quality_observations_verified mode=%s cases=%d subjective_truth_certified=False", request["mode"], len(rows))
    return True
