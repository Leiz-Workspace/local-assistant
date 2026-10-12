# PERSONAL AI LOCAL — DEVELOPMENT LOG

> **Dự án:** SHLDD / Personal AI Local-first  
> **Workspace trên máy Ubuntu của chủ dự án:** `/home/korosaki-ryukai/Workspace/Server/ai`  
> **Vị trí lưu tài liệu trên máy Ubuntu:** `/home/korosaki-ryukai/Workspace/Server/ai/dev_log/dev_log.md`  
> **Giai đoạn:** Phase 1 — Infrastructure, Inference & Model Evaluation  
> **Phạm vi ghi nhận:** Ngày 1–7  
> **Lần biên soạn:** 2026-10-12 (giờ Việt Nam)  
> **Nguyên tắc:** Phân biệt **đã xác nhận từ terminal**, **đã hướng dẫn**, và **chưa xác minh**. Không coi câu lệnh được đề xuất là câu lệnh chắc chắn đã chạy.

---

## 0. Tổng quan và trạng thái

### 0.1. Mục tiêu hệ thống

Xây dựng trợ lý AI cá nhân chạy chủ yếu tại máy riêng: chat tiếng Việt/Anh, reasoning, coding agent, đọc/tạo tài liệu, research web, RAG/memory, vision/voice/video, và mở rộng tool/MCP/skills. Các giai đoạn sau sẽ tạo **FastAPI backend dùng chung**, **CLI**, **Web UI**, agent harness, policy/approval và sandbox. `llama.cpp` chỉ là tầng suy luận model, **không phải** toàn bộ Personal AI.

Chiến lược model đã chọn để thử nghiệm:

1. **CORE:** Qwen3.5-9B gốc, bản GGUF Q6_K lượng tử hóa từ repository cộng đồng `bartowski/Qwen_Qwen3.5-9B-GGUF`.
2. **UNRESTRICTED (đang chờ):** `HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive`, dự kiến GGUF Q6_K. **Chưa có bằng chứng đã tải, chạy hoặc benchmark model này**; chưa cấp quyền shell/file cho profile này.
3. **Inference engine:** `llama.cpp` / `llama-server` với CUDA, API tương thích OpenAI; Ollama tùy chọn, không bắt buộc.
4. **Python:** `uv` quản lý dependency, `.venv` và lockfile; editor là `micro`.

### 0.2. Trạng thái theo ngày

| Ngày | Công việc | Trạng thái dựa trên trao đổi |
|---|---|---|
| 1 | Hardware & environment audit | **Đã xác nhận** |
| 2 | Build `llama.cpp` với CUDA | **Đã xác nhận** |
| 3 | `uv`, GGUF, first inference, non-thinking | **Đã xác nhận** |
| 4 | Synthetic benchmark 512/4K/8K/16K | **Đã xác nhận** |
| 5 | Real API context 16K, retrieval ~12K | **Đã xác nhận** |
| 6 | YAML manifest, Python startup, runtime hash | **Đã xác nhận server `/health` và runtime hash; việc chạy chính xác từ script sau khi sửa YAML chưa có log riêng để đối chiếu** |
| 7 | CORE acceptance smoke tests | **Người dùng cho biết đã đến cuối Ngày 7; chưa thấy output PASS/FAIL của `tests/test_core_acceptance.py` trong hội thoại** |

> **Cảnh báo về lịch:** Các nhãn “Ngày 1–7” là các chặng của roadmap, không được hiểu là mỗi chặng diễn ra đúng một ngày dương lịch. Lệnh và kết quả được ghi theo thứ tự thảo luận. Thời gian thực của từng benchmark chỉ được ghi khi có dữ liệu.

### 0.3. Môi trường phát triển đã xác minh

| Thành phần | Giá trị |
|---|---|
| OS | Ubuntu 26.04.1 LTS, x86_64 |
| CPU | AMD Ryzen 7 7700, 8C/16T |
| GPU | NVIDIA RTX 4070 Ti SUPER, 16,376 MiB theo `nvidia-smi` |
| Driver | 580.178.04 |
| CUDA driver compatibility | 13.0 (`nvidia-smi`; **không phải** toolkit) |
| CUDA Toolkit / `nvcc` | 12.4.131 |
| GCC/G++ mặc định | 15.2.0 |
| GCC/G++ dành riêng cho CUDA build | 13.4.0 |
| Git | 2.53.0 |
| CMake | 4.2.3 |
| Ninja | `/usr/bin/ninja` |
| Python | 3.12.3 |
| uv | 0.9.13 |
| huggingface_hub | 2.2.0 |
| RAM | 30 GiB usable; tại thời điểm kiểm tra ~19 GiB available |
| Swap | 8 GiB |
| Ubuntu root (ext4) | `/dev/sda4`, còn ~650 GiB tại thời điểm kiểm tra |
| HDD Storage (NTFS) | `/dev/sdb2`, còn ~1.4 TiB tại thời điểm kiểm tra |
| Git branch nhìn thấy trong terminal | `production` (cần kiểm tra repo hiện tại nếu cần commit) |

---

## Ngày 1 — Hardware & Environment Audit

**Mục tiêu:** xác minh phần cứng, GPU, CUDA và dung lượng lưu trữ trước khi cài inference runtime.

### 1.1. Các lệnh đã dùng

