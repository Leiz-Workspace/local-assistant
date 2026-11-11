# D74 — Bước tiếp theo sau khi dừng tinh chỉnh phát âm


**Current next work — 2026-11-05:** [Reviewable main integration campaign](D74_VOICE_INTEGRATION_REVIEW.md) now defines B1 identity/UI/contracts, B2 exact adapters/shared residency/borrowed CORE and one conditional B3 six-input panel. Owner approval is pending; no code or campaign has run under [ADR174](../ADR/174-proposed-opt-in-authenticated-voice-integration.md). Existing trial/results and stopped pronunciation cycles remain unchanged. Physical first-audible and product/default decisions remain separate.
**Mục đích:** Xếp công việc kế tiếp theo kết quả thật, sau khi chủ dự án dừng vòng sửa Ngọc Huyền. Phần chuẩn bị và một lượt native reading-aware đã hoàn tất theo ADR165; tài liệu này ghi kết quả và việc còn lại, không tự cho phép lượt chạy mới hoặc thay lựa chọn model.

## Trang thử voice đã chạy — 2026-11-05

**URL trên cùng máy: [http://127.0.0.1:8092](http://127.0.0.1:8092)**. [Cách mở/ghi/dừng/gửi/nghe và kiểm chứng](D74_VOICE_BROWSER_TRIAL_GUIDE.md), [kết quả và receipt](D74_VOICE_BROWSER_TRIAL_RESULT.md). Thêm optional loopback research surface riêng; recorder cũ/750application baseline giữ nguyên, không chọn model/default sản phẩm. Prepare chủ động, không tự thu/nạp/gửi khi mở trang; đúng QwenCUDAFP32/CORE32KFast512/TrúcLyCPU8 đã qualified.

766relatedPythonPASS/20JSPASS, Braveheadless fake-mic/muted/mocked-model UI PASS; browser thật không mock GET/POSTcookie/Origin cũng PASS, không mở microphone. RealHTTPnative6/6:4speech ASR/CORE/playback exactprior, clientroundtrip1.972–3.250s và2negative chặn đúng;6VAD/4ASR/CORE/TTS+1readiness,0retry/guard/runtimefault, toàn bộmodel thu hồi. Lượt Prepare43.843s riêng trướcGửi; không gộp thành cold4secondPASS. Giữ firstCSPfixturefailure/oldresults, không nới policy/model/cap hoặc tải thêm.

**P1 còn lại: chủ dự án kiểm chứng actualmic→Brave→loa/physical4seconds qua URL có thật**, không coi marker “Chuẩn bị phát” là tiếng loa. Web service riêng đangchạy/loopback/4giờ; groupmodel8phút,24attempts/3prepares perwebprocess, RAM-only turnfiles/ephemeral browserresults. Phạm vi userdevice/voice/model/rights/default/product/D74/D90release vẫnOPEN; D60deferred, pronunciationcycles dừng. Full5889là lịch sử, không rerun hoặc tự đóng ngày/gate còn thiếu.

## Checkpoint buffered compute trước trang thử — 2026-11-05

[ADR170–172 / kết quả độ trễ thật](D74_RESIDENT_CUDA_LATENCY_RESULT.md): **LOCAL_BUFFERED_COMPUTE_PASS**, Qwen cùng checkpoint chạy CUDA FP32/eager + CORE32K/Fast512 + Trúc Ly CPU8 đã ready.4/4speech có audio hoàn chỉnh trong2,000–3,334giây;2/2negative chặn trước ASR/CORE/TTS.40/40transcript VI/EN trùng CPU;8native transcript/CORE/audio ở hai lượt PASS trùng byte với CPU8.690relatedPASS/98controls mới; full5889 là lịch sử, không chạy lại.

Sáu nhóm CPU2/4/8 vẫn FAIL maximum4seconds. WhisperCUDA FAIL VI CER253/1984vs248/1984, không chạy native. Lượt CUDA đầu dừng vì mount nhầm bản detector; hash chặn trước inference, giữ nguyên kết quả/code đầu. Bản sửa source-binding đạt6/6 (max3,543s); đã sửa thêm disk-budget polling trỏ nhầm root cũ và xác nhận riêng6/6 (max3,334s), root/guard hiện tại đúng. Giữ cả hai lượt PASS và phiên bản đã chạy; không retry chất lượng, relabel hoặc che lỗi. Chỉ thêm SDK CUDA cô lập, không tải weights/thay model/default/voice/app/config hoặc dịch vụ dùng chung.750application/210protected/14ASRartifacts và runtime cũ giữ nguyên.

**VOICE-LATENCY-AC-001 còn OPEN cho first-audible vật lý:** complete PCM chỉ là gate xử lý cục bộ, không phải tiếng từ loa trong4giây. App recorder chưa nối research runner này. P1 tiếp theo: contract/kiểm thử rồi endpoint nghiên cứu có xác thực và browser playback/đo thực trên Brave/PC; dependency gate hiện tại/explicit-submit/ready/cancel/retention, effort một milestone contract/control+tích hợp cô lập+lượt thiết bị, rủi ro khoảng dư<0,67giây/mạng/autoplay/co-memory/cold-start/cleanup. Chưa yêu cầu owner test một URL workflow chưa có. Model/voice/rights/default/product và D74/D90release vẫn OPEN; D60deferred, pronunciation cycles dừng.

## Trạng thái đã chốt

[Phản hồi mới](../evidence/d74-ngoc-api-owner-stop.json): API Ngọc Huyền tốt hơn nhưng vẫn đọc sai; dừng tinh chỉnh phần này. Không coi candidate ADR163 là bản sửa thành công hoặc tự đưa vào sản phẩm. Giữ mọi audio/input/kết quả. Trúc Ly đã đủ ổn trong phạm vi được nghe, có hạn chế phụ âm cuối tiếng Anh; vòng tinh chỉnh cũng đã dừng. Chưa chốt model/voice/default triển khai.

D74 vẫn OPEN. Microphone Brave/PC capture/playback smoke đã được chủ dự án xác nhận trong phạm vi ghi nhận; chưa phải recorder→ASR→CORE→TTS sản phẩm. Các số TTS riêng không chứng minh chờ tối đa4giây.

## Bước1 đã thực hiện — 2026-11-04

[Reading bridge và kiểm thử](D74_WORKFLOW_READING_BRIDGE_RESULT.md) đã có386relatedPASS,20/20model-free frontend cases và10oldcontrol parity. Giữ nguyên source/product model/default. [ADR165native48case](D74_NATIVE_READING_WORKFLOW_RESULT.md) sau đó đã được owner yêu cầu chạy: đủ48observations,32speechcomplete/16negativefail, buffered target chưa đạt. First-audible trên thiết bị chưa đo; không chạy nhầm ADR155raw cũ.

## Kế hoạch đã thực hiện và phần thiết bị còn lại

**VOICE-LATENCY-AC-001 / D74 workflow recovery — P1.** Các bước 1–3 dưới đây đã có kết quả ADR164/165; bước 4 và các gate chất lượng vẫn mở. Ngừng các lượt thử phát âm bổ sung.

1. Rà soát caller đã sửa, packet/corpus và chính sách đọc đã được chấp nhận. [ADR155](../ADR/155-proposed-workflow-recovery-after-caller-metadata-failure.md) khóa kế hoạch2ASR×2TTS×2trạng thái×6nguồn=48slot, lane Turbo Trúc Ly gốc và Piper VI control. Nó chưa mô tả việc ghép toàn bộ renderer/US-term/API nghiên cứu mới vào phản hồi CORE tùy ý. Không âm thầm chạy bản gốc rồi gọi đó là bản đọc đã được nghe; không mở whitelist của các study đã đóng băng. Cần xác định adapter/lifecycle nào đã có và khoảng trống tích hợp, thêm test hoặc ADR riêng nếu thay cách kết hợp.
2. Chuẩn bị bản kế hoạch cụ thể cho caller/renderer đã kiểm thử, nguồn/phạm vi, request/resource limits và rollback; giữ nguyên các model/lane đã thỏa thuận. Trúc Ly chỉ là lane nghiên cứu sẵn trong kế hoạch cũ, không phải lựa chọn sản phẩm mới; Ngọc Huyền có thể giữ pending tùy chọn, không kéo theo vòng tuning tiếp. Không tự đổi ASR, streaming, context, cap hoặc GPU để đạt4giây.
3. Sau khi phạm vi native phù hợp được duyệt, chạy đúng lượt hữu hạn đã đóng băng. Giữ riêng6workflow slot cũ software-invalid/42chưa gọi; không gộp score với lượt mới. Ghi số lỗi, transcript, complete native audio, cold/warm, ASR/CORE/TTS stages, RAM và cleanup. Thử silence/noise/missing speech theo corpus đã duyệt; không biến test phần mềm thành chứng nhận không hallucinate.
4. Phép đo CLI submission→complete PCM là proxy kỹ thuật. Phải nối endpoint/auth/retention và playback phù hợp trước khi xác nhận submission→first-audible trên Brave/PC≤4giây. Kiểm Stop/Hủy trong luồng thật và giữ bộ microphone smoke đã PASS. Không đánh PASS4giây từ TTS-only hoặc từ PCM có sẵn.

## Bước3 đã đo thật — 2026-11-04

Owner tiếp tục “Chay để xác nhận đi” cho cohort reading-aware riêng ADR165; không suy phê duyệt từ nhận xét nghe trước đó. Đã chạy48/48,0retry/0guardfailure; [số đo và lỗi thực tế](D74_NATIVE_READING_WORKFLOW_RESULT.md). Kế tiếp ưu tiên false speech/no-speech và profileASR/TTS theo dữ liệu trước product; không tự bật VAD cũ hoặc thay model. Target4giây và thiết bị vẫn chưa đạt/chưa xác minh đúng phạm vi.

## Dependency, effort, rủi ro và giới hạn hiện tại

Dependency chuẩn bị, adapter, tests và lượt đo native hữu hạn đã được đáp ứng theo ADR164/165. Việc tiếp theo là thiết kế guard no-speech và profile ASR/TTS, mỗi phần cần controls và phạm vi đo riêng; sau đó đo thiết bị khi có luồng sản phẩm phù hợp. Effort và rủi ro được đánh giá trong báo cáo ADR165; chưa tự xếp một lượt native tiếp theo.

Rủi ro có căn cứ: bản benchmark gốc chưa chứa reading policy mới, các study giới hạn câu/preset, ASR đã có độ trễ và hallucination trên negative, PCM không đồng nghĩa đã phát tiếng, co-residency/cancel/cleanup và nhầm chất lượng nghiên cứu với sản phẩm. Giữ immutable first outcomes, finite budgets và rollback dừng/join riêng workers, xác minh baseline/source; không chạm shared services/weights/Vault/database.

ADR155 yêu cầu **“Request one new explicit approval for one replacement48-slot workflow campaign only.”** Chủ dự án trước đó chọn “Chờ nghe24clip”; các nhận xét nghe và yêu cầu dừng tinh chỉnh không tự phê duyệt48lượt native. Yêu cầu mới “Chay để xác nhận đi” sau đó đã cho phép cohort ADR165 riêng và cohort đó đã đo xong; entry point, kế hoạch và hash ADR155 cũ giữ nguyên.

D60 tiếp tục deferred theo chủ dự án. Rights/model/default/product/D90release và4giây thật còn mở; không chuyển ngày hoặc ghi hoàn tất chỉ vì dừng tinh chỉnh phát âm.


## D74 whole-clip presence follow-up — 2026-11-04

[ADR166 prototype and actual results](D74_WHOLE_CLIP_PRESENCE_RESULT.md): the optional research gate admits the identical full PCM/clock when original Silero v5 finds speech, otherwise the original pipeline refuses before downstream ASR/CORE/TTS. Existing application/models/thresholds/defaults stay unchanged; no concatenation or product activation. 524 related PASS/0FAIL/ERROR/SKIP in 6.47s, including 61 new controls.

100 actual VAD observations / 7 clean workers cover 40 unique original VI/EN speech recordings (40 admitted), 2 padded repeats (2 admitted), 5 authored negatives (5 refused) and 6 derived quiet controls (4 admitted, 2 EN refused). The panel is reused, quiet controls have inherited coarse labels and downstream calls are explicit software sentinels, not native ASR/CORE/TTS. Six original D74 ASR input hashes match; 1903 prior code/evidence files plus the 750-application/210-protected baseline and native/container state remain preserved. Original ADR165 16/16 erroneous negative replies and latency failures are not overwritten; no max4second/device/product PASS.

AUDIO-VAD-ASR-002 P1 is assessed as the next research candidate: detector-only amplitude-normalized view while ASR keeps original PCM, with separately fixed bilingual/quiet/negative controls, source/view provenance, one design/control and bounded comparison milestone. Risks are noise/DC/clipping amplification and overfit; no algorithm/gain/model switch, new measurement or activation is chosen here. Short/quiet-word sensitivity, native full-workflow integration, physical timing/rights/default/product/D90release remain OPEN; D60 deferred and both pronunciation cycles stopped.


## D74 local detector/native gate verified — 2026-11-04

[Actual gate result](D74_DETECTOR_PEAK_GATE_RESULT.md): AUDIO-VAD-ASR-002 local detector and native no-speech checks PASS. Fixed detector-only peak0.5 normalization preserves original ASR PCM/clock; original Silero/settings/model/voice/default remain unchanged. Gain32candidate99/100 remains FAIL; v2records147/147correct (80original speech/46quiet derivatives/6padded repeats admitted,15negative rows refused),288actual VAD observations.20utterances are fresh relative to fix selection; inherited quiet labels and repeated signals are not independent acoustic acceptance.

Conditional ADR168native scope is now8/8PASS:4complete speech outputs and4correct early no-speech refusals, exactly4ASR/4CORE/4TTS plus8VADcalls,0retry/guard/runtime failure and restored baseline. This repeats2VI speech/2negative sources across2ASRs; it is not native quiet-ASR/semantic quality or a repaired original48turn score.592relatedPASS/0FAIL/ERROR/SKIP7.67s; all first failures/source snapshots and original750application/210protected/14post-verified ASR artifacts preserved. No model/package download or shared-service/provider/Vault/database/Docker mutation; product gate remains unactivated.

Next assessed P1 VOICE-LATENCY-AC-001: residency/stage profiling with unchanged quality/models/resource guards, one design/control milestone then separately bounded measurement. Dependency: qualified local gate and retained timing/endpoint/playback contracts; risks co-residency RAM, cancellation/TTL and PCM-versus-speaker timing. Current cold buffered speech11.211–17.857s is NOT max4second PASS. Real mic/short/quiet-word/noise/rights/model/default/product and physical timing remain OPEN; D60 deferred, pronunciation cycles stopped, D90 NOT RELEASED.
