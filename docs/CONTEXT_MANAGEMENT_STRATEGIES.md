# Chiến lược quản lý context

**Mục đích:** Giải thích cách xử lý lịch sử vượt cửa sổ context, cách dùng phần đã triển khai và các gate còn mở. Cập nhật 2026-11-11; [ADR-187](ADR/187-opt-in-pinned-history-and-extractive-compaction.md), [ADR-189](ADR/189-opt-in-token-budget-history-window.md), [ADR-190](ADR/190-opt-in-source-bound-working-state.md), [backlog](progress/HARNESS_PRODUCT_BACKLOG.md).

## 1. Bảy phương pháp và trạng thái thực tế

| Phương pháp | Cơ chế | Ưu điểm | Nhược điểm | Trong repository |
|---|---|---|---|---|
| Truncation | Bỏ nội dung cũ khi thiếu chỗ | Nhanh, không gọi thêm LLM | Có thể bỏ mất dữ kiện quan trọng | Đã có: bỏ **trọn cặp user/assistant**, không cắt giữa câu; policy và câu hỏi hiện tại giữ nguyên. |
| Sliding window | Giữ N lượt gần nhất | Dễ dự đoán số lượt và chi phí | N lượt vẫn có thể vượt token budget; quên phần ngoài cửa sổ | Đã có opt-in `sliding-window`: N tùy chỉnh, ghim lượt quan trọng, kiểm tra token thật rồi bỏ thêm lượt tùy chọn nếu cần. Opt-in `token-budget` (HAR-009-B2): chọn lượt gần nhất theo ngân sách token thay vì số lượt cố định, ưu tiên lượt người dùng đánh dấu `Rule:`/`Quy tắc:`… |
| Summarization | LLM viết tóm tắt lịch sử | Tiết kiệm token cho hội thoại dài | Thêm chi phí, dễ bỏ sót hoặc tạo thông tin sai | **PENDING**: chưa gọi CORE làm summary. Cần benchmark facts/constraints/citations/contradictions và lưu lineage trước adoption. |
| Context compaction | Giữ thông tin cần thiết từ lịch sử, tool output và trạng thái công việc | Hợp tác vụ agent nhiều bước | Khó giữ đầy đủ chi tiết và trạng thái | **Experimental slice**: `extractive-compact` chọn nguyên văn cặp hội thoại liên quan, có hash nguồn. Chưa compact tool outputs, task state hoặc approval. Opt-in `working_state` (HAR-009-C1 slice 1) giữ trạng thái có cấu trúc tất định từ dòng user có marker, mang qua các lần bỏ cửa sổ; không dùng LLM. |
| RAG / retrieval | Tìm lại nguồn liên quan thay vì đưa tất cả vào prompt | Làm việc với dữ liệu lớn | Phụ thuộc tìm kiếm, phân quyền, freshness | File RAG hiện có giữ nguyên. Slice mới chỉ tìm từ khóa trong các bản lịch sử được chỉ định; **chưa tự nối file RAG vào CLI chat**. |
| Hierarchical memory | Phân tầng working/recent/episodic/long-term memory | Duy trì thông tin qua phiên | Cần consent, cập nhật, xóa và xử lý mâu thuẫn | Recent history đã có; consented memory services hiện có độc lập. **PENDING**: tự phối hợp các tầng và memory injection. |
| Context offloading | Đưa dữ liệu lớn ra kho, giữ tham chiếu để nạp lại | Giữ được bản gốc ngoài prompt | Cần expiry/quota/ACL và cơ chế recall | Đã có cache lịch sử **trong RAM của tiến trình**, owner-only, TTL 30 phút; recall/delete rõ ràng. Chưa là kho bền vững qua restart. |

Các phương pháp bổ sung cho nhau. Ví dụ: recent window + pinned constraints + extractive history + explicit recall. Không thể khắc phục mọi thiếu sót bằng cách tăng context size; bản này không đổi model hoặc cửa sổ 32.768 token.

## 2. Nguyên tắc giữ và bỏ

