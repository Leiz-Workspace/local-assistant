# D70 — Khả năng đánh giá audio và nguồn giấy phép

**Mục đích:** Ghi các phần việc D70 có thể xác minh tiếp, cùng một phương án mở khóa việc đánh giá audio thật. Không đổi AC, model hoặc kết quả benchmark đã chốt.

**Quyết định mới nhất2026-10-23:** Chủ dự án duyệt **“Duyệt một lượt diagnostic ADR-103”**. Lượt đã chạy39.749s/exit0/no timeout, raw `yes/no/no/yes` khớp4control và4EOS. Audit phát hiện helper mount vào worker còn chứa metadata/prepare code phía cha: **không coi là strict protocol PASS**, dù worker không truyền các reference đó vào input model. Đã tách pure runtime, native namespace probe PASS; chưa chạy lại original model. Scope một lượt đã dùng, diagnostic modes đóng lại; chỉ imports/load còn mở.249TTSrelated PASS7.63s/Ruff PASS. [Bằng chứng](evidence/d70-presence-diagnostic-first.json). D70 mở, reviewer NOT QUALIFIED/D71 chưa bắt đầu.


## Dịch vụ đã cấu hình

Đã kiểm tra readonly các path/field name của14secret hiện có trong một KV-v2 mount. Chưa tìm thấy metadata provider/audio cho một evaluator sẵn dùng. Không ghi giá trị secret, không sửa Vault và không gửi audio ra ngoài. Kết quả chỉ phản ánh các record đã kiểm tra; không suy luận chủ dự án không có tài khoản ở nơi khác.

## Dịch vụ nhận audio công khai: chưa đạt qualification

