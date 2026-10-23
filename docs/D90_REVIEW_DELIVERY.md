# D90 — Gói bàn giao để duyệt và kiểm thử sau

**Mục đích:** Chỉ ra bản code đầy đủ, bằng chứng và cách mở phần nghe; đây là engineering candidate, chưa phải releasev1.0.

Gói file: `ai/data/backups/local-assistant-d70-d90-20261023-full-files.zip`. `FILES_MANIFEST.json` bên trong ghi chính xác commit snapshot/base, toàn bộ file Git đã thay đổi ở dạng đầy đủ và hash từng file. Receipt ngoài ZIP tại cùng thư mục, tên `.receipt.json`, ghi SHA256/CRC và kết quả đối chiếu byte với Git. Mở gói ở thư mục riêng để review; đây là payload source/evidence, không tự cài đặt hay triển khai.

Các artifact bổ sung gồm log full regression đã che credential, nguồn/test của auditor, các receipt và trang nghe native. Database dump, auth/signing keys, Vault secrets, model weights, SDK/cache/venv vẫn ở vùng dữ liệu riêng của workspace; source package không cần chúng để đọc review. Các đầu vào benchmark lớn và raw results lịch sử vẫn ở vị trí cũ, không bị thay thế.

Để nghe sau, mở riêng `ai/data/backups/d89-native-tts-listening/index.html` trong gói hoặc [file đang có](../data/backups/d89-native-tts-listening/index.html). Đủ24WAV gốc đã nhúng; không cần key/server/mạng. Xem [hướng dẫn](D70_MANUAL_LISTENING_TEST.md), [phiếu chưa điền](D70_MANUAL_LISTENING_RESULTS.pending.md), [nghiệm thu workflow](D89_MANUAL_ACCEPTANCE_CHECKLIST.md).

Kết quả phần mềm:5405PASS/0FAIL/0SKIP,707source files giữ nguyên;9auditor controls riêng không cộng vào5405. Audit ghi rõ updated_at quota là delta vận hành duy nhất,11bảng khác/quyền khớp; không sửa timestamp để giả equality. Phần nghe vẫn0/24, physical mic/voice-model-license/product/D14quality và quyết định release chưa hoàn tất. [Trạng thái cần duyệt](RELEASE_CANDIDATE_STATUS.md). Không tag/push/deploy hoặc đổi model/default.

## Bản bổ sung D81 excerpt guard

Gói `ai/data/backups/local-assistant-d81-excerpt-20261023-full-files.zip` chứa **bản đầy đủ của từng file thay đổi** kể từ `bce04bd`, cùng hai log kiểm thử và manifest commit/hash. Receipt `.receipt.json` bên cạnh ghi kết quả kiểm tra Git-byte/CRC/SHA thực tế. Gói D70–D90 trước giữ nguyên; gói bổ sung không thay thế lịch sử hay chứa secret/model/database dump.

[Guard mới](D81_STRICT_EXCERPT_GUARD.md):66tests mới trong227related PASS/0FAIL/0SKIP/1.56s, Ruff PASS. 5405full là kết quả snapshot D87 trước phần bổ sung, không được cộng các lượt chạy thành một full-suite mới. Guard chặn phản hồi sai định dạng và giữ nguyên điểm D81 cũ; chưa bật route, đổi template/model hoặc đóng nghiệm thu sản phẩm.
