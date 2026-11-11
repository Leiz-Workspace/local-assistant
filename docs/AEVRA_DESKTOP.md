# Aevra — CLI, web và native desktop

**Mục đích:** Hướng dẫn dùng tên/logo Aevra và desktop Linux độc lập, phân biệt phần đã chạy thật với đóng gói/phạm vi còn thiếu. [ADR-188](ADR/188-aevra-brand-and-native-webkit-desktop.md).

## 1. Tên và logo dùng chung

- Tên sản phẩm, command chính và Python distribution: **Aevra / `aevra`**. Alias `la` vẫn được giữ cho các lệnh cũ.
- Logo chính là rồng trắng owner cung cấp tại `aevra-logo-assets/aevra-dragon-white.svg`. Bản SVG và PNG gốc được copy nguyên byte vào `apps/branding/assets/`, có manifest SHA-256. Logo/icon giữ nền trong suốt, không thêm nền vuông hoặc đường viền; không vẽ lại logo. Mục Show Apps hiện dùng PNG trong suốt512px tại đường dẫn bất biến trong `hicolor/512x512/apps/`; shortcut ngoài Desktop đã đạt thì giữ SVG trong suốt. Source SVG/PNG gốc không thay đổi. Đã kiểm riêng hiển thị Show Apps với owner, không lấy preview GTK làm nghiệm thu thay thế.
- CLI: `aevra logo` hiển thị bản ASCII dựng từ chính logo; interactive chat trên terminal hiển thị logo. `aevra --json logo` trả tên/path/hash của SVG, không chèn control sequences vào JSON.
- Web: title, favicon, manifest, sidebar logo, badge và trang kết nối dùng Aevra. Upstream llama-ui b11557 vẫn giữ nguyên70files; wrapper chỉ thay response metadata/chrome bằng assets riêng. Nội dung chat và bundle gốc không bị thay chữ hàng loạt.
- Desktop: titlebar, icon cửa sổ và launcher dùng cùng logo; nội dung chat tiếp tục dùng UI llama.cpp qua backend có xác thực.

```bash
uv sync --locked --dev
uv run --no-sync aevra --help
uv run --no-sync aevra logo
uv run --no-sync aevra --json logo
```

Tên credential directory hiện có vẫn là `~/.local/state/local-assistant/`. Đổi thương hiệu không tự tạo lại identity, di chuyển secret, đổi alias model hoặc sửa database.

## 2. Desktop hiện tại là gì?

**Ứng dụng GTK3 với WebKitGTK 4.1 nhúng**, chạy thành process/cửa sổ riêng. Không mở Brave, Chromium, Chrome hoặc tab trình duyệt; không có fallback sang các trình duyệt đó. Web vẫn có thể mở trong trình duyệt bằng `aevra ui open` khi muốn.

Đây là native application cho Linux hiện tại, **chưa là AppImage hay bộ cài Windows/macOS**. Nó cần checkout/package Python, uv và GTK/WebKit của hệ điều hành. CORE inference vẫn là service riêng; desktop có thể tự quản lý backend API của nó, không tự nạp model.

Host hiện tại đã có `/usr/bin/python3` + PyGObject3.56.2, GTK3.24 và WebKit2.52/API4.1. Không cài thêm OS packages hoặc tải framework/model trong lượt triển khai này. Native runtime được chạy qua uv với OS Python; Python environment của dự án không bị chèn system `dist-packages`.

## 3. Mở ứng dụng

Từ repo:

```bash
uv run --no-sync aevra desktop
# Entry point riêng, tương đương:
uv run --no-sync aevra-desktop
```

Trong menu ứng dụng Linux hiện tại đã có **Aevra**, qua launcher `~/.local/share/applications/io.aevra.Aevra.desktop`. Launcher dùng icon của dự án và không chứa token hoặc mã pairing. Nó còn phụ thuộc vị trí checkout hiện tại; di chuyển repo cần tạo lại launcher.

Khi dùng port/identity riêng:

```bash
uv run --no-sync aevra --url http://127.0.0.1:7090 --token-file /ABSOLUTE/PRIVATE_TOKEN_FILE desktop --auth-file /ABSOLUTE/PRIVATE_PRINCIPALS_FILE
```

Luồng mở:

1. Kiểm tra GTK/WebKit trước khi mint mã pairing hoặc khởi động backend.
2. Nếu backend Aevra đã chạy và xác thực đúng, dùng lại; đóng cửa sổ sẽ không dừng backend đó.
3. Nếu không có backend, kiểm tra token khớp auth file rồi khởi động harness thuộc app. Đóng/lỗi app sẽ dừng và join đúng process group do app tạo. Tự khởi động hiện chỉ hỗ trợ `127.0.0.1` với port không đặc quyền; không chiếm port hoặc thay backend đang có.
4. Truyền nonce một lần qua stdin tới renderer; đổi sang cookie HttpOnly/SameSite theo flow cũ. Bearer token không đưa vào URL, JavaScript hoặc argv của renderer.
5. Hiển thị cửa sổ Aevra. `aevra desktop` chờ tới lúc cửa sổ đóng; JSON kết quả trả sau khi cleanup.

Nếu báo `aevra_backend_restart_required`, backend trên port đó là process cũ/chưa có branding: cần dừng đúng process của bạn rồi chạy từ checkout mới. App không tự restart shared server. Nếu thiếu GTK/WebKit hoặc không có display, báo lỗi native; không âm thầm mở Brave.