Đã xác minh API bình thường của [demo Qwen chính thức](https://huggingface.co/spaces/Qwen/Qwen2.5-Omni-7B-Demo). Serving code dùng alias `qwen-omni-turbo`; tên Space7B không chứng minh backend là checkpoint7B nguyên bản. Không cần model download hoặc credential của chủ dự án. [ADR-099](ADR/099-bounded-public-audio-review-qualification.md) chốt scope synthetic controls, blind inputs, bounds và first-result retention trước inference. Online reviewer không được gọi là khả năng nghe trực tiếp của assistant hoặc human MOS.

Đã thử cả demo trên và [Qwen3.5-Omni-Offline-Demo](https://huggingface.co/spaces/Qwen/Qwen3.5-Omni-Offline-Demo), dùng alias `qwen3.5-omni-plus`. “Offline” là tên interface batch-media; đây vẫn là dịch vụ cloud. Backend checkpoint/seed không được xác minh. Mọi packet dừng ở control đầu tiên, chưa gửi bốn control còn lại hoặc bất kỳ waveform nào trong24benchmark outputs.

| Lượt được giữ riêng | Kết quả quan sát | Ý nghĩa |
| --- | --- | --- |
| Qwen2.5, transport đầu | SSE `404: Session not found.` | Lỗi custom session của client; đã xác minh bằng source Gradio5.23.1, giữ nguyên first failure/source/freeze |
| Qwen2.5, transport sửa đúng event-linked session | SSE `event:error`, `data:null` | Không có usable judgement; không suy đoán nguyên nhân backend |
| Qwen2.5, availability probe theo default system prompt | Cùng error event,2.799s | Probe riêng, không phải quality result |
| Qwen3.5, schema/interface thực tế | SSE `event:error`, `data:null` | Chưa đủ qualification; không review24outputs |
| Qwen3.5, SDK Gradio chính thức, hai workers | Upload/queue/SSE HTTP200; hết120s, exit124 | HTTP success không chứng minh có audio judgement; remote completion/cancellation chưa xác minh |

SDK diagnostic dùng uv environment riêng, Python3.12.3/gradio-client1.13.3, không sửa app hoặc runtime đánh giá cũ. Giữ cả setup lỗi ở environment3.14 ban đầu, local empty-token protocol error và timeout của cấu hình một worker. Đối chiếu SDK cho thấy một worker làm request và SSE reader chờ chung executor; hai workers sửa riêng contention này, nhưng vẫn chưa nhận được kết quả trong giới hạn. Không gọi các lỗi client/setup là lỗi chất lượng model, không gọi timeout là model không hiểu audio. Chưa xác minh provider đã dừng hoặc xóa dữ liệu đã gửi.

**42client tests mới/160TTS related PASS0.39s**, một expected ZIP duplicate warning từ test cũ; Ruff PASS. Đây là kiểm thử các TTS scripts liên quan, không phải full-suite626source. [Availability/integrity audit](evidence/d70-audio-evaluator-availability-audit.json) xác minh626source/toàn bộ624prior nguyên byte,176original audit inputs và23475original D70 SDK entries;24judgements gốc vẫn null/chưa nghe. Các owned SDK Python processes đã kết thúc. Không có local reviewer weights, TTS rerun hoặc model selection. Giữ AC tại D70 và ADR-097 REJECTED.

## Evaluator local đã chạy audio; chưa đạt qualification

Chủ dự án đã trả lời **“Cho phép thử evaluator local theo ADR-098”**. [ADR-098](ADR/098-proposed-isolated-audio-reviewer.md) được duyệt cho nghiên cứu riêng có giới hạn; đây là evaluator bổ sung, không thay CORE/ASR/TTS hoặc registry models. Đúng revision f75b40e.../16artifacts đã tải và xác minh, ba shard11,972,663,208bytes disk; SDK uv riêng23382entries đã freeze. Không dùng Research License thành quyền thương mại.

Lỗi load12GiB đầu được giữ nguyên. Theo chỉ thị tiếp tục sau đề xuất ADR-100, đã chạy đúng16GiB virtual-address lane/18GiB preflight headroom, native load PASS. First9audio controls506.293s/exit0 sinh đến192tokens do EOS cấp ngoài rỗng; đã xác minh original Thinker/tokenizer EOS151645/pad151643 và sửa riêng runner, không vá model hoặc đổi prompt/nhãn.

**Corrected9control hoàn tất173.094s/exit0,9EOS complete, nhưng0validJSON.** Token của mỗi first turn và audio features khớp nguyên lượt trước9of9; raw silence/noise vẫn được mô tả là speech và severe clipping là natural. Không sửa response/parser/labels để biến thành PASS. Đây là evaluator nhận audio thật nhưng **NOT QUALIFIED** cho nhiệm vụ này, chưa có24case auditory/naturalness review.39new/199TTSrelated PASS0.44s/Ruff PASS; [final632source/all626pre-evaluator bytes/originalSDK/model-data-runtime audit](evidence/d70-local-reviewer-final-integrity-audit.json) PASS. [Báo cáo đầy đủ](D70_LOCAL_AUDIO_REVIEW.md).

Trial local đã hoàn tất trong giới hạn; dependency D70 vẫn mở vì cần reviewer đạt các control năng lực. Chưa chọn/tải helper khác, đổi model default hoặc tự retune failed controls. Giữ đầy đủ first failure/preapproval metadata như lịch sử; ADR-097 vẫn REJECTED, D71 chưa bắt đầu.

## Nguồn Lessac đã truy cập được

Các model card Piper đã giữ nguyên cho thấy vais1000 fine-tuned từ Lessac medium, còn card Lessac dẫn bộ dữ liệu Blizzard2013. Chuỗi nguồn này được ghi theo card, chưa phải xác minh toàn bộ lịch sử training.

Lượt tra cứu mới đã đọc được [giấy phép dữ liệu CSTR/Voice Factory/Lessac](https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html): mục1.1 và3.2 giới hạn quyền dùng bộ dữ liệu cho nghiên cứu và loại trừ mục đích thương mại. Không điền/nộp biểu mẫu chấp thuận hoặc tải corpus. Ngày hiển thị trên form không được coi là ngày công bố giấy phép.

**Ảnh hưởng được suy luận:** thông tin CC-BY4.0 của corpus vais1000 và MIT ở repository không tự chứng minh quyền thương mại đầy đủ cho voice fine-tuned. Phạm vi áp dụng tới weights/output cần làm rõ riêng; chưa kết luận rằng toàn bộ model Piper mang cùng giấy phép dataset hoặc rằng private benchmark được phép triển khai thương mại. [Bằng chứng provenance](evidence/d70-piper-lessac-license-followup.json). Không thay model card/config/weights đã freeze hoặc đổi giọng sang voice khác.

## Trạng thái

D70 giữ **IN PROGRESS**, chưa có nhận xét nghe mới hoặc evaluator đủ qualification. Đã dừng các lượt API công khai trong giới hạn; không có polling nền hoặc retry vô hạn. Evaluator local đã được nạp và chạy audio dưới cap16GiB sau khi agent diễn giải sai continuation thành approval, trước câu trả lời từ chối rõ ràng; không gọi các lượt đó owner-approved. Reviewer không đạt kiểm tra năng lực dù đã sửa EOS runner; chưa có reviewer đủ điều kiện. Cũng có thể dùng một API audio sẵn có nếu chủ dự án cung cấp provider/Vault path. Cả hai giữ nguyên AC tại D70. Benchmark cũ,24native outputs và original model/data/runtime tiếp tục được bảo toàn; D71 chưa bắt đầu.

## ADR-101: chỉ cho phép nạp và kiểm tra toàn vẹn

Nghiên cứu metadata ban đầu được giữ nguyên tại [evidence](evidence/d70-12g-pread-feasibility.json). Sau phê duyệt rõ ràng, [ADR-101](ADR/101-proposed-pread-loading-within-12gib.md) đã được triển khai riêng cho load/integrity: native `pread`, meta-schema coverage và byte/storage fidelity, không đổi SDK/weights/cap.221TTSrelated PASS6.24s gồm tiny fixture bằng SDK thật trong namespace12GiB;13controls tăng thêm so với208 trước đó.

Lượt nạp weights gốc dừng tại preflight headroom17.65GiB <18GiB, exit1 trước khi tạo worker/output. [Kết quả](evidence/d70-pread-load-trial.json) không có model RSS hoặc kết luận fit12GiB. Giữ CORE loaded; không hạ ngưỡng/tăng cap/retry. P2 memory investigation còn chờ headroom hợp lệ và kết quả nạp thật; P1 reviewer-quality vẫn chưa đạt. Không chạy lại semantic controls/review24outputs, đổi model hoặc đóng D70/D71.


### Lỗi transport đầu được giữ nguyên

Upload/prediction đã nhận receipt; event stream trả `404: Session not found.` nên chưa có judgement hoặc capability PASS. Source Gradio5.23.1 xác nhận custom session khác event_id gây đọc sai queue ở simple-call API. Giữ packet đầu1of5/0controlsPASS, toàn rawSSE/freeze/source snapshot trước khi sửa riêngtransport. Remote completion của lượt đầu chưa xác minh được. Việc sửa protocol không đổi prompt/control/AC hoặc rescore24native waveforms.

## ADR-102: nạp weights gốc trong cap12GiB đã PASS

Sau explicit approval headroom14GiB/cap12GiB, first original-weight pread load hoàn tất26.471s/exit0, không timeout, đủ1442tensors và9,406,928,896bytes. Child byte/storage/shape/device/dtype accounting và parent full-payload audit đều PASS; CORE cùngPID/start/command/text recovery trước-sau PASS. RSS peak9.333GiB RAM, VmPeak10.393GiB virtual; không inference/VRAM/minimumRAM claim.222TTSrelated PASS6.00s/Ruff PASS. [Evidence](evidence/d70-pread-14g-headroom-load.json), [ADR-102](ADR/102-proposed-headroom-for-retained-12gib-trial.md). P2 memory-loading milestone hoàn tất; không tự retry hoặc mở P1 audio gate.

Readonly9source-control diagnosis xác nhận clip silence vẫn80000exactzeros, nguồn/hashes/masks giữ nguyên. SDK native chọn các frame hợp lệ bằng mask; feature_shape có padding không tự chứng minh lỗi conditioning. Chưa tìm thấy lỗi runner mới đủ căn cứ giải thích các semantic failures. [Diagnosis](evidence/d70-headroom-and-control-diagnosis.json) chỉ là stats/source inspection, không nghe hoặc naturalness.

## ADR-103 — Đã thực hiện một lượt, không mở naturalness gate

Owner approved2026-10-23; actual4first answers match presence controls,39.749s/no timeout/4EOS/12GiB cap. Post-audit namespace deviation (parent preparation metadata remained in mounted helper) prevents strict protocol acceptance; source split plus native bwrap probe fix is tested without model rerun.249TTSrelated PASS7.63s; diagnostic scope consumed/modes closed, original9failures/24nulljudgements preserved. [Evidence](evidence/d70-presence-diagnostic-first.json). P1 next is assessed AUDIO-EVAL-QUALITY-PROTOCOL-001, not scheduled inference or D71 advance.


## 2026-10-23 continuation: tested quality protocol, execution blocked

[ADR-104](ADR/104-proposed-heldout-quality-and-conditional-blind-review.md) concretely prepares twelve new held-out presence/language/severe-corruption/tie controls and, only after strict first-control/source/runtime/parent-metadata recomputation, one blind48-observation review of the retained24complete16k signals. All four new modes remain blocked under imports/load-only policy; consumed ADR-103 scope is not reused.291TTSrelated PASS12.40s/Ruff PASS and native processor-only two-audio/real namespace checks; no original-model loading/generation or actual packet preparation. Prior9failures, limited4factual matches/namespace deviation and all24pending original judgements are unchanged. Fixed12GiB/14GiB/sameCORE/no downloads/default changes. Severe pair controls do not establish absolute naturalness accuracy, VI phonetics expertise or human MOS; results cannot automatically close unchanged D70 AC or advance D71. One entire conditional campaign is proposed for scope approval, rather than separate permission at every stage. [Evidence](evidence/d70-quality-protocol-proposal.json).


## 2026-10-23 ADR-104 approved campaign completed; controls fail

Owner explicitly approved **“Duyệt campaign ADR-104”**. [Actual first evidence](evidence/d70-quality-campaign-first.json), [approved freeze](evidence/d70-quality-campaign-approved-freeze.json). One original-model control worker completed93.437s/exit0/no timeout/12EOS; **8of12strict matches**, with presence4/4, language1/2 (raw `English` violates lowercase protocol) and pair comparisons3/6. Three pair semantic mismatches include an identical EN pair judged second and two damaged-first pairs judged second. Do not normalize labels/parser or rerun these controls. Input-only replay independently reproduces all12feature hashes/masks/token counts, ties have identical features and damaged pairs distinct features; full1442tensor parent fidelity verifies. This replay loads no model or generates a judgement.

Observed RSS9.723GiB RAM/VmPeak10.422GiB virtual/CPU156.821s within approved12GiB/14GiB policy; no minimum-RAM/VRAM or quality certification. Failed gate prevents preparation/execution of conditional24output review, so all24original pending labels remain unchanged. Four campaign modes closed, imports/load-only restored, scope consumed.304TTSrelated PASS12.63s/0SKIP/Ruff PASS;642sources/640approved unchanged,30priorD70JSON/917protected/176inputs/23475+23382SDK/16artifacts and original system/data/security/sameCORE audit preserved. No download/model/default/data/service change. D70 naturalness OPEN/D71 NOT STARTED; actual auditory competence is still inadequate for the accepted gate. Campaign milestone complete with failure; next assessed P1 is AUDIO-EVAL-REVIEWER-RELIABILITY-001, no new inference scheduled.


## 2026-10-23 continuation: specialist route prepared, external media scope pending

[Reviewer reliability assessment](D70_REVIEWER_RELIABILITY_ASSESSMENT.md), [ADR-105](ADR/105-proposed-specialist-public-auditory-review.md), [proposal evidence](evidence/d70-specialist-review-proposal.json). Original ADR-104 strict8of12failure remains unchanged; no rerun or parser/label tuning. Investigation distinguishes model judgement failure, input correctness and interface availability. Native meta-only counting agrees with the analytic lower bound:7,615,616,512text parameters/15,231,233,024BF16bytes≈14.185GiB, before modalities/runtime, so no local native7Bweights are downloaded under12GiB cap. This is not measured RAM/VRAM.

Author-linked specialist demo reports RUNTIME_ERROR. A community SpeechJudge demo reports RUNNING and its exact public metadata/schema/source interface has been checked without audio; remotely loaded weights/seed/resources and retention remain unattested, VI naturalness unqualified. Existing official Qwen frontends still report RUNNING but prior inference failures are not overturned by metadata. No new model/provider is selected or deployed.

New standalone client and fixtures prepare one proposed18control/conditional24comparison campaign, covering all24original outputs in both orientations if controls pass. Guard defaults false; no real packet, audio upload, prediction, weight/package download or new local model inference.34new/338TTSrelated PASS18.10s/0FAIL/0SKIP/Ruff PASS; all642prior source bytes unchanged/current645,32priorD70JSON/917protected/176inputs/23475+23382SDK/16artifacts/original system/data/sameCORE preserved. Explicit new-recipient permission is needed only before sending neutral test audio/authored text to that community endpoint; one campaign approval would cover both conditional stages. D70 AC OPEN/D71 NOT STARTED.
