# HAR-008 — Frozen paired source/review evaluation v1

**Mục đích:** Đo tác động của skill bằng cùng CORE, cùng task/evidence/options và oracle đóng băng trước inference; không dùng smoke đơn lẻ để gọi specialist qualified.

**Ngày:** 2026-11-10. Phạm vi: 12 controlled cases, mỗi case một baseline và một skill attempt, tổng **24 model completions**, không retry. Thứ tự baseline-first/skill-first xen kẽ theo case. Hai skill đã có: `source-reader`, `repo-review`; không sửa instructions hoặc đổi model/preset để thích nghi với kết quả.

## Dữ liệu và điều kiện

[Corpus](../benchmarks/fixtures/har008-source-review-v1.json) gồm 6 source-grounding cases và 6 review-localization cases, trong đó 4 null controls, version/number selection và một source-injection control. Source và oracle do cùng assistant chuẩn bị: đây là controlled panel, không phải human-independent benchmark hoặc đánh giá toàn bộ năng lực coding. Model chưa nhận corpus này trước khi đóng băng lượt đầu; không tuyên bố blindness của người viết/chấm.

[Runner](../benchmarks/har008.py) ghi immutable frozen-inputs/corpus/source/skill/config/code hashes trước model request. Chỉ source evidence và câu hỏi/schema được gửi vào model, không gửi oracle. Dùng actual authenticated product API, exact reviewed installation, native workspace read và context receipts. Root source là synthetic workspace hiện đã được host cho phép, không tự đăng ký repo thật hoặc đọc private source.

CORE đã duyệt, Fast, max output 512, context strict, temperature theo gateway hiện có; không seed override hoặc tài nguyên/model mới. Campaign tối đa 240 giây, mỗi run vẫn theo deadline 120 giây của sản phẩm. Thời gian thực là mô tả một lượt trên host hiện tại, không SLO/TTFT hay bằng chứng đã kiểm soát mọi background load.

## Oracle và kết quả

Mỗi phản hồi phải là JSON object có đúng `value`, `quote`, không fence/prose/extra keys/duplicate keys. Value phải đúng cả type và giá trị; quote phải đúng literal fragment/full line đã khai báo. Null controls cần cả hai null. Không model-grading, không sửa output rồi chấm lại, không đổi oracle sau khi thấy kết quả. Narrative review quality, severity, fixes và arbitrary repository tasks chưa được chấm bằng rubric này.

Giữ mọi first request/response/score và partial result. Model-format/quality failures được ghi và vẫn chạy case tiếp theo; software/API/timeout/binding errors dừng campaign, không tự retry. Cleanup chỉ xóa terminal runs và temporary installations do campaign tạo; raw receipts còn trong private output. Không revoke installation có sẵn của owner.

Evaluation có thể **MEASUREMENT_COMPLETE** dù skill không tốt hơn. Broad promotion luôn **NOT_QUALIFIED** trên panel nhỏ này; báo paired wins/losses/equality, token usage, elapsed và các giới hạn thay vì bịa improvement hoặc large-model parity. Không đóng AC của context resource/semantic compaction, release hoặc model-generation bằng phép đo này.

## Chạy và rollback

Chỉ chạy sau unit/contract tests; chọn output directory mới, parent đã có:

```text
uv run --no-sync python -m benchmarks.har008 --workspace WORKSPACE_UUID --workspace-root /ABSOLUTE/OWNED_SYNTHETIC_ROOT --output data/evaluations/NEW_HAR008_DIRECTORY
```

Không thay production defaults, source PASS cũ, model config, Vault/Docker/database/Qdrant. Dừng runner sẽ giữ partial receipts; cancel/join run đang biết ID, cleanup temporary skill grants và giữ các nguồn synthetic để audit. Trạng thái submit bị mơ hồ phải báo rõ, không tự phát lại request để hoàn tất đủ số lượng.
