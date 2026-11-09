"""Verify default-off composition, startup refusals, local/bearer access, owner scoping and content-free audit logs."""

import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient
from grounded_extract_cases import (
    ANSWERS,
    LABEL_QUOTE,
    LABEL_TEXT,
    LABEL_VALUE,
    PORT_QUOTE,
    PORT_TEXT,
    QUERY,
    Native,
    body_for,
    extract_app,
    plain_hit,
    record_adapters,
)

from apps.api.grounded_extract import compose, create_app

PATH = "/api/v1/grounded/extract"
FLAG = "ASSISTANT_GROUNDED_EXTRACT_ENABLED"
PREREQUISITES = dict(
    DATABASE_URL="postgresql+asyncpg://neutral.invalid/fixture",
    ASSISTANT_FILES_ENABLED="1",
    ASSISTANT_INGESTION_ENABLED="1",
    ASSISTANT_INGESTION_CONFIG_FILE="/nonexistent/neutral-ingestion.json",
    ASSISTANT_RETRIEVAL_ENABLED="1",
    ASSISTANT_GROUNDED_ENABLED="1",
    ASSISTANT_AUTH_FILE="/nonexistent/neutral-auth.json",
)
AUDIT_LOGGERS = {
    "apps.api.grounded_extract",
    "apps.api.routes.grounded_extract",
    "apps.api.routes.retrieval",
    "apps.api.services.grounded",
    "src.application.services.file_storage_policy",
    "src.application.services.grounded_answer",
    "src.infrastructure.inference.structured_excerpt_adapter",
}


def configure(monkeypatch, **changes):
    """Set a complete static enabled environment, then apply deletions (None) or overrides."""
    monkeypatch.setenv(FLAG, "1")
    monkeypatch.delenv("ASSISTANT_VOICE_ENABLED", raising=False)
    for name, value in dict(PREREQUISITES, **changes).items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def local(app):
    """Open a loopback test client that runs the composed lifespan."""
    return TestClient(app, client=("127.0.0.1", 43000))


@pytest.mark.parametrize("value", [None, "0"])
def test_default_off_returns_the_exact_main_app_and_openapi(monkeypatch, caplog, value):
    """Return the same main app object, routes and OpenAPI without the extract path."""
    from apps.api.main import app

    caplog.set_level(logging.INFO)
    routes = list(app.router.routes)
    before = app.openapi()
    if value is None:
        monkeypatch.delenv(FLAG, raising=False)
    else:
        monkeypatch.setenv(FLAG, value)
    monkeypatch.setenv("ASSISTANT_VOICE_ENABLED", "1")
    assert create_app() is app
    assert app.openapi() == before and list(app.router.routes) == routes
    assert PATH not in app.openapi()["paths"]
    assert "grounded_extract_disabled" in caplog.text
    assert "grounded_extract_composed" not in caplog.text


def test_enabled_composition_is_additive_and_leaves_main_untouched(monkeypatch, caplog):
    """Build a new app whose OpenAPI equals main plus exactly the extract operation."""
    from apps.api.main import app as base

    caplog.set_level(logging.INFO)
    configure(monkeypatch)
    routes = list(base.router.routes)
    original = base.openapi()
    app = create_app()
    assert app is not base and "grounded_extract_composed" in caplog.text
    enabled = app.openapi()["paths"]
    assert set(enabled) == set(original["paths"]) | {PATH}
    for path, methods in original["paths"].items():
        assert enabled[path] == methods
    assert set(enabled[PATH]) == {"post"}
    assert base.openapi() == original and list(base.router.routes) == routes
    fresh = get_openapi(title=base.title, version=base.version, routes=base.routes)
    assert PATH not in fresh["paths"]
    assert (app.title, app.version, app.docs_url, app.redoc_url) == (
        base.title,
        base.version,
        base.docs_url,
        base.redoc_url,
    )


@pytest.mark.parametrize(
    "value", ["", "true", "TRUE", "01", " 1", "1 ", "2", "yes", "on", "0 "]
)
def test_invalid_flag_values_are_refused(monkeypatch, value):
    """Refuse any flag spelling other than exactly 0 or 1."""
    configure(monkeypatch)
    monkeypatch.setenv(FLAG, value)
    with pytest.raises(RuntimeError, match="grounded_extract_flag_invalid"):
        create_app()


@pytest.mark.parametrize("voice", ["1", "true", ""])
def test_voice_combination_is_refused(monkeypatch, voice):
    """Refuse the unsupported combined voice and extraction composition."""
    configure(monkeypatch)
    monkeypatch.setenv("ASSISTANT_VOICE_ENABLED", voice)
    with pytest.raises(RuntimeError, match="grounded_extract_voice_unsupported"):
        create_app()


@pytest.mark.parametrize(
    "change",
    [
        *({name: None} for name in PREREQUISITES),
        *({name: ""} for name in PREREQUISITES),
        *(
            {name: value}
            for name in PREREQUISITES
            if name.endswith("_ENABLED")
            for value in ("0", "true", " 1")
        ),
    ],
)
def test_missing_prerequisites_are_refused(monkeypatch, change):
    """Require the whole files/ingestion/retrieval/grounded/auth chain without reading any values."""
    configure(monkeypatch, **change)
    with pytest.raises(RuntimeError, match="grounded_extract_prerequisites_required"):
        create_app()


