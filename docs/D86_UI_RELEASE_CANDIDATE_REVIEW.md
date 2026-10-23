# D86 — UI polish and engineering release review

**Purpose:** Record verified local UI improvements and explain why product release acceptance remains open.

**Status:** Existing recorder UI VERIFIED; **release gate OPEN**. No v1.0/production-ready decision.

The optional D71recording page now has a named main landmark/control group, atomic polite lifecycle announcements, described native keyboard buttons and a named audio preview. Responsive layout supports320CSSpixels without horizontal overflow,44pxminimum targets, explicit focus outline and light/dark contrast. Instructions still disclose explicit microphone permission,30second capture, no upload/recognition and5minute deletion. Only the new recorder index HTML was changed for necessary UI polish; audio state machine, server allowlist/CSP and existing API guards are unchanged.

**1new/17related controls PASS0.42s/0FAIL/0SKIP**, including13prior Node lifecycle controls through their Python wrapper. Actual Brave154fake-device keyboard Tab/Space/Tab/Enter/Escape start/stop/delete PASS; named preview/status/landmarks and320pxdark layout PASS. Screenshots visually inspected at desktop/mobile. Separate original four-stream browser stop/late-permission/hidden/expiry/no-storage regression PASS, every track ended, no page errors/external requests/uploads. Temporary browser and localhost server closed cleanly. [Source/log/browser/image receipts](evidence/d86-ui-review-verification.json).

This is not physical-microphone, auditory quality, formal screen-reader/WCAG or full product UI certification. Product harness/voice activation is still gated; no unauthenticated browser relay, bearer storage, model default or API deployment was introduced to make a demonstration look complete.

Remaining release gates: D70actual listening0/24owner-deferred; D74voice/product/no-speech/short-speech/license/model selection; D14original model scorecard reconciliation; D81strict minimal-quote format failure; D87current full regression; D88clean-install/provenance review; D89owner manual scenarios and final security review. Therefore D86does not meet “zero unresolved critical release blockers”; engineering work can continue independently under the owner's instruction, with that impact explicitly retained.

D87 freezes current source and runs the complete credential-configured suite. Final release/tag remains blocked until actual acceptance evidence and owner decisions exist. [Manual listening guide](D70_MANUAL_LISTENING_TEST.md).
