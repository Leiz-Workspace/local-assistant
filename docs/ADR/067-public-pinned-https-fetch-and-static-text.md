# ADR-067: Public pinned HTTPS fetch and static text

**Purpose:** Assess the existing D49 fetch/text/redirect/canonical-source task before implementation, preserving accepted search, models, infrastructure and data.

**Date:** 2026-10-21 (Asia/Ho_Chi_Minh)

**Status:** Accepted and verified within the local separate static-public-fetch scope:219 controlled included in1859 related PASS/0SKIP/exit0, distinct actual public DNS/TLS/HTTP/text/FD gate and readonly audit pass. D48 commit6a0c042/fresh3010 full source remains byte-identical; no new full claim.

## Priority, dependencies, effort and risks

Existing P1 D49 follows D48. Estimate one separate internal fetch contract/policy/network/extraction milestone plus URL/DNS/TLS/HTTP/parser/cancellation tests and one frozen actual public-source attempt. Dependencies are accepted D48 and existing locked asyncio/ssl/h11/lxml packages; no installation, new model, database/schema, Vault or Docker change. Later explicit research-tool composition remains separate; do not modify the accepted search API/provider or fetch arbitrary model-generated links automatically.

Risks include SSRF through rebinding/redirects/special addresses, ambiguous URL syntax, losing TLS hostname verification while pinning an IP, unbounded headers/body/decompression/DOM, unjoined resolver/socket cleanup, webpage instructions becoming authority and canonical metadata impersonating fetched evidence. Dynamic pages, cache/dates/dedupe, red-team/coverage and semantic citation validation remain D50/D51/D52/D53/D56.

## URL and network policy

Accept an explicit bounded ASCII HTTPS URL on443 only, without credentials, fragments, controls, backslashes, ambiguous/encoded authority, IP literals or internal/special-use host names. Preserve path/query semantics; reject unsupported inputs instead of silently repairing them. Bound2048bytes. Validate every redirect target again; at mostthree redirects, detect loops and refuse downgrade/credentials/private targets before any connection.

Resolve once per hop, validate the complete finite DNS answer set, select one public address, and connect to that numeric address only. No second hostname lookup, address failover, retries, environment proxy/credentials, cookies, authentication headers or subresource fetch. Keep original hostname for TLS SNI/certificate verification and Host. Compare actual peer address with the selected pin. Trust explicit system CA locations without environment key logging or disabled verification.

Use a conservative special-address deny policy in addition to local ipaddress flags, including mapped/tunnel/translation addresses and ranges corrected after this host's Python3.12.3. Restrict IPv6 to eligible global unicast and reject registered special/deprecated/documentation blocks. This is public-destination filtering, not a guarantee that every public endpoint is harmless or that remote GET semantics are enforced. [Python classification changes](https://docs.python.org/3.12/library/ipaddress.html), [IANA IPv4 special registry](https://www.iana.org/assignments/iana-ipv4-special-registry), [IANA IPv6 special registry](https://www.iana.org/assignments/iana-ipv6-special-registry), [IPv6 assignments](https://www.iana.org/assignments/ipv6-unicast-address-assignments).

## Framing, extraction and ownership

