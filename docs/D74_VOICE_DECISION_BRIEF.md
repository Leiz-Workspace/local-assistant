# D74 — Bảng quyết định voice để chủ dự án duyệt

**Mục đích:** Đối chiếu chất lượng nghe, độ trễ, RAM và quyền sử dụng của đúng các ứng viên đã đánh giá; đề xuất bước tiếp theo trước khi chọn giọng/model cho sản phẩm.

**Ngày:** 2026-11-03, Asia/Ho_Chi_Minh. **Trạng thái:** REQUIREMENTS RECORDED / PROTOCOL APPROVED / TTS STANDALONE COMPLETE / WORKFLOW RECOVERY PENDING; MODEL/PHYSICAL PERFORMANCE OPEN; OWNER TARGET 4 SECONDS. VOICE-TTS-DECISION-001 hoàn tất phần chuẩn bị hồ sơ; lựa chọn và kích hoạt chưa được duyệt. D70 đã hoàn tất phép so sánh offline với nhận xét 24/24. D74 sản phẩm vẫn OPEN; D60 tiếp tục chờ theo yêu cầu chủ dự án.

## Yêu cầu chủ dự án đã chốt

[Voice product requirements](VOICE_PRODUCT_REQUIREMENTS.md), 2026-11-03: mục tiêu có VI và EN, hiện ưu tiên **VI / nữ miền Bắc**. Tiếng Anh giữ trong mục tiêu, chưa tự xếp một release; ngôn ngữ tùy biến **PENDING bản sau**. Chủ dự án đã chọn **tối đa 4 giây từ gửi câu hỏi tới bắt đầu nghe lời trả lời**. Hiệu năng chưa được kiểm chứng; không đổi runtime timeout. Đây là yêu cầu sản phẩm, không chọn hoặc duyệt thay model.

## Khảo sát ứng viên và trial đề xuất

[ADR-154](ADR/154-proposed-isolated-vietnamese-voice-feasibility-campaign.md) đã được chủ dự án duyệt. Đã tải đúng16 artifact608.816.450byte, chạy2 qualification và24 clip TTS. [Báo cáo](D74_VI_VOICE_CAMPAIGN_RESULT.md) giữ6 workflow slot lỗi bộ đọc metadata CORE và42 chưa chạy; không có latency workflow hợp lệ. Bản sửa161 tests PASS, chưa chạy native lại. [ADR-155](ADR/155-proposed-workflow-recovery-after-caller-metadata-failure.md) đề nghị một lượt workflow thay thế có phê duyệt mới; không lặp24clip/tải model. Sau lựa chọn chờ nghe, chủ dự án đã gửi [phản hồi nhóm](D74_OWNER_VOICE_FEEDBACK_20261103.md): cả ba giọng đều ổn, thích Trúc Ly và Ngọc Huyền hơn nhưng ngữ điệu máy móc, giờ/ngày và Python/API chưa đọc đúng. ADR-155 chưa được duyệt/chưa chạy; chưa chọn giữa hai giọng hoặc chấp nhận chất lượng sản phẩm. Target4giây vật lý, model/default và activation vẫn mở.

## Kết luận đề xuất

**Giữ trạng thái chưa kích hoạt voice. Ưu tiên điều tra ngữ điệu và cách đọc giờ/ngày/Python/API của các ứng viên đã có; Trúc Ly và Ngọc Huyền được chủ dự án thích hơn, chưa được chọn hoặc nghiệm thu.** Tiếng Anh vẫn trong mục tiêu; Qwen Ryan chỉ là ứng viên EN đáng xem xét về chất lượng trong tập đã nghe, không phải ưu tiên triển khai trước VI hoặc lựa chọn đã duyệt. Với tiếng Việt, chưa có cấu hình TTS đã nghe nào đáp ứng yêu cầu hiện tại: Qwen VI-Auto lỗi nặng; Piper VI đọc đúng nhưng chất giọng không được chủ dự án chấp nhận. Nhận định về ứng viên EN là suy luận từ nhận xét của một người trên corpus nhỏ, không chứng minh đáp ứng giọng nữ miền Bắc cho VI hoặc model tốt nhất nói chung.

