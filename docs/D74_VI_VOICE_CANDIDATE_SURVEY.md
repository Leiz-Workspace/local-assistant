# D74 — Khảo sát giọng nữ miền Bắc và phương án benchmark

**Mục đích:** Đưa ra shortlist có nguồn, chi phí tài nguyên và đề xuất thử nghiệm để chủ dự án duyệt; không tự thay model đang thống nhất.

**Ngày:** 2026-11-03, Asia/Ho_Chi_Minh. **Trạng thái:** SURVEY / PROPOSAL COMPLETE; DOWNLOAD / IMPLEMENTATION / BENCHMARK NOT APPROVED OR RUN. [ADR-154](ADR/154-proposed-isolated-vietnamese-voice-feasibility-campaign.md), [protocol](D74_VI_VOICE_BENCHMARK_PROTOCOL.md), [evidence/hash nguồn](evidence/d74-vi-candidate-survey-20261103.json).

## Đề xuất để duyệt

Ưu tiên **đánh giá VieNeu-TTS v3 Turbo CPU/ONNX FP32**, với hai preset **Trúc Ly** và **Ngọc Huyền**. Cả card đúng revision và manifest voice đều gắn hai preset này là nữ/Bắc/natural. Đây là **nhãn tác giả**, chưa phải xác nhận nghe của chủ dự án. Chưa chọn một voice/model cho sản phẩm. [Model card](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo/blob/61b85e3d937fbbacb387714180e8182823512523/README.md), [manifest](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo/blob/61b85e3d937fbbacb387714180e8182823512523/gguf/voices/manifest.json).

Tác giả khai báo Apache-2.0 và nói rõ phạm vi preset/output cùng quyền nguồn giọng trong FAQ. Vẫn cần giữ notices của đúng SDK, preset, codec và phonemizer; đây là thông tin do publisher cung cấp, không phải chứng nhận pháp lý độc lập. Card ghi23preset trong khi manifest chứa25; SDK/source cũng có tên được đổi. Vì vậy qualification phải kiểm tra đúng tên và asset tại revision đã pin, không lấy default giọng nam hoặc tên alias làm bằng chứng đã chọn đúng giọng nữ Bắc.

## Shortlist và lý do

