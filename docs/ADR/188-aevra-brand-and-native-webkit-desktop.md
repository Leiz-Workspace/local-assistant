# ADR-188: Aevra identity and independent native WebKit desktop

**Purpose:** Record the owner-requested Aevra identity and replace the browser app-window desktop with a native application while reusing the pinned chat UI.

**Date:** 2026-11-11. **Status:** Accepted by the owner's explicit request; Linux implementation verified within the documented scope. Supersedes only the Brave/Chromium desktop-launch choice in ADR-181. Model, API authority, context, skill and memory decisions remain unchanged.

## Context

The owner selected the product name **Aevra**, supplied the white dragon in `aevra-logo-assets/aevra-dragon-white.svg` and requested an independent desktop rather than opening Brave/Chromium. Existing web and desktop shared pinned llama.cpp UI resources; desktop previously invoked an external browser with `--app`.

## Decision

1. Use `aevra` as the primary uv console command and Python distribution name. Retain `la` as a compatibility alias and expose `aevra-desktop`. Do not migrate existing credentials, database/schema identifiers, model aliases or old benchmark artifacts merely for branding.
2. Copy the owner's original white SVG/PNG byte-for-byte into packaged branding resources. Record source/resource hashes; generate transparent favicon/native icons without borders or added backgrounds, following the owner’s correction. CLI renders the same dragon as portable ASCII in interactive chat or `aevra logo`; `--json logo` returns exact SVG metadata. No emoji or new generated logo.
3. Keep all seventy pinned llama-ui files intact. At response time, apply Aevra title/favicon/manifest metadata and owned CSS/JavaScript to product chrome. Replace the sidebar logo visually without rewriting conversation messages or modifying the upstream bundle. Keep upstream licensing resources and the existing authenticated streaming gateway.
4. Implement Linux desktop as a GTK3 application window containing WebKitGTK 4.1. It is an independent GUI process, not a Brave/Chromium launch or browser fallback. Current host already has OS Python/PyGObject/GTK/WebKit. Invoke that interpreter through `uv run --offline --no-project --python /usr/bin/python3`; do not mix its GI extensions into the project's Python environment or silently install OS packages.
5. Use a native header with the verified supplied icon/name. Enable no Python/JavaScript bridge or native tool API. Allow navigation only to the configured direct-loopback origin; reject popups, downloads, file/script/foreign URLs and device permissions. Preserve WebKit's default sandbox; never use a no-sandbox workaround.
6. Retain the existing one-use pairing/cookie protocol. Pass the nonce through stdin, not argv; never pass the bearer to the renderer. Device history is separate from Brave and scoped by endpoint plus credential hash under private Aevra directories. Serialize writers with a profile lock. Server session cookies remain ephemeral; no automatic migration of existing browser conversations.
7. Reuse an authenticated Aevra backend if present. For a missing server only, verify the existing token matches the supplied private auth file, start an owned harness with short bounded readiness probes, and terminate/join only that owned process when the app closes or fails. An occupied/unauthorized/older server is not replaced. Never auto-load, stop or change the LLM or shared services. Fail closed if native dependencies/window initialization are unavailable.
8. Provide a Linux desktop launcher with the Aevra icon and no token/nonce contents. It calls the native command through uv; it is not a standalone AppImage, Windows/macOS installer or bundled Python/WebKit distribution.

## Alternatives and consequences

Keeping Brave app mode contradicts the owner's request. Electron would add another Chromium runtime; Tauri requires a Rust build toolchain and WebKit development setup absent here. Native GTK/WebKit meets the current Linux requirement using installed runtime libraries, with no new Python dependency versions or framework downloads. Cross-platform installers remain a separate delivery task.

The native window and optional managed backend have explicit lifetimes; CLI launch stays attached until the window closes. CORE remains a separately managed inference service, so a native window is not proof of model readiness. Desktop device history contains local raw chat data and must be treated as such. OS dependency availability, display access, upgrades, full desktop UX/accessibility and release packaging need separate validation; software PASS does not certify those broader gates.

## Validation

See [Aevra desktop guide](../AEVRA_DESKTOP.md) and its retained evidence. Tests cover identity/provenance, immutable upstream resources, routing/auth/CSRF, browser-script branding, native origin/profile/lock rules, nonce stdin/no browser fallback, owned backend reuse/start/failure cleanup and native initialization failure. Actual GTK/WebKit smoke loads the pinned UI, displays the white dragon/name and completes one synthetic streaming exchange; no model calls. A separate actual managed-backend start/status/stop probe verifies ownership. Native rendering initially used a focused QA window; final smoke avoids stealing the owner's keyboard focus, preserving earlier observations rather than treating them as quality trials.

## Rollback

Remove only the installed Aevra launcher if reversing desktop integration; preserve private device history for explicit owner disposition. Revert product wrapper/package identity through version control and drain owned processes. Existing `la` scripts and credential locations remain usable. Do not auto-reinstate a browser fallback, change models/data or erase historical evidence.

## Owner correction — transparent logo

2026-11-11: The owner rejected the added dark square visible around the desktop icon. Preserve the supplied alpha channel in PNG/ICO, use the original transparent SVG, remove owned branding badge/sidebar borders/backgrounds and point the installed launcher directly at the original packaged SVG. Earlier dark-backed screenshots/receipts remain historical; this does not change the native desktop architecture or model choices.

2026-11-11 cache follow-up: the owner still observed the former image after the first file-only correction. Install an immutable, hash-named transparent SVG in the user hicolor theme, reference its new theme key in future/current launchers, atomically refresh the installed desktop file and rebuild icon/desktop metadata caches. Gio/GTK resolution and actual themed64px rendering verified; no shell/session restart or favorites/theme setting change. This records renderer validation, not automated inspection of the GNOME application grid.

## Canonical application registration correction — 2026-11-11

The owner confirmed the physical Desktop shortcut was borderless, but the old Show Apps entry still rendered the dark square after SVG/cache refresh and switching to byte-identical transparent PNG. A fresh temporary PNG registration rendered correctly. Replace the old `io.aevra.Desktop` registration with canonical `io.aevra.Aevra`, and use that ID in native Gtk.Application so Wayland app/menu grouping stays aligned. Reference the immutable transparent PNG by absolute path in generated menu entries. The owner then confirmed the primary Aevra Show Apps icon is borderless; remove the temporary TEST entry and retain the retired menu entry only as private evidence.

Impact: OS application identity/association changes; endpoint/credential-scoped native history directories, tokens, API routes, model/configuration and Desktop shortcut remain intact. No registered Aevra favorite was present; unrelated favorites/layout/theme were not rewritten. Do not infer a specific internal GNOME cache bug from this controlled outcome. Source regression75PASS/0FAIL/0SKIP and native dependency/registration checks complement the actual owner visual acceptance.
