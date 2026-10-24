# D90 — Gói bàn giao để duyệt và kiểm thử sau

**Mục đích:** Chỉ ra bản code đầy đủ, bằng chứng và cách mở phần nghe; đây là engineering candidate, chưa phải releasev1.0.

Gói file: `ai/data/backups/local-assistant-d70-d90-20261023-full-files.zip`. `FILES_MANIFEST.json` bên trong ghi chính xác commit snapshot/base, toàn bộ file Git đã thay đổi ở dạng đầy đủ và hash từng file. Receipt ngoài ZIP tại cùng thư mục, tên `.receipt.json`, ghi SHA256/CRC và kết quả đối chiếu byte với Git. Mở gói ở thư mục riêng để review; đây là payload source/evidence, không tự cài đặt hay triển khai.

Các artifact bổ sung gồm log full regression đã che credential, nguồn/test của auditor, các receipt và trang nghe native. Database dump, auth/signing keys, Vault secrets, model weights, SDK/cache/venv vẫn ở vùng dữ liệu riêng của workspace; source package không cần chúng để đọc review. Các đầu vào benchmark lớn và raw results lịch sử vẫn ở vị trí cũ, không bị thay thế.

Để nghe sau, mở riêng `ai/data/backups/d89-native-tts-listening/index.html` trong gói hoặc [file đang có](../data/backups/d89-native-tts-listening/index.html). Đủ24WAV gốc đã nhúng; không cần key/server/mạng. Xem [hướng dẫn](D70_MANUAL_LISTENING_TEST.md), [phiếu chưa điền](D70_MANUAL_LISTENING_RESULTS.pending.md), [nghiệm thu workflow](D89_MANUAL_ACCEPTANCE_CHECKLIST.md).

Kết quả phần mềm:5405PASS/0FAIL/0SKIP,707source files giữ nguyên;9auditor controls riêng không cộng vào5405. Audit ghi rõ updated_at quota là delta vận hành duy nhất,11bảng khác/quyền khớp; không sửa timestamp để giả equality. Phần nghe vẫn0/24, physical mic/voice-model-license/product/D14quality và quyết định release chưa hoàn tất. [Trạng thái cần duyệt](RELEASE_CANDIDATE_STATUS.md). Không tag/push/deploy hoặc đổi model/default.

## Bản bổ sung D81 excerpt guard

Gói `ai/data/backups/local-assistant-d81-excerpt-20261023-full-files.zip` chứa **bản đầy đủ của từng file thay đổi** kể từ `bce04bd`, cùng hai log kiểm thử và manifest commit/hash. Receipt `.receipt.json` bên cạnh ghi kết quả kiểm tra Git-byte/CRC/SHA thực tế. Gói D70–D90 trước giữ nguyên; gói bổ sung không thay thế lịch sử hay chứa secret/model/database dump.

[Guard mới](D81_STRICT_EXCERPT_GUARD.md):66tests mới trong227related PASS/0FAIL/0SKIP/1.56s, Ruff PASS. 5405full là kết quả snapshot D87 trước phần bổ sung, không được cộng các lượt chạy thành một full-suite mới. Guard chặn phản hồi sai định dạng và giữ nguyên điểm D81 cũ; chưa bật route, đổi template/model hoặc đóng nghiệm thu sản phẩm.


## Bản tích lũy 2026-10-24

Gói mới `ai/data/backups/local-assistant-d70-d90-20261024-full-files.zip` là bản đầy đủ các file Git thay đổi từ commit7fa4756 đến commit được ghi trong manifest, kèm bằng chứng được chọn rõ ràng. Dùng bản này để review trạng thái mới nhất; hai ZIP20261023 vẫn giữ nguyên lịch sử. Receipt `.receipt.json` được tạo sau ZIP, ghi commit, SHA256, CRC, số file và đối chiếu từng byte với Git/artifact. Không cộng kết quả các lượt test thành một full suite.

