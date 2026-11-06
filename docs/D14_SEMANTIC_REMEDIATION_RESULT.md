# D14 — Phương án khắc phục chất lượng đã được kiểm chứng

**Mục đích:** Giải thích vì sao gate cũ FAIL, thay đổi đã thực hiện và kết quả thật của đường suy luận tùy chọn mới, giữ nguyên mọi điểm lịch sử.

Ngày: 2026-10-26. **LOCAL CONTRACT REASONING GATE PASS: CORE42/42 và UNRESTRICTED42/42.** [Receipt kiểm chứng độc lập](evidence/d14-contract-full-first-verification.json), [protocol chốt trước inference](D14_CONTRACT_FULL_PROTOCOL.md), [audit bảo toàn source/runtime](evidence/d14-semantic-preservation-verification.json).

## Vì sao trước đây FAIL và đã sửa gì

Các câu trả lời cũ đã đúng JSON nhưng còn sai tính toán, Python và cách trả nhãn nguồn. Request tắt thinking chỉ sinh đáp án ngắn. Bộ đối chiếu mới trên cùng12câu/profile cho direct7/12, trong khi native final của thinking đúng12/12 khi kiểm tra riêng theo budget đã khai báo. Đây là bằng chứng trên bộ đối chiếu nhỏ, không phải kết luận mọi lỗi đều do một tham số.

Thêm `ReasoningProfileAdapter` **opt-in**, dùng nguyên model/template hiện có, native thinking512 trong tổng1024token và JSON schema cấu trúc. Request và validator cùng giới hạn1024. Giữ riêng reasoning; đáp án cuối không được sửa, trích xuất, bọc lại hay điền giá trị. Require native reasoning thật, complete stop/usage/model identity, bounded HTTP/SSE, single-use và joined cancellation.

Lượt đầy đủ đầu sau sửa budget đo CORE41/42, UNRESTRICTED42/42. CORE còn trả giá trị biểu thức khi câu hỏi yêu cầu đánh giá mệnh đề về biểu thức. Thêm hostoption `boolean_answer_contract=True`, **defaultFalse**, làm rõ sự khác nhau đó chỉ khi trustedshapeanswerboolean. Clarification chung không chứa case ID, biểu thức thật, đáp án, oracle hay feedback. Bộ12câu mới/profile cân bằng6True/6False đều đúng trước khi chốt bộ42mới. Các input không chọn option, schema không phải boolean và hệ thống/template/default cũ giữ nguyên.

[ADR135](ADR/135-bounded-request-local-reasoning-comparison.md), [ADR136](ADR/136-opt-in-bounded-reasoning-profile-decoding.md), [ADR137](ADR/137-host-selected-boolean-answer-contract.md) ghi rõ giả thuyết, priority/dependency/effort/risk, token/resource policy, migration và rollback. Không đổi lựa chọn model hay tải weights/package mới.

## Các lượt đo, kể cả lỗi của lượt nghiên cứu đầu

| Lượt đã chốt trước inference | Số model request | Kết quả được giữ nguyên |
|---|---:|---|
| Paired12câu/profile, direct/thinking |48| Direct7/12mỗi profile. Research caller gửi1024nhưng validator giữ512: first accepted thinking0/12, diagnosticINVALID. Raw-wire replay theo declared1024cho native facts12/12mỗi profile; không sửa first rows |
| Full reasoning đầu, chưa chọn boolean contract |86=84scored+2cancel| CORE41/42, UNRESTRICTED42/42; aggregateFAIL vì một câu boolean |
| Qualification boolean mới,6True/6False |26=24scored+2cancel| CORE12/12, UNRESTRICTED12/12; require actual contract/reasoning và lifecycle |
| Full selected-contract mới |86=84scored+2cancel| **CORE42/42, UNRESTRICTED42/42; aggregatePASS** |

Tổng246firstgenerations=240scored+6plannedcancel. Không neuralretry, không tái sinh câu cũ để nâng điểm; chỉ có các cặp/streamreplicates đã khai báo trước. Mọi lỗi đầu, source/test đã chạy, rawrequest/nativewire, freeze và audit đều được giữ. Lỗi512/1024do tôi đưa vào research subclass đã sửa và có boundary tests513/540/1024/1025; không được biến nó thành một lượt firstPASS hồi tố.

Các cohort sau thay input/source labels/numbers/images/codes/sequences. Chỉ bộ direct/thinking là so sánh cùng câu; không diễn giải chênh lệch giữa các cohort thành phần trăm năng lực tổng quát hoặc causal effect duy nhất.

