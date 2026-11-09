# D74 — Chấp nhận B4 của chủ dự án: first-audible trên `/voice`

**Mục đích:** Ghi lại buổi B4 ngày 2026-11-08 trên trang voice chính `/voice`, quyết định "Chấp nhận kèm ghi chú" của chủ dự án, các ghi chú phải đi kèm quyết định đó, và quy trình khởi chạy `/voice` đủ để operator lặp lại.

**Ngày:** 2026-11-08 (giờ Asia/Ho_Chi_Minh). **Phạm vi:** gate B4 của [ADR174](ADR/174-proposed-opt-in-authenticated-voice-integration.md), trên đường `/voice` của [ADR175](ADR/175-optional-main-voice-composition-and-entrypoint-binding.md), [ADR176](ADR/176-bounded-foreign-gpu-tolerance-and-b3-preflight.md) và [ADR178](ADR/178-graceful-sigterm-exit-in-b3-acceptance.md). **Receipt công khai:** [evidence/d74-b4-voice-owner-acceptance-20261108.json](evidence/d74-b4-voice-owner-acceptance-20261108.json).

**Trạng thái:** CHỦ DỰ ÁN CHẤP NHẬN KÈM GHI CHÚ phần first-audible trên thiết bị thật của B4. Đây là chấp nhận của chủ dự án, dựa trên mốc phần mềm của trang và khoảng thời gian phía server, **không** phải phép đo vật lý khách quan: physical first-audible ≤4 giây khách quan vẫn chưa đo (UNVERIFIED). Quyết định cuối về model, giọng, default và sản phẩm vẫn mở.

**Kết luận:** Chủ dự án chạy 14 lượt trên `/voice` bằng Brave, microphone của mình và đầu ra HDMI. Cả 14 lượt đi hết VAD, ASR, CORE và TTS; khoảng thời gian phía server của từng lượt là 1,10–3,93 s. Chủ dự án báo số "Nhận audio" trên trang dưới 4 giây ở các tình huống khác nhau (không báo số của từng lượt), rồi chọn "Chấp nhận kèm ghi chú" thay cho "Đo lại có video". Không có video hay bản ghi khách quan, nên độ trễ của hệ thống âm thanh, HDMI và loa chưa được đo. Lần Chuẩn bị đầu lỗi `dependency_failed` và được bấm lại ngay. Không lượt nào là tình huống im lặng. Voice vẫn mặc định tắt và trạng thái release không đổi.

## Lời chủ dự án

Tất cả trong ngày 2026-11-08 *(owner 2026-11-08, operator record)*:

- Sau PR #40: "Vậy thì trước mắt là cùng làm B4".
- Trong hộp câu hỏi về cách khởi chạy, chủ dự án chọn:
  - có mặt tại PC này và tự tắt Sunshine cùng cửa sổ Settings: "Có, tôi tắt ngay";
  - chạy `/voice` bằng hai script vận hành tạm để ngoài repository: "Script tạm";
  - manifest là template B3 ADR178 cộng bản đồ nguồn hiện tại, receipt giữ trong `data/backups/d74-b4-voice-physical-first/`: "B3 + lưu receipt";
  - chủ dự án tự tạo mã ghép phiên trong terminal của mình: "Tự chạy lệnh".
- Sau buổi chạy: "Được rồi phần âm thanh nhận vào đã <4s ở các case khác nhau". Câu này nói về số "Nhận audio" trên trang. Đó là mốc phần mềm, tính từ cú bấm Gửi đến lúc trang nhận đủ và kiểm xong phản hồi ([session.mjs](../apps/web/voice/session.mjs), `submit`; [page.mjs](../apps/web/voice/page.mjs)); nó không gồm việc phát, hệ thống âm thanh hay loa. Chủ dự án không báo số trên trang của từng lượt, mỗi lượt thuộc tình huống nào, hay có lượt nào định để im lặng.
- Khi được hỏi "Chốt B4 thế nào?" với hai lựa chọn "Đo lại có video" và "Chấp nhận kèm ghi chú", chủ dự án trả lời "Chấp nhận kèm ghi chú".

