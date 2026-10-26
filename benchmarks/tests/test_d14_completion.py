"""Verify immutable D14 scoring, streaming identity, first-error capture and exact owned-process retirement without model weights or network access."""

import json
import runpy
import sys

import httpx
import pytest

MODULE = runpy.run_path("benchmarks/scripts/d14_completion.py")


@pytest.mark.parametrize(
    "content,expected",
    [
        (' {"x": 2} ', {"x": 2}),
        ('{"x":"Đà Nẵng"}', {"x": "Đà Nẵng"}),
        ('{"x":[1,2]}', {"x": [1, 2]}),
    ],
)
def test_strict_reference_allows_only_json_representation_variation(content, expected):
    """Accept whitespace and exact Unicode with complete declared types and structure."""
    assert MODULE["strict_score"](content, expected)


@pytest.mark.parametrize(
    "content",
    [
        '{"x":true}',
        '{"x":"2"}',
        '{"x":2,"x":2}',
        '{"x":NaN}',
        '```json\n{"x":2}\n```',
        '{"x":2,"extra":1}',
        '{"answer":{"x":2}}',
        'prefix {"x":2}',
    ],
)
def test_wrong_types_duplicate_keys_wrappers_and_repairs_remain_failed(content):
    """Do not turn incorrect native content into a correct answer through normalization or extraction."""
    assert not MODULE["strict_score"](content, {"x": 2})


def frame(model, *, text="", finish=None, usage=None):
    """Build a complete authored native streaming frame without synthesizing a model result inside the controller."""
    return (
        "data: "
        + json.dumps(
            dict(
                model=model,
                choices=[dict(index=0, delta=dict(content=text), finish_reason=finish)],
                usage=usage,
            )
        )
        + "\n\n"
    )


def test_stream_requires_actual_model_and_complete_terminal_events():
    """Decode exact native identity/content/usage while preserving actual completion rather than inventing response fields."""
    model = "qwen3.5-9b-core"
    raw = (
        frame(model, text='{"x":2}')
        + frame(model, finish="stop", usage=dict(prompt_tokens=3, completion_tokens=5))
        + "data: [DONE]\n\n"
    ).encode()
    result = MODULE["decode_stream"](raw, model)
    assert (
        result["model"] == model
        and result["choices"][0]["message"]["content"] == '{"x":2}'
    )


@pytest.mark.parametrize(
    "fault", ["wrong_model", "no_done", "duplicate_finish", "foreign_choice"]
)
def test_incomplete_or_foreign_stream_never_inherits_expected_identity(fault):
    """Reject wrong native identity, missing completion or duplicate/foreign choices before scoring."""
    model = "qwen3.5-9b-core"
    raw = frame(model, text='{"x":2}') + frame(model, finish="stop")
    if fault == "wrong_model":
        raw = raw.replace(model, "other")
    if fault == "duplicate_finish":
        raw += frame(model, finish="stop")
    if fault == "foreign_choice":
        raw = raw.replace('"index": 0', '"index": 1')
    if fault != "no_done":
        raw += "data: [DONE]\n\n"
    with pytest.raises(ValueError):
        MODULE["decode_stream"](raw.encode(), model)


def rows():
    """Supply five/four/three explicitly classified first observations for accounting controls."""
    return [
        dict(id=f"{name}-{n}", category=name, passed=True)
        for name, count in [
            ("multimodal", 5),
            ("performance", 3),
            ("memory_context", 4),
        ]
        for n in range(count)
    ]


def checks():
    """Supply five distinct local provenance facts without reading model files or making a legal-clearance claim."""
    return [dict(id=str(n), passed=True) for n in range(5)]


def test_original_weights_do_not_hide_existing_text_failures():
    """Even perfect new domains retain the measured CORE52.5 and UNRESTRICTED45 text points instead of rescoring them."""
    assert MODULE["weighted"](52.5, rows(), checks())["local_composite_points"] == 82.5
    assert MODULE["weighted"](45, rows(), checks())["local_composite_points"] == 75
    failed = rows()
    failed[0]["passed"] = False
    assert MODULE["weighted"](52.5, failed, checks())["local_composite_points"] == 80.5


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "duplicate",
        "category",
        "missing_provenance",
        "duplicate_provenance",
        "weight",
    ],
)
def test_incomplete_domain_counts_and_reweighting_fail_closed(fault):
    """Reject a smaller denominator, replaced duplicate, unknown category or invalid carried text score."""
    r, c, weight = rows(), checks(), 52.5
    if fault == "missing":
        r.pop()
    if fault == "duplicate":
        r[-1] = r[-2]
    if fault == "category":
        r[0]["category"] = "other"
    if fault == "missing_provenance":
        c.pop()
    if fault == "duplicate_provenance":
        c[0] = c[1]
    if fault == "weight":
        weight = 71
    with pytest.raises(ValueError):
        MODULE["weighted"](weight, r, c)


