# D74 — Hồ sơ phương án tích hợp voice để duyệt

**Mục đích:** Đưa ra lựa chọn cụ thể sau phản hồi “Ổn rồi”, dựa trên quyền sử dụng, code hiện tại và số đo đã có. Đây là hồ sơ chuẩn bị; chưa đổi model, cấu hình hoặc bật voice trong API chính.

## Đề xuất A: tích hợp cá nhân tại máy, mặc định tắt

Giữ đúng **Silero v5 → Qwen3-ASR-0.6B GPU → CORE 32K/Fast512 → Trúc Ly CPU 8 luồng** đã kiểm chứng. Tạo giao diện voice trong ứng dụng chính với phiên gắn tài khoản, xác thực trước khi nhận bản ghi, Ghi/Dừng/Gửi/Hủy và nút Đóng phiên để trả tài nguyên. API key được giữ ở phía máy chủ; không tự ghi, tự nạp hoặc đổi model/giọng.

Repo hiện có API chính nhưng `apps/web/` chưa có nội dung. API hiện tại cố ý từ chối yêu cầu trực tiếp từ trình duyệt. Phương án thêm lớp phục vụ giao diện trong cùng ứng dụng, dùng mã ghép tạm để gắn phiên với tài khoản hiện có; API cũ giữ nguyên chính sách. Phiên của trang thử 8092 chưa đáp ứng danh tính này.

ASR giữ VRAM khi sẵn sàng, nên cần điều phối tài nguyên cho cả vòng đời phiên. Trong phạm vi đầu, voice giữ quyền dùng GPU tới khi đóng/hết hạn; các yêu cầu GPU khác báo bận. CORE được dùng lại từ dịch vụ đã xác minh; voice không tự bật/tắt dịch vụ này. Các đường chat hiện có phải cùng tuân thủ điều phối trước khi bật tính năng. Các phép thử D85 và khóa theo hội thoại chưa giải quyết việc này.

## Quyền sử dụng đã đối chiếu

[Bảng quyền sử dụng](D74_VOICE_RIGHTS_REVIEW.md) gắn đúng revision, SDK/preset và notice đang có. Tuyên bố của tác giả bao phủ preset được đóng kèm; dữ liệu hợp đồng nguồn không được kiểm tra độc lập. Các thư viện FFmpeg GPL, libsndfile LGPL và NVIDIA có nghĩa vụ riêng khi phân phối. Đề xuất hiện tại dùng artifact đã cài tại máy, không đóng gói lại hoặc tải thêm. Piper/Lessac là hồ sơ ứng viên khác, không tự trở thành hạn chế của Turbo.

Đã kiểm kê 175 lần hiện diện distribution / 133 cặp tên-phiên bản, cùng giấy phép cục bộ của SDK/codec/runtime. Đây chưa phải SBOM của một bộ cài phát hành. Việc chọn license cho toàn repo hoặc phát hành kèm binary/weights được để riêng, chưa tự quyết.

## Bằng chứng hiệu năng và giới hạn

| Nội dung đã đo | Kết quả / ý nghĩa |
|---|---|
| HTTP thực, 4 bản có tiếng nói / 2 bản không có tiếng nói | 6/6 đạt trong bộ thử; bốn đầu ra nhận dạng/trả lời/audio trùng bản trước |
| Gửi→nhận đủ phản hồi | 1,972 / 2,688 / 3,250 / 3,114 giây; chưa đo tiếng phát từ loa |
| Prepare | 43,843 giây riêng trước Gửi; không phải cold-first-request ≤4 giây |
| ASR GPU | Peak đã lưu khoảng 3,92 GiB VRAM; không phải RAM hoặc tối thiểu cả máy |
| TTS / VAD | RAM đỉnh riêng khoảng 1,40 / 0,28 GiB; các đỉnh chưa được đo đồng thời |
| CORE | VRAM đỉnh lấy mẫu 8792 MiB; chưa có chuỗi RAM đồng thời của toàn luồng |
| Giới hạn hiện tại | RAM worker + CORE đã xác minh 8 GiB / TTS 2 GiB; RAM khả dụng trước nạp tối thiểu 14 GiB; giữ nguyên các giới hạn |

Không có lượt chạy model hoặc phép đo thiết bị mới trong nhiệm vụ chuẩn bị này. Mốc tiếng phát từ loa trong 4 giây, nhận dạng lời ngắn/nhỏ và điều kiện phòng thực tế vẫn cần kiểm chứng; phản hồi “Ổn rồi” được ghi nhận là đánh giá tổng quát tích cực.

## Phạm vi đề nghị duyệt

**A — đề nghị:** duyệt [ADR174](ADR/174-proposed-opt-in-authenticated-voice-integration.md) cho một đợt triển khai có điều kiện:

1. B1: giao diện/phiên/xác thực và API/service contract; feature mặc định tắt, test giả lập không nạp model.
2. B2: tách adapter đã đạt, điều phối GPU chung, kiểm danh tính CORE, hủy/thu hồi/không ảnh hưởng dịch vụ dùng chung.
3. Chỉ khi B1/B2 và các gate nguồn/tài nguyên đạt: một lượt B3 trên đúng 4 nguồn speech VI / 2 negative cũ, tối đa 6 VAD / 4 ASR / 4 CORE / 4 TTS + 1 readiness, không retry/thay model hoặc tải weights.

Ước lượng B1–B3 khoảng 4–6 ngày công, phụ thuộc tích hợp/kiểm thử; không phải ngày lịch cam kết. Các task/dependency/rủi ro và rollback nằm trong ADR. Dừng nếu có lỗi bất ngờ và giữ mọi kết quả; không tự đổi AC để đạt.

**B — lựa chọn còn lại:** giữ chế độ nghiên cứu hiện tại, chưa triển khai phần ứng dụng chính.

Chấp thuận A chỉ bao gồm code/kiểm thử mặc định tắt và lượt kiểm chứng có điều kiện trên. **Chưa bao gồm bật sản phẩm, chốt model/default/giọng, phát hành binary/weights hoặc đóng D74/D90.** Quyết định đó và phép đo tiếng thật từ loa được giữ riêng. D60 vẫn deferred; không mở lại vòng sửa phát âm đã dừng.

[Receipt và nguồn đối chiếu](evidence/d74-voice-integration-review-20261105.json). Không chỉnh source/Docker/Vault/database/config hoặc can thiệp phiên voice đang chạy trong nhiệm vụ này.