## Phạm vi

- **Trang:** trang chính `/voice` (`apps.api.voice:create_app`, mục đích `integration_evaluation`), không phải trang thử 8092.
- **Nguồn:** `develop` `fb5ee5d`. Mã ứng dụng giống `production` `2e5e242`; `develop` chỉ khác `production` ở `docs/`, `dev_log/` và `README.md`. Nguồn đã có PR #33 (`MALLOC_ARENA_MAX=1` trong `src/infrastructure/ocr_worker.py`), nên khoảng thời gian phía server ở dưới chạy trên mã đã có thay đổi mà [kết quả B3](D74_MAIN_VOICE_B3_RESULT.md#sau-pr-33-2026-11-07) nhắc tới.
- **Thiết bị:** PC này, Brave, microphone chủ dự án dùng, đầu ra âm thanh mặc định `alsa_output.pci-0000_01_00.1.hdmi-stereo` (HDMI). Chủ dự án không báo model loa hay âm lượng.
- **Lane:** lane nghiên cứu trong manifest B3 (Qwen3-ASR + CORE + Trúc Ly/VieNeu TTS). Không đổi model, giọng hay tham số.
- **Không có bản ghi khách quan:** không quay video hay bản ghi nào khác. Cách đo khách quan bằng video và phiếu 16 hàng của [checklist](D74_PHYSICAL_FIRST_AUDIBLE_CHECKLIST.md) chưa được thực hiện.

## Chuẩn bị và khởi chạy `/voice`

Quy trình dưới đây là những gì đã làm trong buổi này, viết lại đủ để operator lặp lại. Hai script vận hành tạm (keeper CORE và script ghi manifest) chỉ nằm trong scratchpad của phiên và **không** được commit. Một launcher được commit sẽ cần PR riêng có test. Không ghi token, mã ghép phiên, mật khẩu hay chuỗi kết nối vào tài liệu, chat hay log.

**Ghi chú 2026-11-09 (sau D81):** Trên cây có D81 (phương án A của [ADR177](ADR/177-proposed-d81-structured-excerpt-product-integration.md)), phạm vi nguồn B3/B4 (`source_snapshot()` trong [main_voice_integration.py](../benchmarks/scripts/main_voice_integration.py)) có 310 file thay vì 307: thêm `apps/api/grounded_extract.py`, `apps/api/routes/grounded_extract.py`, `src/application/services/grounded_extract.py`, và `apps/api/services/grounded.py` đổi. Đường code voice không đổi, nhưng `apps.api.voice:create_app` dựng trên `apps.api.main.app`, nên chuỗi import nay nạp thêm module trích xuất. Vì vậy với mọi buổi `/voice` mới phải cập nhật kiểm tra drift của quy trình này: dòng "Phạm vi 307 file nguồn của B3" ở bước 1 (chỉ cho phép khác `src/infrastructure/ocr_worker.py`) và bản đồ nguồn ở bước 3 phải tính lại trên đủ 310 file của cây đang chạy; nếu giữ kiểm tra cũ, buổi chạy sẽ dừng ở bước kiểm tra drift. Chấp nhận B4 ngày 2026-11-08 vẫn giữ nguyên như đã ghi, gắn với nguồn của buổi đó.

### 1. Kiểm tra trước khi nạp CORE

Chủ dự án có mặt tại máy. Chỉ dừng ứng dụng GPU khác khi chủ dự án đồng ý; không tự dừng dịch vụ dùng chung. Trong buổi này, chủ dự án dừng Sunshine (215 MiB GPU compute) và đóng VS Code. Agent dừng dịch vụ nền GNOME Settings (46 MiB) theo yêu cầu của chủ dự án, vì lệnh `pkill -x gnome-control-center` của chủ dự án không khớp tiến trình nào: tên tiến trình bị cắt còn 15 ký tự.

