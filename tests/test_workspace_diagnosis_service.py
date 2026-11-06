"""Verify inherited native diagnostic ownership and unchanged source bytes with disclosed controlled inference."""

import asyncio
import hashlib
import json

import pytest
from test_workspace_diagnosis import proposed_diagnosis
from test_workspace_explanation_service import ControlledCore
from test_workspace_reader import source_workspace as source_workspace

from apps.api.services.workspace_diagnoses import WorkspaceDiagnosisService
from apps.api.services.workspaces import WorkspaceService
from src.application.ports.inference import CompletionResult
from src.application.services.workspace_policy import WorkspaceAccessError


class ControlledDiagnosticCore(ControlledCore):
    """Return an authored bug plan while preserving observable task cancellation behavior."""

    async def complete(self, **options):
        """Resolve the known fixture return line without running the source function or proposed steps."""
        self.calls.append(options)
        self.entered.set()
        try:
            if self.block:
                await self.release.wait()
            lines = json.loads(options["messages"][1]["content"])["sources"]
            line = next(row for row in lines if "return value + 1" in row["text"])
            return CompletionResult(
                json.dumps(proposed_diagnosis(line["source_id"])),
                "controlled-core",
                "fast",
                "stop",
            )
        finally:
            self.exited.set()


@pytest.fixture
def diagnosis_service(source_workspace):
    """Create a disposable arithmetic source and actual workspace service without executing that source."""
    catalog, _, root, _ = source_workspace
    (root / "calc.py").write_text(
        '"""Arithmetic fixture."""\ndef double(value):\n    return value + 1\n'
    )
    return WorkspaceDiagnosisService(
        WorkspaceService(catalog), inference=ControlledDiagnosticCore()
    )


def diagnostic_request(service, spec):
    """Create one source-selected request whose actual symptom is supplied, not measured by this service."""
    return service.operation(
        spec.owner_id,
        spec.workspace_id,
        "double(3) returned4, expected6",
        [dict(path="calc.py")],
    )


@pytest.mark.asyncio
async def test_native_diagnosis_does_not_modify_or_execute_sources(
    diagnosis_service, source_workspace
):
    """Verify exact native bug citation, concrete manual plan and unchanged raw source bytes."""
    _, spec, root, _ = source_workspace
    before = (root / "calc.py").read_bytes()
    names = sorted(p.name for p in root.iterdir())
    async with diagnostic_request(diagnosis_service, spec) as evidence:
        assert evidence.payload["status"] == "diagnosed"
        assert evidence.payload["execution_status"] == "not_executed"
        citation = evidence.payload["citations"][0]
        assert citation["path"] == "calc.py" and citation["line_number"] == 3
        assert citation["source_sha256"] == hashlib.sha256(before).hexdigest()
        assert citation["quote"] == "return value + 1"
        await diagnosis_service.validate(evidence)
    assert (root / "calc.py").read_bytes() == before
    assert sorted(p.name for p in root.iterdir()) == names
    assert (
        not diagnosis_service.operations and not diagnosis_service.workspace.operations
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["mutate", "cancel", "shutdown"])
async def test_inherited_diagnostic_source_fence_and_join(
    diagnosis_service, source_workspace, action
):
    """Exercise actual root/source ownership during controlled model delay without duplicating D36 lifecycle logic."""
    _, spec, root, _ = source_workspace
    diagnosis_service.inference.block = True

    async def operation():
        """Hold one native source-selected diagnostic in its model-delay phase."""
        async with diagnostic_request(diagnosis_service, spec):
            pytest.fail("fenced/cancelled diagnosis delivered")

    task = asyncio.create_task(operation())
    await asyncio.wait_for(diagnosis_service.inference.entered.wait(), 2)
    if action == "mutate":
        (root / "calc.py").write_text("changed\n")
        diagnosis_service.inference.release.set()
    elif action == "shutdown":
        await diagnosis_service.shutdown()
    else:
        task.cancel()
    with pytest.raises(
        WorkspaceAccessError if action == "mutate" else asyncio.CancelledError
    ):
        await task
    assert diagnosis_service.inference.exited.is_set()
    assert not diagnosis_service.operations and not diagnosis_service.admission.locked()


@pytest.mark.asyncio
async def test_blank_diagnostic_sources_use_specialized_shape(
    diagnosis_service, source_workspace
):
    """Return a diagnostic no-source response without explanation fields or an inference call."""
    (source_workspace[2] / "calc.py").write_text(" \n")
    async with diagnostic_request(diagnosis_service, source_workspace[1]) as evidence:
        assert evidence.payload["status"] == "no_sources"
        assert (
            evidence.payload["diagnosis"] is None
            and evidence.payload["execution_status"] == "not_executed"
        )
        assert "answer" not in evidence.payload
    assert not diagnosis_service.inference.calls
