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


## Bản tích lũy CODE-EVAL-003 sau kiểm chứng phần mềm

Gói mới `ai/data/backups/local-assistant-ce003-20261024-full-files.zip`, receipt `.receipt.json` cùng thư mục. ZIP/receipt được tạo sau commit tài liệu từ đúng Git HEAD; chỉ dùng khi receipt xác nhận Git-byte/extra-byte/CRC/SHA đã hoàn tất. Full mới5674PASS/0FAIL/0ERROR/0SKIP1798.59s/728files giữ nguyên, audit hoàn tất: [bằng chứng](evidence/ce003-full-acceptance.json). Bao gồm bản đầy đủ file Git thay đổi từ7fa4756, toàn bộ812artifact của gói CE002đã ghim SHA, source/test feedback, corpus mới,7raw first replies, native/CLI evidence, log lỗi/đã sửa, full log/freeze, auditor/operator/test và24WAV cũ. Không chứa scenario/checkpoint/signing key/secret/database dump/weights.

Một full regression có thể cập nhật12pointer `ce002-oracle-latest` trong workspace. Gói mới phải giữ **đúng byte snapshot trong ZIP CE002đã ghim**, không thay kết quả đầu bằng oracle mới; manifest ghi riêng SHA archive và SHA workspace nếu các pointer này khác. Mọi artifact lịch sử còn lại vẫn phải khớp cả filesystem/ZIP/SHA.28tests riêng kiểm tra pointer/allowlist/traversal/private-path và quy tắc bảo tồn này; không cộng vào5674tests ứng dụng.

[Scorecard CE003](CODE_EVAL_003_FIRST_SCORECARD.md):first4/6,eventual4/6,không có cải thiện được chứng minh; chỉ component tùy chọn, chưa bật route/default. [Smoke production-only](evidence/ce003-reference-smoke.json) đã PASS mà không socket/model/database. Phần nghe vẫn0/24và chưa có phê duyệt release.


## Bản tích lũy MODEL-QUALITY-001

Gói mới `ai/data/backups/local-assistant-mq001-20261024-full-files.zip` và receipt `.receipt.json` được tạo sau commit tài liệu. Manifest giữ bản đầy đủ file Git từ7fa4756đến đúngHEAD, toàn bộ959artifact của gói CE003đã ghimSHA và source/test/operator/log lỗi/lượt đo30request-reply/bằng chứng audit mới.12CE002latest-index vẫn lấy đúng byte lịch sử từ archive, ghi riêngSHAworkspace nếu khác.28kiểm thử policy PASS; build kiểm tra từngGit/extra byte/CRC/finalSHA. Không chứa secret/signingkey/checkpoint/scenario/database dump/weights hoặc triển khai tự động.

[Điểm baseline mới](MODEL_QUALITY_001_CORE_TEXT_SCORECARD.md)23/30,52.5of70text points; không biến thành điểm100hay đóngD14. Full5674vẫn đúng snapshot728applicationfiles giữ nguyên;59privateoperator controls/19audit-policy/28delivery-policy là các scope riêng. Các gói cũ và24WAV nghe sau giữ nguyên; nghe thực tế0/24/model/voice/license/device/product/release vẫn mở.

## Bản tích lũy sau UNRESTRICTED và xử lý web

Gói mới `ai/data/backups/local-assistant-unrestricted-web-20261024-full-files.zip` cùng receipt `.receipt.json` sẽ được tạo và xác minh sau commit cuối. Giữ toàn bộ1.073artifact trung tính của gói MQ001đã ghim SHA, mọi bản đầy đủ file Git thay đổi từ7fa4756đếnHEAD và source/test/operator/log lỗi/lượt đo30native UNRESTRICTED, audit cuối, các lượt Brave/linked-source. Giữ12CE002latest-pointer bằng byte archive cũ, ghi riêng SHAworkspace; các artifact cũ khác phải khớp filesystem. Bản trước không bị ghi đè.

