# D70 — So sánh TTS ngoại tuyến

**Mục đích:** Ghi lại bằng chứng thực tế của MODEL-EVAL-005, phân biệt khả năng chạy, tiếng Việt được hỗ trợ, chỉ số đo được và tiêu chí đánh giá còn mở. Tài liệu không phê duyệt chọn hoặc triển khai model.

**Trạng thái:** IN PROGRESS. Source chuẩn bị `7ff5438`; D69 vẫn PASS tại `5653de4`. Chưa chuyển sang D71.

## Model, giọng và giấy phép

| Instance | Artifact đã chốt | Vai trò trong phép thử | Giới hạn |
|---|---|---|---|
| Qwen3-TTS-0.6B | `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`, revision `85e237c12c027371202489a0ec509ded67b5e4b5`, codec đi kèm, Ryan | 6 câu EN; 6 kiểm tra ngôn ngữ Vietnamese; 6 diagnostic VI-text/Auto riêng | Danh sách ngôn ngữ chính thức và SDK không có Vietnamese. Auto không chứng minh hỗ trợ chính thức; không clone giọng. Apache-2.0. |
| Piper EN | `rhasspy/piper-voices`, revision `5041a7a49ae5b3a0f30e6837769eb03fdbb231bd`, `en_US-ljspeech-medium` | Cùng 6 câu EN | Model card nêu dữ liệu LJSpeech public domain; repository khai báo MIT; runtime Piper GPL-3.0-or-later là lớp giấy phép khác. |
| Piper VI | Cùng revision Piper, `vi_VN-vais1000-medium` | Cùng 6 câu VI | Model card dẫn CC-BY-4.0 và fine-tuned từ Lessac. Endpoint giấy phép nguồn Lessac không truy cập được trong lượt tra cứu; chưa xác minh độc lập toàn bộ chuỗi quyền cho triển khai/phân phối. |

[ADR-096](ADR/096-offline-registry-tts-comparison.md) và [cấu hình](../configs/tts-evaluation-candidates.json) ghi đủ file/size/Gitblob/LFS pins, ưu tiên/dependency/effort/rủi ro, giới hạn và rollback trước provisioning. Không thay bằng model 1.7B, voice khác, tokenizer khác hoặc model bổ trợ.

SDK uv nằm riêng trong `data/backups/d70-tts-evaluation`: Torch/torchaudio2.10.0+cpu, Transformers4.57.3, qwen-tts0.1.1, NumPy2.3.5, ORT1.31.0. Toàn bộ23475entry SDK/Piper source được đóng băng và kiểm tra lại trước lượt scored. Không sửa app/D68/D69 environment hoặc lockfile.

Wheel Piper1.8.0 chính thức được kiểm tra có hai ONNX phụ Hebrew/Arabic. Bytes của archive đã được tải để kiểm tra; hai member này chưa được extract/install/load.430file Python/native/espeak/license giữ đúng bytes từ archive, không sửa model/phonemizer, không cài full wheel. Sử dụng nhánh espeak EN/VI, `use_tashkeel=False`, không graph patch/alignments. Mọi thông báo SDK giữ trong stderr; stdout chỉ có observation JSON.

## Phép thử đã chốt trước kết quả

12 câu authored, sáu tình huống mỗi ngôn ngữ: chào hỏi, câu hỏi, số bằng chữ, ngày bằng chữ, hướng dẫn và câu dài. Đây là tập nhỏ do tác giả soạn, không phải đánh giá người dùng độc lập. Không đổi câu, giọng, seed, threshold hoặc decoder sau kết quả; mỗi request có một quan sát đầu tiên. Các diagnostic Auto được lập lịch từ trước, không phải retry khi Vietnamese bị từ chối.

Qwen: CPUfloat32/eager, Ryan, seed7/case, sampling chuẩn top_k50/top_p1/temperature0.9/repetition_penalty1.05, subtalker sampling tương ứng, max_new_tokens192, non_streaming_modeTrue, instructNone. Theo dõi nguyên output của inner/outer generate để xác minh EOS và codec frames, không sửa args/tensors. API trả toàn bộ waveform đồng bộ; thời điểm audio có sẵn bằng thời gian hoàn tất call, không phải streaming TTFA.

Piper: một process mới cho mỗi voice, CPU ORT intra2/inter1, speaker0, length1, noise defaults của đúng voice, normalize_audioTrue/volume1. Materialize đầy đủ chunks; first-yield là câu hoàn chỉnh đầu tiên. Chuẩn hóa/clip tiêu chuẩn của engine được ghi rõ; không đồng nhất với raw NN output của Qwen hoặc so sánh chỉ riêng kiến trúc.

Một TTS process mỗi lần; không ASR/full-suite chạy đồng thời. Affinity0,1; namespace không network/host credentials/GPU; model/SDK/source readonly; một output directory riêng0700, files0600/exclusive. Giới hạn12GiB address space/3600CPU/1800wall,128MiB tmpfs,20s audio/file16MiB/tổng64MiB. Các giới hạn không phải RAM tối thiểu hoặc SLO. Đo RSS RAM của worker riêng với VRAM của CORE đang giữ nguyên; không gộp disk weights thành RAM/VRAM.