```bash
cat /etc/os-release
uname -m
nvidia-smi
free -h
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
df -h

lscpu | grep -E 'Model name|CPU\(s\)|Architecture'
git --version
cmake --version
g++ --version
command -v nvcc && nvcc --version || echo "CUDA Toolkit chưa có trong PATH"
nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv
```

### 1.2. Kết quả đáng chú ý

- OS Ubuntu 26.04.1 LTS, CPU Ryzen 7 7700, GPU RTX 4070 Ti SUPER.
- `nvidia-smi` chạy ổn định; VRAM ban đầu khoảng 863 MiB được sử dụng bởi desktop/remote desktop và các ứng dụng khác; có một lần kiểm tra báo còn 15,077 MiB.
- NVIDIA driver 580.178.04 và CUDA Toolkit 12.4 là **hai thành phần khác nhau**; `nvidia-smi` hiển thị driver tương thích CUDA 13.0.
- Ubuntu root ở ext4; các ổ Storage/Games là NTFS. Chọn workspace trên hệ thống file Linux, không thay đổi phân vùng.

### 1.3. Workspace thực tế

Người dùng chọn đường dẫn **khác** đề xuất ban đầu:

```text
/home/korosaki-ryukai/Workspace/Server/ai
```

Cấu trúc mục tiêu (một số thư mục có thể được tạo ở các bước sau):

```text
ai/
├── apps/{api,web}/
├── services/{agent,router,rag}/
├── configs/
├── scripts/
├── tests/
├── docs/ADR/
├── runtimes/llama.cpp/
├── models/{core,unrestricted}/
├── benchmarks/{scripts,results}/
├── dev_log/
├── pyproject.toml
├── uv.lock
└── .venv/
```

Ví dụ lệnh tạo cấu trúc đã được hướng dẫn (việc từng thư mục tồn tại nên đối chiếu trên máy):

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
mkdir -p apps/api apps/web services/agent services/router services/rag \
  configs scripts tests docs/ADR runtimes \
  models/core models/unrestricted benchmarks dev_log
```

**Lưu ý bảo mật/repository:** `.venv/`, `models/`, dữ liệu cá nhân, `secrets/`, `.env` không được commit. Các file benchmark tóm tắt/metadata và `dev_log/dev_log.md` nên được version-control có chọn lọc, tránh chứa bí mật hoặc dữ liệu riêng tư.

**Kết luận Ngày 1:** Đạt — đủ nền tảng phần cứng để triển khai Qwen3.5-9B quantized và CUDA.

---

## Ngày 2 — Build llama.cpp với CUDA

**Mục tiêu:** build inference engine riêng, không phụ thuộc Ollama, tối ưu cho compute capability **8.9 (SM 89)**.

### 2.1. Kiểm tra tương thích GCC/CUDA

CUDA Toolkit 12.4 không hỗ trợ GCC 15 làm host compiler theo giới hạn toolkit; sử dụng GCC/G++ 13 **riêng khi build**, không thay compiler mặc định hệ thống.

```bash
command -v gcc-13
command -v g++-13
apt-cache policy gcc-13 g++-13
command -v ninja
```

Đã xác minh `gcc-13` và `g++-13` **13.4.0-10ubuntu1** đã cài, Ninja có tại `/usr/bin/ninja`. Không cần cài lại CUDA hay driver.

### 2.2. Clone và xác định phiên bản

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai/runtimes
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
git rev-parse HEAD
```

`git rev-parse HEAD` lấy commit chính xác, dùng khi debug, benchmark và rollback.

### 2.3. Configure và build

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai/runtimes/llama.cpp

cmake -S . -B build-cuda -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_CUDA=ON \
  -DCMAKE_C_COMPILER=/usr/bin/gcc-13 \
  -DCMAKE_CXX_COMPILER=/usr/bin/g++-13 \
  -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-13 \
  -DCMAKE_CUDA_ARCHITECTURES=89

cmake --build build-cuda -j 8
```

### 2.4. Kiểm tra bản build

```bash
./build-cuda/bin/llama-server --version
./build-cuda/bin/llama-cli --version
ls -lh build-cuda/bin/llama-server
ldd build-cuda/bin/libggml-cuda.so | grep -E 'cuda|cublas'
```

**Output xác nhận:**

```text
version: 0.6.0-dev (build 11557, commit 5c8854fd8)
built with GNU 13.4.0 for Linux x86_64
```

Các thư viện liên kết được quan sát:

```text
libcudart.so.12
libcublas.so.12
libcuda.so.1
libcublasLt.so.12
```

Commit đầy đủ, về sau đã lưu tại `configs/llama-cpp-commit.txt`:

```text
5c8854fd88319125125dc4b836c98b1b215b0f23
```

**Kết luận Ngày 2:** Build và link CUDA thành công. Link thư viện chưa tự chứng minh inference chạy trên GPU; GPU inference được xác nhận ở Ngày 3–4.

---

## Ngày 3 — uv, GGUF, Model Download & First Inference

### 3.1. Thiết lập uv

Chọn `uv` để thay `venv + pip`:

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
uv --version
uv init --bare
uv venv --python 3.12
uv add huggingface-hub
```

Sự cố gặp phải khi `uv add huggingface-hub`:

```text
Failed to install: click-8.5.0-py3-none-any.whl
The wheel is invalid: Metadata field Name not found
```

