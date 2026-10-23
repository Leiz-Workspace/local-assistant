# D90 — Gói bàn giao để duyệt và kiểm thử sau

**Mục đích:** Chỉ ra bản code đầy đủ, bằng chứng và cách mở phần nghe; đây là engineering candidate, chưa phải releasev1.0.

Gói file: `ai/data/backups/local-assistant-d70-d90-20261023-full-files.zip`. `FILES_MANIFEST.json` bên trong ghi chính xác commit snapshot/base, toàn bộ file Git đã thay đổi ở dạng đầy đủ và hash từng file. Receipt ngoài ZIP tại cùng thư mục, tên `.receipt.json`, ghi SHA256/CRC và kết quả đối chiếu byte với Git. Mở gói ở thư mục riêng để review; đây là payload source/evidence, không tự cài đặt hay triển khai.

Các artifact bổ sung gồm log full regression đã che credential, nguồn/test của auditor, các receipt và trang nghe native. Database dump, auth/signing keys, Vault secrets, model weights, SDK/cache/venv vẫn ở vùng dữ liệu riêng của workspace; source package không cần chúng để đọc review. Các đầu vào benchmark lớn và raw results lịch sử vẫn ở vị trí cũ, không bị thay thế.

Để nghe sau, mở riêng `ai/data/backups/d89-native-tts-listening/index.html` trong gói hoặc [file đang có](../data/backups/d89-native-tts-listening/index.html). Đủ24WAV gốc đã nhúng; không cần key/server/mạng. Xem [hướng dẫn](D70_MANUAL_LISTENING_TEST.md), [phiếu chưa điền](D70_MANUAL_LISTENING_RESULTS.pending.md), [nghiệm thu workflow](D89_MANUAL_ACCEPTANCE_CHECKLIST.md).

Kết quả phần mềm:5405PASS/0FAIL/0SKIP,707source files giữ nguyên;9auditor controls riêng không cộng vào5405. Audit ghi rõ updated_at quota là delta vận hành duy nhất,11bảng khác/quyền khớp; không sửa timestamp để giả equality. Phần nghe vẫn0/24, physical mic/voice-model-license/product/D14quality và quyết định release chưa hoàn tất. [Trạng thái cần duyệt](RELEASE_CANDIDATE_STATUS.md). Không tag/push/deploy hoặc đổi model/default.