Dùng các lệnh ở điều kiện 2 của [checklist](D74_PHYSICAL_FIRST_AUDIBLE_CHECKLIST.md), cộng thêm kiểm tra GPU compute của tiến trình lạ, cổng 18092, service thử và phạm vi nguồn:

| Kiểm tra | Ngưỡng | Buổi này |
|---|---|---|
| VRAM trống | phải ≥14.336 MiB; ngưỡng tiến hành đã dùng ≥14.940 MiB | 15.204 MiB |
| `MemAvailable` | phải ≥14.680.064 kB; nên ≥19.922.944 kB | 21.718.160 kB |
| GPU compute của tiến trình lạ | tổng ≤1 GiB ([ADR176](ADR/176-bounded-foreign-gpu-tolerance-and-b3-preflight.md), kiểm lại lúc Chuẩn bị) | 319 MiB: gnome-remote-desktop 253, xdg-desktop-portal-gnome 20, ptyxis 46 |
| `llama-server` | không có | không có |
| Cổng 18080 và 18092 | trống | trống |
| `local-assistant-voice-trial.service` | inactive | inactive |
| Phạm vi 307 file nguồn của B3 | sạch; chỉ được khác commit B3 `73cecdf` ở `src/infrastructure/ocr_worker.py` | đạt |

### 2. CORE trên cổng 18080

- Dùng đúng profile d14: `benchmarks/scripts/d14_completion.py`, `command("core")` (`--host 127.0.0.1 --port 18080 --ctx-size 32768 --parallel 1 --reasoning off --slots --offline`, có mmproj). Khởi động qua `OwnedServer` để giữ nguyên guard preflight và guard monitor. Không đổi tham số.
- Buổi này: keeper khởi động CORE lúc 19:11:13, CORE sẵn sàng lúc 19:11:17 (PID 1200691).
- Sau khi CORE sẵn sàng và trước khi khởi động web, kiểm tra lại:

| Kiểm tra | Ngưỡng | Buổi này |
|---|---|---|
| RSS của CORE | dưới 6 GiB (ngưỡng dừng của ADR176) | 1.236.888 KiB |
| VRAM của CORE | — | 8.764 MiB |
| GPU compute của tiến trình lạ | tổng ≤1 GiB | 273 MiB |
| VRAM trống | ≥6.144 MiB (ASR cần trước khi nạp) | 6.746 MiB |
| `MemAvailable` | ≥14 GiB trước mỗi worker | 24.445.584 kB |

### 3. Manifest

- Lấy `manifest-template.json` của lượt B3 ADR178 (thư mục cục bộ `data/backups/d74-main-integration-adr178/`). Kiểm tra SHA-256 của template khớp `manifest_template_sha256` trong `preparation.json` của lượt đó, và lệnh CORE đang chạy khớp lệnh CORE đã ghi.
- Chỉ thay `source_sha256` bằng bản đồ SHA-256 của 307 file nguồn tính lại trên cây hiện tại; khác biệt duy nhất so với B3 là `src/infrastructure/ocr_worker.py`.
- Thêm khối `core` của CORE đang chạy, cùng dạng runner B3 tạo ([main_voice_integration.py](../benchmarks/scripts/main_voice_integration.py), `run()`).
- SHA-256 của manifest buổi này: `b352a827ee9deea416fa2ee5052c291b11d964cae9e1ca9a239d2ec1a34e9731`. Một bản sao nằm trong thư mục receipt riêng.

### 4. Chạy thử khô

Chạy `VoiceManifest.verify` và `BorrowedCore.verify` trên manifest và CORE đang chạy, không gọi suy luận và không tốn lần Chuẩn bị nào. Buổi này: đạt, mất 41 s.

### 5. Xác thực trong RAM

