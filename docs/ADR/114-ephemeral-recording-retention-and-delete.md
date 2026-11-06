# ADR 114 — Ephemeral recording retention and explicit delete

**Purpose:** Bound local recording preview lifetime and verify deletion/security without introducing server audio storage or deleting research evidence.

**Date:** 2026-10-23. **Status:** Accepted for D73 implementation after local D71/D72 acceptance.

## Decision

The optional D71 surface keeps a completed preview for at most five minutes in an active page, then revokes its object URL, clears Blob references and returns to an inactive state. Explicit delete/cancel, replacement, Escape, hidden page and page exit delete earlier. Timer expiry never starts or resumes capture. The active capture budget remains30seconds with no automatic acquisition/retry. Cancellation of an outstanding browser permission request remains generation-bound; late devices are stopped.

Use a separate preview-expiry timer from the capture/permission deadline. Clear it on every discard and before replacement so it cannot cancel a newer recording. Retain only finite lifecycle events in logs. No localStorage/IndexedDB/cache/service-worker audio, auto-download, upload endpoint or server audio database exists. The read-only surface retains no user audio; it continues to reject remote hosts/origins/proxy headers and all write methods.

Five minutes is the active-page application timer limit, not a secure erasure or universal OS/browser scheduling guarantee. Hidden-page cleanup runs independently; a suspended/crashed browser may defer JavaScript. Audio/OS-managed buffers and explicit downstream caller-owned return values are not claimed to be securely erased. Private benchmark artifacts and original D70 pending files are deliberately retained research evidence, not user recording retention targets.

## Priority, dependencies, validation and rollback

Existing D73/P1, one implementation/security validation milestone. Dependencies: accepted explicit recording lifecycle, object-URL cleanup and native browser tests; no model or database dependency. Risks: stale timers delete a new recording, a preview survives cancellation, a user mistakes remembered microphone permission for active recording, and test evidence is accidentally deleted as product audio. Extend only the necessary new D71 recorder/test files; preserve earlier passed source elsewhere.

Verify explicit/TTL deletion, stale timer cancellation, no on-load acquisition, track release, empty storage, no upload, finite redacted logs and cross-origin/Host/write denials. Native browser uses a fake microphone and controlled expiry trigger; do not represent that as five minutes of wall time or a physical-device check. Rollback retires the preview-expiry addition while retaining all first evidence; no production/model/database migration or cleanup of historical audio.
