# ADR-198: Containerized Aevra web and Electron desktop

**Date:** 2026-11-25
**Status:** Accepted for implementation; Electron acceptance remains release-gated.
**Supersedes:** The primary desktop direction in ADR-188. GTK/WebKit remains rollback legacy until Electron release acceptance passes.

## Context

The product UI must be owned by Aevra rather than being a branded wrapper around the pinned llama.cpp UI. The web and desktop implementations also need one route contract, reproducible deployment, and a session flow that does not require users to copy a one-use URL fragment.

## Decision

1. Serve the standalone Aevra UI at `/` from a non-root, read-only web container. The shell assets are public static files; every data request needs the session.
2. Run the container with host networking and bind `127.0.0.1:7090`, so the existing loopback-peer checks stay meaningful and CORE is reached at `127.0.0.1:8080`. Docker port publishing is not used: it presents the bridge gateway as the peer and would require weakening those checks. The web Compose project does not load, stop or replace CORE.
3. Run the container as the owner's uid and mount the owner-only principals file read-only, so `load_principals` keeps its owner/mode checks.
4. Use a same-origin HttpOnly/SameSite session bootstrap when `ASSISTANT_WEB_AUTO_SESSION=1`, restricted to loopback and exactly one configured principal; bearer credentials never enter renderer code, URLs or storage. Browser requests without a valid cookie get 401 so the UI can recover. The pairing endpoint remains the compatibility path and the secure option on multi-account machines.
5. Use Electron as the desktop shell for the same origin. It accepts only a loopback origin, waits for `/healthz`, shows start instructions while the web is unavailable, and enforces context isolation, sandboxing, disabled Node integration, same-origin navigation and denied downloads, popups and permissions. It does not manage containers.
6. Produce a separate Electron Debian package named `aevra-desktop-electron` with artifact format `aevra-linux-amd64_v<version>-electron.deb`; retain the legacy `aevra-desktop` package identity during migration.

## Consequences

The web container requires CORE on host loopback and the owner's principals file. Auto-session trusts every local process that can reach host loopback. The owner accepted this trade-off on 2026-11-26 and keeps auto-session enabled by default; multi-account machines should set `AEVRA_WEB_AUTO_SESSION=0` and use `aevra ui open`. Electron packaging adds a locked Node dependency tree and Chromium runtime; its npm audit findings must be reviewed before a production release. GTK/WebKit code is duplicated temporarily but can be removed only after real Electron window and clean-install acceptance.

## Validation

Python harness/browser regression tests, Electron static security tests, Node syntax checks, Compose config validation, and a local Electron `.deb` build have passed. A real clean-install window smoke and inference-backed chat smoke remain release gates and must not be represented by these software tests alone.
