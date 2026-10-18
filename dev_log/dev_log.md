# PERSONAL AI LOCAL — DEVELOPMENT LOG

> **Dự án:** SHLDD / Personal AI Local-first  
> **Workspace trên máy Ubuntu của chủ dự án:** `/home/korosaki-ryukai/Workspace/Server/ai`  
> **Vị trí lưu tài liệu trên máy Ubuntu:** `/home/korosaki-ryukai/Workspace/Server/ai/dev_log/dev_log.md`  
> **Giai đoạn:** Phase 1 — Infrastructure, Inference & Model Evaluation  
> **Phạm vi ghi nhận:** Ngày 1–10  
> **Lần biên soạn:** 2026-10-12 (giờ Việt Nam)  
> **Nguyên tắc:** Phân biệt **đã xác nhận từ terminal**, **đã hướng dẫn**, và **chưa xác minh**. Không coi câu lệnh được đề xuất là câu lệnh chắc chắn đã chạy.

---

## 0. Tổng quan và trạng thái

### 0.1. Mục tiêu hệ thống

Xây dựng trợ lý AI cá nhân chạy chủ yếu tại máy riêng: chat tiếng Việt/Anh, reasoning, coding agent, đọc/tạo tài liệu, research web, RAG/memory, vision/voice/video, và mở rộng tool/MCP/skills. Các giai đoạn sau sẽ tạo **FastAPI backend dùng chung**, **CLI**, **Web UI**, agent harness, policy/approval và sandbox. `llama.cpp` chỉ là tầng suy luận model, **không phải** toàn bộ Personal AI.

Chiến lược model đã chọn để thử nghiệm:

1. **CORE:** Qwen3.5-9B gốc, bản GGUF Q6_K lượng tử hóa từ repository cộng đồng `bartowski/Qwen_Qwen3.5-9B-GGUF`.
2. **UNRESTRICTED (đã kiểm thử bước đầu):** `HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive` GGUF Q6_K, đã chạy inference, đối chiếu SHA-256 và benchmark throughput tới 16K sau khi giải phóng VRAM; chưa cấp quyền shell/file cho profile này.
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
| 7 | CORE acceptance smoke tests | **Chưa có output riêng từ `tests/test_core_acceptance.py`; sang Ngày 10 đã có benchmark chất lượng 10 test/model** |
| 8 | Uncensored model download, SHA-256, first inference | **Đã xác nhận hội thoại và SHA-256 theo output gửi** |
| 9 | Uncensored throughput 512/4K/8K/16K, xử lý CUDA OOM | **Đã xác nhận; 16K chạy thành công sau khi dừng tiến trình cạnh tranh VRAM** |
| 10 | CORE vs Uncensored quality smoke benchmark v0.1 | **Đã có output tổng hợp: hai model đều 8/10; chưa đủ để kết luận tương đương năng lực** |

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

## Ngày 8 — Tải, xác minh và chạy Qwen3.5-9B Uncensored

**Mục tiêu:** triển khai profile `unrestricted` tách khỏi CORE; xác nhận nguồn GGUF, checksum và khả năng sinh phản hồi qua API. **Trạng thái:** xác nhận inference và SHA-256; chưa benchmark đầy đủ năng lực, tool safety, vision, refusal.

### 8.1. Model và quyết định thiết kế

| Thuộc tính | Giá trị |
|---|---|
| Profile | `unrestricted` |
| Model GGUF | `Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf` |
| Hugging Face repo | `HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive` |
| Base model công bố | `Qwen/Qwen3.5-9B` |
| Đường dẫn local | `models/unrestricted/qwen3.5-9b/` |
| Backend | `llama.cpp` CUDA, commit `5c8854fd8` (b11557) |
| Inference | `--n-gpu-layers 99 --ctx-size 16384 --parallel 1 --reasoning off` |
| Quyền agent | **Chưa cho phép thực thi shell/file tự động** |

### 8.2. Các lệnh triển khai

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
mkdir -p models/unrestricted/qwen3.5-9b

# Tải riêng GGUF Q6_K, không tải toàn bộ repository
uv run hf download \
  HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive \
  Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf \
  --local-dir models/unrestricted/qwen3.5-9b

# Tính checksum tại máy
sha256sum \
  models/unrestricted/qwen3.5-9b/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf
```

**SHA-256 do Terminal của người dùng trả về (đã xác nhận):**

```text
c0ba7beb68fd3fe47891bd549486d38dcf62d00817296ea314ad37017f5a4986
```

Giá trị trên trùng checksum repository đã ghi nhận trong quá trình triển khai. **Checksum khớp không bảo đảm model không bị can thiệp ở cấp nguồn phát hành hay không suy giảm năng lực.** Chưa có commit/revision repo cụ thể được pin.

Chạy server bằng cách **dừng CORE trước** (`Ctrl+C` tại terminal tương ứng) rồi:

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
./runtimes/llama.cpp/build-cuda/bin/llama-server \
  --model models/unrestricted/qwen3.5-9b/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf \
  --alias qwen3.5-9b-unrestricted \
  --host 127.0.0.1 --port 8080 \
  --n-gpu-layers 99 --ctx-size 16384 --parallel 1 --reasoning off
```

Request kiểm tra tương ứng:

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"qwen3.5-9b-unrestricted",
    "messages":[{"role":"user","content":"Giải thích AI Agent là gì trong đúng 3 câu tiếng Việt."}],
    "temperature":0,"max_tokens":256,"stream":false
  }'
```

### 8.3. Kết quả quan sát

- Model trả lời bằng tiếng Việt với **3 câu** giải thích AI Agent.
- `Reasoning: None` → chế độ non-thinking hoạt động trong phép thử.
- `Finish reason: stop` → phản hồi hoàn tất.
- `Generation speed: 79.56130500682313 tok/s` → **một request**, không phải TPS trung bình.
- Chưa có log VRAM riêng tại lần này; **không ghi thành số đo đã xác nhận**.

**Đánh giá:** đạt smoke test hội thoại; chưa kết luận chất lượng uncensored so với CORE.

---

## Ngày 9 — Benchmark hiệu năng bản Uncensored và xử lý CUDA OOM

**Mục tiêu:** đo throughput theo prompt 512, 4K, 8K, 16K; lưu raw log và kiểm tra giới hạn VRAM. **Trạng thái:** hoàn thành cả bốn mức sau khi xử lý vấn đề tranh chấp VRAM.

### 9.1. Lệnh benchmark và lưu log

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
mkdir -p benchmarks/results/qwen3.5-9b-unrestricted/raw

MODEL='models/unrestricted/qwen3.5-9b/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf'
BENCH='./runtimes/llama.cpp/build-cuda/bin/llama-bench'

"$BENCH" -m "$MODEL" -ngl 99 -p 512 -n 128 -r 5 \
  2>&1 | tee benchmarks/results/qwen3.5-9b-unrestricted/raw/pp512.txt

for TOKENS in 4096 8192 16384; do
  "$BENCH" -m "$MODEL" -ngl 99 -p "$TOKENS" -n 128 -r 3 \
    2>&1 | tee "benchmarks/results/qwen3.5-9b-unrestricted/raw/pp${TOKENS}.txt"
  if [ "${PIPESTATUS[0]}" -ne 0 ]; then
    echo "Benchmark thất bại ở $TOKENS tokens"
    break
  fi
done
```

**Chú ý:** lệnh `tee` ghi đè file cùng tên. Để giữ lịch sử benchmark thất bại và chạy lại, nên dùng hậu tố theo thời gian hoặc tên thử nghiệm khác nhau. Các log của lần chạy lại có thể đã thay thế log cũ nếu dùng chính xác đường dẫn trên.

### 9.2. Benchmark Uncensored đã quan sát

| Số token prompt | PP (tok/s) | TG 128 (tok/s) | Số lần lặp | Trạng thái |
|---:|---:|---:|---:|---|
| 512 | 5.492,73 ± 121,07 | 80,97 ± 0,46 | 5 | PASS |
| 4.096 — lần đầu | 5.503,48 ± 3,43 | 81,09 ± 0,26 | 3 | PASS |
| 8.192 — lần đầu | 5.406,93 ± 26,88 | 80,59 ± 0,57 | 3 | PASS |
| 16.384 — lần đầu | — | — | 3 dự kiến | **CUDA OOM** |
| 4.096 — chạy lại | **5.510,67 ± 27,60** | **80,39 ± 0,67** | 3 | PASS |
| 8.192 — chạy lại | **5.427,26 ± 24,04** | **80,38 ± 0,61** | 3 | PASS |
| 16.384 — chạy lại | **5.244,77 ± 9,78** | **80,32 ± 0,63** | 3 | **PASS** |

Thiết bị: RTX 4070 Ti SUPER (CUDA 8.9); model hiển thị trong `llama-bench`: **8,95 B params, 6,84 GiB**. Runtime: `5c8854fd8` (11557).

### 9.3. Lỗi OOM và cách khắc phục

Lần đầu tại 16K:

```text
ggml_backend_cuda_buffer_type_alloc_buffer: allocating 533.02 MiB on device 0: cudaMalloc failed: out of memory
ggml_gallocr_reserve_n_impl: failed to allocate CUDA0 buffer of size 558913664
graph_reserve: failed to allocate compute buffers
llama_bench: error: failed to create context
```

Kiểm tra tiến trình và VRAM:

```bash
pgrep -af 'llama-server|llama-bench'
nvidia-smi --query-gpu=memory.used,memory.free --format=csv
```

Người dùng xác nhận **dừng tiến trình đang chạy thì thử lại được**. Điều này là bằng chứng mạnh về tranh chấp VRAM giữa các tiến trình, không phải giới hạn kiến trúc cố định của Uncensored. Lần chạy lại 16K hoàn thành, nhưng **tham số batch/micro-batch của lần chạy lại chưa được gửi nguyên văn**, nên không khẳng định mọi điều kiện đo giống hệt CORE. Gợi ý `-b 512 -ub 128` trước đó là **đã hướng dẫn**, không mặc định là đã dùng.

### 9.4. So sánh với CORE (theo số liệu đã báo)

| Prompt | CORE PP (tok/s) | Uncensored PP mới nhất (tok/s) | Chênh lệch tương đối |
|---:|---:|---:|---:|
| 512 | 5.808,53 | 5.492,73 | −5,4% |
| 4.096 | 5.837,81 | 5.510,67 | −5,6% |
| 8.192 | 5.787,35 | 5.427,26 | −6,2% |
| 16.384 | 5.603,16 | 5.244,77 | −6,4% |

Không suy ra bản Uncensored bị suy giảm **năng lực nhận thức** từ chênh lệch PP/TG. Hai file GGUF khác nhau về số tham số và dung lượng: CORE 9,20B/7,40 GiB; Uncensored 8,95B/6,84 GiB. Cần xác minh model metadata/chat template và điều kiện đo trước khi diễn giải chênh lệch như tác động riêng của abliteration.

**Quyết định:** GPU 16GB nên chạy **một model 9B Q6_K tại một thời điểm** khi cần dành VRAM cho context dài; router về sau phải hỗ trợ unload/load model.

---

## Ngày 10 — Quality Benchmark v0.1: CORE so với Uncensored

**Mục tiêu:** kiểm tra sơ bộ reasoning, toán, coding, tiếng Việt, tuân thủ chỉ dẫn, JSON và tool calling trên cùng bộ prompt. **Trạng thái:** đã chạy xong 10 bài cho mỗi model; kết quả bằng nhau nhưng bộ kiểm thử còn nhỏ.

### 10.1. Bộ kiểm thử và thao tác

Script được hướng dẫn tạo tại:

```text
benchmarks/scripts/quality_benchmark.py
```

Gồm **9 bài hỏi đáp** với chấm điểm tự động và **1 bài tool calling** tới `get_weather(city)`. Dùng `temperature=0`, `max_tokens=256`, `stream=false`, server `--reasoning off`. **Tool test chỉ kiểm tra model phát sinh lời gọi công cụ; không thực thi công cụ ngoài đời.**

```bash
# Với Uncensored đã khởi động và đúng model alias
uv run python benchmarks/scripts/quality_benchmark.py \
  --model qwen3.5-9b-unrestricted --profile unrestricted

# Dừng Uncensored trước, khởi động lại CORE ở terminal khác:
uv run python scripts/start-core.py

# Tại terminal benchmark:
uv run python benchmarks/scripts/quality_benchmark.py \
  --model qwen3.5-9b-core --profile core
```

File kết quả được báo cáo từ script:

```text
benchmarks/results/quality/core.json
benchmarks/results/quality/unrestricted.json
```

### 10.2. Kết quả thực tế

| Tiêu chí | CORE | Uncensored |
|---|---:|---:|
| Toán học | 2/2 | 2/2 |
| Reasoning | 2/2 | 2/2 |
| Coding | 1/2 | 1/2 |
| Tiếng Việt | 1/1 | 1/1 |
| Instruction following | 1/1 | 1/1 |
| JSON strict | 0/1 | 0/1 |
| Tool calling | 1/1 | 1/1 |
| **Tổng** | **8/10 = 80,0%** | **8/10 = 80,0%** |

Hai model **cùng sai hai bài**:

1. **`code_02` — lỗi nội dung:** prompt `Python: print(10 // 3). Chỉ trả về kết quả được in.`; cả hai trả `2`, trong khi Python 3 đúng là **`3`**. Đây là lỗi thực, không chỉnh điểm sau khi xem giải thích.
2. **`json_01` — lỗi strict formatting:** cả hai tạo đúng object `{"status":"ok","count":3}`, nhưng bọc trong Markdown fenced code block (```json ... ```), khiến `json.loads(answer)` không parse được trực tiếp. **JSON semantic: đúng; raw JSON strict: sai.**

Phân biệt hai thước đo JSON trong vòng kiểm thử tiếp:

