"""Score frozen bilingual ASR observations without hiding failed coverage, repairing transcripts or promoting a model selection."""

import logging
import math
import unicodedata

logger = logging.getLogger(__name__)


def normalize(text):
    """Apply only predeclared NFC/casefold, punctuation-to-space and whitespace collapse while retaining accents and digits."""
    if type(text) is not str or len(text) > 8192:
        raise ValueError("asr_metric_text")
    value = unicodedata.normalize("NFC", text).casefold()
    result = " ".join(
        "".join(
            " " if unicodedata.category(c).startswith("P") else c for c in value
        ).split()
    )
    logger.debug("asr_text_normalized input_characters=%d", len(text))
    return result


def edit_distance(reference, hypothesis):
    """Compute exact Levenshtein edits using one dynamic-programming row, allowing error rates above one."""
    if len(reference) > 8192 or len(hypothesis) > 8192:
        raise ValueError("asr_metric_length")
    previous = list(range(len(hypothesis) + 1))
    for index, token in enumerate(reference, 1):
        current = [index]
        for position, predicted in enumerate(hypothesis, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[position] + 1,
                    previous[position - 1] + (token != predicted),
                )
            )
        previous = current
    return previous[-1]


def score(cases, predictions):
    """Retain every expected case and fail closed on duplicates/unknown IDs; report observed quality separately from complete coverage."""
    if not cases or len(cases) > 100 or len(predictions) > len(cases):
        raise ValueError("asr_metric_cases")
    expected = {c["id"]: c for c in cases}
    if len(expected) != len(cases) or any(
        c["language"] not in {"vi_vn", "en_us"} for c in cases
    ):
        raise ValueError("asr_metric_identity")
    observed = {}
    for row in predictions:
        if (
            row["id"] not in expected
            or row["id"] in observed
            or row["status"] not in {"ok", "error"}
        ):
            raise ValueError("asr_metric_prediction")
        if row["status"] == "ok":
            if (
                type(row.get("wall_seconds")) not in (int, float)
                or not math.isfinite(row["wall_seconds"])
                or row["wall_seconds"] <= 0
            ):
                raise ValueError("asr_metric_timing")
            normalize(row["text"])
        observed[row["id"]] = row
    rows, languages, controls = [], {}, []
    for identity, case in expected.items():
        observation = observed.get(identity)
        if observation is None or observation["status"] != "ok":
            rows.append(
                dict(id=identity, status="missing" if observation is None else "error")
            )
            continue
        ref, hyp = normalize(case["reference"]), normalize(observation["text"])
        record = dict(
            id=identity,
            status="ok",
            reference=case["reference"],
            prediction=observation["text"],
            normalized_reference=ref,
            normalized_prediction=hyp,
            wall_seconds=observation["wall_seconds"],
            real_time_factor=observation["wall_seconds"]
            / (case["sample_count"] / 16000),
        )
        if case["kind"] == "authored_no_speech":
            if ref:
                raise ValueError("asr_metric_control_reference")
            record["false_positive"] = bool(hyp)
            controls.append(record)
        elif case["kind"] == "independent_public_speech" and ref:
            words, characters = ref.split(), ref.replace(" ", "")
            record.update(
                word_edits=edit_distance(words, hyp.split()),
                reference_words=len(words),
                character_edits=edit_distance(characters, hyp.replace(" ", "")),
                reference_characters=len(characters),
            )
            aggregate = languages.setdefault(
                case["language"],
                dict(
                    observed_speech_cases=0,
                    word_edits=0,
                    reference_words=0,
                    character_edits=0,
                    reference_characters=0,
                ),
            )
            aggregate["observed_speech_cases"] += 1
            for key in (
                "word_edits",
                "reference_words",
                "character_edits",
                "reference_characters",
            ):
                aggregate[key] += record[key]
        else:
            raise ValueError("asr_metric_reference")
        rows.append(record)
    for aggregate in languages.values():
        aggregate.update(
            WER=aggregate["word_edits"] / aggregate["reference_words"],
            CER=aggregate["character_edits"] / aggregate["reference_characters"],
        )
    complete = len(observed) == len(cases) and all(r["status"] == "ok" for r in rows)
    logger.info(
        "asr_observations_scored expected=%d observed=%d complete=%s",
        len(cases),
        len(observed),
        complete,
    )
    return dict(
        coverage_complete=complete,
        expected_cases=len(cases),
        observed_successful_cases=sum(r["status"] == "ok" for r in rows),
        languages=languages,
        no_speech_observed=len(controls),
        no_speech_false_positives=sum(r["false_positive"] for r in controls),
        cases=rows,
        selection=None,
    )
