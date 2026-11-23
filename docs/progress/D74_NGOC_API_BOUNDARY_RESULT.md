# D74 — Ngọc Huyền: thử nhóm API theo dictionary

**Mục đích:** Kiểm tra một giả thuyết tối thiểu sau khi chủ dự án mô tả API nghe thành “E - Pe-I, A - Pe - I”. [Phản hồi nguyên văn](../evidence/d74-ngoc-api-exact-owner-feedback.json), [ADR163](../ADR/163-ngoc-huyen-api-dictionary-boundary-trial.md).

**Trạng thái: CHỦ DỰ ÁN BÁO CẢI THIỆN NHƯNG API VẪN SAI; DỪNG TINH CHỈNH.** [Phản hồi nguyên văn](../evidence/d74-ngoc-api-owner-stop.json) chốt dừng phần này. Giữ lỗi và mọi bản audio, không coi candidate đã sửa thành công hoặc tự áp dụng mặc định. Trúc Ly giữ đúng bản accepted-with-limitations, vòng tinh chỉnh đã dừng.

## Nghe đối chiếu

[Trang hai clip: bản cũ và bản thử](../../data/backups/d74-vi-approved-campaign-20261103/ngoc-api-boundary-first/review/index.html).

Cùng câu: “Bạn có thể gọi API bằng Python trên server này không?”. Bản cũ là WAV Ngọc Huyền nguyên gốc từ bộ 10 câu, không sinh lại. Bản thử mới đặt bên dưới, được nhúng nguyên WAV; trang không có JavaScript, microphone, upload, network hay autoplay.

Các clip giữ để đối chiếu; không yêu cầu nghe hoặc tạo thêm clip trong vòng này. Chủ dự án nhận xét tổng thể tốt hơn nhưng chưa đúng, không cung cấp điểm riêng về Python/server, rè/run, nhịp hoặc identity. Không tự bổ sung các nhãn đó.

## Căn cứ và thay đổi duy nhất

Pinned G2P SDK có dictionary API `ˌeɪpˌiːˈaɪ`, trong khi bản stress hiện có dùng `ˌeɪ pˌiː ˈaɪ`. Chỉ bỏ hai khoảng trắng nội bộ API để thử cách nhóm acronym; nguyên âm/phụ âm/trọng âm giữ nguyên. Không viết phiên âm Việt phỏng đoán, đổi lexicon, tách/ghép audio sửa lỗi, reference-off, thêm ngữ cảnh, đổi model/preset/SDK hoặc train. Đây là giả thuyết về cách nhóm, không phải bằng chứng nguyên nhân sâu của lỗi.

Probe không nạp weights xác minh lại đúng native dictionary, actual original chunk phones, hai token roundtrip chính xác/0unknown và cap. Câu này giữ cùng cap172 của baseline mặc dù original US cap trước là176; compact original cap172. Không tăng hoặc đổi allowance thực tế. Câu ngày giờ/API không nằm trong lượt này vì khoảng trắng có thể làm cap thấp hơn baseline đã lưu; không lén so sánh ngân sách khác nhau. Slot Ngọc Huyền compact API standalone của cohort cũ vẫn UNATTEMPTED sau lỗi standalone A; đây là full-sentence clause-path khác, không retry/hoàn thành lại cohort cũ hoặc phục hồi bộ carrier đã bị chê.

Giữ source/rendered text, chunk/gap/question, Python/server targets, speaker/reference-code hashes, sampling/seed và original joining. Runtime gốc reset NumPy seed7 trước mỗi request turbo. Actual binding mới khớp baseline Ngọc Huyền. Same intended phones/reference hashes không chứng nhận cách phát âm hoặc perceived identity.

## Kết quả và kiểm thử

1 request TTS mới/1 inner chunk/EOS hoàn chỉnh, 0retry/0chưa gọi; cộng 1 baseline cũ tạo2observation/2player. 9row khác trong packet chỉ là metadata để dùng semantic validator cũ, không phải request dự kiến hoặc chưa gọi. Admission khóa đúng mixed-api/Ngọc Huyền/text và từ chối mọi row khác/lặp request. Waveform mới khác cũ; không dùng khác biệt waveform làm điểm chất lượng.

Thêm2module/1test riêng, không sửa43research cũ/750application/210protected.11test mới PASS0,32s; final328related PASS/0FAIL/ERROR/SKIP5,45s, Ruff E4,E7,E9,F/format và descriptions PASS trước sourcefreeze. Tests kiểm exact two-space-only edits, samecap/refusal, source/probe/packet binding, original speaker/reference/sampling/nativewave/join, one-case-only admission, model-free namespace, pairmedia/missingcandidate, consumed-root replay, firsterror/cancellation/join. Full5889/750 là snapshot lịch sử, không phải full regression mới.

Một worker exit0/joined, baseline dịch vụ/native phục hồi; wall3,167s/peak sampledRSS RAM1296,8MiB/TTS-only1,109s. Giữ CPU0,1/hai threads/AS8GiB/RSS2GiB/aggregate8GiB/headroom14GiB/root8GiB, wall mới60s, khôngGPU. Không ASR/CORE/Brave/download/service/config/model/Vault/database/Docker action. Chưa đo physical first-audible4seconds.

[Actual receipt](../evidence/d74-ngoc-api-boundary-result.json), [verification](../evidence/d74-ngoc-api-boundary-verification.json), [full version ba file code/test](../../data/backups/d74-vi-approved-campaign-20261103/ngoc-api-boundary-first/review/full-code.zip). Audit bind actual request/event/native/chunk, only-two-spaces/equalcap/voicehashes, nguyênWAV cũ/mới, codefreeze/snapshots/ZIP/terminal/authority và4295SDKentries. Không nhãn nghe giả, không tự chọn bản thử làm mặc định.

VOICE-ENGLISH-READING-001/VOICE-API-ARTIFACT-001 P1: cặp đối chiếu đã nhận phản hồi cải thiện nhưng chưa đạt, dừng tinh chỉnh theo chủ dự án. [Bước tiếp theo](D74_NEXT_WORKFLOW_VALIDATION.md) là chuẩn bị kiểm thử luồng và độ trễ D74; không tự xếp lượt tuning tiếp. Ngọc Huyền baseline API rejection/English I→i cũ và Trúc Ly acceptance/refinement stop giữ nguyên. ADR15548workflow chưa duyệt/chưa chạy; D60deferred, physical4second/rights/no-speech/product/D90release còn mở.