@pytest.mark.parametrize("profile", ["core", "unrestricted"])
def test_command_uses_only_existing_profile_projector_and_sequential_loopback(profile):
    """Keep existing32K/reasoningoff/GPU99/model paths without Docker, downloads, credential inheritance or production port use."""
    command = MODULE["command"](profile)
    assert command[command.index("--alias") + 1] == "qwen3.5-9b-" + profile
    assert command[command.index("--ctx-size") + 1] == "32768"
    assert command[command.index("--port") + 1] == "18080"
    assert "--offline" in command and "--mmproj" in command and "--no-warmup" in command
    assert not any(word in command for word in ["docker", "--hf-repo", "--url", "8080"])


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "http", "wrong_model", "length", "content"])
async def test_one_native_request_keeps_first_bytes_before_validation(tmp_path, fault):
    """Spend exactly one actual transport dispatch and preserve failures without repair, hidden retry or fake PASS."""
    attempts = []

    async def handle(request):
        """Return one typed mock-wire event while retaining actual attempted payload for assertions."""
        attempts.append(json.loads(request.content))
        return httpx.Response(
            503 if fault == "http" else 200,
            json=dict(
                model="other" if fault == "wrong_model" else "qwen3.5-9b-core",
                choices=[
                    dict(
                        message=dict(
                            content='{"x":3}' if fault == "content" else '{"x":2}'
                        ),
                        finish_reason="length" if fault == "length" else "stop",
                    )
                ],
                usage=dict(prompt_tokens=10, completion_tokens=5),
            ),
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://localhost"
    ) as client:
        value = await MODULE["first_request"](
            client,
            "core",
            dict(
                id="first", category="multimodal", prompt="Read x.", expected={"x": 2}
            ),
            tmp_path,
        )
    assert len(attempts) == value["model_requests"] == 1
    assert value["passed"] is (fault is None)
    assert (tmp_path / "first/native-response.bin").read_bytes()
    assert (tmp_path / "first/measurement.json").is_file()
    assert "expected" not in attempts[0]


@pytest.mark.asyncio
async def test_owned_retirement_joins_only_child_and_keeps_unrelated_process(tmp_path):
    """Exercise real POSIX group retirement/reaping without a GPU, model, Docker action or signal to an unrelated child."""
    import subprocess

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )
    server = MODULE["OwnedServer"]("core", tmp_path)
    server.process = child
    try:
        await server.stop()
        assert server.receipt()["reaped"] and unrelated.poll() is None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        unrelated.terminate()
        unrelated.wait()


@pytest.mark.asyncio
async def test_stream_split_bytes_keeps_first_nonempty_content_frame(tmp_path):
    """Do not call an empty role frame the first token, and decode native SSE correctly across arbitrary transport chunks."""
    model = "qwen3.5-9b-core"
    raw = (
        frame(model)
        + frame(model, text='{"x":2}')
        + frame(model, finish="stop", usage=dict(prompt_tokens=5, completion_tokens=5))
        + "data: [DONE]\n\n"
    ).encode()

    class Wire(httpx.AsyncByteStream):
        """Yield an empty initial content frame before fragmented actual text without any real network operation."""

        async def __aiter__(self):
            """Exercise transport boundaries independently of JSON or SSE event boundaries."""
            for offset in range(0, len(raw), 7):
                yield raw[offset : offset + 7]

    async def handle(request):
        """Return the explicit finite stream fixture to the original HTTP client interface."""
        return httpx.Response(200, stream=Wire())

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://localhost"
    ) as client:
        result = await MODULE["first_request"](
            client,
            "core",
            dict(id="stream", category="performance", prompt="x", expected={"x": 2}),
            tmp_path,
            stream=True,
        )
    assert result["passed"] and result["first_content_frame_seconds"] is not None


