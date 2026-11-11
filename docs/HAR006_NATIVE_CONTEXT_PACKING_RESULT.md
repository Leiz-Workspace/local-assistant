# HAR-006 — Native tokenizer packing probe

**Mục đích:** Kiểm chứng tradeoff thực tế giữa ba context priorities bằng tokenizer/template của CORE, không nhầm token fitting với hiểu đúng context.

**Ngày:** 2026-11-10. [Runner](../benchmarks/context_priority_probe.py), [public observations](evidence/context-priority-native-v1-20261110.json), private frozen inputs tại `data/evaluations/20261110-context-priority-v1`. Runner có 2 software tests PASS trong 0.13 s, không gọi model trong pytest.

## Panel cố định trước khi chạy

Một cặp user/assistant history chứa ID `H-286`, 12,000 lần `stone ` và 12,000 lần `leaf `. Một evidence source chứa ID `R-752` và 10,000 lần `river `, dưới source-byte limit. Current task yêu cầu giữ identifiers có sẵn, không suy diễn evidence bị thiếu. CORE/Fast/max output 512, context window/presets không đổi. Không sửa kích thước hoặc chọn lại panel sau khi xem kết quả.

## Quan sát native

| Strategy | Input tokens cuối | History bị loại | Evidence | ID còn trong packed prompt |
|---|---:|---:|---|---|
| evidence-first | 10,129 | 2 messages | Có | R-752 |
| recent-turns | 24,131 | 0 | Bỏ, reason history_priority | H-286 |
| strict | 24,131 | 0 | Bỏ, reason history_priority | H-286 |

Ba prepare calls hoàn tất, packing đúng policy khai báo; mỗi call khoảng 0.115–0.129 s trong lượt này. Không có text generation/model completion; không đo semantic answer accuracy, TTFT, peak RAM/VRAM hoặc mọi background load. Những thời gian này là preparation wall time, không tốc độ suy luận.

Không strategy nào giữ được cả hai ID ở panel này: evidence-first bỏ whole-turn history để nhận source; hai mode còn lại giữ history và ghi rõ source bị bỏ. Đây là tradeoff có thể inspect, không bằng chứng context đã được tóm tắt/nhớ đầy đủ. Semantic compaction, retrieved-source budgeting, durable working state và long-context quality/resources vẫn OPEN trong HAR-006/HAR-009.