Đề xuất này không chọn model thay chủ dự án. Tác vụ chuẩn bị hồ sơ ban đầu không chạy model. Trial mới chỉ theo phê duyệt ADR-154; không đổi model/default sản phẩm, chuyển GPU hoặc cấu hình dùng chung.

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

**Chủ dự án chốt tối đa 4 giây từ submission tới first-audible answer.** [AC và ranh giới đo](VOICE_PRODUCT_REQUIREMENTS.md) tính ASR→tạo trả lời→TTS→phát tại thiết bị; không lấy beep/PCM/token đầu làm kết quả. Chưa có phép đo first-audible chứng minh đạt, không đổi thành trung bình/p95 hoặc tự cắt câu trả lời sau 4 giây. Các số 46–49 giây của Qwen là đánh đổi cần duyệt rõ, chưa được coi là đáp ứng hội thoại tương tác. Không lấy quảng cáo latency của upstream thay cho số đo tại máy này. Nếu cần khảo sát GPU/streaming/persistent worker, phải có ADR và benchmark tài nguyên/cancel/concurrency riêng; chưa triển khai phương án đó.

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
| B. Xét riêng Qwen Ryan cho EN với model/weights hiện có | Nhận xét EN tốt nhất trong tập chủ dự án vừa nghe; CPU buffered hiện 46–49 s, style instruction bị bỏ qua ở SDK đã giữ | Target4giây đã chốt; cần protocol/chất lượng và approval cụ thể trước mọi tuning/chuyển runtime; effort một thiết kế/đo/nghe milestone, chưa ước lượng thời gian chạy khi protocol chưa có | Ứng viên cân nhắc; **chưa chọn hoặc xếp lịch chạy** |
| C. Đối chiếu VI nữ miền Bắc bằng đề xuất riêng, ưu tiên hiện tại | VI-Auto không đáp ứng; Piper VI voice hiện tại không hợp sở thích | Yêu cầu VI/nữ miền Bắc đã ghi; cần proposal có benchmark/rights/resource/migration/rollback; effort thiết kế đánh giá trước, effort model mới chưa biết; rủi ro đổi tone vẫn không giải quyết phát âm hoặc rights | **Chưa đề cử model/voice mới**, cần chủ dự án duyệt phạm vi trước triển khai |

VI hiện là ưu tiên, nữ miền Bắc đã được yêu cầu; không hỏi lại EN/VI như một lựa chọn còn trống. Tiếng Anh giữ trong mục tiêu. Thời gian chờ tối đa4giây đã chốt, protocol/benchmark còn pending; bằng chứng đang có chưa đủ để chọn TTS thỏa toàn bộ yêu cầu VI/giọng/tự nhiên. Ngôn ngữ tùy biến chỉ là backlog bản sau, chưa có trial/model được duyệt. Việc hoàn thành bảng này không được dùng làm approval thay model, mở endpoint hoặc đóng D74.

## 6. Migration, rollback và kiểm chứng

Tác vụ này chỉ thêm tài liệu/evidence và liên kết trạng thái: **không migration, không đổi default/model/config/API/database/Vault/Docker, không bật recorder hay chạm microphone**. ADR-111/112/113 vẫn là ranh giới hiện tại; không có thay đổi kiến trúc cần một ADR quyết định mới ở bước lập bảng.

Trước một tích hợp được duyệt sau này, phải pin model/voice/runtime, giữ config trước thay đổi, kiểm tra đúng ngôn ngữ/sample clock/owner/auth/budget/stop/cancel và output hoàn chỉnh. Rollback phải ngừng admission mới, dừng/join công việc đang sở hữu, hủy kết quả muộn, phục hồi đúng config trước đó và giữ bằng chứng/audio gốc. Chi tiết ADR, benchmark và rollback phải đi cùng phương án cụ thể, không coi phần khung này là đủ để triển khai.

[Evidence số liệu và hash đầu vào](evidence/d74-voice-decision-20261103.json), [receipt kiểm chứng tài liệu](evidence/d74-voice-decision-20261103-verification.json). Application/config/test 750 file giữ nguyên; full 5889 PASS là kết quả trước đó cho snapshot này, không chạy lại trong nhiệm vụ tài liệu. Các số đo runtime/CORE và audit dịch vụ ở bảng là lịch sử đã ghi, không tuyên bố đo lại hiện trạng server.