- File principal chỉ nằm trong RAM, ở `/dev/shm`, quyền 0600, cùng dạng runner B3 tạo (chỉ chứa id principal và SHA-256 của token).
- Token chỉ nằm trong một file header bearer quyền 0600 và không bao giờ được in ra.
- Cả hai được xóa khi dọn dẹp.

### 6. Web trên cổng 18092

Từ `ai/`, chạy một process với một worker:

```sh
uvicorn apps.api.voice:create_app --factory --host 127.0.0.1 --port 18092 --no-proxy-headers
```

Môi trường giống runner B3, chỉ áp dụng cho process đánh giá này:

- `ASSISTANT_VOICE_ENABLED=1` và `ASSISTANT_VOICE_PURPOSE=integration_evaluation`;
- `ASSISTANT_AUTH_FILE` trỏ tới file principal trong `/dev/shm`, `ASSISTANT_VOICE_MANIFEST` trỏ tới manifest ở bước 3;
- `TMPDIR=/dev/shm`; không đặt `DATABASE_URL`;
- `WEB_CONCURRENCY` phải là 1 hoặc không đặt, vì `create_app` từ chối mọi giá trị khác ([voice.py](../apps/api/voice.py)).

Buổi này web khởi động lúc 19:12:43. Kiểm tra log khởi động có `voice_manifest_loaded activation=False`, `main_voice_composed default_model_change=False` và `voice_managed_gpu_paths_bound count=11`, và trạng thái là `idle` với 24 lượt và 3 lần Chuẩn bị.

### 7. Mã ghép phiên

Chủ dự án tự tạo mã trong terminal của mình: gửi một yêu cầu `POST` không có body tới `http://127.0.0.1:18092/api/v1/voice/pairing` qua loopback, với header bearer đọc từ file 0600 ở bước 5 (ví dụ `curl -H @<file header>`), để token không xuất hiện trên dòng lệnh. Mã chỉ dùng một lần và hết hạn sau 120 s ([voice_identity.py](../apps/api/voice_identity.py), `issue`). Mở `http://127.0.0.1:18092/voice` trong Brave và nhập mã. Không dán mã vào chat hay log. Sau đó làm theo các bước của [checklist](D74_PHYSICAL_FIRST_AUDIBLE_CHECKLIST.md).

### 8. Thứ tự dừng

1. Gửi SIGTERM cho web trước. Kiểm tra log có đủ 5 sự kiện tắt của lifespan voice, đúng thứ tự (`voice_service_closed`, `voice_identity_closed`, `gpu_admission_unbound`, `voice_managed_gpu_paths_restored`, `voice_manifest_closed`), không có dòng lỗi, và worker của nhóm join sạch. Việc tắt êm được đánh giá bằng các sự kiện này trong log, như ADR178; mã thoát vẫn được ghi lại.
2. Sau đó gửi SIGTERM cho keeper CORE, rồi kiểm tra receipt CORE có mã thoát 0 và `guard_failure` null.
3. Xóa thông tin xác thực trong RAM. Kiểm tra không còn `llama-server` hay worker voice nào, cổng 18080 và 18092 trống, và không còn thư mục `/dev/shm/main-voice-*`.

## Diễn biến buổi B4

Theo log ứng dụng:

