# D27-T03 — Human relevance review form

**Current policy update:** The owner subsequently delegated this review and similar tasks to the assistant because they are unavailable. This manual-review material is historical/optional; no manual labeling is currently required. See [owner-delegated evaluation](D27_OWNER_DELEGATED_EVALUATION.md) and [ADR-042](../ADR/042-owner-delegated-relevance-evaluation.md). No human review is claimed.


**Purpose:** Present the frozen score-free challenge once for convenient independent review; no labels or results are prefilled.

**Status:** Historical unfilled manual form. Current local D27 evaluation uses the separately versioned owner-delegated AI review; do not fill a false human review. The authoritative packet/template and validation rules are in [the review protocol](D27_INDEPENDENT_RELEVANCE_REVIEW.md).

Reviewer: PENDING
Reviewed at (ISO8601 with timezone): PENDING
Independent score-blind attestation: PENDING

## Sources

### doc-a

Atlas release 2.4: restore requires snapshot generation G-17 and source hash 8af2. Release 2.5 instead requires G-18; do not mix restore sets.

### doc-b

Atlas release 2.4 upload quota is 128 MiB per file. Indexing leases last 45 seconds; these numbers do not describe the restore generation.

### doc-c

Bảng chi phí tháng 9: gói A 120000 đồng, gói B 210000 đồng. Tháng 10: gói A 135000 đồng, gói B 225000 đồng. Chưa gồm VAT.

### doc-d

Bảng chi phí tháng 9: gói A 120000 đồng, gói B 210000 đồng. Tổng dự toán quý chưa được phê duyệt; không dùng làm số liệu tháng 10.

### doc-e

OCR chưa duyệt: Mã lô AB-I07 hoặc AB-107; ảnh mờ không phân biệt được I và 1. Cần xem ảnh gốc trước khi chốt mã lô.

### doc-f

Biên bản đã đối chiếu ảnh gốc: mã lô AB-107, nhận ngày 12/09. Kết quả này chỉ áp dụng lô hiện tại, không xác nhận mã của lô trước.

### doc-g

Sheet Revenue cell C7 contains =SUM(C2:C6), cached value 900, cache date 2026-09-01. Formula execution is disabled and this cached total may be stale.

### doc-h

Rollback ranking: disable and drain the optional reranker, then use dense ordering. Retain embeddings, sources and vector IDs; no reindex is needed for this ranking rollback.

## Queries

- **review-q01**: For Atlas 2.4, which snapshot generation must be restored?
- **review-q02**: Atlas 2.5 khôi phục bằng generation nào?
- **review-q03**: Chi phí gói B tháng 10 chưa VAT là bao nhiêu?
- **review-q04**: What is the approved quarterly total including VAT?
- **review-q05**: Nguồn nào xác nhận chắc chắn mã lô hiện tại sau khi đối chiếu ảnh gốc?
- **review-q06**: Does the OCR snippet alone resolve whether the lot code contains I or 1?
- **review-q07**: Can the cached C7 value be treated as a newly recalculated current total?
- **review-q08**: Khi rollback reranker thì có cần tạo lại embedding và vector ID không?

## Pair decisions

Replace every `PENDING` with true/false after reviewing the sources. Supply a short reason for each pair in the separate JSON response. A source supporting a negative answer can be relevant; no supporting source is also allowed. Do not infer labels from document order or from the old diagnostic results.

| Query | doc-a | doc-b | doc-c | doc-d | doc-e | doc-f | doc-g | doc-h |
|---|---|---|---|---|---|---|---|---|
| review-q01 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| review-q02 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| review-q03 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| review-q04 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| review-q05 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| review-q06 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| review-q07 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| review-q08 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
