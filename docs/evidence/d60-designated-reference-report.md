# Research report

Citation integrity: exact owner-signed source excerpts. Support labels and reasons are unverified model assessments. Semantic truth and publication/freshness are not verified.

## Goal

```text
Research the official SearXNG Search API GET and POST methods and RFC 9111 unqualified private cache rules using complementary search queries.
```

## Assessment provenance

Assessment UTC: 2026-10-21T19:30:28.196090+00:00
Assessment SHA256: ccc69756e7965e75edac54c70432b79aa9b71b0647e380c28a4f0469fc5618cb

## Claims supported by supplied excerpts (unverified assessment)

### C1

```text
The SearXNG search endpoints support both GET and POST methods.
```

Evidence: [E1]

Unverified model reason:

```text
Quote explicitly states endpoints support both GET and POST methods.
```

## Claims contradicted by supplied excerpts (unverified assessment)

### C2

```text
RFC 9111 allows a shared cache to store a response with an unqualified private directive.
```

Evidence: [E2]

Unverified model reason:

```text
Quote states shared cache MUST NOT store response with unqualified private directive.
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

Fetched UTC: 2026-10-21T19:30:25.836628+00:00
Snapshot: d92f9ea2-043b-4d41-a9aa-4c9aa3a9bd5a
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
RFC 9111: HTTP Caching
```

Final source URL:

```text
https://www.rfc-editor.org/rfc/rfc9111.html
```

Fetched UTC: 2026-10-21T19:30:26.244576+00:00
Snapshot: 024dd993-2f62-4ac7-be19-d441db60ae60
Exact code-point span: 53973:54073
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