1. Đếm bằng `/apply-template` và `/tokenize` của đúng CORE, đúng thinking mode; không dùng số ký tự làm token ở runtime.
2. Giữ host policy, system messages, skill đã duyệt, câu hỏi hiện tại và các **cặp hội thoại được ghim**. Pin đánh số từ 1 trên lịch sử đầy đủ của request, không phải thứ hạng trong cửa sổ đang giữ.
3. Chọn N cặp gần nhất, hợp với các pin, giữ thứ tự gốc. Nếu vẫn thiếu chỗ, bỏ cặp tùy chọn cũ nhất. Pin quá lớn thì trả `context_overflow`/422; không âm thầm cắt pin hoặc câu hỏi hiện tại.
4. Với compact, ngưỡng mềm mặc định là 80% ngân sách input, không phải 80% tổng context. Khi có thể, bỏ thêm lượt tùy chọn để chừa chỗ cho phần trích; nội dung bắt buộc có thể vượt ngưỡng mềm nhưng vẫn phải vừa giới hạn cứng.
5. Compact lưu toàn bộ các cặp bị bỏ vào cache trước khi gọi completion. Phần trích chọn bằng lexical overlap với câu hỏi hiện tại: tối đa 8 cặp, mỗi cặp tối đa 4 KiB, giữ **nguyên cặp**, không paraphrase hoặc cắt chữ. Cặp quá lớn vẫn có trong bản cache nhưng không được trích vào prompt.
6. Phần trích được gắn trong JSON `untrusted_history_context` ở message user hiện tại, có hash/turn nguồn. Role bên trong JSON chỉ là dữ liệu, không tạo message system/assistant mới. Đối thoại mới và yêu cầu hiện tại được policy ưu tiên khi mâu thuẫn; đây không phải bảo đảm model luôn hiểu đúng.
7. `evidence-first` ưu tiên nguồn sau nội dung bắt buộc; `recent-turns`/`strict` chỉ thêm nguồn nếu không làm mất lịch sử đã chọn. `strict` từ chối mọi việc bỏ lượt do cửa sổ hoặc áp lực token. Đây là lựa chọn độc lập với history policy.

8. `token-budget` (ADR-189) không dùng N lượt. Nếu toàn bộ lịch sử vừa ngưỡng mềm (mặc định 80% ngân sách input) thì giữ hết. Nếu không: giữ phần bắt buộc; giữ cặp mới nhất còn vừa ngưỡng; giữ dãy cặp gần nhất liền mạch trong tối đa nửa phần còn trống; rồi giữ các cặp cũ hơn có **tin nhắn user mở đầu** bằng một marker (`rule:`, `constraint:`, `important:`, `decision:`, `remember:`, `quy tắc:`, `quy ước:`, `ràng buộc:`, `quan trọng:`, `quyết định:`, `ghi nhớ:`, không phân biệt hoa thường/NFC/NFD) trong ngưỡng, thử tối đa 8 cặp; cuối cùng nới dãy gần nhất tới hết ngưỡng. Receipt ghi lý do giữ/bỏ từng cặp, không chứa nội dung. Marker chỉ đổi thứ tự ưu tiên giữ lại, không cấp quyền gì. Rủi ro đã đo: quyết định cũ có marker được giữ trong khi lời đính chính mới hơn không có marker bị bỏ, model trả lời giá trị cũ.

9. `working_state` (ADR-190, opt-in, dùng với `sliding-window` hoặc `token-budget`, không dùng với `extractive-compact`): mỗi **dòng** trong tin nhắn user mở đầu bằng marker (có thể có gạch đầu dòng và khóa trong ngoặc vuông, ví dụ `Decision[db-region]: Warsaw`) trở thành một mục `goal`/`constraint`/`decision`/`todo`/`done`/`note`/`correction`, giữ nguyên văn, có số cặp tuyệt đối và SHA-256 của cặp gốc. Mục sau cùng khóa thay thế mục trước; `Done[key]` đóng `Todo[key]`; mục không khóa không bao giờ bị tự thay thế. Cặp mới hơn chia sẻ ít nhất 3 từ có nghĩa với một mục được ghi trong `newer_mentions`, và với `token-budget` thì cặp mới nhất như vậy được giữ (lý do `newer_related`). State hiển thị là JSON không tin cậy trong tin nhắn user hiện tại, tính vào phần bắt buộc; vượt 64 mục đang hiệu lực hoặc 32 KiB thì bỏ mục `note`/`correction` cũ nhất trước, rồi mục cũ nhất, và báo số lượt bị bỏ trong `dropped_active` (CLI in ra). Dòng có marker nhưng sai cú pháp, khóa rỗng hoặc dài quá 48 ký tự, hay dài quá 500 ký tự được báo trong `skipped_lines`. Lời của assistant không bao giờ thành mục. Receipt trả state đầy đủ cho chính người gọi để mang sang request sau; log chỉ ghi số đếm.

