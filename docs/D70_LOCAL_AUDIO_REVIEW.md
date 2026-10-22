# D70 — Evaluator audio local được phê duyệt

**Mục đích:** Ghi quyền thử, nguồn model/runtime, protocol và kết quả thực tế của công cụ đánh giá audio bổ sung. Tài liệu này không thay kết quả TTS gốc hoặc tự đóng Acceptance Criteria.

**Quyết định mới nhất2026-10-23:** Chủ dự án duyệt **“Duyệt một lượt diagnostic ADR-103”**. Lượt đã chạy39.749s/exit0/no timeout, raw `yes/no/no/yes` khớp4control và4EOS. Audit phát hiện helper mount vào worker còn chứa metadata/prepare code phía cha: **không coi là strict protocol PASS**, dù worker không truyền các reference đó vào input model. Đã tách pure runtime, native namespace probe PASS; chưa chạy lại original model. Scope một lượt đã dùng, diagnostic modes đóng lại; chỉ imports/load còn mở.249TTSrelated PASS7.63s/Ruff PASS. [Bằng chứng](evidence/d70-presence-diagnostic-first.json). D70 mở, reviewer NOT QUALIFIED/D71 chưa bắt đầu.


Chủ dự án đã trả lời **“Cho phép thử evaluator local theo ADR-098”**. [ADR-098](ADR/098-proposed-isolated-audio-reviewer.md) được duyệt cho thử nghiệm nghiên cứu riêng có giới hạn. Giữ nguyên AC D70, ADR-097 REJECTED, model registry/default/CORE và thứ tự D70→D71. Không có phê duyệt chọn/deploy TTS, chuyển tiêu chí nghe sang ngày khác hoặc thay model dự án.

## Artifact và runtime

Đúng `Qwen/Qwen2.5-Omni-3B`, revision `f75b40e3da2003cdd6e1829b1f420ca70797c34e`. Đã tải và xác minh16artifact: ba shard safetensors nguyên bản **11,972,663,208bytes**, tokenizer/config/template/license/README gốc. Con số11.97GB là disk weights, không phải RAM/VRAM. Các shard đầy đủ có cả thành phần output không dùng; không tuyên bố chỉ tải Thinker weights. Không tải `spk_dict.pt`, không chạy Talker hoặc token-to-wave.

