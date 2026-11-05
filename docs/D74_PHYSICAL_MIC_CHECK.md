# D74 — Kiểm tra microphone thật trước nghiệm thu voice

**Mục đích:** Hướng dẫn chủ dự án kiểm tra phần recorder local đã có bằng thiết bị thật, tách biệt với TTS listening và ASR/CORE/TTS sản phẩm.

## Trang thử voice đã chạy — 2026-11-05

**URL trên cùng máy: [http://127.0.0.1:8092](http://127.0.0.1:8092)**. [Cách mở/ghi/dừng/gửi/nghe và kiểm chứng](D74_VOICE_BROWSER_TRIAL_GUIDE.md), [kết quả và receipt](D74_VOICE_BROWSER_TRIAL_RESULT.md). Thêm optional loopback research surface riêng; recorder cũ/750application baseline giữ nguyên, không chọn model/default sản phẩm. Prepare chủ động, không tự thu/nạp/gửi khi mở trang; đúng QwenCUDAFP32/CORE32KFast512/TrúcLyCPU8 đã qualified.

766relatedPythonPASS/20JSPASS, Braveheadless fake-mic/muted/mocked-model UI PASS; browser thật không mock GET/POSTcookie/Origin cũng PASS, không mở microphone. RealHTTPnative6/6:4speech ASR/CORE/playback exactprior, clientroundtrip1.972–3.250s và2negative chặn đúng;6VAD/4ASR/CORE/TTS+1readiness,0retry/guard/runtimefault, toàn bộmodel thu hồi. Lượt Prepare43.843s riêng trướcGửi; không gộp thành cold4secondPASS. Giữ firstCSPfixturefailure/oldresults, không nới policy/model/cap hoặc tải thêm.

**P1 còn lại: chủ dự án kiểm chứng actualmic→Brave→loa/physical4seconds qua URL có thật**, không coi marker “Chuẩn bị phát” là tiếng loa. Web service riêng đangchạy/loopback/4giờ; groupmodel8phút,24attempts/3prepares perwebprocess, RAM-only turnfiles/ephemeral browserresults. Phạm vi userdevice/voice/model/rights/default/product/D74/D90release vẫnOPEN; D60deferred, pronunciationcycles dừng. Full5889là lịch sử, không rerun hoặc tự đóng ngày/gate còn thiếu.

**Trạng thái 2026-11-03:** OWNER-REPORTED CAPTURE/PLAYBACK CHECKS PASS. Chủ dự án đã kiểm tra bằng Brave với microphone cắm vào PC: nghe rõ, đủ câu, không rè; Dừng/Hủy/Escape/chuyển tab đều tắt thu. Ba kiểm tra bổ sung mở/reload, từ chối quyền và giới hạn 30 giây đều được chủ dự án xác nhận đạt. [Kết quả tổng hợp](evidence/d74-owner-physical-mic-completion-20261103.json), [báo cáo đầu giữ nguyên](evidence/d74-owner-physical-mic-20261103.json). Đây là kết quả do chủ dự án báo cáo, agent không tự quan sát, mở microphone hoặc cấp quyền. [Phạm vi recorder D71](D71_EXPLICIT_RECORDING.md) vẫn giữ nguyên.

## Kết quả đã nhận và phần còn lại

| Quan sát | Kết quả chủ dự án báo cáo |
|---|---|
| Nghe lại bản ghi | PASS: rõ, đủ câu, không rè |
| Dừng | PASS: tắt thu |
| Hủy | PASS cho việc tắt thu |
| Escape | PASS cho việc tắt thu |
| Chuyển tab | PASS cho việc tắt thu |
| Mở/reload trang | PASS: microphone không tự thu |
| Từ chối quyền | PASS: hiện lỗi, không thu âm |
| Giới hạn 30 giây | PASS: tự dừng thu theo báo cáo; không có phép đo elapsed time độc lập |

**Đã hoàn tất bộ kiểm tra thu âm/nghe lại vừa yêu cầu:** 8 quan sát bao phủ 7 tình huống (ghi/nghe lại và dừng nằm trong cùng một tình huống). Không còn ba mục bổ sung chờ kết quả, không cần làm lại. Giữ rõ ranh giới: xóa preview/audio, TTL, không tự ghi lại sau hủy/trở về tab và feedback chưa được báo cáo riêng; không gộp những thuộc tính đó vào PASS thu âm hoặc tự chốt toàn bộ nghiệm thu D89/sản phẩm.

Ngày nhận báo cáo là 2026-11-03; ngày test cụ thể, bản Brave, hệ điều hành và model/cổng kết nối microphone chưa được cung cấp. Không suy ra chúng từ môi trường server. Không nhận hoặc yêu cầu file ghi âm. [Receipt đối chiếu mới](evidence/d74-owner-physical-mic-completion-20261103-verification.json); [receipt đầu](evidence/d74-owner-physical-mic-20261103-verification.json) giữ nguyên trạng thái ở thời điểm chưa có follow-up.

## Mở recorder khi muốn kiểm tra

Trên máy chạy repository, từ `ai/`, chạy surface local đã có:

```sh
uv run --no-sync uvicorn apps.voice.main:app --host 127.0.0.1 --port 8091 --no-proxy-headers
```

Mở `http://127.0.0.1:8091` trong Chrome/Firefox trên **máy có microphone của bạn**. Nếu server ở máy khác, dùng SSH local port forwarding đã cấu hình; microphone là thiết bị của trình duyệt, không phải server. Nếu port đã được sử dụng, kiểm tra process trước; không dừng dịch vụ khác để lấy port.

Recorder chỉ tạo bản nghe trong bộ nhớ trình duyệt, không có upload/ASR/TTS. Chỉ bấm “Bắt đầu ghi” và cấp quyền khi bạn muốn thu âm. Có thể dùng câu trung tính, không cần gửi nội dung hoặc file ghi âm vào chat.

## Các thao tác và kết quả cần quan sát

| Kiểm tra | Thao tác | Kết quả cần quan sát |
|---|---|---|
| Không tự thu | Mở hoặc reload trang | Không có microphone đang capture trước khi bấm bắt đầu |
| Ghi và dừng | Bấm bắt đầu, cấp quyền, nói một câu, bấm “Dừng và nghe lại” | Capture dừng; bản nghe có đúng tiếng nói của bạn, không feedback lặp liên tục |
| Hủy | Bắt đầu lượt mới rồi bấm “Hủy / xóa audio” | Capture dừng, preview bị bỏ; không tự bắt đầu lại |
| Escape | Trong lượt ghi mới, nhấn Escape | Capture dừng và audio bị hủy |
| Chuyển tab | Trong lượt ghi mới, chuyển sang tab khác | Capture dừng; trở lại không tự ghi tiếp |
| Từ chối quyền | Khi kiểm tra trường hợp này, từ chối quyền microphone | Thông báo lỗi hữu hạn; không capture hoặc tự retry |
| Giới hạn thời gian | Bắt đầu lượt mới và để quá 30 giây | Capture kết thúc trong giới hạn; không tự bắt đầu lượt kế |

Biểu tượng “đã cấp quyền” có thể vẫn còn khi capture đã dừng; phân biệt với chỉ báo đang sử dụng microphone. Nếu browser/OS không cho kiểm tra một tình huống, ghi chưa kiểm tra và lý do; không đánh dấu PASS. Có thể chia nhiều buổi.

## Gửi kết quả

Chỉ cần gửi trong chat: browser/version, hệ điều hành, loại microphone, ngày kiểm tra, từng thao tác đã làm và kết quả/lỗi. Không cần key, JSON hoặc upload audio. Chưa làm mục nào thì ghi rõ mục đó.

Khi kiểm tra xong, dừng đúng process recorder bạn vừa mở bằng Ctrl+C. Hoàn tất recorder/device không tự chốt ASR/VAD/TTS, giấy phép, endpoint sản phẩm hoặc release. [Bảng quyết định D74](D74_VOICE_DECISION_BRIEF.md) giữ riêng các điều kiện đó.