## Bản sửa nghiên cứu và panel mới theo yêu cầu chủ dự án

[ADR156 thực tế](D74_SPEECH_READING_QUALITY_RESULT.md): đã có renderer speech riêng và adapter giữ câu hỏi qua phoneme API của model hiện có;221scoped PASS/48clip mới/54chunk native/0retry.12/16cặp đối chứng–sửa cách đọc giống hệt, nên không coi lỗi đọc giờ/ngày đã khắc phục; Python/API dùng phiên âm Việt thử nghiệm, cần nghe so sánh. Ngữ điệu tự nhiên vẫn cần chủ dự án xác nhận. Không chọn voice/model, không sửa sản phẩm/weights/SDK, không chạy ADR155workflow.


## English/API follow-up sau nhận xét mới

[Chủ dự án đã xác nhận](D74_ENGLISH_READING_FOLLOWUP.md) date/time chuẩn và thích `clauses` nhất; giữ phần đó. Python đọc chưa đúng tiếng Anh và API rè/run ở cảhai giọng vẫn là quality blocker. Bản input-only mới bỏ phiên âm Việt,236scoped PASS/8clip mới chờ nghe;17file nghiên cứu đã có nguyên hash. Không chọn giữahai giọng hoặc kích hoạt sản phẩm/workflow recovery.


## API reference diagnostic — 2026-11-04

[Actual result and eight paired listening clips](D74_API_REFERENCE_DIAGNOSTIC_RESULT.md): first16-slot diagnostic remains stopped at Ngọc Huyền isolated-A13frames/EOSfalse (4complete/1failed/11unattempted); no retry or raised cap. A separately declared8-slot full-carrier cohort completes all4exact phoneme/token/speaker/anchor pairs with reference-code on/off; combined13actualTTS≤16, not original16PASS. Final257scoped software PASS/0FAIL/ERROR/SKIP4.29s, RuffPASS;250initialPASS. Exact token roundtrip/zero unknowns do not establish acoustic Ei or absence of APIbuzz.

VOICE-ENGLISH-READING-001/VOICE-API-ARTIFACT-001 remain P1. Subsequent owner feedback reports the new set worse; diagnostic quality NOT ACCEPTED (see current disposition below). No automatic reference-off/model/voice/default selection; weights/SDK/presets unchanged. Python not re-evaluated; reviewed date/time and preferred `clauses` retained. All750application/210protected/19prior research files and prior audio unchanged. No new downloads, ASR/CORE/Brave calls, shared service changes or ADR155workflow execution. Physical4second/rights/no-speech/product/D90release remain open; D60owner-deferred. Full5889/earlier236scoped counts remain historical, not new full runs.


**Current owner disposition, 2026-11-04:** [Exact feedback](evidence/d74-api-reference-owner-rejection.json): “Còn tệ hơn cả bản trước nữa”. Reject adoption of this diagnostic and preserve the earlier `clauses` path/date/time acceptance. No separate clip, ref-on/off or Ei/buzz/timbre ratings are inferred. API quality remains open; Python not reassessed. Different texts/direct-phoneme preparation prevent causal attribution of the old-to-new regression. Next engineering step is a source-backed minimal same-text/same-voice comparison design on the retained clauses path; no new native trial scheduled or remaining slots consumed.257scoped PASS is historical software evidence only. No model/default/workflow activation or new source/config/model/provider calls.


## Same-text API stress follow-up — 2026-11-04

[ADR159 actual result and four same-text pairs](D74_API_STRESS_COMPARISON_RESULT.md): latest owner “Làm đi” continues narrowly on the old english-01/04 sentences and both retained voices.4newTTS/6innerchunks complete/EOS/exit0/no retry; four exact ADR157baselines reused. Only API stress marks change at the old ProsodyAdapter phonemizer dependency, preserving text/date/clauses/question/Pythoninput/referenceON/sampling/frame caps. Two first date chunks match old audio byte-for-byte.267scoped software PASS4.78s/RuffPASS; two initial test-fixture failures retained.

