"""Re-derive one default whole-turn packing and report exact prefix-marginal layers without repacking."""

import hashlib
import json
import logging

from apps.api.runtime.presets import (
    ANSWER_RESERVE,
    CONTEXT_RESERVE,
    PresetError,
    calculate_budget,
    get_preset,
)
from src.application.ports.inference import InferenceFailure
from src.application.services.context_composer import POLICY, evidence_block
from src.application.services.conversation_context import (
    fit_token_budget,
    select_whole_turns,
)
from src.application.services.review_output_contract import (
    INSTRUCTIONS as REVIEW_INSTRUCTIONS,
    NAME as REVIEW_NAME,
    QUOTE_FIRST_NAME,
)
from src.application.services.source_output_contract import INSTRUCTIONS, NAME
from src.application.services.special_literals import neutralize

LOGGER = logging.getLogger(__name__)
METHOD = "prefix-marginal-v1"
SELECTION_MESSAGES = 24
WINDOW_PAIRS = (SELECTION_MESSAGES - 1) // 2
SOURCE_BYTE_LIMIT = 65536
FRAGMENT_CHARS = 256
SKILL_HEADER = "\nReviewed task skill (subordinate to host policy):\n"
REVIEW_TARGET_HEADER = "\nHost-selected review target: "
STRATEGIES = {"evidence-first", "recent-turns", "strict"}
COUNTED_REASONS = {"token_budget", "history_priority"}
CONTROL_LITERALS = {
    "im_start": b"<|im_start|>",
    "im_end": b"<|im_end|>",
    "endoftext": b"<|endoftext|>",
    "think_open": b"<think>",
    "think_close": b"</think>",
}


class _Mismatch(Exception):
    """Stop the reconstruction with a closed reason code instead of raising to the caller."""

    def __init__(self, reason):
        """Keep only the reason code, never message or evidence text."""
        super().__init__(reason)
        self.reason = reason


class _Counter:
    """Count calls to the caller's token counter and remember whether it raised."""

    def __init__(self, count_tokens):
        """Wrap the exact counter used by the composer."""
        self.count_tokens = count_tokens
        self.calls = 0
        self.failed = False

    async def __call__(self, rows):
        """Count fresh copies so the counter can never mutate caller-owned messages."""
        self.calls += 1
        try:
            return await self.count_tokens([dict(row) for row in rows])
        except BaseException:
            self.failed = True
            raise


def _valid_rows(rows):
    """Accept only non-empty lists of role/content messages with string content."""
    return (
        isinstance(rows, list)
        and bool(rows)
        and all(
            isinstance(row, dict)
            and set(row) == {"role", "content"}
            and isinstance(row["role"], str)
            and row["role"] in {"system", "user", "assistant"}
            and isinstance(row["content"], str)
            for row in rows
        )
    )


def _contract_matches(segment, output_contract):
    """Check that the system segment between policy and skill is exactly the selected host contract."""
    if output_contract == "text":
        return segment == ""
    if output_contract == NAME:
        return segment == "\n" + INSTRUCTIONS
    if output_contract not in {REVIEW_NAME, QUOTE_FIRST_NAME}:
        return False
    head = (
        "\n"
        + REVIEW_INSTRUCTIONS.replace(REVIEW_NAME, output_contract)
        + REVIEW_TARGET_HEADER
    )
    if not segment.startswith(head):
        return False
    encoded = segment[len(head) :]
    try:
        target = json.loads(encoded)
    except ValueError:
        return False
    return isinstance(target, str) and json.dumps(target, ensure_ascii=False) == encoded


def _block(raw):
    """Rebuild the exact evidence suffix the composer appends to the current task."""
    return evidence_block(raw)


def _evidence_facts(raw):
    """Describe one evidence item by size, UTF-8 validity and literal control-token counts."""
    try:
        raw.decode("utf-8")
        valid = True
    except UnicodeDecodeError:
        valid = False
    return {
        "bytes": len(raw),
        "utf8_valid": valid,
        "control_literals": {
            name: raw.count(literal) for name, literal in CONTROL_LITERALS.items()
        },
    }