Với policy mới, Fast/Balanced/Deep giữ chỗ cho output ceiling của preset hoặc giới hạn output yêu cầu; reserve vẫn 256 token. Unlimited không có output ceiling cố định thì giữ tối thiểu 512 token cho câu trả lời, rồi dùng ngân sách động hiện có. Không truyền `history_policy` thì chạy đúng nhánh whole-turn cũ, không tự tạo archive.

Compact có overhead JSON/hash/policy. Hội thoại ngắn có thể dùng **nhiều token hơn** cửa sổ đơn giản; đây không phải công cụ luôn nén nhỏ hơn hay tăng độ đúng của model.

## 3. Dùng qua CLI

Khởi động CORE và harness theo [runbook](HARNESS_CLI_DESKTOP_RUNBOOK.md). Chính sách mới chỉ có ở process khởi động từ checkout mới; không tự restart backend cũ.

```bash
uv run --no-sync la chat --history-policy sliding-window --history-window 8
uv run --no-sync la chat --history-policy sliding-window --history-window 8 --pin-turn 1
uv run --no-sync la chat --history-policy extractive-compact --history-window 8 --compact-trigger 0.8
uv run --no-sync la chat --history-policy token-budget --history-budget-ratio 0.8
uv run --no-sync la chat --history-policy token-budget --working-state
uv run --no-sync la context archives
uv run --no-sync la context recall ARCHIVE_UUID
uv run --no-sync la context forget ARCHIVE_UUID
uv run --no-sync la chat --history-policy extractive-compact --recall ARCHIVE_UUID --message 'Atlas cần snapshot nào?'
```

`--pin-turn 1` bắt đầu có hiệu lực khi cặp hỏi–đáp đầu tiên đã hoàn thành. CLI giữ lịch sử đầy đủ trong RAM để số lượt không đổi; không âm thầm cắt còn 22 message trong mode mới. API nhận tối đa 256 messages/request; CLI dừng rõ ràng ở giới hạn sau 128 cặp thay vì lặng lẽ đánh số lại hoặc giả vờ nhớ vô hạn. Chat CLI mặc định giữ hành vi cũ.

Interactive CLI hiển thị lượt bị đưa ra ngoài cửa sổ và archive ID trên stderr. `context recall` trả **nguyên văn lịch sử**, có thể là dữ liệu nhạy cảm; chỉ chạy khi muốn hiển thị dữ liệu đó. `context archives` chỉ liệt kê metadata để tìm/xóa cache kể cả khi model lỗi sau preparation. `--recall` chỉ tìm đoạn liên quan trong đúng các ID đã chỉ định, không tự đưa toàn bộ archive vào prompt.

## 4. API và inspection

POST `/api/v1/harness/chat`, bearer authentication hiện có:

```json
{
  "messages": [
    {"role": "user", "content": "Atlas dùng snapshot G-17."},
    {"role": "assistant", "content": "Đã ghi nhận trong hội thoại."},
    {"role": "user", "content": "Atlas dùng snapshot nào?"}
  ],
  "preset": "fast",
  "context_strategy": "evidence-first",
  "history_policy": {
    "mode": "extractive-compact",
    "window_turns": 8,
    "pinned_turns": [1],
    "trigger_ratio": 0.8,
    "max_extracts": 8,
    "recall_ids": []
  }
}
```

Response `context` schema 2 có số token thật, included/omitted evidence và `history_policy`: retained/evicted/pinned turns, source hash của các extracts, archive metadata, soft target, các cờ `llm_summary=false`, `archive_persistent=false`, `recall_automatic=false`. Trace không chứa raw history/extract text. Schema 1 và payload cũ giữ nguyên khi không chọn policy mới.

