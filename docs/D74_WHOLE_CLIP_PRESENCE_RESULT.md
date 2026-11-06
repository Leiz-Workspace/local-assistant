# D74 — Chặn đầu vào không có lời nói, giữ nguyên cả clip

**Mục đích:** Báo cáo prototype và phép đo thật theo [ADR166](ADR/166-whole-clip-presence-with-original-pcm.md), sau 16 lượt trả lời nhầm ở [ADR165](D74_NATIVE_READING_WORKFLOW_RESULT.md).

**Kết luận:** Đường chặn hoạt động đúng trong kiểm thử; Silero nhận đủ speech gốc và chặn 5 mẫu negative, nhưng từ chối 2 mẫu tiếng Anh giảm âm lượng. **Robustness chưa đạt; chưa bật gate sản phẩm và D74 chưa PASS.** [Receipt và hash](evidence/d74-whole-clip-presence-result.json).

## Thay đổi và phép đo

Thêm adapter nghiên cứu `WholeClipASR`: khi detector trả kết quả hợp lệ có lời nói, chuyển **đúng đối tượng audio gốc** cho ASR, gồm toàn bộ PCM, khoảng lặng và mốc thời gian. Không cắt/ghép waveform như thử nghiệm D72 trước. Khi kết quả hợp lệ không có segment, trả empty transcript có đúng owner/source/model binding; VoicePipeline cũ dừng với `no_speech` trước ASR/CORE/TTS. Lỗi detector hoặc binding không bị chuyển thành “im lặng” hay fallback sang ASR.

Giữ nguyên model Silero v5.0, threshold 0.5, min speech 250 ms, min silence 100 ms và padding 30 ms. Không đổi ASR/TTS/CORE, context, cấu hình, lựa chọn giọng, reference hoặc source ứng dụng. Không tải gì, dùng Vault/database hoặc sửa Docker/shared services. Hai vòng chỉnh phát âm tiếp tục dừng theo chủ dự án.

Panel được cố định trước khi chạy: toàn bộ 47 mẫu D72 cũ qua PCM port gốc, cộng 6 bản giảm âm lượng toàn clip từ một câu VI và một câu EN, gain 0.5/0.1/0.03. Đây là robustness controls có nhãn kỳ vọng kế thừa, không phải bản ghi độc lập hay xác nhận nghe được của con người. Sáu input ASR của D74 được đối chiếu đúng hash với lượt trước.

## Kết quả thật

| Nhóm | Kết quả detector |
|---|---|
| 40 bản ghi speech gốc, 20 VI + 20 EN | Nhận 40/40 |
| 2 bản lặp thêm khoảng lặng | Nhận 2/2; không tính thêm vào 40 bản ghi độc lập |
| 5 nguồn negative tự tạo | Chặn 5/5, gồm hai nguồn D74 từng dẫn tới trả lời nhầm |
| 3 control VI giảm âm lượng | Nhận 3/3 |
| 3 control EN giảm âm lượng | Nhận 1/3; từ chối bản gain 0.1 và 0.03 |

100 quan sát VAD thực tế: 47 mẫu theo thứ tự xuôi/ngược (94), rồi 6 control riêng. Có 7 worker, đều exit 0/reaped, không retry, không bỏ lượt. Tổng native wall 15.848 giây, không gồm chuẩn bị/chuẩn hóa nguồn. Segmentation mỗi clip min/median/max 9.27/30.49/59.86 ms; import/load từng worker vẫn riêng. Đỉnh lifetime worker RSS **348808 KiB RAM**, CPU-only; không phải VRAM hoặc RAM tối thiểu của toàn luồng. Cap VAD 3 GiB được đối chiếu từ lệnh `prlimit` thực tế; helper preflight dùng chung còn field cap evaluator 12 GiB kế thừa trong receipt, không phải cap của worker VAD.

