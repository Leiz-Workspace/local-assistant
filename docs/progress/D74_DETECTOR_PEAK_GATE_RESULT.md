# D74 — Gate detector và kiểm tra luồng thoại cục bộ đã PASS

**Mục đích:** Báo cáo kết quả thực tế cho yêu cầu “Tiếp tục làm để pass đi”, giữ nguyên model, source ứng dụng và các lần lỗi trước. [ADR167](../ADR/167-detector-only-fixed-gain-comparison.md), [ADR169](../ADR/169-fixed-detector-peak-normalization-and-fresh-controls.md), [native scope ADR168](../ADR/168-qualified-detector-native-voice-check.md).

**Kết luận:** Detector đạt **147/147** kiểm soát cố định; luồng model thật đạt **8/8** kiểm tra cục bộ. Đây là PASS của gate vừa sửa, **chưa phải D74 sản phẩm hoặc tối đa 4 giây**. [Receipt và hash](../evidence/d74-detector-peak-gate-result.json).

## Sửa nguyên nhân và giữ kết quả trước

Chỉ bản sao đưa cho Silero được tăng đỉnh âm lượng lên 0,5; audio gửi ASR vẫn là toàn bộ PCM và mốc thời gian gốc. Không cắt/ghép, lọc, sửa transcript, hạ threshold hoặc thay model. Với PCM16, gain được giới hạn tự nhiên tối đa 16384 bởi độ phân giải số; không tăng giới hạn RAM/CPU hoặc đổi context.

Candidate gain≤32 đầu tiên đạt 99/100 nên giữ **FAIL**. Mẫu EN còn lỗi vốn rất nhỏ, chạm trần gain nhưng bản detector vẫn chưa đủ biên độ; bản v2 loại bỏ trần tùy ý này. Toàn bộ code/audio/probabilities/điểm cũ được giữ riêng, không thử lại hoặc sửa điểm. Lần chuẩn bị đầu cũng giữ FAIL: 134,183 MiB vượt cap 128 MiB trước mọi model load. Đã bỏ bản lưu PCM trùng, khôi phục chính xác từ float và xác minh hash; test đủ 65536 giá trị PCM16. Root mới vẫn dưới 128 MiB.

## Detector: kết quả thật và phạm vi

| Nhóm | Kết quả v2 |
|---|---:|
| 80 bản ghi speech gốc, 40 VI + 40 EN | Nhận 80/80 |
| 46 control giảm âm lượng, kế thừa nhãn presence | Nhận 46/46 |
| 6 bản lặp có thêm khoảng lặng | Nhận 6/6 |
| 15 lượt kiểm soát negative tự tạo | Chặn 15/15 |
| Tổng 147 hàng đã cố định | **147/147 PASS** |

V2 chạy đúng 9 worker, 288 quan sát Silero thực tế gồm thứ tự xuôi/ngược cho ba nhóm 47 và sáu control riêng. Có 20 bản ghi chưa dùng để chọn cách sửa trong các lượt trước, cùng 20 bản gain 0,03, năm negative và hai bản lặp mới. Dataset vẫn là nguồn công khai đã lưu từ D68/D72, không phải dữ liệu chưa từng xuất hiện trong pretraining. Các control giảm âm lượng chưa có nhãn nghe/word-boundary độc lập; bản lặp và negative giống waveform không tính thành bản ghi độc lập.

Giữ nguyên baseline ADR166 và candidate gain32: raw 87/100, candidate 99/100. Không gộp điểm 147 mới thành một so sánh paired tổng hợp hoặc tuyên bố độ nhạy phổ quát. Các phép đo chỉ xác nhận whole-clip speech presence trên panel này, không xác nhận chất lượng nhận từng từ ở âm lượng thấp.

## Luồng model thật: 8/8 PASS