def test_lifespan_refuses_without_live_grounded_retrieval(monkeypatch):
    """Fail startup when the unchanged base lifespan creates no retrieval/grounded services."""
    from apps.api.main import app as base

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(
        RuntimeError, match="grounded_extract_requires_grounded_retrieval"
    ):
        with local(compose(base)):
            pass


@pytest.mark.parametrize("fault", ["closing", "unlinked", "retrieval_missing"])
def test_lifespan_refuses_closing_or_unlinked_services(fault):
    """Require live grounded service bound to the same live retrieval service."""
    retrieval = SimpleNamespace(closing=False)
    grounded = SimpleNamespace(closing=fault == "closing", retrieval=retrieval)
    if fault == "unlinked":
        grounded.retrieval = SimpleNamespace(closing=False)

    @asynccontextmanager
    async def lifespan(app):
        """Expose controlled service state without any database or model."""
        app.state.retrieval_service = (
            None if fault == "retrieval_missing" else retrieval
        )
        app.state.grounded_service = grounded
        yield

    with pytest.raises(
        RuntimeError, match="grounded_extract_requires_grounded_retrieval"
    ):
        with local(compose(FastAPI(lifespan=lifespan))):
            pass


def test_local_and_bearer_rules_apply_before_the_body(auth_settings):
    """Require loopback, no Origin or proxy headers, and a valid bearer before any source access."""
    principal = auth_settings["principals"][0]
    port = plain_hit(PORT_TEXT)
    native = Native()
    app, dense, service = extract_app([(principal, port)], native)
    body = body_for(("port", "integer", port))
    headers = auth_settings["headers"][0]
    with local(app) as client:
        assert client.post(PATH, json=body).status_code == 401
        assert (
            client.post(
                PATH, json=body, headers={"Authorization": "Bearer " + "x" * 48}
            ).status_code
            == 401
        )
        for extra in (
            {"Origin": "http://example.invalid"},
            {"X-Forwarded-For": "192.0.2.1"},
            {"Forwarded": "for=192.0.2.1"},
            {"X-Real-IP": "192.0.2.1"},
        ):
            response = client.post(PATH, json=body, headers={**headers, **extra})
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == "local_access_required"
    remote, remote_dense, _ = extract_app([(principal, port)], native)
    with TestClient(remote, client=("192.0.2.1", 43000)) as client:
        assert client.post(PATH, json=body, headers=headers).status_code == 403
    assert native.calls == 0 and dense.options is None
    assert remote_dense.options is None


def test_disabled_service_returns_grounded_unavailable(auth_settings):
    """Return 503 grounded_unavailable when the grounded service is absent or closing."""
    principal = auth_settings["principals"][0]
    port = plain_hit(PORT_TEXT)
    app, dense, service = extract_app([(principal, port)], Native())
    with local(app) as client:
        service.closing = True
        response = client.post(
            PATH,
            json=body_for(("port", "integer", port)),
            headers=auth_settings["headers"][0],
        )
        assert response.status_code == 503
        assert response.json() == {"detail": {"code": "grounded_unavailable"}}
        service.closing = False
        app.state.grounded_service = None
        response = client.post(
            PATH,
            content=b"{",
            headers={**auth_settings["headers"][0], "Content-Type": "application/json"},
        )
        assert response.json() == {"detail": {"code": "grounded_unavailable"}}
        app.state.grounded_service = service
    assert dense.options is None


def test_authenticated_extraction_over_http(auth_settings, monkeypatch):
    """Deliver exact typed facts and citations with private no-store headers for the bearer principal."""
    built = record_adapters(monkeypatch)
    principal = auth_settings["principals"][0]
    port, label = plain_hit(PORT_TEXT), plain_hit(LABEL_TEXT)
    native = Native()
    app, dense, service = extract_app([(principal, port), (principal, label)], native)
    with local(app) as client:
        response = client.post(
            PATH,
            json=body_for(("port", "integer", port), ("label", "string", label)),
            headers=auth_settings["headers"][0],
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    data = response.json()
    assert set(data) == {
        "status",
        "facts",
        "citations",
        "answer_trust",
        "content_trust",
        "extraction",
    }
    assert data["status"] == "extracted"
    assert data["facts"] == dict(port=7443, label=LABEL_VALUE)
    assert [row["quote"] for row in data["citations"]] == [PORT_QUOTE, LABEL_QUOTE]
    assert dense.owners == [principal]
    assert dense.options == dict(
        top_k=2, file_ids=[UUID(port["file_id"]), UUID(label["file_id"])]
    )
    assert len(built) == 1 and built[0].calls == 1 and len(native.generations) == 1
    assert not dense.held and not service.admission.locked() and not service.operations


def test_delivery_fence_over_http(auth_settings):
    """Return 409 retrieval_source_changed when the source changes after inference but before headers."""
    principal = auth_settings["principals"][0]
    port = plain_hit(PORT_TEXT)
    native = Native()
    app, dense, service = extract_app([(principal, port)], native, change_at=3)
    with local(app) as client:
        response = client.post(
            PATH,
            json=body_for(("port", "integer", port)),
            headers=auth_settings["headers"][0],
        )
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "retrieval_source_changed"}}
    assert PORT_QUOTE not in response.text and "7443" not in response.text
    assert dense.validations == 3 and len(native.generations) == 1
    assert not dense.held and not service.admission.locked()


