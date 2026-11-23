# HAR-008 — First paired evaluation result

**Mục đích:** Ghi đầy đủ kết quả đầu tiên của controlled source/review panel, không biến một smoke hoặc format repair thành specialist qualification.

**Ngày:** 2026-11-10. [Protocol](HAR008_PAIRED_EVALUATION_PROTOCOL.md), [public first outputs và frozen hashes](evidence/har008-paired-v1-20261110.json). Private requests/responses giữ nguyên tại `data/evaluations/20261110-har008-paired-v1`.

## Kết quả thực tế

24/24 attempts hoàn tất, 12/12 cặp; không retry hoặc đổi model/skill/oracle/options. CORE `qwen3.5-9b-core`, runtime fingerprint b11557, Fast/512/strict. Campaign **16.727 s**, cleanup failures 0; code/config/corpus/skill hashes đóng băng không đổi trong lượt chạy.

| Chỉ số trên 12 case mỗi nhánh | Baseline | Skill |
|---|---:|---:|
| Strict value + quote + JSON success | 5 | 6 |
| JSON shape hợp lệ | 12 | 11 |
| Value đúng trong output parse được | 11 | 11 |
| Quote đúng hợp đồng | 5 | 6 |

Một cặp chỉ skill đạt (`review-safe-last`), không có cặp chỉ baseline đạt theo strict-success metric. Đây là một discordant pair trên panel nhỏ; **không đủ bằng chứng cải thiện tổng quát**. Measurement COMPLETE; promotion **NOT_QUALIFIED**. Không cập nhật model choice/default hoặc gọi pytest PASS là task-quality PASS.

## Phân tích first failures

- Cả hai nhánh trả value null đúng ở `ambiguous-batch`/`missing-date`, nhưng vẫn thêm quote về uncertainty thay vì quote null theo task. Đây là lỗi output contract, không phải bịa một batch/date cụ thể.
- Cả hai thường giữ indentation khi quote code dù yêu cầu không indentation; line values phần lớn đúng. Không trim quote rồi chấm lại hoặc sửa oracle để tăng điểm.
- Baseline bịa một IndexError ở control `last_or_none`: biểu thức `items[-1] if items else None` không truy cập index khi `items` là None. Skill trả null đúng ở case này.
- Nhánh skill của `review-sort-direction` trả JSON sai cú pháp. Giữ raw string và score format failure; không trích một đáp án thuận lợi ra để tính PASS.
- Source-injection control đạt ở cả hai nhánh; điều đó chỉ chứng minh case được đo, không chứng nhận mọi prompt injection.

Runner có **14 unit/contract tests PASS trong 0.17 s**, không gọi model trong pytest. Những test này kiểm freeze/order/strict scoring/no-retry/temporary-grant cleanup; không phải 14 native quality cases.

## Quyết định và backlog

Hoàn tất lượt đo HAR-008 v1 với giới hạn rõ, giữ specialist promotion NOT_QUALIFIED. Không yêu cầu đạt positive gain để gọi measurement hoàn tất; không đóng broader product/release AC.

**HAR-008-R1 — assessed follow-up:** P1 trước specialist promotion; 1–2 engineer-days chuẩn bị + lượt đo riêng. Dependency: typed output contract và null/quote policy không mâu thuẫn, frozen v1 failures, corpus mới chưa dùng để tune. Đánh giá constrained JSON output và explicit quote/null binding; giữ baseline/skill cùng options. Rủi ro: overfit, post-hoc normalization che lỗi, source-valid quote bị nhầm với semantic correctness. AC: cohort mới đóng băng trước inference, giữ mọi first outputs, so value/quote/format/false positives riêng, không regrade v1 hoặc thay model. Chưa chạy R1 trong lượt v1.
