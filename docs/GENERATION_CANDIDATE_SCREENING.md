# Generation candidate screening — chưa chọn model

**Mục đích:** Ghi lại metadata ứng viên sinh ảnh/video để chuẩn bị quyết định sau HAR-010; không thay Model Registry hoặc chứng nhận khả năng chạy.

**Ngày:** 2026-11-10. **Trạng thái:** SCREENING ONLY. Không tải weights, cài diffusion SDK, nạp hoặc chạy hai ứng viên dưới đây. Đây không phải shortlist đã duyệt, không đề xuất thay CORE/embedding/TTS/model hiện có.

## 1. Phần đã biết

| Hướng | Nguồn / revision đã đọc | Metadata và giới hạn |
|---|---|---|
| Image baseline nhỏ: SD v1.5 | [Artifact repository/model card](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5), revision `451f4fe16113bff5a5d2269ed5ad43b0592e9a14` | API metadata báo ungated. Bốn FP16 safetensors của UNet/VAE/text encoder/safety checker tổng **2,740,623,950 byte**; chưa cộng tokenizer/config/SDK/cache. Model card ghi nền tảng 512×512, license CreativeML OpenRAIL-M. Repo tự nêu là mirror, không liên kết với Runway; provenance cần được đánh giá trước chọn. Không khẳng định đây là model tốt nhất hiện tại hoặc đã đạt chất lượng. |
| Video feasibility: Wan2.1 T2V 1.3B | [Upstream source](https://github.com/Wan-Video/Wan2.1), [artifact repository](https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B), revision `37ec512624d61f7aa208f7ea8140a131f93afc9a` | API metadata báo ungated. Ba weight files chính tổng **17,545,600,722 byte**, chưa cộng đầy đủ tokenizer/SDK/cache. Upstream công bố tham chiếu khoảng **8.19 GB VRAM**; đó không phải số đo trên máy này hoặc khi CORE cùng resident. |

Các size là tổng trường LFS size của nhóm file đã chỉ rõ trong metadata public, không là complete download manifest hoặc RAM/VRAM estimate. Không chuyển thông số upstream thành benchmark của dự án. Không dùng `.pth` hay remote repository code trước khi có loader/trust assessment và SDK lock cụ thể.

## 2. Tài nguyên tại thời điểm screening

GPU hiện là RTX 4070 Ti SUPER, 16,376 MiB theo `nvidia-smi`. Sau khi nạp CORE đã duyệt trong đợt smoke, một snapshot báo **8,934 MiB used / 7,007 MiB free**. Đây chỉ là snapshot, không là peak, reservation hay guarantee cho job khác. Số 8.19 GB upstream của Wan đã lớn hơn free snapshot trước khi thêm headroom; co-residency chưa được chứng minh. Không unload CORE hoặc đổi context/precision để ép chạy.

## 3. Trước khi được tải/chạy bất kỳ ứng viên nào

1. Chốt candidate/provenance/license và phạm vi chất lượng cần dùng; ghi vào proposal, chưa tự thêm thành approved selection trong Model Registry.
2. Freeze đầy đủ artifact manifest/revisions/hashes/bytes và isolated uv SDK lock; tính tổng disk gồm dependencies/cache, không chỉ weights.
3. Soạn preflight RAM/VRAM/CORE residency, worker/process/time/disk/output caps, cancellation/OOM/cleanup và rollback cụ thể. Không gọi CUDA allocator limit là hard global VRAM cap.
4. Freeze corpus/seed/resolution/steps/oracle: image fidelity/prompt adherence/latency; video temporal consistency/duration/fps/latency. Đo cold/warm, peak RAM/VRAM và tác động CORE; giữ failures.
5. Xin owner duyệt **phạm vi preparation/evaluation cụ thể** trước download/run; adoption/default/product activation cần quyết định sau benchmark. Không fallback provider hay thay model đã thống nhất.

Tiếp tục HAR-011 trước nếu chọn nhánh image; HAR-013 chỉ là feasibility khi chưa có resource envelope. [Backlog](progress/HARNESS_PRODUCT_BACKLOG.md) và [runbook](HARNESS_CLI_DESKTOP_RUNBOOK.md) phân biệt contract đã viết với generation còn unavailable.