- Tại một thời điểm, `uv sync --no-cache -v` chỉ resolved 1 package; import `huggingface_hub` thất bại vì dependency chưa được thêm thành công.
- Đã hướng dẫn làm sạch cache package và thử `uv add huggingface-hub --no-cache`; uv báo không hardlink được cache → fallback copy (warning, không phải lỗi).
- **Mốc đã xác nhận sau khắc phục:**

```bash
uv --version
uv run python --version
uv run python -c "import huggingface_hub; print(huggingface_hub.__version__)"
uv run hf --help
```

```text
uv 0.9.13
Python 3.12.3
huggingface_hub 2.2.0
hf CLI chạy bình thường
```

> Thận trọng: Không khẳng định cơ chế hỏng wheel ban đầu nếu chưa có log từ package index; chỉ biết các bước khắc phục đưa môi trường về trạng thái hoạt động.

### 3.2. Model gốc và lượng tử hóa

- Model gốc: `Qwen/Qwen3.5-9B`.
- Model đã quantize sang GGUF do cộng đồng phát hành: `bartowski/Qwen_Qwen3.5-9B-GGUF`.
- Quantization: `Q6_K` — khoảng 6-bit K-quants cho phần lớn trọng số, cân bằng quality/VRAM.
- Model **không phải uncensored**. **Chưa tải vision projector `mmproj`** trong giai đoạn thử text.

**Lệnh tải đúng tên file** (đã sửa lỗi tên file ở hướng dẫn ban đầu):

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
mkdir -p models/core/qwen3.5-9b
uv run hf download bartowski/Qwen_Qwen3.5-9B-GGUF \
  Qwen_Qwen3.5-9B-Q6_K.gguf \
  --local-dir models/core/qwen3.5-9b

ls -lh models/core/qwen3.5-9b/
sha256sum models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf
```

**Kết quả quan sát:** file ~7.5 GiB theo `ls -lh`, ~7.40 GiB trong `llama-bench`.

```text
SHA-256 (local):
073a9275e65d9c8cd2819cf5f77b99fbaa6e87ba591da6bbaa86ec073a64bfef
```

Checksum **được tính từ file local**, chưa có bằng chứng đã đối chiếu với SHA do nguồn phát hành công bố. Để cải thiện provenance, về sau pin commit/revision của Hugging Face repo và đối chiếu LFS OID/file digest từ nguồn tin cậy.

### 3.3. Chạy thử text inference bằng llama-server

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai

./runtimes/llama.cpp/build-cuda/bin/llama-server \
  --model models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf \
  --alias qwen3.5-9b-core \
  --host 127.0.0.1 \
  --port 8080 \
  --n-gpu-layers 99 \
  --ctx-size 8192 \
  --parallel 1
```

Terminal giám sát:

```bash
watch -n 1 nvidia-smi
curl -s http://127.0.0.1:8080/health
```

Dữ liệu ban đầu:

```text
GPU memory.used: 8304 MiB / 16376 MiB
GET /health: {"status":"ok"}
```

Request đầu tiên:

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"qwen3.5-9b-core",
    "messages":[{"role":"user","content":"Xin chào, hãy giới thiệu bản thân bằng tiếng Việt trong 3 câu."}],
    "max_tokens":512,
    "stream":false
  }'
```

Phản hồi ban đầu không có final `content`, `reasoning_content` dài, `finish_reason=length`; hết 512 token trong phần reasoning. Throughput theo JSON **78.006 tok/s**. Điều này **không** có nghĩa model hoặc GPU hỏng.

### 3.4. Tách Thinking / Non-thinking

Kiểm tra cờ server:

```bash
./runtimes/llama.cpp/build-cuda/bin/llama-server --help 2>&1 | grep -i -A 5 reasoning
```

Đã xác minh có:

```text
--reasoning [on|off|auto]
--reasoning-format FORMAT
--reasoning-budget N
```

Dừng server (`Ctrl+C`), khởi động lại với `--reasoning off`:

```bash
./runtimes/llama.cpp/build-cuda/bin/llama-server \
  --model models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf \
  --alias qwen3.5-9b-core \
  --host 127.0.0.1 \
  --port 8080 \
  --n-gpu-layers 99 \
  --ctx-size 8192 \
  --parallel 1 \
  --reasoning off
```

Kiểm tra chat API:

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"qwen3.5-9b-core",
    "messages":[{"role":"user","content":"Giải thích AI Agent là gì trong đúng 3 câu."}],
    "max_tokens":512,
    "stream":false
  }'
```

**Kết quả xác nhận:**

```text
Content: (3 câu giải thích AI Agent bằng tiếng Việt)
Reasoning: None
Finish reason: stop
Generation speed: 78.4789786098135 tokens/s
```

> `--reasoning off` yêu cầu template tắt thinking; `--reasoning-format` chỉ điều khiển cách tách/hiển thị thought. Hai ý không được đánh đồng.

**Kết luận Ngày 3:** Text model, GPU inference, Web UI mặc định của `llama-server`, REST API và Non-thinking đều đã chạy được. **Web UI này không phải Web UI riêng của Personal AI.**

---

## Ngày 4 — Synthetic Performance Benchmark

**Mục tiêu:** đo prompt processing (PP) và text generation (TG) trong điều kiện lặp lại, cùng runtime và model.

### 4.1. Baseline 512 token

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
./runtimes/llama.cpp/build-cuda/bin/llama-bench \
  -m models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf \
  -ngl 99 -p 512 -n 128 -r 5
