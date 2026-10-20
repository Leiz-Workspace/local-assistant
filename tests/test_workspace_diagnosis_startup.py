"""Verify default-off diagnosis startup requires workspace capability and never starts models or commands."""

import pytest
from test_workspace_reader import source_workspace as source_workspace
from test_workspace_startup import workspace_config as workspace_config

from apps.api.services.workspaces import WorkspaceService
from apps.api.storage.workspace_diagnoses import initialize_workspace_diagnoses


@pytest.mark.asyncio
async def test_default_off_diagnosis_is_inert(monkeypatch):
    """Initialize no optional service or dependency unless diagnosis is explicitly enabled."""
    monkeypatch.delenv("ASSISTANT_WORKSPACE_DIAGNOSE_ENABLED", raising=False)
    assert await initialize_workspace_diagnoses(None) is None


@pytest.mark.asyncio
async def test_enabled_diagnosis_requires_live_workspace(source_workspace, monkeypatch):
    """Bind the existing capability only and reject missing/draining dependencies without model loading."""
    monkeypatch.setenv("ASSISTANT_WORKSPACE_DIAGNOSE_ENABLED", "1")
    with pytest.raises(RuntimeError):
        await initialize_workspace_diagnoses(None)
    workspace = WorkspaceService(source_workspace[0])
    service = await initialize_workspace_diagnoses(workspace)
    assert service.workspace is workspace and not service.operations
    await service.shutdown()
    await workspace.shutdown()
    with pytest.raises(RuntimeError):
        await initialize_workspace_diagnoses(workspace)


def test_actual_later_startup_failure_drains_all_workspace_dependents(
    workspace_config, monkeypatch
):
    """Prove real diagnosis/explanation/workspace services close in dependency order after later startup failure."""
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.storage import lifecycle

    monkeypatch.setenv("ASSISTANT_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_WORKSPACE_CONFIG_FILE", str(workspace_config[0]))
    monkeypatch.setenv("ASSISTANT_WORKSPACE_EXPLAIN_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_WORKSPACE_DIAGNOSE_ENABLED", "1")
    monkeypatch.setenv("DATABASE_URL", "controlled-unavailable-url")
    events = []

    def tracked_initializer(original, name):
        """Wrap an actual initializer only to observe its actual shutdown without replacing resource cleanup."""

        async def initialize(*arguments):
            """Create the real inert service and preserve its original dependency teardown."""
            service = await original(*arguments)
            shutdown = service.shutdown

            async def close():
                """Record ordered real cleanup and join the original service teardown."""
                events.append(name)
                await shutdown()

            monkeypatch.setattr(service, "shutdown", close)
            return service

        return initialize

    for attribute, name in [
        ("initialize_workspace_service", "workspace"),
        ("initialize_workspace_explanations", "explanation"),
        ("initialize_workspace_diagnoses", "diagnosis"),
    ]:
        monkeypatch.setattr(
            lifecycle,
            attribute,
            tracked_initializer(getattr(lifecycle, attribute), name),
        )

    def fail_engine():
        """Fail only the later engine constructor without contacting a database or credential service."""
        raise RuntimeError("CONTROLLED-PRIVATE-ENGINE-ERROR")

    monkeypatch.setattr(lifecycle, "create_database_engine", fail_engine)
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pytest.fail("failed startup yielded")
    assert events == ["diagnosis", "explanation", "workspace"]
    assert app.state.workspace_diagnosis_service is None
    assert (
        app.state.workspace_explanation_service is None
        and app.state.workspace_service is None
    )
