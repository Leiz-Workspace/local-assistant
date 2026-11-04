# D74 — Kết quả chạy thật luồng thoại với reading policy

**Mục đích:** Xác nhận bằng model thật theo chỉ dẫn “Chay để xác nhận đi”, [ADR165](ADR/165-reading-aware-native-voice-workflow-validation.md) và [authority](evidence/d74-workflow-reading-native-authorization.json), sau phần nối phần mềm ADR164.

**Kết luận: đã đo đủ48/48; luồng chạy thông, nhưng CHƯA ĐẠT mốc4giây hoặc yêu cầu không trả lời khi không có lời nói.** [Receipt đầy đủ](evidence/d74-workflow-reading-native-result.json). D74 sản phẩm chưa PASS.

## Kết quả và phạm vi

- 32lượt có lời nói đều tạo native audio và PCM hoàn chỉnh. Đây là xác minh đường chạy, chưa chấm độ chính xác ASR/nội dung trả lời hoặc chất lượng nghe chung.
- 16/16lượt không có lời nói đều bị ASR sinh text và dẫn tới CORE/TTS trả lời;0lượt từ chối đúng. Đây là2mẫu negative cũ lặp trên8tổ hợp, không phải16mẫu độc lập. Không thay transcript bằng nhãn tham chiếu hoặc bật VAD để giấu lỗi.
- 48ASR/48CORE/48TTS thực tế,0retry/0chưa gọi/0generation recovery ngoài luồng. Ledger144ID duy nhất,96worker result events và48HTTP completion client records được đối chiếu;56ASR/TTS workers và1ownedCORE đều exit0/joined,0guard failure, native/container baseline phục hồi.

Bốn mẫu speech gốc dài5,1/9,9/12,9/18,84giây; hai negative3giây. Hai ASR và hai TTS giữ nguyên; Whisper CPU requestedint8/actualint8_float32, Qwen CPUfloat32/eager, Trúc Ly CPU FP32 với policy đã chốt và Piper VI đối chứng. CORE giữ32K/Fast512. Thứ tự Whisper→Qwen, Trúc Ly→Piper, nạp mới→resident được ghi trước để lấy bằng chứng lane ítRAM trước, không chọn model theo điểm. Không chạy qualification/standalone mới, không tải hoặc thay model/voice/config/default, không chỉnh lại phát âm.

## Thời gian có đủ PCM trả lời, chỉ32lượt có lời nói

Đơn vị giây; mỗi hàng chỉ4mẫu, không phải p95 hoặc cam kết chung. CORE đã nạp trước mọi hàng; “nạp mới” ở đây chỉ ASR/TTS. Tổng thời gian chiến dịch native462,967giây gồm cả sở hữu/khởi động CORE và resident-group setup, khác thời gian từng lượt.

| ASR | TTS | Trạng thái | Nhỏ nhất | Median | Lớn nhất | PCM≤4s |
|---|---|---|---:|---:|---:|---:|
| Whisper small | Trúc Ly/reading | Nạp mới ASR/TTS | 10.576 | 11.583 | 12.618 | 0/4 |
| Whisper small | Trúc Ly/reading | Đã nạp ASR/TTS | 3.335 | 4.889 | 6.363 | 1/4 |
| Whisper small | Piper VI/control | Nạp mới ASR/TTS | 7.750 | 8.471 | 9.031 | 0/4 |
| Whisper small | Piper VI/control | Đã nạp ASR/TTS | 2.450 | 3.252 | 3.703 | 4/4 |
| Qwen3-ASR-0.6B | Trúc Ly/reading | Nạp mới ASR/TTS | 17.260 | 18.431 | 20.943 | 0/4 |
| Qwen3-ASR-0.6B | Trúc Ly/reading | Đã nạp ASR/TTS | 4.264 | 8.205 | 11.122 | 0/4 |
| Qwen3-ASR-0.6B | Piper VI/control | Nạp mới ASR/TTS | 12.351 | 15.488 | 18.879 | 0/4 |
| Qwen3-ASR-0.6B | Piper VI/control | Đã nạp ASR/TTS | 3.171 | 6.574 | 9.693 | 1/4 |

Chỉ6/32lượt speech có đủ PCM trong4giây; riêng Trúc Ly1/16. Ở Whisper–Trúc Ly đã nạp sẵn, median stageASR2,382s/CORE0,390s/TTS2,116s; Qwen–Trúc Ly tương ứng5,788/0,368/1,875s. Median từng stage không nhất thiết cộng đúng median tổng. ASR và TTS là phần cần tối ưu trên phép đo này; giữ model/32K/cap đã thỏa thuận, không tự chọn Piper hoặc Whisper vì có hàng nhanh hơn. Piper hiện vẫn có nhận xét không hợp chất giọng từ owner.

Đây là submission→completePCM của luồng buffered, **chưa đo loa bắt đầu phát trên PC**. Với đường phải chờ đủPCM mới trả kết quả, các lượt>4s không hỗ trợ claim≤4s; lượt≤4s cũng chưa là physical PASS. Không tính các câu trả lời sai ở negative vào tốc độ speech thành công, không thay yêu cầu “tối đa” bằng median hoặc beep/PCM/token đầu.