```

```text
pp512: 5808.53 ± 151.43 tok/s
tg128:   79.38 ± 0.60 tok/s
```

**Raw log 512 không được lưu bằng `tee` trong lần đầu**, nhưng các số trên được chép từ output thực tế.

### 4.2. Prompt 4K

```bash
./runtimes/llama.cpp/build-cuda/bin/llama-bench \
  -m models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf \
  -ngl 99 -p 4096 -n 128 -r 3 \
  | tee benchmarks/results/qwen3.5-9b-q6k-4k.txt
```

```text
pp4096: 5837.81 ± 37.19 tok/s
tg128:    79.11 ± 0.70 tok/s
```

### 4.3. Prompt 8K

```bash
./runtimes/llama.cpp/build-cuda/bin/llama-bench \
  -m models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf \
  -ngl 99 -p 8192 -n 128 -r 3 \
  | tee benchmarks/results/qwen3.5-9b-q6k-8k.txt
```

```text
pp8192: 5787.35 ± 25.94 tok/s
tg128:    79.79 ± 0.12 tok/s
Observed VRAM high: 8718 MiB
GPU utilization sampling: 100%
Power draw observed: up to 296.60 W
```

### 4.4. Prompt 16K

`llama-bench --help` trên commit hiện tại **không hiển thị `-c` hoặc `--n-ctx`**. Vì vậy benchmark synthetic dùng `-p` để chỉ độ dài prompt; kiểm tra **server context capacity** được thực hiện riêng ở Ngày 5.

```bash
./runtimes/llama.cpp/build-cuda/bin/llama-bench \
  -m models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf \
  -ngl 99 -p 16384 -n 128 -r 3 \
  | tee benchmarks/results/qwen3.5-9b-q6k-16k.txt
```

```text
pp16384: 5603.16 ± 18.34 tok/s
tg128:     79.70 ± 0.15 tok/s
Observed VRAM high: 8961 MiB
GPU utilization sampling: 100%
Power draw observed: up to 296.01 W
```

### 4.5. Bảng kết quả tổng hợp

| Test | PP (tok/s ± spread) | TG128 (tok/s ± spread) | Repetitions |
|---|---:|---:|---:|
| 512 | 5808.53 ± 151.43 | 79.38 ± 0.60 | 5 |
| 4096 | 5837.81 ± 37.19 | 79.11 ± 0.70 | 3 |
| 8192 | 5787.35 ± 25.94 | 79.79 ± 0.12 | 3 |
| 16384 | 5603.16 ± 18.34 | 79.70 ± 0.15 | 3 |

Điều kiện cố định:

```text
Model: Qwen3.5-9B Q6_K, 9.20B params, ~7.40 GiB
Runtime: llama.cpp build 11557, commit 5c8854fd8
Backend: CUDA, n-gpu-layers requested = 99
GPU: RTX 4070 Ti SUPER, SM 8.9
```

**Diễn giải:** `pp` và `tg` trong `llama-bench` là các phép đo riêng. `tg128` **không** có nghĩa model chắc chắn sinh 79 tok/s sau khi đọc 16K token trong cùng hội thoại. `memory.used` là các mẫu quan sát, không bảo đảm bắt được true peak. Tốc độ PP 16K thấp hơn PP 512 khoảng 3.54% trong các thử nghiệm synthetic.

### 4.6. Lưu kết quả (đã hướng dẫn)

Định dạng mục tiêu:

```text
benchmarks/results/qwen3.5-9b-q6k/
├── metadata.json
├── summary.csv
└── raw/
    ├── pp512.txt (chỉ có nếu chạy lại và lưu)
    ├── pp4096.txt
    ├── pp8192.txt
    └── pp16384.txt
```

Các lệnh tổng hợp sang thư mục cấu trúc mới đã được hướng dẫn; **chưa có output xác nhận riêng rằng `summary.csv` và `metadata.json` thực sự được tạo**. Các file `.txt` 4K/8K/16K có lệnh `tee` kèm theo và đã sinh output thành công.

Kiểm tra hiện trạng:

```bash
find benchmarks/results -maxdepth 4 -type f | sort
```

**Kết luận Ngày 4:** Đạt benchmark synthetic đến 16K prompt. Cần thêm thử nghiệm full context và quality.

---

## Ngày 5 — Real 16K Context & Retrieval

### 5.1. Chạy server với context capacity 16K

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
./runtimes/llama.cpp/build-cuda/bin/llama-server \
  --model models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf \
  --alias qwen3.5-9b-core \
  --host 127.0.0.1 --port 8080 \
  --n-gpu-layers 99 --ctx-size 16384 --parallel 1 \
  --reasoning off
```

Server log xác nhận:

```text
n_slots = 1, n_ctx_slot = 16384, kv_unified = 'false'
model loaded
listening on http://127.0.0.1:8080
```

### 5.2. API smoke test với prompt ngắn

Dùng Python stdlib `urllib.request` gửi request POST đến `/v1/chat/completions` và đo `time.perf_counter()`.

```text
Answer: AI Model ... Inference Engine ... AI Agent ...
Finish reason: stop
Total request time: 1.346 s
Prompt tokens: 32
Completion tokens: 96
Generation speed: 78.44536156705756 tok/s
```

Server log:

```text
prompt eval time = 127.17 ms / 32 tokens (~251.62 tok/s)
eval time        = 1211.03 ms / 96 tokens (~78.45 tok/s)
total time       = 1338.21 ms / 128 tokens
truncated = 0
```

**Giới hạn:** Prompt chỉ 32 token, chứng minh 16K capacity chạy được nhưng chưa kiểm tra khả năng đọc 16K token.

### 5.3. Long-context benchmark — lần đầu lỗi 400

Script:

```bash
micro benchmarks/scripts/long_context.py
uv run python benchmarks/scripts/long_context.py
```

Lỗi ban đầu:

```text
urllib.error.HTTPError: HTTP Error 400: Bad Request
```

Sau khi thêm `HTTPError` handler, server trả:

```json
{"error":{"code":400,"message":"request (77510 tokens) exceeds the available context size (16384 tokens), try increasing it","type":"exceed_context_size_error","n_prompt_tokens":77510,"n_ctx":16384}}
```

**Root cause:** Script tạo ~2200 đoạn văn với nhiều token, 77,510 > 16,384. Lỗi không phải CUDA/GPU/model. Từ đây dùng `/tokenize` để đếm token thực tế trước khi gửi.

### 5.4. Script cải tiến

File:

```text
benchmarks/scripts/long_context.py
```

Các chức năng chính của phiên bản đã chạy:

1. Tạo dữ liệu synthetic với `random.Random(42)` để tái lập.
2. Chèn ba facts ở ~5%, 50%, 95% tài liệu.
3. Dùng `POST /tokenize` lấy độ dài prompt; binary search số records sao cho gần 12K token, không vượt target.
4. Để dự phòng token cho chat template và response: `prompt_tokens + max_output_tokens + 128 <= 16384`.
5. Gửi chat completion `temperature=0`, `max_tokens=256`, `stream=false`, `--reasoning off` ở server.
6. So khớp ba mã, ghi JSON kết quả.

Mã cần truy xuất:

```json
{
  "dau": "SHLDD-ALPHA-7291",
  "giua": "SHLDD-BETA-4836",
  "cuoi": "SHLDD-GAMMA-9514"
}
```

Lệnh thực thi:

```bash
uv run python benchmarks/scripts/long_context.py
```

**Kết quả xác nhận từ terminal:**

```text
Prompt tokens (/tokenize): 11971
Actual prompt tokens: 11983
Time: 2.96 s
Answer: {
  "dau": "SHLDD-ALPHA-7291",
  "giua": "SHLDD-BETA-4836",
  "cuoi": "SHLDD-GAMMA-9514"
}
Scores: {'dau': True, 'giua': True, 'cuoi': True}
Accuracy: 100%
Finish reason: stop
Saved: benchmarks/results/qwen3.5-9b-q6k/long-context.json
```

Kết quả đọc lại bằng script kiểm tra:

```text
Model: qwen3.5-9b-core
Context: 16384
Prompt tokens: 11983
Accuracy: 100%
Latency: 2.9587436059991887 s
```

**Giới hạn khoa học:** 100% là **3/3 facts trên một bài test synthetic**, không phải 100% accuracy tổng quát trên mọi ngữ cảnh dài. Kết quả trong ~3 giây có thể chịu ảnh hưởng cache/server state; chưa đo full TTFT, peak VRAM, multiple seeds, multi-turn dài hoặc thông tin gây nhiễu khó.

**Kết luận Ngày 5:** Context 16K chạy được, retrieval ~12K thành công; tạm chọn 16K cho CORE, chưa tuyên bố là cấu hình tối ưu tuyệt đối.

---

## Ngày 6 — CORE Configuration & Startup Automation

**Mục tiêu:** thay lệnh CLI dài bằng YAML manifest và script có thể lặp lại; lưu version nguồn.

### 6.1. Thêm YAML parser

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
uv add pyyaml
```

Lệnh trên đã được hướng dẫn; chưa có output `uv add` riêng nhưng script sau đó đã đọc được cấu hình bằng PyYAML.

### 6.2. Model manifest

Tạo/chỉnh sửa:

```bash
micro configs/models.yaml
```

Cấu hình mẫu đã thống nhất (đối chiếu trạng thái thực tế trước khi ghi đè):

```yaml
models:
  core:
    name: qwen3.5-9b-core
    base_model: Qwen/Qwen3.5-9B
    repository: bartowski/Qwen_Qwen3.5-9B-GGUF
    path: models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf
    quantization: Q6_K
    sha256: 073a9275e65d9c8cd2819cf5f77b99fbaa6e87ba591da6bbaa86ec073a64bfef
    inference:
      engine: llama.cpp
      backend: cuda
      gpu_layers: 99
      context_size: 16384
      parallel: 1
      reasoning: "off"
      host: 127.0.0.1
      port: 8080

  unrestricted:
    name: qwen3.5-9b-unrestricted
    status: pending_benchmark
```

**Giải thích `unrestricted.status`:** chỉ là placeholder profile dự kiến, **không tải hoặc cấp phát VRAM**; startup CORE chỉ đọc `models.core`.

### 6.3. Python startup script

Tạo/chỉnh sửa:

```bash
micro scripts/start-core.py
```

Nội dung theo hướng dẫn (phiên bản cơ bản):

```python
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/models.yaml"

with CONFIG.open(encoding="utf-8") as file:
    data = yaml.safe_load(file)

