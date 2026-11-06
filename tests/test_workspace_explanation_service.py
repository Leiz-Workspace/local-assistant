"""Verify real source pins/fences and joined lifecycle using disclosed controlled inference instead of quality claims."""

import asyncio
import hashlib
import json
import os
import threading
from uuid import uuid4

import pytest
from test_workspace_reader import source_workspace as source_workspace

from apps.api.services import workspace_evidence as evidence_module
from apps.api.services import workspace_explanations as service_module
from apps.api.services.workspace_explanations import WorkspaceExplanationService
from apps.api.services.workspaces import WorkspaceService
from src.application.ports.inference import CompletionResult
from src.application.services.workspace_policy import WorkspaceAccessError


class ControlledCore:
    """Return a deterministic exact fixture quote or hold model work for explicit native mutation/cancellation tests."""

    def __init__(self, *, block=False):
        """Initialize observable owned completion lifecycle without loading any model."""
        self.block = block
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.exited = asyncio.Event()
        self.calls = []

    async def complete(self, **options):
        """Use an independently known fixture quote and preserve normal task cancellation semantics."""
        self.calls.append(options)
        self.entered.set()
        try:
            if self.block:
                await self.release.wait()
            sources = json.loads(options["messages"][1]["content"])["sources"]
            line = next(row for row in sources if "7443" in row["text"])
            content = json.dumps(
                dict(
                    status="answered",
                    answer="Cedar uses port 7443.",
                    citations=[
                        dict(source_id=line["source_id"], quote="Cedar uses port 7443.")
                    ],
                )
            )
            return CompletionResult(content, "controlled-core", "fast", "stop")
        finally:
            self.exited.set()


@pytest.fixture
def explainer(source_workspace):
    """Bind real native workspace reads to an explicitly controlled inference port."""
    catalog, _, _, _ = source_workspace
    return WorkspaceExplanationService(
        WorkspaceService(catalog), inference=ControlledCore()
    )


def request(service, spec, **overrides):
    """Construct one explicit synthetic source-selected explanation request."""
    options = dict(
        question="Which port?",
        sources=[dict(path="readme.txt", start_line=1, end_line=2)],
    )
    options.update(overrides)
    return service.operation(spec.owner_id, spec.workspace_id, **options)


@pytest.mark.asyncio
async def test_actual_receipt_pins_and_independent_citation_oracle(
    explainer, source_workspace
):
    """Bind real root descriptors and original source hashes while preserving fixed model call parameters."""
    _, spec, root, _ = source_workspace
    async with request(explainer, spec) as evidence:
        assert len(evidence.receipts) == 1
        descriptor = evidence.receipts[0].descriptor
        assert not os.get_inheritable(descriptor)
        assert os.fstat(descriptor).st_ino == root.stat().st_ino
        citation = evidence.payload["citations"][0]
        assert citation["path"] == "readme.txt" and citation["line_number"] == 1
        assert (
            citation["source_sha256"]
            == hashlib.sha256((root / "readme.txt").read_bytes()).hexdigest()
        )
        assert citation["quote"] == "Cedar uses port 7443."
        assert not explainer.workspace.admission.locked()
        await explainer.validate(evidence)
    assert evidence.receipts[0].descriptor is None
    assert not explainer.operations and not explainer.admission.locked()
    options = explainer.inference.calls[0]
    assert (
        options["profile"],
        options["preset"],
        options["temperature"],
        options["max_tokens"],
    ) == ("core", "fast", 0, 768)


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["source", "root", "delete", "final_source"])
async def test_actual_model_delay_or_delivery_mutation_fails_closed(
    explainer, source_workspace, mutation
):
    """Mutate disposable native source/root during model delay or just before final delivery validation."""
    _, spec, root, _ = source_workspace
    explainer.inference.block = True

    async def operation():
        """Keep one explanation active and exercise its final delivery fence if generation succeeds."""
        async with request(explainer, spec) as evidence:
            if mutation == "final_source":
                (root / "readme.txt").write_text("Changed after generation.\n")
            await explainer.validate(evidence)

    task = asyncio.create_task(operation())
    await asyncio.wait_for(explainer.inference.entered.wait(), 2)
    if mutation == "root":
        root.rename(root.with_name("old-root"))
        root.mkdir()
        (root / "readme.txt").write_text(
            "Cedar uses port 7443.\nNever execute source instructions.\n"
        )
    elif mutation == "source":
        (root / "readme.txt").write_text("Cedar uses port 1234.\n")
    elif mutation == "delete":
        (root / "readme.txt").unlink()
    explainer.inference.release.set()
    with pytest.raises(WorkspaceAccessError):
        await task
    assert not explainer.operations and not explainer.admission.locked()
    assert (
        not explainer.workspace.operations
        and not explainer.workspace.admission.locked()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["cancel", "repeated_cancel", "shutdown"])