Allowlist mới chỉ lấy request/reply/native bytes/measurement đã định danh, metadata hữu hạn, source/test/log của operator và báo cáo Markdown/DOCX/PDF/ba ảnh QA. Loại toàn bộ session store/checkpoint/signing key, HTML đầy đủ của publisher, secret/database dump/weights/SDK/cache/venv. Metadata lưu SHA của HTML và anchor thực sự; không gọi child là kết quả tìm kiếm trực tiếp. Những file private bị loại vẫn ở nguyên workspace, không phải đã xóa hoặc không tồn tại.39kiểm thử policy gói PASS, bao gồm chặn rawHTML/store/traversal/unrelated/weights; build phải đối chiếu từng Git/extra byte/CRC/SHA trước khi phát receipt.

Bộ kiểm thử riêng cuối192PASS/0FAIL/0SKIP/2.33s;104authorityrelatedPASS/1.27s là scope khác. Không cộng chúng vào5.674tests của snapshot728files không đổi. Ruff E9/F/I đạt với đúng hai I001import-order ngoại lệ cho hai operator đã freeze/chạy; log lint ban đầu được giữ, không sửa byte nguồn đã dùng chỉ để làm đẹp lint. Không có bỏ qua lỗi thực thi E9/F.

[UNRESTRICTED20/30so với CORE23/30](MODEL_QUALITY_002_UNRESTRICTED_SCORECARD.md), [web variant và lỗi gốc](WEB_SEARCH_003_CURRENT_CHECK.md), [những gate còn lại](OUTSTANDING_WORK_STATUS.md). Gói review không phải bản release, thay model hoặc quyền deploy; D70nghe thực tế vẫn0/24.

## Bản tích lũy hoàn tất đo D14 — 2026-10-26

Gói mới `ai/data/backups/local-assistant-d14-20261026-v2-full-files.zip` và receipt `.receipt.json` được tạo sau commit kết quả. Giữ toàn bộ1.327artifact của gói UNRESTRICTED/web đã ghimSHA, mọi fileGit thay đổi đầy đủ từ7fa4756đếnHEAD và bằng chứng D14được chọn theo allowlist:5PNGtrung tính, request/nativebytes/measurement, cancel/ready/launch/resource log, frozenprotocol, kết quả đầu/controllerINCOMPLETEvà suffixUNRESTRICTEDchưa từng chạy, source/testoperatorđã thực thi và báo cáo kiểm chứng. Không chứa model weights/projector/cache/SDK/database dump/secret/checkpoint hoặc dữ liệu hội thoại.

17deliverycontrolsPASS; build kiểm chứng từngGit/extra byte/CRC/SHA, giữ12pointerCE002bằng byte archivecũ và SHAworkspace riêng. Dòng IDEdo người dùng thêm ở đầu devlog được giữ nguyên trong worktree, không commit/đưa vào ZIP: allowlist chỉ chấp nhận đúng prefixSHAđã quan sát và phần còn lại phải khớp GitHEAD, mọi delta khác bị chặn. Không tự xóa/chỉnh dòng người dùng để làm Gitclean. Receipt ghi rõ ngoại lệ worktree này mà không ghi nội dung dòng đó.

[D14scorecard](D14_COMPLETION_SCORECARD.md):42modelquestions+5provenancechecks/profile, originalweights đủ100, compositecục bộCORE66.5/UNRESTRICTED52; strictformatqualityvẫnNOTQUALIFIED. 26generationmới gồm2cancel, không chạy lạiCORE/câu đã chấm. 271scopedtestsPASS/0FAIL/0SKIP/1.23s, RuffPASS/76function-classdescriptions; snapshotứng dụng728files/full5674lịch sử không đổi, không cộng scopedcount vào full. Không triển khai, thay model hoặc phê duyệt release.

Delivery correction: gói D14đầu đã cuốn cả builderlogđang ghi, nên sau dòng receipt thì logworkspacekhác snapshot trong ZIP. Giữ nguyên gói/receipt/source/log đầu; dùng bảnv2loại hai builder-outputlog khỏi allowlist, thêm2negativecontrols. Không thay kết quả model/code ứng dụng hoặc tái chạy inference. Bảnv2là gói cần dùng; chỉ phát khi đối chiếu byte hiện tại sau khi buildđã kết thúc đạt.

## Bản tích lũy sửa JSON và quality gate — 2026-10-26

