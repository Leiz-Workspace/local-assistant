# D70 — Khả năng đánh giá audio và nguồn giấy phép

**Mục đích:** Ghi các phần việc D70 có thể xác minh tiếp, cùng một phương án mở khóa việc đánh giá audio thật. Không đổi AC, model hoặc kết quả benchmark đã chốt.

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

## Phương án local bổ sung vẫn cần duyệt

[ADR-098](ADR/098-proposed-isolated-audio-reviewer.md) đề xuất thử một **AI reviewer nhận audio thật**, chạy riêng với Qwen2.5-Omni-3B nguyên bản. Đã pin revision/shard sizes/hashes và đọc giấy phép; chưa tải weights hoặc cài runtime. Đây là công cụ đánh giá bổ sung, không thay CORE/ASR/TTS hoặc ứng viên registry. Khoảng11.97GB là disk weights; RAM/latency và năng lực đánh giá tiếng Việt còn chưa đo.

Approval chỉ cho phép thử và đánh giá bằng AI có provenance rõ, không xác nhận sẵn năng lực reviewer hoặc human MOS. D70 vẫn phải đủ AC; nếu qualification/tiếng Việt/coverage không đạt thì vẫn mở. ADR-097 vẫn REJECTED, D71 chưa bắt đầu. [Metadata cụ thể](evidence/d70-audio-reviewer-proposal-metadata.json).

## Nguồn Lessac đã truy cập được

Các model card Piper đã giữ nguyên cho thấy vais1000 fine-tuned từ Lessac medium, còn card Lessac dẫn bộ dữ liệu Blizzard2013. Chuỗi nguồn này được ghi theo card, chưa phải xác minh toàn bộ lịch sử training.

Lượt tra cứu mới đã đọc được [giấy phép dữ liệu CSTR/Voice Factory/Lessac](https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html): mục1.1 và3.2 giới hạn quyền dùng bộ dữ liệu cho nghiên cứu và loại trừ mục đích thương mại. Không điền/nộp biểu mẫu chấp thuận hoặc tải corpus. Ngày hiển thị trên form không được coi là ngày công bố giấy phép.

**Ảnh hưởng được suy luận:** thông tin CC-BY4.0 của corpus vais1000 và MIT ở repository không tự chứng minh quyền thương mại đầy đủ cho voice fine-tuned. Phạm vi áp dụng tới weights/output cần làm rõ riêng; chưa kết luận rằng toàn bộ model Piper mang cùng giấy phép dataset hoặc rằng private benchmark được phép triển khai thương mại. [Bằng chứng provenance](evidence/d70-piper-lessac-license-followup.json). Không thay model card/config/weights đã freeze hoặc đổi giọng sang voice khác.

## Trạng thái

D70 giữ **IN PROGRESS**, chưa có nhận xét nghe mới hoặc evaluator đủ qualification. Đã dừng các lượt API công khai trong giới hạn; không có polling nền hoặc retry vô hạn. Local fallback theo ADR-098 vẫn là đề xuất bổ sung model nghiên cứu ngoài tập đã thống nhất, cần phê duyệt riêng trước tải weights. Cũng có thể dùng một API audio sẵn có nếu chủ dự án cung cấp provider/Vault path. Cả hai giữ nguyên AC tại D70. Benchmark cũ,24native outputs và original model/data/runtime tiếp tục được bảo toàn; D71 chưa bắt đầu.


### Lỗi transport đầu được giữ nguyên

Upload/prediction đã nhận receipt; event stream trả `404: Session not found.` nên chưa có judgement hoặc capability PASS. Source Gradio5.23.1 xác nhận custom session khác event_id gây đọc sai queue ở simple-call API. Giữ packet đầu1of5/0controlsPASS, toàn rawSSE/freeze/source snapshot trước khi sửa riêngtransport. Remote completion của lượt đầu chưa xác minh được. Việc sửa protocol không đổi prompt/control/AC hoặc rescore24native waveforms.