| Thước đo | Ý nghĩa | CORE | Uncensored |
|---|---|---|---|
| `json_semantic` | Object được diễn đạt đúng sau khi tách fence | PASS | PASS |
| `json_strict` | `json.loads(raw_content)` thành công nguyên bản | FAIL | FAIL |

### 10.3. Tập lệnh xem các FAIL đã dùng

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
uv run python - <<'PYCODE'
import json
from pathlib import Path
root = Path('benchmarks/results/quality')
for name in ('core', 'unrestricted'):
    d = json.loads((root / f'{name}.json').read_text(encoding='utf-8'))
    print(f"\nMODEL: {name}")
    print(f"SCORE: {d['passed']}/{d['test_count']}")
    print(f"ACCURACY: {d['score']:.1%}")
    for case in d['results']:
        if not case['passed']:
            print('FAIL:', case['id'])
            print('ERROR:', case.get('error'))
            print('ANSWER:', str(case.get('answer'))[:500])
PYCODE
```

### 10.4. Quyết định và giới hạn

- **Chưa có model thắng:** cùng 8/10 chỉ cho biết cùng đạt ở **mẫu nhỏ 10 bài**, không đủ chứng minh chất lượng tương đương trong coding agent thực tế hoặc sai khác dưới 5 điểm phần trăm.
- Giữ **CORE làm model mặc định**, Uncensored làm profile tùy chọn, chưa có quyền thực thi tool/file/shell tự động.
- Ngày 11–12 mở rộng coding tests thực thi trong sandbox, tool calling nhiều bước, structured outputs với schema, vision khi có mmproj và kiểm tra hồi quy khả năng tuân thủ chỉ dẫn.
- `json_01` trong điểm 8/10 **không được tự động đổi thành PASS**: có thể thêm metric semantic bên cạnh strict score.
- Chưa có bộ kiểm thử NSFW/refusal hợp pháp đủ lớn và chưa có đánh giá security prompt-injection.

### 10.5. Kết quả cần giữ nguyên để tái lập

```text
CORE:         8/10 (80.0%)
UNRESTRICTED: 8/10 (80.0%)
Shared FAIL:  code_02, json_01
Decision:     No winner. Keep CORE default pending expanded evaluation.
```

---

## 11. Known issues, fixes & lessons learned

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

## 12. Cấu hình, bảo mật và tái lập

### 12.1. Files quan trọng

```text
configs/models.yaml                          # Model/profile manifest
configs/llama-cpp-commit.txt                # Version chính xác llama.cpp
scripts/start-core.py                       # Khởi động CORE từ YAML
tests/test_core_acceptance.py                # Smoke tests (chưa có output xác minh)
benchmarks/scripts/long_context.py          # Synthetic long-context retrieval
benchmarks/results/qwen3.5-9b-q6k/...      # Logs/results
models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf  # File trọng số (không commit)
```

### 12.2. Health và version commands

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
curl -s http://127.0.0.1:8080/health
cat configs/llama-cpp-commit.txt
uv --version
uv run python --version
uv run python -c 'import huggingface_hub; print(huggingface_hub.__version__)'
nvidia-smi
```

### 12.3. Khởi động và dừng

```bash
# Mở terminal thứ nhất; bảo đảm server cũ không chạy cùng cổng
cd /home/korosaki-ryukai/Workspace/Server/ai
uv run python scripts/start-core.py

# Mở terminal thứ hai
curl -s http://127.0.0.1:8080/health
```

Dừng ở terminal đang chạy bằng `Ctrl+C`. Không chạy đồng thời hai model 9B Q6_K khi chưa có VRAM budget rõ ràng.

### 12.4. Git hygiene

- Giữ `.env`, `secrets`, model weights và local private data ngoài Git.
- Kiểm tra `.gitignore`: trước đó có mẫu bỏ qua `benchmarks/results/`; muốn commit `summary.csv`, `metadata.json` hoặc `dev_log.md` phải điều chỉnh ignore có chủ đích.
- Pin nguồn model: lưu `base_model`, GGUF repo, revision, file SHA-256, `llama.cpp` commit, CUDA/driver/compiler, flags inference.
- Không đưa lời nhắc chứa secret/dữ liệu người dùng vào log công khai.

---

## 13. Checklist kết thúc Ngày 10 / trước Ngày 11

- [x] Ngày 1–6: phần cứng, runtime CUDA, CORE Q6_K, API, benchmark PP/TG và long-context 12K.
- [x] Đã ghi commit `5c8854fd88319125125dc4b836c98b1b215b0f23` cho `llama.cpp`.
- [x] Ngày 8: bản Uncensored đã sinh phản hồi tiếng Việt; SHA-256 đã đối chiếu.
- [x] Ngày 9: throughput Uncensored 512/4K/8K/16K đã có số đo; xử lý OOM bằng dừng tiến trình cạnh tranh GPU.
- [x] Ngày 10: 10 bài/model, cả CORE và Uncensored 8/10, cùng FAIL `code_02`, `json_01`.
- [ ] Chưa nhận log riêng của bài Ngày 7 `tests/test_core_acceptance.py`; không đánh dấu là PASS.
- [ ] Chưa pin revision của model repositories và xác minh metadata/architecture giữa hai GGUF.
- [ ] Chưa xác nhận batch/micro-batch của lần chạy lại Uncensored 16K, cần lưu lệnh đầy đủ.
- [ ] Cải tiến benchmark JSON semantic/strict, tool-call validation, coding execution, nhiều test/seed và vision.
- [ ] Ngày 11–12: mở rộng benchmark chất lượng trước khi chốt model.
- [ ] Ngày 13–14: weighted scorecard, release gate và cập nhật dev log.

---

## 14. Mẫu nhật ký cho ngày tiếp theo

> **Cách cập nhật:** Sau mỗi ngày triển khai, bổ sung một mục vào phần nhật ký theo thứ tự ngày (trước mục Known issues nếu cần), không ghi đè dữ liệu đã xác nhận, không ghi đè dữ liệu benchmark cũ. Phân biệt lệnh đã chạy, output quan sát, thay đổi cấu hình và open issues. Ngày 11 sẽ nằm trong cùng Phase 1; sang Phase 2 thêm heading giai đoạn mới.

```markdown
## Ngày 11 — [Tên công việc]

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

## 15. Nguồn nội bộ / giới hạn xác minh

- Lệnh, số liệu, SHA-256 và trích xuất output: lấy từ các đoạn Terminal người dùng đã gửi trong cuộc hội thoại triển khai Giai đoạn 1.
- Các lệnh chưa có output xác nhận được gắn nhãn “đã hướng dẫn”, “mẫu” hoặc “chưa xác minh”.
- Không có quyền kiểm tra trực tiếp workspace ở máy Ubuntu của người dùng; đường dẫn `/home/korosaki-ryukai/...` là vị trí **để người dùng lưu**, không phải vị trí trợ lý đã ghi trực tiếp.
- Đã có quality smoke benchmark 10 bài/model đến Ngày 10; NSFW refusal hợp pháp, coding thực thi, tool-call reliability đa bước, vision và multimodal chưa được thử nghiệm đủ tại checkpoint này.


---

# BỔ SUNG — Checkpoint Runtime V1 (ghi nhận 2026-10-16)

> **Nguyên tắc lịch sử:** Bản gốc Ngày 1–10 và các checklist trước đó được giữ nguyên ở trên. Mục này ghi nhận các bước đã thực sự được báo cáo sau snapshot cũ. Ngày ghi nhận là 2026-10-16, **không khẳng định tất cả công việc dưới đây đều được thực hiện đúng ngày đó**. Checklist cũ ở phần 13 phản ánh trạng thái tại thời điểm snapshot cũ, không thay thế checkpoint mới.

## Ngày 11 — Multimodal, long-context và Docker runtime (bổ sung lịch sử)

**Trạng thái:** Đã có xác nhận từng phần qua terminal; một số benchmark trước checkpoint chưa đủ raw log để tái dựng chi tiết tuyệt đối.

- CORE: `Qwen_Qwen3.5-9B-Q6_K.gguf`, projector `mmproj-Qwen_Qwen3.5-9B-bf16.gguf`; Unrestricted: `Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf` và projector tương ứng.
- 32K CORE: synthetic needle retrieval tại các vị trí 8K, 16K, 24K, 30K đều 4/4 PASS; input dài nhất ghi nhận khoảng 30.608 tokens; VRAM sampled peak ~11.270 MiB. Những số liệu này không thay cho acceptance suite toàn diện.
- Multimodal: CORE vision và bài frame-video có kết quả; benchmark video không đủ cơ sở để kết luận model đọc video liên tục một cách đáng tin cậy. Tách frame là preprocessing ngoài model, không phải năng lực xem video native đã nghiệm thu.
- Backend container: image `local-assistant/llama-cuda:5c8854fd8`, commit llama.cpp `5c8854fd88319125125dc4b836c98b1b215b0f23`; dùng external Docker network `home-net`; publish `127.0.0.1:8080:8080`.
- Không khởi chạy CORE và Unrestricted cùng lúc vì hai service cùng bind port và giới hạn VRAM; với Unrestricted dùng `--spec-type none` vì GGUF hiện tại thiếu MTP layers; CORE dùng `--spec-type draft-mtp`.

**Lệnh thực thi/kiểm tra liên quan:**

```bash
cd ~/Workspace/Server/ai
# Kiểm tra Compose; với zsh có thể dùng `nocorrect` nếu bị hỏi sửa lệnh
nocorrect docker compose -f docker-compose.yaml config --quiet
# Chỉ tái tạo CORE khi cần thay cấu hình; KHÔNG chạy lệnh này để kiểm tra thường xuyên
# docker compose -f docker-compose.yaml --profile core up -d --no-build --force-recreate core
curl -sS http://127.0.0.1:8080/health
curl -sS http://127.0.0.1:8080/v1/models | uv run python -m json.tool
nocorrect docker compose -f docker-compose.yaml --profile core logs --tail=40 core
```

**Kết quả khởi động đã ghi nhận:** `model loaded`, `n_slots=1`, `n_ctx_slot=32768`, projector multimodal loaded, MTP draft context initialized, `/health` trả `{"status":"ok"}`. Lần đầu ngay sau recreate có thể trả HTTP 503 `Loading model`; phải chờ health OK.

## Ngày 12 — FastAPI Gateway và Runtime Presets

**Trạng thái:** PASS regression + live smoke. **Không tạo endpoint mới**; giữ `POST /api/v1/chat/completions` và hai profile `core` / `unrestricted`.

**Các file hiện hữu được giữ/tích hợp:**
- `apps/api/main.py` — giữ router health/chat.
- `apps/api/core/model_config.py` — đọc `configs/models.yaml`, bắt buộc loopback.
- `apps/api/routes/chat.py` — nhận `profile`, `messages`, `temperature`, `preset`, optional `max_tokens`.
- `apps/api/services/llama_gateway.py` — `httpx.AsyncClient`, `/v1/models`, `/apply-template`, `/tokenize`, `/v1/chat/completions`, báo lỗi khi response không hoàn tất.
- `apps/api/runtime/presets.py` + `apps/api/runtime/__init__.py` — chính sách preset và token budget.
- `tests/test_runtime_presets.py` — unit tests.

| Preset | Thinking | Reasoning budget | Maximum completion tokens |
|---|---|---:|---:|
| Fast | Off | N/A | 4096 |
| Balanced (default) | On | 4096 | 8192 |
| Deep | On | 8192 | 16384 |
| Unlimited | On | -1 | Context còn lại (trừ reserve) |

**Budget policy:** 32.768 context, 256 safety reserve, ít nhất 512 answer reserve. Budget finite yêu cầu còn đủ chỗ cho tối đa reasoning cộng tối thiểu answer. Tính bằng chat template + tokenizer của llama.cpp, không đo theo số ký tự. `reasoning_budget_requested` trong response là tham số đã **yêu cầu**, không phải proof về nội bộ backend.

**Lệnh build/test:**

```bash
cd ~/Workspace/Server/ai
uv run python -m compileall -q apps/api
uv run python -m pytest tests/test_runtime_presets.py tests/test_api_health.py tests/test_llama_gateway.py -v
# Output được người dùng báo cáo: 23 passed in 0.25s

