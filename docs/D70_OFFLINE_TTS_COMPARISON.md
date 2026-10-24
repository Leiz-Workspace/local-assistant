# D70 — So sánh TTS ngoại tuyến

> **Trạng thái hiện tại — 2026-10-24:** D70 đã hoàn tất đo máy; nghe thực tế **0/24, chủ dự án để test sau**. [ADR-111](ADR/111-owner-deferred-tts-listening-and-explicit-recording.md) đã cho phép tiếp tục; D71–D73 đã kiểm chứng phạm vi local, D74 còn nghiệm thu sản phẩm. Các dòng “D71 NOT STARTED” ở lịch sử bên dưới mô tả thời điểm trước quyết định này. Các guard research vẫn đóng; xem phê duyệt và lượt chạy theo đúng ngày của từng thí nghiệm. Không mở lại evaluator campaign hoặc sửa điểm/nhãn cũ. Xem [trạng thái dự án hiện tại](RELEASE_CANDIDATE_STATUS.md), [hướng dẫn nghe](D70_MANUAL_LISTENING_TEST.md).

**D70 acceptance clarification2026-10-23:** Machine measurements are recorded; **actual listening0/24 remains the unmet original AC**. Fresh native audio input is still omitted. Extra evaluator research is a route, not a replacement deliverable; no new trial scheduled. [Exact checklist and blocker](D70_ACCEPTANCE_STATUS.md).

**Historical actual checkpoint2026-10-23:** Approved ADR110 completed; eager/SDPA first answers unchanged on4historical presence cases, full-vector differences retained/audited. Scope consumed/guardFalse, no backend/model selection. D70 naturalness OPEN/D71 NOT STARTED. [Actual result](D70_VOXTRAL_ATTENTION_DIAGNOSTIC.md).

**Historical checkpoint2026-10-23:** Approved ADR-109 completed; strict **4/12 FAIL**, no conditional24audio review. Guard closed/scope consumed; D70 naturalness OPEN/D71 NOT STARTED. [First campaign report](D70_VOXTRAL_AUDITORY_CAMPAIGN.md), [immutable observations/audit](evidence/d70-voxtral-auditory-first.json), [source-only triage](evidence/d70-voxtral-auditory-source-triage.json).

**Mục đích:** Ghi lại bằng chứng thực tế của MODEL-EVAL-005, phân biệt khả năng chạy, tiếng Việt được hỗ trợ, chỉ số đo được và tiêu chí đánh giá còn mở. Tài liệu không phê duyệt chọn hoặc triển khai model.

**Checkpoint ADR-105 trước đó ngày 2026-10-23:** ADR-105 đã được duyệt và chạy một lượt; dịch vụ trả `GPU task aborted` ở kiểm soát đầu tiên, chưa có đánh giá hợp lệ. Quyền chạy đã dùng và được khóa lại; không gửi 24 audio benchmark. Bộ kiểm thử TTS liên quan đạt 355 PASS, 0 SKIP; model, dữ liệu và CORE giữ nguyên. [Bằng chứng](evidence/d70-specialist-campaign-first.json). D70 vẫn mở/D71 chưa bắt đầu.

**Checkpoint ADR-103 trước đó2026-10-23:** Chủ dự án duyệt **“Duyệt một lượt diagnostic ADR-103”**. Lượt đã chạy39.749s/exit0/no timeout, raw `yes/no/no/yes` khớp4control và4EOS. Audit phát hiện helper mount vào worker còn chứa metadata/prepare code phía cha: **không coi là strict protocol PASS**, dù worker không truyền các reference đó vào input model. Đã tách pure runtime, native namespace probe PASS; chưa chạy lại original model. Scope một lượt đã dùng, diagnostic modes đóng lại; chỉ imports/load còn mở.249TTSrelated PASS7.63s/Ruff PASS. [Bằng chứng](evidence/d70-presence-diagnostic-first.json). D70 mở, reviewer NOT QUALIFIED/D71 chưa bắt đầu.


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


## 2026-10-23 continuation: specialist route prepared, external media scope pending