GET `/api/v1/harness/context/archives` liệt kê metadata của owner. GET/DELETE `/api/v1/harness/context/archives/{id}` đọc/xóa đúng owner; UUID lạ, khác owner hoặc hết hạn cùng trả 404. GET đặt `Cache-Control: private, no-store`. Không có endpoint nhận owner tự khai hoặc upload archive tùy ý. Browser UI llama.cpp chưa có controls cho policy này và vẫn dùng đường streaming cũ.

## 5. Lưu trữ và giới hạn

- Mỗi entry tối đa 128 KiB; mỗi owner tối đa 16 entries/2 MiB; toàn process tối đa 128 entries/8 MiB. Đầy cache trả 429, không âm thầm đuổi bản chưa hết hạn. Raw quá lớn trả 413; không âm thầm lưu một phần.
- TTL tối đa 1.800 giây, tính từ lúc tạo. Đọc hoặc deduplicate cùng bytes không gia hạn. Cache chỉ được prune khi có thao tác tiếp theo; TTL là hạn truy cập, không cam kết xóa vật lý tức thời trong RAM.
- Đóng process sẽ xóa cache; không có disk store, recovery hay resume. SHA-256 bảo vệ binding bytes, không xác minh tính đúng của lời model trước đây.
- Log chỉ có operation/category/count/ID/size/token, không raw text. Signed metadata history hiện có không nhận archive payload, consent, quyền tool hoặc approval.
- Nếu completion lỗi sau khi chuẩn bị, cache có thể đã tồn tại: dùng `context archives` để xóa hoặc đợi TTL. Xóa cache không xóa conversation gốc hoặc bản đang có trong RAM của CLI; không bảo đảm secure erase RAM.
- Offloading giảm dữ liệu đưa **vào prompt**, không bảo đảm giảm tổng RAM: client vẫn giữ lịch sử và server có thêm cache tạm.

## 6. Kiểm chứng đợt này

**462 PASS / 0 FAIL / 0 SKIP, 4.75 s**, 38 test files liên quan, gồm 55 tests mới. Đã kiểm window/pins/hard/soft limits/Unlimited, original bytes, malformed/oversized pairs, source priorities, scope/expiry/quota/corruption, no raw logs, API/CLI và fake native protocol. Không phải full D87 hoặc 462 model-quality cases.

[Native receipt](evidence/context-policy-native-20261111.json): fixed synthetic panel, inputs/code/config frozen trước chạy, **8 kịch bản preparation-only**, đúng CORE/Q6_K/config hiện có; zero completion calls, no retries. Kết quả:

| Kịch bản | Input token sau compose | Dữ kiện cũ G-17 | Quan sát |
|---|---:|---|---|
| Legacy | 343 | Không | Cửa sổ 11 cặp bỏ lượt 1. |
| Sliding N=3 | 173 | Không | Giữ lượt 12–14. |
| Sliding N=3, pin 1 | 215 | Có | Giữ lượt 1,12–14. |
| Extractive compact N=3 | 460 | Có | Lượt 1 có trong phần trích nguyên văn có nguồn. |
| Explicit recall | 395 | Có | Lấy lại từ cache cùng owner, không khôi phục live roles. |
| Token pressure, pin 1 | 20.328 | Có | Giữ 1,4; bỏ trọn 2,3; vừa input limit 32.000 với output 512. |
| Strict N=3 | — | — | Từ chối `strict_context_would_trim`. |
| Mandatory overflow | — | — | Từ chối `context_overflow`. |

Đây là kiểm chứng **dữ liệu có mặt trong context**, không chứng minh câu trả lời đúng, factual consistency, TTFT/peak RAM/VRAM hoặc chất lượng tóm tắt. CORE được chạy riêng bằng launcher hiện có rồi dừng sau probe; không restart shared desktop, không tải/đổi model, Docker, Vault, database hoặc Qdrant. Cache synthetic đã xóa.

## 7. Phần tiếp theo và gate

HAR-009-A đóng riêng mechanics thử nghiệm trên; **HAR-009 tổng vẫn PARTIAL**. Không hạ AC adoption hiện có: cần frozen paired semantic benchmark, constraint/fact/citation retention, contradiction/failure/ACL cases, latency/TTFT và peak RAM/VRAM trước chọn làm mặc định hoặc gọi là compact đủ chất lượng.

