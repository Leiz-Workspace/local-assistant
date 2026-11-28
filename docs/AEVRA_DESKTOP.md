# Aevra — web container và Electron desktop

**Trạng thái:** Electron là target desktop mới; GTK/WebKitGTK là legacy trong thời gian chuyển tiếp. Web và desktop dùng cùng một Aevra product UI tại `/`; UI llama.cpp ghim sẵn chỉ còn là bề mặt tương thích.

## Kiến trúc

```text
Browser ──┐
Electron ─┼─> Aevra web container (host network, 127.0.0.1:7090) ─> CORE 127.0.0.1:8080
CLI ──────┘
```

Container dùng `network_mode: host` để giữ nguyên ranh giới chỉ-loopback của Aevra: app bind `127.0.0.1:7090` trên host, thấy đúng peer loopback và gọi CORE qua `127.0.0.1:8080`. Docker port publishing không được dùng vì peer sẽ là gateway của bridge và mọi request bị chặn. Container không khởi động, dừng hay đổi CORE dùng chung.

Container chạy bằng uid của chủ máy (`AEVRA_UID`/`AEVRA_GID`, mặc định `1000`) để mở được file principals `0600`, mount read-only; root filesystem read-only, `/tmp` là tmpfs, bỏ mọi capability và bật `no-new-privileges`. Build context là allowlist trong `.dockerignore` (`apps/`, `src/`, `configs/`, `pyproject.toml`, `uv.lock`), nên `models/` và `data/` không bao giờ vào image.

Route:

- `/` — Aevra UI (shell tĩnh, không chứa dữ liệu);
- `/healthz` — readiness đi qua cùng kiểm tra loopback như UI (Docker healthcheck và Electron dùng route này);
- `/api/v1/harness/*` — chat, context, memory, skills, runs và generations, cần session.

## Khởi động

Cần file principals do `aevra init` tạo tại `~/.local/state/local-assistant/principals.json` (hoặc đặt `AEVRA_PRINCIPALS_FILE`). Từ thư mục dự án:

```bash
docker compose -f docker-compose.web.yaml up -d --build aevra-web
```

Rồi mở `http://127.0.0.1:7090/`. Lệnh trên không cần chuẩn bị UI llama.cpp. CORE phải đang chạy để chat có câu trả lời; nếu chưa, UI báo "CORE không phản hồi" thay vì lỗi chung.

## Session

Với `ASSISTANT_WEB_AUTO_SESSION=1` (mặc định trong compose, tắt bằng `AEVRA_WEB_AUTO_SESSION=0`), UI tự tạo cookie HttpOnly/SameSite=strict khi gặp 401 đầu tiên, nên không cần mã pairing. Bearer không nằm trong URL, DOM, localStorage hay preload. Đăng xuất thu hồi session hiện tại; UI không tự tạo phiên mới cho tới khi bấm "Kết nối lại". Electron hiện cần auto-session vì chưa có đường pairing bằng token của owner.

**Owner đã chấp nhận (2026-11-26):** giữ auto-session bật mặc định. Đánh đổi: auto-session cấp phiên owner cho bất kỳ tiến trình nào trên máy gọi được `127.0.0.1:7090` với header hợp lệ, kể cả tài khoản hệ điều hành khác. Trên máy chỉ một người dùng, rủi ro thấp; nếu máy có nhiều tài khoản, tắt auto-session và dùng `aevra ui open` (pairing tự động bằng token `0600` của owner).

Khi tắt auto-session, UI hiện màn hình kết nối trong app và hướng dẫn chạy `aevra ui open`; flow `/pair/#code` vẫn là đường tương thích.

## UI

Kiến trúc UI và hợp đồng chi tiết ở [AEVRA_WEB_UI_SPEC.md](AEVRA_WEB_UI_SPEC.md) và [ADR-199](ADR/199-aevra-ui-parity-architecture.md). Tóm tắt: sidebar đóng/mở (rail icon, Ctrl/Cmd+B) với lịch sử hội thoại lưu trên thiết bị (IndexedDB), tìm kiếm, ghim, đổi tên, xuất JSON, xóa; khung chat có nút `+` (tệp văn bản/code, skill đã cài, system message), chọn mức reasoning, chọn model (chỉ CORE đã duyệt), vòng context, nút mic, Gửi/Dừng; câu trả lời stream có khối suy nghĩ, thống kê, sao chép/sửa/tạo lại/xóa và chuyển phiên bản. Mic, ảnh/PDF và đổi sang model unrestricted đang chờ owner duyệt.

## Electron desktop

Package tại `desktop/electron/`:

```bash
npm --prefix desktop/electron ci
npm --prefix desktop/electron run pack -- --publish never
```

Artifact `aevra-linux-amd64_v<version>-electron.deb`, package identity `aevra-desktop-electron` (không xung đột với gói GTK legacy `aevra-desktop`), dùng icon Aevra và `chrome-sandbox` 4755 root.

Electron chỉ nhận `AEVRA_WEB_URL` là origin loopback (mặc định `http://127.0.0.1:7090`, từ chối path/query/hash), mở cửa sổ ngay, chờ `/healthz`, rồi tải `/`. Khi web chưa chạy, cửa sổ hiện lệnh khởi động container và tự kết nối khi web sẵn sàng. Renderer dùng `contextIsolation`, `sandbox`, tắt `nodeIntegration`, chặn popup và navigation khác origin; chỉ cho ghi clipboard và tải về (xuất hội thoại, artifact) từ chính origin Aevra, mọi permission khác bị từ chối. Electron không quản lý container.

## Legacy GTK/WebKit

`apps/desktop/` và package `aevra-desktop` giữ lại để rollback trong giai đoạn chuyển tiếp, không dùng để đánh giá Electron.

## Kiểm chứng và giới hạn

Đã chạy thật: UI trên trình duyệt với CORE giả lập (chat, lỗi CORE + thử lại, Markdown, cả 7 panel với dữ liệu thật: archive, skill, run; logout/kết nối lại; mobile 375px), container build và chạy (`/` 200, `/healthz` 200, API không cookie 401, bootstrap, chat), và cửa sổ Electron ở trạng thái chờ lẫn đã kết nối vào container. Lần chụp Electron dùng binary dev nên chạy với OS sandbox tắt; gói `.deb` cài bằng quyền root mới có sandbox setuid.

Chưa có: chat với CORE/model thật, cài `.deb` trên máy sạch, streaming câu trả lời. Test UI/API không phải đo chất lượng model.
