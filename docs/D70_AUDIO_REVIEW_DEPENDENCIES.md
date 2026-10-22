# D70 — Khả năng đánh giá audio và nguồn giấy phép

**Mục đích:** Ghi các phần việc D70 có thể xác minh tiếp, cùng một phương án mở khóa việc đánh giá audio thật. Không đổi AC, model hoặc kết quả benchmark đã chốt.

## Dịch vụ đã cấu hình

Đã kiểm tra readonly các path/field name của14secret hiện có trong một KV-v2 mount. Chưa tìm thấy metadata provider/audio cho một evaluator sẵn dùng. Không ghi giá trị secret, không sửa Vault và không gửi audio ra ngoài. Kết quả chỉ phản ánh các record đã kiểm tra; không suy luận chủ dự án không có tài khoản ở nơi khác.

## Dịch vụ nhận audio công khai: đang qualification

Đã xác minh API bình thường của [demo Qwen chính thức](https://huggingface.co/spaces/Qwen/Qwen2.5-Omni-7B-Demo). Serving code dùng alias `qwen-omni-turbo`; tên Space7B không chứng minh backend là checkpoint7B nguyên bản. Không cần model download hoặc credential của chủ dự án. [ADR-099](ADR/099-bounded-public-audio-review-qualification.md) chốt scope synthetic controls, blind inputs, bounds và first-result retention trước inference. Online reviewer không được gọi là khả năng nghe trực tiếp của assistant hoặc human MOS.

40new client controls/158related PASS0.39s, protocol626source/all624prior nguyên byte và5controls đã freeze. Chưa có inference/qualification result tại checkpoint này; chỉ khi control checks đạt mới xem xét24audio benchmark. Giữ AC tại D70 và ADR-097 REJECTED.

## Phương án local bổ sung vẫn cần duyệt

[ADR-098](ADR/098-proposed-isolated-audio-reviewer.md) đề xuất thử một **AI reviewer nhận audio thật**, chạy riêng với Qwen2.5-Omni-3B nguyên bản. Đã pin revision/shard sizes/hashes và đọc giấy phép; chưa tải weights hoặc cài runtime. Đây là công cụ đánh giá bổ sung, không thay CORE/ASR/TTS hoặc ứng viên registry. Khoảng11.97GB là disk weights; RAM/latency và năng lực đánh giá tiếng Việt còn chưa đo.

Approval chỉ cho phép thử và đánh giá bằng AI có provenance rõ, không xác nhận sẵn năng lực reviewer hoặc human MOS. D70 vẫn phải đủ AC; nếu qualification/tiếng Việt/coverage không đạt thì vẫn mở. ADR-097 vẫn REJECTED, D71 chưa bắt đầu. [Metadata cụ thể](evidence/d70-audio-reviewer-proposal-metadata.json).

## Nguồn Lessac đã truy cập được

Các model card Piper đã giữ nguyên cho thấy vais1000 fine-tuned từ Lessac medium, còn card Lessac dẫn bộ dữ liệu Blizzard2013. Chuỗi nguồn này được ghi theo card, chưa phải xác minh toàn bộ lịch sử training.

Lượt tra cứu mới đã đọc được [giấy phép dữ liệu CSTR/Voice Factory/Lessac](https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html): mục1.1 và3.2 giới hạn quyền dùng bộ dữ liệu cho nghiên cứu và loại trừ mục đích thương mại. Không điền/nộp biểu mẫu chấp thuận hoặc tải corpus. Ngày hiển thị trên form không được coi là ngày công bố giấy phép.

**Ảnh hưởng được suy luận:** thông tin CC-BY4.0 của corpus vais1000 và MIT ở repository không tự chứng minh quyền thương mại đầy đủ cho voice fine-tuned. Phạm vi áp dụng tới weights/output cần làm rõ riêng; chưa kết luận rằng toàn bộ model Piper mang cùng giấy phép dataset hoặc rằng private benchmark được phép triển khai thương mại. [Bằng chứng provenance](evidence/d70-piper-lessac-license-followup.json). Không thay model card/config/weights đã freeze hoặc đổi giọng sang voice khác.

## Trạng thái

D70 giữ **IN PROGRESS**, chưa có nhận xét nghe mới hoặc model/helper được phê duyệt. Đang thử qualify API audio công khai theo ADR-099; nếu không đạt thì chưa có evaluator được xác nhận. Local fallback theo ADR-098 vẫn cần phê duyệt riêng. Cả hai giữ nguyên AC tại D70. Benchmark cũ,24native outputs và original model/data/runtime tiếp tục được bảo toàn.


### Lỗi transport đầu được giữ nguyên

Upload/prediction đã nhận receipt; event stream trả `404: Session not found.` nên chưa có judgement hoặc capability PASS. Source Gradio5.23.1 xác nhận custom session khác event_id gây đọc sai queue ở simple-call API. Giữ packet đầu1of5/0controlsPASS, toàn rawSSE/freeze/source snapshot trước khi sửa riêngtransport. Remote completion của lượt đầu chưa xác minh được. Việc sửa protocol không đổi prompt/control/AC hoặc rescore24native waveforms.
