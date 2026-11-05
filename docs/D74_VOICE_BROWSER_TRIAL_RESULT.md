# D74 — Trang thử voice chạy được và kết quả kiểm chứng

**Mục đích:** Ghi đúng phần đã triển khai cho yêu cầu “Làm đi” sau khi chủ dự án hỏi link kiểm thử, tách UI/HTTP/model thật khỏi nghiệm thu tiếng phát từ loa.

**Ngày:** 2026-11-05. **LOCAL_UI_AND_NATIVE_HTTP_VERIFIED**. [Mở trang trên cùng máy](http://127.0.0.1:8092) · [Hướng dẫn](D74_VOICE_BROWSER_TRIAL_GUIDE.md) · [Receipt/hashes](evidence/d74-voice-browser-trial-result.json).

## Thay đổi đã thực hiện

Thêm riêng `apps/voice_trial`, không sửa recorder cũ hoặc750file application baseline. Reuse nguyên ExplicitRecorder/worklet đã PASS; trang thử giới hạn capture1–20giây theo ASRcontract cũ. Prepare chủ động, Ghi/Dừng/Gửi/Hủy, hiển thị transcript/câu trả lời như text và phát audio hoàn chỉnh. Reload không tự thu, nạp model hoặc gửi dữ liệu. Cookie HttpOnly/SameSiteStrict và exactloopbackHost/Origin/FetchMetadata bảo vệ API; URL không chứa credential. Không expose lên mạng hoặc tích hợp API sản phẩm.

Giữ đúng research lane: Silero v5 detector-only peak view; toàn bộ PCM/clock gốc cho Qwen3-ASR-0.6B CUDAFP32/eager/TF32off; ownedCORE32K/Fast512 và Trúc Ly CPU8/FP32 accepted reading. Worker mới chỉ xác minh manifest/budget rồi gọi nguyên implementation đã đo. Không tải/cài thêm, chọn model/default/giọng sản phẩm, thay context/cap hoặc sửa phát âm. [ADR173](ADR/173-loopback-voice-trial-and-playback-instrumentation.md).

Prepare mất43,843giây trong lượt thực tế gồm xác minh nguồn/runtime/checkpoint và nạp model. Đây là bước riêng trước Gửi, không phải cold-request4second claim. Có một1secondzero-ASRreadiness đã khai báo. Model chỉ được nạp sau Prepare; khi bàn giao đã release hết nhóm tự kiểm tra, để trangidle chờ chủ dự án.

## Kiểm thử phần mềm và trình duyệt

**766 Python PASS /0FAIL/ERROR/SKIP /9,29s**, gồm59controls mới và17recording legacy ngoài nhóm690trước. **20 JS PASS**, gồm7mới và13recorder cũ. Ruff/format/module/class/function descriptionsPASS. Full5889 vẫn là lịch sử, không chạy lại hoặc gộp vào kết quả này.

Brave headless/Chromium154.0.8037.58 thực thi UI thật bằng **microphone tổng hợp**, outputmuted và modelAPIgiả: không tự capture/POST; dừng tắt fake tracks; Send chủ động; trả/phát đúng output hiện hành; Hủy chặn response muộn; TTLxóa replay/text; từ chối quyền; giới hạn đúng320000samples/20giây; Escape; no browserstorage/pageerror/externalrequests. Desktop/mobile320px/darkmode đã chụp và xem. Hai fake submissions chỉ có một output phát trong môi trường test; không tính là nativeTTS hoặc nghe từ loa.

Lượt browser đầu giữ FAIL vì test dùng `fetch(blob:)` bị CSPchặn. Test đọc trực tiếp Blob giả của nó, giữ nguyên CSP; lượt xác nhận riêng PASS. Một fixture retirement cũng thiếu auditdirectory trước native; đã sửa/giữ log, không có retry model. Nguồn model-free đầu và finalsource được giữ nguyên riêng.

Braveheadless không mock cũng đã mở trang thật, nhận sessioncookie, GETstatus200 và POSTcancel200 với Origin do browser tạo; securecontext=True, không Prepare/microphone/inference. Đây là kiểm chứng link/session/protocol, không phải đo thiết bị thật.

## HTTP thật: 6/6 PASS, không retry

Bốn nguồn speech và hai negative gốc đã dùng ở các lượt trước, không phải holdoutmới. Một Prepare duy nhất; gọi thật API qua TCP, runtime inference giữ nguyên. Mỗi speech phải trùng byte transcript/CORE/playbackPCM với priorqualified output, đủ EOS/stop và maximum≤4seconds.

| Nguồn VI | Server nhận→audio hoàn chỉnh | Client gửi→nhận đủ phản hồi |
|---|---:|---:|
| 0036 | 1,969 s | **1,972 s** |
| 0024 | 2,685 s | **2,688 s** |
| 0078 | 3,247 s | **3,250 s** |
| 0040 | 3,112 s | **3,114 s** |

4/4speech exactcomplete,2/2negative HTTP422/no_speech và không dispatchASR/CORE/TTS. Đúng6VAD/4ASR/4CORE/4TTS+1readiness,0retry/runtime/guard failure. Không đổi tốc độ/sampling, cắt câu, dùng beep hoặc lấy trung bình. Sau release cả3worker exit0, ownedCOREexit0/reaped; không còn model/native process hoặc RAMworkspace. Web service riêng tiếp tục chạy.

## Tài nguyên, dữ liệu và audit

Giữ các guard đã chốt: pre-loadMemAvailable14GiB, aggregateworkers+CORE8GiBRAM/TTS2GiB, CUDA64GiBvirtual/allocator4GiB/ownedASR4,5GiB/free1,25GiB/preload6GiB; workerwall/CPUcaps giữ nguyên, sampler chạy cả lúcidle. ActualASRpeak~3,92GiBVRAM; không cộng peakRSS khác thời điểm thành concurrent peak. Bounded24submissions/3preparations perwebprocess; groupready8phút/1turn65giây, không tự reload/retry. Cancel/disconnect thu hồi và join, cần Prepare lại.

Body canonicalWAV không resample/trim/gain cho ASR; separate full-length detectorcopy. Singleadmission trước bodyread, bounded UUID/body/quotas, tombstonecancel chống late submit, resultgeneration chống phátresponsecũ. Userinput/nativechunks/diagnostics ở64MiBcappedprivate`/dev/shm`, xóa sau joinedturn/groupclose; TMPDIR=/dev/shm giữ conversiontempfile trongRAM. Persistentreceipt/journal chỉ chứa counts/resources/finiteevents, không rawaudio/text/answer/privatefingerprints; kiểm tra journal bằng chính4publicoutputs. SDK/model có thể giữ transientbuffer trongRAM/VRAM tới groupretirement; không tuyên bố secure memory erasure hoặc hardware cache wiping.

Audit readonly xác nhận source16file (15code/test+ADR),750application/210protected,14ASRartifacts,originalruntime/officialVAD,15870CUDA SDKfiles và9priorresult hashes không đổi.2959priorfiles/evidence cũng khớp. Native0/cùng15containers baseline phục hồi; không Vault/database/Qdrant/Docker/provider/shared-service mutation. Thêm đúng owneduserunit`local-assistant-voice-trial.service`,127.0.0.1:8092,khôngaccesslog/khôngURLtoken, tự dừng sau4giờ. Chỉ service mới này được restart trước native để nạp finalcode; không động dịch vụ khác.

[Code đầy đủ](../data/backups/d74-voice-browser-trial-first/full-code.zip) gồm final15code/test,ADR173,dependencies nguyên bản, source model-free đầu/software logs/receipts. Không chứa ownerAGENTS/private devlog/.env/key/weights hoặc capture của người dùng.

## Gate còn lại

URLthật, UIfunctional, realbrowsercookie/Origin và realHTTPnative6/6 đã đạt; chưa có realmic→realbrowser→loa nghe thực tế. Các số nhận audio/scheduledplayback trên trang không phải physicalfirst-audible. Chủ dự án giờ chỉ cần mở link, Prepare, ghi/dừng/gửi và nghe; dùng bản ghi màn hình kèm tiếng loa nếu cần đối chiếu mốc4giây. Không yêu cầu nghe lại vòng phát âm đã dừng hoặc làm lại bộ mic cũ đã PASS. D60deferred; physical4seconds, voice/model/rights/default/product/D74vàD90release vẫn OPEN.
