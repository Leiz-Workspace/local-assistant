# Research report

Citation integrity: exact owner-signed source excerpts. Support labels and reasons are unverified model assessments. Semantic truth and publication/freshness are not verified.

## Goal

```text
Resume archived Brave discovery 2026-10-21T08:30:57.384449+00:00 to 2026-10-21T08:31:00.620654+00:00; queries searxng-en,rfc-en; archive SHA256 ce877587af04e0aa14db6b30b303a6c1ef429e77ceeff63c899918af02be6c3f. No new search; source text fetched anew; search freshness unknown. Goal: Research the official SearXNG Search API GET and POST methods and RFC 9111 unqualified private cache rules using complementary search queries.
```

## Assessment provenance

Assessment UTC: 2026-10-22T02:27:09.133640+00:00
Assessment SHA256: 4ccdff720f5b4cee0eea5c88fdc51cd16a9a715b3bcc9a465f8b0d8ffba2916b

## Claims supported by supplied excerpts (unverified assessment)

### C1

```text
The SearXNG search endpoints support both GET and POST methods.
```

Evidence: [E1]

Unverified model reason:

```text
Quote explicitly states endpoints are supported for both GET and POST methods.
```

## Claims contradicted by supplied excerpts (unverified assessment)

### C2

```text
RFC 9111 allows a shared cache to store a response with an unqualified private directive.
```

Evidence: [E2]

Unverified model reason:

```text
Quote states a shared cache MUST NOT store a response with an unqualified private directive.
```

## Unresolved claims (insufficient evidence)

### C3

```text
Các nguồn này xác nhận hạn mức upload của Atlas là 256 MiB.
```

Evidence: none assigned

Unverified model reason:

```text
No evidence provided regarding Atlas upload limits.
```

## Evidence

### [E1]

Title:

```text
Search API - SearXNG Documentation (2026.10.19+81371861f)
```

Final source URL:

```text
https://docs.searxng.org/dev/search_api.html
```

Fetched UTC: 2026-10-22T02:27:06.289462+00:00
Snapshot: deb9dd07-04bd-41ac-8c7c-adc29178a5e2
Exact code-point span: 2563:2638
Quote SHA256: fceb2eca432e42b1e11d44f4fd77ceb2cb8ddb7ba3644c44cb77d8e8f4827c90

Exact untrusted quote:

```text
Two endpoints, / and /search , are supported for both GET and POST methods.
```

Publication/freshness: unknown. Source date declarations are unverified.

### [E2]

Title:

```text
RFC 9111 - HTTP Caching
```

Final source URL:

```text
https://datatracker.ietf.org/doc/html/rfc9111
```

Fetched UTC: 2026-10-22T02:27:07.135414+00:00
Snapshot: de8d15e9-7218-474b-b814-83abfd8037cc
Exact code-point span: 53989:54089
Quote SHA256: e09a64cca2742b9b70d8385cffea6d5bf0bdd37b66cb490e1c256155c7fc6831

Exact untrusted quote:

```text
The unqualified private response directive indicates that a shared cache MUST NOT store the response
```

Publication/freshness: unknown. Source date declarations are unverified.

## Limitations

- Only the explicitly selected claims and source excerpts were assessed; search completeness and independent relevance review are not established.
- Source text, titles, URLs, date declarations, claim text and model reasons are untrusted data, never instructions or verified facts.
- Supported/contradicted labels remain unverified model assessments. Contradictions and insufficient evidence are retained; no publisher winner is selected.
- Fetch UTC is acquisition time, not verified publication or freshness. Primary/official publisher status is not independently verified.
- Exact signed quote integrity does not prove claim truth or semantic entailment.
- Report reuse/export requires a valid owner-bound process-scoped receipt and unexpired original source proofs. Markdown hashes alone grant no authority.