## Đúng bản reading và giới hạn bao phủ

24TTS Trúc Ly có manifest/profile/reading-policy/input/voice/reference/token/frame/chunk/native hashes khớp;24trace originalCOREanswer→speech và48playbackPCM hashes được kiểm. Original answer giữ nguyên, không sửa transcript hoặc câu trả lời.24TTS Piper đi đường gốc.

**Cả24COREanswer trong lane Trúc Ly đều không cần edit text hoặc thuật ngữ.** Lượt này xác nhận wiring/profile/provenance thực tế, không chứng minh nhánh edit phức tạp đã xảy ra với COREoutput sống. Các nhánh đó có20probe SDK/10old-control parity,58software controls và các native listening controls trước; không bịa coverage mới. Không tự chấm lại API/English/identity; cả hai vòng tinh chỉnh đã dừng theo owner.

## Tài nguyên và kiểm thử

398related PASS/0FAIL/ERROR/SKIP6,11s gồm12new campaign controls; focused12PASS0,34s/RuffE4,E7,E9,F/format/descriptions PASS trước sourcefreeze. Full5889/750 vẫn là snapshot lịch sử.52research cũ/750application/210protected/4295SDKentries/23475TTS-runtime entries và14ASRcheckpoint artifacts reverified; old6software-invalid/42unattempted ADR154/155hashes giữ nguyên. Không sourceapp/shared-service/Vault/database/Docker mutation, không provider/Brave call.

Peak sampled RSS RAM theo worker: QwenASR5820,32MiB; Whisper1000,34MiB; Trúc Ly1717,27MiB; Piper317,31MiB. CORE riêng ghi sampledVRAM8802MiB, native wait4 peakRAM8082404KiB. Đây là peak riêng/khác thời điểm, không cộng thành peak đồng thời hoặc RAM tối thiểu; ASR/TTS dùngCPU, không gán RAM thànhVRAM. Original guard AS8GiB/RSS-TTS2GiB/aggregate8GiB/headroom14GiB/CPU0,1/2threads/root8GiB/turn180s/campaign3600s giữ nguyên; không guard failure quan sát được.

Audit đầu so nhầm slot wrapper códescription với bare row; audit kế tiếp giả định server có accesslog HTTP. Sửa checker-only: so đúng row fields và dùng48nativeclient HTTP completion records/48COREresponses; server không ghi các path đó trong retainedlog. Giữ receipt hai lỗi checker, không sửa artifact/source/score hoặc chạy model lại. Source snapshot/ZIP/terminal/authority/native/pipelinechain được đối chiếu nguyên hash. [Full version8file code/test](../data/backups/d74-vi-approved-campaign-20261103/workflow-reading-native-first/full-code.zip).

## Việc còn lại sau phép đo

1. AUDIO-VAD-ASR-001 follow-up — P1 trước product: xử lý false speech/no-speech với guard/dataset thích hợp. Dependency là16negative failures và D72gated/ungated evidence; effort một milestone thiết kế/controls rồi một bounded measurement. Rủi ro loại nhầm giọng nhỏ/EN, cắt sample clock hoặc lặp lại VAD concatenation vốn chưa qualified. Không tự bật gate cũ.
2. VOICE-LATENCY-AC-001 — P1: tối ưu/profile ASR/TTS và vòng đời đã nạp theo dữ liệu; resident giúp nhưng Trúc Ly vẫn có lượt>4s. Dependency scope tài nguyên/identity/model đã chốt, stage measurements và protocol; effort một profiling/design milestone rồi measurement riêng. Rủi ro đổi CPU/GPU/concurrency ảnh hưởng shared resources, chất lượng hoặc coi PCM là physical playback. Chưa xếp một lượt tuning/native tiếp hoặc đổi model.
3. Endpoint/auth/retention/playback và first-audible trên Brave/PC, rights/model/default/product signoff vẫn riêng; microphone smoke cũ giữ PASS đúng phạm vi. D60deferred; D90 NOT RELEASED. Original ADR155raw vẫn không chạy; ADR165là cohort mới đã được owner cho chạy, không gộp điểm.


## Follow-up riêng — 2026-11-04

[ADR166 whole-clip presence](D74_WHOLE_CLIP_PRESENCE_RESULT.md) đã có prototype và100quan sát Silero thật:5negative bị chặn/40speech gốc nhận đủ, nhưng2quiet EN controls bị từ chối.524relatedPASS; không bật gate, không thêm native ASR/CORE/TTS hoặc sửa điểm48lượt trên. Chỉ sentinel được dùng để kiểm đường chặn; D74/no-speech/product và4giây vẫn chưa PASS.


## Separate local gate follow-up — 2026-11-04

[ADR169detector147/147 and ADR168native8/8](D74_DETECTOR_PEAK_GATE_RESULT.md) now verify the new detector-only peak normalization/whole-clip gate in a separate finite scope,592relatedPASS.4speech native outputs/4correct no-speech early refusals; models and prior scores in this report remain unchanged. Gate product activation/quiet-ASRsemantics/real mic/noise/physical4seconds/rights/default/product/release remain OPEN; no original failed row is rescored.