Ei/APIbuzz/whole-sentence naturalness remain unaccepted pending owner listening; unchanged Python phones do not certify its waveform. The rejected carrier trial remains OWNER_REPORTED_WORSE_NOT_ACCEPTED; no ref-off or model/voice/default/policy adoption.25prior research/750application/210protected/SDK/model/audio preserved, no ASR/CORE/provider/download/service change. ADR155workflow unapproved/unexecuted; physical4second/rights/no-speech/product/D90release open, D60owner-deferred;5889full remains historical.


## API owner acceptance and Roman context check — 2026-11-04

[Exact owner feedback](evidence/d74-api-python-roman-owner-feedback.json) confirms API pronunciation correct on the reviewed ADR159panel; Python remains unacceptable. Preserve that API operator/audio. No per-clip or separate APIbuzz/timbre acceptance, voice/model/default/product approval is inferred.

[Roman/Python context result](D74_ROMAN_CONTEXT_RESULT.md): original SDK verifies5of5fixed unambiguous targets, preserving vi in vi phạm/VI PHẠM and reading Chương VI as sáu, including both meanings in one sentence; IV/IX frontend-only. Identifier VI is observation-only. Bare/tagged Python phones identical, not a fix.8Roman-word+2EnglishPython native controls complete10TTS/10chunks/EOS/exit0/no retry;2oldmixed references unchanged, new acoustic listening pending.275scoped software PASS5.03s/RuffPASS. No normalization/pronunciation rule or model/SDK/acceptedAPI change;29oldresearch/750application/210protected and previous audio preserved. VOICE-CONTEXT-READING-001 P1 frontend corpus complete, acoustic gate open; Python P1 remains open. ADR155workflow/physical4second/rights/no-speech/product/D90release unaccepted; D60deferred.


## XI context and same-voice American English — 2026-11-04

[Owner feedback](evidence/d74-vi-xi-bilingual-owner-feedback.json) accepts reviewed VI/vi, reports Vietnamese-accented English not acceptable, and asks XI/xi măng. [Explicit preference](evidence/d74-owner-en-us-preference.json): en-US, retaining the same voice identity. API pronunciation/date/prosody accepted-scope preserved; no per-clip labels, new voice/model or deployment approval.

[XI and bilingual result](D74_XI_BILINGUAL_RESULT.md): existing frontend5of5fixed targets correct, including XI MĂNG and mixed Roman/word usage;6nativeXIcontrols/6chunks complete/EOS/exit0/no retry, listening pending.282scoped software PASS5.25s/RuffPASS.31oldresearch/750application/210protected/SDK/model/audio preserved, no reading-rule/source-policy change or ASR/CORE/Brave/new model/reference/training.

P1VOICE-BILINGUAL-IDENTITY-001 assessed, not executed: same-identity VI/EN-US pronunciation/accent/voice-similarity rubric, source-backed PythonUS frontend comparison as next design step; broader bilingual reference/adaptation proposals need data/rights/resource/migration/rollback review and explicit owner approval. Existing bilingual support is not acoustic acceptance; pinned infer has no accent/language parameter and ignores style. No guaranteed preset accent fix established. D60deferred/ADR155workflowunapproved; physical4second/rights/no-speech/model/voice/product/D90release open.


## Same-voice US term comparison — 2026-11-04

[ADR160 actual result and paired listening pages](D74_US_TERMS_COMPARISON_RESULT.md): owner explicitly continues PythonUS plus other words. Six exact sentences/two retained voices; change only Python US vowel, GitHub whole-word dictionary form and server rhotic hypothesis. Docker/browser/database input phones unchanged, accepted API function and clause path retained. Shared min(original) frame budgets never increased; GitHub fresh baseline allowance conservatively reduced140→136.

16newTTS/16chunks/EOS/exit0/no retry +4oldPythonbaselines +4sharedunchangedcontrols =24logicalobservations/12pairs,20actualplayers split into two voice pages. Eight changed pairs differ in waveform; no acoustic PASS inferred. Four fresh GitHub/server pairs match measuredspeaker/reference hashes; oldPython provenance bound to retained source/audio without retrospective measurements.295scoped software PASS5.31s/RuffPASS;4newsource/test,33oldresearch/750application/210protected/SDK/model/audio preserved,baseline restored. No model/reference/training/app/config/ASR/CORE/Brave changes.

