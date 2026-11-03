# D74 — Bảng quyết định voice để chủ dự án duyệt

**Mục đích:** Đối chiếu chất lượng nghe, độ trễ, RAM và quyền sử dụng của đúng các ứng viên đã đánh giá; đề xuất bước tiếp theo trước khi chọn giọng/model cho sản phẩm.

**Ngày:** 2026-11-03, Asia/Ho_Chi_Minh. **Trạng thái:** PROPOSAL READY / OWNER DECISION PENDING. VOICE-TTS-DECISION-001 hoàn tất phần chuẩn bị hồ sơ; lựa chọn và kích hoạt chưa được duyệt. D70 đã hoàn tất phép so sánh offline với nhận xét 24/24. D74 sản phẩm vẫn OPEN; D60 tiếp tục chờ theo yêu cầu chủ dự án.

## Kết luận đề xuất

**Giữ trạng thái chưa kích hoạt voice.** Với tiếng Anh, giữ Qwen Ryan làm ứng viên ưu tiên xem xét tiếp về chất lượng trong tập đã nghe, đồng thời giải quyết giới hạn độ trễ CPU trước khi chọn. Với tiếng Việt, chưa có cấu hình TTS đã nghe nào đáp ứng yêu cầu hiện tại: Qwen VI-Auto lỗi nặng; Piper VI đọc đúng nhưng chất giọng không được chủ dự án chấp nhận. Nhận định ưu tiên EN là suy luận từ nhận xét của một người trên corpus nhỏ, chưa phải phê duyệt hoặc kết luận model tốt nhất nói chung.

Đề xuất này không chọn model thay chủ dự án. Không có model/voice mới, tuning, download, inference, chuyển GPU hoặc thay cấu hình trong tác vụ chuẩn bị hồ sơ.

## 1. Chất lượng, RAM và tốc độ TTS đã đo

| Cấu hình đã thử | Nhận xét nghe của chủ dự án | Đỉnh RSS RAM worker D70 | RTF D70 | Đề xuất xử lý |
|---|---|---:|---:|---|
| Qwen3-TTS-0.6B CustomVoice / Ryan / EN | Phát âm đúng 6/6; tự nhiên, nhưng kéo dài Hello, hơi chậm và một mẫu ngữ điệu chưa phù hợp | 5.529 GiB | 4.566 | Giữ ứng viên EN; chưa duyệt độ trễ hoặc sửa nhịp bằng phỏng đoán |
| Cùng Qwen / Ryan / VI-Auto diagnostic | 5 mẫu sai phát âm/dấu/ngữ điệu; mẫu 03 người nghe nhận xét thành tiếng Trung | Cùng worker 5.529 GiB, không đo riêng VI | Chung EN + VI-Auto, không phải RTF riêng VI | Không đưa VI-Auto thành cấu hình sản phẩm từ kết quả này |
| Piper / en_US-ljspeech-medium / EN | 5/6 được nhận xét đọc đúng; sai notebook, có giọng ngang/hạ tông bất thường | 241.883 MiB | 0.03252 | Giữ ứng viên so sánh tốc độ; các lỗi chất lượng vẫn cần xử lý trước quyết định |
| Piper / vi_VN-vais1000-medium / VI | Đọc đúng, nhấn nhá tốt theo nhận xét nhóm 6 mẫu; chủ dự án không thích tông và thấy không tự nhiên | 225.074 MiB | 0.03209 | Voice hiện tại chưa đáp ứng sở thích; không tự đổi voice hoặc coi đọc đúng là nghiệm thu |

Nguồn: [nhận xét nghe](D70_OWNER_LISTENING_20261103.md), [số đo máy D70](D70_OFFLINE_TTS_COMPARISON.md), [receipt gốc](evidence/d70-tts-readonly-measurement-audit.json). RTF là thời gian tổng hợp chia thời lượng audio: nhỏ hơn 1 nghĩa là tổng hợp nhanh hơn thời lượng phát trong lượt đo. Đây là CPU float32/eager của Qwen và CPU ONNX của Piper; RSS là đỉnh RAM toàn tiến trình, không phải VRAM hoặc RAM tối thiểu của model. Qwen chung một worker EN/VI-Auto; không tách giả số RAM hay RTF theo ngôn ngữ. Cache có thể ấm; số đo này không chứng nhận tải nguội, streaming hoặc SLO.

### Giới hạn quan trọng khi đề xuất sửa Qwen EN

SDK **qwen-tts 0.1.1 đang giữ** đặt `instruct=None` cho `tts_model_size="0b6"`; config checkpoint này đúng là `0b6`. Vì vậy không thể coi việc thêm câu “đọc tự nhiên/nhanh hơn” vào `instruct` là phương án đã hoạt động trên cấu hình hiện tại. Đã đối chiếu tĩnh config và AST của SDK, không import hoặc chạy model. Model card có mô tả điều khiển style rộng hơn, nhưng không thay thế hành vi của đúng SDK đã thử. [Evidence và hash SDK/config](evidence/d74-voice-decision-20261103.json).