Các waveform native f32 và IEEEfloat32 WAV được giữ nguyên và parent kiểm tra lại samples/rate/hash/header/timing/EOS. Không cắt silence, chuẩn hóa âm lượng, sửa phát âm hoặc tổng hợp lại native output. [Qualified freeze](evidence/d70-tts-qualified-first-freeze.json) giữ624source/toàn bộ612file cũ nguyên byte, các protected model/config/data/runtime pins và exact D68 MD-only transition.

## Qualification và các lỗi được giữ lại

118 kiểm thử mới nằm trong436 related PASS/10.60s/0FAIL/0SKIP; một warning có chủ ý từ archive duplicate đối kháng. Ruff PASS. Ba smoke độc lập đều exit0/CORE cùng PID-start-command và text recovery PASS: Qwen24k/EOS, Piper EN/VI22050Hz. Đây không phải common-corpus accuracy/naturalness benchmark.

Lượt chuẩn bị diagnostic smoke đầu bị host validator từ chối vì ID `0.6B` chứa dấu chấm ngoài alphabet leafname. Chưa chạy model/DSP trong lượt này; log/folder đầu giữ nguyên. Sửa riêng encoding định danh thành safe leaf, thêm regression; lượt qualified3/3 resample/Opus copies PASS. Không sửa model, corpus hoặc mẫu đã sinh.

## Kết quả common-corpus

Đã hoàn tất các lượt đầu, theo đúng thứ tự Qwen → Piper EN → Piper VI, mỗi process retire/join trước lượt sau.30/30attempts được giữ:24 native waveforms hợp lệ và6explicit-Vietnamese refusals. Không timeout, missing, exhausted EOS hoặc retry. CORE PID37256/start/command/text recovery giữ nguyên trước/sau từng worker.

| Instance | Attempts / native audio | Worker wall | Import / load | Lifetime process peak RSS RAM | Tổng audio / synthesis calls | RTF theo tổng duration |
|---|---|---:|---:|---:|---:|---:|
| Qwen |18;12audio +6unsupported VI |224.784s |5.738s /1.195s |5797248KiB ≈5.529GiB |47.520s /216.959s |4.565644 |
| Piper EN |6/6audio |1.529s |0.129s /0.806s |247688KiB ≈241.883MiB |14.826s /0.482s |0.032516 |
| Piper VI |6/6audio |1.402s |0.126s /0.769s |230476KiB ≈225.074MiB |12.585s /0.404s |0.032086 |

Qwen process CPU438.392s; Piper EN2.055s/VI1.855s. RTF chỉ dùng các successful waveforms/calls;6refusal vẫn có status/timing riêng, không được biến thành speech-success hoặc bình quân để làm đẹp latency. First measured call có thể có lazy initialization; OS/model cache đã được qualification dùng trước, không gọi đây là cold-storage hoặc warm-steady SLO. RSS là lifetime process RSS, không là RAM tối thiểu hoặc unique physical RAM toàn hệ thống. CPU-only là quan sát device/providers và namespace không GPU; các số trên không phải VRAM. CORE vẫn có VRAM riêng.

| Group | Thời gian audio có sẵn min / median / max | Native peak max / số samples tại hoặc vượt full scale |
|---|---:|---:|
| Qwen EN |11.328 /15.417 /22.670s |0.668148 /0 |
| Qwen VI Auto diagnostic |12.646 /15.304 /36.147s |0.710714 /0 |
| Piper EN |0.062538 /0.068829 /0.135946s |1.0 /6 |
| Piper VI |0.050557 /0.059731 /0.109401s |1.0 /6 |

Qwen trả toàn bộ waveform, Piper trả chunk câu đầu; đây là khác biệt API/voice/engine/decoder, không phải model-only TTFA đối chứng. Piper chạm1 ở mỗi output do normalizer tiêu chuẩn được bật; không suy luận những sample này tự chứng minh méo tiếng. Qwen và Piper đều giữ native float32 không hậu xử lý.

## ASR roundtrip và đánh giá tự nhiên

Diagnostic riêng dùng cùng `scipy.signal.resample_poly` về16k. Nếu filter ringing làm peak vượt1, chỉ input ASR riêng được nhân reciprocal peak và ghi factor/hash/count; native không đổi. Replay một lần bằng Qwen3-ASR0.6B/D68 SDK/source đã đóng băng, language hint cố định, không reference text trong ASR namespace, sau khi mọi TTS process đã retire. Normalization/edit distance giữ nguyên primitive D68, nhưng ghi đúng đây là authored TTS text, không relabel thành independent public speech. Waveform không đạt contract1–20s của D68 phải báo ineligible, không padding/cắt để che điều kiện.

24/24waveform đã transform và replay một lần, exit0/50.492s; không ineligible/cap/missing/retry. Mọi native hash giữ nguyên.