**HAR-009-B1 đã đo (2026-11-11)** theo [protocol](HAR009_B1_RETENTION_PROTOCOL.md) đóng băng trước inference, 60 lượt native đầu tiên, không retry ([kết quả](HAR009_B1_RETENTION_RESULT.md)): câu trả lời đúng nghiêm ngặt `full` 11/12, `legacy` 3/12, `window3` 1/12, `window3_pin1` 3/12, `compact3` 12/12 (`compact3` 0 câu trả lời giá trị cũ, 9 gain/0 regression so với legacy). `full` và `compact3` đều giữ đủ dữ kiện; chênh 12/11 chỉ do luật chấm chữ số. `compact3` dùng trung vị trên 1210 token input so với 564 của `full` trên hội thoại ngắn (~600 token) vì overhead JSON/provenance; corpus không tạo áp lực token và làm truy xuất từ khóa dễ (kết quả của `compact3` là cận trên). Đây là đo đạc, không quyết định default hay adoption.

**HAR-009-B2 đã triển khai và đo (2026-11-11)**: chế độ opt-in `token-budget` ([ADR-189](ADR/189-opt-in-token-budget-history-window.md)), [protocol](HAR009_B2_TOKEN_BUDGET_PROTOCOL.md) đóng băng trước completion, chạy 2 lần × 36 lượt native đầu tiên, không retry; lần 2 chạy trên code đã sửa lỗi thứ tự chọn lượt do review độc lập phát hiện, kết quả chấm giống hệt lần 1 ([kết quả](HAR009_B2_TOKEN_BUDGET_RESULT.md)). Đúng nghiêm ngặt: `legacy` 3/12, `token-budget` 7/12, `extractive-compact` 11/12. Với 40 lượt ngắn, `token-budget` giữ đủ 40 cặp và đúng 4/4 (legacy 0/4); dưới áp lực token, nó giữ rule có marker (2/2, legacy 0/2) nhưng **trả lời giá trị cũ ở cả 2 case quyết định có marker bị đính chính sau không có marker** (2 regression so với legacy, đúng rủi ro đã dự đoán). Compact giữ đủ dữ kiện 12/12, 0 câu trả lời cũ, 0 regression; corpus vẫn làm truy xuất từ khóa dễ nên đây là cận trên. Với lịch sử dài, hai nhánh mới có trung vị trên 23,7k (`token-budget`) và 24,0k (`extractive-compact`) token input so với 29,6k của legacy, chữ đầu tiên sớm hơn khoảng 1,2 s. Không đổi default; trước khi dùng mặc định, luật marker cần cho phép lời đính chính mới hơn thắng.

**HAR-009-C1 slice 1 đã triển khai và đo (2026-11-11)**: working state opt-in ([ADR-190](ADR/190-opt-in-source-bound-working-state.md)), [protocol](HAR009_C1_WORKING_STATE_PROTOCOL.md), 2 lần × 54 lượt native đầu tiên, không retry; lần 2 chạy trên code đã sửa sau review độc lập, cùng kế hoạch context ([kết quả](HAR009_C1_WORKING_STATE_RESULT.md)). Trên corpus B2, `token-budget` + working state đúng 9/12 rồi 7/12: freshness giữ lời đính chính không marker ở cặp 6 bên cạnh quyết định có marker trong cả 4 lượt thuộc case cũ-mới; trả lời đúng 3/4, lượt còn lại nêu cả Đà Nẵng lẫn Hà Nội nên bị tính là giá trị cũ; `budget` không state đúng 0/4 (legacy còn giữ cặp 6 nên đúng 4/4). Với hội thoại 200 lượt mà CLI phải bỏ cửa sổ 3 lần, state mang theo trả lời đúng 5/5 case có marker ở cả 2 lần (quyết định cập nhật theo khóa, rule sớm, việc còn mở, mục tiêu), các nhánh không có state 0/5; thông tin không marker vẫn mất ở mọi nhánh. Chi phí: 78 token cho dòng policy; 126–140 token khi có mục; 169–181 token khi giữ thêm cặp `newer_related`. Không đổi default.

Tiếp theo: HAR-009-C: context layers/consented memory/RAG/tool-state; HAR-009-D: durable offload/invalidation và UI controls. Priority, dependency, effort và rủi ro nằm trong backlog; không tự chọn model mới hoặc phục hồi approval qua memory.