Để model trả lời thật, CORE phải sẵn sàng theo [inference documentation](DOCUMENTATION.md). App không tự tải/đổi/nạp/dừng CORE. Authentication, UI assets và inference readiness là ba điều kiện riêng.

## 4. Dữ liệu local và giới hạn

- Desktop có storage riêng dưới `~/.local/state/aevra/desktop/`, quyền700, tách theo backend và credential hash; không dùng profile Brave. Profile có lock chống hai process ghi đồng thời.
- IndexedDB/history trên thiết bị có thể lưu raw chat. Chưa đồng bộ PostgreSQL và không tự import lịch sử từ Brave. Xóa app/launcher không tuyên bố đã xóa mọi bản chat.
- Cookie phiên server vẫn hết hạn sau30phút; backend restart mất session. Khi hết phiên, mở lại desktop để pair. Không lưu bearer trong WebKit; credential storage bị tắt, không cấu hình persistent cookie store.
- Không có Python bridge hoặc native tools cấp cho trang. Navigation ra ngoài origin, popup, download tự động, file/script URLs và device permissions bị chặn. Existing backend/auth/CSRF/CSP checks vẫn áp dụng.
- Context policy mới, task và skill vẫn qua CLI/API; UI controls nâng cao chưa được nối chỉ vì đổi logo hoặc chuyển native host.
- Linux đã kiểm trên máy này; native installers/clean-machine matrix, Windows/macOS, accessibility/device acceptance và release gate tổng vẫn pending.

## 5. Kiểm chứng

Bằng chứng GUI dùng **backend synthetic**, không gọi model: cửa sổ GTK/WebKit thật, title/sidebar/favicon/logo Aevra, nhập và nhận stream `fixture`, exit0. [Ảnh desktop thật](evidence/aevra-native-desktop-20261111.png) thể hiện rõ câu trả lời fixture; không quảng bá nó thành inference thực. Lượt đầu kiểm load UI, sau đó kiểm stream và bổ sung chế độ QA không chiếm keyboard focus; mọi quan sát cũ giữ riêng.

Đã chạy thực tế managed backend: start → authenticated status Aevra → stop/join; không chạy model hoặc thay service đang tồn tại. Khi chủ động SIGTERM owned uv group, outer uv exit143 là expected termination, không gọi đó là native-window exit0.

Phần mềm được kiểm riêng với fixtures/doubles cho source logo hashes, build icon, response-only branding, API/CLI, native origin/profile/lock, initialization failure, stdin nonce/no raw logs, matching identity, owned cleanup và smoke orchestration. Kết quả final combined và hashes ở [receipt](evidence/aevra-native-desktop-20261111.json). Không phải full D87 hoặc nghiệm thu toàn dự án.

### Làm mới icon hệ thống — 2026-11-11

Sau khi owner báo vẫn thấy icon cũ, cài lại SVG trong suốt vào `~/.local/share/icons/hicolor/scalable/apps/` với resource name riêng, cập nhật launcher bằng atomic replacement, chạy `gtk-update-icon-cache` và `update-desktop-database`. Gio/GTK xác nhận launcher resolve đúng resource mới và ảnh64px có alpha0 ở góc; [ảnh kiểm tra từ GTK](evidence/aevra-icon-theme-20261111.png) là preview nền xám, không phải file icon để cài. Không restart GNOME/session hoặc thay theme/favorites của owner.

### Lối tắt ngoài màn hình Desktop — 2026-11-11

Owner xác nhận viền còn ở biểu tượng trên desktop máy Ubuntu. Kiểm tra XDG desktop directory thấy trước đó chỉ có Steam, không có Aevra. Đã tạo `~/Desktop/Aevra.desktop` riêng qua CLI hiện có, executable/trusted và custom-icon trỏ đúng SVG trong suốt đã kiểm hash/alpha; menu entry giữ nguyên. `desktop-file-validate` và Gio/GTK resolution từ chính file Desktop PASS. Đây là kiểm cấu hình/bộ nạp icon; chưa có ảnh xác minh trực tiếp grid DING ngoài desktop. Không dùng ảnh preview menu để tuyên bố đã kiểm vị trí này.

### Show Apps: owner xác nhận hoàn tất — 2026-11-11

Shortcut ngoài Desktop đã hết nền đen, nhưng owner xác nhận mục Aevra cũ trong Show Apps vẫn có nền sau các lượt thay file/cache, SVG trực tiếp và PNG. Mục tạm TEST Aevra có application ID mới và PNG trong suốt thì hiển thị đúng. Đã thay riêng mục đăng ký cũ bằng `io.aevra.Aevra.desktop`, đồng bộ native `APPLICATION_ID=io.aevra.Aevra`, dùng PNG512px bất biến giống nội dung ảnh TEST. Owner xác nhận **Aevra chính trong Show Apps đã hết ô đen**. Đã gỡ TEST và đưa entry cũ vào bằng chứng riêng; chỉ còn một Aevra hiển thị trong danh mục.

Đây là kết quả đối chiếu/khắc phục thực tế, không khẳng định đã chứng minh nguyên nhân nội bộ GNOME. API mở Show Apps tự động bị session từ chối; không bật unsafe mode, restart shell/session hoặc đổi theme/favorites. Profile/history/credentials/backend/model không đổi theo application ID mới.75 scoped tests PASS/0FAIL/0SKIP/1.11s; Ruff/format7files PASS, OS Python native dependency probe PASS. Các ảnh/receipts trước vẫn là lịch sử của source/registration cũ.