# FastAPI ở terminal riêng
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
# terminal kiểm tra
curl --fail --silent --show-error http://127.0.0.1:8000/openapi.json -o /dev/null
```

**Live smoke:** Fast `FAST-PRESET-OK` trả đúng, `finish_reason=stop`, `prompt_tokens=20` bằng `input_tokens_counted=20`, không có reasoning. Balanced `125*16=2000`, reasoning bật, `prompt_tokens=24` bằng token counted, `completion_tokens=1277`, `finish_reason=stop`. Deep `37*48=1776`, `budget=8192`, `max_output=16384`; Unlimited cùng đáp án, `budget=-1`, `max_output=32490`. Hai ca đều `finish_reason=stop`. Số tokens là số trên từng case, không phải tốc độ benchmark.

## Ngày 13 — Auto Router V1

**Trạng thái:** PASS unit test, smoke test, extended benchmark; không tuyên bố accuracy tổng quát.

- `auto` chọn trong Fast/Balanced/Deep, **không tự chọn Unlimited**. Default vẫn Balanced.
- Greeting độc lập rất ngắn -> `simple_greeting_rule` -> Fast.
- Các yêu cầu khác -> một lần phân loại bằng LLM `temperature=0`, `max_tokens=96`, thinking off; classifier chỉ thấy 6 messages gần nhất, tối đa 1200 ký tự/message.
- Classifier sai format/lỗi -> fallback Balanced; nhãn bắt buộc khớp chính xác.
- Metadata: `preset_requested`, `preset_selected`, `auto_source`.
- Thêm `tests/test_runtime_auto.py`; giữ regression cũ.

**Unit tests:** 42/42 PASS sau Auto V1; cuối checkpoint 47/47 PASS trên `uv run python -m pytest tests/ -q`.

**Smoke tests:** `Xin chào!` -> Fast rule; `What is the capital of France?` -> Fast classifier; complex multi-agent architecture -> Deep classifier, HTTP 200, 27.9s, 4188 completion tokens, reasoning 18418 ký tự, `finish_reason=stop`.

**Benchmark mở rộng đã chạy:**

```bash
cd ~/Workspace/Server/ai
uv run python -m compileall -q benchmarks/scripts
uv run python benchmarks/scripts/auto_router_validation.py
uv run python -m pytest tests/ -q
# 47 passed in 5.49s ở lượt đã báo cáo
```

**Results:** `benchmarks/results/runtime/auto-router.json`

| Case | Selected | Latency | Routing | Completion |
|---|---|---:|---|---|
| python_easy_debug | balanced | 12.09s | PASS | PASS |
| distributed_debug | deep | 50.78s | PASS | PASS |
| long_translation | balanced | 30.56s | PASS | PASS |
| easy_multistep | fast | 0.88s | PASS | PASS |
| complex_architecture | deep | 14.13s | PASS | PASS |
| constrained_planning | deep | 23.20s | PASS | PASS |
| multiturn_debug | balanced | 30.08s | PASS | PASS |
| classification_injection | deep | 17.40s | PASS | PASS |

**Summary:** `Routing acceptable: 8/8`, `Completions OK: 8/8`. `classification_injection` qua một ca không chứng minh miễn nhiễm prompt injection nói chung. Latency là end-to-end (gồm classify + inference), chưa được phân rã.

**Sự cố vận hành quan trọng:** Lượt benchmark đầu `0/8` vì cổng FastAPI `127.0.0.1:8000` không có listener; `/health` llama-server `127.0.0.1:8080` vẫn OK. Sau khi bật lại Uvicorn, benchmark Auto đạt 8/8. Không xem lỗi `All connection attempts failed` là lỗi phân loại của Auto.

## Ngày 14 — Reasoning hard-budget validation & release gate

**Trạng thái:** Xác minh thực nghiệm hard cap ở mức nhỏ; 4096/8192 **chưa chạm ngưỡng để kiểm chứng riêng**. Runtime V1 đủ điều kiện chuyển phát triển tiếp theo với giới hạn này được ghi rõ.

**Script và lệnh đã chạy:**

```bash
cd ~/Workspace/Server/ai
uv run python benchmarks/scripts/reasoning_budget_validation.py
# Saved: benchmarks/results/runtime/reasoning-budget.json
uv run python benchmarks/scripts/auto_router_validation.py
# Saved: benchmarks/results/runtime/auto-router.json
uv run python -m pytest tests/ -q
# 47 passed in 5.49s
```

**Result từ llama.cpp trực tiếp:**

| Reasoning budget | Visible reasoning tokens qua /tokenize | Completion tokens | Finish reason | Interpretation |
|---:|---:|---:|---|---|
| 64 | 64 | 1088 | length | Bằng cap đo được |
| 256 | 255 | 1280 | length | Gần bằng cap |
| 512 | 512 | 1536 | length | Bằng cap đo được |
| 4096 | 2797 | 5120 | length | Chạm tổng max_tokens (4096+1024), không chạm reasoning cap |
| 8192 | 2797 | 5325 | stop | Dừng tự nhiên |

**Giới hạn diễn giải:** số visible reasoning tokens là phép tokenize lại nội dung đã trả, không phải counter nội bộ của sampler. Ở các case `finish_reason=length`, dù `has_final_answer=True` vẫn không được đánh dấu completion hoàn chỉnh. Không được diễn giải các mức 4096/8192 thành chứng nhận cưỡng chế đã chạm ngưỡng.

**Release gate Runtime V1:**
- [x] CORE 32K với runtime CUDA + MTP hoạt động theo log và benchmark đã ghi nhận.
- [x] Fast/Balanced/Deep/Unlimited hoạt động live trong các case đã báo cáo.
- [x] Auto V1: 3/3 smoke, 8/8 extended routing & completion.
- [x] 47/47 pytest regression PASS.
- [x] Đếm prompt token khớp response usage ở 2 bài kiểm thử.
- [x] Hard reasoning cap hoạt động thực nghiệm tại 64/256/512.
- [ ] Chưa có test chạm cap tại chính 4096 và 8192.
- [ ] Chưa đo accuracy routing bằng dữ liệu lớn, chưa phân rã latency classifier/inference.
- [ ] Chưa nghiệm thu conversation persistence sau restart.

**Quyết định:** Kết thúc Runtime V1, bước tiếp theo là Conversation Storage & Multi-turn Chat Engine. Không thay đổi Docker Compose, không cần triển khai PostgreSQL hay thêm service; dùng SQLite V1.

## Ngày 15 — Conversation Storage & Multi-turn Chat Engine (DESIGN ONLY)

**Ngày mở thiết kế:** 2026-10-16. **Trạng thái:** Chưa triển khai, chưa migrate, chưa có persistence test. Bản thiết kế chi tiết nằm trong `conversation_schema_design_day15.md` đính kèm checkpoint này.

**Yêu cầu chính:** lưu conversation ID, messages theo thứ tự, atomic write, idempotent send, restart recovery, lưu metadata inference mà không lưu reasoning trace theo mặc định, giới hạn context trước inference, không phá endpoint `/api/v1/chat/completions`.

**Thứ tự triển khai:** schema/migration -> repository & manager -> conversation endpoints -> context builder -> integration/live restart test. Không đánh dấu DONE cho tới khi có test thực tế.

---

# CHECKPOINT — 2026-10-17 — D15-T05 Conversation REST API

**Purpose:** Ghi nhận thay đổi đã thực hiện trực tiếp trong workspace, kết quả kiểm thử và các Acceptance Criteria còn thiếu.

**Trạng thái: PARTIAL. Day 15 vẫn ACTIVE; chưa chuyển sang D15-T06 hoặc D16.**

## Căn cứ và phạm vi

- Không tồn tại `docs/MASTER_ROADMAP.md` trong checkout. Đã đọc roadmap thực tế `docs/LOCAL_ASSISTANT_MASTER_ROADMAP.md`, toàn bộ dev log, thiết kế schema, repository, manager, inference adapter và API/runtime hiện tại.
- Roadmap checkpoint mới hơn dev log cũ: D15-T01–T04 có focused PASS trong lịch sử; task tiếp theo là D15-T05. Không triển khai lại SQLite theo ghi chú cũ đã bị supersede.
- Tại thời điểm bắt đầu, Git working tree sạch. Không đổi model runtime, preset, stateless router/gateway, migration, Vault policy hoặc container.

## Thay đổi đầy đủ trong workspace

- `apps/api/routes/conversations.py`: tám routes create/list/detail/update/history/send/archive/delete; UUID và validation; schema output rõ ràng; phân trang; mã lỗi nhất quán.
- `apps/api/services/conversations.py`: composition trên repositories và ConversationManager hiện hữu; dùng profile/preset đã lưu; ngăn update/archive/delete khi inference pending theo locking convention sẵn có.
- `apps/api/storage/lifecycle.py`: tạo pool/session factory khi có DATABASE_URL, dispose khi shutdown, trả conversation 503 nếu chưa cấu hình; khởi tạo lỗi được redact. Không tự chạy migration hoặc lấy Vault token.
- `apps/api/main.py`: đăng ký lifespan và conversation router; stateless chat vẫn được giữ nguyên.
- `.gitignore`: đổi `models/` thành `/models/`. Pattern cũ vô tình bỏ qua `src/infrastructure/models/`; năm file ORM hiện hữu giờ có thể version-control. Bổ sung module/class/method descriptions, không thay mappings, DDL hay logic chuyển đổi entity.
- `tests/test_conversation_api.py`: HTTP/unit tests cho tám routes, validation, pagination, peer/origin/proxy access, redaction, pool disposal, stored defaults, busy mutations, ORM mapping và endpoint stateless.
- `tests/integration/test_conversation_http_persistence.py`: HTTP qua PostgreSQL thật, multi-turn, idempotency/replay/conflict, pool/lifespan restart, archive/delete và variant gọi CORE thật khi opt-in. Cleanup chỉ theo UUID của conversation do test tạo.
- `docs/ADR/016-conversation-http-composition.md`: lý do, tác động và giới hạn composition, credential delivery và local access boundary. POST archive theo roadmap mới thay PATCH archive của bản thiết kế gốc.
- `docs/CONVERSATION_API_LOCAL_RUNBOOK.md`: cách chạy local một worker, không trust proxy headers; hợp đồng API và lệnh acceptance.
- Cập nhật roadmap cùng chú thích checkpoint trong schema design; giữ nguyên nội dung lịch sử dev log phía trên.

## Bằng chứng kiểm thử thực tế

Đã chạy từ `ai/` bằng uv:

```sh
uv run python -m pytest tests/test_conversation_api.py tests/test_api_health.py tests/test_llama_gateway.py tests/test_runtime_presets.py tests/test_runtime_auto.py -q
```

**Kết quả cuối:** `85 passed in 0.53s`.

```sh
uv run python -m pytest tests/ --ignore=tests/test_core_acceptance.py -q -rs
```

**Kết quả cuối:** `90 passed, 4 skipped in 0.48s`.

Bốn ca SKIP đều do DATABASE_URL chưa được inject: hai variant HTTP persistence mới, manager integration và repository integration. Đây **không phải PASS cho PostgreSQL/restart/live inference**. Variant live còn yêu cầu `LOCAL_ASSISTANT_LIVE_E2E=1` và CORE đang chạy.

```sh
uv run python -m pytest tests/ -q
```

**Kết quả:** exit 2, `1 error during collection`, `ConnectionRefusedError`/`URLError` trong `tests/test_core_acceptance.py:44`. Script lịch sử gọi trực tiếp model tại `127.0.0.1:8080` ngay khi import; không có listener tại lần chạy. Lỗi này đã tồn tại ở baseline trước thay đổi và vẫn được giữ nguyên để không sửa thành phần ngoài task. Không tuyên bố full-suite green.

```sh
uv run python -m compileall -q apps/api src tests/test_conversation_api.py tests/integration/test_conversation_http_persistence.py
uvx ruff format apps/api/main.py apps/api/routes/conversations.py apps/api/services/conversations.py apps/api/storage/lifecycle.py src/infrastructure/models tests/test_conversation_api.py tests/integration/test_conversation_http_persistence.py
uvx ruff check --select E9,F63,F7,F82,F401 apps/api/main.py apps/api/routes/conversations.py apps/api/services/conversations.py apps/api/storage/lifecycle.py tests/test_conversation_api.py tests/integration/test_conversation_http_persistence.py
```

Compile thành công; formatter đã áp dụng; lint phạm vi trên `All checks passed!`. Ruff chạy qua uvx, không thêm dependency/đổi uv.lock.

Trong quá trình kiểm thử, đã sửa việc Pydantic kế thừa cấu hình trim khiến transcript/answer bị mất whitespace, và đổi tên integration test để tránh trùng module basename. Các kết quả cuối ở trên được chạy sau các sửa này.

## Acceptance còn thiếu và bước tiếp theo

- [x] HTTP contracts, validation, DI/pool lifecycle, safe error mapping và local boundary có tests thực thi.
- [x] Stateless endpoint có regression kiểm tra delegation và response.
- [ ] Inject DATABASE_URL từ credential app hiện hữu bằng phương thức được cấp quyền; không dùng Vault root token/unseal file hoặc migrator credential.
- [ ] Chạy integration thật và local HTTP → PostgreSQL → gateway → assistant với CORE. Không đánh dấu PASS cho ca đang SKIP.
- [ ] Chứng minh persistence qua restart process FastAPI thật; test mới tự động tái tạo lifespan/pool nhưng chưa được chạy với DB.
- [ ] Production Vault identity/secret delivery theo least privilege chưa cấu hình. Environment injection là interface local, không phải chứng nhận production bootstrap.
- [ ] D15-T06 vẫn gồm cross-connection concurrency, orphan lease/recovery, whole-turn token trimming, process/DB restart và auth ownership.

Không có user ownership trong V001. Guard hiện tại chỉ bảo vệ local development: từ chối peer ngoài loopback, Origin và forwarding headers; không thay thế authentication. Local process vẫn có thể đọc history. Không publish qua reverse proxy hoặc Internet trước khi có owner boundary.

**Task kế tiếp vẫn là hoàn tất acceptance của D15-T05.** Hướng dẫn và lệnh chạy nằm trong runbook; không tự đánh dấu Day 15 hoàn thành.

---

# FOLLOW-UP — 2026-10-17 — Vault-backed acceptance for D15-T05

**Purpose:** Ghi nhận lần kiểm tra credential Vault thực tế theo chỉ dẫn tiếp theo của người dùng và thay thế trạng thái SKIP bằng bằng chứng chạy thật; giữ nguyên checkpoint trước như lịch sử.

**Trạng thái mới: D15-T05 PASS trong phạm vi localhost; Day 15 vẫn ACTIVE; D15-T06 là NEXT.**

## Credential và runtime thực tế

Người dùng xác nhận password đã lưu trong Vault và yêu cầu kiểm tra. Đã dùng helper hiện hữu tại `infras/scripts/vault_static_secret.py` để kiểm tra có TLS verification. Vault ban đầu initialized nhưng **sealed**, nên health/secret trả HTTP 503. Đã dùng riêng hàm load bootstrap/unseal hiện hữu của `infras/vault-server/scripts/initialize-vault.py` để unseal; không initialize lại, không thay policy, mount, token, password hoặc audit configuration.

Sau unseal, đọc thành công đúng secret `secret/server/local-assistant/postgresql`, xác minh identity `local_assistant_app` / `local_assistant`. Tạo URL với SQLAlchemy URL builder để encode credential; chỉ giữ trong bộ nhớ và environment của tiến trình tests/API. Operator token không truyền cho tiến trình con. Không in password, URL có credential, token hoặc unseal shares; không ghi chúng vào file. Đây là operator verification được người dùng chỉ định, không phải production Vault auth implementation.

CORE container hiện hữu `local-assistant-core-1` ban đầu Exited; đã `docker start` container này, không recreate/build/đổi Compose. VRAM free trước start: 15173 MiB. Đợi `/health` HTTP 200 trước vòng acceptance cuối. Vault được giữ unsealed, CORE đang chạy sau kiểm tra; hai process API tạm đã dừng. Không restart PostgreSQL hoặc các service khác.

## Lỗi phát hiện và sửa tối thiểu

- Vòng đầu: `3 passed, 1 failed` vì CORE đang load, live endpoint nhận 502.
- Sau khi CORE ready: `3 passed, 1 failed` vì request test đặt `max_tokens=128`, thấp hơn answer reserve 512 của policy hiện hữu, nên API trả 422 đúng thiết kế.
- Chỉ sửa fixture trong `tests/integration/test_conversation_http_persistence.py`: `max_tokens=512`. Giữ nguyên runtime/preset/gateway/manager đã PASS. Bản file đầy đủ nằm tại đường dẫn trên.

## Kết quả cuối đã chạy

Qua `uv run python`, operator wrapper đọc Vault và inject DATABASE_URL vào subprocess dùng cùng Python environment; bật `LOCAL_ASSISTANT_LIVE_E2E=1`. Không dùng `--ignore`, không skip integration.

```sh
python -m pytest tests/integration/ -q -rs --tb=short
# 4 passed in 1.18s