model = data["models"]["core"]
inference = model["inference"]

reasoning = inference["reasoning"]
if not isinstance(reasoning, str) or reasoning not in {"on", "off", "auto"}:
    raise ValueError('reasoning phải là chuỗi "on", "off" hoặc "auto" trong YAML')

server = ROOT / "runtimes/llama.cpp/build-cuda/bin/llama-server"
model_path = ROOT / model["path"]

if not server.is_file():
    raise SystemExit(f"Không tìm thấy llama-server: {server}")
if not model_path.is_file():
    raise SystemExit(f"Không tìm thấy model: {model_path}")

command = [
    str(server),
    "--model", str(model_path),
    "--alias", model["name"],
    "--host", str(inference["host"]),
    "--port", str(inference["port"]),
    "--n-gpu-layers", str(inference["gpu_layers"]),
    "--ctx-size", str(inference["context_size"]),
    "--parallel", str(inference["parallel"]),
    "--reasoning", reasoning,
]

print("Starting:", model["name"], flush=True)
print("Context:", inference["context_size"], flush=True)
print("API:", f'http://{inference["host"]}:{inference["port"]}', flush=True)

try:
    subprocess.run(command, cwd=ROOT, check=True)
except KeyboardInterrupt:
    print("\nllama-server đã dừng.")
```

> Chú ý: đây là mã *tham chiếu đã hướng dẫn*, không khẳng định file thực tế trên máy được sửa đúng từng ký tự.

### 6.4. Sự cố YAML — `off` thành `False`

Chạy:

```bash
uv run python scripts/start-core.py
```

Ban đầu lỗi:

```text
Starting: qwen3.5-9b-core
Context: 16384
API: http://127.0.0.1:8080
error while handling argument "--reasoning": error: unknown value for --reasoning: 'False'
```

**Root cause:** PyYAML `safe_load` dùng kiểu ngầm YAML 1.1, parse `reasoning: off` thành Boolean `False`. Python `str(False)` → `"False"`, `llama-server` chỉ nhận `on|off|auto`.

**Fix:** sửa YAML thành `reasoning: "off"` (giữ dấu ngoặc kép). Có thể thêm validation trong Python script:

```python
reasoning = inference["reasoning"]
if not isinstance(reasoning, str) or reasoning not in {"on", "off", "auto"}:
    raise ValueError('inference.reasoning phải là "on", "off" hoặc "auto"')
```

Kiểm tra:

```bash
uv run python -c '
import yaml
with open("configs/models.yaml") as f:
    config = yaml.safe_load(f)
v = config["models"]["core"]["inference"]["reasoning"]
print(v, type(v).__name__)
'
```

Mong đợi: `off str`.

### 6.5. API Health & Runtime Hash

Người dùng xác nhận:

```bash
curl -s http://127.0.0.1:8080/health
```

```json
{"status":"ok"}
```

Sau đó đã chạy và lưu:

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
mkdir -p configs
git -C runtimes/llama.cpp rev-parse HEAD > configs/llama-cpp-commit.txt
cat configs/llama-cpp-commit.txt
```

```text
5c8854fd88319125125dc4b836c98b1b215b0f23
```

**Lưu ý trạng thái:** `/health` chứng minh có `llama-server` đang nghe và sẵn sàng, nhưng riêng output này **không cho thấy PID server có chắc được khởi động bằng `scripts/start-core.py` sau khi sửa YAML hay không**. Muốn xác minh đầy đủ:

```bash
ps -ef | grep '[l]lama-server'
curl -s http://127.0.0.1:8080/health
```

**Kết luận Ngày 6:** Manifest, lệnh startup, kiến thức xử lý YAML và version pin đã được triển khai theo tiến trình trao đổi; runtime hash và API health có output xác nhận.

---

## Ngày 7 — CORE Acceptance Test & Architecture Checkpoint

**Mục tiêu:** smoke-test khả năng tiếng Việt, toán cơ bản, JSON; xác nhận ranh giới giữa inference engine và Personal AI platform.

### 7.1. Acceptance test được hướng dẫn

File dự kiến:

```text
tests/test_core_acceptance.py
```

Mở bằng `micro`:

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
micro tests/test_core_acceptance.py
```

Nội dung theo hướng dẫn:

```python
import json
import urllib.request

API = "http://127.0.0.1:8080/v1/chat/completions"
MODEL = "qwen3.5-9b-core"

tests = [
    {
        "name": "Vietnamese",
        "prompt": "Hãy trả lời bằng đúng một từ: Xin chào.",
        "expected": "Xin chào"
    },
    {
        "name": "Arithmetic",
        "prompt": "Tính 17 nhân 23. Chỉ trả về kết quả.",
        "expected": "391"
    },
    {
        "name": "JSON",
        "prompt": 'Chỉ trả về JSON hợp lệ: {"status":"ok","count":3}',
        "expected_json": {"status": "ok", "count": 3}
    }
]

def chat(prompt):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 256,
        "stream": False
    }
    request = urllib.request.Request(
        API,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)["choices"][0]["message"]["content"]

for test in tests:
    answer = chat(test["prompt"]).strip()
    if "expected_json" in test:
        try:
            passed = json.loads(answer) == test["expected_json"]
        except json.JSONDecodeError:
            passed = False
    else:
        passed = answer == test["expected"]
    print(f'{"PASS" if passed else "FAIL"} | {test["name"]}')
    print("  Answer:", answer)