Bao gồm source/test đầy đủ của adapter/evaluator, từng phiên bản nguồn đã chạy, raw request/response trung tính và log FAIL/PASS, kiểm thử/auditor/snapshot/reference-smoke, log/metadata/source-freeze của các full suite và trang nghe24WAV gốc. Không lấy cả thư mục scenario: checkpoint chứa signing key được loại trừ hoàn toàn, cùng mọi secret, database dump, weights, SDK/cache/venv.11kiểm thử riêng xác nhận allowlist, chống traversal/symlink/file quá lớn, từ chối bundle cũ bị sửa và loại trừ checkpoint; không thuộc5596tests ứng dụng.

D81workflow gốc đã PASS sau sửa compiler, mọi FAIL trước giữ nguyên. Full mới nhất5596PASS/0FAIL/0ERROR/0SKIP/1760.86s bao gồm phần structured,719files giữ nguyên; [terminal receipt và audit đã hoàn tất](evidence/d90-structured-full-acceptance.json). Snapshot5507PASS trước đó vẫn giữ riêng. Phần nghe vẫn0/24; hướng dẫn/phiếu thiết bị và model/voice/license/product/quality/release vẫn chờ nghiệm thu thực tế. Gói source/evidence không tự triển khai hoặc phê duyệt model.

## Bản tích lũy sau CODE-EVAL-002

Gói mới nhất `ai/data/backups/local-assistant-ce002-20261024-full-files.zip` chứa bản đầy đủ mọi file Git thay đổi từ7fa4756đến commit ghi trong manifest, toàn bộ437artifact đã kiểm tra của gói trước và bằng chứng CODE-EVAL-002 được chọn theo path/hash. Receipt `.receipt.json` bên cạnh ghi SHA256/CRC, số file và đối chiếu byte thực tế; các gói cũ giữ nguyên.

Kèm corpus12ca mới, source/test đầy đủ, raw request/first reply của24lượt, mọi lỗi, oracle native trước inference, regression, audit và nguồn/test của operator. Chỉ đi theo artifact pointer có SHA đúng trong namespace oracle/case của campaign; không diễn giải code/JSON trong chuỗi model và không lấy thư mục scenario/checkpoint.10tests riêng kiểm tra việc chọn pointer/loại signing key, tách khỏi5596full và116related.

Kết quả mới là **đo đủ24lượt, cả hai nhánh sửa đúng7/12**, không phải24/24sửa đúng. Hint không được áp dụng mặc định.116relatedPASS/0FAIL/0SKIP, audit đạt;723file giữ nguyên, trong đó toàn bộ719file của full5596trước vẫn khớp. Các tiêu đề D70đã đối chiếu ADR111để lịch sử “D71NOTSTARTED” không bị hiểu là trạng thái hiện tại. Không thêm nhãn nghe, đổi model hoặc phê duyệt release.


## Bản tích lũy CODE-EVAL-003 đang chuẩn bị

Gói dự kiến `ai/data/backups/local-assistant-ce003-20261024-full-files.zip`, receipt `.receipt.json` cùng thư mục. Chỉ tạo sau full5674kết thúc, audit và commit tài liệu; hiện chưa có receipt PASS của gói này. Bao gồm bản đầy đủ file Git thay đổi từ7fa4756, toàn bộ812artifact của gói CE002đã ghim SHA, source/test feedback, corpus mới,7raw first replies, native/CLI evidence, log lỗi/đã sửa, full log/freeze, auditor/operator/test và24WAV cũ. Không chứa scenario/checkpoint/signing key/secret/database dump/weights.

Một full regression có thể cập nhật12pointer `ce002-oracle-latest` trong workspace. Gói mới phải giữ **đúng byte snapshot trong ZIP CE002đã ghim**, không thay kết quả đầu bằng oracle mới; manifest ghi riêng SHA archive và SHA workspace nếu các pointer này khác. Mọi artifact lịch sử còn lại vẫn phải khớp cả filesystem/ZIP/SHA.28tests riêng kiểm tra pointer/allowlist/traversal/private-path và quy tắc bảo tồn này; không cộng vào5674tests ứng dụng.

[Scorecard CE003](CODE_EVAL_003_FIRST_SCORECARD.md):first4/6,eventual4/6,không có cải thiện được chứng minh; chỉ component tùy chọn, chưa bật route/default. [Smoke production-only](evidence/ce003-reference-smoke.json) đã PASS mà không socket/model/database. Phần nghe vẫn0/24và chưa có phê duyệt release.