python -m pytest tests/ -q -rs --tb=short
# 94 passed in 6.48s
```

Cả **4 ca trước đây SKIP nay PASS**: repository lifecycle, ConversationManager persistence/idempotency/failure, HTTP persistence với inference giả, HTTP persistence với CORE thật. Full suite exit 0, không SKIP, không lỗi collection. Script core acceptance lịch sử chỉ print PASS/FAIL, không assert, nên kết quả pytest không được diễn giải thành chứng nhận chất lượng toàn diện của model.

## Restart process thật

Đã thực thi kiểm tra HTTP riêng với Uvicorn bind loopback trên cổng tạm, một worker, `--no-proxy-headers`:

1. Process A PID 785554: tạo conversation, gọi CORE thành công, đọc lịch sử hai messages.
2. Terminate và chờ process A thoát.
3. Process B PID 785601: đọc list/history giữ nguyên dữ liệu; gửi cùng request_key nhận `cached=true`, assistant_message_id giữ nguyên và không thêm message.
4. Kết quả audit: `actual_process_restart_acceptance=PASS history_count=2 cached_replay=true`.
5. Dừng process B; xóa đúng conversation của kiểm tra cùng inference/message rows theo FK order, không đụng dữ liệu người dùng.

## Tiến độ và giới hạn

Roadmap, schema checkpoint, ADR-016 và runbook đã cập nhật T05 PASS cho localhost với bằng chứng trên. Không đánh dấu Day 15 DONE. Production AppRole/secret delivery, owner-based auth, concurrency/crash recovery, context trimming và PostgreSQL restart vẫn là các gate mở; chưa triển khai T06 trong lượt này.

---

# CHECKPOINT — 2026-10-17 — Commit T05 and implement D15-T06 hardening

**Purpose:** Ghi nhận commit được yêu cầu, code hardening mới, kiểm thử thực tế và các release gates còn thiếu.

## Git và phạm vi

- Đã commit toàn bộ checkpoint D15-T05, ORM source bị ignore trước đó, tests, ADR-016, roadmap và dev log trên branch `develop`.
- Commit thực tế: **`18f3175` — `feat(ai): add persistent conversation API and record verified T05 acceptance`**; 17 files, 1698 insertions, 33 deletions.
- Tiếp tục đúng task kế tiếp D15-T06. Không chuyển Day 16; không thay preset policy, stateless router, LlamaGateway implementation, model/container configuration hoặc shared database schema.
- Credential vẫn lấy đúng secret app trong Vault, tạo URL bằng SQLAlchemy và inject trong bộ nhớ vào child test environment. Không đưa operator token vào application/test children hoặc ghi secret vào output/Git.

## Code đã triển khai

- `src/application/services/conversation_context.py`: chọn system instructions và các cặp user/assistant nguyên vẹn; bỏ những user turn cũ chưa có câu trả lời; luôn giữ current user. Fit bằng token count qua callback và budget policy hiện hữu, loại từng cặp cũ nếu cần, trả 422 nếu current/system không thể fit.
- `src/infrastructure/repositories/message_repository.py`: thêm bounded recent-context query cùng system instructions; khắc phục lỗi đọc first-500 khiến new message ngoài trang đầu bị báo inconsistent. Không xóa hay cắt text transcript.
- `src/infrastructure/inference/llama_adapter.py`: resolve Auto một lần, dùng template/tokenizer và preset policy hiện hữu để fit trước inference; gateway vẫn recheck final input. Map timeout/connect/HTTP/malformed response thành InferenceFailure có status an toàn. Không thay logic model gateway đã PASS.
- `src/infrastructure/repositories/inference_run_repository.py`: owner UUID + lease expiry trong JSONB có sẵn, DB clock để claim/renew/check; interrupted transition và expiry recovery có khóa. Không cần migration. Dữ liệu lease không lộ qua HTTP response schemas.
- `src/application/services/conversation_manager.py`: lease mặc định 120s, heartbeat 30s qua transaction ngắn; race model coroutine với heartbeat, cancel và await tasks khi kết thúc; finalization khóa conversation rồi fence pending/owner/live lease trước khi insert assistant. Cancellation lưu interrupted; failed/finalization rollback có log an toàn. Recovery commit riêng trước reservation để 409 không rollback việc expire.
- Các file Python đã đụng có module/class/function descriptions tiếng Anh; log theo ID/counter/code, không log prompt/reasoning/credential.
- `docs/ADR/017-conversation-hardening.md`: rationale, locking/lease policy, lazy recovery, rollback/drain constraints, context strategy, helper coupling và các giới hạn. Roadmap, schema checkpoint và runbook đã cập nhật.

## Tests mới và bằng chứng đã chạy

Thêm ba test files:

- `tests/test_conversation_context.py`: nguyên cặp, system/current preservation, tokenizer budget, irreducible overflow và invalid output settings.
- `tests/test_llama_adapter.py`: actual gateway helpers qua HTTP mock transport; Auto chỉ resolve một lần, whole-turn trim, không lưu reasoning, timeout/connect/model-not-loaded/malformed responses.
- `tests/integration/test_conversation_hardening.py`: PostgreSQL thật; cùng/khác request key, simultaneous reservation race với hai `pg_backend_pid()` khác nhau; rollback reservation/finalization; length/model/preset mismatch; cancellation; heartbeat renewal/loss; expiry fencing; legacy unowned pending preservation; history >500; pending update/archive/delete; pool capacity; SIGKILL disposable worker và real CORE tokenizer overflow.

Mọi lệnh Python chạy qua uv. Operator wrapper gọi child bằng cùng interpreter của uv, chỉ inject credential app và `LOCAL_ASSISTANT_LIVE_E2E=1`:

```sh
uv run python -m pytest tests/test_conversation_context.py tests/test_llama_adapter.py -q --tb=short
# 12 passed in 0.07s

python -m pytest tests/ -q -rs --tb=short
# Final: 127 passed in 9.27s
# Exit 0, zero skipped, no exclusions

python -m pytest tests/integration/test_conversation_hardening.py::test_pool_capacity_is_available_during_many_inferences -q -o log_cli=true --log-cli-level=INFO --tb=short
# 1 passed in 0.36s
# pool_saturation_probe blocked_inferences=12 checked_out=0
```

Các lượt integration trước đó đạt 21 PASS; sau khi bổ sung race barrier qua hai backend connections, legacy pending và heartbeat-loss tests, full suite cuối ở trên có 127 cases. Pool probe cleanup đủ 12 conversation do test tạo. Mỗi test cleanup theo UUID riêng, không xóa dữ liệu người dùng.

Crash test thật khởi động một Python worker tạm với app credential, đợi marker sau reservation commit, SIGKILL đúng worker đó, đợi lease hết hạn rồi recovery. Kết quả: interrupted/lease_expired, không fake assistant, same-key không tự replay và intentional new-key chạy được. Không kill process API hiện hữu, CORE hay dịch vụ dùng chung.

Live overflow test dùng current input 40000 lần `x ` qua template/tokenizer của CORE: nhận `context_overflow`/422, giữ nguyên user content trong DB, run failed và không có assistant_message_id. Đây là token-boundary evidence, không phải benchmark chất lượng model.

Đã chạy formatter/lint qua uvx và compileall cho source/tests. Ruff phát hiện hai unused imports trong test mới và đã loại bỏ trước lượt full regression cuối. Import sorting/formatting và bổ sung descriptions không thay logic. `git diff --check` được dùng trước commit.

## Kết luận Acceptance Criteria

- [x] Race cùng/khác key, hai DB backend connections, đúng một inference, sequence không trùng, replay/conflict xác định.
- [x] Rollback khi lỗi trước reserve commit và sau assistant insert/trước run complete.
- [x] Không completed giả cho length/model/preset mismatch; current context overflow kiểm tra bằng tokenizer thật.
- [x] Lease/heartbeat/expiry/fencing; cancellation và disposable-process crash; không tự replay pending/failed/interrupted.
- [x] Không giữ DB session/transaction trong thời gian chờ model; pool probe 12 inferences/zero checked-out connections.
- [x] Recent whole-turn context, system/current preservation và lịch sử hơn 500 messages.
- [x] Pending update/archive/delete bị chặn; CORE E2E và gateway error mapping/regression còn PASS.
- [x] Full suite 127/127 PASS, zero skipped.
- [ ] Owner-based authentication/authorization và user-to-user negative access tests: V001 vẫn chưa có owner identity. Local peer/proxy/origin denial không thay cho quyền sở hữu.
- [ ] Shared PostgreSQL restart: phải có backup, isolated restore verification và maintenance/recovery plan được review trước khi restart. Chưa thực hiện thao tác ảnh hưởng các consumer dùng chung.
- [ ] Production pool metrics export/load SLOs, production scoped Vault bootstrap và definition-of-done review tổng thể vẫn mở.

**Trạng thái: D15-T06 PARTIAL, Day 15 ACTIVE (5/6 tasks PASS).** Recovery mới là lazy-on-send hoặc explicit per-conversation; pending cũ không lease cần xác minh thủ công. T04 Auto pending vẫn lưu provisional balanced theo schema bắt buộc, full dependency inversion/Unit of Work vẫn chưa hoàn chỉnh. Khi rollback phải drain active runs trước, không chạy lẫn old/new writers không hiểu lease.

**Bước tiếp theo:** hoàn tất owner identity/schema/access policy design và kế hoạch backup/isolated restore/maintenance cho shared PostgreSQL, rồi thực thi các gate còn lại với bằng chứng. Không đánh dấu DONE hoặc nhảy Day 16 khi các gate này còn mở.

---

# CHECKPOINT — 2026-10-18 — D15-T06 remaining gates accepted

**Purpose:** Ghi lại owner authorization, pool telemetry và backup/restore/restart thực tế; kết thúc local acceptance Day 15 bằng bằng chứng, không thay lịch sử các checkpoint trước.

**Trạng thái:** D15-T06 PASS cho authenticated localhost; Day 15 local gate PASS (6/6 tasks). D16 là NEXT, chưa viết code D16.

## Quyết định và phạm vi

Đã đọc lại roadmap, source, tests và ADR-016/017. Working tree ban đầu sạch. ADR-018 được viết trước operational drill, nêu rõ identity contract, không silent backfill, backup/recovery/rollback và điều kiện restart. Không thêm service/DB instance, không thay shared Keycloak realm, preset thresholds, LlamaGateway implementation, model configuration hoặc migration V001.

Owner UUID lưu trong JSONB metadata hiện hữu. Phạm vi local API dùng bearer credential ngẫu nhiên entropy cao, file digest có quyền owner-only và owner filters tại service/repository/manager locks. Đây là phương án V1 không cần DDL; PostgreSQL RLS/typed-owner migration và OIDC là bước deployment sau, không giả vờ đã triển khai. Hội thoại cũ không owner được giữ nguyên và ẩn khỏi HTTP, không gán đại cho user đầu tiên.

## Source thay đổi

- `apps/api/core/conversation_auth.py`: file regular owner-UID/0600, từ chối final symlink; validate UUID/digest schema; reload mỗi request; constant-time digest comparison; fail closed 503 config và 401 auth; từ chối duplicate Authorization headers. Không log bearer/digest.
- `apps/api/services/conversations.py`, `src/infrastructure/repositories/conversation_repository.py`, `src/application/services/conversation_manager.py`: request-scoped principal, owner filter cho create/list/detail/history/update/archive/delete; lock reservation/recovery/finalization kiểm tra owner độc lập để tránh bypass/TOCTOU. Owner từ server, không từ body/header tự khai báo. Trusted maintenance interfaces giữ khả năng unscoped; HTTP luôn bind principal.
- `apps/api/routes/conversations.py`: require bearer principal sau direct-localhost guard; an toàn khi pool timeout, record telemetry counter và trả 503. API stateless giữ contract cũ.
- `src/infrastructure/database/pool_telemetry.py`: checkout/checkin/invalidation/timeout/peak + current utilization; sample JSON log định kỳ 30s và timeout/shutdown; không giữ connection/SQL/exception payload.
- `src/infrastructure/database/connection.py`: pool wait 10s và hide SQL parameters; lifecycle quản lý sampler/listeners, cancel/await khi shutdown.
- `apps/api/core/logging_config.py`, `apps/api/main.py`: app INFO logs và pool export thực sự xuất hiện khi chạy Uvicorn mặc định; tôn trọng handler có sẵn, không nhân đôi handler hoặc bật SQL echo.
- `scripts/postgres_recovery_acceptance.py`: guarded operator drill, private/exclusive backup files, SHA-256 manifest, restore probe guard, source fingerprint, owner/ACL checks, quiet gate, optional explicit restart và consumer verification. Không tự restore đè production nếu lỗi.
- Tests mới: `tests/conftest.py`, `tests/test_conversation_auth.py`, `tests/test_application_logging.py`, `tests/test_postgres_recovery_acceptance.py`, `tests/integration/test_conversation_ownership.py`, `tests/integration/test_pool_telemetry.py`. Các tests HTTP cũ được cấp credential test hợp lệ thay vì bỏ qua auth.

## Credential/runtime thực tế

Máy đã reboot: Vault initialized nhưng sealed, CORE stopped. Dùng đúng helper unseal hiện hữu theo quyền operator đã được người dùng chỉ định trước đó; không initialize lại, rotate key/password hay sửa Vault policy. Đọc credential `local_assistant_app` trong Vault vào bộ nhớ; API/test children chỉ nhận DATABASE_URL và auth-file path, không nhận operator token. Khởi động lại container CORE hiện hữu và đợi health 200.

Đã tạo stable principal/API token trong KV v2 `secret/server/local-assistant/api`, fields `principal_id` và `api_token`, bằng helper CAS/static-secret hiện hữu. Raw token chỉ nằm trong Vault/bộ nhớ; `ai/data/auth/principals.json` chứa UUID và SHA-256 digest, file 0600, thư mục 0700. Namespace app được dùng lại, không tạo policy/consumer identity production mới. File runtime/auth/backups nằm trong Git ignore; không ghi token, password, URL có credential hoặc unseal shares vào Git/output.

## Bằng chứng tests

Tất cả chạy bằng uv; child pytest dùng cùng interpreter và DATABASE_URL app được inject trong bộ nhớ, `LOCAL_ASSISTANT_LIVE_E2E=1`:

```sh
python -m pytest tests/ -q -rs --tb=short
# Final after shared PostgreSQL restart: 151 passed in 9.45s
# Exit 0; zero skipped; no exclusions
```

Có lượt trung gian 147 PASS trước khi bổ sung ACL-mismatch guard, duplicate auth header, stale-backend reconnect và fresh-runtime logging test. Lượt integration đầu sau reboot nhận 26 PASS/2 FAIL vì CORE chưa chạy; sau khi start và đợi ready, lỗi môi trường đó đã được kiểm tra lại trong full suite cuối, không bỏ qua hoặc đổi thành SKIP.

Hai principal thật trên PostgreSQL: tất cả cross-owner detail/history/update/send/replay/archive/delete trả 404; own operations/replay hoạt động; không gọi inference trái phép; unowned legacy rows bị ẩn; owner injection bị 422; manager lock trực tiếp cũng chặn principal khác. Revocation reload, unsafe file permissions/symlink/malformed config và duplicate headers được kiểm tra.

Pool test thật: saturate pool size 1 -> timeout, invalidation, periodic samples, peak/counters chính xác; HTTP timeout được map 503 không lộ driver details. Một test chỉ terminate backend PID do chính nó tạo, rồi pool_pre_ping thay connection và query thành công với `local_assistant_app`.

Kiểm tra Uvicorn độc lập dùng credential app thực tế từ Vault và private auth file: anonymous list trả 401; CORE trả completed answer; hai messages giữ nguyên qua hai process; same-key replay cached với cùng assistant ID; startup/shutdown có `database_pool_metrics`, logs không chứa raw token/DB password/URL/operator token. Hai process tạm và conversation của test đã dọn.

## Backup/restore/restart thực tế

Trước drill, PostgreSQL chỉ có 5 connection Keycloak idle, không có active consumer transaction hoặc pending inference. ADR-018 đã ghi plan và rollback trước khi thực thi. Không force-kill consumer transaction hoặc restart Keycloak.

```sh
uv run python scripts/postgres_recovery_acceptance.py --backup-directory data/backups/t06-preflight-20261018
# Protected backups + app data restore comparison PASS; no restart