| Ứng viên | Bằng chứng phù hợp và hạn chế | Disposition |
|---|---|---|
| **VieNeu-TTS v3 Turbo**, revision `61b85e3…` | Có preset nữ Bắc theo card/manifest; CPU ONNX và codec riêng; chưa đo tốc độ/giọng trên máy này | **Đề xuất một trial riêng**, FP32 trước, không tự chọn backend hoặc int8 |
| VieNeu-TTS v3 Nano, revision `aba295e…` | Card có giọng nữ Bắc nhưng ghi preview, âm sắc/prosody yếu hơn, không frame-streaming; RTF upstream không phải kết quả local | Dự phòng trên giấy; **không tải/chạy trong proposal này**. [Card](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Nano/blob/aba295eb96a6fa6003ebe417cc1f2802a7adc1dc/README.md) |
| VieNeu-TTS-0.3B, revision `4c4056e…` | Card hiện có voice nữ Bắc và Apache-2.0; revision cũ được search trả về từng ghi CC-BY-NC. Không suy license/version giữa GGUF cũ và bản hiện tại | Dự phòng; cần giải quyết đúng artifact/runtime/provenance, không trộn với v3. [Card hiện pin](https://huggingface.co/pnnbao-ump/VieNeu-TTS-0.3B/blob/4c4056e33bea543dd62115abc84c1612be8166c9/README.md) |
| F5-TTS Vietnamese ViVoice, revision `5c14cdd…` | Card CC-BY-NC-SA-4.0; checkpoint được liệt kê5.394GB, cần reference/SDK/vocoder phù hợp; chưa có preset nữ Bắc được kiểm chứng ở đây | Không ưu tiên trial đầu; không mặc định NC ngăn mọi thử nghiệm cá nhân hoặc coi code license thay cho weights license. [Card](https://huggingface.co/hynt/F5-TTS-Vietnamese-ViVoice/blob/5c14cdd4e3f62b69e75140558bea2b2e293ee8f1/README.md) |
| viXTTS, revision `c06f437…` | Card CPML; nêu hạn chế câu VI dưới10từ và tương thích thư viện; metadata API chỉ ghi `other` | Không ưu tiên lượt đầu, cần đối chiếu LICENSE chính xác; không khẳng định đáp ứng accent/latency. [Card](https://huggingface.co/capleaf/viXTTS/blob/c06f4378883110615941aab481532a9802440b05/README.md) |

Đây là thứ tự **khảo sát tính khả thi**, không phải bảng chất lượng đã benchmark. Không tải audio mẫu, weights, codec, embedding preset hoặc gửi text/audio vào demo. Các fork/Space tìm được không dùng làm nguồn chính để chốt model. Mọi số liệu publisher về TTFA/RTF chỉ là thông tin trên phần cứng/protocol của họ; không dùng để tuyên bố đạt4giây trên hệ thống này.

## Nút thắt ASR đã thấy trong dữ liệu cũ

Đã tính lại trên20utterance VI ungated D72, không inference mới:

| ASR đã có | Prediction wall min / median / max | Số câu riêng ASR >4s | WER VI đã đo |
|---|---:|---:|---:|
| Qwen3-ASR-0.6B | 2.526 / 5.654 / 10.086 s | **17/20** | 7.614% |
| Whisper small CT2 | 1.697 / 2.274 / 2.914 s | **0/20** | 20.474% |

[Recomputation và hash worker/nguồn](evidence/d74-existing-asr-latency-analysis-20261103.json). Timer `transcribe` tách khỏi import/load, chưa gồm CORE/TTS/playback. Đây là các câu cũ và thiết lập CPU khác nhau của từng ASR, không phải benchmark mới hoặc chứng nhận khả năng tổng quát. Warm/resident worker có thể loại chi phí nạp nhưng không xóa thời gian inference này. Vì vậy **chỉ thay TTS chưa giải quyết mục tiêu4giây**; cần so cả lỗi nhận dạng/no-speech và độ trễ, không tự chọn Whisper hoặc bật VAD để làm đẹp số đo.

## Phần cứng và chi phí đề xuất

Read-only snapshot09:23UTC: Ryzen7 7700,8cores/16threads; RAM tổng32,220,790,784bytes, available22,538,399,744bytes; RTX4070TiSUPER16,376MiB, free15,113MiB;15containers và không có `llama-server` native. Đây là snapshot idle, không phải reservation/minimum RAM. CORE32K trong số đo lịch sử dùng9,386MiBVRAM riêng; không lấy GPU trống hiện tại làm chứng minh còn chỗ khi CORE được nạp.

Trial đầu đề xuất **CPU FP32**, giữ GPU cho CORE và tránh đổi precision trước khi có chất lượng baseline. [16artifact pin](evidence/d74-vi-turbo-proposed-artifacts-20261103.json) tổng **608,816,450bytes ≈580.613MiB disk**; SDK/cache/results nằm trong cap8GiB riêng. Đây không phải RAM/VRAM tối thiểu. RSS/load/TTFA/RTF/CORE contention của candidate mới đều **CHƯA ĐO**. Không cộng kích thước checkpoint thành RAM hoặc khẳng định mẫu sẽ đạt4giây.

## Những điểm phải kiểm soát khi triển khai bộ thử

- CPU constructor đọc codec từ repo MOSS khác và eager-load denoiser. Manifest bao gồm các thành phần này và preset asset; không chỉ duyệt một file TTS rồi để SDK tự tải thêm.
- Pinned SDK có `device/backend="auto"`, lookup model không truyền revision và `style` bị bỏ qua. Phải ép CPU/ONNX, dùng cache/local snapshots đã pin trong môi trường offline; không hứa sửa giọng bằng style string hoặc auto dùng GPU.
- Cơ chế babble có thể sinh lại câu ngắn. Đặt `babble_retries=0`, audit số lần gọi thực và giữ output đầu, normalization của upstream được ghi rõ; không retry để lấy mẫu tốt.
- Cần khóa/audit SDK trước chạy; hiện **chưa dựng SDK hoặc runner**. Package source/bundled preset là nội dung cần duyệt trong preparation, không được tự cài full project với extras rồi suy là không có model phụ.

## Việc tiếp theo và quyết định cần duyệt

[ADR-154](ADR/154-proposed-isolated-vietnamese-voice-feasibility-campaign.md) đề xuất một campaign có điều kiện: chuẩn bị riêng → qualification/24audio so sánh →48turn workflow CPU theo packet cố định, tối đa74TTS/48ASR/50COREcalls. Một phê duyệt có thể bao trọn các pha nếu precondition/test/freeze đạt; sai scope/resource/pin phải dừng, không tự đổi model/cap.

Trial vẫn giữ nguyên default/registry selections, source PASS, original Piper/Qwen, audio cũ và dữ liệu. Đánh giá giọng không tự phê duyệt triển khai; benchmark digital-render cũng không thay thế first-audible thực tế tại thiết bị. D60 pending; VI ưu tiên, EN giữ mục tiêu, ngôn ngữ tùy biến bản sau vẫn pending; D74 sản phẩm và D90 release còn mở.

Khảo sát/proposal P1 đã chuẩn bị; implementation/download/inference chưa được duyệt. [Receipt kiểm chứng khảo sát](evidence/d74-vi-survey-20261103-verification.json). Không có benchmark mới để báo cáo thắng/thua hoặc model đã được thay.

Ghi chú provenance: verifier đầu phát hiện trường SHA của response tree API giữ commit-ref thay vì tree ID đã resolve. [Đối chiếu độc lập](evidence/d74-upstream-git-tree-identity-20261103.json) tái dựng đủ23Git tree objects khớp tree mà commit tham chiếu; các source blob tải về được kiểm tra hash riêng. Giữ lỗi kiểm tra đầu, không bỏ qua mismatch hoặc suy source hợp lệ chỉ từ URL.