[Reviewer reliability assessment](D70_REVIEWER_RELIABILITY_ASSESSMENT.md), [ADR-105](ADR/105-proposed-specialist-public-auditory-review.md), [proposal evidence](evidence/d70-specialist-review-proposal.json). Original ADR-104 strict8of12failure remains unchanged; no rerun or parser/label tuning. Investigation distinguishes model judgement failure, input correctness and interface availability. Native meta-only counting agrees with the analytic lower bound:7,615,616,512text parameters/15,231,233,024BF16bytes≈14.185GiB, before modalities/runtime, so no local native7Bweights are downloaded under12GiB cap. This is not measured RAM/VRAM.

Author-linked specialist demo reports RUNTIME_ERROR. A community SpeechJudge demo reports RUNNING and its exact public metadata/schema/source interface has been checked without audio; remotely loaded weights/seed/resources and retention remain unattested, VI naturalness unqualified. Existing official Qwen frontends still report RUNNING but prior inference failures are not overturned by metadata. No new model/provider is selected or deployed.

New standalone client and fixtures prepare one proposed18control/conditional24comparison campaign, covering all24original outputs in both orientations if controls pass. Guard defaults false; no real packet, audio upload, prediction, weight/package download or new local model inference.34new/338TTSrelated PASS18.10s/0FAIL/0SKIP/Ruff PASS; all642prior source bytes unchanged/current645,32priorD70JSON/917protected/176inputs/23475+23382SDK/16artifacts/original system/data/sameCORE preserved. Explicit new-recipient permission is needed only before sending neutral test audio/authored text to that community endpoint; one campaign approval would cover both conditional stages. D70 AC OPEN/D71 NOT STARTED.


## 2026-10-23 first-evidence gate follow-up

[Binding and correction evidence](evidence/d70-specialist-first-evidence-binding.json). While external consent remains pending, the standalone gate now verifies exactly56first-control artifacts, all hashes, fixed-origin unique event receipts and exact result/observation/SSE/parsed-judgement agreement. Two regressions reproduced against6e9f6ab; after repair41specialist/346TTSrelated PASS0.53s/18.40s,0FAIL/0SKIP/Ruff PASS. Authored full18control+24review flow and partial-stream failure tests require no real upload/model. Execution remains disabled and original ADR-1048of12 unchanged.

Audit correction:6e9f6ab's917preserved claim used a pre-edit audit; a later redundant agent note changed protected AUDIO_BACKLOG.md, leaving916of917unchanged at that commit. Only that append is now removed and the exact protected baseline restored, while current progress stays in canonical roadmap/devlog/backlogs. First failed audit/removed-note version and prior evidence retained; fresh917protected/runtime/model/SDK/data/sameCORE audit passes. No historical result is relabelled. All642pre-specialist source bytes remain unchanged/current645; only specialist helper/test changed. No media, weights or predictions added. D70 OPEN/D71 NOT STARTED.


## 2026-10-23 real local control packet ready; external consent remains pending

[Local preparation evidence](evidence/d70-specialist-local-control-preparation.json). Removed the unnecessary consent barrier around reversible local copies while retaining EXECUTION_ALLOWEDFalse for every provider client/upload/inference. Actual18control/36WAV/38file packet is now prepared privately and its first manifest verified; later execution must reuse/check those exact bytes. Common benchmark inputs still require complete18control qualification and are not prepared. No media sent, no prediction or new weights.

A first local CLI attempt exposed missing owned-root initialization before any file publication; fixed0700creation/symlink rejection and tested a previously nonexistent root, preserving the failed log.348TTSrelated PASS18.38s/0FAIL/0SKIP/Ruff PASS, including2new preparation/changed-packet cases after the binding follow-up. All642pre-specialist source bytes and34priorD70JSON preserved/current645,917protected/176inputs/23475+23382SDK/16artifacts/original system/sameCORE audit passes;24pending judgements unchanged. Local preparation was authorized continuation work; only transmission to the new community recipient awaits explicit permission. D70 OPEN/D71 NOT STARTED.

## 2026-10-23 ADR-105 approved campaign: upstream GPU failure, no auditory scores

Owner explicitly approved **“Cho phép gửi audio theo ADR-105”**. [Approved freeze](evidence/d70-specialist-approved-freeze.json), [actual first evidence](evidence/d70-specialist-campaign-first.json), [protocol and outcome](ADR/105-proposed-specialist-public-auditory-review.md). Reused the hash-bound first local packet; exact source/runtime/schema preflight passed. Two neutral WAV uploads and one accepted prediction request reached the community endpoint. At the first identical EN control, four heartbeats ended in `System Error: 'GPU task aborted'` / `ZeroGPU worker error`, without a score or rationale. The unchanged parser rejected it as `specialist_first_generation`; this is **service failure, not measured wrong audio judgement**. One control attempted/17unattempted/0usable comparisons, no retry or conditional24benchmark packet/upload. Remote completion/resources/root cause/deletion remain unverified.