uv run python scripts/postgres_recovery_acceptance.py --backup-directory data/backups/t06-restart-20261018 --execute-restart
# Data restore, source persistence and Keycloak recovery PASS

uv run python scripts/postgres_recovery_acceptance.py --backup-directory data/backups/t06-acl-verified-20261018 --execute-restart
# Final strengthened drill: preserve/compare ownership and ACLs as well as rows
# postgres_isolated_restore_verified tables=4
# postgres_shared_restart_started verified_restore=true
# postgres_restart_persistence_verified dependent_keycloak_ready=true
# postgres_restore_probe_removed / postgres_acceptance_canary_removed
# postgres_recovery_acceptance_passed
```

Vòng đầu chỉ so data; khi review backup correctness, đã bỏ flags loại ownership/ACL và bổ sung security fingerprint + test mismatch. Final drill sau cải tiến mới là evidence đầy đủ. Đây là lý do có hai controlled restart; không che giấu lượt data-only trước đó. Mỗi vòng dùng backup directory mới, không overwrite backup cũ.

Final manifest: `ai/data/backups/t06-acl-verified-20261018/manifest.json`; `restore_verified=true`, `restore_security_verified=true`, `restart_verified=true`. Có 4 custom database archives và globals, file 0600/thư mục 0700. Đã xác minh lại SHA-256 từng file, owner/ACL fingerprint sau restart, zero remaining canary và zero restore-probe databases. Restored Local Assistant có 4 bảng so khớp rows và normalized schema/table/sequence owners/ACLs. Archive giữ metadata owner/privilege; globals có role password hashes nên chỉ giữ protected, không commit/đóng gói artifacts review.

Restore dùng database tạm UUID trên đúng instance PostgreSQL hiện hữu rồi drop đúng probe; không có PostgreSQL service/instance thứ hai. Shared container được restart graceful với named volume giữ nguyên; Keycloak discovery 200 trước/sau và container healthy. Chỉ canary/test rows do drill tạo bị xóa. Backup all-DB archives được tạo, nhưng chỉ Local Assistant được restore-verify; off-host/full-cluster disaster recovery không được suy diễn là đã chứng nhận.

## Definition-of-done review

- [x] V001 còn nguyên; runtime app role đúng và không dùng superuser trong API.
- [x] Persistence/multi-turn/idempotency, concurrency, failure atomicity, lease/cancellation/crash fencing và tokenizer/context gates từ checkpoint trước vẫn regression PASS.
- [x] Two-principal auth/owner negative access, private auth config/revocation, giữ localhost boundary.
- [x] Runtime pool metrics xuất thật; timeout/saturation/invalidation/reconnect được kiểm tra.
- [x] Authenticated API process restart + CORE/replay và shared PostgreSQL restart sau verified data/owner/ACL restore.
- [x] Full 151/151 PASS, zero SKIP; ADR-018/runbook/roadmap/dev log phản ánh kết quả thực tế.
- [x] Không đưa secrets/private backups vào Git; không mark production multiworker/OIDC/off-host DR/model quality là PASS.

**Kết luận:** D15-T06 PASS trong phạm vi authenticated localhost và Day 15 local release gate được chấp nhận. Các khoản nợ production scoped Vault/OIDC, RLS/typed-owner migration, explicit legacy adoption, Unit of Work inversion, multiworker/load SLO và off-host DR tiếp tục được theo dõi riêng. Không cần kéo dài Day 15 cho những capability production chưa thuộc local acceptance đã chốt.

**Bước kế tiếp:** D16 — bounded file metadata/storage design, tái sử dụng principal ownership, xác định path isolation, quota/size/type/checksum/provenance và rollback trước khi thêm upload API. Chưa triển khai D16 trong checkpoint này.

---

# CHECKPOINT — 2026-10-18 — D16 bounded file metadata/storage design

**Purpose:** Ghi nhận task kế tiếp đã hoàn tất đúng phạm vi roadmap: thiết kế schema/storage/rollback và policy có tests, trước khi triển khai upload/download D17.

**Trạng thái:** D16 PASS ở phạm vi design/policy. Day 15 giữ PASS; D17 NEXT/TODO. File persistence/HTTP upload/download chưa được triển khai hoặc tuyên bố PASS.

## Kiểm tra hiện trạng và quyết định

Working tree ban đầu sạch, commit Day 15 `60c431b`. Đã đọc roadmap, dev log, ADR-018, auth/owner/schema/repository ports, Alembic V001 và dependencies. Chưa có file metadata/storage/upload implementation. Filesystem `/dev/sda4` tại inspection: khoảng 617 GiB available, 29% used. Đây là quan sát capacity, không phải throughput benchmark.

Chọn private local filesystem V1 + shared PostgreSQL journal/usage. Tái sử dụng UUID principal Day 15; không dùng filenames làm path; không cần MinIO credential/bucket/policy trong D16. ADR-019 so sánh các phương án và ghi rõ priority/dependency/effort/risk, giới hạn, rollout/rollback và D17 acceptance. Các feature phát sinh như cross-owner dedup, remote URL import, macro/archives, MinIO adapter đều chưa xếp lịch khi chưa có assessment riêng.

## File tạo mới và nội dung thực hiện

- `docs/FILE_STORAGE_DESIGN.md`: owner-typed metadata/usage V002 proposal, quota/global locking, provenance, canonical replay fingerprint, bounded formats/bytes/count/stream/archive policy, private root/UUID keys, lifecycle/crash journal, no-follow/FD/file-lock/no-replace contract, cleanup, backup/identity restore và D17 acceptance matrix.
- `docs/ADR/019-bounded-local-file-storage.md`: lý do chọn FS local; PostgreSQL source-of-truth; không implicit attachment/dedup; không giữ transaction khi chờ client/I/O; không trả quota chỉ vì lease hết hạn hoặc đã unlink nhưng inode vẫn mở.
- `src/application/services/file_storage_policy.py`: dataclasses policy/usage/plan; positive/consistent limits; NFC/UTF-8 filename validation; UUID key generation; SHA-256 declaration and semantic fingerprint; byte/quota/concurrency/disk bounds; detected-vs-declared media contract; archive totals limits; safe audit events không log tên file/digest/request key.
- `tests/test_file_storage_policy.py`: 86 cases về traversal/control/portable filenames, UTF-8 byte cap, file types, canonical fingerprints, owner/key separation, invalid IDs/hash/keys/sizes/config/usage, exact quota/free-space boundaries, MIME spoofing, expansion bounds và log privacy.
- Roadmap/dev log cập nhật task D16 và handoff D17. Existing Day 15 source, migrations, manifests, dependencies và services không bị thay đổi.

Default design limits: reservation JSON 8 KiB trước parse; 25 MiB/file; 1 GiB + 1,000 allocated files/owner; 10 GiB + 10,000 global; 2 owner/4 global active upload reservations; 2 GiB physical free-space floor; 64 KiB chunks; 300s reservation/stream wall, 30s idle, 60s lease/15s heartbeat; OOXML expanded 100 MiB, 1,000 entries, ratio 100:1. Đây là initial product policy, không phải capability/performance đã đo trên uploader chưa triển khai.

## Review các invariant quan trọng

- Owner của file luôn từ authenticated principal, typed UUID trong new schema; không backfill conversation owner hay nhận client path/owner override.
- Fingerprint bao gồm owner/NFC label/declared size/hash, không gồm generated file UUID hoặc request key; retry cùng key trỏ resource cũ, không collision do UUID mới. Không cross-owner dedup/existence leak.
- Reserve/usage changes atomic theo global -> owner -> file; helper snapshot không tự bảo đảm concurrency. D17 phải chứng minh bằng PostgreSQL connections/races thật.
- Giữ allocated bytes/files từ reservation qua ready/purging, chỉ release sau cleanup/close và commit marker một lần. Ready chỉ trả upload slot. Paused writer hoặc download reader còn giữ inode không được làm quota trông như đã rảnh.
- DB/file lease + cooperative exclusive/shared FD lock; không chờ lock trong transaction. Publish durable no-replace trước DB ready; crash ở giữa vẫn hidden/charged và có journal để reconcile.
- Review đã bổ sung rõ delete trong receiving/verifying phải fence/cancel rồi chờ FD đóng; tombstone chưa phải physical delete. Backup/restore phải giữ principal UUID ổn định qua Vault/auth, không gán resources cho identity mới.
- Sau D17 có blob, DB-only backup Day 15 không đủ: metadata + blob inventory/hashes + payload restore phải được kiểm chứng cùng nhau. Rollback disable admission/drain/fence và giữ bảng/blob; không drop hoặc xóa dữ liệu để rollback code.

## Vault và kiểm thử thực tế

Theo chỉ dẫn người dùng, lấy credential app từ đúng `secret/server/local-assistant/postgresql` qua helper TLS hiện hữu; không yêu cầu gửi lại key. Chỉ inject DATABASE_URL và live-test flag vào child pytest, không truyền operator token. Không in/ghi password, URL có credential hoặc key vào output/Git. Không cần đọc MinIO/other-app secrets vì milestone hiện tại chưa dùng chúng.

Read-only query bằng `local_assistant_app`: Alembic version `0001`; đúng bốn bảng `alembic_version`, `conversations`, `messages`, `inference_runs`. Không tạo/migrate file tables, không tạo blob root hoặc chạy DB restart/restore mới trong D16.

```sh
uv run python -m pytest tests/test_file_storage_policy.py -q --tb=short
# Final focused: 86 passed in 0.06s