Use asyncio TLS streams and the existing h11 public event API for HTTP/1.1 framing, rather than inventing an HTTP parser or changing global HTTP client logging. h11 maps socket bytes to response/data/end events and bounds incomplete events; enforce complete header/trailer/body budgets independently. [h11 API](https://h11.readthedocs.io/en/stable/api.html), [client pattern](https://h11.readthedocs.io/en/stable/basic-usage.html). Considered existing HTTPCore custom networking; direct streams keep URL logging, peer pinning and ownership explicit without private transport mutation. [HTTPCore network interface](https://www.encode.io/httpcore/network-backends/).

Fixed initial limits: one nonqueued operation per fetcher,15second cooperative total deadline,3second DNS/connect/handshake/read stages,16KiB/128 header fields,1MiB complete raw body,2MiB complete wire including chunk overhead, and8192byte reads. Strict CRLF headers and no folded fields; deny nonempty trailers. Original duplicate framing fields are checked before h11 normalization. Accept200 static UTF-8 HTML/plain text only, identity encoding only; reject compression, incomplete framing, unsupported media/encoding and overbudget content without clipping. Up tothree bounded informational responses, no protocol upgrade. Close and join every owned writer before admission release.

A system DNS operation cannot safely be preempted inside a thread. Shield and join the owned lookup on cancellation/timeout, retaining admission until it returns; never claim a hard wall-clock DNS/cleanup SLO or orphan repeated lookups. Test repeated caller cancellation while lookup/socket cleanup is held. No unrelated task/backend/model cancellation.

Parse HTML with an incremental no-network strict non-huge parser, bounded node count32768 and explicit external-resource denial. Remove executable/embedded/template/navigation-like content and extract deterministic static text, not rendered visibility or JavaScript evaluation. No DTD/external entity/file/network retrieval. Bound title1024bytes, complete extracted text128KiB and encoded result256KiB. Unsupported/overbudget/deep input fails instead of returning a clipped page. [lxml parser restrictions/recovery](https://lxml.de/parsing.html).

Return exact requested/final fetched URL, redirect chain, title, media type, body/text hashes and untrusted text. Source authority is the URL actually fetched. An advertised canonical link is an explicitly unverified metadata claim, never fetched or substituted for final URL; reject/mark ambiguous unsupported relative/base/multiple/invalid claims. No freshness/entailment/cache/independent-quality claim or raw HTML persistence.

## Acceptance and rollback

Initial contracts: immutable hop response and fetched-page result; finite WebFetchError codes only, no raw diagnostics. At most64 DNS entries, one selected pin/no failover. Header budget16KiB/128 fields, no nonempty trailers; at mostthree informational responses. HTML node ceiling32768/title1024/text131072/encoded result262144 bytes; one unverified canonical claim, reject ambiguous/invalid/base-dependent claims. No source clipping. Finalize and freeze source/oracle before the first actual public fetch. Controlled development failures remain retained, without changing their expected denial oracles. Test URL tricks/special IP families, whole-answer mixed DNS denial and pin/peer/SNI preservation, redirect revalidation/loops/limits, duplicate/oversized/header/trailer/chunked/EOF/compression cases, actual controlled TLS with a disposable CA, strict static extraction/canonical/injection cases, finite errors/log privacy and joined repeated cancellation/timeout/shutdown. Separate controlled seams from actual public network evidence.

Freeze source/query/oracle before one actual public HTTPS attempt; retain the first outcome including failure, no query/threshold switching or automatic retry. Run affected regression and readonly source/model/security/data/container audit; report historical full D48 separately if accepted sources/composition remain untouched. Full suite is required again if necessary implementation changes shared composition/dependencies beyond this separate adapter scope. D49 PASS only after actual gates.

Rollback drops/drains only the later fetch adapter/tool; no model swap, reindex, migration, old evidence rewrite, accepted search API change or existing service restart.


## Controlled development observations before actual fetch

Initial policy/parser138 PASS/2 FAIL/.18s:explicit3fff::/20 documentation prefix was missing on old Python3.12.3; direct-address and unsafe-DNS-tail tests caught it. Whole first source/tests/log/ADR archive retained; policy-only repair140 PASS. Expanded network172 PASS, service/TLS203 PASS and final hardening219 PASS/.48s (zero skips). One intermediate test insertion was caught by isolated Ruff (one unused/three undefined locals) before pytest ran; moved the new constructor test outside the existing shutdown test, no oracle relaxation. Initial import ordering fixes also occurred before freeze. [First failure](../evidence/d49-initial-ipv6-failure.json). Actual network/related/audit gates still pending.

TLS tests use real loopback sockets and disposable certificates. Their positive framing test explicitly authors the public peer view; real loopback peer denial and hostname/CA failures are separately verified. The actual public gate must use original system trust, actual public DNS/pin/peer/SNI without that authored view. Input/structure caps are not a separate-process OS CPU/RSS sandbox or a hard DNS wall-clock guarantee. URI-equivalent host case/default443/root-path normalization is visible through separate requested/final URLs; path/query bytes, including an explicit empty query, are preserved.


## Actual completion

[Acceptance](../evidence/d49-public-fetch-acceptance.json), [scope/failures](../D49_BOUNDED_PUBLIC_FETCH.md), [observed actual fetch](../evidence/d49-observed-public-fetch.json), [audit](../evidence/d49-final-readonly-audit.json).219 controlled/1859 related PASS/117.93s/0SKIP,462 source/config/932 hashes,11 Python files/141 described functions/classes. First IPv6 two-test failure and first HTTP200/closed-writer observer AttributeError retained; observer-only separate cohort .242s/one DNS/TLS/HTTP/final4825byte static text/actual FD retirement, unchanged production adapter/source URL/content oracle. All451 accepted D48 source/config bytes remain current; its full3010 is historical, no new full claim. D50 NEXT.
