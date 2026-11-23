# D74 — Kết quả độ trễ với model giữ nguyên

**Mục đích:** Ghi kết quả thực tế của VOICE-LATENCY-AC-001 sau khi sửa quản lý vòng đời và bộ chạy CUDA, tách gate xử lý cục bộ khỏi first-audible trên thiết bị.

**Ngày:** 2026-11-05. **Kết luận:** Gate **LOCAL_BUFFERED_COMPUTE_PASS**: 4/4 câu trả lời có audio hoàn chỉnh trong 2,000–3,334 giây; 2/2 negative bị chặn trước ASR/CORE/TTS. **Chưa xác nhận tiếng phát từ loa PC trong 4 giây; D74 sản phẩm vẫn OPEN.** [Receipt](../evidence/d74-resident-cuda-latency-result.json).

## Cách sửa và chất lượng giữ nguyên

Nạp sẵn detector/ASR/TTS cho một nhóm thử nghiệm thay vì nạp lại mỗi câu. Qwen3-ASR-0.6B chạy CUDA FP32/eager, tắt TF32/autocast; dùng đúng checkpoint/tokenizer/processor và cách giải mã cũ. CORE32K/Fast512 giữ nguyên. Silero v5 chạy CPU, detector-only peak view đã đạt gate trước; ASR nhận toàn bộ PCM/mốc thời gian gốc. Trúc Ly và policy đã nghe giữ nguyên, TTS ONNX FP32 chạy trên 8 nhân vật lý. Không sửa app/config/default, chọn model/giọng sản phẩm hoặc tải weights mới.

Chỉ chuẩn bị SDK CUDA riêng bằng `uv`, khoảng 6,707 GiB phần mềm, dùng Torch2.10.0+cu128 cùng core version CPU. Không thay môi trường CPU. Probe không-weights dùng khoảng 865 MiB RAM/310 MiB VRAM và thoát sạch. [ADR170 CPU](../ADR/170-resident-voice-cpu-latency-comparison.md), [ADR171 CUDA](../ADR/171-same-checkpoint-cuda-asr-latency-qualification.md), [ADR172 sửa binding](../ADR/172-cuda-original-source-binding-recovery.md).

## CPU: giữ nguyên kết quả chưa đạt

36 lượt cố định gồm 2 ASR × 3 cấu hình CPU × 6 nguồn. 24 câu speech hoàn chỉnh/12 negative chặn đúng; không retry/lỗi tài nguyên. Thời gian lớn nhất trong bốn câu speech mỗi nhóm:

| ASR | 2 luồng | 4 luồng | 8 luồng |
|---|---:|---:|---:|
| Whisper-small CT2 | 6,199 s | 5,173 s | 4,797 s |
| Qwen3-ASR-0.6B | 10,423 s | 9,696 s | 8,953 s |

Cả sáu nhóm **không đạt maximum 4 giây**. 16 cặp so sánh 4/8 với 2 luồng có transcript, câu trả lời, native float và playback PCM trùng byte. Không lấy trung bình hoặc negative nhanh để đổi điểm. CPU8 Qwen riêng bước ASR có câu mất 7,022 giây, là lý do tiếp tục CUDA cùng model.

## CUDA: chất lượng trước tốc độ

Chạy đúng 80 nhận dạng trên 40 bản ghi gốc D72 (20 VI/20 EN) cho hai ASR. Đây là so sánh với baseline CPU lịch sử trên cùng dữ liệu, không phải holdout mới hoặc benchmark CPU đồng thời.

- **Qwen đạt:** cả 40 raw transcript trùng CPU; VI WER45/591 = 7,614%, CER99/1984 = 4,990%; EN WER26/460 = 5,652%, CER84/2038 = 4,122%. Giữ cả lỗi nhận dạng đã có; không tuyên bố nhận đúng 100% lời nói.
- **Whisper không đạt:** VI CER tăng từ248/1984 lên253/1984; VI WER không đổi121/591. EN tốt hơn không bù cho VI. Chỉ22/40 transcript trùng; không cho chạy tiếp native, không đổi tiêu chí hoặc đổi precision để cứu điểm.

Lượt native đầu bị dừng ở request đầu do bộ chạy mount nhầm thư mục detector. Hash gốc từ chối trước khi ASR xử lý, CORE/TTS không được gọi. Giữ nguyên toàn bộ root/kết quả/code đầu; không gọi đây là lỗi VRAM. Bản sửa bắt buộc khai báo phase và mount original PCM riêng cho native. Kiểm thử dùng hai waveform khác nhau xác nhận bản detector bị từ chối. Lượt phục hồi ADR172 có root/scope riêng, chỉ dùng lại kết quả Qwen đã đạt; không lặp 80 nhận dạng hay chạy Whisper.

## Native sửa source-binding đầu tiên: 6/6 đạt trong phạm vi cố định

| Nguồn VI gốc | ASR | CORE | TTS/hoàn tất | Tổng complete PCM |
|---|---:|---:|---:|---:|
| 0036 | 0,408 s | 0,306 s | 1,432 s | **2,146 s** |
| 0024 | 0,786 s | 0,370 s | 1,514 s | **2,670 s** |
| 0078 | 0,913 s | 0,466 s | 1,833 s | **3,212 s** |
| 0040 | 1,261 s | 0,363 s | 1,919 s | **3,543 s** |