Đỉnh xác suất speech ở hai EN control bị từ chối chỉ khoảng **0.01988/0.01201**, không window nào đạt 0.5. Vì vậy việc chỉ giảm min-speech-duration không giải quyết hai kết quả này với threshold hiện tại. Chưa xác định cơ chế nội bộ hoặc kết luận mọi giọng nhỏ sẽ thất bại; không hạ threshold hay sửa gain sản phẩm sau khi thấy điểm.

Đã đưa 53 kết quả detector thật qua adapter và VoicePipeline gốc với **sentinel downstream giả lập**: 46 lượt được nhận giữ nguyên audio/clock và gọi sentinel ASR; 7 lượt bị chặn không gọi downstream. **Zero native ASR/CORE/TTS trong phép đo này.** Không coi sentinel là benchmark ASR, lời trả lời thật, chất lượng audio hoặc bản chạy lại 48 lượt ADR165. Các lỗi ADR165 vẫn giữ nguyên.

## Kiểm thử và bảo toàn

524 related PASS / 0 FAIL / 0 ERROR / 0 SKIP, 6.47 giây, gồm 61 controls mới. Kiểm tra owner/PCM/clock/model/segment binding, full-clip forwarding, timeout/cancel/shutdown có join, detector fault, nguồn bị sửa, giới hạn 7 worker, dừng lỗi đầu tiên và không retry đều có tests. Ruff và English module/class/function descriptions PASS. Full 5889 trước vẫn là snapshot lịch sử, không phải full mới.

Đối chiếu độc lập giữ nguyên 1903 file code/evidence cũ, riêng baseline ứng dụng 750 file và 210 protected file; model/source D72 và ADR165 không sửa. Native 0 và cùng 15 container được phục hồi; source freeze, raw logs, probabilities, reverse replay, seven retirement receipts, input PCM và archive đều được kiểm. Historical padded rows kế thừa `kind` của nguồn; báo cáo tách bằng ID `padded-`, không sửa nhãn cũ.

[Toàn bộ 4 file code/test mới và 5 dependency nguyên bản](../data/backups/d74-whole-clip-presence-first/full-code.zip). Artifact và snapshot code riêng nằm trong `data/backups/d74-whole-clip-presence-first/`.

## Công việc tiếp theo đã đánh giá

**AUDIO-VAD-ASR-002 — P1, đề xuất nghiên cứu:** đánh giá một bản audio chuẩn hóa biên độ **chỉ cho detector**, còn ASR vẫn nhận PCM/clock gốc. Dependency: lỗi quiet EN đã giữ nguyên, exact source/view hash binding và corpus VI/EN/quiet/negative cố định riêng trước khi đo. Effort: một milestone thiết kế/controls và so sánh hữu hạn. Rủi ro: khuếch đại noise/DC/clipping, lệch provenance và overfit hai câu đã biết. Chưa chọn thuật toán/gain, chưa triển khai hoặc chạy phương án này; cần benchmark trước quyết định tích hợp.

Sau khi sensitivity/negative controls phù hợp, mới nối detector native vào workflow thật và đo lại theo scope riêng. VOICE-LATENCY-AC-001 vẫn cần profile ASR/TTS; không cộng segmentation-only vào số cũ để giả lập max 4 giây. Short-speech/word retention, first-audible trên PC, endpoint/auth/retention/playback, quyền sử dụng và lựa chọn model/default/sản phẩm vẫn OPEN. D60 deferred; D90 NOT RELEASED.


## Separate local gate follow-up — 2026-11-04

[ADR169detector147/147 and ADR168native8/8](D74_DETECTOR_PEAK_GATE_RESULT.md) now verify the new detector-only peak normalization/whole-clip gate in a separate finite scope,592relatedPASS.4speech native outputs/4correct no-speech early refusals; models and prior scores in this report remain unchanged. Gate product activation/quiet-ASRsemantics/real mic/noise/physical4seconds/rights/default/product/release remain OPEN; no original failed row is rescored.