Command elapsed78.37s; local-client maximumRSS43276KiB, not provider RAM/VRAM. Exit0 means handled failure recorded, not PASS. Gate restoredFalse/scope consumed; original local policy remains imports/load-only. **350preflight/355finalTTSrelated PASS19.04s/19.30s,0FAIL/0SKIP/Ruff PASS**,7new regression cases since348; no full645-source or auditory benchmark claim. All642pre-specialist source bytes preserved/current645,917protected/35priorD70JSON/176inputs/23475+23382SDK/16artifacts/original system/security/model/data/sameCORE audit PASS. First audit-launch import-root error retained and corrected without an inference retry.24original pending naturalness labels remain null/unlistened. **D70 naturalness OPEN; D71 NOT STARTED.** No model/default/provider deployment, weights/package download, AC waiver or new campaign scheduled.

## 2026-10-23 context/VRAM hypothesis checked

[Resource diagnostic](D70_CONTEXT_RESOURCE_DIAGNOSTIC.md), [measured evidence](evidence/d70-context-resource-diagnostic.json). Owner permitted reducing context if useful. Current local CORE remains32K/parallel1,9386MiB GPU allocation with5675MiB free on the host at the sample; this is not a historical peak or an OOM exclusion. The failed evaluator runs on external ZeroGPU, so lowering local CORE context cannot change its GPU resources. Fresh metadata exposes only text/twoaudio/number-of-generations, already1; no context/output-token/runtime knob. Exact retained provider source sets30sGPUduration, moves the model to CUDA inside that function, and allows1024outputtokens. Duration/transfer overhead is a source-backed investigation lead, not a proven cause. RemoteOOM remains unconfirmed; no inference retry/upload/restart/context change performed.6existing boundary tests PASS0.18s/0SKIP and readonly645source/917protected/originalsystem/sameCORE audit PASS. D70 naturalness OPEN/D71 NOT STARTED;355prior related tests and all first failed outcomes unchanged.

## 2026-10-23 offline provider patch complete; local preparation option assessed

[ADR-106](ADR/106-proposed-controlled-speechjudge-runtime-remediation.md), [provider-source evidence](evidence/d70-provider-source-remediation.json). Full source-bound candidate and patch are locally generated and independently applied/checked: move CUDA placement outside request time,120sprovider allowance, pin the inspected model revision; retain BF16/SDPA, decoder/rubric and four-parameter API.11new tests/366related PASS19.36s/0SKIP. This is an undeployed proposal, not a proven GPU fix or auditory judgement. The owner confirmed no Hugging Face Space **and no account**; readonly14Vault/local credential inspection found no matching configured token. No account/Space, billing, authentication or model download was attempted. [Resource decision](evidence/d70-reviewer-hosting-resource-decision.json).

[ADR-107](ADR/107-proposed-isolated-voxtral-evaluator-preparation.md), [local feasibility](evidence/d70-voxtral-meta-feasibility.json), [exact unapproved preparation manifest](evidence/d70-voxtral-preparation-manifest.json). Public ungated Voxtral-Mini-3B-2507 is only an additional research candidate; VI is not listed and naturalness unqualified. Existing SDK meta-only construction matches4676271104parameters/762tensors/9356382208native tensor bytes, including strict-FP32 audio positions. First all-BF16 estimator failure retained/corrected without weights or generation. This is storage feasibility, **not measured RAM/VRAM or proof of fitting12GiB**. Exact9artifacts total9371455742bytes, excluding duplicate consolidated weights; proposed isolated CPU SDK/model root20GiB, unchanged12GiBAS/14GiBhost guard/sameCORE. Preparation remains unapproved; no weights/SDK installation/load/inference. Final367TTSrelated PASS25.04s/0SKIP/Ruff PASS, current648source/all645prior bytes preserved. D70 naturalness OPEN/D71 NOT STARTED; original models, first failures and24pending labels remain unchanged.

## 2026-10-23 approved ADR-107 preparation completed