Không sửa SDK để ép instruction, đổi lên model lớn hơn, kéo tốc độ waveform hoặc điều chỉnh sampling nhằm che lỗi. Nếu chủ dự án muốn nghiên cứu sửa nhịp/tốc độ, cần một protocol riêng với corpus mới, cấu hình được khai báo, đầu ra gốc và đánh giá nghe tương ứng; chưa có benchmark chứng minh phương án nào cải thiện các lỗi vừa nêu.

## 2. Độ trễ luồng thoại đã đo ở D72

| ASR | TTS / ngôn ngữ | Đủ audio trả lời sau | RAM ASR / RAM TTS (GiB) |
|---|---|---:|---:|
| Qwen3-ASR-0.6B | Qwen Ryan EN | 45.937 s | 5.6359 / 5.5269 |
| Qwen3-ASR-0.6B | Piper EN | 11.359 s | 5.6359 / 0.2187 |
| Qwen3-ASR-0.6B | Piper VI | 13.980 s | 5.6361 / 0.2224 |
| Whisper small CT2 | Qwen Ryan EN | 49.315 s | 0.8563 / 5.5278 |
| Whisper small CT2 | Piper EN | 7.775 s | 0.8563 / 0.2544 |
| Whisper small CT2 | Piper VI | 7.849 s | 0.8564 / 0.2178 |

[Sáu ví dụ native](D72_BUFFERED_VOICE_COMPOSITION.md), [số đo gốc có stage/RSS](evidence/d74-local-engineering-review.json). Mỗi hàng chỉ là một ví dụ wiring, gồm nạp worker, ASR → CORE → TTS và chuyển đổi PCM; không phải median/p95 hoặc thời gian câu đầu bắt đầu phát. ASR/TTS chạy tuần tự, không cộng hai RSS thành peak đồng thời. Qwen D70 và D72 khác workload, không tráo số RAM giữa hai phép đo. CORE trong phép đo lịch sử giữ allocation VRAM riêng 9386 MiB; không suy ra VRAM trống hiện tại hay khả năng chuyển TTS lên GPU.

**Chưa có ngân sách độ trễ sản phẩm do chủ dự án chốt.** Các số 46–49 giây của Qwen là đánh đổi cần duyệt rõ, chưa được coi là đáp ứng hội thoại tương tác. Không lấy quảng cáo latency của upstream thay cho số đo tại máy này. Nếu cần khảo sát GPU/streaming/persistent worker, phải có ADR và benchmark tài nguyên/cancel/concurrency riêng; chưa triển khai phương án đó.

## 3. Giấy phép và provenance

| Lớp cần đối chiếu | Bằng chứng hiện có | Trạng thái quyết định |
|---|---|---|
| Qwen checkpoint | Model card revision đã pin khai báo Apache-2.0; danh sách 10 ngôn ngữ không có VI | Metadata đã đối chiếu; không biến thành hỗ trợ VI hoặc phê duyệt mọi dependency/đường triển khai |
| Piper runtime 1.8.0 | Metadata gói chính thức ghi GPL-3.0-or-later; runtime đánh giá được curate nguyên byte, không phải cài toàn bộ wheel | Cần xem nghĩa vụ của đúng cách tích hợp/phân phối trước kích hoạt; chưa cấp phép sản phẩm trong task này |
| Piper EN voice/data | Card đã giữ: LJSpeech, public-domain source dataset; voice repository khai báo MIT | Tách runtime/weights/data; chưa có quyết định tích hợp/phân phối |
| Piper VI voice/data | Card đã giữ: VAIS1000, CC-BY-4.0, fine-tuned từ Lessac | Chuỗi nguồn vẫn cần giải quyết trước activation; MIT repository và CC-BY của VAIS không tự giải quyết Lessac |
| Lessac nguồn upstream | Trang CSTR truy cập được ở follow-up cũ và kiểm tra ngày 2026-11-03; có grant cho nghiên cứu, không cấp quyền thương mại cho dataset qua grant đó | Đây là dataset license; **chưa kết luận quyền của weights hoặc generated output**. Không ký form, nhận grant hay tải dataset |