```

Chạy:

```bash
uv run python tests/test_core_acceptance.py
```

**Tình trạng bằng chứng:** Chưa có output `PASS/FAIL` của test này trong hội thoại. Người dùng vừa cho biết “bây giờ là vừa xong ngày 7”; ghi nhận đây là **mốc tiến độ do chủ dự án xác nhận**, nhưng **không tự điền kết quả test thành PASS**. Trước ngày 8, nên chạy và lưu bằng `tee`:

```bash
mkdir -p benchmarks/results/qwen3.5-9b-q6k
uv run python tests/test_core_acceptance.py 2>&1 \
  | tee benchmarks/results/qwen3.5-9b-q6k/core-acceptance-day7.txt
```

> Về chất lượng test: Kiểm tra tiếng Việt bằng equality tuyệt đối dễ FAIL vì dấu câu/cách diễn đạt; là smoke test chứ chưa phải quality benchmark. Kiểm tra JSON nên đánh giá parser và schema, không chỉ so sánh chuỗi.

### 7.2. Kiến trúc API, CLI, Web UI (đã bàn, chưa triển khai)

```text
       Web UI (tương lai)       CLI (tương lai)
               \                 /
                \               /
                 FastAPI backend (tương lai)
                  ├── Model Router
                  ├── Agent Harness / Tools / Approval
                  ├── Documents / RAG / Memory
                  └── Provider Adapter
                           |
                   llama-server (đã có)
                           |
                   Qwen3.5-9B Q6_K (đã có)
                           |
                   RTX 4070 Ti SUPER
```

**Đã có:** API `http://127.0.0.1:8080/v1/chat/completions` và UI mặc định của `llama-server`. **Chưa có:** backend API, CLI, web app riêng của Personal AI; chưa có agent, tool runner, RAG, auth, sandbox. Đây là các phần ở giai đoạn kế tiếp.

Roadmap điều chỉnh: sau benchmark Uncensored ngày 8–14, dự kiến FastAPI backend v0.1 (ngày 15–17), CLI v0.1 (18–19), Web UI v0.1 (20–22), sau đó RAG/docs. Đây là **kế hoạch**, không phải feature đã hoàn thành.

### 7.3. Quyết định kỹ thuật đến cuối ngày 7

1. Sử dụng Ubuntu native + CUDA build của `llama.cpp`.
2. Sử dụng `uv`, `micro`.
3. Model CORE là Qwen3.5-9B Q6_K, `reasoning: "off"` mặc định; thinking bật theo tác vụ sau khi kiểm thử.
4. Context 16,384 là cấu hình **thử nghiệm mặc định**, cần đo VRAM/TTFT/retrieval đa dạng trước khi coi tối ưu.
5. API inference bind `127.0.0.1`; không mở trực tiếp ra Internet.
6. Tách hoàn toàn inference runtime và FastAPI backend/CLI/Web UI tương lai.
7. Profile Uncensored **pending_benchmark**; chưa thay CORE và chưa được tự thực thi tool nhạy cảm.

**Kết luận Ngày 7:** Đã đến checkpoint cuối tuần 1 theo xác nhận của người dùng. Các smoke test chưa có bằng chứng đầu ra và là mục cần xác thực bổ sung.

---

## 8. Known issues, fixes & lessons learned

| Mã | Vấn đề | Root cause / quan sát | Cách xử lý |
|---|---|---|---|
| I-001 | CUDA 12.4 + GCC 15 | Toolkit không hỗ trợ GCC mặc định quá mới | Chỉ định GCC/G++ 13 cho CMake CUDA build |
| I-002 | `uv add` lỗi wheel `click` | Wheel báo thiếu metadata `Name`; nguyên nhân upstream chưa chứng minh | Cache/retry/no-cache; cuối cùng `huggingface_hub` import thành công |
| I-003 | `uv` warning hardlink | Fallback từ hardlink sang copy | Warning; có thể chọn link-mode copy, không ảnh hưởng inference |
| I-004 | Tên GGUF sai trong hướng dẫn đầu | File thực tế mang prefix `Qwen_Qwen3.5-9B-` | Tải chính xác `Qwen_Qwen3.5-9B-Q6_K.gguf` |
| I-005 | Chat request trả `content` rỗng | `max_tokens=512` tiêu hết trong reasoning, `finish_reason=length` | `--reasoning off` cho thử nghiệm non-thinking |
| I-006 | Long context HTTP 400 | Prompt 77,510 > context 16,384 | Đếm token qua `/tokenize`, resize gần 12K |
| I-007 | `--reasoning False` | PyYAML parse `off` thành Boolean | YAML `reasoning: "off"` + Python validation |
| I-008 | Không lưu raw benchmark 512 lần đầu | Không dùng `tee` | Lưu lại từ output đã có, chạy lại nếu cần raw log |
| I-009 | Dễ nhầm model/UI API | `llama-server` không phải backend Personal AI | Thiết kế adapter/FastAPI riêng giai đoạn sau |

---

## 9. Cấu hình, bảo mật và tái lập

### 9.1. Files quan trọng

