# D49 bounded public HTTPS and static text

**Purpose:** Describe the separate explicit-URL fetch adapter, measured evidence and limits while preserving accepted search, models, infrastructure and data.

**Status:** PASS within the defined local static-public-source scope. [Acceptance](../evidence/d49-public-fetch-acceptance.json), [ADR-067](../ADR/067-public-pinned-https-fetch-and-static-text.md). D50 remains next.

## Available boundary

`src.infrastructure.web_fetch.BoundedWebFetcher` implements the internal `WebFetchPort.fetch(url)` contract. Constructing it is inert; an explicit trusted caller must provide a URL. No application HTTP route, model tool, automatic search-hit fetch, permanent flag, cache/history, database/Vault or Docker change is introduced. D48's authenticated search API and its quotas remain unchanged. Later research-tool composition must preserve its own authentication/admission and owner/context limits.

Only explicit ASCII HTTPS443 destinations are supported. Credential/fragment/control/ambiguous/IP-literal/internal-name forms are refused. Original URL is returned separately from actual normalized URI; hostname case/default443/root spelling normalization is visible, complete path/query bytes including an empty query are preserved. Entire DNS answer set must pass conservative public-unicast policy before selecting one address. Pin exactly one numeric address per hop with original TLS SNI/Host/system CA verification and actual peer equality; no second DNS lookup, address fallback, proxy/env credentials, cookies or retry.

Validate every redirect location and its new DNS set; at mostthree redirects/four hops, no loops/private/downgrade/credentials. Canonical page metadata is explicitly unverified, never fetched and never substituted for the actual final source URL. Malformed, multiple or unsupported base-dependent canonical claims fail. Title, static text, exact body/text hashes and complete redirect chain bind evidence to the actual source; content remains untrusted. Page instructions/scripts never become model/tool/command authority.

## Limits and ownership

One nonqueued operation per fetcher.15second cooperative total,3second DNS/connect/handshake/read stages, bounded1second graceful TLS shutdown followed by abort/join if necessary. System DNS cannot safely be preempted in a thread; cancellation/deadline retains admission and joins the lookup until it actually returns. This is not a hard DNS wall-clock SLA. Repeated caller cancellation, late unreturned writers, task-creation failure, socket read/close and shutdown cleanup are tested. No unrelated service/model is stopped.

Strict CRLF and original16KiB/128-field header bounds before h11 normalization; no folded fields or duplicate critical headers, no nonempty trailers, at mostthree informational replies/no upgrade. Body at most1MiB, complete wire2MiB including chunk overhead, reads8192bytes.200 identity-encoded UTF-8/ASCII HTML/plain text only; no decompression/media/codec guessing. Complete content exceeding a bound is rejected without clipping.

Incremental strict lxml no-network/no-external-resource/non-huge parser, at most32768nodes; title1024UTF-8 bytes, complete text128KiB, encoded result256KiB. Remove executable/embedded/template/navigation/hidden elements and extract deterministic static text. No JavaScript/CSS execution, rendered-visibility certificate, subresource/DTD/entity/file retrieval, dynamic-page fallback, source date verification or cache. Input/structure caps are not a separate-process OS CPU/RSS sandbox. Dynamic pages remain D50; provenance/cache D51, red-team D52, coverage D53 and semantic citation validation D56.

## Observed gates and preserved failures

Final **219 controlled PASS/.48s,0SKIP**, including real loopback TLS/hostname/CA/peer/request framing and actual FD retirement. Positive loopback framing explicitly authors only its public peer view; separate tests prove a real loopback peer is denied. These seams are not called an actual public network.

Related **1859 PASS/117.93s (0:01:57),0SKIP,exit0**. [Related result](../evidence/d49-related-regression.json). All451 D48 accepted source/config files remain byte-identical. Historical D48 fresh full3010 PASS/1637.76s remains separate; no new3229 full-suite claim. Eleven new Python files/141 described functions/classes pass isolated Ruff correctness/import/format. Final source462/config/932 unique current source-protected hashes; [freeze](../evidence/d49-observed-fetch-freeze.json), [quality](../evidence/d49-observed-source-quality.json).

Distinct actual public `https://docs.searxng.org/dev/search_api.html`: **PASS/.242s**, one original system DNS resolution/one numeric TLS connection/one HTTP200, system certificate verification, exact pin/peer/SNI,835HTML nodes/4825UTF-8 text bytes, original source/body/text hashes and native socket FD=-1 after joined closure. No authored peer, model call, automatic retry, subresource or raw real HTML/text persistence. This asserted script is separate from pytest, one visible smoke source and not a latency SLO, semantic/freshness/general-quality benchmark. [Observation](../evidence/d49-observed-public-fetch.json).

Two earlier failures are retained:

- First controlled138 PASS/2 FAIL/.18s:explicit3fff::/20 documentation denial omitted on old Python3.12.3; direct-address/unsafe-tail tests caught it. Policy-only repair140 PASS, unchanged denial oracles; exact first source/tests/log archive retained. [Record](../evidence/d49-initial-ipv6-failure.json).
- First actual HTTP200/one DNS+TLS/1.135s reached content assertions, then cleanup observer called closed SSL writer.get_extra_info and raised AttributeError. Whole gate remains FAILED; no retrospective FD PASS. Production adapter unchanged. Capture native socket before close; add a real TLS FD assertion, freeze a distinct observer cohort with the same source URL/content oracle. Both source/script/freeze/outcome archives remain exclusive. Total actual public attempts across the two cohorts:2, no automatic retry or model. [Record](../evidence/d49-first-observer-failure.json).

One intermediate test placement mistake was caught by Ruff (F841/three F821) before pytest and fixed before final freeze; no oracle relaxation. Existing D47 refusal/Google failure, D46 first7/10 and D45/D43/D38 original scores stay immutable.

Final readonly audit passes:V006, zero source/memory/quota/vector/probe/worker/native/advisory-lock/app/pending inventories; original owners/ACL/narrow grants/invoker fixed-search-path triggers, all14 original containers and owned SearXNG identity/security/resource/mount/ports preserved. Existing CORE/provider healthy; agreed model/config/dependency/migration bytes unchanged. [Audit](../evidence/d49-final-readonly-audit.json).

Complete evaluated11-file archive `data/backups/d49-observed-evaluated-full-files.zip`, SHA256 `988d6f0fa743196f46da21d51eca243da1b763a46af620833b961ef7872fccff`,0600/CRC/exact bytes verified. Complete final committed file versions are retained after local commit. Rollback drains/drops only this unwired adapter; no model swap, migration/reindex/data deletion, accepted API change or existing service restart.
