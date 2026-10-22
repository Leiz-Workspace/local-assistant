# D70 — Khả năng đánh giá audio và nguồn giấy phép

**Mục đích:** Ghi các phần việc D70 có thể xác minh tiếp, cùng một phương án mở khóa việc đánh giá audio thật. Không đổi AC, model hoặc kết quả benchmark đã chốt.

**Quyết định mới nhất2026-10-22:** Chủ dự án duyệt **“Cho phép thử ADR-101, giữ cap 12 GiB”** cho imports/nạp/kiểm tra toàn vẹn; `qualify`/`review` và tạo packet/refresh inventory vẫn bị chặn. ADR-100 tiếp tục REJECTED. Loader native `pread` đã triển khai,221TTSrelated kiểm thử PASS, gồm tensor giả nhỏ qua SDK thật trong namespace12GiB. Lượt nạp weights gốc bị preflight chặn: MemAvailable18,946,437,120bytes≈17.65GiB < ngưỡng18GiB; chưa khởi chạy worker nạp model, chưa chứng minh fit12GiB. Không tự hạ ngưỡng, tăng cap, dừng CORE hoặc retry. [Bằng chứng](evidence/d70-pread-load-trial.json). Các lượt16GiB lịch sử vẫn không được coi là owner-approved. D70 mở, D71 chưa bắt đầu.

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