Nguồn chính đã kiểm tra lại: [Qwen model card đúng revision](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice/blob/85e237c12c027371202489a0ec509ded67b5e4b5/README.md), [Piper 1.8.0 metadata](https://pypi.org/pypi/piper-tts/1.8.0/json), [Lessac dataset license](https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html). Bốn lần mở Piper card qua blob/resolve bằng web tool không truy cập được; dùng hai card nguyên byte đã giữ, đối chiếu hash. Đường GitHub `LICENSE.md` trả 404, không dùng làm bằng chứng license; metadata chính thức và bản runtime đã giữ là nguồn của phiên bản 1.8.0. [Follow-up Lessac cũ](evidence/d70-piper-lessac-license-followup.json), [kiểm tra nguồn mới](evidence/d74-voice-primary-sources-20261103.json).

## 4. ASR/VAD và microphone còn cần nghiệm thu

[D72 trên 20 câu độc lập mỗi ngôn ngữ](D72_VAD_ASR_COMPARISON.md): Qwen ASR ungated WER VI 7.614%, EN 5.652%; Whisper VI 20.474%, EN 6.087%. Trên 5 negative, Qwen sinh text 4/5 và Whisper 5/5 khi không gate. Gating loại được cả 5 nhưng làm giảm chất lượng nhiều nhóm speech, đặc biệt EN; chưa chứng nhận giữ từ ngắn/nhỏ tiếng. Giữ VAD concatenation chưa kích hoạt và ASR chưa chọn default. Không biến một tập nhỏ thành xác suất hallucination chung hoặc tự đặt ngưỡng VAD sản phẩm.

Nghe TTS bằng loa không chứng minh luồng thoại sản phẩm đã đạt. Chủ dự án nay đã báo cáo [microphone thật cơ bản PASS](D74_PHYSICAL_MIC_CHECK.md) trên Brave/PC: bản nghe rõ/đủ câu/không rè, Dừng/Hủy/Escape/chuyển tab tắt thu. Ba tình huống mở trang/từ chối quyền/giới hạn 30 giây nay đều được xác nhận PASS; bộ smoke thu âm/nghe lại đã hoàn tất. Các chi tiết xóa/TTL/không tự ghi lại chưa nêu giữ chưa xác nhận riêng. Đây là recorder local, không có kết quả gọi model hoặc upload audio. Luồng recorder → ASR → CORE → TTS với người dùng thật phải chờ model/voice, endpoint/auth/retention và giới hạn đã được duyệt; sáu ví dụ CLI D72 chưa phải endpoint sản phẩm. Không hứa chạy E2E người dùng trên giao diện recorder hiện chưa có upload.

## 5. Các phương án để duyệt và điều kiện chuyển bước

| Phương án | Ưu/nhược điểm đã có bằng chứng | Dependency, effort và rủi ro | Trạng thái |
|---|---|---|---|
| A. Giữ voice chưa kích hoạt, hoàn thiện recorder/device và hồ sơ sản phẩm | Bảo toàn lựa chọn; phần engineering độc lập có thể tiếp tục. Chưa có voice sản phẩm để sử dụng | Microphone/browser thật và quyết định scope; một milestone nghiệm thu thiết bị; không được ghi fake-device thành test người dùng | **Khuyến nghị hiện tại**, không thay cấu hình |
| B. Xét riêng Qwen Ryan cho EN với model/weights hiện có | Nhận xét EN tốt nhất trong tập chủ dự án vừa nghe; CPU buffered hiện 46–49 s, style instruction bị bỏ qua ở SDK đã giữ | Chủ dự án chốt độ trễ/chất lượng mong muốn và protocol mới trước mọi tuning/chuyển runtime; effort một thiết kế/đo/nghe milestone, chưa ước lượng thời gian chạy khi protocol chưa có | Ứng viên cân nhắc; **chưa chọn hoặc xếp lịch chạy** |
| C. Giải quyết VI voice bằng đề xuất riêng | VI-Auto không đáp ứng; Piper VI voice hiện tại không hợp sở thích | Yêu cầu chất giọng và proposal đã có benchmark/rights/resource/migration/rollback; effort thiết kế đánh giá trước, effort model mới chưa biết; rủi ro đổi tone vẫn không giải quyết phát âm hoặc rights | **Chưa đề cử model/voice mới**, cần chủ dự án duyệt phạm vi trước triển khai |

Muốn chọn phương án B cần nêu rõ: chỉ EN hay VI cũng bắt buộc; độ trễ chấp nhận được; yêu cầu giọng/intonation. Nếu VI bắt buộc và phải tự nhiên theo sở thích hiện tại, bằng chứng đang có chưa đủ để chốt TTS. Việc hoàn thành bảng này không được dùng làm approval thay model, mở endpoint hoặc đóng D74.

## 6. Migration, rollback và kiểm chứng

Tác vụ này chỉ thêm tài liệu/evidence và liên kết trạng thái: **không migration, không đổi default/model/config/API/database/Vault/Docker, không bật recorder hay chạm microphone**. ADR-111/112/113 vẫn là ranh giới hiện tại; không có thay đổi kiến trúc cần một ADR quyết định mới ở bước lập bảng.

Trước một tích hợp được duyệt sau này, phải pin model/voice/runtime, giữ config trước thay đổi, kiểm tra đúng ngôn ngữ/sample clock/owner/auth/budget/stop/cancel và output hoàn chỉnh. Rollback phải ngừng admission mới, dừng/join công việc đang sở hữu, hủy kết quả muộn, phục hồi đúng config trước đó và giữ bằng chứng/audio gốc. Chi tiết ADR, benchmark và rollback phải đi cùng phương án cụ thể, không coi phần khung này là đủ để triển khai.

[Evidence số liệu và hash đầu vào](evidence/d74-voice-decision-20261103.json), [receipt kiểm chứng tài liệu](evidence/d74-voice-decision-20261103-verification.json). Application/config/test 750 file giữ nguyên; full 5889 PASS là kết quả trước đó cho snapshot này, không chạy lại trong nhiệm vụ tài liệu. Các số đo runtime/CORE và audit dịch vụ ở bảng là lịch sử đã ghi, không tuyên bố đo lại hiện trạng server.