```text
configs/models.yaml                          # Model/profile manifest
configs/llama-cpp-commit.txt                # Version chính xác llama.cpp
scripts/start-core.py                       # Khởi động CORE từ YAML
tests/test_core_acceptance.py                # Smoke tests (chưa có output xác minh)
benchmarks/scripts/long_context.py          # Synthetic long-context retrieval
benchmarks/results/qwen3.5-9b-q6k/...      # Logs/results
models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf  # File trọng số (không commit)
```

### 9.2. Health và version commands

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
curl -s http://127.0.0.1:8080/health
cat configs/llama-cpp-commit.txt
uv --version
uv run python --version
uv run python -c 'import huggingface_hub; print(huggingface_hub.__version__)'
nvidia-smi
```

### 9.3. Khởi động và dừng

```bash
# Mở terminal thứ nhất; bảo đảm server cũ không chạy cùng cổng
cd /home/korosaki-ryukai/Workspace/Server/ai
uv run python scripts/start-core.py

# Mở terminal thứ hai
curl -s http://127.0.0.1:8080/health
```

Dừng ở terminal đang chạy bằng `Ctrl+C`. Không chạy đồng thời hai model 9B Q6_K khi chưa có VRAM budget rõ ràng.

### 9.4. Git hygiene

- Giữ `.env`, `secrets`, model weights và local private data ngoài Git.
- Kiểm tra `.gitignore`: trước đó có mẫu bỏ qua `benchmarks/results/`; muốn commit `summary.csv`, `metadata.json` hoặc `dev_log.md` phải điều chỉnh ignore có chủ đích.
- Pin nguồn model: lưu `base_model`, GGUF repo, revision, file SHA-256, `llama.cpp` commit, CUDA/driver/compiler, flags inference.
- Không đưa lời nhắc chứa secret/dữ liệu người dùng vào log công khai.

---

## 10. Checklist sau ngày 7 / trước ngày 8

- [x] Ubuntu/GPU/CUDA xác minh.
- [x] llama.cpp CUDA build và version ghi lại.
- [x] Qwen3.5-9B Q6_K tải và nạp thành công.
- [x] Chat API và non-thinking mode hoạt động.
- [x] Synthetic PP/TG 512/4K/8K/16K có kết quả.
- [x] Server 16K + retrieval gần 12K đạt 3/3 facts.
- [x] API health và full runtime commit có output xác nhận.
- [ ] Xác nhận `start-core.py` sau sửa YAML là tiến trình đang phục vụ API (nếu cần kiểm toán chặt).
- [ ] Chạy và lưu output Ngày 7 của `tests/test_core_acceptance.py`.
- [ ] Kiểm tra `metadata.json`/`summary.csv` và các raw log đã tồn tại.
- [ ] Đối chiếu checksum/revision model với nguồn phát hành.
- [ ] Ghi nhận VRAM peak thực tế và TTFT trên prompt dài, nhiều seed.
- [ ] Ngày 8–14: xác minh nguồn, tải, chạy và benchmark Uncensored cùng bộ test; chỉ chốt sau khi có kết quả.

---

## 11. Mẫu nhật ký cho ngày tiếp theo

> **Cách cập nhật:** Sau mỗi ngày triển khai, bổ sung một mục vào **cuối tài liệu này**, không ghi đè dữ liệu benchmark cũ. Phân biệt lệnh đã chạy, output quan sát, thay đổi cấu hình và open issues. Ngày 8 sẽ nằm trong cùng Phase 1; sang Phase 2 thêm heading giai đoạn mới.

```markdown
## Ngày 8 — [Tên công việc]

**Ngày ghi nhận:** YYYY-MM-DD  
**Mục tiêu:** ...  
**Trạng thái:** Đã xác minh / Một phần / Chưa hoàn thành

### Các lệnh đã chạy
\`\`\`bash
# ...
\`\`\`

### Kết quả thực tế
- Output / file / benchmark / metrics: ...

### Vấn đề và cách xử lý
- Error: ...
- Root cause: ...
- Fix / workaround: ...

### Artifacts / commit
- File tạo/sửa: ...
- llama.cpp commit: ...
- Model sha256: ...

### Việc còn lại
- [ ] ...
```

### Cập nhật tự động?

Tài liệu này là snapshot được tạo từ hội thoại. Trợ lý **không thể tự sửa file trên ổ đĩa Ubuntu mỗi ngày** nếu không có quyền truy cập file/automation phù hợp. Khi hoàn thành Ngày 8, hãy gửi log và yêu cầu cập nhật; tôi sẽ tạo bản `dev_log.md` mới giữ nguyên lịch sử, để bạn chép đè vào cùng đường dẫn. Việc đặt file trong `dev_log/` **không** làm ChatGPT tự đồng bộ với máy bạn.

---

## 12. Nguồn nội bộ / giới hạn xác minh

- Lệnh, số liệu, SHA-256 và trích xuất output: lấy từ các đoạn Terminal người dùng đã gửi trong cuộc hội thoại triển khai Giai đoạn 1.
- Các lệnh chưa có output xác nhận được gắn nhãn “đã hướng dẫn”, “mẫu” hoặc “chưa xác minh”.
- Không có quyền kiểm tra trực tiếp workspace ở máy Ubuntu của người dùng; đường dẫn `/home/korosaki-ryukai/...` là vị trí **để người dùng lưu**, không phải vị trí trợ lý đã ghi trực tiếp.
- Model quality/NSFW refusals, coding benchmark, tool-call reliability và multimodal chưa được thử nghiệm đủ tại checkpoint này.