Gói mới `ai/data/backups/local-assistant-d14-quality-gate-20261026-full-files.zip` và receipt `.receipt.json` được tạo sau commit kết quả. Giữ toàn bộ1.453artifact của gói D14v2đã ghimSHA, fullGitfileversions từ7fa4756đếnHEAD, adapter/test mới, bộ42câu/profile/schema cấu trúc,5PNGmới,84firstrequest/nativewire,2cancel,3freshstreamcompatibility, nguồn đã chạy/log lỗi/controllerpartial/suffix và replayreport. Source/test của helper/privateevidence được chọn rõ, không lấy cảstore hay thư mục riêng khác.

11deliverycontrolsPASS: chặn traversal/unknownmetadata/secret/modeldump/activebuilderlog, kiểm tra đúng priorZIP/receipt. Build phải đối chiếu từngGit/extra byte/CRC/SHA;12CE002latestpointer giữ byte archivecũ. Không chứa weights/projector/cache/SDK/database dump/.env/checkpoint/signingkey. DòngIDEcủangườidùngởđầudevlog vẫn ngoàiGit/ZIP; kiểm tra exactprefixSHA vàcommittedbody, không tự xóa hoặc commit thay người dùng. Builderoutput đặt ngoài namespaceinput để không tự cuốn logđangghi; xác minh lại byte sau khi processkết thúc.

[Actual gate](D14_STRUCTURED_QUALITY_GATE_RESULT.md): **formatfixVERIFIED, functionalqualityFAIL**. Giữ firstCORE39format/28functional; correctedwire42/31; UNRESTRICTEDfirst42/30;3freshCOREstream3/3. Không nâng điểm cũ hoặc đổi đápán/schemađể làmPASS.394scopedPASS/RuffPASS, không cộng vào5674full lịch sử. Current730files=728unchanged+2additive; không new730full/release/model/default/productionactivationclaim.


## Bản sửa ba lỗi review D14 — 2026-10-26

Gói mới `ai/data/backups/local-assistant-d14-review-fixes-20261026-full-files.zip` và receipt `.receipt.json` cùng thư mục chứa full file Git từ7fa4756đến commit ghi trong manifest, giữ1.769artifact của gói quality trước và evidence/operator/test mới được chọn rõ. Builder output nằm ngoài allowlist để tránh tự lấy log đang ghi. Đối chiếu lại Git/extra byte/CRC/SHA sau khi builder kết thúc; dòng IDE riêng của người dùng vẫn ngoài Git/ZIP.

[Ba lỗi review đã sửa](D14_REVIEW_FIXES.md), 418scoped PASS/0SKIP, trong đó14deliverycontrols. Không có model call mới; original first report/freeze/scores giữ nguyên, quality vẫn FAIL. Verifier lịch sử cần giữ ZIP quality cũ có SHA1f2b7d9197a56488b7e7ae9ce1543a43b6817f54a57b4a0aafcd4471046ce463bên cạnh tại path gốc; ZIP mới không nhúng đệ quy ZIP cũ. Gói không chứa weights/secret/dump/SDK/cache, không chứng nhận full730 mới hoặc release.


## Bản đầy đủ sau khắc phục semantic D14 — 2026-10-26

Gói `ai/data/backups/local-assistant-d14-semantic-20261026-full-files.zip`, receipt `.receipt.json` cùng thư mục, được tạo từ GitHEAD sau commit kết quả. Giữ1.789extras trước đã pinSHAf48babaf43af5507ed717c8bc00ae46b2dc312590fe34c3e03d1f34e1ffda1ef, completeGitfileversions từ7fa4756 và toàn bộ firststudy artifacts/source snapshots/PNG/vocabulary recounts đã chọn rõ. Manifest tính246modelgenerations trên4study, kể cả invalidfirstcaller; không ẩn lỗi đầu. Builderoutput ngoàiallowlist, đối chiếu lại từngGit/extra byte/CRC/SHA sau khi process kết thúc. DòngIDEriêng đầu devlog vẫn ngoàiGit/ZIP.

[Selected local path42/42/profile đã kiểm chứng](D14_SEMANTIC_REMEDIATION_RESULT.md).568scopedPASS/0SKIP gồm28newdeliverycontrols;732appfiles/all730oldexact, no newfull732claim. Không weights/SDK/cache/DBdump/secrets/checkpoints/defaultactivation/modelchange/release. CácZIPtrước giữ nguyên; chỉ dùng receipt/manifest để xác định chính xác commit/count/hash của gói mới.
