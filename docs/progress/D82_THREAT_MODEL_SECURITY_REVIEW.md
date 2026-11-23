# D82 — Local threat model and security controls

**Purpose:** State local trust boundaries, the verified stateless access fix and remaining deployment limits.

**Status:** Local negative controls VERIFIED; production exposure/release acceptance is not granted. [ADR121](../ADR/121-authenticated-bounded-stateless-inference.md).

| Boundary / actor | Authority | Verified control |
|---|---|---|
| Unauthenticated browser/remote peer | None | Direct loopback only; all Origin/proxy headers rejected; no permissive CORS |
| Local bearer principal | Own resources only | Private digest file, constant-time comparisons, duplicate header denial and immediate reload/revocation |
| Source/README/web/model/MCP output | Untrusted data | Typed tools, source bindings; cannot set owner/profile/approvals or execute callbacks |
| CORE host harness | Finite allowlist | D75–D79 scopes, budgets, current authorization and original one-shot actions |
| UNRESTRICTED text profile | Text only | No harness/tool/approval path; no fallback/model activation |
| Checkpoint/history | Metadata, not consent | Signed latest chain, no recovered action grant, uncertain writes not retried |
| Operator/backend loopback8080 | Trusted local deployment | Not a public API; no auth/TLS certification for exposing the native backend |

The legacy stateless chat route was the concrete access exception: missing credentials and cross-origin calls could reach the model gateway, and raw backend/config exception text was returned. Red test reproduced it. The route now applies existing local/principal helpers **before body parsing**, accepts only JSON bounded262144stream bytes independently of Content-Length, preserves authenticated original profile/preset/message/gateway response semantics and emits private/no-store/nosniff headers. Errors expose finite codes rather than private diagnostics. No persistence/tools/approval authority or model settings change.

**19new/174related PASS13.07s/0FAIL/0SKIP**, including actual disposable Uvicorn/TCP missing bearer/origin denial, successful original response and immediate credential revocation before another gateway call. Also malformed/oversized/media/duplicate credentials/config faults/remote peers and redaction, existing conversation compatibility/ownership and injection-authority controls. Existing owner/resource suites remain authoritative for their specific domains; this is not an independent external penetration test.

Necessary passed-source exception: only apps/api/routes/chat.py changed under ADR121. All other660original source files,917protected files and176original inputs unchanged. Tests used private temporary auth files/fixture gateway, no production restart/config/token/Vault/database/model change. [Source/before-after/log receipt](../evidence/d82-security-verification.json).

Stateless API callers must now send the same bearer credential as resource endpoints, read from the protected operator configuration; never put it in URLs or browser persistent storage. Missing config503, invalid/revoked credential401, external Origin/proxy/non-loopback403. Existing local API remains direct-only; a future browser gateway/reverse proxy/OIDC/TLS/multiworker or scoped Vault bootstrap needs its own reviewed design. Disable stateless access rather than restoring an unauthenticated rollback.

D70 manual listening, D74 product/model/license/no-speech gates and D81 strict quote-format issue remain open. D83 observability proceeds independently; no zero-critical release declaration is made here.
