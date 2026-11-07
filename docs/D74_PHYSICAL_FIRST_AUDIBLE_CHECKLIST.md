# D74 — Checklist đo tiếng trả lời đầu tiên trên PC thật

**Mục đích:** Giúp chủ dự án tự đo trên PC thật, bằng Brave và loa thật, khoảng thời gian từ lúc bấm **Gửi câu hỏi** đến lúc **nghe được tiếng đầu tiên của câu trả lời**. Checklist cũng kiểm tra câu ngắn, nói nhỏ, tiếng ồn phòng và các lượt không có lời nói. Mục tiêu tối đa là 4 giây theo [yêu cầu voice](VOICE_PRODUCT_REQUIREMENTS.md) và [xác nhận "4 giây đi"](evidence/d74-latency-target-4s-20261103.json).

**Ngày:** 2026-11-06 (cập nhật tình trạng B3 của `/voice` ngày 2026-11-07). **Trạng thái:** CHECKLIST SẴN SÀNG / CHƯA CÓ KẾT QUẢ. Physical first-audible ≤4 giây vẫn UNVERIFIED. Phản hồi "Ổn rồi" ([ghi nhận](evidence/d74-voice-browser-owner-feedback-20261105.json)) không phải số đo.

## Đã có gì và còn thiếu gì

- [Trang thử 8092](D74_VOICE_BROWSER_TRIAL_RESULT.md) chạy HTTP thật 6/6: thời gian client gửi→nhận đủ phản hồi là 1,972–3,250 s, và 2 negative bị chặn đúng. [Compute cục bộ](D74_RESIDENT_CUDA_LATENCY_RESULT.md) tạo xong audio hoàn chỉnh trong 2,000–3,334 s. Cả hai lượt đều dùng file đã lưu, không qua microphone, Brave thật hay loa.
- Hai số "Nhận audio" và "Chuẩn bị phát" trên trang là mốc phần mềm. [trial.mjs](../apps/voice_trial/static/trial.mjs) bấm giờ từ lúc Gửi đến khi nhận phản hồi và đến khi gọi lệnh phát. Hai số này không gồm độ trễ của hệ thống âm thanh, loa hay Bluetooth. Chỉ ghi lại để tham khảo.

## Dùng trang nào

| Trang | Dùng cho checklist này? |
|---|---|
| Trang thử `http://127.0.0.1:8092` ([hướng dẫn](D74_VOICE_BROWSER_TRIAL_GUIDE.md)) | **Có.** Đây là bề mặt đầu tiên có lượt model thật qua HTTP đạt PASS (6/6, gọi API trực tiếp, không qua trình duyệt); từ 2026-11-07 `/voice` cũng có B3 PASS (xem dưới). UI đã kiểm bằng Brave headless với microphone tổng hợp và model giả. Chưa có lượt trình duyệt → model → loa nào được agent kiểm chứng. Kết quả chỉ áp dụng cho lane nghiên cứu Qwen3-ASR CUDA FP32 + CORE 32K/Fast512 + Trúc Ly CPU8. |
| Trang chính `/voice` ([UI](../apps/web/voice/page.mjs), [ADR175](ADR/175-optional-main-voice-composition-and-entrypoint-binding.md)) | **Có, cho gate B4.** Trang này vẫn mặc định tắt, chỉ bật cho mục đích `integration_evaluation` và cần mã ghép phiên. B3 đã PASS ngày 2026-11-07 theo [ADR178](ADR/178-graceful-sigterm-exit-in-b3-acceptance.md) (xem dưới), nên có thể lặp lại checklist này trên `/voice` theo gate B4 trong [ADR174](ADR/174-proposed-opt-in-authenticated-voice-integration.md). Ghi kết quả riêng cho `/voice`, không gộp với 8092. Các điều kiện 2–6 bên dưới viết theo mã của trang thử; `/voice` mượn CORE đã xác thực, nên khi đo trên `/voice` hãy ghi rõ trang đã dùng và mọi khác biệt so với các điều kiện đó. Checklist này chưa có hướng dẫn khởi chạy `/voice` (auth file, manifest operator, mã ghép phiên); cần chuẩn bị hướng dẫn đó trước khi đo B4 trên `/voice`. |

**Tình trạng B3 của `/voice`:**