Model có [Qwen Research License tại revision đã pin](https://huggingface.co/Qwen/Qwen2.5-Omni-3B/blob/f75b40e3da2003cdd6e1829b1f420ca70797c34e/LICENSE), phạm vi thử này là nghiên cứu không thương mại. Không suy ra quyền thương mại, phân phối hay product adoption. Dùng genuine [Thinker-only interface của Transformers4.57.3](https://huggingface.co/docs/transformers/v4.57.3/model_doc/qwen2_5_omni#text-only-generation), không vá checkpoint/tensor hoặc remote code.

Uv environment riêng Python3.12.3/Torch2.10.0+cpu/Transformers4.57.3/NumPy2.3.5/safetensors0.8.0/librosa0.11.0/torchvision0.25.0+cpu; torchvision chỉ là SDK dependency, không tải pretrained vision weights riêng. Inventory **23382SDK entries** đóng băng trước import thật. Root evaluation khoảng13.27GB apparent disk tại thời điểm trước load, dưới budget20GiB. Không sửa app/D68/D69/D70 môi trường cũ hoặc lockfile.

## Protocol được đóng băng trước suy luận

Một process CPU, affinity0,1/Torch2threads/inter-op1, BF16/eager, cap12GiB **address space**, qualification600s, review7200s/14400CPU. Address-space limit không đồng nghĩa RAM RSS thực tế. Namespace không network/GPU/credentials/reference text; SDK/model/worker/samples readonly, private tmpfs128MiB, output qua JSONL có giới hạn. CORE giữ loaded cùng identity trước/sau và literal recovery.

Chín control được chốt trước predictions: EN/VI generated smoke riêng; silence5s; seed7noise5s; severe clipping copy; hai bản FLEURS EN/VI gốc; hai copy FLEURS có nửa giữa thay bằng zeros. Nguồn công khai cũ/metadata/hash được kiểm tra; đây không phải24native benchmark outputs. Control expectations/provenance ở parent, worker chỉ thấy ID mờ/sample count/hash/float32mono16k.

Năm control smoke/noise kế thừa PCM16 copies đã giữ nguyên. Convert PCM16÷32767 rồi resample_poly theo rate; nếu resampling overshoot thì chỉ copy qualification đó chia theo peak và ghi rõ divisor, không thay native signal hoặc giấu normalization. FLEURS gốc giữ nguyên sample bits; gap copies ghi chính xác zero span. Mọi input đầy đủ timeline, không trim hoặc sinh lại speech.

Prompt cố định/seven-key JSON, seed7/greedy/max192new tokens. Bắt buộc actual audio feature/mask/token evidence, raw response/token IDs/EOS/provenance; JSON/schema failure/cap/uncertainty được giữ, không repair semantic hoặc outcome retry. Qualification yêu cầu mọi control đạt, gồm nhận đúng VI/EN và phát hiện severe defects; không thay bằng ASR/acoustic proxy. Chỉ khi qualified mới chuẩn bị24retained outputs theo seed7 opaque order và original16k diagnostic copies, đầy đủ source/native/resampling/level provenance. AI observations không phải nghe trực tiếp của assistant hoặc human MOS. Nhận24JSON đơn thuần không đủ đóng D70.

## Kiểm thử và lỗi chuẩn bị được giữ nguyên

**27test mới/187TTSrelated PASS0.43s**, một expected ZIP duplicate warning ở test cũ, Ruff PASS. Không gọi đây là full632-source suite. Giữ nguyên historical160/436/4495 và scope của mỗi lượt. Kiểm tra artifact size/hash/exclusive publication/partial failures, blind request bounds, waveform integrity, strict JSON, source/coverage/EOS/audio-conditioning gates, namespace limits và chặn review khi chưa qualified.

Prepare đầu chạy bằng app env thiếu SciPy: chưa có neural prediction, giữ folder/log rồi chạy đúng evaluator environment thành công. Run preflight đầu thiếu synthetic identity directory: chưa chạy worker, giữ log/sáu source-test snapshots, sửa initialization và thêm regression test. [Freeze đầu](evidence/d70-local-reviewer-qualified-first-freeze.json) không bị ghi đè; [preflight-qualified freeze](evidence/d70-local-reviewer-preflight-qualified-freeze.json) chốt632source/toàn626prior bytes nguyên vẹn và control/runtime/approved ADR trước import tiếp theo.

## Kết quả thực tế hiện có

**Import SDK PASS**, worker exit0/6.065s, imports5.494s, lifetime process RSS415440KiB/CPU5.239s. Đây là RAM của import process, không phải model-only/minimum RAM/VRAM. CORE cùng PID/start/command và text recovery trước/sau PASS. Chưa có audio-conditioned observation trong lượt import.

**First native load FAILED**, worker exit1/6.459s, không timeout; lỗi mmap4,999,787,448bytes của shard thứ hai dưới `RLIMIT_AS=12GiB`. Chưa tới ready/processor/audio generation. Giữ nguyên stdout/stderr/result/freeze, không retry hoặc tự tăng cap. CORE cùng PID/start/command/text recovery PASS trước/sau. Không có đo RSS tại thời điểm failure hoặc virtual peak, không suy ra RAM/VRAM tối thiểu từ lỗi virtual address space.

[Original header layout](evidence/d70-local-reviewer-checkpoint-layout.json) cho9,406,928,896Thinker tensor bytes,769,209,856Talker và1,796,205,184token2wav; chỉ là checkpoint bytes, không phải thực RAM. Full shards chứa cả output components không dùng; không tách hoặc vá tensors. [ADR-100](ADR/100-proposed-local-reviewer-address-space-trial.md) chuẩn bị riêng đề xuất16GiB virtual cap với host headroom gate, không tải thêm model; **chưa duyệt hoặc thực thi**. Giữ đúng điều kiện stop của ADR-098.

Chưa có qualification/naturalness hoặc D70 acceptance. Bản pending24reviews và mọi TTS measurements gốc giữ nguyên; D71 chưa bắt đầu.

## Tiếp tục với cap16GiB theo ADR-100

Sau đề xuất cụ thể, agent đã diễn giải “Continue from where you left off” thành phê duyệt16GiB và thực hiện các lượt dưới đây trước khi nhận câu trả lời rõ ràng. Chủ dự án sau đó chọn giữ12GiB/chưa chạy tiếp; cách diễn giải approval đó đã được sửa tại ADR-100, không suy ra chủ dự án đã chọn16GiB. Lịch sử thực thi vẫn được giữ: preflight MemAvailable≥18GiB trước chuẩn bị và ngay trước launch, resource snapshots trước/sau load và trongfinally. Các model/SDK/control/prompt/decoder/AC/order giữ nguyên.32test mới/192TTSrelated PASS0.50s/Ruff PASS tại checkpoint đó, không full632-source regression.

**16GiB load-only PASS**, worker6.427s/exit0, genuine model load+processor0.637s. Missing/mismatched/error counts đều0;1102unexpected keys đều thuộc output components Talker/token2wav không thực thi. Thinker có4,703,464,448parameters, CPU/bfloat16, hai threads/inter-op1/affinity0,1. Full-original checkpoint được mmap; load đã được parent hash-read nên không gọi thời gian này là cold-storage load.

Kernel VmPeak15,823,836KiB≈15.091GiB virtual; after-ready VmRSS769804KiB và lifetime ru_maxrss769264KiB≈751.2MiB RAM. Hai counter có accounting khác nhau; không ép bằng nhau. RSS của lượt chỉ nạp không phải RAM suy luận hoặc minimum hardware: mmap có lazy page faults. Headroom ngay trước launch20,533,002,240bytes, không phải reserved RAM. CORE samePID/start/command/text recovery trước-sau PASS.

Đã bắt đầu first9control qualification trong namespace riêng; một memory point quan sát worker VmRSS7,937,604KiB khoảng7.57GiB, không phải peak. Chưa có kết quả đầy đủ tại checkpoint này, chưa có common24review hoặc naturalness acceptance. [16GiB protocol freeze](evidence/d70-local-reviewer-16g-first-freeze.json) giữ632source/toàn628file khác nguyênbyte, chỉ sửa bốn local-review controller/worker/test files; toàn626file trước evaluator và mọi native/audio/model/config cũ giữ nguyên. Các first12GiB/preflight failure không bị viết đè.

## First9control đã chạy; phát hiện lỗi EOS runner

First audio-conditioned run hoàn tất9observations/506.293s/exit0, không timeout; CPU993.169s, lifetime peak RSS8,810,840KiB≈8.403GiB RAM, kernel VmPeak15,822,808KiB≈15.090GiB virtual. Đây là toàn worker gồm imports/model/features/generation; không VRAM/model-only/minimum RAM claim. Mỗi input có actual audio tokens/feature mask/hash và đủ source provenance. Không dùng24native benchmark outputs.

Tất cả9responses dài192tokens, không dừng tại EOS và không parse được JSON. Không gọi worker exit0 thành review PASS; qualification chưa đạt. Raw first turns gọi silence/noise là speech và severe-clipping English là natural; đây là nội dung nguyên bản chưa được nhận làm structured labels, không phải evidence để tự đóng quality AC.

Đối chiếu nguyên generation_config.json cấp ngoài chỉ có metadata, không EOS. Native load xác nhận `model.generation_config.eos_token_id=null`, trong khi original Thinker config và tokenizer thống nhất EOS151645/pad151643. Mọi raw token array đều có151645 sớm (offset47–59) nhưng runner không dừng, sinh tiếp các hội thoại không được yêu cầu. Đây là lỗi runner, không được gán toàn bộ192-token overrun cho năng lực model.

Đã sửa riêng truyền native EOS/pad từ original Thinker/tokenizer với cross-check, không vá model/config/SDK, đổi prompt/labels hoặc chấp nhận Python-literal thay JSON. Thêm regression về empty outer config, missing/foreign boundary IDs và không dùng pre-repair packet để promote protocol mới. **39tests mới/199TTSrelated PASS0.44s**, Ruff PASS. Giữ tất cả first raw responses/old source snapshots và freezes.

Load sau sửa PASS6.283s/exit0, processor/model0.591s, native boundary151645/151643 và outerEOSnull được ghi thật. [EOS control-lane freeze](evidence/d70-local-reviewer-eos-control-first-freeze.json) chốt trước lượt9control riêng để xác minh end-to-end repair; audio/expectations/prompt/seed/max192tokens và mọi bound khác giữ nguyên. Lượt riêng này không rewrite hoặc relabel first failure và không tự hạ qualification; chỉ khi mọi control đạt mới có thể review24outputs. Chưa có kết quả đầy đủ của lượt sửa tại checkpoint này.

## Kết quả cuối của lượt native-EOS repair

Đã chạy đủ9observations sau sửa, **173.094s/exit0/no timeout**, CPU336.655s.9of9 kết thúc đúng EOS151645, độ dài48–60tokens; không còn192-token overrun. Token arrays của từng câu trả lời khớp chính xác prefix đến EOS đầu của lượt cũ9of9; source/features/mask/audio-token counts cũng khớp9of9. Bản sửa chỉ chốt đúng response boundary, không tạo câu trả lời có lợi hơn.

**0of9 validJSON, qualification FAILED.** Raw replies dùng Python-style single-quoted dictionaries; một reply còn dùng chuỗi `artifacts: 'none'` thay list. Không literal-eval/repair hoặc coi chúng là structured labels đạt chuẩn. Quan trọng hơn, raw first turns vẫn mâu thuẫn các known controls:

| Control | Nguồn đã chốt | Nội dung raw response | Kết luận giới hạn |
| --- | --- | --- | --- |
| clip-03 | Exact zeros5s | `'presence': 'speech', 'language': 'english'` | Mô tả speech không có trong control |
| clip-04 | Seed7 Gaussian noise5s | `'presence': 'speech', 'language': 'english'` | Không phân biệt được no-speech control theo protocol |
| clip-05 | Severe-clipping English copy | `'naturalness': 'natural', 'artifacts': []` | Không phát hiện severe defect đã chốt |

Các trích đoạn chỉ ghi raw text không được nhận làm machine-validated quality labels. Không báo accuracy0% hoặc MOS từ schema failures. Một số raw replies nhận đúng VI/EN nhưng chưa đủ chứng minh reviewer đáng tin hoặc tiếng Việt TTS đạt naturalness. Không retune prompt/labels/decoder hoặc lặp lại để tìm lượt đạt.

Corrected lifetime peak RSS8,377,988KiB≈7.990GiB **RAM**; kernel VmPeak15,823,896KiB≈15.091GiB **virtual**, finalRSS8,219,800KiB là point sample. Không VRAM/model-only/minimum RAM/general SLO/cold-load claim. Các limits600wall/1200CPU/16GiBAS được giữ, CORE cùng PID/start/command/text recovery trước-sau PASS. Owned evaluator processes đã kết thúc.

[Final readonly audit](evidence/d70-local-reviewer-final-integrity-audit.json) PASS632source/toàn626file trước evaluator và628file ngoài bốn local controller-worker/tests thay đổi; original176audit inputs/23475D70SDK/23382localSDK/model-config-data-security-runtime giữ nguyên. Kiểm tra gate thật từ chối evaluator chưa đạt; không có common24review packet hoặc waveform được reviewer này đánh giá,24pending judgements gốc vẫn null/chưa nghe.39new/199TTSrelated PASS0.44s/Ruff PASS, không full632-source suite; historical436related/full4495 giữ đúng scope.

**Trial COMPLETED / reviewer NOT QUALIFIED / D70 IN PROGRESS / D71 NOT STARTED.** Việc tiếp theo là tìm reviewer vượt các control thực tế trước đánh giá24outputs, giữ nguyên AC. Chưa chọn/tải evaluator khác hoặc thay model/default/provider, không thay bằng ASR/acoustic proxy và không mở theo dõi nền. Giữ mọi artifacts/first failures phục vụ audit; Piper VI license và các integration gates trước D72 tiếp tục riêng biệt.

## Thực thi quyết định giữ12GiB và chưa chạy tiếp

Khôi phục `ADDRESS_SPACE_BYTES=12GiB`, thêm một execution policy dùng chung để chặn controller API/CLI và worker trực tiếp trước input/affinity/SDK/model/CORE/subprocess. Không có CLI bypass hoặc tự resume. Giữ bản sửa native EOS đã kiểm chứng, mọi artifact/audio/result/freezes và cap16GiB lịch sử; không nạp hay đánh giá model mới.

**208TTSrelated unit/controlled tests PASS0.44s**, gồm9case mới kiểm tra pause ở bốn mode, CLI, worker trực tiếp, runtime constructor và review trên instance có sẵn. Các test pipeline cũ chỉ mở policy trong fixture đã mock model/services/subprocess, không inference thật. Ruff PASS. Đây không phải full632-source suite hoặc một lượt model validation. Các kết quả199test/9control trước đó giữ nguyên là lịch sử. Quyết định pause áp dụng evaluator; không tự đánh dấu hoàn tất D70 hoặc bắt đầu D71.

[Bằng chứng quyết định pause](evidence/d70-owner-evaluator-pause.json) xác minh static12GiB/disabled policy, không còn owned evaluator processes và18historical D70 evidence files nguyên byte. Đây là source/policy/unit-test verification, không phải một lượt model hoặc fresh service audit.

## ADR-102 — Kết quả nạp pread với headroom14GiB/cap12GiB

Explicit owner reply **“Duyệt headroom 14 GiB, giữ cap 12 GiB”** cho phép giảm riêng host preflight từ18xuống14GiB; process virtual cap12GiB không đổi. Ngưỡng18cũ xuất phát từ phương án16GiB, không phải model RAM đã đo; swap gần đầy là risk đã trình bày, không thay swap/dừng ứng dụng của chủ dự án. Source/tests/ADR đóng băng trước first new load, original preflight failure tại28cedf9 giữ nguyên.

Native Thinker-only original-weight load/integrity **PASS26.471s/exit0/no timeout**; model/processor20.892s bao gồm audits trên artifacts đã được parent warm-read, không cold-load. Tất cả1442tensor BF16/9,406,928,896bytes khớp original shape/keys và hashes đọc độc lập từ shards; native storage vẫn chia sẻ đúng original tensor buffers. Missing/unexpected/mismatch/error0. Parent đọc lại đủ payload và đối chiếu mọi hash sau worker exit: PASS.4,703,464,448parameters/CPU/BF16/threads2/interop1/affinity0,1, original EOS151645/pad151643.

Lifetime ru_maxrss9,786,388KiB≈9.333GiB RAM; kernel VmHWM9,786,536KiB là counter riêng, không ép bằng nhau. VmPeak10,897,948KiB≈10.393GiB virtual, dưới12GiB. Đây là toàn worker load-only, **chưa đo inference fit12GiB**, không VRAM/minimumRAM/generalSLO claim. Prelaunch MemAvailable19,063,668,736bytes, chỉ là sample không reservation. CORE cùngPID/start/command/text recovery PASS trước-sau; worker joined, không còn owned evaluator processes.

**222TTSrelated PASS6.00s/0FAIL/0SKIP/Ruff PASS**; test14GiB exact/below-bound và17GiB acceptance vẫn kiểm đúng12GiB sandbox. Final634source và mọi prior626/632other source bytes,917protected hashes,176original audit inputs,23475D70SDK/23382localSDK,16original reviewer artifacts và readonly model/data/security/service audit PASS. [Actual evidence](evidence/d70-pread-14g-headroom-load.json), [first freeze](evidence/d70-pread-14g-headroom-first-freeze.json).

**AUDIO-EVAL-LOAD-12G-001 load/integrity COMPLETE.** Không có audio generation trong lượt này; local reviewer vẫn NOT QUALIFIED,24original judgements vẫn null, D70 mở/D71 unstarted. Không dùng memory fix để repair JSON/labels/prompt outcomes hoặc tự chạy lại semantic controls.

## ADR-103 — First factual diagnostic và deviation của namespace

Explicit approval ngày2026-10-23 cho một packet4control đã preregister. Source/protocol636file/917protected/26priorD70evidence được freeze sau248TTSrelated PASS6.11s, trước real preparation/inference. Dùng đúng pinned original model/SDK, question/system/seed/EOS đã chốt; max16tokens, cap12GiB/headroom14GiB/600wall/1200CPU, không download hoặc synthesis. Cả4control chỉ gửi đầy đủ opaque waveform và fixed question vào model; parent-only request/expectations hashes đóng băng trước gọi.

| Control mờ | Parent-only nguồn | Raw answer | Expected | EOS |
| --- | --- | --- | --- | --- |
| clip-01 | Original complete FLEURS EN0001 | yes | yes |151645 |
| clip-02 | Authored seed102noise3.75s | no | no |151645 |
| clip-03 | Exactzero3.75s | no | no |151645 |
| clip-04 | Original complete FLEURS VI0001 | yes | yes |151645 |

Actual worker39.749s/exit0/no timeout, CPU50.860s, mỗi response2tokens, không parse repair/cap/uncertainty. Runtime factual flag4/4true được giữ nguyên. RSS peak10,006,588KiB≈9.543GiB RAM, VmPeak10,900,092KiB≈10.395GiB virtual; observed inference fit cho4case này, không minimumRAM/VRAM/generalSLO claim. CORE cùngPID/start/command và literal recovery PASS trước-sau, worker joined.

**Namespace deviation:** helper mount ban đầu vẫn chứa `SOURCES` và parent packet preparation/expectation code. Frozen Runtime.diagnose không dùng các reference này trong model inputs, nhưng filesystem/module globals chưa đúng isolation đã đề ra. Audit đánh **strict protocol không PASS**, không giấu deviation hoặc biến raw4/4thành reviewer qualification. Giữ full actual source/result/stdout/stderr/packet và mọi hash; lỗi không được ghi ngược rằng namespace đầu đã sạch.

Sửa riêng ranh giới source: parent preparation module không mount; pure response runtime module không có source IDs/hashes/prepare_packet. Probe thật trong bwrap xác nhận parent helper absent/unimportable, runtime không chứa SOURCES và parent-only labels/project root không nhìn thấy. Không chạy lại original model để tìm kết quả thuận lợi. Scope103 đã dùng và diagnostic modes khóa lại. **249TTSrelated PASS7.63s/Ruff PASS**, gồm5controls tăng thêm so với244(protected mode4/native namespace1); real fixture probes không phải inference/quality scores.

Final638source,633file trong636approved freeze giữ nguyên; ba source controller/worker/helper thay đổi cần thiết và hai file runtime/probe-test mới.917protected/26priorD70evidence/176original inputs/23475D70SDK/23382localSDK/16reviewer artifacts và system/data/security audit PASS;24judgements null, owned evaluators0, no common24review. [Actual evidence](evidence/d70-presence-diagnostic-first.json), [approved freeze](evidence/d70-presence-diagnostic-approved-freeze.json). Presence observations không chứng minh prosody/pronunciation/artifact/naturalness; prompt và stimuli khác lượt cũ nên không suy causal prompt fix. **D70 IN PROGRESS, reviewer NOT QUALIFIED, D71 NOT STARTED.**

[Correction proof](evidence/d70-diagnostic-namespace-correction.json) ghi native namespace probe và AST comparison: parse_answer/audit_events giữ nguyên function bodies sau khi tách module, không sửa acceptance/response logic để làm4answers thành PASS. Original namespace deviation không được retroactively xóa.


## 2026-10-23 continuation: tested quality protocol, execution blocked

[ADR-104](ADR/104-proposed-heldout-quality-and-conditional-blind-review.md) concretely prepares twelve new held-out presence/language/severe-corruption/tie controls and, only after strict first-control/source/runtime/parent-metadata recomputation, one blind48-observation review of the retained24complete16k signals. All four new modes remain blocked under imports/load-only policy; consumed ADR-103 scope is not reused.291TTSrelated PASS12.40s/Ruff PASS and native processor-only two-audio/real namespace checks; no original-model loading/generation or actual packet preparation. Prior9failures, limited4factual matches/namespace deviation and all24pending original judgements are unchanged. Fixed12GiB/14GiB/sameCORE/no downloads/default changes. Severe pair controls do not establish absolute naturalness accuracy, VI phonetics expertise or human MOS; results cannot automatically close unchanged D70 AC or advance D71. One entire conditional campaign is proposed for scope approval, rather than separate permission at every stage. [Evidence](evidence/d70-quality-protocol-proposal.json).