Hai negative gốc trả `no_speech`, không dispatch ASR/CORE/TTS. Đúng6VAD/4ASR/4CORE/4TTS, zero retry/guard/runtime failure, wall25,192 giây. Bốn transcript, bốn câu CORE và bốn native/playback audio trùng byte với nhóm QwenCPU8. Không cắt câu, hạ context, đổi voice/reference/cap hoặc dùng beep/silence để đạt thời gian.

Model đã ready trước submission; một inference readiness công khai trên 1 giây zero PCM cho mỗi ASR load, không chứa dữ liệu người dùng/cached answer. Đây **không phải cold-start** hoặc độ trễ thiết bị. Bốn nguồn speech và hai negative đã dùng trước; chưa chứng nhận mọi độ dài/ngôn ngữ/âm lượng/noise/phòng thực tế hoặc tải đồng thời.

## Bản cuối sửa disk guard: xác nhận riêng 6/6 PASS

Audit sau lượt PASS đầu phát hiện polling dung lượng trong worker kế thừa vẫn kiểm tra root cũ; workflow đã kiểm tra root hiện tại sau từng turn và cả root thực tế vẫn dưới8GiB. Giữ nguyên số đo, source snapshot và ZIP của lượt này. Bản sửa truyền đúng root hiện tại cho cả VAD/ASR/TTS và quality, bổ sung test; không đổi inference-worker, weights, SDK, decoder hoặc cap. [Addendum ADR172](../ADR/172-cuda-original-source-binding-recovery.md) cố định riêng một lượt xác nhận6mẫu, không lặp quality80hay retry lỗi model.

| Nguồn | ASR | CORE | TTS/hoàn tất | Complete PCM bản cuối |
|---|---:|---:|---:|---:|
| 0036 | 0,363 s | 0,292 s | 1,345 s | **2,000 s** |
| 0024 | 0,705 s | 0,373 s | 1,504 s | **2,582 s** |
| 0078 | 0,800 s | 0,460 s | 2,074 s | **3,334 s** |
| 0040 | 1,060 s | 0,357 s | 1,603 s | **3,020 s** |

Đúng6VAD/4ASR/4CORE/4TTS và1readiness;2negative chặn đúng, zero retry/runtime/guard failure, wall26,014giây. Cả bốn đầu ra tiếp tục trùng CPU8 về ASR/CORE/native/playback bytes. Hai lượt6/6 là lặp cùng4speech/2negative để xác nhận bản sửa, không phải12nguồn độc lập hoặc dùng lượt tốt hơn để thay điểm cũ. Lượt đầu max3,543 và bản cuối max3,334đều giữ PASS riêng; cả hai vẫn chưa đo speaker first-audible.

## Tài nguyên, kiểm thử và bảo toàn

690 related tests PASS/0 FAIL/ERROR/SKIP trong7,97 giây, gồm98 controls mới; Ruff/format và descriptions PASS. Full5889 là bằng chứng lịch sử, không chạy lại và không gộp thành số mới. 10 file code/test mới đầy đủ, các dependencies nguyên bản và code thất bại đầu được lưu trong [full-code.zip](../../data/backups/d74-cuda-root-guard-confirmation-first/full-code.zip).

Giữ cap RAM vật lý tổng các worker+CORE8GiB, TTS2GiB, pre-load MemAvailable14GiB. CUDA có profile **64GiB address space ảo**, không phải64GiB RAM/VRAM; PyTorch allocator4GiB, owned ASR VRAM4,5GiB, GPUfree1,25GiB và pre-load6GiB. ASR GPU peak quan sát khoảng3,94GiB; không tăng CORE VRAM/context/cap CPU cũ. Peak các tiến trình ở thời điểm khác nhau không được cộng thành đỉnh RAM đồng thời.

Audit độc lập xác nhận 2959 file cũ/evidence theo freeze, 750 application/210 protected,14 artifact ASR,15870 file SDK và runtime cũ không đổi. Toàn lượt này49VAD,112ASR kết quả +5 readiness =117 ASR inference thực,32TTS/32CORE; riêng một native dispatch bị chặn trước inference được giữ riêng. 34 process groups đã thu hồi; chỉ worker đầu lỗi integrity exit1, các worker/CORE còn lại exit0. Baseline native0/cùng15container khôi phục. Không thao tác Vault/database/Qdrant/Docker/provider hoặc restart dịch vụ dùng chung.

## Phần tiếp theo của gate 4 giây

VOICE-LATENCY-AC-001 **chỉ đóng phần buffered compute cục bộ**. Tiếp theo cần endpoint nghiên cứu có xác thực, explicit-submit/ready/busy/cancel/retention, playback trên trình duyệt và phép đo submission→tiếng trả lời thật từ loa. App recorder hiện chỉ capture/playback, chưa nối runner CUDA này; không gửi người dùng một URL giả là có workflow. Chuẩn bị tích hợp và kiểm thử trước khi yêu cầu owner đo trên Brave/PC; không bắt nghe lại các clip/phát âm đã dừng.

Dependency: gate hiện tại và contract endpoint/playback; ưu tiên P1; effort một milestone contract/control, một tích hợp cô lập và một lượt thiết bị thực; rủi ro khoảng dư dưới0,67giây, mạng/codec/autoplay, co-residency, cold-start và cleanup/cancel. Không thay tiêu chí first-audible thành PCM hoặc hạ model/default/rights approval. D60 deferred; D74 sản phẩm, physical4seconds, model/voice/rights và D90release OPEN.