- B3 lần 1 (2026-11-05): NOT_PASS (`main_voice_prepare_fault`, 6/6 hàng chưa chạy, 0 retry). [ADR176](ADR/176-bounded-foreign-gpu-tolerance-and-b3-preflight.md) ghi rằng guard thực sự kích hoạt không được log. Nguyên nhân khả dĩ nhất có bằng chứng là quy tắc NVML của ADR175 từ chối tiến trình GPU sẵn có của desktop (NVML sau lỗi thấy gnome-remote-desktop giữ 223 879 168 byte, khoảng 214 MiB hay 223,9 MB; ADR176 viết "223 MiB"). Theo operator, RSS ổn định của CORE khoảng 0,96 GiB đo ở preflight lần thay thế cho thấy trần RAM 8 GiB không phải nguyên nhân (operator 2026-11-06).
- ADR176 (ACCEPTED, vào develop qua PR #26, lên staging/production qua PR #30/#31 ngày 2026-11-07) cho phép tiến trình GPU lạ tổng ≤1 GiB và giữ nguyên các trần RAM/VRAM. Chủ dự án duyệt đúng một panel B3 thay thế (owner 2026-11-06, operator record).
- B3 thay thế (2026-11-06 17:45): preflight thấy 2 tiến trình GPU lạ dùng tổng khoảng 260 MiB; Chuẩn bị mất 56,78 s; 4/4 hàng speech EXACT_COMPLETE_PCM, server 2,247–3,241 s (client 2,250–3,244 s); 2/2 negative CORRECT_NO_SPEECH trong khoảng 0,017 s; đúng 6 VAD/4 ASR/4 CORE/4 TTS + 1 readiness, 3 worker đã join, CORE do runner sở hữu thoát mã 0, nguồn không đổi. Kết quả vẫn **NOT_PASS** (`main_voice_call_budget_or_cleanup`): runner đòi web process thoát mã 0, còn uvicorn 0.54.0 trả −15 (SIGTERM) dù log cho thấy lifespan đã tắt đầy đủ, nên bước kiểm tra CORE mượn còn sống sau khi app tắt chưa được đánh giá trong lượt đó. Không retry; khi đó muốn chạy thêm panel nào cần quyết định mới của chủ dự án.
- Chủ dự án trả lời "Duyệt B3 mới" (owner 2026-11-06): sửa runner để chỉ chấp nhận mã −SIGTERM khi audit chứng minh ứng dụng đã tắt êm đầy đủ, rồi chạy đúng một panel mới. [ADR178](ADR/178-graceful-sigterm-exit-in-b3-acceptance.md) (ACCEPTED 2026-11-07, vào develop qua PR #28, lên staging/production qua PR #30/#31 ngày 2026-11-07) chỉ đổi runner B3; runner mới cũng đòi 3 worker join sạch và release trả HTTP 200 rồi `idle` không lỗi.
- B3 theo ADR178 (2026-11-07 10:31): **PASS**, đúng một panel, 0 retry. Preflight thấy CORE RSS khoảng 1,17 GiB và 2 tiến trình GPU lạ dùng tổng khoảng 225 MiB; Chuẩn bị mất 51,45 s; 4/4 hàng speech EXACT_COMPLETE_PCM, server 2,608–3,747 s (client 2,619–3,753 s); 2/2 negative CORRECT_NO_SPEECH trong 0,017–0,024 s; đúng 6 VAD/4 ASR/4 CORE/4 TTS + 1 readiness, 3 worker join sạch (mã 0, không bị buộc dừng), web process thoát −15 và runner xác nhận đã tắt êm đầy đủ, release HTTP 200 rồi `idle` không lỗi, CORE mượn còn sống sau khi app tắt, CORE do runner sở hữu thoát mã 0 (đỉnh VRAM 8792 MiB, VRAM trống thấp nhất 2251 MiB), nguồn không đổi. Cả 6 hàng có playback, PCM và WAV giống hệt lượt thay thế. Hàng chậm nhất chỉ còn khoảng 0,25 s dưới trần 4 s. Đây là thời gian xử lý cộng HTTP loopback với file đã lưu, không qua microphone, Brave hay loa, nên physical first-audible vẫn UNVERIFIED.
- Sau PR #33 (2026-11-07, merge `cebf9a0` vào develop): B3 PASS ở trên đo trên commit `73cecdf`, trước bản sửa lỗi decoder P2. Trong phạm vi snapshot của B3, develop nay chỉ khác ở `src/infrastructure/ocr_worker.py`, là launcher dùng cho bước chuyển audio TTS sang playback ở cả `/voice` lẫn trang thử 8092. `staging`/`production` chưa có thay đổi này. Chủ dự án chọn chấp nhận B3 PASS kèm ghi chú hay duyệt đúng một panel B3 mới ([kết quả B3](D74_MAIN_VOICE_B3_RESULT.md), mục "Sau PR #33"; [hồ sơ D90](D90_RELEASE_DECISION_DOSSIER.md)). Khi đo vật lý, ghi commit đang chạy vào phiếu.
- Báo cáo đầy đủ: [kết quả B3](D74_MAIN_VOICE_B3_RESULT.md), receipt công khai [lượt ADR178](evidence/d74-main-voice-b3-adr178-result.json) và [lượt thay thế ADR176](evidence/d74-main-voice-b3-adr176-result.json); receipt chi tiết nằm ở thư mục cục bộ không đưa vào git (`data/backups/d74-main-integration-first/`, `data/backups/d74-main-integration-adr176/`, `data/backups/d74-main-integration-adr178/`).

Kết quả trên 8092 không tự chuyển thành kết quả của `/voice`, vì `/voice` mượn CORE đã xác thực, có cơ chế cấp quyền dùng GPU và BFF riêng. ADR176 chỉ đổi mã của `/voice` và runner B3, ADR178 chỉ đổi runner B3; cả hai không đổi nguồn trang thử. Trang thử không từ chối tiến trình GPU lạ: bộ đo của nó chỉ cộng VRAM của tiến trình do chính nó tạo ([vi_voice_cuda_check.py](../benchmarks/scripts/vi_voice_cuda_check.py), `Monitor.sample`). Tuy vậy, VRAM của tiến trình lạ vẫn trừ vào các ngưỡng VRAM trống ở điều kiện 5.

## Điều kiện trước khi đo

1. Dùng Brave trên chính PC chạy repository, cùng microphone đã dùng ở [bước kiểm tra mic](D74_PHYSICAL_MIC_CHECK.md). Phát qua **loa thật**, không dùng tai nghe. Ghi lại loại loa (tích hợp, dây hoặc Bluetooth) và giữ nguyên âm lượng suốt buổi. Nếu dùng Bluetooth, độ trễ của nó vẫn tính vào kết quả.
2. Trước mỗi lần Chuẩn bị, khi Brave (và OBS nếu dùng) đã mở, kiểm tra trong terminal. Chạy xong các lệnh này rồi mới bấm Chuẩn bị (xem điều kiện 6):
   ```sh
   pgrep -a llama-server              # phải không in ra gì
   ss -ltn | grep ':18080 '           # phải không in ra gì
   nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits   # phải ≥ 14336 (MiB); nên ≥ 14940
   grep MemAvailable /proc/meminfo    # phải ≥ 14680064 kB; nên ≥ khoảng 19922944 (19 GiB)
   ```
   Trang thử tự chạy CORE riêng, từ chối nạp nếu một điều kiện trên không đạt, và dừng nếu trong lúc chạy xuất hiện `llama-server` khác ([d14_completion.py](../benchmarks/scripts/d14_completion.py), `OwnedServer.start`, `OwnedServer.monitor`). Các ngưỡng "phải" chỉ là kiểm tra trước khi nạp CORE. Sau khi CORE đã nạp (khoảng 8790 MiB VRAM theo receipt B3 `/voice` ngày 2026-11-06 và 2026-11-07, cả hai lượt đều có đỉnh 8792 MiB, cùng trình khởi chạy CORE), trang còn đòi VRAM trống ≥6 GiB trước khi nạp ASR và RAM khả dụng ≥14 GiB trước mỗi worker ([native.py](../apps/voice_trial/native.py), `IPCWorker.start`). Mức "nên" là ước lượng từ receipt, không phải bảo đảm: VRAM 8792 + 6144 ≈ 14940 MiB; RAM cộng thêm khoảng 5 GiB, vì RAM khả dụng giảm từ lúc kiểm tra trước khi nạp CORE (`owned-core/preflight.json`) đến mức thấp nhất khi chạy: khoảng 3,4 GiB trong B3 2026-11-06 (20,93 → 17,50 GiB) và khoảng 4,9 GiB trong B3 2026-11-07 (21,92 → 16,99 GiB). Không tự dừng dịch vụ dùng chung; nếu không đạt thì chọn lúc khác hoặc báo lại. Không chat hay chạy model khác trong lúc đo.
3. Dùng một web process mới để có đủ 24 lượt gửi và 3 lần Chuẩn bị (reload trang không reset quota). Service thử tạo ngày 2026-11-05 chỉ có thời hạn 4 giờ. Nếu nó vẫn chạy, dừng bằng `systemctl --user stop local-assistant-voice-trial.service`, rồi từ `ai/` chạy lệnh trong mục "Vận hành khi cần" của [hướng dẫn](D74_VOICE_BROWSER_TRIAL_GUIDE.md). Khi xong, dừng bằng Ctrl+C.
4. Bấm **Chuẩn bị** và đợi dòng "Sẵn sàng. Bạn có thể ghi câu hỏi." rồi mới bắt đầu đo. Thời gian Chuẩn bị ghi riêng (lượt trước trên 8092 mất 43,843 s; B3 `/voice` ngày 2026-11-06 mất 56,78 s và ngày 2026-11-07 mất 51,45 s) và không tính vào 4 giây. Đo trên video: từ khung trạng thái đổi sang "Đang chuẩn bị, vui lòng chờ…" đến khung hiện "Sẵn sàng…". Sai số có thể tới khoảng 1,5 s, vì trang chỉ hỏi trạng thái mỗi 1,5 s ([page.mjs](../apps/voice_trial/static/page.mjs)).
5. Nếu trang báo "Chưa chuẩn bị được", dừng lại và báo. Không sửa nguồn, không nới guard, không thử lặp. Guard giữ nguyên: trước khi nạp CORE cần RAM khả dụng ≥14 GiB, VRAM trống ≥14 GiB, cổng 18080 trống và không có `llama-server` khác; trước khi nạp mỗi worker vẫn cần RAM khả dụng ≥14 GiB, riêng ASR cần VRAM trống ≥6 GiB; trong lúc chạy VRAM trống phải ≥1,25 GiB (ASR) và ≥512 MiB (CORE), RAM khả dụng ≥4 GiB, tổng RSS worker+CORE ≤8 GiB ([d14_completion.py](../benchmarks/scripts/d14_completion.py); [vi_voice_campaign.py](../benchmarks/scripts/vi_voice_campaign.py), `Worker.check`; [native.py](../apps/voice_trial/native.py), `IPCWorker`). VRAM của ứng dụng khác (desktop như gnome-remote-desktop, Brave, OBS nếu dùng) vẫn trừ vào các ngưỡng VRAM trống. Theo receipt B3 cục bộ, VRAM trống khi chưa nạp model của dự án chỉ khoảng 14,66 GiB (2026-11-05) và 14,96 GiB (2026-11-06); sau khi nạp CORE, phần dư so với ngưỡng 6 GiB của ASR chỉ khoảng 0,1–0,4 GiB (94 MiB đo ngày 2026-11-05; khoảng 387 MiB tính cho ngày 2026-11-06).
6. Giữ tab Brave luôn hiển thị. Chuyển tab, thu nhỏ cửa sổ hoặc nhấn Escape khi đang có lượt chạy sẽ hủy lượt đó và thu hồi nhóm model (phải Chuẩn bị lại). Trong lúc "Đang chuẩn bị…" (khoảng 44–57 s), các thao tác này hủy lần Chuẩn bị đó và vẫn trừ 1 trong 3 lần Chuẩn bị; sau khi bấm Dừng mà chưa Gửi, chúng xóa bản ghi câu hỏi ([page.mjs](../apps/voice_trial/static/page.mjs), `cancel`; [main.py](../apps/voice_trial/main.py), `Controller.release`). Vì vậy không rời tab Brave từ lúc bấm Chuẩn bị cho tới khi hiện "Sẵn sàng…". Nhóm model chỉ sẵn sàng 8 phút và trang không hiện thời gian còn lại ([native.py](../apps/voice_trial/native.py), `NativeRuntime.health`; [main.py](../apps/voice_trial/main.py), `Controller.watch`). Ghi thời điểm "Sẵn sàng" trên video; không bắt đầu lượt mới khi còn dưới khoảng 1 phút trước mốc 8 phút. Nếu nhóm hết hạn sát hoặc trong một lượt, trang có thể báo "Không xử lý được câu hỏi…" hoặc "Phiên đã dừng…" (lượt đã bị trừ quota), hoặc "Máy đang bận…" khi trang chưa kịp cập nhật trạng thái (server không trừ lượt). Ghi nguyên văn thông báo và nguyên nhân hết hạn trong cột Ghi chú; hàng đó vẫn là FAIL theo quy tắc bên dưới. Kết quả trên trang tự xóa sau 5 phút.
7. Dùng câu trung tính, không nói thông tin cá nhân, vì câu nhận dạng và câu trả lời hiện trên màn hình và sẽ có trong video.

## Cách đo khách quan

Không lấy số trên trang làm kết quả. Mốc bắt đầu và mốc kết thúc phải lấy từ **cùng một bản ghi**.

**Cách A (khuyến nghị): quay một video bằng điện thoại.** Đặt điện thoại cố định, camera thấy rõ dòng trạng thái, nút Gửi và vùng kết quả, microphone của điện thoại ở gần loa. Quay 60 khung/giây nếu máy hỗ trợ; mỗi nhóm quay một video liền mạch. Ở đầu video, vỗ tay một lần trong khung hình để kiểm tra độ lệch giữa hình và tiếng.

**Cách B (thay thế): quay màn hình bằng OBS.** Ngày 2026-11-06 không tìm thấy OBS trong PATH, và checklist này không cài thêm phần mềm. Nếu bạn tự dùng OBS: rãnh "Desktop Audio" chỉ là tín hiệu hệ thống trước khi ra loa, nên ghi kết quả là `system_audio`, không phải tiếng từ loa. Muốn tính là tiếng từ loa thì thêm một rãnh microphone đặt gần loa và đọc mốc trên rãnh đó.

Cách xác định các mốc:

- **t_gửi:** khung hình đầu tiên trang thay đổi vì cú bấm Gửi: trạng thái đổi thành "Đang nghe và tạo câu trả lời…", nút Gửi mờ đi, trình nghe lại câu hỏi biến mất và dòng ghi âm đổi thành "Đã gửi câu hỏi và tắt microphone." Các thay đổi này xảy ra ngay trong sự kiện bấm ([page.mjs](../apps/voice_trial/static/page.mjs), [trial.mjs](../apps/voice_trial/static/trial.mjs)), nên khung này không thể sớm hơn cú bấm.
- **t_tiếng:** điểm waveform bắt đầu âm tiết đầu tiên của câu trả lời. Không lấy tiếng click chuột, tiếng tách/pop, tiếng ồn nền hay khoảng lặng.
- **Trễ = t_tiếng − t_gửi + 1 khoảng khung**, trong đó "1 khoảng khung" là khoảng cách giữa khung t_gửi và khung liền trước. Phần cộng thêm này bù việc camera chỉ thấy thay đổi ở khung sau cú bấm. Mốc hình vẫn trễ hơn cú bấm một chút do trình duyệt và màn hình vẽ lại, nên Trễ có thể hơi thấp hơn thực tế. Nếu rãnh tiếng nghe rõ tiếng click chuột lúc bấm Gửi, ghi thêm thời điểm đó vào Ghi chú để đối chiếu; cột t_gửi vẫn dùng mốc hình. Ghi 2 chữ số thập phân.

Đọc mốc bằng ffmpeg/ffplay (có sẵn ở `/usr/bin`, đã kiểm tra ngày 2026-11-06). Chạy trong một thư mục tạm **nằm ngoài repository**, vì video có giọng nói của bạn:

```sh
# 1. Liệt kê các thời điểm âm thanh bắt đầu sau ít nhất 0,15 s yên lặng
ffmpeg -hide_banner -i nhom1.mp4 -vn -af silencedetect=noise=-35dB:d=0.15 -f null - 2>&1 | grep silence_end
# 2. Nghe đoạn quanh một mốc để xác nhận đó đúng là âm tiết đầu của câu trả lời
ffplay -autoexit -ss 71.0 -t 2 nhom1.mp4
# 3. Xuất các khung hình trong khoảng 1 giây quanh cú bấm Gửi, kèm thời gian của từng khung
ffmpeg -hide_banner -i nhom1.mp4 -an -vf "select='between(t,70.5,71.5)',showinfo" -fps_mode passthrough khung_%03d.png 2>&1 | grep -oE "n: *[0-9]+ +pts: *[0-9]+ +pts_time:[0-9.]+"
```

- Ảnh `khung_001.png` ứng với dòng `n: 0`. Mở các ảnh theo thứ tự, chọn ảnh đầu tiên đã đổi trạng thái; `pts_time` trên dòng tương ứng chính là t_gửi.
- Thay `70.5`, `71.5` và `71.0` bằng thời điểm thật của từng lượt (xem video để ước lượng trước).
- Nếu tiếng ồn liên tục khiến lệnh 1 không tách được mốc, thử `-30dB` và ghi lại ngưỡng đã dùng. Luôn nghe lại bằng lệnh 2 để xác nhận.
- Độ lệch hình–tiếng = (`silence_end` của tiếng vỗ tay) − (`pts_time` của khung hai bàn tay chạm nhau). Nếu lệch quá 2 khung, ghi lại và báo; không tự sửa số đo.
- Có thể dùng trình chỉnh video hiển thị waveform trên cùng timeline thay cho ffmpeg; khi đó ghi tên công cụ.

## Bảng tình huống cố định

| Mã | Tình huống | Nói gì | Số lượt | Kết quả mong đợi |
|---|---|---|---:|---|
| S1 | Câu thường, phòng yên | Lần lượt: "Xin chào, bạn có thể giúp tôi việc gì?" / "Hôm nay tôi nên sắp xếp công việc thế nào cho hợp lý?" / "Bạn giải thích ngắn gọn vì sao bầu trời có màu xanh nhé." | 3 | Trả lời tự phát, Trễ ≤ 4,00 s |
| S2 | Câu ngắn | "Chào bạn." / "Bạn là ai?" / "Cảm ơn nhé." Bản ghi vẫn phải dài ít nhất 1 giây, vì nút Gửi chỉ bật khi đủ 1 giây | 3 | Như S1 |
| S3 | Nói nhỏ | Ba câu của S1, nói nhỏ nhưng vẫn ra tiếng (không thì thào), giữ khoảng cách tới mic như cũ | 3 | Như S1 |
| S4 | Có tiếng ồn phòng | Ba câu của S1, giọng thường; tiếng ồn đều từ một thiết bị khác, không phát qua loa PC | 3 | Như S1 |
| N1 | Không nói, phòng yên | Ghi 3 giây im lặng | 2 | Không có câu trả lời, không có tiếng; trang báo "Không nhận thấy lời nói…" |
| N2 | Không nói, có ồn | Ghi 3 giây chỉ có tiếng ồn như S4 | 2 | Như N1 |

**Thứ tự:** Nhóm 1 (Chuẩn bị lần 1, video 1): S1 ×3, S2 ×3, N1 ×2. Nhóm 2 (Chuẩn bị lần 2, video 2): S3 ×3, S4 ×3, N2 ×2. Tổng cộng 16 lượt và 2 lần Chuẩn bị, còn dư 8 lượt và 1 lần dự phòng. Mỗi nhóm có 8 lượt trong chưa tới 8 phút, nên làm liền tay.

Sau lượt cuối của nhóm 1, dừng video 1 và chờ nhóm 1 tự hết hạn (8 phút kể từ "Sẵn sàng") cho tới khi trang hiện "Bấm Chuẩn bị để bắt đầu phiên thử.", kiểm tra lại điều kiện 2, rồi mới bấm Chuẩn bị lần 2. Khi nhóm đang sẵn sàng, nút Chuẩn bị bị mờ. Khi nhóm đã sẵn sàng và không có lượt chạy, Hủy / xóa không thu hồi nhóm; nhóm chỉ được thu hồi khi hết hạn, khi một guard tài nguyên/tiến trình ở điều kiện 5 kích hoạt, hoặc khi dừng web process (Ctrl+C) ([page.mjs](../apps/voice_trial/static/page.mjs), `render`, `cancel`; [main.py](../apps/voice_trial/main.py), `Controller.prepare`, `Controller.watch`; [native.py](../apps/voice_trial/native.py), `NativeRuntime.health`).

Nếu nhóm hết hạn hoặc bị thu hồi giữa chừng (lượt lỗi hay hết giờ cũng thu hồi nhóm, trừ khi trang báo không nhận thấy lời nói hoặc "Bản ghi cần dài từ 1 đến 20 giây."; [main.py](../apps/voice_trial/main.py), `Controller.execute`), bấm Chuẩn bị lại (dùng lần Chuẩn bị dự phòng; ghi rõ đây là lần thứ mấy) và ghi chú; nếu xảy ra ở nhóm 1 thì nhóm 2 sẽ dùng lần Chuẩn bị cuối cùng. Không chạy lại các lượt đã xong. Nếu đã dùng hết 3 lần Chuẩn bị, để trống các lượt còn lại và báo; kết luận khi đó là CHƯA ĐỦ. Với S4, giữ tiếng ồn trong lúc ghi câu hỏi; có thể tắt ngay sau khi bấm Dừng để dễ đọc waveform, vì sau đó server chỉ xử lý bản ghi đã gửi. Ghi rõ có tắt hay không.

## Các bước cho mỗi lượt

1. Khi trang báo "Sẵn sàng…", bấm **Ghi câu hỏi**, nói (hoặc giữ im lặng/để tiếng ồn với N1/N2), rồi bấm **Dừng và nghe lại**. Có thể bỏ qua phần nghe lại để tiết kiệm thời gian của nhóm.
2. Giữ yên khoảng 2 giây rồi bấm **Gửi câu hỏi** một lần. Không nói, không gõ phím cho tới khi câu trả lời bắt đầu phát.
3. Nghe hết câu trả lời. Ghi nhanh vào phiếu: trả lời tự phát hay phải bấm nút phát, câu nhận dạng đúng hay sai, thông báo lỗi (nếu có) và hai số trên trang. Bấm Ghi câu hỏi ở lượt sau sẽ xóa hai số này; nếu camera thấy vùng kết quả thì có thể điền chúng sau từ video.
4. Không gửi lại câu cũ, không bỏ lượt chậm hoặc lượt lỗi.

## Phiếu kết quả

Thông tin chung: ngày giờ đo; trang đã dùng (8092 hay `/voice`) và commit đang chạy (`git log --oneline -1`); phiên bản Brave (xem ở `brave://version`); hệ điều hành; microphone; loa (model, tích hợp/dây/Bluetooth); mức âm lượng; thiết bị quay và số khung/giây; độ lệch vỗ tay ở nhóm 1 và nhóm 2; kết quả kiểm tra ở điều kiện 2, thời gian Chuẩn bị và thời điểm "Sẵn sàng" của từng lần; nguồn ồn dùng cho S4/N2 và có tắt sau Dừng hay không; công cụ đọc mốc và ngưỡng `silencedetect` đã dùng.

| # | Mã | t_gửi (s) | t_tiếng (s) | Trễ (s) | Tự phát? | Nhận dạng (Đúng/Sai một phần/Sai/Không có) | Số trên trang | Ghi chú/lỗi |
|---:|---|---|---|---|---|---|---|---|
| 1 | S1-1 | | | | | | | |
| 2 | S1-2 | | | | | | | |
| 3 | S1-3 | | | | | | | |
| 4 | S2-1 | | | | | | | |
| 5 | S2-2 | | | | | | | |
| 6 | S2-3 | | | | | | | |
| 7 | N1-1 | | | | | | | |
| 8 | N1-2 | | | | | | | |
| 9 | S3-1 | | | | | | | |
| 10 | S3-2 | | | | | | | |
| 11 | S3-3 | | | | | | | |
| 12 | S4-1 | | | | | | | |
| 13 | S4-2 | | | | | | | |
| 14 | S4-3 | | | | | | | |
| 15 | N2-1 | | | | | | | |
| 16 | N2-2 | | | | | | | |

## Quy tắc PASS/FAIL

- **Lượt có lời nói** PASS khi câu trả lời tự phát và Trễ ≤ 4,00 s. Lượt bị FAIL nếu vượt 4,00 s, phải bấm nút phát, bị báo không có lời nói, hoặc bị báo bận/hết giờ/lỗi. Nếu không ghi được video thì đánh dấu KHÔNG ĐO ĐƯỢC; đó không phải PASS.
- **Lượt không lời (N1/N2)** PASS khi không có câu nhận dạng, câu trả lời hay tiếng trả lời. Có bất kỳ câu trả lời nào là FAIL.
- Một tình huống chỉ PASS khi mọi lượt của nó đều PASS. Xét theo lượt chậm nhất, không lấy trung bình.
- Kết luận cho phạm vi này chỉ là PASS khi đủ 12/12 lượt có lời nói và 4/4 lượt không lời đều PASS. Có lượt FAIL thì kết luận là FAIL; thiếu lượt thì là CHƯA ĐỦ.
- Chỉ chạy lượt bổ sung khi bị lỗi quay video, và ghi "bổ sung cho #n"; lượt gốc giữ trạng thái KHÔNG ĐO ĐƯỢC. Không thêm lượt để thay cho một lượt chậm hoặc FAIL, kể cả lượt FAIL vì nhóm hết hạn.
- Cột Nhận dạng không làm thay đổi kết quả thời gian. Đó là quan sát để chủ dự án quyết định riêng về câu ngắn, nói nhỏ và tiếng ồn. Kết quả trong khoảng 3,90–4,00 s vẫn áp dụng các quy tắc trên, nhưng ghi chú thêm "sát ngưỡng".

## Ngoài phạm vi và không được suy ra

- Lượt đo trên 8092 không phải nghiệm thu trang `/voice` chính. Đây cũng không phải B3 hay việc bật sản phẩm; lượt lặp lại trên `/voice` chỉ là phép đo vật lý cho gate B4. Không tự chuyển kết quả 8092 sang `/voice`.
- Đây không phải phép đo cold-start: thời gian Chuẩn bị được ghi riêng.
- Kết quả chỉ áp dụng cho PC, Brave, microphone, loa và lane đã ghi. Nó không phải p95, không phải SLO chung, và không đại diện cho thiết bị khác, mạng ngoài hay lúc GPU/chat đang chạy song song.
- 3 lượt mỗi tình huống chỉ là quan sát, không phải WER/CER hay chất lượng ASR tổng quát. Đây cũng không phải đánh giá chất lượng câu trả lời của CORE, phát âm hay độ tự nhiên của giọng; các vòng chỉnh phát âm đã dừng.
- Checklist không chọn model, giọng hay default, không duyệt quyền sử dụng/phân phối model hay giọng (LICENSE MIT của repo, do chủ dự án chọn (owner 2026-11-06, operator record), đã vào develop qua PR #25 và lên staging/production qua PR #30/#31 ngày 2026-11-07, không thay đổi điểm này), và không đóng D86/D89 sản phẩm hay D90 release ([các D còn mở](OPEN_DAYS_20261105.md)).
- Test phần mềm (766 Python/20 JS của trang thử; 1070 Python liên quan/27 JS của gate phần mềm B3 thay thế và 1122 Python liên quan/27 JS của gate phần mềm B3 ADR178, không phải full suite; CI của repo), các mốc trên trang, số HTTP của B3 và phản hồi "Ổn rồi" đều không thay được phép đo này.

## Gửi kết quả

Dán phiếu đã điền vào chat dưới dạng text: thông tin chung, 16 hàng (cộng các hàng bổ sung nếu có) và thời gian Chuẩn bị. Không gửi video, audio, key hay mã ghép phiên. Agent sẽ ghi đúng những số bạn báo thành evidence "do chủ dự án đo", không tự quan sát và không làm tròn lại; mục nào thiếu sẽ ghi là chưa đo. Nếu bạn muốn agent đọc mốc từ video trên máy, hãy nêu rõ đường dẫn và xác nhận đồng ý. Khi đó agent chỉ báo các thời điểm, không chép nội dung, và kết quả được ghi riêng là "agent đọc từ video của chủ dự án".

Khi xong, bấm **Hủy / xóa** để xóa kết quả trên trang, rồi dừng web process bằng Ctrl+C; bước này mới thu hồi model nếu nhóm chưa hết hạn. Xóa video nếu không cần giữ. Không đặt video vào repository.