def _evidence_decisions(evidence, report, strategy):
    """Check C1: indices partition into included and omitted with the composer's admissible reasons."""
    included, omitted = report.get("included_evidence"), report.get("omitted_evidence")
    if len(evidence) > 4 or not isinstance(included, list):
        raise _Mismatch("evidence_partition")
    if not isinstance(omitted, list):
        raise _Mismatch("evidence_partition")
    hashes = [hashlib.sha256(raw).hexdigest() for raw in evidence]
    decisions = {}
    for entry in included + omitted:
        index = entry.get("index") if isinstance(entry, dict) else None
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not 0 <= index < len(evidence)
            or index in decisions
            or not isinstance(entry.get("reason", "included"), str)
        ):
            raise _Mismatch("evidence_partition")
        decisions[index] = entry.get("reason", "included")
    order = sorted(decisions)
    expected_included = [
        {"index": index, "sha256": hashes[index]}
        for index in order
        if decisions[index] == "included"
    ]
    expected_omitted = [
        {"index": index, "sha256": hashes[index], "reason": decisions[index]}
        for index in order
        if decisions[index] != "included"
    ]
    if (
        len(decisions) != len(evidence)
        or included != expected_included
        or omitted != expected_omitted
    ):
        raise _Mismatch("evidence_partition")
    admissible = {"included", "token_budget"}
    if strategy != "evidence-first":
        admissible.add("history_priority")
    seen = set()
    for index, raw in enumerate(evidence):
        if hashes[index] in seen:
            allowed = {"duplicate_evidence"}
        elif len(raw) > SOURCE_BYTE_LIMIT:
            allowed = {"source_byte_limit"}
        else:
            allowed = admissible
        seen.add(hashes[index])
        if decisions[index] not in allowed:
            raise _Mismatch("evidence_reason")
    return hashes, decisions


def _budget(preset, input_tokens, max_tokens):
    """Return the output budget at the packed input, with its closed-form input ceiling and identity."""
    try:
        config = get_preset(preset)
        plan = calculate_budget(
            preset=preset, input_tokens=input_tokens, requested_max_tokens=max_tokens
        )
    except PresetError:
        raise _Mismatch("budget_rejected") from None
    finite = (
        config.thinking
        and config.reasoning_budget is not None
        and config.reasoning_budget >= 0
    )
    floor = ANSWER_RESERVE + (config.reasoning_budget if finite else 0)
    ceiling = plan.context_size - CONTEXT_RESERVE - floor
    unallocated = plan.context_size - input_tokens - CONTEXT_RESERVE - plan.max_tokens
    nominal = [value for value in (config.max_output, max_tokens) if value is not None]
    return {
        "preset": config.name.value,
        "thinking": config.thinking,
        "reasoning_budget": config.reasoning_budget,
        "requested_max_tokens": max_tokens,
        "max_tokens_granted": plan.max_tokens,
        "preset_output_ceiling": config.max_output,
        "context_size": plan.context_size,
        "context_reserve": CONTEXT_RESERVE,
        "answer_reserve": ANSWER_RESERVE,
        "unallocated": unallocated,
        "input_ceiling": ceiling,
        "output_squeezed": bool(nominal) and plan.max_tokens < min(nominal),
        "identity_ok": (
            input_tokens + CONTEXT_RESERVE + plan.max_tokens + unallocated
            == plan.context_size
            and unallocated >= 0
            and input_tokens <= ceiling
        ),
    }