@pytest.mark.asyncio
async def test_planned_cancel_requires_content_then_actual_slot_retirement(tmp_path):
    """Close one native-shaped stream and prove cleanup using a separate readonly slot observation without a second generation."""
    model = "qwen3.5-9b-core"
    dispatches = []

    async def handle(request):
        """Record one generation and one readonly status request with finite authored native fixtures."""
        dispatches.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json=[dict(is_processing=False)])
        return httpx.Response(200, content=frame(model, text="1").encode())

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://localhost"
    ) as client:
        result = await MODULE["cancellation_probe"](client, "core", tmp_path)
    assert result["native_slot_retired"] and result["client_stream_closed"]
    assert dispatches == ["POST", "GET"]


@pytest.mark.asyncio
async def test_cancel_foreign_model_stops_without_followup_generation(tmp_path):
    """Retain the first identity failure without claiming a successful cancel or issuing a retry."""
    dispatches = []

    async def handle(request):
        """Return only one explicit wrong-identity stream and count attempted network operations."""
        dispatches.append(request.method)
        return httpx.Response(200, content=frame("foreign", text="1").encode())

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://localhost"
    ) as client:
        result = await MODULE["cancellation_probe"](client, "core", tmp_path)
    assert result["status"] == "FAILED" and dispatches == ["POST"]


@pytest.mark.asyncio
async def test_frozen_input_drift_rejected_before_model_or_runtime_inventory(
    tmp_path, monkeypatch
):
    """Require exact pre-inference bytes before invoking any model, Docker inventory or native process operation."""
    source = tmp_path / "source.py"
    source.write_text("changed")
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps(dict(sha256={str(source): "0" * 64})))
    monkeypatch.setitem(MODULE["run"].__globals__, "FREEZE", freeze)
    with pytest.raises(ValueError, match="d14_frozen_input_changed"):
        await MODULE["run"]()


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_first", [False, True])
async def test_complete_campaign_spends_exact_declared_requests_and_retires_both_profiles(
    tmp_path, monkeypatch, failed_first
):
    """Exercise the complete real controller with native-shaped HTTP fixtures, exact request accounting, retained errors and no weights/GPU/network."""
    globals_ = MODULE["run"].__globals__
    output = tmp_path / "output"
    output.mkdir()
    image = tmp_path / "image.png"
    image.write_bytes(b"authored non-network fixture")
    media = [
        dict(
            id=f"media-{n}",
            category="multimodal",
            prompt="Read.",
            expected={"x": n},
            image=str(image),
        )
        for n in range(5)
    ]
    context = [
        dict(
            id=f"context-{n}",
            category="memory_context",
            needle=str(n),
            expected={"code": str(n)},
        )
        for n in range(4)
    ]
    performance = [
        dict(
            id=f"perf-{n}",
            category="performance",
            prompt="Sequence.",
            expected={"x": 10},
        )
        for n in range(3)
    ]
    freeze = tmp_path / "freeze.json"
    freeze.write_text(
        json.dumps(
            dict(
                sha256={},
                application_sha256={"frozen": "source"},
                media=media,
                context=context,
                performance=performance,
                retained_text_points=dict(core=52.5, unrestricted=45),
            )
        )
    )
    model_dispatches = dict(core=0, unrestricted=0)
    retired = []

    class Server:
        """Provide a fully owned fake lifecycle while letting the real controller perform every HTTP capture and scoring step."""

        def __init__(self, profile, root):
            """Retain exact profile and fresh target without starting a process."""
            self.profile, self.failure, self.exit_code = profile, None, None

        async def start(self):
            """Make the fake server ready without changing process or GPU state."""
            self.exit_code = None

        async def stop(self):
            """Expose exact retirement of each separately selected profile."""
            self.exit_code = 0
            retired.append(self.profile)

        def receipt(self):
            """Return only the explicit fake lifecycle fact, never a real-model memory measurement."""
            return dict(reaped=self.exit_code == 0, fixture_only=True)

    async def calibrate(client, case):
        """Supply fixed token-count metadata without sending a tokenizer or generation request."""
        return case["needle"], dict(user_tokens=30500, needle_prefix_tokens=8000)

    async def handle(request):
        """Serve exactly the declared first outcomes including optional failure and a final intentional cancellation stream."""
        if request.method == "GET":
            return httpx.Response(200, json=[dict(is_processing=False)])
        payload = json.loads(request.content)
        profile = payload["model"].removeprefix("qwen3.5-9b-")
        number = model_dispatches[profile]
        model_dispatches[profile] += 1
        all_cases = media + context + performance
        if number == 12:
            return httpx.Response(
                200, content=frame(payload["model"], text="1").encode()
            )
        case = all_cases[number]
        content = json.dumps(case["expected"])
        if failed_first and number == 0:
            return httpx.Response(503, content=b"first failure retained")
        usage = dict(
            prompt_tokens=30550 if case["category"] == "memory_context" else 20,
            completion_tokens=20,
        )
        if payload["stream"]:
            return httpx.Response(
                200,
                content=(
                    frame(payload["model"], text=content)
                    + frame(payload["model"], finish="stop", usage=usage)
                    + "data: [DONE]\n\n"
                ).encode(),
            )
        return httpx.Response(
            200,
            json=dict(
                model=payload["model"],
                choices=[dict(message=dict(content=content), finish_reason="stop")],
                usage=usage,
            ),
        )

    original_client = httpx.AsyncClient

    def client_factory(**options):
        """Redirect the real HTTP interface only to an explicit deterministic transport fixture."""
        return original_client(
            transport=httpx.MockTransport(handle), base_url="http://localhost"
        )

    def state():
        """Return unchanged authored boot/container facts for the controller's baseline comparison."""
        return dict(native_pids=[], boot_id="fixture", containers=[])

    monkeypatch.setitem(globals_, "FREEZE", freeze)
    monkeypatch.setitem(globals_, "OUTPUT", output)
    monkeypatch.setitem(globals_, "source_manifest", lambda: {"frozen": "source"})
    monkeypatch.setitem(globals_, "verify_manifest", lambda source: None)
    monkeypatch.setitem(globals_, "local_state", state)
    monkeypatch.setitem(globals_, "OwnedServer", Server)
    monkeypatch.setitem(globals_, "context_prompt", calibrate)
    monkeypatch.setitem(globals_, "provenance", lambda profile: checks())
    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await MODULE["run"]()
    assert model_dispatches == dict(core=13, unrestricted=13)
    assert retired == ["core", "unrestricted"] and result["runtime_baseline_restored"]
    assert result["status"] == "MEASUREMENT_COMPLETE_QUALITY_FINDINGS_RETAINED"
    for profile in ["core", "unrestricted"]:
        assert len(result["profiles"][profile]["rows"]) == 12
        if failed_first:
            assert result["profiles"][profile]["rows"][0]["passed"] is False
            assert (
                output / profile / "media-0/native-response.bin"
            ).read_bytes() == b"first failure retained"