# Via uv operator wrapper with existing app URL injected in memory:
python -m pytest tests/ -q -rs --tb=short
# 237 passed in 9.48s
# Exit 0, zero skipped, no exclusions; real PostgreSQL and ready CORE
```

237 = 151 existing Day 15 cases + 86 new pure policy cases. Existing auth/owner/conversation/lease/CORE/recovery regression vẫn PASS. Bộ test mới không giả vờ MIME sniff, upload streaming, FS durability hoặc SQL quota race đã tồn tại.

Đã format/lint bằng uvx Ruff, compile và kiểm tra descriptions cho mọi function/class/file Python mới; `git diff --check` trước commit. Ruff đã loại hai unused imports trước focused test cuối.

## Acceptance và bước tiếp theo

- [x] Schema/ownership/provenance/quota design, limits và request replay contract đã review.
- [x] Path/FD/publish/journal/cleanup/rollback/paired-backup plan cụ thể, kể cả open-inode quota và identity restore edge cases.
- [x] Priority/dependency/effort/risk và deferred scope minh bạch; không thêm service/credential/dependency ngoài nhu cầu.
- [x] Executable policy boundaries 86/86 PASS; full regression 237/237 PASS; V001 và Day 15 source giữ nguyên.
- [ ] D17 sẽ triển khai V002/repositories/FS adapter/HTTP với admission disabled trước; fresh protected backup và reviewed DDL/grants/rollback trước apply.
- [ ] D17 phải test actual owner/SQL/FS/stream/container/crash/cleanup/race và paired blob+metadata restore rồi mới mark runtime upload/download PASS.

**D16 hoàn tất ở phạm vi design/policy đã chốt. D17 là task tiếp theo, chưa triển khai trong checkpoint này.**


---

# CHECKPOINT — 2026-10-18 14:47 +07:00 — D17-T01 private local filesystem adapter

**Purpose:** Ghi nhận triển khai và kiểm thử thực tế filesystem foundation của D17, giữ các gate PostgreSQL/MIME/HTTP/restore còn mở.

**Trạng thái:** D17-T01 PASS trong phạm vi adapter FS độc lập. **D17 IN PROGRESS**, chưa hoàn thành ngày và không chuyển sang D18. D15/D16 vẫn PASS theo acceptance đã ghi trước đó.

## Hiện trạng, scope và thứ tự thực hiện

Bắt đầu từ working tree sạch tại `2a6be5a`. Đọc roadmap, dev log, FILE_STORAGE_DESIGN, ADR-019, policy, database/repositories/auth/API/lifespan và dependencies. D17 ban đầu chưa có file implementation. Chia D17 thành T01 FS, T02 journal/quota/migration, T03 MIME/container, T04 HTTP, T05 reconciliation/paired restore. Đây là phân rã scope đã có, không cắt bớt acceptance hoặc tự chuyển ngày.

Thực hiện T01 trước DDL để kiểm chứng các invariant absent inode, open FD và purge trên filesystem thật. Không cần migration, credential mới, dependency parser hoặc production payload directory cho task này. Không đổi source/config/runtime đã PASS của Day 15.

## Code và các file liên quan

- `src/infrastructure/local_blob_storage.py`: private root 0700; no-follow descriptor walk từ root path, generated directories 0700/same device/process UID; payload regular 0600, O_EXCL/O_NOFOLLOW/O_NONBLOCK/CLOEXEC; tên chỉ từ UUID.
- Writer giới hạn chunk, declared/actual bytes, kernel short writes, SHA-256, actual free-space floor; file fsync; sealed verifier FD và rehash trước publish để phát hiện verifier sửa bytes; không buffer cả payload.
- Publish dùng hard link không replace trên cùng device, inode/link checks, sync object parent, unlink staging, sync staging parent. Collision/EXDEV/fsync failure không overwrite/copy fallback hoặc báo ready.
- Writer giữ EX payload + resource guard đến close; reader giữ SH inode; purge nonblocking EX mọi inode trước unlink. Close idempotent/context-manager; không dùng SQL session trong adapter.
- `tests/test_local_blob_storage.py`: 66 cases chạy trên file/FD/locks thật; có spawned processes, SIGSTOP/SIGKILL và injected syscall failures.
- `docs/ADR/020-resource-directory-locks.md`: quyết định resource directory guard và contract tích hợp journal; cập nhật spec/roadmap/dev log để không suy diễn FS-only PASS thành runtime upload PASS.

## Review và sửa lỗi correctness

Payload flock không bảo vệ tên chưa tồn tại: purge có thể chạy giữa open/create và flock. Bổ sung EX guard trên directory inode ổn định `staging/<owner>/<file>`, không xóa directory này khi purge. Writer duplicate guard FD để tiếp tục giữ lock sau admission context. Reject guard đóng, guard identity sai hoặc guard từ root/inode khác. Test xen purge chính xác trước payload open chứng minh busy thay vì cleanup thành công.

**Contract bắt buộc cho T02/T04:** acquire resource guard ngoài SQL transaction; recheck/claim DB lease dưới guard rồi mới create writer/đọc body. Fence row trước purge; chỉ release counter trong final fenced transaction sau purge true. Nếu chỉ check lease trước khi chờ filesystem guard thì stale worker vẫn có thể tạo file sau cleanup; adapter độc lập không thay thế bước DB recheck.

Không coi staging của lease lạ là không có bytes: inventory đúng resource directory, báo `untracked_staging_entry`, không xóa/adopt và không báo purge thành công. Distinct staging/final inodes báo `object_collision`; untracked hard links/permissions/inode substitution fail closed. Không glob-delete, không đụng auth/backups/models. Failed unlink/fsync giữ cleanup pending; retry sync parent ngay cả khi tên đã vắng. Event `blob_purged` chỉ log sau khi local payload FDs đã đóng.

ADR-020 ghi P0/dependency/effort/risk: extra directory FDs/fsync, busy responses và empty lock directories được giữ lâu dài; retention cần review riêng. Không thêm lock service hoặc PostgreSQL instance. Các process cùng OS UID phải hợp tác; không tuyên bố chống root/malicious same-UID process.

## Tests thực tế

```sh
uv run python -m pytest tests/test_local_blob_storage.py -q --tb=short
# 66 passed in 0.90s

# uv operator wrapper: app credential lấy từ Vault, chỉ truyền DATABASE_URL/live flag vào child
python -m pytest tests/ -q -rs --tb=short
# 303 passed in 10.38s
# Exit 0, zero SKIP, no exclusions; real PostgreSQL + CORE