| Thời điểm | Sự kiện |
|---|---|
| 19:16:26 | Mã ghép phiên được cấp. |
| 19:17:10 | Mã được dùng; Brave đã ghép phiên. |
| 19:17:16 | Chuẩn bị lần 1 được nhận. |
| 19:17:53 | Manifest được xác minh; tiếp theo CORE mượn được xác minh, GPU lạ được chấp nhận (3 tiến trình, 319 MiB). |
| 19:17:55 | VAD sẵn sàng; nạp ASR được cấp quyền. |
| 19:18:04 | Worker ASR bị join với mã −15, `forced=True`; tiếp theo `voice_operation_failed code=dependency_failed` và `voice_prepare_failed`. Log không ghi nguyên nhân (mã lỗi chung). |
| 19:18:06 | Chuẩn bị lần 2 được nhận: chủ dự án bấm Chuẩn bị lại khoảng 2 s sau, trong khi điều kiện 5 của checklist yêu cầu dừng và báo trước. |
| 19:18:40 | Manifest được xác minh. |
| 19:18:42 | VAD sẵn sàng. |
| 19:18:52 | ASR sẵn sàng; readiness được xác minh. |
| 19:18:56 | TTS (turbo) sẵn sàng; nhóm sẵn sàng với thời hạn 480 s. Chuẩn bị lần 2 mất 49,73 s tính phía server. |
| 19:19:29–19:25:41 | 14 lượt. |
| 19:28:44 | Trạng thái `idle`, `error` null: nhóm đã tự hết hạn. Còn 10 lượt và 1 lần Chuẩn bị. |
| 19:28:52 | Web nhận SIGTERM. |

## 14 lượt: khoảng thời gian phía server

Cả 14 lượt qua VAD và đi hết ASR, CORE và TTS (số lượt gọi VAD 14, ASR 14, CORE 14, TTS 14). Không lượt nào bị xếp là không có lời nói, nên chưa thử tình huống im lặng N1/N2.

**Khoảng này đo gì:** thời gian giữa hai sự kiện trong log ứng dụng, từ lúc server nhận lượt (`voice_turn_admitted`, [voice_session.py](../src/application/services/voice_session.py), `submit`) đến lúc xóa dữ liệu RAM của lượt (`main_voice_turn_RAM_erased`, [native.py](../src/infrastructure/voice/native.py), `ask`). Khoảng này gồm việc đọc bản ghi gửi lên qua loopback, VAD, ASR, CORE, TTS, bước chuyển sang playback và bước dọn lượt.

**Khoảng này không gồm:** thời gian từ cú bấm Gửi đến lúc server nhận yêu cầu; gửi phản hồi về Brave; trình duyệt giải mã và bắt đầu phát; hệ thống âm thanh, HDMI và loa. Đây không phải số trên trang ("Nhận audio", "Chuẩn bị phát") và **không** phải physical first-audible.

| Lượt | Server (s) | Ghi chú |
|---:|---:|---|
| 1 | 2,09 | |
| 2 | 1,10 | nhanh nhất |
| 3 | 1,89 | |
| 4 | 3,17 | |
| 5 | 3,77 | |
| 6 | 1,50 | |
| 7 | 2,17 | |
| 8 | 2,13 | |
| 9 | 1,75 | |
| 10 | 1,19 | |
| 11 | 2,44 | |
| 12 | 3,17 | |
| 13 | 3,93 | chậm nhất, sát trần 4 giây |
| 14 | 3,21 | |

Không biết mỗi lượt thuộc tình huống nào (câu thường, câu ngắn, nói nhỏ hay có ồn), vì chủ dự án không báo.

## Tắt máy, audit và receipt CORE

**Web:**
- Web nhận SIGTERM lúc 19:28:52. Log có đủ 5 sự kiện tắt của lifespan, đúng thứ tự, và 0 dòng lỗi.
- Worker của nhóm (turbo, qwen3-asr-0.6b, vad) join với mã 0, `forced=False`. Worker ASR và VAD của lần Chuẩn bị lỗi có mã −15, `forced=True`.
- Số lượt gọi của nhóm: VAD, ASR, CORE và TTS mỗi loại 14. Token không xuất hiện trong log.
- Launcher chạy nền báo mã thoát 144; như ADR178, việc tắt êm được đánh giá bằng các sự kiện trong log.

**CORE:** keeper nhận SIGTERM. Receipt CORE có mã thoát 0, `guard_failure` null. Giá trị lấy mẫu: đỉnh VRAM 8.790 MiB, VRAM trống thấp nhất 2.366 MiB, `MemAvailable` thấp nhất 17.825.184 KiB (khoảng 17,0 GiB), đỉnh RSS 8.084.080 KiB (khoảng 7,71 GiB).