@pytest.mark.asyncio
async def test_existing_native_runtime_blocks_trial_before_loading(
    tmp_path, monkeypatch
):
    """Refuse an occupied runtime slot rather than stopping, replacing or taking ownership of another model process."""
    globals_ = MODULE["OwnedServer"].start.__globals__

    def busy():
        """Report an unrelated pre-existing native PID without accessing the real machine."""
        return dict(native_pids=[123])

    monkeypatch.setitem(globals_, "local_state", busy)
    server = MODULE["OwnedServer"]("core", tmp_path)
    with pytest.raises(ValueError, match="d14_native_runtime_busy"):
        await server.start()
    assert server.process is None


@pytest.mark.parametrize("fault", [None, "changed", "unrelated", "symlink"])
def test_provenance_flattened_copy_requires_original_complete_hash(
    tmp_path, monkeypatch, fault
):
    """Reconcile known relocated metadata bytes without silently fixing old manifests or trusting an unrelated or changed replacement."""
    directory = tmp_path / "models/unrestricted/qwen3.5-9b"
    directory.mkdir(parents=True)
    copy_path = directory / "config.json"
    copy_path.write_bytes(b"original pinned bytes")
    expected = MODULE["digest"](copy_path)
    item = dict(
        file="models/unrestricted/qwen3.5-9b/upstream_reference/config.json",
        sha256=expected,
    )
    if fault == "changed":
        copy_path.write_bytes(b"changed")
    if fault == "unrelated":
        item["file"] = "unrelated/config.json"
    if fault == "symlink":
        original = directory / "original.json"
        copy_path.rename(original)
        copy_path.symlink_to(original)
    monkeypatch.setitem(MODULE["source_binding"].__globals__, "ROOT", tmp_path)
    result = MODULE["source_binding"](item, directory)
    assert result["complete_sha256_matches"] is (fault is None)
    assert result["original_path_exists"] is False