| Group | Số câu / reference words | ASR proxy WER | ASR proxy CER |
|---|---:|---:|---:|
| Qwen EN explicit |6/48 |0/48 =0% |0/216 =0% |
| Qwen VI Auto diagnostic |6/59 |35/59 =59.322% |80/194 =41.237% |
| Piper EN explicit |6/48 |0/48 =0% |0/216 =0% |
| Piper VI explicit |6/59 |3/59 =5.085% |5/194 =2.577% |

Đây là lỗi transcript của proxy trên audio đã sinh, chưa có nghe đối chiếu để quy nguyên nhân hoàn toàn cho TTS hoặc ASR. Một câu Qwen VI Auto có25word-edits/8reference words; giữ nguyên trường hợp WER trên100%, không clip điểm hoặc retry câu đó.0% ở48từ EN của tập nhỏ không chứng minh phát âm/chất lượng hoàn hảo hay khả năng generalize.

ASR roundtrip có thể thiên về họ Qwen liên quan. WER/CER và peak/RMS/silence không đo được tự nhiên/MOS. Có thể tạo bản nghe Ogg Opus24k riêng, RMS target0.10/peak headroom0.95 và toàn bộ timeline, ghi gain/hash/codec; đây là bản nghe lossy, không thay native output.

**Tiêu chí nghe thực tế đang mở.** Khi gửi bản nghe smoke thật qua công cụ audio, công cụ trả `audio content omitted because you do not support audio input`. Chưa có khả năng nghe, chưa có per-output auditory judgement, human MOS hoặc xác nhận tự nhiên. Không chế tạo đánh giá nghe, không tự hạ Acceptance Criteria hoặc đánh dấu D70 PASS từ ASR/acoustic metrics.

## Tương thích, migration và rollback

Hai family/voice có sample rate, API streaming/chunk, phonemizer, decoder, bộ ngôn ngữ và giấy phép khác nhau. Qwen nguyên bản không cung cấp explicit Vietnamese; Auto là diagnostic ngoài tập ngôn ngữ tài liệu, không là phương án thay voice được duyệt. Piper VI cần xác minh quyền từ nguồn Lessac trước quyết định triển khai. Cần tích hợp source/sample clocks, resampling, buffer, stop/cancel, concurrency/RAM và retention ở các milestone sau; candidate hiện chưa là sản phẩm voice hay API được chọn.

Không migration dữ liệu/config/index/model default trong nhiệm vụ này. Rollback chỉ retire namespace đánh giá đang sở hữu; giữ artifacts/SDK/native/results phục vụ audit, không xóa dữ liệu gốc. Mọi lựa chọn/thay thế model cần benchmark, hiệu năng/tài nguyên/tương thích, migration/rollback và phê duyệt rõ của chủ dự án. Chưa có lựa chọn mới. D71 còn gated bởi việc đóng D70 theo AC; AUDIO-VAD-ASR-001 và approved model/license gates vẫn bắt buộc trước D72.


## Kiểm toán và trạng thái tiếp theo

[Readonly measurement audit](evidence/d70-tts-readonly-measurement-audit.json) PASS về tính toàn vẹn kết quả và trạng thái hệ thống; **không phải D70 acceptance**.34private auditor controls PASS0.37s, kiểm tra copies đối kháng về coverage/order/source/SDK/device/precision/threads/voice/unsupported claims/EOS/native hash/timing/CORE/RSS/CPU/ASR edits/cap/listening/selection. Không chạy lại model trong audit.

624source/toàn bộ612file cũ nguyên byte và23475SDK/source entries khớp freeze; original model/config/V006/zero source-memory/quota-vector-probe-workers-locks/ACL-grants-triggers/15services/same CORE giữ nguyên. ExactD68 progress-document transition được kiểm tra old/current/Git, không refresh broad guards. Historical D67 full4495 chỉ phủ599source;436related hiện tại không được gọi thành full624-source suite.

[Bản nghe24audio ngoại tuyến](../data/backups/d70-tts-listening-review/index.html) có đủ timeline, native/preview hashes và authored text; [JSON review pending](../data/backups/d70-tts-listening-review/review.pending.json) giữ mọi judgement null/has_actually_listenedFalse. Đây là artifact để công cụ hoặc reviewer có khả năng nghe đánh giá tiếp, không phải yêu cầu chủ dự án đã nghe hoặc nguồn human labels.

D70 giữ **IN PROGRESS / NATURALNESS OPEN / NOT_SELECTED / NOT_DEPLOYED**. Phần benchmark máy, capability/license assessment và audit đã hoàn tất. Chưa thể đóng AC nghe thực tế bằng công cụ hiện tại; chưa tự chuyển D71. D71 tiếp theo là push-to-talk/recording consent và stop/cancel, độc lập với chọn giọng; chỉ được bắt đầu sau khi D70 được đóng theo AC hoặc chủ dự án duyệt thay đổi thứ tự/phạm vi. Model/voice selection, chuỗi giấy phép Piper VI và AUDIO-VAD-ASR-001 vẫn là các gate riêng trước D72/triển khai.
