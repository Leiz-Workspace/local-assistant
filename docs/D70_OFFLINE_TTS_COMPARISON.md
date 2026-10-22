# D70 — So sánh TTS ngoại tuyến

**Mục đích:** Ghi lại bằng chứng thực tế của MODEL-EVAL-005, phân biệt khả năng chạy, tiếng Việt được hỗ trợ, chỉ số đo được và tiêu chí đánh giá còn mở. Tài liệu không phê duyệt chọn hoặc triển khai model.

**Quyết định mới nhất2026-10-23:** Chủ dự án duyệt **“Duyệt một lượt diagnostic ADR-103”**. Lượt đã chạy39.749s/exit0/no timeout, raw `yes/no/no/yes` khớp4control và4EOS. Audit phát hiện helper mount vào worker còn chứa metadata/prepare code phía cha: **không coi là strict protocol PASS**, dù worker không truyền các reference đó vào input model. Đã tách pure runtime, native namespace probe PASS; chưa chạy lại original model. Scope một lượt đã dùng, diagnostic modes đóng lại; chỉ imports/load còn mở.249TTSrelated PASS7.63s/Ruff PASS. [Bằng chứng](evidence/d70-presence-diagnostic-first.json). D70 mở, reviewer NOT QUALIFIED/D71 chưa bắt đầu.


**Trạng thái:** IN PROGRESS — chờ khả năng nghe thực tế theo quyết định chủ dự án ngày2026-10-22. ADR-097 bị từ chối; giữ nguyên AC và thứ tự D70→D71. Source chuẩn bị `7ff5438`; D69 vẫn PASS tại `5653de4`. Chưa chuyển sang D71.

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

D70 giữ **IN PROGRESS / NATURALNESS OPEN / NOT_SELECTED / NOT_DEPLOYED**. Phần benchmark máy, capability/license assessment và audit đã hoàn tất. Chưa thể đóng AC nghe thực tế bằng công cụ hiện tại; chưa tự chuyển D71. D71 tiếp theo là push-to-talk/recording consent và stop/cancel, độc lập với chọn giọng; chỉ được bắt đầu sau khi D70 được đóng theo AC. Chủ dự án đã chọn giữ nguyên AC, chờ khả năng nghe và từ chối thay đổi thứ tự/phạm vi tại ADR-097 ngày2026-10-22. Model/voice selection, chuỗi giấy phép Piper VI và AUDIO-VAD-ASR-001 vẫn là các gate riêng trước D72/triển khai.


### Kiểm tra lại khả năng nghe theo yêu cầu tiếp tục