## Full gate cuối và chi phí

| Nhóm | CORE | UNRESTRICTED |
|---|---:|---:|
| Reasoning |8/8|8/8|
| Python |8/8|8/8|
| Source-policy |8/8|8/8|
| Vietnamese |6/6|6/6|
| Fresh image |5/5|5/5|
| Near32Kretrieval |4/4|4/4|
| Streaming |3/3|3/3|
| Format và exact facts |**42/42**|**42/42**|

Đủ cancellation/slotretirement,5/5distinctprovenance, exit0/reaped/guardNone và originalbaseline. Giữ yêu cầu42/42mỗi profile, không hạ AC. Verifier tái dựng nguyên request/template/schema/ảnh/tham số và native first values. Context được kiểm tra bằng40vocabulary-onlyrecounts: minimalprefix/maximaltail, vị trí needle, token calibration, nativeprompt usage và prompt+1024fit32768. Recount không loadweights/generate và không được gọi là receipt trước inference.

Full cuối: tổng thời gian42request **319.944s CORE /314.539s UNRESTRICTED**, không gồm coldload/cancel/retirement;21375/21601outputtokens gồm reasoning+final. Whole-native-worker peakRSS RAM khoảng**9.73GiB/9.58GiB**, sampledpeakVRAM **8884MiB/8548MiB**. Đây là chi phí cả process, không phải model-only size hoặc hard CUDAaddress-space cap.

Trên bộ12câu text matched, thinking tốn khoảng84–86s và6444–6458tokens so với5.6–6.2s và277–287tokens direct. Chất lượng đổi lấy thời gian/token; không suy ra productionSLO từ các mẫu này.

## Code, kiểm thử và phạm vi giữ nguyên

Component: `src/infrastructure/inference/reasoning_profile.py`. Caller phải chọn adapter và `boolean_answer_contract=True` một cách tường minh; không có route/default/API activation. Các runner đã có executionreceipt từ chối chạy lại. Native test workers đã đóng, không tạo dịch vụ inference thường trực.

**568 scoped tests PASS /0FAIL/0ERROR/0SKIP,6.17s.** Bao gồm native-shaped HTTP/SSE, upper-budget regression, true/false/value/proposition controls, wrong-fact denials, request/image/source/context tamper controls, lifecycle, actual vocabulary-count proof và delivery allowlists. Native84câu thật không được cộng thành unittest. RuffE4/E7/E9/F, format và Englishmodule/function/classdescriptions đạt cho20activePythonfiles. Không gọi đây là fullsuite mới.

Current732appfiles: all730priorfiles byte-identical; chỉ hai file adapter/test mới được phát triển. Full5674/728files vẫn là lịch sử. Audit bảo toàn916/917olderprotectedfiles; ngoại lệ duy nhất là MODEL_REGISTRYdocumentationdelta đã được duyệt trước nhiệm vụ này. All176originalinputs, model/config/runtime pins và15container identities/images/ports giữ nguyên, nativeprocess0. Không Vault/database/Qdrant/data/ACL/service/provider change hoặc freshdatabaseaudit claim.

OriginalD14compositesCORE66.5/UNRESTRICTED52, MQ001/002scores, earlier functionalFAILs và raw outputs không đổi. D14-SEMANTIC-001 được **VERIFIED_LOCAL_OPT_IN** trên boundedfreshgate này; broadunattendedcoding, realdevice, model/voice/license/product, D70actualhearing0/24 và release vẫn là gate riêng. Không modelreplacement/adoption, push/tag/deploy.

## Bàn giao và rollback

Full-file bundle `data/backups/local-assistant-d14-semantic-20261026-full-files.zip`, receipt `.receipt.json` cùng thư mục. Gói giữ1.789extras của bản review trước, toàn bộ currentGitfileversions từ7fa4756, và các firststudy artifacts/source snapshots/recounts được chọn rõ. Receipt/manifest ghi commit, từng byte/SHA/CRC và tổng246generation; builderoutput được loại khỏi input, đối chiếu lại sau khi process kết thúc. Không weights/SDK/cache/dump/secrets/checkpoints; dòngIDEriêng đầu devlog vẫn ngoàiGit/ZIP.

Rollback: không chọn component/option mới; defaultpath cũ và mọi dữ liệu không cần migration. Không xóa first evidence hoặc chạy lại failure chỉ để tạo điểm đẹp.