async def _inspect(
    messages,
    fitted,
    report,
    counter,
    *,
    preset,
    max_tokens,
    skill,
    evidence,
    output_contract,
):
    """Reconstruct the packing with checks C1-C6, then count prefix-marginal layers and omissions."""
    evidence = list(evidence)
    if not _valid_rows(messages) or not _valid_rows(fitted) or len(fitted) < 2:
        raise _Mismatch("invalid_messages")
    if messages[-1]["role"] != "user" or fitted[-1]["role"] != "user":
        raise _Mismatch("invalid_messages")
    strategy = report.get("source_priority")
    if (
        report.get("strategy") != "whole-turn-evidence-v1"
        or not isinstance(strategy, str)
        or strategy not in STRATEGIES
    ):
        raise _Mismatch("report_strategy")
    if report.get("automatic_memory") is not False:
        raise _Mismatch("report_flags")
    if report.get("summarization") is not False:
        raise _Mismatch("report_flags")
    if report.get("skill_sha256") != (skill.raw_sha256 if skill is not None else None):
        raise _Mismatch("skill_sha256")
    system = fitted[0]["content"]
    skill_block = SKILL_HEADER + skill.instructions if skill is not None else ""
    if (
        fitted[0]["role"] != "system"
        or not system.startswith(POLICY)
        or not system.endswith(skill_block)
        or len(system) < len(POLICY) + len(skill_block)
    ):
        raise _Mismatch("system_segments")
    contract = system[len(POLICY) : len(system) - len(skill_block)]
    if not _contract_matches(contract, output_contract):
        raise _Mismatch("output_contract")
    system_row = {"role": "system", "content": system}
    client_indices = [
        index for index, row in enumerate(messages) if row["role"] == "system"
    ]
    clients = [messages[index] for index in client_indices]
    if fitted[1 : 1 + len(clients)] != clients:
        raise _Mismatch("client_system")

    task = messages[-1]
    history = [
        index for index, row in enumerate(messages[:-1]) if row["role"] != "system"
    ]
    turns = [
        (history[position], history[position + 1])
        for position in range(len(history) - 1)
        if messages[history[position]]["role"] == "user"
        and messages[history[position + 1]]["role"] == "assistant"
    ]
    paired = {index for turn in turns for index in turn}
    unpaired = [index for index in history if index not in paired]

    def flatten(selected_turns):
        """Return the original messages of the given pairs in conversation order."""
        return [messages[index] for turn in selected_turns for index in turn]

    original = [system_row] + messages
    selected = select_whole_turns(original, SELECTION_MESSAGES)
    window = turns[-WINDOW_PAIRS:]
    if selected != [system_row] + clients + flatten(window) + [task]:
        raise _Mismatch("selection")
    middle = fitted[1 + len(clients) : -1]
    retained = len(middle) // 2
    if len(middle) % 2 or retained > len(window):
        raise _Mismatch("retained_pairs")
    if middle != flatten(turns[len(turns) - retained :]):
        raise _Mismatch("retained_pairs")
    trimmed = len(original) - len(fitted)
    if report.get("retained_messages") != len(fitted):
        raise _Mismatch("trimmed_messages")
    if report.get("trimmed_messages") != trimmed:
        raise _Mismatch("trimmed_messages")
    if strategy == "strict" and trimmed:
        raise _Mismatch("strict_trimmed")

    hashes, decisions = _evidence_decisions(evidence, report, strategy)
    included = [index for index in sorted(decisions) if decisions[index] == "included"]
    omitted = [index for index in sorted(decisions) if decisions[index] != "included"]
    blocks = {index: _block(evidence[index]) for index in included}
    last = {
        "role": "user",
        "content": task["content"] + "".join(blocks[index] for index in included),
    }
    if fitted[-1] != last:
        raise _Mismatch("task_evidence")
    included_hashes = {hashes[index] for index in included}
    for index in omitted:
        if hashes[index] in included_hashes:
            continue
        escaped = json.dumps(
            evidence[index].decode("utf-8", errors="replace"), ensure_ascii=False
        )[1:-1]
        sent = neutralize(escaped)[0]
        fragments = {
            escaped[:FRAGMENT_CHARS],
            escaped[-FRAGMENT_CHARS:],
            sent[:FRAGMENT_CHARS],
            sent[-FRAGMENT_CHARS:],
        } - {""}
        if any(part in row["content"] for part in fragments for row in fitted):
            raise _Mismatch("omitted_evidence_present")

    try:
        history_fit = await fit_token_budget(
            [dict(row) for row in selected],
            preset=preset,
            max_tokens=max_tokens,
            count_tokens=counter,
        )
    except InferenceFailure as error:
        if counter.failed:
            raise
        raise _Mismatch("history_fit_" + error.code) from None
    fitted_pairs = (len(history_fit) - 2 - len(clients)) // 2
    if history_fit[1 + len(clients) : -1] != flatten(
        turns[len(turns) - fitted_pairs :]
    ):
        raise _Mismatch("history_fit")
    if retained > fitted_pairs:
        raise _Mismatch("retained_pairs")
    if strategy != "evidence-first" and retained != fitted_pairs:
        raise _Mismatch("retained_pairs")
    if fitted_pairs > retained and not included:
        raise _Mismatch("evidence_priority_without_evidence")
    trim = {
        "unpaired": len(unpaired),
        "turn_window": 2 * (len(turns) - len(window)),
        "token_budget": 2 * (len(window) - fitted_pairs),
        "evidence_priority": 2 * (fitted_pairs - retained),
    }
    if sum(trim.values()) != report["trimmed_messages"]:
        raise _Mismatch("trim_split")

    task_row = {"role": "user", "content": task["content"]}
    previous = await counter([task_row])
    layers = [{"layer": "current_task", "tokens": previous}]

    async def add_layer(rows, entry):
        """Count one larger prefix and record its marginal over the previous prefix."""
        nonlocal previous
        total = await counter(rows)
        entry["tokens"] = total - previous
        previous = total
        layers.append(entry)

    await add_layer(
        [{"role": "system", "content": POLICY}, task_row], {"layer": "policy"}
    )
    for name, text, end in (
        ("output_contract", contract, len(POLICY) + len(contract)),
        ("skill", skill_block, len(system)),
    ):
        if text:
            prefix = {"role": "system", "content": system[:end]}
            await add_layer([prefix, task_row], {"layer": name})
        else:
            layers.append({"layer": name, "tokens": 0})
    for position, message in enumerate(client_indices):
        await add_layer(
            [system_row] + clients[: position + 1] + [task_row],
            {"layer": "client_system", "message": message},
        )
    base = [system_row] + clients
    base_tokens = previous
    kept = []
    for number in range(len(turns) - retained, len(turns)):
        kept += flatten([turns[number]])
        await add_layer(
            base + kept + [task_row], {"layer": "history_pair", "pair": number + 1}
        )
    content = task["content"]
    for index in included:
        content += blocks[index]
        await add_layer(
            base + kept + [{"role": "user", "content": content}],
            {
                "layer": "evidence",
                "index": index,
                "sha256": hashes[index],
                **_evidence_facts(evidence[index]),
            },
        )
    if base + kept + [{"role": "user", "content": content}] != fitted:
        raise _Mismatch("prefix_mismatch")
    if previous != report.get("input_tokens"):
        raise _Mismatch("input_tokens")

    positioned = [
        (index, {"message": index, "messages": 1, "reason": "unpaired", "tokens": None})
        for index in unpaired
    ]
    boundaries = (
        (len(turns) - len(window), "turn_window"),
        (len(turns) - fitted_pairs, "token_budget"),
        (len(turns) - retained, "evidence_priority"),
    )
    counted_pairs = 0
    for number, turn in enumerate(turns[: len(turns) - retained]):
        reason = next(name for limit, name in boundaries if number < limit)
        tokens = None
        if reason != "turn_window":
            counted_pairs += 1
            tokens = await counter(base + flatten([turn]) + [task_row]) - base_tokens
        positioned.append(
            (
                turn[0],
                {"pair": number + 1, "messages": 2, "reason": reason, "tokens": tokens},
            )
        )
    history_omissions = [entry for _, entry in sorted(positioned, key=lambda x: x[0])]
    evidence_omissions = []
    for index in omitted:
        tokens = None
        if decisions[index] in COUNTED_REASONS:
            candidate = [dict(row) for row in fitted]
            candidate[-1]["content"] += _block(evidence[index])
            tokens = await counter(candidate) - report["input_tokens"]
        evidence_omissions.append(
            {
                "index": index,
                "sha256": hashes[index],
                "reason": decisions[index],
                **_evidence_facts(evidence[index]),
                "tokens": tokens,
            }
        )
    budget = _budget(preset, report["input_tokens"], max_tokens)
    counted_evidence = sum(entry["tokens"] is not None for entry in evidence_omissions)
    bound = (
        (len(window) + 1)
        + 4
        + len(clients)
        + retained
        + len(included)
        + counted_pairs
        + counted_evidence
    )
    return {
        "schema_version": 1,
        "method": METHOD,
        "status": "COMPLETE",
        "layers": layers,
        "layer_total": sum(entry["tokens"] for entry in layers),
        "trimmed": trim,
        "omissions": {"history": history_omissions, "evidence": evidence_omissions},
        "budget": budget,
        "checks": {
            name: True for name in ("C1", "C2", "C3", "C4", "C5", "C6", "layer_sum")
        },
        "count_bound": bound,
        "count_calls": counter.calls,
    }


async def inspect_context(
    messages,
    fitted,
    report,
    *,
    count_tokens,
    preset,
    max_tokens=None,
    skill=None,
    evidence=(),
    output_contract="text",
):
    """Inspect a schema-1 packing; return COMPLETE, MISMATCH or UNSUPPORTED and let counter errors propagate."""
    counter = _Counter(count_tokens)
    if not isinstance(report, dict):
        result = {"status": "MISMATCH", "reason": "invalid_report"}
    elif report.get("schema_version") != 1:
        result = {"status": "UNSUPPORTED", "reason": "history_policy_path"}
    else:
        try:
            result = await _inspect(
                messages,
                fitted,
                report,
                counter,
                preset=preset,
                max_tokens=max_tokens,
                skill=skill,
                evidence=evidence,
                output_contract=output_contract,
            )
        except _Mismatch as mismatch:
            result = {"status": "MISMATCH", "reason": mismatch.reason}
    if result["status"] != "COMPLETE":
        result = {
            "schema_version": 1,
            "method": METHOD,
            **result,
            "count_calls": counter.calls,
        }
    LOGGER.info(
        "context_inspection_computed status=%s calls=%d layers=%d",
        result["status"],
        counter.calls,
        len(result.get("layers", ())),
    )
    return result
