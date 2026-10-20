"""Verify explicit default-off explanation startup and ordered lifecycle without model loading or database setup."""

import pytest
from test_workspace_reader import source_workspace as source_workspace
from test_workspace_startup import workspace_config as workspace_config

from apps.api.services.workspaces import WorkspaceService
from apps.api.storage.workspace_explanations import initialize_workspace_explanations


@pytest.mark.asyncio
async def test_default_off_explanations_need_no_workspace(monkeypatch):
    """Return no optional service unless the operator explicitly enables source explanations."""
    monkeypatch.delenv("ASSISTANT_WORKSPACE_EXPLAIN_ENABLED", raising=False)
    assert await initialize_workspace_explanations(None) is None


@pytest.mark.asyncio
async def test_enabled_explanations_require_live_workspace(
    source_workspace, monkeypatch
):
    """Refuse missing/draining workspace dependencies and initialize only an inert existing inference adapter."""
    monkeypatch.setenv("ASSISTANT_WORKSPACE_EXPLAIN_ENABLED", "1")
    with pytest.raises(RuntimeError):
        await initialize_workspace_explanations(None)
    workspace = WorkspaceService(source_workspace[0])
    service = await initialize_workspace_explanations(workspace)
    assert service.workspace is workspace and not service.operations
    await service.shutdown()
    await workspace.shutdown()
    with pytest.raises(RuntimeError):
        await initialize_workspace_explanations(workspace)


def test_later_startup_failure_drains_explanation_before_workspace(
    workspace_config, monkeypatch
):
    """Fail a later existing resource and prove both actual optional services drain in dependency order."""
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.storage import lifecycle

    monkeypatch.setenv("ASSISTANT_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_WORKSPACE_CONFIG_FILE", str(workspace_config[0]))
    monkeypatch.setenv("ASSISTANT_WORKSPACE_EXPLAIN_ENABLED", "1")
    monkeypatch.setenv("DATABASE_URL", "controlled-unavailable-url")
    events = []
    original_workspace = lifecycle.initialize_workspace_service
    original_explanation = lifecycle.initialize_workspace_explanations

    async def tracked_workspace():
        """Initialize the actual explicit catalog and observe its existing shutdown without replacing cleanup."""
        service = await original_workspace()
        original = service.shutdown

        async def shutdown():
            """Record ordered real workspace teardown."""
            events.append("workspace")
            await original()

        monkeypatch.setattr(service, "shutdown", shutdown)
        return service

    async def tracked_explanation(workspace):
        """Initialize the actual optional explainer and observe its real dependency-ordered shutdown."""
        service = await original_explanation(workspace)
        original = service.shutdown

        async def shutdown():
            """Record ordered real explanation teardown."""
            events.append("explanation")
            await original()

        monkeypatch.setattr(service, "shutdown", shutdown)
        return service

    def fail_engine():
        """Inject a later controlled engine failure without database or credential access."""
        raise RuntimeError("CONTROLLED-PRIVATE-ENGINE-ERROR")

    monkeypatch.setattr(lifecycle, "initialize_workspace_service", tracked_workspace)
    monkeypatch.setattr(
        lifecycle, "initialize_workspace_explanations", tracked_explanation
    )
    monkeypatch.setattr(lifecycle, "create_database_engine", fail_engine)
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pytest.fail("failed startup yielded")
    assert events == ["explanation", "workspace"]
    assert (
        app.state.workspace_explanation_service is None
        and app.state.workspace_service is None
    )