def test_foreign_file_ids_match_nothing_under_owner_scoping(auth_settings, monkeypatch):
    """Give no_sources for another principal's files and extract_source_mismatch when only some resolve."""
    built = record_adapters(monkeypatch)
    own, other = auth_settings["principals"]
    port, label = plain_hit(PORT_TEXT), plain_hit(LABEL_TEXT)
    native = Native()
    app, dense, service = extract_app([(other, port), (own, label)], native)
    headers = auth_settings["headers"][0]
    with local(app) as client:
        foreign = client.post(
            PATH, json=body_for(("port", "integer", port)), headers=headers
        )
        mixed = client.post(
            PATH,
            json=body_for(("port", "integer", port), ("label", "string", label)),
            headers=headers,
        )
    assert foreign.status_code == 200
    assert foreign.json() == dict(
        status="no_sources",
        facts=None,
        citations=[],
        answer_trust="model_generated",
        content_trust="untrusted",
        extraction=None,
    )
    assert mixed.status_code == 422
    assert mixed.json() == {"detail": {"code": "extract_source_mismatch"}}
    assert dense.owners == [own, own]
    assert native.calls == 0 and not built


@pytest.mark.parametrize("mode", ["extracted", "refusal", "malformed", "mismatch"])
def test_audit_records_contain_no_content(auth_settings, monkeypatch, caplog, mode):
    """Scan every record: no query, names, values, quotes, text, file/chunk IDs or digests anywhere.

    The only exception is the pre-existing shared bearer event
    conversation_principal_authenticated, which logs the principal ID for every
    authenticated route, /grounded/answer included.
    """
    caplog.set_level(logging.INFO)
    built = record_adapters(monkeypatch)
    principal = auth_settings["principals"][0]
    port, label = plain_hit(PORT_TEXT), plain_hit(LABEL_TEXT)
    native = Native(
        dict(port_marker_name=ANSWERS["port"], label_marker_name=ANSWERS["label"]),
        refusal=mode == "refusal",
        fault="malformed" if mode == "malformed" else None,
    )
    rows = (
        [(principal, port)]
        if mode == "mismatch"
        else [(principal, port), (principal, label)]
    )
    app, dense, service = extract_app(rows, native)
    with local(app) as client:
        response = client.post(
            PATH,
            json=body_for(
                ("port_marker_name", "integer", port),
                ("label_marker_name", "string", label),
            ),
            headers=auth_settings["headers"][0],
        )
    expected = dict(extracted=200, refusal=200, malformed=503, mismatch=422)[mode]
    assert response.status_code == expected
    records = [row.getMessage() for row in caplog.records]
    events = " ".join(records)
    inherited = [
        row
        for row in caplog.records
        if row.name == "apps.api.core.conversation_auth"
        and row.getMessage().startswith("conversation_principal_authenticated ")
    ]
    assert len(inherited) == 1
    assert inherited[0].getMessage() == (
        "conversation_principal_authenticated principal_id=" + str(principal)
    )
    owned = [row for row in caplog.records if row.name in AUDIT_LOGGERS]
    assert owned and all(str(principal) not in row.getMessage() for row in owned)
    assert sum(str(principal) in message for message in records) == 1
    secrets = [
        QUERY,
        "PRIVATE-QUERY-MARKER",
        "port_marker_name",
        "label_marker_name",
        "7443",
        LABEL_VALUE,
        PORT_QUOTE,
        LABEL_QUOTE,
        PORT_TEXT,
        LABEL_TEXT,
        "PRIVATE-MODEL-MARKER",
        port["file_id"],
        label["file_id"],
        port["chunk_id"],
        label["chunk_id"],
        port["source_sha256"],
        label["source_sha256"],
        port["generation"],
        label["generation"],
        auth_settings["tokens"][0],
    ]
    if built and built[0].provenance is not None:
        secrets += [
            built[0].provenance.prompt_sha256,
            built[0].provenance.schema_sha256,
            built[0].provenance.content_sha256,
        ]
    if mode == "extracted":
        data = response.json()
        secrets += [
            data["extraction"]["prompt_sha256"],
            data["extraction"]["schema_sha256"],
        ]
    for secret in secrets:
        assert secret not in events
    assert "grounded_operation_closed" in events
    if mode == "extracted":
        assert "grounded_extract_admitted fields=2" in events
        assert "grounded_extract_published fields=2 citations=2" in events
    elif mode == "refusal":
        assert "grounded_extract_insufficient_evidence" in events
    elif mode == "malformed":
        assert "grounded_extract_failed code=extract_model_unavailable" in events
    else:
        assert "grounded_extract_source_refused code=extract_source_mismatch" in events
        assert "grounded_extract_failed code=extract_source_mismatch" in events