**Dọn dẹp:** không còn `llama-server` hay worker voice nào, cổng 18080 và 18092 trống, không còn `/dev/shm/main-voice-*`, thông tin xác thực trong RAM đã xóa. Sau đó VRAM trống là 15.219 MiB.

**Receipt riêng:** thư mục cục bộ `data/backups/d74-b4-voice-physical-first/` (không đưa vào git, không công khai) chứa `app-audit.log`, `keeper.log`, `manifest.json` và `owned-core-1/` (`launch.json`, `preflight.json`, `ready.json`, `server.log`). Hai script vận hành ở lại trong scratchpad của phiên và không được commit.

## Ghi chú đi kèm chấp nhận

Chấp nhận B4 này chỉ có giá trị khi đi cùng các ghi chú sau:

1. Không có video hay bản ghi khách quan, nên độ trễ đầu ra của loa/HDMI chưa được đo. Physical first-audible ≤4 giây khách quan vẫn chưa đo.
2. Khoảng thời gian phía server chậm nhất là 3,93 s (lượt 13), sát trần 4 giây.
3. Không lượt nào là tình huống im lặng (N1/N2).
4. Chủ dự án không báo đã phủ những tình huống câu ngắn, nói nhỏ hay có ồn nào.
5. Lần Chuẩn bị đầu lỗi `dependency_failed` (log không ghi nguyên nhân) và được bấm lại ngay, không dừng để báo như checklist yêu cầu.
6. Kết quả chỉ áp dụng cho PC này, Brave, microphone đã dùng, đầu ra HDMI và lane nghiên cứu trong manifest B3 (Qwen3-ASR + CORE + Trúc Ly/VieNeu TTS). Đây không phải p95 hay SLO.

## Vẫn mở

- Quyết định cuối về model, giọng, default và sản phẩm, vốn là một phần của gate B4 trong ADR174.
- Bật dùng sản phẩm: voice vẫn mặc định tắt, `ASSISTANT_VOICE_ENABLED` vẫn mặc định 0 và chỉ cho phép mục đích `integration_evaluation`; không đổi default nào.
- Buổi này không cho biết đã phủ tình huống câu ngắn, nói nhỏ hay có ồn nào và chưa thử im lặng, nên không rút ra kết luận riêng về nhận dạng trong các tình huống đó.
- Nếu sau này cần số đo vật lý khách quan, cách đo bằng video và phiếu 16 hàng của checklist vẫn áp dụng; buổi này không thay thế chúng.
- D81, D87, D88 (chỉ khi phân phối), D89 và D90 vẫn mở; D60 vẫn hoãn. Tài liệu này không đánh dấu ô nào của D89/D90 và không điền phiếu chủ dự án của D90.
- Trạng thái release không đổi: không tag, không GitHub Release, không deploy.
- Launcher `/voice` được commit cần PR riêng có test.

## Liên kết

- [Checklist đo tiếng trả lời đầu tiên](D74_PHYSICAL_FIRST_AUDIBLE_CHECKLIST.md)
- [Kết quả B3: voice qua API chính](D74_MAIN_VOICE_B3_RESULT.md)
- [ADR174](ADR/174-proposed-opt-in-authenticated-voice-integration.md), [ADR175](ADR/175-optional-main-voice-composition-and-entrypoint-binding.md), [ADR176](ADR/176-bounded-foreign-gpu-tolerance-and-b3-preflight.md), [ADR178](ADR/178-graceful-sigterm-exit-in-b3-acceptance.md)
- [Hồ sơ D90](D90_RELEASE_DECISION_DOSSIER.md), [các D còn mở](OPEN_DAYS_20261105.md)
- Receipt công khai: [evidence/d74-b4-voice-owner-acceptance-20261108.json](evidence/d74-b4-voice-owner-acceptance-20261108.json)
