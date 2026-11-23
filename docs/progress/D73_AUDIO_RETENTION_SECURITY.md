# D73 — Ephemeral audio retention, delete and capture security

**Purpose:** Document verified local audio deletion and access boundaries without claiming secure erasure or deleting retained research artifacts.

**Status:** PASS local capture/ephemeral-service scope. [ADR114](../ADR/114-ephemeral-recording-retention-and-delete.md) adds only the required preview-lifetime control to D71; production voice activation remains gated as recorded at D72.

## Product behavior

- Capture requires a fresh visible start action; no on-load/background/automatic retry recording. Active audio is capped at30seconds/480000samples.
- Stop releases tracks before encoding a local preview. A ready preview expires after300000milliseconds in an active page. Expiry clears application Blob references, revokes the object URL and leaves capture inactive.
- Explicit cancel/delete, replacement, Escape, hiding or exiting the page deletes earlier. Permission cancellation stops a later acquired device. Both capture and preview timers are retired; the preview callback is bound to its generation so stale callbacks cannot delete a newer capture.
- No product audio upload/write endpoint, persistent browser store, auto-download or server audio database. Static files are no-store; remote peer/Host/origin/proxy access and write methods are denied. Logs retain lifecycle/error codes, not signal/transcript bodies.
- D72's returned value is explicitly caller-owned ephemeral PCM; the service retains no completed-operation registry. This does not promise deletion of a downstream caller's copies. Browser/OS scheduling and buffers are outside secure-erasure guarantees; a suspended process can defer JavaScript timers. Hidden-page cleanup is a separate early-delete path.

Original D70 audio, private benchmark outputs, failed experiments and audit packets remain **intentionally retained research evidence**. D73 does not clean or overwrite them. No source collection/database/Vault/Docker/model/default changes.

## Actual validation

**271related Python tests PASS7.08s/0FAIL/0SKIP**; includes the Node wrapper. **13Node controls PASS**, not13additional independent Python cases. New controls cover ready-preview expiry, explicit replacement/discard, stale expiry callbacks, no new device request on expiry, four denied HTTP write methods and body redaction. Previous recording/source/owner/clock/cancellation/inference-adapter tests still pass. Ruff/diff checks PASS.

Real Brave154.0.8037.58 with a fake microphone verifies4acquisitions all end, valid mono16k WAV, forced preview-expiry cleanup, Escape/hidden and late-permission cleanup, no upload/external requests, empty localStorage/sessionStorage/IndexedDB and no page errors. Expiry was triggered through an injected test timer callback; this is **not five minutes wall-time waiting or physical microphone verification**. Temporary test browser/UI processes were stopped. [Acceptance/source/log receipts](../evidence/d73-audio-retention-acceptance.json).

Only the new D71 recorder/UI and their tests changed for this necessary retention feature; existing661source/917protected files/176inputs and original24pending review labels are unchanged. Earlier D71/D72 receipts retain their historical source hashes; they are not rewritten as tests of this later revision.

## User check and next gate

Use the [D71 run command](D71_EXPLICIT_RECORDING.md), stop a short recording and leave the page active for five minutes; verify the preview disappears and microphone remains inactive. Repeat with explicit cancel and tab hiding. The agent has not used your physical microphone. D74 must combine existing multimodal/resource evidence with remaining manual/model/license/activation gates; this privacy milestone does not approve TTS naturalness or final production voice use.