Sau quyết định giữ nguyên AC tại `9d58085`, đã gửi lại đúng bản nghe smoke Ogg có hash được xác minh, không sinh audio mới. Công cụ vẫn trả `audio content omitted because you do not support audio input`. Tra cứu plugin bằng ba truy vấn tìm thấy Descript chưa cài, có mô tả transcription/cleanup/editing; chưa có bằng chứng khả năng đánh giá tự nhiên thực tế đáp ứng AC. Kết quả tra cứu không phải danh mục đầy đủ; có thể còn lựa chọn khác trong [danh mục plugin](https://chatgpt.com/plugins). Không cài plugin hoặc gửi audio ra dịch vụ ngoài. [Bằng chứng recheck](evidence/d70-audio-capability-recheck-001.json).

624source và176file audit inputs khớp hash;24judgements vẫn pending/null. D70 tiếp tục chờ khả năng nghe, D71 chưa bắt đầu, ADR-097 vẫn REJECTED. Không thử lại benchmark hoặc thay đổi model/AC.


### Tiếp tục kiểm tra dependency và thử qualification audio thật

Đã kiểm tra readonly14Vault records; không có matching metadata xác định evaluator audio được cấu hình, không ghi secret values hoặc sửa Vault. Đã đọc được nguồn Lessac/CSTR trước đó bất khả dụng; quyền dùng dataset giới hạn nghiên cứu, full weight/output rights của PiperVI vẫn chưa được xác minh. [Dependency/license follow-up](D70_AUDIO_REVIEW_DEPENDENCIES.md) phân biệt nguồn dataset với license của weights/engine/output; không tự thay model.

Tìm thấy API của demo Qwen chính thức đang chạy. [ADR-099](ADR/099-bounded-public-audio-review-qualification.md) chốt thử5synthetic/generated-smoke controls trên interface công khai, no credential/local neural download/model-default change. Serving code dùng alias `qwen-omni-turbo`, backend/decoder chưa pin được; không gọi là original7B local hoặc human MOS. Client40new/158TTSrelated controls PASS0.39s/0SKIP, một expected ZIP warning từ test cũ;626source/all624prior bytes freeze trước call. Chưa có qualification hoặc nhận xét nghe mới; chỉ xét review24audio khi controls đạt. ADR-098 local3B proposal chưa được phê duyệt/provision, ADR-097 vẫn REJECTED; D70 chưa đóng/D71 chưa bắt đầu.

### Kết quả thử evaluator công khai và SDK chính thức

Checkpoint trên được tiếp nối bằng ba packet qualification, mỗi packet chỉ thực hiện control đầu rồi dừng: Qwen2.5 transport đầu lỗi session404; sau sửa session theo source Gradio thì error event/null; Qwen3.5 alias `qwen3.5-omni-plus` cũng error event/null. Giữ cả default-settings availability probe lỗi riêng. Không có usable audio judgement hoặc naturalness score; không suy ra chất lượng nghe của backend từ lỗi transport/service. Không upload24native benchmark outputs. [Chi tiết từng lượt](D70_AUDIO_REVIEW_DEPENDENCIES.md).

SDK Gradio1.13.3 được cài bằng uv trong environment riêng Python3.12.3 để kiểm tra normal published queue/SSE. Giữ các lỗi setup đầu, empty-token protocol và một-worker executor contention; cấu hình hai workers đạt upload/queue/SSE HTTP200 nhưng timeout120s/exit124, không trả judgement. Owned SDK processes đã kết thúc; remote completion/retention/cancellation chưa xác minh. Không thay app/D68/D69/D70 environment, không tải neural weights mới hoặc chạy lại synthesis.

**42client tests mới/160TTSrelated PASS0.39s, Ruff PASS**; đây là scope TTS scripts liên quan, không thay thế historical436related/full4495 hoặc được gọi thành full626-source suite. [Audit hiện tại](evidence/d70-audio-evaluator-availability-audit.json) xác minh626source/toàn bộ624prior nguyênbyte,176original audit inputs,23475original SDK entries và original models/config/data/security/runtime/CORE.24pending reviews vẫn null/chưa nghe. D70 giữ IN PROGRESS; D71 NOT STARTED. ADR-098 local additional research evaluator chưa được duyệt hoặc tải weights, ADR-097 vẫn REJECTED. Primary Lessac license đã đọc được là follow-up sau protocol gốc, chưa tự giải quyết full weights/output rights hoặc thay đổi voice.


### Evaluator local được chủ dự án duyệt; first load chạm cap

Chủ dự án sau đó trả lời “Cho phép thử evaluator local theo ADR-098”. Đã provision đúng16artifact/revisionf75b40e.../ba shard11.97GB disk và uv SDK riêng23382entries.27new/187TTSrelated PASS0.43s/Ruff PASS. Import thật PASS6.065s/RSS415440KiB; native Thinker-only BF16/eager load FAILED6.459s/exit1, mmap shard thứ hai dưới12GiB virtual-address cap. Đây chưa phải đo model RAM/VRAM hoặc capability tiếng Việt; không chạy control/common24review. Giữ nguyên lỗi/first source/freeze và stop condition, không tự tăng cap. [Báo cáo local](D70_LOCAL_AUDIO_REVIEW.md).

[Readonly audit](evidence/d70-local-reviewer-integrity-audit.json) xác minh632source/toàn626prior bytes/original176inputs/23475SDK/model-config-data-security-runtime/CORE;24judgements vẫn null. ADR-10016GiB virtual-cap trial là PROPOSED/NOT APPROVED/NOT EXECUTED; không xin lại quyền tải model đã duyệt hoặc waiver AC. D70 vẫn IN PROGRESS, D71 NOT STARTED. Metadata/ADR ghi preapproval trước đó giữ nguyên trong lịch sử.


### Kết quả local trial sau16GiB/EOS repair — chưa đạt reviewer qualification

Owner continuation sau đề xuất ADR-100 được áp dụng vào đúng16GiB virtual lane/18GiB headroom precondition. Native loading PASS;9audio controls đầu506.293s/exit0 bị overrun192tokens vì outer generationEOSnull. Sửa riêng runner lấy original Thinker/tokenizer EOS151645/pad151643, giữ model/prompt/audio/expectations/seed/token cap; first failures/source/freezes không đổi.39new/199TTSrelated PASS0.44s/Ruff PASS.

Corrected9controls173.094s/exit0/9EOS complete/0validJSON, raw token first-turn/features match original9of9. Silence/noise vẫn được mô tả là speech, severe clipping là natural. Không sửa schema/labels để chấp nhận, không gán lỗi EOS đã sửa thành mọi quality failure, không chạy common24review. Peak worker RSS7.990GiB RAM corrected versus8.403GiB original, không VRAM/model-only/minimum RAM/cold-SLO claim. [Local report](D70_LOCAL_AUDIO_REVIEW.md), [final audit](evidence/d70-local-reviewer-final-integrity-audit.json)632source/all626pre-evaluator bytes/original176inputs/23475originalSDK/23382localSDK/models-data-security-runtime/CORE PASS.

**Local trial COMPLETED, evaluator NOT QUALIFIED; D70 remains IN PROGRESS, D71 NOT STARTED.** Audio input đã hoạt động nhưng chưa có reviewer đủ tin cậy.24original pending labels/native waveforms và mọi TTS benchmark máy giữ nguyên. Không đổi AC, model choice, provider/default hoặc order. Việc tiếp theo vẫn là qualified actual audio review tại D70; không tự chuyển ngày hoặc thay bằng ASR/acoustic proxy.


## 2026-10-23 continuation: tested quality protocol, execution blocked

[ADR-104](ADR/104-proposed-heldout-quality-and-conditional-blind-review.md) concretely prepares twelve new held-out presence/language/severe-corruption/tie controls and, only after strict first-control/source/runtime/parent-metadata recomputation, one blind48-observation review of the retained24complete16k signals. All four new modes remain blocked under imports/load-only policy; consumed ADR-103 scope is not reused.291TTSrelated PASS12.40s/Ruff PASS and native processor-only two-audio/real namespace checks; no original-model loading/generation or actual packet preparation. Prior9failures, limited4factual matches/namespace deviation and all24pending original judgements are unchanged. Fixed12GiB/14GiB/sameCORE/no downloads/default changes. Severe pair controls do not establish absolute naturalness accuracy, VI phonetics expertise or human MOS; results cannot automatically close unchanged D70 AC or advance D71. One entire conditional campaign is proposed for scope approval, rather than separate permission at every stage. [Evidence](evidence/d70-quality-protocol-proposal.json).


## 2026-10-23 ADR-104 approved campaign completed; controls fail

Owner explicitly approved **“Duyệt campaign ADR-104”**. [Actual first evidence](evidence/d70-quality-campaign-first.json), [approved freeze](evidence/d70-quality-campaign-approved-freeze.json). One original-model control worker completed93.437s/exit0/no timeout/12EOS; **8of12strict matches**, with presence4/4, language1/2 (raw `English` violates lowercase protocol) and pair comparisons3/6. Three pair semantic mismatches include an identical EN pair judged second and two damaged-first pairs judged second. Do not normalize labels/parser or rerun these controls. Input-only replay independently reproduces all12feature hashes/masks/token counts, ties have identical features and damaged pairs distinct features; full1442tensor parent fidelity verifies. This replay loads no model or generates a judgement.

Observed RSS9.723GiB RAM/VmPeak10.422GiB virtual/CPU156.821s within approved12GiB/14GiB policy; no minimum-RAM/VRAM or quality certification. Failed gate prevents preparation/execution of conditional24output review, so all24original pending labels remain unchanged. Four campaign modes closed, imports/load-only restored, scope consumed.304TTSrelated PASS12.63s/0SKIP/Ruff PASS;642sources/640approved unchanged,30priorD70JSON/917protected/176inputs/23475+23382SDK/16artifacts and original system/data/security/sameCORE audit preserved. No download/model/default/data/service change. D70 naturalness OPEN/D71 NOT STARTED; actual auditory competence is still inadequate for the accepted gate. Campaign milestone complete with failure; next assessed P1 is AUDIO-EVAL-REVIEWER-RELIABILITY-001, no new inference scheduled.