Chỉ sau khi v2 đạt đủ gate mới chạy scope mới: Whisper-small CT2 và Qwen3-ASR-0.6B, mỗi model trên hai nguồn speech VI gốc và hai nguồn negative gốc. CORE32K/Fast512, Trúc Ly reading policy và weights/reference giữ nguyên; mỗi lượt nạp ASR/TTS mới sau khi VAD đã thoát.

- 4/4 lượt speech tạo native audio và playback PCM hoàn chỉnh.
- 4/4 lượt negative dừng với `no_speech`; không có request hoặc thư mục ASR/CORE/TTS ở những lượt này.
- Đúng 8 quan sát VAD, 4 ASR + 4 CORE + 4 TTS; 0 retry, 0 lỗi guard/runtime, 0 lượt chưa chạy.
- Hai nguồn speech và hai negative được lặp trên hai ASR; không phải tám bản ghi độc lập. Không có thử nghiệm native quiet-ASR hoặc chấm lại ngữ nghĩa/độ tự nhiên trong scope này.

Audit đối chiếu view/PCM/owner/clock, nguyên text ASR→CORE, CORE stop/context/budget, manifest/voice/native output, playback hashes và 12 ledger entries. Cả 8 worker VAD, 8 worker ASR/TTS và CORE đều thoát sạch; baseline native 0/cùng 15 container được phục hồi. Toàn bộ ba scope trong lượt tiếp tục này có 684 quan sát VAD thật, giữ cả candidate lỗi; không gọi chúng là 684 mẫu độc lập.

Cold buffered latency của bốn lượt speech: **11,211 / 11,490 / 15,541 / 17,857 giây**; native phase wall 67,067 giây. Số này gồm detector và nạp ASR/TTS, CORE đã nạp sẵn; không phải whole-system cold boot. **Chưa đạt tối đa 4 giây**, chưa đo first-audible trên loa PC. Không dùng tốc độ từ chối negative để chứng nhận độ trễ lời trả lời.

## Kiểm thử, bảo toàn và code đầy đủ

**592 related PASS / 0 FAIL / 0 ERROR / 0 SKIP, 7,67 giây**, gồm 68 controls mới trên exact source trước native runs. Ruff/format/module/class/function descriptions PASS. Full 5889 trước vẫn là snapshot lịch sử. Đối chiếu mã/bằng chứng cũ, baseline 750 application/210 protected, pinned VAD/TTS/runtime và post-run 14 artifact ASR giữ nguyên. Không truy cập/thay Vault, database, collection, Docker/shared services hoặc provider. Model/default/giọng/context không thay đổi; không download. Không bật gate sản phẩm.

[Toàn bộ code/test và các phiên bản lỗi đã giữ](../../data/backups/d74-detector-view-native-first/full-code.zip). Artifact riêng: `data/backups/d74-detector-view-storage-corrected-first/`, `d74-detector-peak-v2-first/`, `d74-detector-view-native-first/`. Lần preparation lỗi nằm nguyên ở `d74-detector-view-first/`.

## Việc còn lại

AUDIO-VAD-ASR-002 hoàn tất kiểm tra cục bộ detector + native no-speech integration theo scope trên. Trước sản phẩm vẫn cần kiểm tra giọng nói/mic thực tế, short-speech và quiet-ASR/word accuracy, noise đời thực và lựa chọn/rights/default của chủ dự án. Hai vòng tinh chỉnh phát âm vẫn dừng.

**VOICE-LATENCY-AC-001 — P1 kế tiếp:** profile và quản lý vòng đời detector/ASR/TTS đã nạp, dựa trên số stage thật; giữ nguyên model, chất lượng và guard. Dependency: gate vừa đạt, các số warm/cold trước và endpoint/playback contract. Effort: một milestone thiết kế/controls rồi phép đo hữu hạn riêng. Rủi ro: co-residency vượt RAM guard, cancellation/TTL và nhầm complete PCM với âm thanh từ loa; không tự tăng cap, giảm context, chọn ASR khác hoặc bỏ mốc tối đa. D60 deferred; D74 toàn bộ/physical 4 giây/rights/product và D90 release vẫn OPEN.
