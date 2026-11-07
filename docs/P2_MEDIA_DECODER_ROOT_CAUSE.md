# P2: nguyên nhân gốc của lỗi decoder media gián đoạn

**Ngày:** 2026-11-07. **Phạm vi:** lỗi `VideoError: video_invalid_content` gián đoạn ở `tests/test_video_sampler.py`, `tests/test_video_description.py` và `tests/test_media_timeline.py` (job quarantine trên CI), cùng một lỗi `audio_invalid_content` đã ghi trong [ledger](OUTSTANDING_WORK_STATUS.md). **Sửa:** biến `MALLOC_ARENA_MAX=1` cho mọi tiến trình native do `child_output` khởi chạy ([ocr_worker.py](../src/infrastructure/ocr_worker.py)). **Test hồi quy:** [test_native_child_address_space.py](../tests/test_native_child_address_space.py).

**Kết luận:** Nguyên nhân nằm trong code dự án, ở chỗ worker phối hợp với glibc. Fixture, ffmpeg và runner không có lỗi. Worker video và audio đặt `RLIMIT_AS` 512 MiB rồi chạy ffprobe/ffmpeg qua `child_output`, nên tiến trình con kế thừa trần này. FFmpeg CLI chạy nhiều luồng (demuxer, decoder, filter, encoder, muxer). glibc cấp cho mỗi luồng mới một arena malloc riêng: arena này giữ chỗ 64 MiB không gian địa chỉ, và trong lúc căn lề còn giữ tạm 128 MiB. Các lần giữ chỗ này lấp gần đầy trần 512 MiB. Lần cấp phát nào rơi đúng vào cửa sổ đó sẽ nhận ENOMEM. Nếu đó là mmap stack của luồng mới thì `pthread_create` trả EAGAIN, FFmpeg thoát với mã 245. Nếu đó là malloc của filter thì FFmpeg báo "Cannot allocate memory" và thoát với mã 244. Thời điểm phụ thuộc vào cách lập lịch luồng, nên lỗi xảy ra ngẫu nhiên. `video_worker.native` ánh xạ mọi mã thoát khác 0 thành `video_invalid_content`. Fixture module-scope (`sample`, `inputs`) biến một lần lỗi thành 33–69 ERROR, đúng như các run CI đã thấy. Với một arena duy nhất, footprint trở nên tất định (FFmpeg cần khoảng 290 MiB), trần 512 MiB giữ nguyên và không có retry.

## Bằng chứng

