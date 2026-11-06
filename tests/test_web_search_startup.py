"""Verify default-off inert search initialization and joined cleanup on later application startup failures."""

import pytest

from apps.api.storage.web_search import initialize_web_search_service


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [None, "0", "true", "yes"])
async def test_default_off_does_not_construct_provider_or_inference(flag, monkeypatch):
    """Require the exact operator flag without reading a credential or constructing a network dependency."""
    from apps.api.storage import web_search

    if flag is None:
        monkeypatch.delenv("ASSISTANT_WEB_SEARCH_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ASSISTANT_WEB_SEARCH_ENABLED", flag)

    def forbidden(*args, **kwargs):
        """Fail if disabled startup attempts any optional dependency construction."""
        raise AssertionError("dependency_constructed")

    monkeypatch.setattr(web_search, "SearxNGSearchAdapter", forbidden)
    monkeypatch.setattr(web_search, "LlamaInferenceAdapter", forbidden)
    assert await initialize_web_search_service() is None


@pytest.mark.asyncio
async def test_enabled_initializer_is_inert_and_uses_only_selected_fixed_dependencies(
    monkeypatch,
):
    """Construct the owned-instance/original-CORE pipeline without making a request, loading a model or using a workspace."""
    import httpx

    monkeypatch.setenv("ASSISTANT_WEB_SEARCH_ENABLED", "1")

    def forbidden(*args, **kwargs):
        """Reject any accidental client construction during service initialization."""
        raise AssertionError("network_at_startup")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    current = await initialize_web_search_service()
    assert (
        current.pipeline.provider_id == "searxng"
        and current.quota.total == 0
        and not current.operations
    )
    await current.shutdown()


def test_later_startup_failure_drains_actual_search_service(monkeypatch):
    """Close the real optional service when a later workspace initializer fails before lifespan yields."""
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.storage import lifecycle

    monkeypatch.setenv("ASSISTANT_WEB_SEARCH_ENABLED", "1")
    created = []
    original = lifecycle.initialize_web_search_service

    async def tracked():
        """Retain the actual initialized service to verify its cleanup state after failure."""
        result = await original()
        created.append(result)
        return result

    async def fail_workspace():
        """Raise a later controlled startup fault without touching a real workspace or database."""
        raise RuntimeError("controlled-later-startup")

    monkeypatch.setattr(lifecycle, "initialize_web_search_service", tracked)
    monkeypatch.setattr(lifecycle, "initialize_workspace_service", fail_workspace)
    with pytest.raises(RuntimeError, match="controlled-later-startup"):
        with TestClient(app):
            pytest.fail("failed startup yielded")
    assert len(created) == 1 and created[0].closing and not created[0].operations
    assert app.state.web_search_service is None
