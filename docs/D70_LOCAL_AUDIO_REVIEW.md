# D70 — Evaluator audio local được phê duyệt

**Mục đích:** Ghi quyền thử, nguồn model/runtime, protocol và kết quả thực tế của công cụ đánh giá audio bổ sung. Tài liệu này không thay kết quả TTS gốc hoặc tự đóng Acceptance Criteria.

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