uvx ruff check --select E9,F63,F7,F82,F401,I src/infrastructure/local_blob_storage.py tests/test_local_blob_storage.py
uvx ruff format --check src/infrastructure/local_blob_storage.py tests/test_local_blob_storage.py
# PASS after final formatting
```

303 = 151 prior + 86 D16 policy + 66 D17-T01 FS. Các lượt trước là 293 PASS/9.82s và 301 PASS/10.42s. Review cuối sửa FD leak ở missing-name fsync failure và đóng handle khi context entry thất bại; bổ sung hai tests tương ứng rồi chạy lại đủ 303 cases. Lượt 303 là evidence cuối.

Hai reader/writer process riêng bị SIGSTOP vẫn chặn purge; SIGKILL đóng FDs mới cho cleanup. Uploader process bị kill tại **8 boundary**: create, write, seal, link, object-parent fsync, stage unlink, stage-parent fsync, publish-return. Sau kill, cleanup exact keys và retry đều thành công. Kiểm tra symlink ancestor/subdirectory/payload, FIFO/directory, hardlink, collision, substituted inode, root/file permissions, owner namespace, tampered key/size, unknown lease, closed handles, descriptor inventory và audit privacy.

ENOSPC, short writes, EXDEV và file/parent fsync failures là **fault injection trên file thật**; không giả vờ đã làm đầy disk chung hoặc chứng minh physical power-loss durability. FS crash tests không phải DB/FS cross-resource crash certification.

Dùng helper TLS hiện hữu đọc đúng app secret `secret/server/local-assistant/postgresql`; không yêu cầu user cung cấp key. Không truyền operator Vault token vào pytest hoặc in credential. Read-only query xác nhận Alembic `0001` và đúng 4 bảng assistant cũ; không apply DDL, restart container hoặc tạo production `data/files`. CORE/PostgreSQL hiện hữu được tái sử dụng. Kiểm tra AST descriptions mọi file/function/class mới, py_compile, Ruff và git diff --check.

## Acceptance và bước tiếp theo

- [x] D17-T01 standalone descriptor/permission/byte/hash/no-replace/locks/purge contract có 66 tests PASS.
- [x] Real process crash/held-FD cases, creation/purge race và unknown-stage fail-closed đã kiểm chứng.
- [x] Full 303/303 PASS, zero SKIP; ADR-020/spec/roadmap/dev log cập nhật; Day 15 source/dependencies/V001 không thay đổi.
- [ ] **NEXT D17-T02:** fresh protected backup; lấy existing migrator credential từ Vault; review offline V002 DDL/grants/rollback; implement journal và atomic global -> owner -> file quota/replay/lease/counter-release với real PostgreSQL races.
- [ ] D17-T03 bounded MIME/container verification cho đủ formats đã chốt.
- [ ] D17-T04 authenticated raw upload/download/list/detail/delete, HTTP bounds/deadlines/cancellation/owner ACL và off-event-loop FS work.
- [ ] D17-T05 DB/FS reconciliation, quota/HTTP/delete/download races và paired metadata/blob backup/isolated restore.

**Chưa có HTTP upload feature hoặc live file journal. Không mark D17 hoàn tất và không bắt đầu D18 khi các gate trên chưa đạt.**


---

# CHECKPOINT — 2026-10-18 — D17-T02 V002 and atomic file journal/quota

**Purpose:** Ghi nhận triển khai/migrate/kiểm thử journal và quota thật; tiếp tục D17, không chuyển D18.

**Trạng thái:** T02 PASS ở phạm vi repository; D17 IN PROGRESS. T03 MIME NEXT, HTTP/reconciliation/paired blob restore còn mở.

## Thực hiện và rollout

- Đọc credential app và migrator hiện hữu từ đúng Vault app paths qua TLS; không tạo key, không hỏi lại user, không truyền operator token vào app/tests.
- Fresh backup `data/backups/d17-v002-preflight-20261018`: 4 database archives + globals, file 0600/dir 0700, hashes verified; isolated app restore so rows và owner/ACL đạt. Probe/canary cleanup hoàn tất; không restart shared PostgreSQL.
- Review offline `alembic upgrade 0001:0002 --sql` với placeholder không credential: đúng 3 additive tables, indexes/CHECKs/owner-key uniqueness, explicit DML/revoke TRUNCATE, local lock/statement timeout. Không sửa V001 hoặc bảng conversation cũ.
- Apply V002 bằng `local_assistant_migrator` lấy từ Vault. So sánh fingerprints của conversation/message/run rows và owner/ACL trước/sau bằng kết nối migrator: giống nhau. Revision hiện tại `0002`; không tạo production blob root hoặc bật HTTP file admission.
- `migrations/versions/0002_file_journal.py`: files/owner usage/global singleton, typed ownership/provenance/key, hash/size/state/release invariants, guarded downgrade từ chối bất kỳ file row/tombstone hoặc allocation chưa sạch.
- `src/infrastructure/repositories/file_journal.py`: short transactions global -> owner -> file; capacity/replay atomic, immutable policy snapshot, DB-clock claim/heartbeat, verifying/ready, purge fencing và release markers đúng một lần. Ready chỉ trả upload slot; bytes/files giữ đến physical purge.
- ADR-021 ghi decision/dependency/P0/effort/risk/rollout/rollback; spec/roadmap/dev log cập nhật. Không có FS I/O trong SQL transaction; caller phải giữ ADR-020 guard qua post-lock DB claim và chỉ release sau purge true.

## Kiểm thử và sửa lỗi

Focused lượt đầu phát hiện annotation `list[dict]` bị method `list` trong class che tên built-in; đã thêm deferred annotations. Initial claim dùng một DB timestamp để lease=wall không lỗi CHECK do drift microseconds. Sau fix, focused 21/21 PASS; thêm 3 tests actual FS+DB protocol rồi chạy đủ suite.

`tests/integration/test_file_journal.py`: **24 cases** về same-key race chỉ một allocation, key conflict/cross-owner independence, byte/file/owner-slot/global-slot/global-byte admission race, CRUD/lease/ready/purge owner checks, progress monotonic/oversize/expiry, ready/terminal structural CHECKs, app grants/non-superuser, populated downgrade guard, ready slot release và concurrent exactly-once terminal release.

Ba tests dùng adapter filesystem thật: writer còn mở giữ quota/purge pending; delayed worker recheck dưới guard sau cleanup bị từ chối trước create; published-but-not-ready vẫn hidden/charged rồi cleanup conservative sau expiry. Không coi đây là full HTTP/DB/FS crash/paired-restore certification.

```sh
# Vault operator wrapper, child chỉ có app DATABASE_URL và live-test flag
python -m pytest tests/ -q -rs --tb=short
# 327 passed in 11.41s; exit 0; zero SKIP; real PostgreSQL + CORE
```

327 = 303 prior + 24 journal cases. Owner-specific test cleanup khóa global và chỉ trừ allocations của các UUID test; không reset counters của app/owner khác. Ruff/format, AST descriptions, py_compile và git diff --check thực hiện cho các file mới. Source/config/runtime Day 15 giữ nguyên; schema chỉ thêm V002 đã review/backup.

**Tiếp tục ngay:** D17-T03 verifier MIME/container trong process riêng có resource/deadline bounds; sau đó T04 raw HTTP và T05 recovery/paired restore. Không mark D17 PASS trước các gate đó.


---

# CHECKPOINT — 2026-10-18 — D17-T03 isolated MIME/container verification

**Purpose:** Ghi nhận verifier có bounds và môi trường cô lập thật; tiếp tục T04 ngay trong D17.

**Trạng thái:** T03 PASS ở verifier scope; D17 IN PROGRESS, HTTP/paired restore chưa PASS.

- T02 đã commit `1a9ce17`; tiếp tục theo chỉ dẫn làm liên tục, không đợi user nhắc task kế tiếp.
- `file_verifier.py`, `file_verifier_worker.py`, `file_content_verifier.py`: sealed payload FD vào subprocess; không truyền original filename/path/credential; Bubblewrap namespaces thật với read-only system runtime/venv/src, không mount home/data/Vault, clearenv, network riêng, caps dropped, readonly tmp, die-with-parent. Không fallback parse trong API nếu sandbox lỗi.
- Worker limits: 512 MiB address space, CPU soft/hard 5/6s, wall 10s, 32 FDs, core 0, file output 4096 bytes. Anonymous regular verdict file + parent đọc tối đa 4097 bytes tránh PIPE capture không giới hạn. Timeout test thật chứng minh không còn worker/supervisor giữ FD.
- TXT/MD/CSV incremental UTF-8/control/prefix checks; PNG/JPEG/WebP verify+decode đúng format, single frame/max20M pixels; PDF strict/encryption/pages/indirect traversal/expanded streams/active-feature checks; DOCX/XLSX ZIP directory preflight, header+actual expansion/CRC limits, path/duplicate/symlink/encryption/macro/nested archive checks, bounded defused XML, required types/main parts/local relationships và workbook sheets.
- `uv add 'pypdf>=6,<7' 'defusedxml>=0.7,<1'`: lock 6.21.1/0.7.1, chỉ 2 dependencies mới; Pillow giữ nguyên. Bubblewrap 0.11.1 có sẵn và namespace probe PASS. pyproject/uv.lock có purpose descriptions; `uv lock --check` PASS.
- ADR-022 ghi P0/dependency/effort/risk, conservative V1 limits, integration/cancellation và rollback. Runtime feature chưa bật; không certificate malware/semantic trust hoặc production multiworker.

Tests `tests/test_file_verifier.py`: **62 passed in 6.05s**. Bao gồm đủ 10 suffix formats, fake headers, malformed UTF-8/controls/leading markup, macro/encrypted/bomb/traversal/symlink/duplicate/nested ZIP, DTD/entity/external relationships/missing parts, encrypted/active/truncated PDF; real namespace network/host secret/env isolation, worker kernel limits, real timeout cleanup và malformed JSON verdicts. Review thêm typed verdict checks để không phát sinh raw TypeError.

Full Vault-backed suite: **389 passed in 17.53s**, exit0, zero SKIP/no exclusions, PostgreSQL + CORE thật. 389 = 327 prior + 62 verifier. Ruff/format, AST descriptions và git diff --check PASS. Không đổi schema hoặc runtime Day 15 trong T03.

**Tiếp tục ngay T04:** owner-authenticated reserve/raw PUT/list/detail/download/delete, metadata/body bounds, heartbeat/deadline/cancellation, FD-safe off-event-loop I/O và honest pending cleanup. Sau đó T05 reconciliation/paired restore; D17 còn mở.


---

# CHECKPOINT — 2026-10-18 — D17-T04 authenticated file HTTP and durable root binding

**Purpose:** Ghi nhận HTTP/service/lifespan có tests thật và fix wrong-root cleanup trước recovery; tiếp tục T05 ngay.

**Trạng thái:** T04 local HTTP scope PASS. D17 IN PROGRESS; T05 recovery/paired restore/process restart chưa PASS. Feature mặc định disabled.

- T03 commit `d28a111`. Thêm `apps/api/services/files.py`, `routes/files.py`, `storage/files.py`; chỉ sửa main/lifespan Day 15 ở chỗ cần register optional router/resources, dùng lại auth UUID/loopback và pool cũ.
- POST metadata bounded8KiB trước JSON parse, reject duplicate/unknown fields; raw PUT không multipart/pre-admission spooling; actual bytes/hash/MIME enforced. List/detail/download/delete luôn owner scoped; explicit DTO không lộ internal owner/path/key/fingerprint/lease/purge token.
- File I/O/hash/verifier chạy thread ngoài SQL transaction. Shield+join trước propagate cancel; đóng cả guard/handle mà caller bị cancel trước khi nhận kết quả. Response close reader ngay cả khi send header bị cancel trước generator entry. Shutdown join request trước pool dispose.
- Heartbeat sample serialized chống progress regression; idle và absolute wall deadline không được kéo dài bởi byte progress. Dùng policy snapshot cho writer; ready release slot, physical purge mới release bytes/files. Delete202 khi reader/writer/FS lỗi giữ quota, 204 sau cleanup thật.
- Download lock SH, verify size/SHA từ FD rồi recheck owned-ready trước header; attachment/nosniff/private no-store. Missing/corrupt blob503 không gửi bytes sai hoặc tự trả quota.
- Review phát hiện rủi ro cấu hình root rỗng/test root làm cleanup nhầm: thêm private durable `.storage-namespace` marker, namespace context immutable trong JSONB snapshot; runtime journal và recovery scoped; startup từ chối root khác cho allocations của current principals. Không sửa migration V002; không auto-adopt legacy/unbound rows. ADR-023/024 ghi rationale/P0/dependency/effort/risk/rollback.

`tests/integration/test_file_http.py`: **31 cases** với PostgreSQL/FS thật. `tests/test_local_blob_storage.py` thêm **8 cases**, tổng FS74. Bao gồm HTTP roundtrip text/image/PDF/provenance/replay, owner/auth/proxy, malformed/chunked metadata, short/overflow/hash/MIME, held-reader delete202, bad blob503, pool/write/publish fault injection, verifier FD/guard cancellation, header-before-generator cancel, idle/wall deadlines, shutdown joins và root namespace restart/restore/tamper/cross-root denial.

Focused đầu có một test MIME khai báo hash của text khác payload binary nên đúng ra dừng ở hash422; sửa fixture để declared hash khớp binary rồi test thực sự đi tới MIME415, không nới code để chiều test.

Full Vault-backed regression sau fix/binding: **428 passed in 24.12s**, exit0, zero SKIP/no exclusions, PostgreSQL + CORE thật. Các lượt trước 419/20.83s và421/23.98s là intermediate; 428 là final checkpoint. 428=389 prior+31 HTTP+8 FS. Ruff/format/AST descriptions/compile/git diff checks thực hiện; không tạo production payload root hoặc bật API deployment.

**Tiếp tục T05:** namespace-scoped recovery/fair pending retries; paired DB/blob/identity snapshot và isolated restore; actual authenticated API process restart/cleanup; full regression và final D17 acceptance review.


---

# CHECKPOINT — 2026-10-18 — D17-T05 recovery/paired restore và final D17 acceptance

**Purpose:** Ghi kết quả cuối sau khi làm liên tục T02→T03→T04→T05, đủ kiểm thử và operational evidence trước khi chốt D17.

**Trạng thái:** **D17 T01–T05 PASS trong phạm vi authenticated direct localhost, một API worker. D18 native PDF extraction NEXT/TODO.** Không suy diễn production multiworker/load/off-host DR/model quality là PASS.

## Triển khai và review hệ thống

- T04 commit `da28890`; tiếp tục namespace-scoped startup recovery và loop5s, batch bounded50. Chỉ fence expired reserved/receiving/verifying theo DB clock; purging giữ quota khi FD/guard bận hoặc cleanup lỗi. Retry timestamp được rotate sau resource khác để không starvation. Ready paging theo UUID chỉ gỡ staging link nếu cùng inode/private/size/SHA và exclusive locks; không trả quota ready hoặc xóa/adopt unknown/collision.
- `LocalBlobStorage.inventory`: FD no-follow/private/device/single-link, marker bắt buộc đúng, depth/entry ceilings; backup phải khớp exact known ready inventory. Thêm tests inventory bounds/symlink/missing marker và colliding ready-stage inode.
- `scripts/file_storage_recovery_acceptance.py`: operator CLI, không API/model tool; yêu cầu dừng consumer, no pending states, counters consistent, nonempty ready/current principal bindings/same namespace. App-role read-only repeatable-read exported snapshot; Docker PostgreSQL hiện hữu dump cùng snapshot; private archive bounded64MiB trước helper restore, chunked hash/copy, exact inventory/SHA/perms, namespace và digest-only identity preserved.
- Independent restored blob root cùng source namespace; DB restore probe trên cùng instance so 7 tables và owner/ACL, drop đúng generated probe. Manifest chỉ ghi success sau tất cả checks. Không restart shared PostgreSQL/Keycloak hoặc tạo service/role/credential mới.
- Paired tests clone **schema only** vào source DB probe riêng, seed V002/version/global0, dùng app role; tránh giả định database thật trống file hoặc chạm blob user. Probe source/target được dọn bằng guard prefix UUID. Các runtime tests còn lại owner/root-scoped.
- ADR-025 và FILE_STORAGE_LOCAL_RUNBOOK ghi decisions/P0/dependency/effort/risk/limits/rollout/rollback. Default feature vẫn off; bật rõ flag và root/auth/app credential đúng mới khởi tạo. V001/old business schema/code behavior giữ regression PASS; V002 là additive đã review/backup ở T02.

## Tests cuối

`tests/integration/test_file_recovery.py`: **12 cases**. Actual partial/published uploader process bị kill; expired live guard giữ quota trước kill, sau kill cleanup/release đúng một lần. Fair retry khi reader giữ file; ready same-inode link cleanup; actual unlink/fsync failure giữ allocation; real counter UPDATE rồi forced SQL transaction rollback, retry về0; concurrent HTTP same-key/quota; DELETE đồng thời raw PUT receiving trả202/hide ngay, PUT409 không thành ready và cleanup về0. Paired restore + API readback hai principals và negative owner access; unknown/corrupt/pending source từ chối backup với lỗi cụ thể, không che infra failure bằng broad assertion.

```sh
# Vault TLS helper delivers only app DATABASE_URL/live-test flag to child
python -m pytest tests/ -q -rs --tb=short
# FINAL: 443 passed in 30.14s
# Exit 0; zero SKIP; no exclusions; real PostgreSQL + CORE
```

443 = **151 Day15 + 86 D16 policy + 77 FS + 24 journal + 62 verifier + 31 HTTP/service + 12 recovery**. Các lượt intermediate 439/28.20s và443/28.64s giữ làm lịch sử; final443/30.14s chạy sau khi cô lập paired source probes. Focused recovery cuối12/12 PASS6.60s. Ruff/format/AST file/function/class descriptions/py_compile/uv lock/diff checks PASS.

## Operational drill giữ artifacts thực tế

Dùng đúng existing app DB/API credential từ Vault; xác minh token digest ↔ principal UUID khớp protected `data/auth/principals.json`. Parent giữ operator token trong memory; Uvicorn/pytest/verifier không nhận operator Vault token hoặc raw key trong code/log.

1. Actual Uvicorn worker1 trên loopback: anonymous401; reserve201; raw upload200 ready; download bytes53/SHA đúng. Root production riêng `data/files` được khởi tạo0700 với namespace marker/payload0600.
2. Stop/drain worker1, pool đóng. Paired backup `data/backups/d17-paired-20261018`: archive28231bytes; 1 fixture53bytes; DB exported-snapshot dump, 7-table restored rows/normalized owners/ACLs giống; independent copied/restored blobs hashes và stable namespace/principal binding đúng; DB probe được dọn.
3. Actual worker2 mở lại cùng root/auth/V002: metadata/download200 đúng bytes; POST same key replay201 cùng ID không charge thêm; DELETE204 sau cleanup, subsequent download404.
4. Dừng worker2. Cleanup chỉ resource test có exact owner/UUID/request key và released/deleted marker; không đụng user resources. So existing conversation/message/run fingerprints và owner/ACL trước/sau: giống nhau.
5. Recheck protected backup archive SHA, mọi inventory blob SHA/size, owner UID, file0600/dir0700, no symlink; manifest paired/database/security/identity flags true. Global usage `(0,0,0)`, zero process canary journal, zero source/restore DB probes. CORE/PostgreSQL/Keycloak và shared containers vẫn healthy; không restart shared service.

Artifacts riêng tư giữ ngoài Git/source archive: `data/backups/d17-paired-20261018/`; API logs0600 trong `/tmp/local-assistant-d17-q21k55og/`. Globals preflight vẫn ở backup T02, không đóng gói credential/backup/payload. Không activate overwrite production DB từ archive; chỉ isolated restore verification.

## Final acceptance review

- [x] Typed owner/key/provenance/state constraints; atomic owner/global quota và same-key replay; independent-session/HTTP races PASS.
- [x] Guard/inode/no-follow/permissions/no-replace, bounded body/hash/format, namespace binding và unknown-data quarantine PASS.
- [x] Isolated bounded verifier mọi allowed family; raw HTTP owner/auth/pagination/headers/short/overflow/hash/MIME/deadline/cancel/shutdown gates PASS.
- [x] Held reader/writer/expired worker không trả quota; real crash boundaries, physical/DB-release failures, fair retry/ready-stage recovery PASS.
- [x] Paired metadata/blob/namespace/identity restore, restored API readback và actual API process restart/replay/download/delete PASS.
- [x] Full443/443, zero SKIP; ADR-019–025/design/runbook/roadmap/dev log phản ánh evidence; source-only full-file artifact tách khỏi secrets/backups.

**D17 hoàn tất đúng local acceptance. Bước kế tiếp D18:** P1 native PDF extraction có file UUID/content hash/page locators/extractor version, owner/namespace/ready/hash recheck và isolated resource bounds. Review ADR trước thay đổi kiến trúc/persistence; golden multi-page/Unicode/blank/error/page mapping và full regression phải PASS trước khi chốt D18. OCR/VLM thuộc D21, không auto-ingest hoặc coi file content là instruction.

---

# Ngày 18 — Native PDF extraction có provenance từng trang (2026-10-18)

**Mục đích:** Ghi lại triển khai, quyết định kiến trúc và kết quả kiểm thử thực tế của D18 sau D17 PASS.

**Kết quả:** **D18 PASS trong phạm vi localhost/one worker**. Full regression **476 passed in34.23s**, exit0, **0 SKIP**, không exclude test. D19 DOCX read/write là task tiếp theo; chưa đánh dấu PASS hay triển khai D19. Ngày trong roadmap là milestone, không phải hạn buộc phải nhảy task.

## Đánh giá phạm vi và ADR

P1, phụ thuộc owned ready files/namespace/FD/sandbox đã PASS của D17. Rủi ro: font/text ordering, page mapping, malformed streams, resource exhaustion, concurrent delete và hostile document instructions. ADR-026 chốt trích xuất native PDF **theo yêu cầu, không lưu cache/persist extraction**; không cần migration hoặc dependency mới. Không auto-ingest/attach/model call. OCR/VLM vẫn D21. Không đổi schema, config hay hành vi Day15 đã PASS; chỉ bổ sung reader FD API cần cho extraction và service/router liên quan của D17.

## Code đầy đủ trong checkout

- `src/infrastructure/pdf_extractor.py`: parent sandbox invocation, wall/output bounds, exact protocol/version/page numbering/UTF-8 validation, safe errors và audit counts/version.
- `src/infrastructure/pdf_extractor_worker.py`: kernel limits trước import parser, D17 PDF structure/active-content validation, plain native text từng trang, reject overflow thay vì truncate.
- `src/infrastructure/local_blob_storage.py`: `BlobReader.extraction_reader()` giữ read-only borrowed FD trên shared locked inode; không reopen user pathname.
- `apps/api/services/files.py`: tối đa2 extraction đồng thời, không queue; track/join request và thread trước close; owner/namespace/ready/hash trước parsing và integrity/ready sau parsing. Delete có thể hide/202 khi reader còn giữ lock; không trả stale extracted text.
- `apps/api/routes/files.py`: authenticated `POST /api/v1/files/{id}/extract`, private/no-store và nosniff; response UUID/SHA/extractor/version, `content_trust=untrusted`, pages với one-based number/text/locator/status. Không có native text trả `no_native_text`, không khẳng định visual page blank.
- Tests/golden/ADR/design/runbook/roadmap cập nhật đồng bộ. Source archive cuối chứa full versions của các file thay đổi, không phải patch; không kèm key/data/backup.

## Giới hạn thực thi

Reuse Bubblewrap read-only runtime/code, isolated network/PID/user/IPC, cleared environment, không mount home/data/auth/Vault.512 MiB RAM;5/6s CPU;10s parent wall;32FD;zero core;8 MiB regular stdout. Tối đa1000 pages,128 KiB UTF-8/page,1 MiB UTF-8/document. Parser errors không lộ exception text. Logs chỉ UUID/count/version/error code, không page text. Đây là native/plain extraction có golden coverage cụ thể; chưa chứng nhận arbitrary font/layout/table fidelity.

## Kiểm thử đã quan sát

1. **25 parser/protocol/resource cases PASS**: independent hand-assembled3-page PDF có2 dòng, explicit Unicode CMap U+1EC7, trang không text; exact page/text oracle. Actual malformed/encrypted/active/1003-page/per-page text/document text limits. Wrong schemas/numbering/version/surrogate/oversized replies, sanitized process failures/source rewind. Actual kernel-limit entrypoint, real stalled sandbox timeout không còn worker và log privacy. Golden README ghi rõ coverage và limitations.
2. **8 real PostgreSQL HTTP/service cases PASS**: auth401, foreign owner404, reserved409, non-PDF415, source tamper503; exact UUID/hash/version/page locators/status, private headers, repeat determinism/source download/quota unchanged; concurrent delete, cancellation, shutdown, tamper **sau parser hoàn thành** giữ lock/join và final revalidation;2-slot admission/429/release; foreign storage namespace từ chối trước parser.
3. **Full regression:476 passed in34.23s**,0 skip, real PostgreSQL + CORE.443 baseline +25 parser +8 HTTP/service. Credential đọc từ Vault bằng TLS helper, parent chỉ cấp app DATABASE_URL/live flag cho pytest; strip VAULT env, redact secrets trước output. Không hardcode/print key.
4. Ruff selected correctness/import rules (`E4,E7,E9,F,I`, fixture re-export exceptionF811), format7 files, AST descriptions112 definitions, uv lock check và git diff check PASS. Không tuyên bố toàn bộ repository lint sạch; các policy lint legacy không thuộc thay đổi này.
5. Sau regression: global file usage `(0,0,0)`, restore probes0; shared containers vẫn running/healthy, không restart/new service. Tests dùng UUID/root riêng và cleanup đúng owner; production namespace/auth/paired backup không bị thay thế.

Lượt thử đầu phát hiện oversized-PDF fixture thiếu font nên không sinh native text; đã sửa fixture dùng font thật từ golden rồi cả per-page/document caps được kiểm chứng bằng actual sandbox. Một fixture tamper dùng reservation chưa có lease đã được sửa bằng ready identity từ journal; một lượt lint loại fixture imports đã được phục hồi bằng explicit re-export. Chỉ kết quả full476 sau các sửa này được dùng chốt PASS.

**Tiếp theo D19:** review supported DOCX paragraphs/tables/styles/read-write/round-trip semantics; đánh giá dependency/effort/security/output ownership-quota; ADR trước persistence/API mới. Giữ476 baseline và chỉ chuyển milestone sau Acceptance Criteria có kết quả thực tế.

---

# Ngày 19 — DOCX read/write, tables, styles và round-trip (2026-10-18)

**Mục đích:** Ghi quyết định phạm vi, triển khai và acceptance thực tế cho D19 sau D18 PASS.

**Kết quả:** **D19 PASS trong phạm vi localhost/one worker và plain direct-run editing**. Final full regression **529 passed in 43.90s**, exit0, **0 SKIP**, không exclusions; PostgreSQL/CORE thật, credential từ Vault. D20 XLSX là task NEXT, chưa triển khai hoặc đánh dấu PASS.

## Ưu tiên, dependency, effort và ADR

P1, phụ thuộc D17 owned ready/namespace/hash/FD/sandbox và conventions provenance/lifecycle D18. Rủi ro: ZIP/XML expansion, external relationships, mất formatting hoặc package parts, ambiguous edit targets, source thay đổi/xóa trong lúc parse và slow-client giữ output. ADR-027 được viết trước API/persistence changes; chọn đọc cấu trúc và sửa text **trong existing plain direct runs**, giữ run/paragraph/table/style properties, serialize riêng `word/document.xml`, giữ mọi member khác nguyên bytes sau decompression. Không hứa arbitrary Word layout/pagination hoặc tính toán inherited formatting.

Output là bounded ephemeral attachment; không cache/journal/migration hay charge persistent quota mới. Caller muốn lưu phải reserve/upload như file bình thường. Không sửa source, không model/ingestion, không thay đổi Day15/PDF code đã PASS. Chỉ mở rộng service/router cần cho D19. D19 được hoàn thành trong một milestone sau acceptance; roadmap không ép một milestone tương ứng một ngày lịch.

Dependencies thêm bằng uv: runtime `lxml>=6,<7` khóa6.1.3 để giữ namespace khi sửa XML; dev-only `python-docx>=1.2,<2` khóa1.2.0 làm independent reopen oracle/golden generator. Dùng LibreOffice có sẵn để mở/render trusted test fixture, không đưa LibreOffice vào runtime untrusted parsing và không tạo service/container mới. Lockfile purpose header được giữ lại sau uv update.

## Code và contract

- `src/application/services/docx_contract.py`: strict plans/views, source SHA precondition, unique one-based paragraph/run targets, XML-valid Unicode/tab/newline, numbering/reference/text/count bounds và versioned processor ID.
- `src/infrastructure/docx_content.py`: đọc ordered main-body paragraphs/runs/tables/cells/merges/style references; direct bold/italic/underline dùng tri-state để không nhầm inherited formatting. Rewrite chỉ selected text/tab/line-break nodes, giữ rPr và các phần không sửa. Unsupported fields/drawings/hyperlinks/bookmarks/tracked changes/page-column breaks không được edit; signed packages bị từ chối rewrite.
- `src/infrastructure/docx_processor.py` và `docx_worker.py`: borrowed read-only source FD vào stdin; bounded anonymous request FD được bwrap mount read-only tại `/request.json`, không nhét edit text vào argv/env. D17 OOXML preflight trước lxml (`resolve_entities/load_dtd/huge_tree=False`, `no_network=True`); reverify generated DOCX trước release. Parent bounded output/schema, safe allowlisted errors; không log parser diagnostics/text.
- `FileService.docx_operation()` giữ tối đa2 DOCX slots, active task và shared source lock **đến khi gửi xong response hoặc cancel**, tránh tích tụ output25 MiB do client chậm. Recheck owner/namespace/ready/size/hash trước parsing và hash/ready sau parsing. Cancellation/shutdown join thread rồi mới close FD. PDF giữ gate riêng như cũ.
- Authenticated `POST /api/v1/files/{id}/docx/read`: file UUID/hash, processor version, untrusted label, paragraphs/runs/tables/styles và source locators.
- Authenticated `POST /api/v1/files/{id}/docx/rewrite`: strict JSON tối đa64 KiB,1–100 unique edits, source hash; trả DOCX attachment private/no-store/nosniff với source/output SHA và processor headers. Không đổi nguồn/quota. Chỉ có native source indices, không tự tạo page citations cho Word.

## Giới hạn

512 MiB RAM;5/6s CPU;10s parent wall;32FD;zero core;25 MiB output/stdout. Read JSON8 MiB; native text1 MiB; run64 KiB; main XML2 MiB;10000 paragraphs/cells;20000 runs;1000 styles. Mọi overflow reject, không truncate. D17 archive/DTD/macro/external/nested-package bounds vẫn áp dụng. Các phần không sửa giữ nguyên, không phải chứng nhận mọi nội dung Word là an toàn hay mọi visual layout giống nhau.

## Kết quả kiểm thử đã quan sát

1. **37 processor/contract/resource/opening cases PASS**: genuine styled Unicode golden,3 differently formatted runs, custom paragraph style, table cells/gridSpan merge, source main-body order; source hash/unique targets/invalid XML chars/strict types; exact run edits và no-op/empty/multiple runs. Independent python-docx reopen chứng minh bold/italic/underline/style/table/header/footer còn đúng; mọi non-document.xml member bytes giống nguồn. Actual LibreOffice mở trusted rewritten DOCX và convert PDF; pypdf xác minh edited text/table values. Không coi extract-only smoke là đủ.
2. Actual hostile variants: malformed/external relationship/DTD/macro/nested package; XML/paragraph/run/document text limits; unsupported field/signature/missing target/stale hash. Assert **exact safe code/status**, không chấp nhận broad infrastructure503 cho negative input. Resource XML dùng ZIP_STORED để chứng minh native budgets thay vì vô tình chạm ZIP ratio trước.
3. Kernel limit probe ở production worker parser entrypoint; read-only metadata mount, host/private paths absent, credential-free environment; real stalled sandbox timeout không còn worker. Parent timeout/OS/crash/malformed/oversized/error-type replies và log privacy fail closed. Oversized serialized edit plan bị chặn trước scheduling worker.
4. **16 real PostgreSQL HTTP/service cases PASS**: owned read/rewrite/reopen/provenance/headers, auth401/foreign404/reserved409/deleted404/non-DOCX415, immutable source và chỉ1 original blob/quota unchanged. Stale hash/unknown fields/duplicate targets/duplicate JSON keys/oversize/media/tamper safe errors. Concurrent delete/cancel/shutdown/tamper sau parse không trả stale content và join/release đúng. Hai actual slow rewrite responses giữ cả2 slots, request3 trả429, delete giữ allocation, cancellation đóng FD rồi cleanup về0. Wrong namespace và response-construction failure không leak operation. JSON response budget được kiểm tra sau khi thêm provenance; exceeded413 giải phóng slot và giữ nguyên nguồn.
5. **Final full:529 passed in 43.90s**,0 skip, no exclusions;476 baseline +37 processor +16 integration. Intermediate528/43.32s và528/43.41s giữ làm lịch sử; final529 chạy sau khi bổ sung cap8 MiB cho HTTP JSON kể cả source locators và test cleanup, cùng kiểm tra independent LibreOffice subprocess cũng dùng credential-free environment (`PATH/LANG/XDG_CACHE_HOME` only). Runtime sandbox từ đầu không nhận DB/Vault/API env. Vault TLS helper chỉ giao app DATABASE_URL/live flag cho pytest; strip VAULT env và redact trước output, không print/hardcode key.
6. Ruff selected correctness/import rules `E4,E7,E9,F,I` (explicit fixture re-export exceptionF811), format8 files, AST descriptions102 definitions, uv lock và diff checks PASS. Không tuyên bố toàn repository lint sạch ngoài phạm vi.
7. Post-test audit: global file allocation `(0,0,0)`, restore probes0; existing shared services vẫn running/healthy, không restart/new instance. D19 không đụng production schema/root/auth/retained paired backup; tests dùng root/UUID riêng và cleanup đúng owner.

Roadmap v3.12, ADR-027, design/runbook và golden README được cập nhật theo final evidence; full-file source archive tại `/tmp` không chứa key/data/backup. **Next D20:** P1 XLSX sheets/cells/styles/formula-source preservation; đánh giá dependency/effort/risk và ADR trước API mới, không execute formula/macro hay tự recalculation; golden workbook round-trip và full regression bắt buộc trước PASS.