| Nơi | Điều kiện | Kết quả |
|---|---|---|
| Home Server (ffmpeg 8.0.1, glibc 2.43, 16 CPU, stack 8 MiB) | 3 file, chưa sửa, 60 lượt | 6/60 lượt lỗi (54 lượt sạch) |
| Home Server, có ghi stderr của tiến trình con | 40 lượt trong số trên, 1.120 lần lấy mẫu | 4/4 lỗi bất thường đều là `pthread_create() failed: Resource temporarily unavailable` ở luồng demuxer, ffmpeg thoát 245. Lượt 40 cho đúng "97 passed, 36 errors" như CI |
| Home Server, ffmpeg render đơn lẻ | Quét `RLIMIT_AS`, trong và ngoài sandbox bwrap | ≤288 MiB: 100% lỗi với đúng thông điệp trên; ≥296 MiB: 0% lỗi. Khi không có arena, FFmpeg cần khoảng 290 MiB |
| Home Server, strace một lượt render *thành công* dưới 512 MiB | | 5 luồng. Có 42 lần glibc giữ chỗ arena 128/64 MiB bị ENOMEM (lệnh audio: 369 lần), tức là tiến trình chạy sát trần. Với `MALLOC_ARENA_MAX=1`: 0 lần giữ chỗ arena |
| CI ubuntu-24.04 (ffmpeg 6.1.1, glibc 2.39, 2 vCPU, stack 16 MiB), run [42376813479](https://github.com/DungeonLeiz/local-assistant/actions/runs/42376813479), chưa sửa | 30 lượt 3 file | 6/30 lượt sạch. 36 lần ffmpeg thoát 244 với `Error while filtering: Cannot allocate memory` |
| Cùng run CI, đã sửa | 30 lượt 3 file | 30/30 lượt sạch, 0 lần ffmpeg lỗi. Chỉ còn 90 lần ffprobe thoát 1, đúng bằng 3 test âm tính cố ý × 30 lượt |
| Home Server, đã sửa | 100 lượt 3 file | 100/100 lượt liên tiếp sạch, mỗi lượt 133 passed |

Stack trên runner CI là 16 MiB (gấp đôi Home Server), nên phần dư dưới trần ít hơn và tỉ lệ lỗi cao hơn. Đã loại trừ các giả thuyết sau. Tranh chấp file fixture: các fixture dùng chung là file `.mkv` đã commit, chỉ đọc. ffmpeg chưa flush output: lỗi nằm ở tiến trình con đọc `/payload`. Tái sử dụng `tmp_path`: các fixture lỗi không dùng `tmp_path`. Timeout: timeout được ánh xạ thành `video_processing_timeout`. `RLIMIT_NPROC` và `pids.max` của cgroup: `pids.events` vẫn là `max 0`.

Tiền lệ trong repo: [ADR060](ADR/060-approved-snapshot-checks-without-host-execution.md) ghi nhận Ruff dưới trần 512 MiB cũng abort vì lỗi cấp phát/tạo luồng, và đã sửa bằng `MALLOC_ARENA_MAX=1`. `check_runner.py` đã đặt sẵn biến này.

## Test hồi quy

`test_native_child_address_space.py` chạy entry point `main()` thật của worker video và audio (trần thật, sandbox bwrap thật, launcher `child_output` thật). Test chỉ thay phần decode bằng một tiến trình con 8 luồng: mỗi luồng gọi malloc với stack cố định 1 MiB. Test yêu cầu VmPeak tăng dưới 32 MiB, tức là chỉ có stack và không có arena 64 MiB nào. Với env trước khi sửa, test fail tất định: VmPeak tăng 478.330.880 byte, giống nhau trên Home Server và CI. Sau khi sửa, test pass. Một test đối chứng chạy cùng probe nhưng không có trần arena và không có rlimit, để chứng minh probe thực sự phát hiện được arena.

## Kiểm chứng

- Test mới: trước khi sửa 3 failed, 1 passed; sau khi sửa 4 passed (Home Server và CI).
- Home Server, lệnh `uv run --no-sync python -m pytest tests/test_video_sampler.py tests/test_video_description.py tests/test_media_timeline.py -q -p no:cacheprovider -rfE`: trước khi sửa 6/60 lượt lỗi; sau khi sửa 100/100 lượt liên tiếp sạch (133 passed mỗi lượt, 0 skip). Nếu lỗi vẫn ở tỉ lệ cũ khoảng 10% mỗi lượt, xác suất có 100 lượt sạch liên tiếp chỉ khoảng 3·10⁻⁵.
- CI: 30/30 lượt sạch trong run chẩn đoán 42376813479; job quarantine của PR #33 (run 42377548910, khi 3 file còn trong quarantine) xanh.
- Các suite khác dùng chung `child_output` hoặc worker: OCR trang, audio, vision OCR, native input/image, worker payload, TTS review worker và 3 file `benchmarks/tests/test_vi_voice_*`: 111 + 98 passed.
- Sau đó 3 file được gỡ khỏi `.github/ci/hosted-runner-quarantine.txt` và chạy trong job CI chính (job chặn merge). Mục `tests/test_page_ocr.py::test_timeout_reaps_worker_and_descendant` có nguyên nhân khác (phụ thuộc thời gian) nên vẫn giữ trong quarantine.

## Giới hạn

- Lần `audio_invalid_content` ghi trong ledger dùng cùng launcher, cùng trần và cùng kiểu lệnh FFmpeg đa luồng. strace cho thấy lệnh audio cũng chạy sát trần. Vì vậy cơ chế này giải thích được lần lỗi đó, nhưng chính sự kiện lịch sử ấy không được tái hiện lại.
- Chỉ sửa launcher `child_output` (OCR, audio, video). `report_export_worker` khởi chạy LibreOffice bằng subprocess riêng, giới hạn riêng, nên không thay đổi.
- Đường `/voice` cũng dùng launcher này cho bước chuyển audio TTS sang playback (`src/infrastructure/voice/native.py` gọi `NativeAudioNormalizer`, qua worker audio rồi `child_output` để chạy ffmpeg), nên thay đổi này chạm vào mã mà B3 đo. B3 PASS ngày 2026-11-07 được đo trước bản sửa, trên commit `73cecdf`; ảnh hưởng của bản sửa tới thời gian B3 chưa được đo. Ngày 2026-11-07 chủ dự án trả lời "Giữ PASS kèm ghi chú" *(owner 2026-11-07, operator record)*: B3 PASS được giữ làm bằng chứng B3 cho release này, kèm ghi chú rằng thay đổi này là khác biệt nguồn duy nhất trong snapshot nguồn của B3 và rủi ro độ trễ chưa đo được chấp nhận; không chạy panel B3 mới. Chi tiết ở [hồ sơ D90](D90_RELEASE_DECISION_DOSSIER.md) và [kết quả B3](D74_MAIN_VOICE_B3_RESULT.md).
- Đây là kết quả test phần mềm, không phải phép đo chất lượng model.