The owner approved **“Duyệt chuẩn bị local theo ADR-107”**. [Actual preparation/audit](evidence/d70-voxtral-preparation-completed.json), [ADR-107 execution and boundaries](ADR/107-proposed-isolated-voxtral-evaluator-preparation.md#executed-preparation-2026-10-23). Earlier unapproved/proposed entries remain historical. All9 exact Voxtral artifacts downloaded,9,371,455,742bytes, independently full-hash verified; shard/index audit762tensors/9,356,382,208payloadbytes. Separate uv CPU SDK installed with unchanged core pins/hash-locked dependencies,19,561entries frozen and imports PASS in an offline/read-only/no-GPU/no-model/no-audio namespace. Root with cache/SDK/models/receipts **10.5929GiB <20GiB**; this is disk, not model RAM/VRAM. No neural model load or audio inference.

Final383TTSrelated PASS25.39s/0FAIL/0SKIP/Ruff PASS, including16new preparation tests; no full650-source or auditory-quality claim. Retain the first budget-fixture and uv-lock-validator failures plus corrected successful preparation; no changed dependency pins. Original648source/38priorD70JSON/917protected/176inputs/two oldSDKs/16oldartifacts/24pending labels/services/database/model config/same CORE verified unchanged. Preparation scope consumed, execution gateFalse. **D70 naturalness OPEN; D71 NOT STARTED.** Next is a separately reviewed load/integrity-only protocol for the retained bytes at12GiB AS/14GiB host headroom/CORE loaded; held-out auditory competence remains a later gate. No production replacement/default change or additional download scheduled.

## 2026-10-23 Voxtral load-only protocol ready; original execution closed

[ADR-108](ADR/108-proposed-voxtral-load-integrity-only.md), [actual protocol/test/audit evidence](evidence/d70-voxtral-load-protocol-prepared.json). Separate controller/runtime preserve the accepted Qwen loader and all650existing source bytes. Bounded index/header checks, native strict-FP32/BF16 schema, pread, complete original-payload hashes/pointers and parent reconciliation are implemented. A model-free/offline/readonly namespace tests only a2,760-parameter/36-tensor synthetic native checkpoint; its success proves no original-model memory fit or auditory competence. Original worker/controller gateFalse; real output directory absent. No original checkpoint load, audio request, new download or SDK change.

Final **404TTSrelated PASS30.12s/0FAIL/0SKIP/Ruff PASS**, including21new controls; no full653-source regression. First integration failure from projecting pytest-dependent fixture source retained; standalone projection fixed without environment changes. Readonly original/new SDK/artifact/source/data/service/sameCORE audit PASS,24naturalness labels unchanged. Concrete next proposal is **one load/integrity-only attempt**, existing weights/SDK,12GiBAS/14GiBsampledhostguard/CPU2/offline/600swall/20GiBroot, no retry or audio inference. ADR-107 approval excluded loading, so this execution remains separately unapproved. **D70 naturalness OPEN; D71 NOT STARTED.**

## 2026-10-23 approved first Voxtral load/integrity passed

The owner explicitly approved one ADR-108 load-only attempt. [First result and independent audit](evidence/d70-voxtral-load-first.json), [ADR-108 closure](ADR/108-proposed-voxtral-load-integrity-only.md#actual-first-execution-and-closure-2026-10-23). **PASS_LOAD_INTEGRITY_ONLY**, 1 attempt/0 retries, 762 tensors/9,356,382,208 payload bytes independently verified with original pointer/hash/shape/BF16+FP32 preservation. Native load/integrity **30.661s**; worker wall **33.029s**. Measured whole-worker **RSS RAM9.0404GiB**, virtual **VmPeak10.2380GiB**, retained12GiBAS/14GiBhostguard/CPU2. These are load-worker figures, not VRAM, model-only memory or audio-inference fit.

All prepared/original SDKs, artifacts, model choices, data, services and sameCORE preserved; 24 naturalness labels remain null/unlistened. Runtime permission flag was enabled only for the approved attempt, then restored to its exact reviewed closed bytes; worker reaped/no longer resident. Final **405TTSrelated PASS30.41s/0FAIL/0SKIP/Ruff PASS**; no full653-source or auditory-quality claim. The only final source change is one added permission-switch test; all652other source bytes unchanged. No audio features, tokenizer/processor or predictions. **D70 naturalness OPEN; D71 NOT STARTED.** Next is a separately reviewed held-out auditory qualification protocol; no audio execution/model selection granted by this consumed load scope.

## 2026-10-23 Voxtral auditory campaign prepared; execution closed

[ADR-109](ADR/109-proposed-voxtral-auditory-qualification-and-conditional-review.md), [actual preparation/test/audit evidence](evidence/d70-voxtral-auditory-protocol-prepared.json). New independent controller/runtime freeze12blind EN/VI/presence/severe-defect/tie controls,18signals/20files; no24audio review packet yet. Original audio/model execution remains unapproved and gateFalse. Proposed one campaign admits a conditional24audio qualitative review only after12/12first controls, native EOS/schema, original tensor fidelity, unchanged inputs/CORE and independent no-weights conditioning replay all pass. No retries or model selection.

Native SDK synthetic tests verify lossless FLOAT WAV source prefixes plus exact zero-padding,128x3000mel features,375audio placeholders/chunk (750/pair), raw token and FP32/BF16 feature hashes; no original weights/recorded audio mounted. Tiny2,760parameter native SDPA/decoder tests preserve bytes/dtypes/pointers; observed fixture logit difference0 is not a real-model accuracy/performance claim. Four preparation compatibility failures were retained/corrected in the caller/estimator without SDK changes or original predictions. Final **431TTSrelated PASS40.29s/0FAIL/0SKIP/Ruff PASS**,26new controls, including duplicate-original-identity rejection before24audio publication.656source/all653prior bytes and original system/models/SDK/data/sameCORE/24pending labels verified unchanged. No full656-source or naturalness benchmark claim. **D70 naturalness OPEN; D71 NOT STARTED.**

## 2026-10-23 approved ADR-109 campaign completed: strict 4/12 FAIL

[First campaign report](D70_VOXTRAL_AUDITORY_CAMPAIGN.md), [immutable observations/audit](evidence/d70-voxtral-auditory-first.json), [source-only triage](evidence/d70-voxtral-auditory-source-triage.json).

The owner explicitly approved “Duyệt campaign ADR-109” for commit2348566. One original-weight worker completed all12 first responses/EOS/schema; one no-weights conditioning replay matched every input/feature receipt and all762original tensor receipts matched ADR108. Strict scores: presence1/4, language1/2, comparisons2/6, total4/12 against unchanged12/12. Both identical pairs returned SECOND, silence YES, EN/VI speech NO and VI language ENGLISH. No answer repair, retry, threshold change or causal model-quality claim. The conditional24audio packet/worker were not created because the gate failed.

Worker wall238.164530s; replay5.379030s, both exit0/no timeout/reaped. Whole-worker peak RSS **RAM9.428303GiB** and **virtual VmPeak10.238766GiB** under12GiBAS; sampled host headroom14GiB retained. CPU2/inter-op1/affinity0,1/offline/nativeSDPA; no evaluator GPU/VRAM measurement, new download/package or CORE context change. Executed source bindings were independently checked before restoring the auditory guard to exact reviewed False bytes; the one-campaign scope is consumed. Source-only pinned processor/forward/cache/decoder/model-card triage is complete, without another inference; root cause remains unconfirmed.

Final **432TTSrelated PASS40.13s/0FAIL/0SKIP/Ruff PASS** (one existing deliberate duplicate-archive warning), not full656-source regression or qualification PASS. Fresh readonly audit verifies656source/all655other final bytes,917protected/176inputs/38oldD70JSON/23,475+23,382oldSDK entries/16oldartifacts/19,561VoxtralSDK entries/all9artifacts/originalservices/data/security/sameCORE preserved. Only one positive permission-switch unit test remains as a source change.24pending human naturalness fields remain null/unlistened. No Docker/Vault/database/config/production-model/default change, deployment or push.

**AUDIO-EVAL-VOXTRAL-QUAL-004 EXECUTED/CLOSED FAIL; reviewer NOT QUALIFIED. D70 NATURALNESS OPEN; D71 NOT STARTED.** Reviewer-reliability parent remains open. No replacement model or new neural experiment is selected/scheduled. Existing AC, prior failures and D24/a88584b/E5 rollback stay unchanged.

## 2026-10-23 further synthetic diagnosis complete; ADR-110 prepared, original execution closed

[Investigation and limits](D70_VOXTRAL_SYNTHETIC_DIAGNOSTICS.md), [prepared source/test/audit evidence](evidence/d70-voxtral-attention-protocol-prepared.json), [concrete ADR-110](ADR/110-proposed-voxtral-paired-attention-diagnostic.md). Standard versus pread loading preserves nonpersistent FP32 RoPE buffers and exact logits on a7,116parameter fixture; eager/SDPA cache routing is correct on tiny random inputs. A random1280width/20head/1500position attention block preserves bidirectionality, with maximum difference0.000244140625 within declared tolerance. Four authored mel inputs match independent Mistral-filter/STFT math exactly. These tests establish no causal fix or original-weight quality.

New paired controller/runtime retain both backend first responses and full131072-element FP32 logit vectors; the parent independently recomputes hashes/argmax/differences/RMS and source-bound no-weights replay. Actual native paired forwarding/generation is tested only on a random2,114,232parameter fixture with authored silence; its random invalid labels/non-EOS responses remain unmodified and are not qualification evidence. Final **470TTSrelated PASS64.37s/0FAIL/0SKIP/Ruff PASS**,38new tests, one existing deliberate duplicate-archive warning; not full661-source regression. Fresh audit661source/all656prior bytes/917protected/176inputs/52immutableD70JSON/threeSDKs/all prior artifacts/originalservices/data/security/sameCORE/24pending human labels preserved.

AUDIO-EVAL-VOXTRAL-DIAG-005 now has protocol/code/tests/local4signal/6file packet complete. **Execution NOT APPROVED/NOT RUN; guardFalse.** Proposed one original-weight worker compares eager then SDPA on four historical presence signals,8explicit forwards+8first responses, then one no-weights replay. Retain12GiBAS/14GiBhostguard/CPU2/offline/COREloaded/20GiBroot; worker900swall/retained1200sCPU, replay120swall. No new weights/packages, retry, model/backend selection, fresh qualification or24audio review. Original eager fit is unmeasured and must fail inside the unchanged cap if insufficient. P1 dependency of reviewer reliability; effort one bounded diagnostic/audit, risks original-scale numeric differences/memory/time/order/selection bias, production migration none, rollback closes the research guard and retains first evidence. Previous explicit ADR109 one-campaign approval is consumed; a new original worker awaits its own exact approval. Original4/12FAIL and all prior results remain unchanged. **D70 naturalness OPEN; D71 NOT STARTED.**

## 2026-10-23 approved ADR-110 diagnostic complete: numerical differences, unchanged answers

[Actual report](D70_VOXTRAL_ATTENTION_DIAGNOSTIC.md), [immutable first observations/full-vector/audit receipts](evidence/d70-voxtral-attention-first.json). The owner explicitly approved “Duyệt một lượt ADR-110” for commita950539. Exactly one original-weight worker performed8explicit forwards+8first generations on4historical presence cases, followed by one no-weights replay. Both eager and SDPA returned **NO/YES/NO/NO**, all8raw answers matching ADR109 and all8nativeEOS/schema valid. Full logit vectors differ (maximum absolute difference0.25–0.53125), but first-token argmax agrees on all4cases. Parent independently recomputes all8full131072-elementFP32 vectors/metrics and reconciles both backend/historical/replay features plus762native tensor receipts. Switching to eager did not fix these four answers; this is not fresh qualification or a universal root-cause exclusion. Original4/12FAIL remains unchanged.

Worker217.312967s/replay5.337580s, exit0/no timeout/reaped; whole-worker peak **RSS RAM9.565887GiB**, **virtualVmPeak10.237831GiB**, retaining12GiBAS/14GiBsampledheadroom/CPU2/offline/originalCOREloaded. No evaluator VRAM/new weights/packages/retry/context change. After verifying full executed-source bindings, the guard was restored to exact reviewedFalsebytes; all661canonical sources match the reviewed baseline. Final **470TTSrelated PASS64.25s/0FAIL/0SKIP/Ruff PASS**, not full661-source or reviewer-quality PASS. Fresh audit917protected/176inputs/53prior immutableD70JSON/allthreeSDKs/allpriorartifacts/originalservices/data/security/sameCORE/24pending humanlabels preserved. DIAG-005 bounded counterfactual COMPLETE/no causalfix; scope consumed/guardFalse/workers0. No backend/model selection, qualification rerun,24audio review or next trial scheduled. Reviewer-reliability parent remains open. **D70 NATURALNESS OPEN; D71 NOT STARTED.**