VOICE-ENGLISH-READING-001/VOICE-BILINGUAL-IDENTITY-001 now have a real paired word panel; en-US pronunciation/accent, perceived voice similarity, naturalness and API inside new mixed audio await listening. Accepted prior API/VI/date/clauses remain scoped, XI review pending. No model/voice/default/policy adoption; D60deferred/ADR155workflowunapproved, physical4second/rights/no-speech/product/D90releaseopen;5889full historical.


## Owner assessment by voice — 2026-11-04

[Exact feedback and retained I traces](evidence/d74-us-terms-owner-voice-assessment.json): Trúc Ly pronunciation accepted as en-US on the reviewed word panel; Ngọc Huyền English not acceptable, with I heard as i. Exact clip/role ratings and full-playback confirmation were not supplied. Both voices' retained baseline/candidate I sentence inputs already beginˈaɪ, so no frontend I→/i/ conversion is demonstrated; a specific model/reference/decoder cause remains unknown.

[Current disposition](D74_US_TERMS_COMPARISON_RESULT.md) prioritizes preserved Trúc Ly for wider same-voice VI/en-US validation. Ngọc Huyền is unqualified for English under this panel; Vietnamese findings remain intact. Broader pronunciation/accent, naturalness, perceived identity and API in new mixed audio remain separate; no per-clip scores, universal quality claim or product voice/model/default selection. Next validation depends on a declared broader corpus and tested bounded protocol; effort one milestone, risk authored-panel overfit/regression, no new native run scheduled. Documentation only/0new inference/source/config/model actions; old panel/source/audio and295softwarePASS retained. ADR155workflow unapproved, D60deferred, XI listening/physical4second/rights/no-speech/product/D90release open.


## Trúc Ly broader-context validation — 2026-11-04

[ADR161 actual result and grouped listening pages](D74_TRUC_LY_VALIDATION_RESULT.md): ten new sentences, only retained Trúc Ly, four EN/three mixed/three VI. All10TTS/12original chunks complete/EOS,0retry,worker exit0/baseline restored. Same API/date/clause/US-term policy and measured speaker/reference binding, no new lexicon/model/reference/training/default.306related software PASS/0FAIL/ERROR/SKIP5.39s;37oldresearch/750application/210protected/4295SDKentries preserved. Prior Trúc Ly en-US panel acceptance and Ngọc Huyền English rejection remain scoped and intact.

VOICE-ENGLISH-READING-001/VOICE-BILINGUAL-IDENTITY-001: broader native corpus complete, acoustic review OPEN. Hear I/ship-sheep/right-light, terms, mixed API, date/amount and VI/XI; score pronunciation/accent separately from naturalness/perceived identity and artifacts. Dependency owner listening, effort one review milestone, risk authored-panel overfit/regression; no further tuning run scheduled. Physical first-audible4seconds remains unverified despite TTS-only0.781–2.214s; prior XI review/rights/no-speech/product/release stay open. ADR155workflow NOT APPROVED/NOT EXECUTED; D60deferred, no product voice/model selection.


## Owner accepts current Trúc Ly quality; refinement stopped — 2026-11-04

[Exact feedback](evidence/d74-truc-validation-owner-acceptance.json) accepts the latest broader Trúc Ly panel as sufficient and asks to stop this refinement cycle. Known English articulation limitation retained: final sounds unclear, “this” heard as “dít”. No perfect-pronunciation claim, per-clip labels, separate naturalness/identity scores or product voice/model selection inferred. [Current report](D74_TRUC_LY_VALIDATION_RESULT.md) supersedes its earlier pending-listening status; old native results remain immutable.

Ngọc Huyền has NOT run this new10-sentence corpus; its earlier US-term panel was tested and owner-rejected, including I→i, which remains historical evidence. New-corpus evaluation PENDING separately: same corpus/policy/model and retained first failures, tested bounded voice-specific runner required because ADR161 is Trúc Ly-only; effort one evaluation milestone, risk articulation/identity/cap failure, no new run or fix claimed.0new inference/code/config/model/download changes or software tests in this feedback update;306scoped/5889full remain historical. ADR155workflow unapproved, D60deferred; physical4second/rights/no-speech/product/D90release remain open.