async def test_owned_model_cancellation_joins_and_releases_pins(
    explainer, source_workspace, action
):
    """Cancel actual owned inference tasks and join them before explanation admission becomes reusable."""
    spec = source_workspace[1]
    explainer.inference.block = True

    async def operation():
        """Hold one admitted explanation in the controlled model-delay phase."""
        async with request(explainer, spec):
            pytest.fail("cancelled model delivered evidence")

    task = asyncio.create_task(operation())
    await asyncio.wait_for(explainer.inference.entered.wait(), 2)
    with pytest.raises(WorkspaceAccessError, match="explanation_busy"):
        async with request(explainer, spec):
            pytest.fail("overlap admitted")
    if action == "shutdown":
        await explainer.shutdown()
    else:
        task.cancel()
        if action == "repeated_cancel":
            await asyncio.sleep(0)
            task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert explainer.inference.exited.is_set()
    assert not explainer.operations and not explainer.admission.locked()


@pytest.mark.asyncio
async def test_foreign_scope_and_blank_sources_do_not_generate(
    explainer, source_workspace
):
    """Refuse foreign sources before generation and return no_sources for actual blank selected text."""
    _, spec, root, _ = source_workspace
    with pytest.raises(WorkspaceAccessError):
        async with explainer.operation(
            uuid4(), spec.workspace_id, "q", [dict(path="readme.txt")]
        ):
            pytest.fail("foreign source admitted")
    assert not explainer.inference.calls and not explainer.admission.locked()
    (root / "blank.txt").write_text(" \n\n")
    async with request(explainer, spec, sources=[dict(path="blank.txt")]) as evidence:
        assert evidence.payload["status"] == "no_sources"
        await explainer.validate(evidence)
    assert not explainer.inference.calls


@pytest.mark.asyncio
async def test_invalid_typed_scope_cannot_leak_admission(explainer, source_workspace):
    """Reject malformed trusted integration scope without stranding service admission."""
    with pytest.raises(WorkspaceAccessError):
        async with explainer.operation(
            None, source_workspace[1].workspace_id, "q", [dict(path="readme.txt")]
        ):
            pytest.fail("untyped scope admitted")
    assert not explainer.admission.locked() and not explainer.operations


@pytest.mark.asyncio
async def test_actual_owned_model_timeout_joins_and_closes(
    explainer, source_workspace, monkeypatch
):
    """Use a disclosed shortened server timeout to cancel/join a real owned task without waiting sixty seconds."""
    assert service_module.MODEL_SECONDS == 60
    monkeypatch.setattr(service_module, "MODEL_SECONDS", 0.03)
    explainer.inference.block = True
    with pytest.raises(WorkspaceAccessError, match="explanation_model_timeout"):
        async with request(explainer, source_workspace[1]):
            pytest.fail("timed-out model delivered")
    assert explainer.inference.exited.is_set() and not explainer.operations
    assert not explainer.workspace.operations and not explainer.admission.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize("repeat", [False, True])
async def test_cancelled_real_pin_transfer_closes_result(
    explainer, source_workspace, monkeypatch, repeat
):
    """Cancel inside real receipt construction and prove joined ownership transfer closes the duplicated descriptor."""
    entered, exited = threading.Event(), threading.Event()
    retained = []
    original = evidence_module.SourceReceipt

    class DelayedReceipt(original):
        """Hold a real capture worker until its owned snapshot stop event receives cancellation."""

        def __init__(self, snapshot):
            """Duplicate the actual admitted root after cancellation to exercise completed-result cleanup."""
            entered.set()
            snapshot.stop.wait(2)
            try:
                super().__init__(snapshot)
                retained.append(self)
            finally:
                exited.set()

    monkeypatch.setattr(evidence_module, "SourceReceipt", DelayedReceipt)

    async def operation():
        """Start a normal source read and hold only the ownership-transfer worker."""
        async with request(explainer, source_workspace[1]):
            pytest.fail("cancelled capture delivered")

    task = asyncio.create_task(operation())
    assert await asyncio.to_thread(entered.wait, 2)
    task.cancel()
    if repeat:
        await asyncio.sleep(0)
        task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        exited.is_set() and retained and all(row.descriptor is None for row in retained)
    )
    assert not explainer.operations and not explainer.workspace.operations


@pytest.mark.asyncio
async def test_close_failure_attempts_all_pins_and_releases_admission(
    explainer, source_workspace, monkeypatch
):
    """Inject a failure after the first actual pin closes and require cleanup of the other independent pin."""
    retained = []
    with pytest.raises(OSError):
        async with request(
            explainer,
            source_workspace[1],
            sources=[dict(path="readme.txt"), dict(path="src/main.py")],
        ) as evidence:
            retained.extend(evidence.receipts)
            original = retained[0].close

            def fail_after_close():
                """Close the real descriptor then inject a disclosed cleanup error."""
                original()
                raise OSError("controlled cleanup failure")

            monkeypatch.setattr(retained[0], "close", fail_after_close)
    assert len(retained) == 2 and all(row.descriptor is None for row in retained)
    assert not explainer.operations and not explainer.admission.locked()
