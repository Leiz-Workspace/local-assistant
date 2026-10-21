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

---

# Ngày 20 — XLSX read/write, sheets, formula preservation và security (2026-10-18)

**Mục đích:** Ghi lại phạm vi, triển khai và bằng chứng acceptance của D20 sau D19 PASS.

**Kết quả:** **D20 PASS trong phạm vi localhost/one worker, existing literal-cell edits và D17 conservative OOXML subset**. Final full regression **587 passed in52.87s**, exit0, **0 SKIP**, không exclusions; PostgreSQL/CORE thật với credential từ Vault.529 baseline +42 processor/contract/sandbox +16 HTTP/service =587. D21 OCR/VLM là NEXT, chưa triển khai hoặc đánh dấu PASS.

## Ưu tiên, dependency, effort và ADR

P1, phụ thuộc D17 owned ready/namespace/hash/FD/sandbox và D19 bounded response lifecycle. ADR-028 viết trước code/API; đánh giá rủi ro ZIP/XML expansion, formula execution/cache corruption, mất styles/package parts, ambiguous sheet/cell identity và slow/cancelled response. Chọn native XML read và sửa **existing literals**, giữ nguyên source, formula source/attributes/cache và các phần không sửa. Không thực thi formula/macro, không remote fetch, không model/ingestion. Cache không được tính lại; output báo `preserved_not_recalculated` kể cả khi sửa input khiến cache cũ có thể stale. Không coi cache preservation là correctness của kết quả tính toán.

Reuse runtime lxml6.1.3 và existing bwrap/verifier; chỉ thêm **dev-only openpyxl3.1.5 + et-xmlfile2.0.0** bằng uv để independent reopen và tạo golden. Không thêm runtime dependency, schema/migration/service/container. Không sửa parser/PDF/DOCX endpoints đã PASS; FileService bổ sung XLSX operation riêng và main đăng ký router mới. Output ephemeral attachment, caller muốn persist phải dùng normal reserve/upload; source/persistent quota không đổi.

## Triển khai và liên kết hệ thống

- `src/application/services/xlsx_contract.py`: strict source-hash plans,1–100 unique native sheet/A1 targets; explicit string/number/boolean kinds. Number nhận lexical string, reject NaN/overflow/underflow/coercion; XML-valid Unicode/tab/newline và UTF-8/UTF-16 bounds. Read schema kiểm numbering/identity/style refs, formulas/cache, counts/text budget.
- `src/infrastructure/xlsx_content.py`: resolve unique workbook-sheet relationships, inline/shared/rich strings, lexical native values, formula attributes/cache, style indices và merged ranges. Reject ambiguous rows/cells/shared/style references; không expand full cell grid. Rewrite literal hiện hữu, giữ cell style/row/column/workbook properties; serialize changed sheet XML mà thôi, byte-identical các member khác và formula XML trong sheet đã sửa. Formula/merged/rich/metadata cells, signed package hoặc target thiếu bị từ chối.
- `xlsx_processor.py`/`xlsx_worker.py`: credential-free isolated source FD + bounded anonymous read-only `/request.json`; edit/cell/formula text không vào argv/env/log. D17 preflight trước strict lxml, output reverified trước release; parent schema/output limits và safe errors. Không import openpyxl runtime.
- `FileService.xlsx_operation()` giữ2-slot admission/active task/SH FD đến hết response hoặc cancellation; owner/namespace/ready/size/hash recheck trước và hash/ready sau parse; join thread trước close. Existing PDF/DOCX gates giữ nguyên.
- `apps/api/routes/xlsx.py` và main: authenticated `/api/v1/files/{id}/xlsx/read` + `/xlsx/rewrite`, UUID/hash/version/untrusted label/native sheet-cell locators. Attachment có source/output hashes và cache-status header; private/no-store/nosniff. JSON cap bao gồm locators; response construction failure/cancel đóng operation đúng.

## Bounds và phạm vi hỗ trợ

512 MiB RAM;5/6s CPU;10s parent wall;32FD;zero core;25 MiB output. Read JSON8 MiB kể cả provenance; lexical text1 MiB; cell64 KiB UTF-8/32767 UTF-16 units;100 sheets;50000 cells;100000 shared strings;10000 styles; existing2 MiB/XML part/archive limits. Reject thay vì truncate. Canonical addresses trong A1–XFD1048576. Chỉ edit ô đã tồn tại, không thêm sheet/cell/formula/style. String bắt đầu `=` luôn ghi inlineStr để không biến thành formula. Workbook application bên ngoài có calculation policy riêng khi mở file.

D17 absolute package-root relationships/external/macro/DTD/nested-package restrictions giữ nguyên. Golden độc lập chuẩn hóa OPC relationship targets sang relative để nằm trong supported subset; runtime **không tự repair/adopt** package user. Mọi cached result giữ nguyên, không chứng nhận calculation freshness/visual fidelity của mọi workbook. Đây là limitation được ghi rõ trong ADR/runbook/golden README, không sửa bừa thành phần PASS để mở rộng phạm vi.

## Kiểm thử thực tế

1. **42 processor/contract/sandbox cases PASS**: trusted multi-sheet Unicode/numeric/boolean/shared-string/styled/merged golden, cross-sheet formulas, explicit caches30/60 và native formula attribute `ca=1`. Independent openpyxl reopen cả `data_only=False/True`: edited literals đúng, number format/bold/color/fill/freeze pane/column width/merged ranges giữ đúng; formula/cache giữ nguyên mặc dù input đổi. Toàn bộ member ngoài changed sheet byte-identical; formula XML trong changed sheet byte-identical. Chuỗi `=SUM(1,2)` mở lại là text, không formula.
2. Actual malformed/external/DTD/macro/nested/oversized XML/cell-count/text-budget/bad shared-style refs/duplicate cells; formula/merged/signed/missing/stale edits đều assert exact safe code/status. Native resource variants dùng stored XML; cell-count fixture dùng nhiều cells mỗi row để không vô tình chạm XML-size bound trước. Strict plan từ chối duplicate/coercion/invalid coordinates/XML/number types.
3. Parent process failure/malformed/oversized reply/error-type probes; log privacy. Production worker kernel budgets, read-only metadata mount/private host paths absent/cleared env; actual stalled sandbox timeout không còn worker. Không chạy spreadsheet calculation engine để kiểm chứng parser.
4. **16 real PostgreSQL HTTP/service cases PASS**: auth/owner/namespace/ready/hash, native locators/headers/cache uncertainty, immutable download/quota/one original blob. Stale/extra/duplicate/oversize/media/tamper errors, concurrent delete/cancel/shutdown/post-parser tamper; hai slow rewrite responses giữ slots, request3 trả429, delete pending giữ allocation rồi cancellation release/cleanup. Construction failure và JSON limit sau provenance không leak source/slot.
5. **Final full:587 passed in52.87s**,0 skip, no exclusions; real PostgreSQL + CORE. Focused42/4.30s và16/4.97s PASS trước final full; final thêm explicit formula-attribute golden assertion. Vault TLS helper chỉ cấp app DATABASE_URL/live flag cho pytest, strip VAULT env và redact output. Production worker nhận env rỗng; không hardcode/print key.
6. Ruff selected correctness/import rules `E4,E7,E9,F,I` với fixture re-export exceptionF811; format9 files; AST descriptions82 definitions; uv lock/diff checks PASS. Lockfile purpose header giữ lại. Không tuyên bố toàn repo lint sạch ngoài phạm vi.
7. Post-test audit global file usage `(0,0,0)`, restore probes0; CORE/shared containers vẫn running/healthy, không restart hay new instance. Production DB schema/root/auth/retained paired backup không bị thay thế; tests dùng root/UUID riêng và cleanup đúng owner.

Một lượt integration đầu còn tên `DocxResponse` trong XLSX construction-failure test; đã sửa thành `XlsxResponse`, rerun focused16 và full587 PASS. Chỉ final full sau sửa và golden refinement được dùng chốt milestone. Roadmap v3.13, ADR-028, design/runbook/golden README cập nhật cùng evidence; source-only full-file archive tại `/tmp` không chứa key/data/backup.

**Next D21:** đánh giá P1 OCR/VLM fallback cho scans/images/tables, existing CORE vision/mmproj, bounded rasterization/model/VRAM budgets và uncertainty measurement. ADR trước backend/API mới; golden scanned/native comparisons, page/source mapping và full regression bắt buộc trước PASS. Có thể tách nhiều milestone nếu Acceptance Criteria chưa đạt; không tự nhảy D22.

---

# Ngày 21 — Per-page OCR/VLM fallback, confidence và uncertainty (2026-10-18)

**Mục đích:** Ghi lại triển khai D21, ranh giới renderer/model và bằng chứng chất lượng thực tế sau D20 PASS.

**Kết quả:** **D21 PASS trong phạm vi localhost/one worker: native PDF, English OCR và explicit local CORE VLM fallback**. Final full regression **641 passed in66.51s**, exit0, **0 SKIP**, không exclusions, real PostgreSQL/CORE;587 baseline +28 page/parser/kernel +10 vision protocol +12 HTTP/lifecycle +4 metric/live =641. D22 chunking là NEXT; chưa triển khai hoặc đánh dấu PASS.

## Ưu tiên, dependency, effort và ADR

P1, phụ thuộc D17 owned ready/namespace/hash/FD/sandbox, D18 native page provenance và D19 response-lifetime ownership. ADR-029 được ghi trước code; rủi ro renderer hostile input, CPU/pixels/GPU budgets, hallucination/document instructions, uncertainty và delete/cancel races. Chọn xử lý **một trang mỗi request**; native-first `auto`, forced `ocr`, explicit `vlm`. Không tự model-call khi upload hoặc khi OCR confidence thấp. Không tools/history/context/indexing/remote URLs; source và quota/schema giữ nguyên.

Máy có sẵn Tesseract5.5.0 (eng/osd, chưa có Vietnamese traineddata), Poppler26.01.0 và CORE alias qwen3.5-9b-core. Existing CORE thực sự đọc được image/table trong live drill; không restart/thêm inference container. Reuse Pillow/pypdf/bwrap hiện có, không thêm runtime/dev dependency hay migration. Scope tiếng Anh của OCR và unverified/always-review VLM được ghi rõ, không coi đây là chứng nhận arbitrary-language/layout accuracy.

## Code và source/model boundary

- `src/application/services/ocr_contract.py`: strict bounded page/word/box/table/model schemas, version/provenance, confidence/review invariants và safe validation. OCR score là character-weighted engine score, **không phải calibrated correctness probability**; VLM confidence luôn null, review luôn true.
- `src/infrastructure/page_ocr.py`/`ocr_worker.py`: D17 verify source trước parse; PDF native text hoặc selected-page Poppler render; EXIF orientation/RGB/thumbnail và **xóa mọi metadata gồm ICC** trước PNG; Tesseract TSV nhận sanitized pixels, trả text/word boxes trong rendered pixel space. Read-only private sandbox, no private host paths/network/credentials. Child output dùng inherited anonymous bounded stdout, không writable scratch directory.
- `apps/api/services/vision_ocr.py`: configured loopback CORE alias verified; no environment proxies/redirects; strict JSON Schema, fixed transcription-only prompt, no tools/history,1024 output tokens/temperature0/thinking off,45s total/64 KiB response. Finish reason/incomplete/schema failures fail closed, không trả model exception/text trong error/log. Chỉ sanitized raster vào explicit vision mode.
- `FileService.ocr_operation()` giữ1 slot/active task/SH FD đến xong model/response hoặc cancellation. Owner/namespace/ready/size/hash trước CPU, hash/ready trước model disclosure và sau model. CPU thread được join; model async request bị client cancel cũng được join tới bounded completion trước release, tránh submit lặp do cancel. Không khẳng định server-side inference chắc chắn aborted sau network timeout; không restart shared server để xử lý cancel.
- `apps/api/routes/ocr.py` + main: authenticated `POST /api/v1/files/{id}/ocr?page=1&mode=auto|ocr|vlm`. File UUID/hash/page locator/untrusted label, normalized boxes, engine/version, uncertainty/table status; không lộ raster/base64/path; private/no-store/nosniff. JSON cap sau provenance, construction failure/slow send/cancel đều đóng operation.
- `scripts/ocr_acceptance.py`, golden README và tracked `docs/evidence/d21-ocr-acceptance.json`: reproducible synthetic-only quality drill. Metric artifact chỉ giữ version/hash/numeric evidence, không source/model text/image/keys. Default benchmark output vẫn ignored theo repository; retained evidence dùng explicit `--output docs/evidence/...`, không force-add private benchmark directories.

## Resource và product limits

Input image20M-pixel D17 bound; selected page normalized side≤2000/≤4M pixels, PNG≤4 MiB. Worker512 MiB RAM,8/9s per-process CPU,25s parent wall,32FD,zero core,8 MiB stdout; renderer/OCR child deadlines8/10s. Native/OCR/model lexical text64 KiB;5000 words;20 tables/100 rows/20 cells;public JSON1 MiB kể cả locator. Reject thay vì truncate; parent timeout test chứng minh namespace worker và nested child không giữ FD sau kill. One operation/response, no queue, excess429.

`auto` chỉ dùng native PDF text nếu có; mixed pages có thể thiếu text trong image và được báo limitation, caller phải force OCR/VLM. OCR không infer table grid; điểm<85 hoặc không text cần review, English-only/order/table limitations luôn hiện. Empty output không chứng minh trang visual blank. VLM tables là unverified model data; source instructions không có quyền trở thành tools/actions. Calibrated confidence, arbitrary language/layout, load SLO và model server cancellation guarantees vẫn ngoài scope.

## Chất lượng được đo, không che lỗi

Retained metric artifact đã chạy lại bằng actual production parser/client:

- clean.png và scanned.pdf/page1: **CER0/WER0** trên exact known English text; engine scores lần lượt95.634/95.898, không được diễn giải thành xác suất đúng. Source page1/2 và normalized word boxes đúng.
- blank.png và scanned.pdf/page2: empty output, no numeric score, review required; không khẳng định mọi trang blank sẽ luôn được phân loại đúng.
- unclear.png chứa ground truth `uncertain 7381`, bị blur mạnh: OCR không đọc được, **CER1.0/WER1.0 (100% error)**. Gate riêng là `uncertainty_detection`: review required và score absent/low. Không đổi ground truth thành empty để tạo accuracy giả, không gộp case này thành transcription success.
- table-vie.png: actual CORE trả đúng **6/6 cells và exact row order** của table tiếng Việt. Đây là một clean golden, không general Vietnamese OCR benchmark; confidence vẫn null và review required. D18 native extraction trên scanned.pdf thật sự không có text, xác nhận cần fallback.

## Tests và operational evidence

1. **28 page/parser/kernel cases**: actual image/scan/native/blank/degraded/selected-page/error mapping, measured text/box quality, orientation/metadata stripping, forged page/box/nonfinite confidence/review/text/model-schema negatives; worker protocol failures, combined text/word/separator cap, actual kernel/private mount/env bounds và real nested-child timeout/reaping. Logs không lộ recognized text.
2. **10 vision protocol cases**: actual request has strict schema/no tools/history/fixed token/thinking limits; alias/status/redirect/timeout/truncated/malformed/schema/oversized/choice failures safe. Prompt alone không được coi là security certificate.
3. **12 real PostgreSQL HTTP/lifecycle cases**: auth/owner/namespace/ready/hash/source/page/provenance/private headers, no raster exposure, immutable source/quota; wrong type/corrupt/reply cap; delete/cancel/shutdown/post-parser tamper fenced **trước model disclosure**; pending model cancellation join giữ slot/FD, slow response giữ single slot và deletion quota; namespace/construction cleanup đúng.
4. **4 metric/live-quality cases**: known character/word edit-distance oracles và actual CORE/Tesseract/Poppler golden evaluation, retained temp metric artifact không chứa source image/text. Full live flag được cấp qua existing Vault wrapper nên không skip model/DB acceptance.
5. **Final:641 passed in66.51s**,0 skip/no exclusions. Intermediate641/66.34s và641/67.59s chỉ giữ lịch sử; final chạy sau sửa degraded-case oracle và ICC stripping. Focused37/5.42s +16/8.51s trước cuối; final thêm combined-separator budget case và expanded ICC metadata assertion. Operator `uv run python -m scripts.ocr_acceptance --output docs/evidence/d21-ocr-acceptance.json` exit0, retained5 cases +actual table6/6, degraded CER1.0, source SHA/engine versions verified.
6. Ruff selected correctness/import `E4,E7,E9,F,I` (fixture re-export exceptionF811), format12 files, AST descriptions95 definitions, uv lock/diff checks PASS. Không tuyên bố full-repository policy lint ngoài phạm vi. Không dependency/lockfile/schema change.
7. Post-test global file usage `(0,0,0)`, restore probes0; existing shared containers/CORE vẫn running/healthy, không restart/new instance. Private namespace/auth/paired backup không bị thay thế; tests dùng root/UUID riêng và cleanup đúng owner. Vault TLS helper chỉ giao app DATABASE_URL/live flag cho pytest, strip VAULT env/redact; parser/env không nhận keys.

## Các phát hiện đã sửa trước PASS

VLM JSON-object-only probe ban đầu sai schema và bị từ chối502; strict JSON Schema generation sửa được protocol, actual table6/6 PASS. Review scoring phát hiện blurred-case oracle không nên là empty: sửa thành actual source text và giữ CER100% với uncertainty gate riêng. Expanded JPEG test tái hiện Pillow giữ ICC profile dù đã re-encode PNG; assertion FAIL trước fix, `normalized.info.clear()` làm test PASS, rồi chạy lại full641. Chỉ final evidence sau tất cả sửa được dùng chốt D21.

Roadmap v3.14, ADR-029, design/runbook/golden README và retained evidence cập nhật cùng tiến độ. Full-version source archive tại `/tmp` tách khỏi credentials/user data/backups. **Next D22:** P1 deterministic chunks theo page/paragraph/table/sheet, stable source/hash/version/span IDs và ACL labels; carry OCR/VLM review/uncertainty. ADR trước persistence/API mới; golden source mapping/size/idempotence/access tests +full regression phải PASS trước khi chuyển D23.

---

# Ngày 22 — Deterministic private chunks, provenance và access labels (2026-10-18)

**Mục đích:** Ghi lại D22 triển khai/kiểm thử thực tế sau D21 PASS, cùng giới hạn identity/source/response và handoff D23.

**Kết quả:** **D22 PASS trong phạm vi localhost/one worker**. Final full Vault-backed regression **700 passed in76.12s**, exit0, **0 SKIP**, không exclusions;641 baseline +30 mapping/identity/budget +29 real PostgreSQL HTTP/lifecycle. Existing CORE cũng được kiểm tra bởi live suite D21. D23 mixed-document evaluation/repair là NEXT, chưa PASS hoặc triển khai trong milestone này.

## Ưu tiên, dependency, effort và ADR

P1, phụ thuộc D17 owned namespace/ready/hash/SH FD, D18–D21 native/structured/OCR projections và response ownership. ADR-030 ghi trước code; effort một hoặc nhiều milestone tùy acceptance. Rủi ro chính: mất table structure/source spans, unstable IDs, lẫn owner/namespace, oversized row/metadata, mất uncertainty và delete/cancel/shutdown races. Reuse parser/worker/runtime hiện có; không thêm dependency, schema, index, service hay persistence. UTF-8 bytes là policy v1; tokenizer/embedding vẫn D24, không gọi byte budget là token budget.

## Triển khai và kiểm tra liên quan

- `document_chunks.py`: exact Unicode code-point spans; text split không normalize/trim/overlap, giữ ranh giới page/paragraph; empty fields có record riêng. Atomic rows dùng canonical sorted-key UTF-8 JSON; oversized row413 thay vì split/truncate. SHA-256 ID bind private owner/namespace/file, source SHA, parser/chunker version, byte policy và toàn bộ text/span/structure/section/quality. Access labels private/principal/opaque scope do server tạo, không lộ namespace và không cấp quyền truy cập.
- `chunk_sources.py`: golden PDF page mapping; DOCX declared Heading1–9/basedOn section refs, paragraphs/table rows với row/column/gridSpan/vertical merge; XLSX sheet/row/address/type/style/formula attributes/cache/merge metadata. Source field spans giữ exact lexical values/formulas/caches, không evaluate. Nested/overlapping table paragraph membership và cyclic heading ancestry422. Input ordering của DOCX paragraphs/styles/cells và XLSX sheets/cells không làm đổi deterministic result.
- OCR narrative/table là hai projections có nhãn riêng; quality/review/confidence basis/uncertainties/coordinates/dimensions đi theo từng chunk/empty field. VLM luôn review/null confidence; table chưa verified. Không nhân bản word arrays; D21 page endpoint vẫn cung cấp boxes. Nondeterministic model content thay đổi thì ID thay đổi đúng contract; không tuyên bố same source luôn cho cùng model transcription.
- `apps/api/services/chunks.py` giữ1 slot/active task/outer verified SH FD qua joined parser/transform và response; reuse DOCX/XLSX/OCR contexts đến cuối delivery. Final independent source hash và owned ready fence sau construction. Plain UTF-8 reader bounded1 MiB+1; supported TXT/MD/CSV lexical, không infer CSV table. Source `auto` PDF native toàn bộ pages; explicit OCR một page, VLM chỉ khi caller yêu cầu.
- `apps/api/routes/chunks.py` + main: authenticated `POST /api/v1/files/{id}/chunks?max_bytes=2048&source=auto&page=1&ocr_mode=auto`; UUID/hash/processor/chunker/policy/access/locators/spans/untrusted metadata, private/no-store/nosniff. Invalid/irrelevant options fail422, wrong OCR source415; owner/namespace404, not-ready409, integrity503. Response construction/send/cancel đều đóng context.
- **Thay đổi cần thiết trên FileService đã PASS:** thêm counter cho chunk operation và reference count nested `track/untrack`, vẫn giữ active task set cho shutdown. Vì D22 giữ parser context lồng trong outer source context, inner exit trước đây có thể discard outer task khỏi shutdown inventory. Đếm depth bảo vệ outer source đến khi close; không đổi auth/schema/quota/parser/upload/download/recovery contracts. Có test trực tiếp inner-close và slow-response cho cả text/DOCX/XLSX/OCR; full baseline regression giữ PASS.

## Resource/product limits

Chunk text256–8192 UTF-8 bytes, default2048; table row là một chunk, chưa group nhiều rows. Projected lexical text/structured-row JSON tối đa1 MiB, combined chunks/empty records1000, complete reply8 MiB kể cả provenance. Metadata được tính tăng dần trước khi tích lũy complete reply, sau cùng và ở response đều kiểm cap; merged-range metadata chia sẻ trong bộ nhớ thay vì sort/copy lại mỗi row. Existing D18–D21 parser limits giữ nguyên. Không partial/truncated result.

DOCX section dựa vào declared heading ancestry, không visual heading inference/rendered-page claim; D19 main-body scope không tự mở rộng header/footer. Nested/ambiguous table unsupported. CSV là lexical text. Row vượt byte cap fail413 kể cả khi text value ngắn nhưng structured metadata lớn. Byte policy chưa tối ưu cho tokenizer; access labels/IDs chỉ mô tả trusted server decision, future retrieval vẫn phải query source ownership. OCR English-only/raw-score/mixed-page/always-review limitations và formula stale-cache flag giữ nguyên. Chunking ephemeral; chưa embedding/index/cache/generated-output persistence hay model-context attachment.

## Evidence kiểm thử và vận hành

1. **30 mapping/identity/budget cases PASS:** exact source reconstruction gồm ASCII/Vietnamese/combining codepoints/emoji/whitespace/empty, UTF-8 byte caps, native PDF3page/blank; actual sandbox DOCX paragraph/section/table/merge và XLSX row/formula/cache/style/merge fixtures. Complete cell objects/source field spans giữ nguyên. Heading inheritance/subsection reset, cyclic/nested rejection; canonical digest tính độc lập; repeat/reordered input ổn định, changed owner/namespace/file/hash/processor/policy/content/section/quality/structure đổi ID. Count/source/atomic-row/metadata limits; overbudget iterator dừng trước next unit.
2. **29 real DB HTTP/lifecycle cases PASS:** TXT/MD/CSV/PDF/DOCX/XLSX/image actual uploads/chunks, source UUID/hash/access locators/private headers và repeat IDs; anonymous/foreign/ready/deleted/query/media negatives. Native scanned-PDF empty projections và explicit selected-page OCR empty/review đúng. Controlled explicit VLM qua real sanitized raster giữ narrative/table/uncertainty flags; actual CORE call được giữ trong full suite hiện có, không coi controlled model test là live accuracy evidence.
3. Source immutable download/allocation; pre/post transform corruption, final ready fence, joined cancellation/shutdown, delete pending giữ quota và release sau close. Slow response của cả text/DOCX/XLSX/OCR giữ chunk single-slot, parser nested depth và owner-first rejection; cancel đóng mọi reader/counter/task. Wrong namespace, response construction failure, reply/source limits đều cleanup đúng. Không reset global counters để làm test xanh.
4. Focused trước refinements **56 passed in9.48s**; final sau incremental metadata cap/empty-count/explicit VLM integration **700 passed in76.12s**,0 skip/no exclusions. Một lệnh tạo test ban đầu dùng sai prefix thư mục nên không tạo file/no tests collected; đã sửa path, không tính là kiểm thử thành công. Initial shell edit gọi `python` không có binary cũng được chạy lại đúng bằng `uv run python`; không dùng kết quả failed commands làm acceptance.
5. Ruff selected correctness/import `E4,E7,E9,F,I`, fixture re-export exceptionF811, format8 files; AST descriptions8 files/79 definitions; `uv lock --check` và diff checks PASS. Không dependency/lockfile change hay tuyên bố full-repository lint ngoài scope.
6. Post-test Vault audit: global file usage **(0,0,0)**, restore probes **0**. Existing CORE/shared containers vẫn running/healthy, không restart/new instance. Private root/namespace/auth/paired backup không thay thế; tests dùng disposable UUID/root và owner cleanup. Vault helper TLS cấp app DB/live flag trong memory, strip VAULT env/redact output; không in key/source text hoặc đưa secret vào code/archive.

Roadmap v3.15, ADR-030, file design và local runbook cập nhật cùng evidence. Full-version source-only archive `/tmp/local-assistant-d22-complete-full-files.zip` chứa toàn bộ file thay đổi, không credentials/runtime data/backup. **Next D23:** P1 mixed-document evaluation/error report với independent golden oracles, honest empty/degraded/unsupported outcomes, source-span coverage và measured stage evidence. Đánh giá priority/dependency/effort/risk trước phát sinh; repair chỉ khi có failure, ADR trước đổi architecture/API/persistence, full regression PASS trước chuyển D24.

---

# Ngày 23 — Mixed-document pipeline evaluation và error/quality report (2026-10-18)

**Mục đích:** Ghi lại corpus độc lập, pipeline drill thực tế và bằng chứng D23; giữ riêng lỗi nhận dạng thật với acceptance của uncertainty/rejection contracts.

**Kết quả:** **D23 PASS trong phạm vi local đã định nghĩa**. Final full Vault-backed PostgreSQL/CORE regression **748 passed in92.02s**, exit0, **0 SKIP**, không exclusions;700 baseline +30 scorer/failure/CLI +18 corpus/live. Corpus thực tế **18/18 case gates PASS**, **56/56 source fields** covered,32 chunks/7 empty records. D24 embedding selection/Qdrant collection design/ADR là NEXT; chưa triển khai/đánh dấu PASS.

## Priority, dependency, effort và quyết định scope

P1, phụ thuộc D17 verification, D18–D21 native/structured/OCR/read/write và D22 deterministic chunks. Effort một hoặc nhiều milestone tùy acceptance; rủi ro circular oracle, che OCR failure sau pass count, mất source spans/structure, expected rejection bị hiểu nhầm thành hỗ trợ mọi input, content/key leakage trong evidence. Đã kiểm tra code và các hợp đồng liên quan trước triển khai. Chỉ thêm scripts/fixtures/tests/docs/evidence; **không sửa code/config production, dependency, schema, root/auth/namespace hoặc service**. Không có thay đổi kiến trúc quan trọng/API/persistence nên không cần ADR mới; ADR-026–030 vẫn authoritative. Evaluation chưa tìm thấy supported-contract failure cần repair; không thay thành phần PASS chỉ để tạo thay đổi.

## Corpus, evaluator và independent scoring

- `tests/fixtures/pipeline/manifest.json` +README:18 case oracles viết từ source construction và existing independent golden docs, không serialize output production thành expected answer. Reuse native PDF3 pages, DOCX7 paragraphs/table/style, XLSX2 sheets/formula/cache, OCR clean/scan/blank/blur/Vietnamese table. Thêm synthetic TXT/Markdown/CSV có Unicode combining/non-BMP/CRLF/quoted newline, nested DOCX và malformed PDF có purpose rõ ràng. Fixtures không chứa user data/key/macros/external relationships.
- `scripts/document_pipeline_acceptance.py`: CLI chỉ dùng packaged trusted synthetic corpus, không nhận arbitrary source path. Verify/parser thực tế qua borrowed **read-only FD**; stage wall/child CPU và cumulative child peak RSS giữ cả stage lỗi. Fixed DOCX run edit `Đã sửa` và XLSX A2 numeric99.5 dùng source hash; dev-only python-docx/openpyxl độc lập reopen, untouched ZIP members byte-identical, formula/cache/style/merge đúng; reparse/chunk output bằng output SHA và synthetic identity riêng.
- `scripts/document_pipeline_oracles.py`: exact text/cells/styles/table/formula/cache so với handwritten manifest; independently assemble private identity/digest và exact page numbering. Source spans phải đúng field/range, không missing/gap/overlap/duplicate/foreign references; text slices reconstruct exact original extracted content, row text đúng canonical structured JSON. Table/sheet row objects, section refs và OCR/cache quality phải giữ nguyên. Repeat chỉ cùng parsed content, không giả định model transcription deterministic.
- Expected rejection bắt buộc exact **stage/code/status**. Unexpected accept/reject/exception fail gate, error fixed/sanitized, các case sau vẫn chạy. CLI không bật `--include-vlm` thì vision case `not_run`, complete/pass false và exit1. Explicit flag dùng existing local CORE; không implicit model call khi OCR score thấp, không restart hoặc new service.
- Retained `docs/evidence/d23-document-pipeline.json` chỉ có synthetic case/fixture names, hashes/versions/check flags/counts/CER/WER/table matches và timing/resource evidence. Không source text/model output/images/private exceptions/credentials. `failures` và `quality_failures` tách riêng; UTF-8 budget vẫn không phải embedding token budget.

## Kết quả đo thực tế, giữ nguyên giới hạn

Lệnh thực tế: `uv run python -m scripts.document_pipeline_acceptance --include-vlm --output docs/evidence/d23-document-pipeline.json`, exit0. Final retained run tổng sequential case wall **6401.331ms**,18 cases: **11 accepted**, **3 empty**, **1 degraded**, **3 expected_rejection**, gate failures0.56/56 lexical source fields covered,32 chunks/7 empty records; native/structured golden exact và independent rewritten outputs reopen đúng. Actual CORE trả exact **6/6 Vietnamese table cells/3 rows**, review required/confidence null; narrative không được chấm bằng invented ground truth.

- Scanned PDF native mode trả hai empty projections, không giả vờ đã OCR; explicit OCR page1 exact known text, page2 empty/review đúng.
- Blank image và scan page2 không có text/score, cần review; empty recognition không chứng minh visual page luôn blank.
- Blurred fixture ground truth vẫn `uncertain 7381`, OCR hiện tại không đọc được: **CER1.0/WER1.0 =100% transcription error**, giữ `transcription_passed=false` và `quality_failures`. Case PASS vì required uncertainty detection hoạt động, **không phải accuracy PASS**.
- Nested table422 `unsupported_chunk_structure` tại adapt; XLSX row vượt256-byte cap413 `chunk_row_too_large` tại chunk; malformed PDF415 `invalid_file_content` tại verify. Đây là đúng supported contract, không phải successful data extraction.
- Child peak RSS là cumulative Linux KiB từ RUSAGE_CHILDREN, không per-case memory hoặc CORE GPU usage; child CPU không đo model-server CPU. Stage wall/CPU là local observations, không SLO/concurrency/production memory certification. Existing parser kernel/resource regression mới là evidence cho enforcement.

## Tests và audit

1. **30 scorer/failure/CLI cases PASS:** known exact split Unicode/empty coverage; deliberately dropped/duplicated/gapped/overlapping/foreign/out-of-range/noninteger spans, wrong text/page/owner/hash/digest/bytes/formula/cache quality phải fail gate đúng. Mutant production identity bỏ namespace vẫn bị independent oracle phát hiện. Native expected text không lấy từ parser. Degraded OCR metric giữ transcription failure dù uncertainty gate PASS.
2. Explicit model default không call; unrun không PASS. Unexpected private exceptions sanitized; wrong rejection stage/status không được coi expected. Corpus tiếp tục sau một stage fail; aggregate report giữ failed check/stage. CLI exit chỉ0 khi complete+passed; fixture path escape refused, descriptor write attempt thật bị OSError.
3. **18 integration/corpus cases:**17 actual non-VLM scenarios mỗi scenario riêng và1 complete actual CORE report drill. Full report phải18/18, table6/6, coverage100%, known blur quality failure còn nguyên; write/read report equality và content/key markers absent.
4. Initial scorer24 PASS/0.16s; focused **46 PASS/17.09s** trước page/independent private-identity refinements. Final scorer **30 PASS/5.48s** và final full **748 PASS/92.02s**,0 skips/exclusions. Default initial corpus intentionally exit1 vì vision chưa opt-in; không dùng incomplete result đánh dấu PASS. Explicit full corpus được chạy lại sau final evaluator changes, retained18/18; final full chạy sau mọi code/test changes.
5. Ruff selected correctness/import `E4,E7,E9,F,I` và format4 Python files PASS; AST descriptions4 files/40 definitions; `uv lock --check`, diff và fixture/report hashes/privacy PASS. Không tuyên bố full-repo lint hoặc model quality dựa trên pytest count. Không dependency/lockfile change.
Staged diff ban đầu phát hiện trailing tab/CRLF có chủ đích trong Unicode golden. Giữ nguyên tested bytes và thêm fixture-local `.gitattributes` (`-text`, scoped whitespace rule) để checkout không normalize source; staged diff check sau đó PASS. Không sửa implementation/test data sau final regression, chỉ Git attributes và documentation.

6. Post-test Vault audit global file usage **(0,0,0)**, restore probes **0**; existing CORE/shared containers vẫn running/healthy, không restart/new instance. Private source/root/auth/paired backup giữ nguyên; regression disposable owner/root được cleanup. Vault TLS helper chỉ cấp app DATABASE_URL/live flag trong memory, strip VAULT env/redact output; không in key hoặc đưa credentials vào artifact.

## Handoff và feature assessment

`docs/DOCUMENT_PIPELINE_EVALUATION.md` ghi priority/dependency/effort/risk trước xếp lịch cho các giới hạn có thể phát sinh feature: degraded/multilingual OCR P2/2–4 milestones phụ thuộc corpus/routing/model budgets, nested table P2/1–3 phụ thuộc hierarchy/locators, row splitting P2/1–2 phụ thuộc D24 tokenizer/versioned span contract. Chưa đưa vào current milestone; OCR/nested backlog sau D32 nếu không có blocker thực tế, row splitting đánh giá sau D24. Không auto-repair/embedding/indexing/context attachment.

Roadmap v3.16, evaluation spec, corpus README, file design/runbook và retained report cập nhật cùng evidence. Full-version source-only archive `/tmp/local-assistant-d23-complete-full-files.zip` chứa toàn bộ file thay đổi, không runtime data/backup/keys. **Next D24:** P1 đo shortlist embedding bằng independent multilingual retrieval oracles, actual local accuracy/memory/latency/tokenizer constraints và ADR collection schema/ACL/model-version/distance/update-delete/rollback. Reuse existing Qdrant, không new container/replace user collections; D25 ingestion và D26 search vẫn các gate riêng. Chỉ chuyển sau Acceptance Criteria thực sự đạt.

---

# Ngày 24 — Measured CPU embeddings và private Qdrant collection design (2026-10-18)

**Mục đích:** Ghi lại model shortlist/corpus độc lập, lựa chọn có số đo thực tế và ADR/schema/lifecycle trước khi triển khai ingestion.

**Kết quả:** **D24 PASS cho local selection/design**, chọn **intfloat/multilingual-e5-base, official ONNX int8 AVX512-VNNI,768 dimensions**. Final full Vault-backed regression **783 passed in95.11s**, exit0, **0 SKIP**, không exclusions;748 baseline +33 unit/negative +2 real CPU/Qdrant. Existing PostgreSQL/CORE/Qdrant được kiểm tra thật. **D25 durable ingest/upsert/delete/worker là NEXT**; chưa worker/production collection/vector points/search API.

## Priority, dependency, effort, inventory và ADR

P1 phụ thuộc D17 owned journal/source FD, D22 chunks/hash/access labels và D23 independent corpus. Effort một hoặc nhiều milestone; rủi ro Vietnamese/cross-language quality, silent truncation, model/runtime drift, CORE GPU contention, stale vectors/cross-owner data và shared collection mutation. Đã đọc roadmap/devlog/code/config/infra/Qdrant/Vault helper. ADR-031 ghi trước dependency/model/probe changes; nguồn primary là official E5 cards, ONNX Runtime/tokenizers API và Qdrant collections/multitenancy docs, có links trong ADR/spec.

Máy Ryzen7 7700/16 logical CPUs, AVX512-VNNI, khoảng30GiB RAM; RTX4070Ti SUPER16GiB còn khoảng5GiB VRAM tại inventory khi CORE chạy. Existing Qdrant1.18.2 dùng chung, không new container/restart. Chọn shortlist CPU-only2-thread ONNX int8 chính thức small384/base768, cả hai upstream MIT, pin repository commit và từng model/tokenizer SHA/size. Dev-only `onnxruntime1.31.0`, `tokenizers0.23.3`, transitives `flatbuffers25.12.19`/`protobuf7.36.2` qua uv; uv.lock purpose header giữ lại. Không Torch/CUDA stack/runtime service/app source/DB schema/auth/root/model CORE config change.

## Corpus và ngưỡng cố định trước khi đo

`tests/fixtures/embedding/retrieval.json` gồm20 related synthetic passages và40 handwritten Vietnamese/English/cross-language queries, relevance source ID độc lập. Có distractors gần nhau: backup/restore, OCR/VLM, chunks/tokens, delete/retry, health/quality. Không lấy D23 reconstruction làm retrieval accuracy oracle. Labels/gates không đổi sau khi thấy kết quả.

Ngưỡng ADR/corpus: Recall@3≥0.90, MRR@10≥0.80, mỗi language group Recall@3≥0.80, peak child RSS≤2048MiB, warm single-query p95≤500ms. Trong eligible candidates, chọn RSS thấp nhất nếu cách best MRR≤0.05; không có eligible thì milestone không PASS. Exact ID tie-break/rank/fractional recall và reciprocal rank≤10 có independent unit oracles.

## Kết quả thực đo và lựa chọn

Retained `docs/evidence/d24-embedding-selection.json`, generated bằng actual isolated CPU sessions, không mock model:

| Candidate | Recall@3 / MRR@10 | cross / en / vi Recall@3 | Peak child RSS | Warm query p50 / p95 | Cold load | Gate |
|---|---|---|---|---|---|---|
| multilingual-e5-small int8/384 |0.750 /0.655377 |0.500 /0.9375 /0.6875 |558.156MiB |2.051 /2.409ms |648.092ms | FAIL chất lượng |
| multilingual-e5-base int8/768 |0.925 /0.874405 |0.875 /1.000 /0.875 |802.863MiB |6.321 /7.378ms |888.308ms | PASS, selected |

Small nhẹ/nhanh hơn nhưng không đạt các ngưỡng quality; không hạ ngưỡng để làm xanh. Base là eligible duy nhất, vẫn top3 miss `delete-en` rank6, `ocr-vi` rank7, `embedding-vi` rank11; mọi query rank/top3 được giữ lại. Đây là20/40 synthetic short-query local selection, không phải general Vietnamese/MTEB accuracy hay global-best model. D26/D27 phải mở rộng independent retrieval/quality/reranking, giữ nguyên lịch sử miss.

Selected repo revision `d128750597153bb5987e10b1c3493a34e5a4502a`, model SHA `2523551878658b305550d8759443822dbfda9ed9c8012ef2c354ba2c5b9de503`, tokenizer SHA `62c24cdc13d4c9952d63718d6c9fa4c287974249e16b7ade6d5a85e7bbb75626`. Base model+tokenizer295769071 bytes; small135429554. Fingerprint `e8e395bc1b54979c09466eab46e949c197b99abe2518793612bb0cdc582b02dc` bind toàn bộ pins/prefix/pooling/norm/token/runtime-format/package versions. `configs/embedding-selected.json` ghi **selected_not_deployed**, full-fingerprint collection name; không tự enable service.

## Code, token/resource contracts và probe

- `embedding_runtime.py`: explicit public pinned downloads atomic publish/hash/size, remove partial; missing/changed artifact reject, không implicit API startup/test downloads. Weights trong ignored models/embedding, không source archive. No remote Python code/private Hub key. Provision lần đầu có HTTP signed public-CDN redirect logs của public assets; CLI hiện giảm HTTP logger xuống WARNING, không liên quan user/Vault credential.
- CPUExecutionProvider only,2 intra-op/1 inter-op/sequential, batch≤4. Thật sự disable tokenizer truncation/padding, thêm `query: `/`passage: ` kể cả tiếng Việt, mask mean pool/L2 normalize, finite/nonzero/exactdimension checks. Empty/over32768-byte text hoặc>512 total prefix/special tokens reject; không silenttruncate. Corpus max passage/query45/24 tokens; cả hai measured overflow rejected, repeat delta0, unit norm error≈5.96e-8. Đây không chứng nhận long-context performance.
- `embedding_acceptance.py`: mỗi candidate là child process mới, env whitelist không keys/VAULT/Hub/proxy, fixed180s wall/120–121s CPU/4GiB virtual memory. RSS là per-child process, latency excludes download;20-passage encode60.812/167.112ms. Không claim load SLO/GPU/model-server CPU. Parent report không raw text/query/vector/private exception.
- `qdrant_embedding_design.py`: plan named dense768/Cosine/on_disk,1 shard/replica,10 indexes owner UUID `is_tenant=true`, namespace/file UUID và hash/chunk/chunker/processor/model/generation/state keywords. Only fresh random la_d24_probe name, collision reject, cleanup chỉ khi create acknowledged; schema/index lỗi vẫn remove owned probe. Lost create acknowledgement cần scoped audit, không tự nhận/xóa collection khác.
- Actual Vault `secret/server/qdrant/admin` chỉ đọc vào memory; existing loopback6333, no proxy/redirect, bounded reply/timeouts/error sanitation. Retained `docs/evidence/d24-qdrant-design.json`: actual1.18.2 schema/10 indexes/UUID tenant accepted, zero points, probe removed; existing collections0, before/after fingerprints identical. Không production collection/point/ingestion hoặc shared-data mutation.

## Lifecycle/ACL design chưa bị nhầm thành implementation

ADR-031 mô tả payload server-derived owner/namespace/file/source SHA/chunk/chunker/processor/model/index-generation, UUIDv5 point identity, pending→active publication sau complete upsert/final ready/hash fence, durable job/outbox/idempotency/retry/reconcile và tombstone cleanup. PostgreSQL/Qdrant không có distributed atomic transaction; delete phải ẩn PostgreSQL ngay và retrieval sau này luôn rehydrate/revalidate source, không tin vector alone hoặc caller access labels. Shared Qdrant admin key không phải user ACL.

Đây là design cho **D25/D26**, chưa code production. D25 cần ADR/migration/journal/admission/worker thật, token preflight (D22 byte cap không đảm bảo512 tokens), source/hash/owner/namespace fencing, crash/retry/update/delete/generation consistency và rollback. Không chunk truncation, implicit embed/index/model-context attachment. Nguồn đã PASS, OCR blurred failure/stale formula cache/nested422/row413 giữ nguyên.

## Tests, evidence và post-audit

1. **33 unit/negative PASS:** independent known ties/multi-relevance/rank/recall/MRR và malformed/nonfinite/foreign/duplicate labels; frozen quality/group/memory/latency/overflow/repeat gates, quality-tolerance/RSS selection, masked mean hand vector và invalid mask/norm/dimension; prefix/special token512/513, actual full input retained; fingerprint invalidates revision/tokenizer/runtime; mock public download exactbytes/hash/oversize/partial cleanup và no Authorization.
2. Probe tests giữ synthetic shared collection7 points, never mutate foreign names; index/schema/server errors cleanup acknowledged probe, creation conflict không delete, existing-name collision không mutating call, changed inventory không PASS, server bodies không lộ. **2 live**: actual two pinned CPU models và actual Vault-authenticated Qdrant empty schema/index/cleanup. Model report giữ smaller-candidate failure.
3. Focused **35 PASS in3.03s**; final full **783 PASS in95.11s**,0 skip/no exclusions. Existing wrapper mở rộng đọc Qdrant key từ Vault vào pytest env và redact cùng DB/key/token; embedding children whitelist env, production parsers vẫn clear env. Không hardcode/in key; không dùng missing-key skip như acceptance.
4. Ruff correctness/import `E4,E7,E9,F,I`/format6 files, AST descriptions6 files/44 definitions, `uv lock --check`, artifact/corpus/report/selected-config fingerprint/privacy và diff checks PASS. Không tuyên bố full-repo lint. Runtime dependencies không tăng, chỉ dev group.
5. Post-test file global usage **(0,0,0)**, restore probes **0**, Qdrant collection count **0**, remaining D24 probes **0**. Existing CORE/shared containers running/healthy, không restart/new instance; private root/namespace/auth/paired backups giữ nguyên. Không đổi apps/src/source schema để phục vụ benchmark.

Roadmap v3.17, ADR-031, selection spec/fixture README, file design/runbook và retained reports cập nhật cùng acceptance. Full-version source-only archive `/tmp/local-assistant-d24-complete-full-files.zip` chứa file thay đổi đầy đủ, không weights/runtime data/backup/credentials. **Next D25:** P1 durable incremental ingestion/worker; estimate nhiều milestones nếu cần, ADR trước persistence/API/schema, actual token/source/owner/generation/crash/retry/delete tests và full Vault-backed regression mới được đánh dấu PASS. D26 ACL search, D27 retrieval evaluation là gates riêng.

# 2026-10-18 — MODEL-EVAL-001: actual Qwen/E5 comparison and transition proposal

**Purpose:** Audit the owner-authorized offline evaluation separately from D24 and the unimplemented D25 ingestion work.

## Authorization and preserved state

Owner's latest “Làm đi” authorized the proposed Qwen download and benchmark. This supersedes the earlier no-download instruction only for evaluation; selected model/cutover still requires owner approval of measured tradeoffs and migration/rollback. The complete MODEL_REGISTRY lineup is preserved unchanged. D24/a88584b remains PASS for its historical E5-only local selection/design scope. D25 remains NEXT; this evaluation is not D25 implementation.

Downloaded official Qwen3-Embedding-0.6B revision97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3 (Apache2.0), four artifacts1203020554 bytes, exact SHA256 verified in ignored local model storage. Used official BF16 CPU safetensors,1024 dimensions, upstream query instruction/plain documents/last-attended-token pooling/L2 normalization. Common512-token cap with truncation disabled; native32K context is not certified. Frozen20 passages/40 queries/chunks/labels unchanged. No third-party model conversion or replacement downloaded.

ADR-032 preceded execution. Added evaluation-only profile, comparison/runtime/worker scripts and tests; production E5 adapter/application source remain unchanged. Qwen uses separately locked uv script environment, torch2.10.0+cpu/transformers4.57.6,2 intra-op/1 inter-op threads,batch4. An initial dependency sync failed because a typing-extensions4.16 wheel lacked package Name metadata; pinning4.15 resolved isolated environment provisioning. Project pyproject.toml/uv.lock were not modified. Workers receive no Vault/API/DB/Hub/proxy credentials, run offline with bounded wall/CPU/memory, GPU allocation0.

## Actual measurements

Six sequential fresh-process runs (three per candidate), stable ranks and identical input hashes; all frozen D24 reference gates met. Different precision/runtime must be considered: E5 int8/ONNX versus Qwen BF16/PyTorch. These results compare those feasible configurations, not model-only speed.

| Measurement | E5-base | Qwen3-Embedding-0.6B |
|---|---:|---:|
| Recall@3 |0.925|0.975|
| Recall@5 |0.925|1.000|
| Recall@10 |0.975|1.000|
| MRR@10 |0.874405|0.968750|
| Peak RSS max, MiB |803.305|1318.086|
| Warm query p95 max, ms |6.744|113.928|
| Cold load range, ms |921.824–958.977|2189.158–2211.451|
| Batch passage throughput range, per second |120.072–122.644|14.983–15.771|

E5 top3 misses: delete-en rank6,ocr-vi rank7,embedding-vi rank11. Qwen only embedding-vi rank4. Per-group results, every relevant rank/top10 and all repetitions are retained in docs/evidence/model-eval-001-qwen-e5-comparison.json. Small synthetic corpus limits generalization; Qdrant ingestion throughput/disk, long-input quality and concurrent CORE impact remain NOT MEASURED. Flat-memory vector/index metrics are not Qdrant results.

## Tests and review outcome

- Scoped actual-model and unit regression: **58 PASS in11.34s,0 SKIP**. Includes instruction/pooling/overflow/independent rank metrics, credential-free workers, retained measurements, proposed-config guard and exact E5 rollback; existing embedding-selection/Qdrant-design unit tests included. No stateful live-service tests were invoked. Historical783 PASS/95.11s remains historical, not rerun.
- Ruff correctness/import checks and format passed on five Python files. All functions/classes have English descriptions. Input/artifact/runtime hashes are retained. Selected E5 configuration, E5 shortlist/runtime/acceptance scripts, original D24 evidence, frozen corpus, project dependency files and MODEL_REGISTRY remain unchanged; no Docker/Vault/database/Qdrant operations or collection/data changes. HEAD stays a88584b.
- Roadmap v3.19, backlog and append-only ADR-031 follow-up link ADR-032 and the new evidence. docs/QWEN_E5_COMPARISON_AND_TRANSITION.md explains tradeoffs and a concrete full reindex/cutover/rollback plan; docs/evidence/model-eval-001-transition-proposal.json contains proposed Qwen configuration and exact current E5 rollback, not active config changes.

**Recommendation:** Propose Qwen as the original registry-aligned target, accepting measured latency/RAM costs, after owner approval and deployment gates. **MODEL-EVAL-001: offline comparison complete / broader task partial / OWNER_APPROVAL_PENDING.** D24 unchanged, D25 NEXT. Leave patch uncommitted for review; no automatic deployment, schema migration, collection creation, deletion or mixed vector spaces. Full source-only files archive: /tmp/local-assistant-model-eval-001-complete-full-files.zip; downloaded weights/credentials/runtime data excluded.

# 2026-10-18 — Owner-approved Qwen selection applied

**Purpose:** Audit the approved model/configuration change and retained E5 rollback separately from deployment acceptance.

The owner replied “Làm đi” after the actual Qwen/E5 results, concrete migration/rollback review and clarification that Qwen's measured1.29GiB peak is system RAM, not VRAM. This approves the proposed Qwen selection. Applied `configs/embedding-selected.json` with official pinned Qwen3-Embedding-0.6B BF16 CPU,1024 dimensions, exact benchmark runtime/packages/fingerprint, official query instruction/plain documents/last-token L2,512-token cap and status **selected_not_deployed**. No production embedding worker or retrieval endpoint exists yet; changing selection does not claim a live service cutover.

Before applying, verified the original selected file SHA256 against the reviewed proposal and exact rollback JSON. Saved its bytes unchanged in `configs/embedding-e5-rollback.json`, then atomically replaced selected config. `docs/evidence/model-eval-001-selection-approval.json` records owner authorization, before/after SHA256, model fingerprint, rollback path and explicit deployment/collection/data-migration=false. Original preapproval proposal and six-run measurements remain unchanged as historical evidence. E5 artifacts, original shortlist/corpus/runtime/dependencies, D24 evidence/commit, MODEL_REGISTRY and all existing data remain preserved; no Docker/Vault/database/Qdrant operation occurred.

Updated roadmap v3.20, model backlog, embedding selection specification, transition review and append-only ADR-031/032 decision records. Current Qwen selection is distinguished from historical D24 E5 acceptance. D24 remains PASS; D25 remains NEXT, now targeting Qwen with production adapter/durable ingestion/token/ACL/generation/retry/delete/rollback gates still open. No automatic collection creation, reindex or routing switch.

Validation: **59 PASS in11.44s,0 SKIP** using explicit actual-model offline flag and `uv run --no-sync pytest` over comparison tests, actual E5/Qwen integration, embedding-selection and Qdrant-design unit suites. New selection checks validate owner audit/hash, exact rollback, unchanged reviewed proposal, model-specific preprocessing/runtime identity and separate1024-dimensional space. Actual Qwen process identity/packages/fingerprint match selected config; both real models preserve config/evidence hashes during inference. Ruff correctness/import checks and formatting passed. Full DB/CORE/Qdrant783-test regression was not rerun; its prior D24 result stays historical. Full-file source-only archive: `/tmp/local-assistant-qwen-approved-selection-complete-full-files.zip`; no weights, credentials or runtime data.

# 2026-10-18 — D25-T01: deterministic ingestion plans and actual Qwen token admission

**Purpose:** Record the first D25 implementation milestone with observed tests while keeping durable ingest/update/delete acceptance open.

## Scope and architecture

Read the current roadmap, model registry/selection, D24 design/ADR-031/032, D22 chunk builder/service, file journal/source lifecycle, current migrations and related integration tests. Recorded **ADR-033 before implementation**. D25 split into T01 source/model/token admission, T02 durable PostgreSQL journal/migration and T03 bounded embedding/Qdrant upsert/delete/recovery; these are dependencies within existing D25 scope, not automatic Day advancement. P1, multiple milestones; reviewed distributed-commit, stale-source, ACL, truncation, lease, resource and rollback risks.

Added immutable source-bound ingestion plans: trusted ready owner/file/namespace/hash checks, recomputed exact D22 chunk identities, duplicate/tamper/foreign rejection, bounded text/chunk/metadata, model contract fingerprint validation and deterministic SHA256 generation/UUIDv5 job/point identities. Retries preserve IDs; owner/root/file/hash/processor/byte policy/content/metadata/order changes create a different generation. Canonical private payloads retain provenance/quality/uncertainty with pending state, separate from raw embedding text. Exact Unicode, atomic row/formula/cache content and explicit empty generations remain intact. Descriptive D22 labels/digests are consistency checks, never caller authorization.

Added `validate_source_fence` to reject stale/missing/deleted/nonready/foreign/changed-hash metadata before future admission/publication. It does not itself acquire DB locks; T02/T03 must call it inside short source-locked transactions and retain existing FileService integrity/source-reader checks. No endpoint accepts client-supplied chunks or access assertions.

Added an isolated frozen uv Qwen tokenizer worker and host adapter. Same pinned official profile/runtime fingerprint as approved selection, local-only/remote code disabled, unprefixed complete passages, no embedding-model weight load/session and no GPU/network/download. Separate script lock/environment provisioned entirely from cached dependencies; project pyproject.toml/uv.lock and original benchmark lock/environment unchanged. One nonqueued process-local admission, busy429; stdin private JSON≤8MiB, text≤1MiB/1000 passages, reply≤16KiB,90s wall/60–61s child CPU/4GiB virtual-address cap. Parent kills/joins the owned process group on timeout/interruption before releasing admission. Credentials/proxies excluded; no raw source/private child diagnostics in logs. Token overflow422; unavailable/unexpected worker failure503; no partial admission.

## Observed tests and correction

Initial actual512-boundary fixture failed because repeating ` x`512 times produces513 total tokens after the official tokenizer's special token. The worker correctly refused it without truncation. Corrected the fixture to511 repetitions for exactly512 total tokens, verified by the real tokenizer;512 repetitions remain a513-token rejection. No tokenizer/model/corpus/threshold was modified to force a pass.

- **58 new unit/negative PASS:** independent manifest/UUID reconstruction, replay identity/drift, exact Unicode/rows/cache/review payloads, empty generation, duplicate/foreign/tampered chunks, model/runtime/source fences, complete512/513 count validation, credential-free stdin protocol, malformed/partial/wrong-identity/oversized/failing replies, busy-slot release and process-group timeout kill/join.
- **3 actual Qwen tokenizer cases PASS:** exact512 total tokens accepted,513 rejected422 without truncation, complete private Unicode batch counts with no content leakage. Approved selected config/E5 rollback and original D24/new comparison evidence hashes unchanged during inference.
- Final focused comparison/chunks/admission suite **117 PASS in19.98s,0 SKIP**. Full existing Vault-backed regression with actual PostgreSQL/CORE/Qdrant and actual Qwen/tokenizer flags: **870 PASS in114.48s,0 SKIP**, exit0. Credentials loaded by the existing wrapper and redacted; none committed/printed. No credential-based skips used as acceptance.
- Ruff correctness/import and format checks on five new Python files PASS; all module/function/class descriptions verified. Frozen preflight uv lock check PASS; protected original D24 config shortlist/corpus/runtime/evidence/project dependencies unchanged, selected Qwen approval hash unchanged, E5 rollback byte-for-byte original and MODEL_REGISTRY unchanged. Existing source/API code not modified. No D25 schema migration, ingestion collection creation or vector upsert/delete performed; full regression still runs its existing owned cleanup probes.

[Retained T01 acceptance](../docs/evidence/d25-t01-ingestion-admission.json) records exact observed results/boundaries and source hashes. Roadmap v3.21, ADR-033, ingestion lifecycle and related file design/runbook updated. Full-version source-only archive: `/tmp/local-assistant-d25-t01-complete-full-files.zip`; weights/credentials/runtime data excluded. HEAD remains a88584b; no commit/push performed.

**Status:** D24 remains historical PASS. **D25-T01 PASS for local planner/token admission; D25 IN PROGRESS, not PASS. NEXT D25-T02:** reviewed additive journal/schema, protected backup/restore verification, source-locked admission/replay, leases/generation/tombstones and real transaction/race tests. T03 embedding worker/upsert/delete/crash recovery and complete Day acceptance remain mandatory before D26. Qwen remains `selected_not_deployed`; no live indexing claim.

# 2026-10-19 — D25-T02 durable ingestion journal verification

**Purpose:** Record the implemented journal/migrations and actual verification progress before claiming acceptance.

ADR-034 preceded persistence changes. V003 added ingestion jobs/desired-active heads; V004 restricted inherited table UPDATE grants to mutable columns on only those new tables. Existing seven-table rows/owners/ACLs were preserved at rollout; protected pre-migration seven-table and post-V004 nine-table restores (including column ACLs) passed without a shared restart. Evidence is retained under `docs/evidence/d25-t02-*`; private backups remain under `data/backups/d25-t02-*`.

Journal admission binds namespace/owner/source hash/model/manifest/points/counts, resolves replay before capacity, fences superseded attempts and persists deterministic generation identity. Short transactions have5s lock and15s statement/idle limits. Claims use fresh server UUID, database time,120s renewable lease bounded by one hour, five attempts and2–30s backoff. Publication requires latest desired revision/live lease/current ready source and complete acknowledged IDs. Terminal cleanup/tombstones, paginated invalid-source discovery and source-ready/hash-filtered active reads are durable; no text/vector payload is stored.

Observed corrections: pytest basename collision fixed by naming the PostgreSQL test module separately; NULL keyset cursor explicitly casts UUID; inherited default table UPDATE required forward V004; initial full regression831 PASS/71 errors/4 failures exposed file initializer's exact0002 guard. It now accepts only reviewed0002/0003/0004 with eight startup tests, preserving unknown-schema refusal and original upload/delete/root/quota logic. Related schema fixtures follow actual migration head/source revision. New journal scope36 PASS/2.56s; related journal/file HTTP/recovery/startup scope111 PASS/16.85s,0 SKIP.

On2026-10-19 the previous transient regression process/log could not be recovered. A fresh final run was started after restoring the already initialized Vault from sealed state with existing bootstrap material; no Vault initialization, rotation or policy/configuration edit. DB schema remains0004. Final full regression and post-test audit are pending; D25-T02 is not marked PASS yet. Qwen/E5 rollback/model registry/T01 source and existing source data remain preserved. No D25 embedding worker, Qdrant upsert/delete, admission HTTP route or live index is implemented; D25 remains IN PROGRESS, D26 remains later work.

## Final D25-T02 acceptance — 2026-10-19

Fresh full regression initially stopped at collection because existing CORE was not running. Resumed the existing configured CORE profile with vision via `uv run --no-sync python scripts/start-model.py --profile core --vision`, health200, without editing configuration/model/projector or downloading weights. Vault unseal used existing material only. These environment failures were not counted as acceptance.

Final full Vault-backed run **914 PASS in120.13s,0 SKIP**, exit0, actual PostgreSQL/CORE/Qdrant and actual offline Qwen/tokenizer.44 new cases:14 journal unit,22 actual PostgreSQL and8 startup compatibility; focused journal36 PASS/2.56s, related111 PASS/16.85s. Tests cover simultaneous replay/claim/capacity, stale lease recovery, bounded retry/deadline, generation replacement/old replay, complete point acknowledgements, delete/publication race, durable tombstone discovery/cleanup acknowledgement, owner/root/composite FK isolation, actual column grants, guarded downgrade and real transaction rollback after job-write faults. Sanitized full log retained privately in `data/backups/d25-t02-final-regression.log`.

Readonly post-audit: schema0004; jobs0/heads0/files0, global quota `(0,0,0)`, restore probe databases0, Qdrant collections0; manifest UPDATE denied, state UPDATE allowed, TRUNCATE denied. Original schema/table owners/ACL fingerprint remains unchanged. No D25 vector writes/deletes or production worker deployment. Protected pre/post backup checksums and permissions verified, including actual nine-table/column-ACL restore. New artifact `docs/evidence/d25-t02-journal-acceptance.json` binds results to nine changed Python files; `d25-t02-post-audit.json` retains clean state. Ruff correctness/import/format and104 function/class descriptions PASS. Original V001/V002, file journal/FileService, dependencies, models config, selected Qwen hash, byte-exact E5 rollback, T01 source/lock hashes, registry and original D24 evidence remain unchanged. The only accepted application component change is the necessary file-startup revision guard; upload/delete/root/quota logic is preserved.

Roadmap v3.22, ADR-033/034, journal/lifecycle specifications and related file design/runbook updated. **D25-T02 PASS for local repository/schema; D25 IN PROGRESS, not PASS. NEXT D25-T03:** bounded actual Qwen embedding worker, owned Qdrant generation/upsert/delete, admission integration, source/point/count/hash verification and retry/crash/shutdown acceptance. D26 stays later work. Current Qwen is still `selected_not_deployed`. No commit/push performed; full-version source-only archive `/tmp/local-assistant-d25-t02-complete-full-files.zip` excludes credentials, weights, backups and runtime logs.

# 2026-10-19 — D25-T03-A adapter checkpoint

**Purpose:** Record observed actual encoder/vector adapter acceptance before orchestration work.

ADR-035 preceded changes. Added separately locked offline CPU Qwen encoding process with exact pinned model/pooling/prompt/fingerprint, batch4, input8MiB/text1MiB/1000 passages, reply32MiB, wall600s/CPU480–481s/8GiB virtual-address bounds. Parent validates complete finite1024-dimensional unit vectors/counts/fingerprint; one nonqueued slot, cancellation/timeout kill and join process group before release. No API credentials enter child environment/stdin/arguments; no model/dependency change to project or previous benchmark/preflight environments.

Added owned Qdrant adapter with application/installation UUID/model collection metadata, collision refusal, exact approved dense1024/Cosine/on-disk schema and tenant indexes. Deterministic batch upsert wait/strong ordering, independent full stored ID/payload/vector verification, exact six-field owner/namespace/file/hash/model/generation delete+zero-count verification. No collection-deletion method in production adapter. Minimal payload hashes source/provenance instead of copying D22 structure rows (which can contain private text); quality presence/untrusted status remain explicit and full source metadata is rehydration work for D26.

**36 new unit+2 actual tests PASS; focused38 PASS in4.16s. Final full952 PASS in117.24s,0 SKIP**, actual PostgreSQL/CORE/Qdrant/Qwen. Actual10-vector multi-batch/multi-page generation retry did not duplicate; delete preserved20 points in newer/foreign scopes before their explicit cleanup. Actual cancellation reaped child/no live process-group members. Shared Qdrant inventory fingerprint and selected configuration unchanged; owned probe removed. No production collection/point or journal publication. T03-A PASS only; continuing B source/journal/lease/recovery and C explicit admission/lifecycle before any Day PASS. Sanitized logs moved under ignored protected `data/backups/`.

# 2026-10-19 — D25-T03 and final local lifecycle acceptance

**Purpose:** Record complete adapter/worker/HTTP implementation, observed verification and the exact D25 acceptance boundary.

ADR-035 preceded adapters; ADR-036 preceded orchestration/API and records hard-parent-death supervision. T03 now implements a separately frozen offline pinned CPU Qwen encoder, strict complete1024-vector/count/fingerprint validation, owned Qdrant schema/metadata and deterministic generation upsert/independent verification/activation/delete. Vector payload is an explicit identity/digest allowlist: copying D22 structured rows would expose source text, so full provenance is rehydrated from trusted source in D26. No approved model, precision, artifact, registry role or selected configuration changed.

The source-held worker reconstructs immutable plan/counts under existing FileService integrity/read lifetime, heartbeats DB-time leases, fences latest generation/source and publishes only after complete stored-vector verification. Dedicated committed PostgreSQL advisory session excludes duplicate namespace/model workers without a long transaction; shielded control checks survive cancellation. Lost vector acknowledgement retries the same IDs, lost SQL publication acknowledgement reads durable ready state. Source deletion hides active status through the existing SQL ready/hash join. Repeated bounded terminal sweeps include previously acknowledged cleanup, repairing late writes after restart instead of treating an earlier zero count as permanent proof. Busy source429 defers without model-attempt charge/deadline extension. Shutdown joins admissions/source/model/network before closing vector/lock/file resources; exact parent PID/start/pidfd supervision kills an encoder after hard API-parent death.

Added authenticated loopback file-index admission and owner-scoped job status, explicitly off by default. Index `max_bytes=256` is a declared source-preserving policy; unchanged `/chunks` default2048 and actual512-token limit are not silently modified. Immutable content replacement uploads a new file UUID/hash, explicitly indexes it and deletes the obsolete source. Private operator credential/ownership file is validated before startup; no Vault root/bootstrap access inside API. No production credential file or collection was created. Existing selected artifact remains `selected_not_deployed`.

Related-file review: API main/lifespan only wires the new default-off router/resource with ingestion drained before file shutdown. T02 journal gains only `reject`, `terminal_candidates`, `defer`; all pre-existing methods are AST-identical to the accepted T02 ZIP. FileService/file journal/root/quota/delete contracts, V001/V002, schema0004/grants, original T01 hashes/locks, project dependencies, original D24 evidence, approved selected-file hash, byte-exact E5 rollback and unchanged MODEL_REGISTRY were checked. No Docker/config/Vault-policy or shared database schema changes in T03.

## Observed verification

- Final full existing Vault-backed regression: **979 PASS in162.02s (2:42),0 SKIP**, exit0; actual PostgreSQL/CORE/Qdrant/offline Qwen.65 new T03 cases:36 adapter unit,3 actual encoder/vector/process,14 startup/HTTP policy unit,10 actual worker integration and2 actual opt-in HTTP integration. Historical T03-A952 PASS/117.24s remains its earlier checkpoint.
- Actual10-vector multi-batch/multi-page verification/retry/delete preserves20 newer/foreign-scope points until their own explicit cleanup. Real authenticated upload/index/status/replay/replacement/delete passed. Actual worker SIGKILL after Qdrant upsert before publication recovered the same IDs under a fresh lease/process. Actual model-parent SIGKILL during initialization left no live owned encoder group. Source-delete heartbeat, shutdown, duplicate-worker, cancelled-check exclusion, reconstruction drift, overflow and acknowledged-cleanup/late-write/restart repair passed.
- Fault-only worker fixtures explicitly inject deterministic unit vectors for acknowledgements/lease/cancellation controls; they are not model-quality results. Separate live adapter/HTTP/worker cases execute actual Qwen. Intermediate fixture/correction failures were resolved before the final run, including busy-source deferral and replacing an invalid crash-test plan fixture with a valid200-chunk plan. No corpus, relevance label, model or acceptance threshold was altered to force a pass.
- Focused B/C/encoder14 PASS/48.53s preceded two final boundary tests; final startup/adapter50 PASS/0.52s. Ruff correctness/import and format checks on all15 T03 Python files PASS;178 function/class descriptions and module purposes verified. Initial project `uv run ruff` was unavailable; the cached isolated `uvx --offline ruff` ran successfully without project dependency changes.
- After the final regression, one synthetic10-point drill measured encoder3.014031s, schema/index0.303696s, upsert plus complete verification0.123681s (80.853points/s), delete/zero verification0.047804s. Apparent directory353055814 bytes includes WAL/preallocation, not allocated filesystem bytes or steady-state index storage; flat float32 vectors40960 bytes. This is not a large-corpus/long-context/concurrent-load benchmark. Owned probe removed; inventory hash unchanged.
- Final read-only post-audit: revision0004; jobs0/heads0/files0/quota(0,0,0), restore probe DBs0, Qdrant collections0, live encoders0, worker advisory locks0. Immutable manifest UPDATE denied, mutable state UPDATE allowed, TRUNCATE denied; original table owners/ACL fingerprint unchanged. Sanitized logs retained privately under ignored `data/backups/`; no credential output/archive inclusion.

[Final acceptance](../docs/evidence/d25-ingestion-acceptance.json), [post-audit](../docs/evidence/d25-post-audit.json) and [small index drill](../docs/evidence/d25-qwen-index-probe.json) retain exact results. Roadmap v3.23, ADR-035/036, lifecycle/journal, embedding-selection/backlog and related file design/runbook updated; [operating guide](../docs/INCREMENTAL_INGESTION.md) covers enablement/drain/rollback. Extended quality/load/long-input, populated SQL/blob/vector/ownership disaster recovery and tombstone compaction are separately evaluated backlog, not claimed PASS.

**Status:** **D25 PASS for local opt-in lifecycle; D26 ACL-filtered retrieval NEXT.** Production rollout/search/reranking remain open. Preserve approved Qwen and exact E5 rollback; future agreed-model changes require benchmark/resource/migration/rollback review and owner approval. HEAD remains a88584b; no commit/push performed. Full-version source-only archive `/tmp/local-assistant-d25-complete-full-files.zip` contains complete pending changed files; unchanged user registry, weights, credentials, backups and runtime logs excluded.

## Commit handoff — 2026-10-19

**Purpose:** Record the owner's explicit request to commit the verified work through D25.

Commit scope includes the owner-approved Qwen comparison/selection and exact E5 rollback, original unchanged MODEL_REGISTRY needed by roadmap links, D25 T01–T03 implementation/tests/migrations, ADR-031 follow-up and ADR-032–036, retained evidence, roadmap and this dev log. The complete67-file review archive matched current bytes before this documentation entry; the registry hash also matches the preserved owner file. Functional verification remains979 PASS/0 SKIP; no code changed after that run. Private credentials, model weights, backups and runtime logs are excluded. D25 PASS local opt-in; D26 NEXT. Local commit only; no push or production enablement. Earlier “no commit” entries describe their historical checkpoints.

# 2026-10-19 — D26 private source-revalidated retrieval acceptance

**Purpose:** Record implemented ACL-filtered search, actual verification, preserved baseline and the next milestone.

ADR-037 preceded implementation. D26 adds a read-only owned dense Qdrant query adapter and strict authenticated loopback `POST /api/v1/retrieval/search`: exact query text, top_k1–10 and optional1–16 unique file UUIDs only. Server derives conjunctive owner/namespace/model/private/untrusted/active predicates; caller ACL/filter/model/generation/vector fields are forbidden. Bounded20–50 candidates, no returned vectors, malformed/foreign/duplicate/nonfinite input/reply refusal. Optional file IDs narrow scope without granting access. Results may underfill within that explicit budget; no corpus-exhaustion or quality threshold claim.

Query uses the unchanged approved profile instruction plus original bytes through the existing empty-prefix passage worker. Actual full instructed/special token counts must match preflight and encoding; overflow422 without truncation. The exact ingestion encoder instance/admission is shared, preventing a second model process during indexing. No model, runtime, precision, weight, lockfile or project dependency changes/downloads. Approved Qwen CPU/1024 and exact E5 rollback remain intact.

Candidates are hints only: owner/root/source-ready/hash-filtered SQL active job, exact generation/UUID membership, deterministic source projection/manifest and complete allowlisted payload must agree. Text/provenance/quality comes only from verified source reconstruction. Rehydrate files sequentially under existing chunk admission, retain separate verified readers through response, and track the complete operation in FileService. Final integrity I/O is followed by one SQL snapshot checking all retained generations before headers. Source deletion/publication during preparation fences delivery; changes after the final authorization point are ordered after authorization, with no distributed SQL/Qdrant/HTTP atomicity claim. Similarity is not confidence; retrieved content stays untrusted and is not automatically added to chat context.

One nonqueued search admission is retained through delivery, with response bytes≤1MiB and query≤4096 UTF-8 bytes. Startup remains explicitly off by default (`ASSISTANT_RETRIEVAL_ENABLED=0`), requires enabled approved ingestion/files and an existing owned collection, and performs no retrieval vector mutations/new credential reads. Lifespan drains retrieval before ingestion/files/pool. Existing FileService, file/ingestion repositories, workers, model selection, schema0004/grants, Docker and Vault remain unchanged; among established code only API router and resource registration/order changed.

## Observed verification and corrections

- **Final full1030 PASS in216.32s (3:36),0 SKIP**, exit0; actual existing PostgreSQL/CORE/Qdrant and offline Qwen via the existing Vault-backed wrapper.51 new cases:40 unit/policy/protocol/delivery and11 actual SQL/Qdrant/service/HTTP. Final focused51 PASS in54.37s. No credential skips accepted.
- Actual HTTP uses Qwen query/document encoding, owned vector storage, private source upload/index/retrieval and SQL publication: two principals, exact source/provenance, optional foreign file narrowing, immutable new UUID/hash replacement, old-source delete hiding and query-token overflow. No reranker/quality improvement is inferred from these tests.
- Actual service faults cover wrong owner/root/file scope, deleted and superseded generations despite stale points, forged content/provenance payload, reconstruction drift, retained-reader delete fencing, busy response lifetime, query cancellation and joined shutdown. A legitimate new generation published during final integrity I/O is caught by the final single SQL snapshot. Fault cases inject explicit unit vectors against real SQL/Qdrant; separate HTTP tests run actual Qwen.
- Earlier unit fixture failures (4) omitted ASGI `type=http`. The first integration run7 PASS/3 failures exposed two assertions referring to a nonexistent FileService tracking attribute and strict UUID element parsing rejecting JSON narrowing; corrected to existing `active` inventory and explicit UUID parsing without relaxing top-k/extra-field validation. All fixes preceded final focused/full runs; no labels, chunks, model, threshold or source contract changed to force success.
- Ruff correctness/import/format PASS on all11 changed Python files;68 function/class descriptions plus module purposes verified. Protected D25 acceptance source hashes remain unchanged except the necessary main/lifespan wiring. Selected Qwen/configs/model profile/registry/E5 rollback, dependencies, runtime locks, all migrations/schema and existing source/repository/worker code were checked unchanged against e7fc697. No functional code changed after the final full run.
- Readonly post-audit: schema0004; jobs0/heads0/files0/quota(0,0,0), restore probe DBs0, Qdrant collections0, live encoders0 and worker advisory locks0. Immutable manifest UPDATE denied/state UPDATE allowed/TRUNCATE denied; old owners/ACL fingerprint unchanged. Only owned removable acceptance probes were used; no production collection/configuration enabled. Protected redacted logs are ignored under `data/backups/d26-*.log`; credentials/weights/backups/logs excluded from commit/archive.

[Acceptance](../docs/evidence/d26-retrieval-acceptance.json), [post-audit](../docs/evidence/d26-post-audit.json), [guide](../docs/RETRIEVAL.md), ADR-037, roadmap v3.24, embedding/model backlog and related file design/runbook updated. Full-version changed-file archive: `/tmp/local-assistant-d26-complete-full-files.zip`. This verified milestone is prepared for a local commit including this dev log; no push or production enablement.

**Status:** **D26 PASS for local opt-in retrieval; D27-T01 baseline/reranker evaluation planning NEXT.** Freeze an independent corpus/labels/thresholds and no-reranker baseline before candidate execution. Preserve original Qwen3-Reranker-0.6B nomination; no reranker has been downloaded/evaluated/deployed here. Future agreed-model changes still require benchmark, performance/resources, compatibility, migration/rollback and owner approval. Production multiworker/load/DR, independent quality/long-input and safe tombstone compaction remain open.

# 2026-10-19 — D27-T01 frozen baseline verification in progress

**Purpose:** Record the next milestone's actual scope and focused results before final regression acceptance.

ADR-038 precedes evaluation code. Froze a new agent-authored synthetic24-document/36-query corpus (12 each vi/en/cross-language) and exact binary labels/near-topic negatives before inference. Corpus SHA256 `0bc96e6c5bebacb3ffbd3eedd4fed466c730f2f540eef556aeb4654949bd7ee8`; plan SHA256 `4f39578e917b8a07175ea86946e21e76f577a0d7c6ffd5397ad1a6aaf6423048`. This is separate diagnostic data, not human-blinded/production-held-out evidence. New scorer independently verifies duplicate/unknown/missing/nonfinite/unsorted inputs, multiple-relevance binary nDCG/recall and deterministic descriptive bootstrap; no post-score relabeling or threshold changes.

Harness encodes60 real complete CPU inputs once through unchanged pinned Qwen worker (24 passages+36 instructed queries, existing batches4), then explicitly replays those actual vectors in isolated source/SQL/Qdrant/D26 retrieval. It preserves full token counts/fingerprint/source hashes, one256-byte chunk/source, actual source admission/publication, exact reconstruction/final checks and two complete query rounds. A foreign owner has an identical-content source, testing ACL exclusion under equal semantic content. Cached query timing excludes per-request tokenizer/model startup/HTTP; batch/padding numeric differences from singleton production queries are disclosed. Child RAM/VRAM not instrumented and remain null. Application/model/schema/dependencies and original D24–D26 evidence unchanged.

Focused21 unit+1 actual integration **22 PASS/89.34s**. Initial frozen baseline R@3/R@5=.972222, R@10=1, MRR@10=.949074, nDCG@10=.961613; both replay orders stable and identical-text foreign source excluded. Retain misses: query-q2 rank6, owner-q1 rank2, vision-q1 rank2; no corpus/label/threshold repair. Proposed diagnostic warning gates met but do not authorize model adoption. Replay cached p95≈113ms is not API/model p95; actual60-input encoder wall≈6.698s and tokenizer≈2.519s in this focused run.

Read only official public reranker metadata/config: original Qwen3-Reranker-0.6B revision e61197ed45024b0ed8a2d74b80b4d909f1255473, license and artifact LFS/Git identities retained. Card advertises32K while config declares40960 positions; proposed complete-pair budget512 tokens has no long-input claim. No reranker weights/tokenizer assets downloaded, executed, selected or routed. T02 candidate resources/format/quality/fixed-top10/rollback proposal is documented for separate execution scope; runtime/provisioning/adoption remain open.

Full existing Vault-backed regression is running; **D27-T01 acceptance pending full result, D27 IN PROGRESS, D28 not started**. No commit of this milestone yet; final status/evidence will follow actual verification.

## Final D27-T01 acceptance — 2026-10-19

**Purpose:** Supersede the pending checkpoint with actual regression/audit results, preserving incomplete D27 gates.

Final complete existing Vault-backed regression **1052 PASS in306.02s (5:06),0 SKIP**, exit0.22 new cases (21 unit/oracle/freeze/replay protocol,1 actual CPU/source/SQL/Qdrant baseline); focused22 PASS/89.34s. Both focused/full measured the same quality: R@3/R@5=.972222, R@10=1, MRR@10=.949074, nDCG@10=.961613. Cross-language R@3=.916667/MRR=.847222/nDCG=.884839; vi/en each1 on this authored diagnostic set. Retain query-q2 rank6, owner-q1 rank2 and vision-q1 rank2. Two rounds stable; identical-content foreign source excluded. No corpus/labels/threshold changes after first inference.

Final actual60-input tokenizer wall2.583498s and encoder batch wall6.695255s; cached-query retrieval p50110.445787ms/p95116.019685ms over72 observations. Timing excludes per-request model/tokenizer startup and HTTP/serialization; batch4 query vectors need not equal singleton request numerics. Child RAM/VRAM remain null, not copied from old benchmarks or inferred from parent RSS. Descriptive seeded query-bootstrap intervals acknowledge36 correlated queries sharing12 authored intents; not human/production-independent confidence.

Full evidence retains both query replay candidate orders/scores, immutable source/point/hash bindings, complete actual token counts and all misses. Independent post-run audit matched every source and candidate hash to frozen corpus bytes. Post-audit: schema0004; jobs/heads/files/quota0, restore probe DBs0, Qdrant collections0, encoder processes0, worker advisory locks0; immutable-column UPDATE denied/state allowed/TRUNCATE denied and original owners/ACL fingerprint unchanged. Only owned removable probes and synthetic source principals were used. No shared service restart, model provisioning, application/source/repository change or production flag/configuration enablement.

All three new Python files pass Ruff correctness/import/format,22 function/class descriptions and module purposes verified; D26 acceptance source hashes and selected Qwen/model registry/E5 rollback, dependencies/runtime locks/migrations/configs unchanged. Evaluation-only replay records contain actual CPU vectors, with no synthetic fallback; production D25/D26 code untouched. No functional code changed after the final full run. The new raw replay retention assertion was included in that full run; the earlier focused run predates that report-detail addition. Private redacted logs and raw operator artifacts stay ignored under data/backups; committed evidence contains public synthetic data and metadata only.

Roadmap v3.25, ADR-038, D27 evaluation/candidate execution proposal, model backlog, retrieval guide, embedding-selection note and retained baseline/acceptance/post-audit updated. Full-version source-only archive: `/tmp/local-assistant-d27-t01-complete-full-files.zip`. This milestone is prepared for a local commit with this dev log; no push. Earlier pending/no-commit statements describe historical checkpoints.

**Status:** **D27-T01 PASS for local frozen diagnostic measurement; D27 IN PROGRESS, T02 original Qwen3-Reranker-0.6B offline comparison NEXT, D28 not started.** Candidate weights/tokenizer not provisioned, inference/scores/RAM/VRAM not measured, selection/routing not changed. Keep the exact frozen corpus/candidate/labels for paired comparison; independent human judgments, full paired quality/latency/resources and owner-reviewed adoption/migration/rollback remain required. No benchmark score alone authorizes model changes.

# 2026-10-19 — D27-T02 original-candidate comparison in progress

**Purpose:** Record authorized evaluation-only provisioning/execution before any candidate result or adoption claim.

The owner's continuation followed the concrete T02 plan. ADR-039 records this interpretation: execute the original Qwen3-Reranker-0.6B comparison in isolation, with no selection/deployment/model replacement. Pinned official revision e61197ed45024b0ed8a2d74b80b4d909f1255473; four required artifacts verified by exact size/SHA256 against T01 Git/LFS metadata, stored only in a new ignored cache ID. A new evaluation profile and separately frozen CPU uv script environment reuse reviewed package pins; project/embedding locks/configuration remain unchanged. Actual tokenizer no/yes IDs2152/9693 were verified and pinned before scoring. Execution manifest binds runtime/worker/comparison/lock/profile/corpus/plan/baseline hashes; source drift fails before launch. No original corpus/labels/candidate list/threshold change.

New evaluation runtime uses official complete pair/chat formatting, no embedding pooling, CPU BF16 SDPA/batch1/two threads/no KV cache, final-position finite float32 no/yes softmax. Full prefix/pair/suffix counts<=512 with no truncation. Three repetitions score the same36-query ten-candidate sets; source hashes/point bindings are verified before inference and relevance labels are not sent to the model. Raw class logits, probabilities, token counts, query wall times and all ranks/gates are retained when complete. Loaded-model timing is separate from cold artifact/model load and D26 cached retrieval latency; no singleton HTTP SLO claim.

Resources are supervised:4GiB actual RSS watchdog,8GiB virtual-address ceiling (distinct from RAM),60s per-query hard timer,600s parent wall/480–481s child CPU; CPU-only runtime/device verified. Exact parent PID/start/pidfd supervision and shielded launch/kill/join preserve cleanup across cancel/timeout/death; one nonqueued evaluation admission, credential/proxy-free environment and bounded stdin/reply. No application source, API, DB/Vault/Docker/service/collection mutation for candidate scoring. Existing T01 baseline/evidence remains immutable.

35 unit/protocol tests PASS/0.35s. Initial fake tokenizer fixture incorrectly requested one total token despite its declared22 prefix/suffix tokens; corrected fixture to23 before actual scoring, with no token-limit/code-policy change. Actual comparison and cancel/timeout/parent-death/watchdog/tokenizer tests are running. **T02 acceptance and quality/resource outcome pending; D27 remains IN PROGRESS, D28 not started.** Any failed gate will be retained; model adoption still requires independent judgments, full review and owner decision.

## T02 initial failure and execution v2 amendment

**Purpose:** Preserve the unsuccessful measurement and document an equivalent-computation correction before accepting results.

First focused run **41 PASS/1 FAIL in244.05s**; actual comparison did not return an accepted reply. Last observed candidate CPU413s/RSS1654616KiB; failure occurred near the frozen480s CPU budget, but exact exit code was not logged, so CPU-limit cause remains inferred. No accepted candidate quality metric exists from that attempt. Initial log/source archive and manifest v1 hashes are retained in d27-t02-initial-failure.json and protected data/backups; do not relabel the failure as a benchmark pass.

Reviewed installed pinned Transformers4.57.6 Qwen3 forward: `logits_to_keep=1` applies the vocabulary head only at the required final hidden position. Execution v2 avoids unused earlier-position vocabulary heads; same full input, model/weights/dtype/attention/no-cache semantics and scoring. Before scoring rounds it must prove exact actual no/yes logits against the original full-head computation on the first frozen pair, and records that parity/changed contract. Numeric process exit/completed-round diagnostics added. Corpus/labels/prompt/candidate list, token/RSS/query/CPU/wall budgets and quality thresholds are unchanged. Manifest v2 refrozen before candidate execution.36 unit/protocol tests PASS/0.35s, including parity-tamper refusal; actual v2 evaluation is in progress. D27/T02 not yet accepted, no adoption/production changes.

## T02 batch1 CPU failure confirmed; distinct batch4 experiment

**Purpose:** Preserve failed runtime contracts and assess a separately declared evaluation variant.

V2 focused42 PASS/1 FAIL in242.76s; safe diagnostics logged launcher exit152 (128+SIGXCPU24) and two completed rounds. Original batch1/480s CPU contract is FAILED/INCOMPLETE; no complete candidate quality results accepted. Manifest v2/source/log archive hashes retained. No quality/resource threshold is raised to mark batch1 PASS.

ADR-040 precedes a separate batch4 CPU BF16 profile using identical cached weights/tokenizer, full frozen inputs/prompt/labels/candidates and unchanged budgets/gates. Ten candidates process4+4+2 with left padding/masks; exact token counts/source alignment and finite class logits remain required. Padding/matmul shape can change numeric results versus singleton; this is explicitly a distinct runtime, not a claim of bit-identical batch1 scores. New independent golden-array test verifies token order/masks/row outputs;37 unit cases PASS/0.34s. Manifest v3 frozen before candidate scoring. Actual three-round v3 measurement is running; adoption remains unauthorized and D27 open.

## T02 batch4 focused comparison completed

**Purpose:** Record actual successful runtime-variant measurement while full regression is still pending.

Focused **44 PASS in234.51s**,0 SKIP:37 unit/protocol/padding cases and7 actual comparison/tokenizer/process/watchdog cases. Batch4 completed all3 real repetitions; rankings stable. R@3/R@5/R@10/MRR@10/nDCG@10 all1.0 on the unchanged36 authored judgments; baseline .972222/.972222/1/.949074/.961613. Delta R@3+.027778, MRR+.050926, nDCG+.038387; each group nonregression and all frozen quality/resource gates met. Real singleton reference/final-head no/yes logits exactly[12.375,21.25]. No labels/candidates/prompt/threshold changes; batch1 failures remain retained, not promoted to PASS.

Measured peak candidate process RSS1594.512MiB RAM, CPU-only GPU allocation0, cold artifact/model load2.276442s, loaded-model ten-pair query p50≈2120.184ms/p95≈2232.294ms/max≈2298.982ms (108 samples). These timings exclude embedding/retrieval/HTTP and model cold load; RAM includes parity probe and scoring. They are not host GPU/total application memory or an end-to-end API SLO. No human-independent/general quality claim or model adoption.

A full existing Vault-backed regression is running. T02 is not formally accepted until full result/post-audit; D27 IN PROGRESS, T03 decision/human review remains later, D28 not started. No application/selection/configuration/schema/dependency/service mutation.

## Final D27-T02 batch4 measurement acceptance — 2026-10-19

**Purpose:** Record actual complete comparison/regression, retain failed runtimes and define the remaining review boundary.

Final full existing Vault-backed regression **1096 PASS in540.75s (9:00),0 SKIP**, exit0, actual PostgreSQL/CORE/Qdrant/offline model gates.44 new tests:37 unit/protocol/manifest/golden-padding and7 actual comparison/tokenizer/process/watchdog cases. Final focused44 PASS/234.51s. Batch4 performs3 actual rounds/108 ten-candidate queries/1080 measured pairs; ranks stable, full/focused quality identical. R@3/R@5/R@10/MRR@10/nDCG@10 all1.0 on unchanged36 authored judgments; baseline .972222/.972222/1/.949074/.961613. Deltas R@3+.027778, MRR+.050926, nDCG+.038387; all frozen diagnostic group/resource gates met. Three old rank6/rank2 misses become rank1. Descriptive paired nDCG-gain95% interval[0,.094657] includes0; correlated small agent-authored data is not independent human/production quality.

Final peak candidate process RSS **1596.055MiB RAM**, GPU allocation0 by verified CPU-only Torch/parameter devices; fresh artifact/model-session initialization2.300225s with filesystem cache uncontrolled. Warm loaded-model ten-pair query p50≈2120.524ms/p95≈2238.943ms/max≈2292.312ms (108 samples), excludes initialization/embedding/retrieval/HTTP. Peak RSS includes load/reference-parity/scoring, not disk bytes or cumulative parent/child RAM; co-resident/persistent-service memory, real singleton end-to-end and sustained CORE contention remain unmeasured.480/481s CPU hard cap enforced; total CPU time is not separately instrumented. No fabricated end-to-end SLO or calibrated confidence.

Actual singleton full-head/final-head no/yes logits exactly[12.375,21.25]. Batch4 padding is separately disclosed and not claimed numerically identical to batch1. Actual full512/513 token boundaries, source/candidate/hash completeness, wrong-identity/nonfinite/logit consistency, credential-free stdin, launch-gap cancellation, real timeout/cancel/parent SIGKILL and real OS RSS/query watchdog kills passed. Watchdog fault tests use tiny budgets/fake blocked computations, not a4GiB allocation or a model-quality sample. Relevance labels never enter model input. Frozen corpus/plan/prompt/top10/labels and every quality/resource threshold remained unchanged.

Original batch1 v1/v2 remain **FAILED/INCOMPLETE**, not qualified by batch4 success: v1 unaccepted worker failure41 PASS/1 FAIL/244.05s near CPU cap (cause inferred), v2 exit152/SIGXCPU after2/3 rounds42 PASS/1 FAIL/242.76s (confirmed). Initial logs/source archive hashes/manifests retained; no complete quality metrics invented for either. Exact last-head optimization and a separately declared batch4 runtime are documented in ADR-039/040 before their respective executions; budgets were not raised. All three attempts are visible in comparison/review evidence.

Readonly post-audit: revision0004; jobs/heads/files/quota0, restore probe DBs0, Qdrant collections0, live encoder/reranker workers0 and worker advisory locks0. Immutable-column UPDATE denied/state allowed/TRUNCATE denied; old owners/ACL fingerprint unchanged. Candidate scoring itself has no DB/Vault/source/vector/service writes; full regression uses only its normal owned removable probes. Existing D25/D26/T01 source hashes, registry, approved selected embedding/profile/precision, exact E5 rollback, project/runtime locks and migrations remain unchanged. Five new Python files/68 function-class descriptions pass Ruff/import/format; frozen isolated worker lock and manifest checks pass. No functional code changed after the final full run.

[Complete comparison](../docs/evidence/d27-t02-reranker-comparison.json), [acceptance](../docs/evidence/d27-t02-acceptance.json), [post-audit](../docs/evidence/d27-t02-post-audit.json), provisioning and all execution/failure artifacts retained. Roadmap v3.26, ADR-039/040, baseline/evaluation/embedding/retrieval/backlog documents updated; [T03 review proposal](../docs/D27_RERANKER_ADOPTION_REVIEW.md) includes concrete benefit/cost, independent quality gates, optional integration scope and nondestructive disable/drain rollback. No adoption approval, default routing, application/API/schema/Docker/Vault change or production collection enablement. New weights/cache and raw private logs remain ignored, excluded from commit/source archive.

**Status:** **D27-T02 PASS for local batch4 measurement; D27 IN PROGRESS, T03 independent quality/resource/adoption review NEXT, D28 not started.** Keep original model lineup and approved embedding. No diagnostic score alone authorizes model/routing changes. This verified milestone is prepared for a local commit including dev log; no push. Full-version source-only archive `/tmp/local-assistant-d27-t02-complete-full-files.zip`; earlier pending/no-commit notes are historical checkpoints.


# 2026-10-19 — D27-T03 review preparation and bounded request-cost probe

**Purpose:** Continue authorized work autonomously while keeping missing human judgments, model decisions and real HTTP/concurrent-service gates explicit.

New score-blind review preparation is frozen before any new challenge inference: eight authored unlabeled queries/eight source snippets/64 complete pending pairs, numeric/month/release-generation, unresolved identifiers/OCR, stale formula-cache, rollback and potentially absent-answer coverage. Agent-authored input is not independently authored/human-reviewed/production-held-out. No human labels supplied. Deterministic content-hash ordering hides model ranking/order and old role/target labels. Original D27 corpus/plan/top10/labels/thresholds/baseline/T02 comparison/failed experiments remain unchanged. The structural validator binds exact corpus/packet/review identities, all query/source pairs, strict booleans, reasons, reviewer metadata/timezone timestamp and explicit attestation; rejects duplicate keys/nonfinite values/partial or foreign data and never overwrites existing artifacts. Private0600 outputs and count/hash-only logs preserve auditability. Structural acceptance cannot authenticate a human, certify independence or approve a model. All-negative labels are supported without inventing a relevant target; a later paired plan needs explicit absent-answer metrics because the old scorer intentionally rejects empty relevance. Test-only synthetic labels are not committed as human judgments.

A separate resource-only worker uses the first original frozen query and ten exact source/hash-bound candidates, unchanged pinned CPU BF16 batch4 weights/prompt/runtime (4+4+2), plus meaningless repeated-token stress input. It never reads the new challenge. Own frozen manifest/uv script lock, secret-free offline environment, exact parent supervision, joined cancel/launch-gap/timeout, actual RSS4GiB watchdog,8GiB virtual ceiling,120/121s CPU,150s child wall and180s parent wall; these are separate probe limits and do not alter any T02 budget/profile. Actual full512-token forward and513 rejection are measured; resource stress is not long-document relevance validation.

Initial probe focused **60 PASS/1 FAIL in0.91s** before any accepted measurement. Importing the comparison helper pulled application dependencies into the model-only environment; a separate diagnostic confirmed `ModuleNotFoundError: No module named 'starlette'`. Failure/source/log/original freeze hashes retained. Revision2 replaces only worker-side manifest/request loading with standard-library reads and exact existing hashes. No input/model/scoring/limit changes. Pre-execution revision2 frozen. Final focused **61 PASS in15.65s,0 SKIP**:60 protocol/control cases including real owned-process cancellation/launch-gap/timeout and one actual model-resource probe. Current source purposes/docstrings (48 functions/classes) and Ruff correctness/import/format pass.

Focused actual measurements: worker-start-to-first-query6.987930s, model-init4.721388s, warm ten-pair queries2.149916/2.197008/2.187672s; complete512-token forward1.117899s,513 rejected. Peak worker RSS1565.941MiB RAM, worker user+system CPU24.614314s, verified CPU-only allocation0. Parent total15.103750s includes all four queries and boundary probes, not a first-query SLO. Child first-request time starts before model imports, excludes interpreter/uv launch/IPC, and includes artifact verification/import/model load/first score. Cache state is uncontrolled. No p95/SLO derived from three warm samples; no HTTP/embedding/source retrieval, sustained concurrent CORE or persistent co-residency measurement claim.

Full existing Vault-backed regression is running. No T03/day PASS until the corresponding gates are actually met. Review protocol, roadmap v3.27, backlog and adoption-review follow-up updated. Human review requested asynchronously while independent verification continues. No architecture/application/source/API/model selection/profile/DB/schema/ACL/Vault/Docker/production service change; existing ADR-039/040 runtime reused, no new application ADR required for evaluation-only tooling. New dependencies/weights are not downloaded; isolated probe lock reuses existing cached pins. D27 remains IN PROGRESS, D28 NOT STARTED.

Owner response during verification: **the owner will perform the human relevance review**. This identifies the reviewer only; no labels, attestation or adoption approval have been supplied. Readable score-free form and a private0600 pending working copy at `data/backups/d27-t03-human-review.json` are prepared; committed pending evidence is preserved. Independent work/regression continues.


## Verified D27-T03 preparation/resource checkpoint — 2026-10-19

**Purpose:** Record completed regression and post-audit without falsely closing independent review or D27.

Full existing Vault-backed regression **1157 PASS in553.32s (9:13),0 SKIP, exit0**; original1096 plus61 new cases. Final focused61 PASS/15.65s. No code changed after the final full run. Actual final isolated worker first-request4.451425s, model-init2.236234s; warm ten-pair requests2.234218/2.211714/2.220581s; full512 forward1.113713s and513 rejected. Peak1549.250MiB process RAM,22.222974s user+system CPU, verified CPU-only GPU allocation0. Parent12.639595s includes four requests and boundary probes. Focused/full raw results both retained; cache-dependent initialization differs, no p95/HTTP/load SLO inferred. Original T02 comparisons/failures and every old profile/input/threshold remain immutable. Initial resource import failure remains retained, not rewritten as a successful attempt.

Readonly post-audit: revision0004, jobs/heads/files/quota0, owned restore DBs0, Qdrant collections0, encoder/reranker/resource-probe workers0, advisory worker locks0; original owners/ACL fingerprint unchanged, immutable-column UPDATE denied/state allowed/TRUNCATE denied. Latest accepted source hashes38 match; historical D25 main/lifecycle hashes were legitimately superseded in D26, so old evidence is preserved rather than compared as if it described the newer checkpoint. All preexisting application files are byte-identical to base2a663e6; original registry, selected/rollback model profiles, models.yaml, dependencies/locks and old frozen evidence unchanged.

Review tooling/strict unlabeled challenge, readable review form, owner assignment, resource-only script/lock, raw final/focused results, freezes/failure, preparation acceptance and post-audit added. Four new Python files/48 function-class descriptions pass module-purpose, Ruff correctness/import/format checks. Roadmap v3.27, adoption review, model backlog and review protocol updated. No new application architecture/model/routing decision made; reuse ADR-039/040, later integration still requires its own ADR and owner decision. Full-version source-only archive `/tmp/local-assistant-d27-t03-preparation-full-files.zip` will contain every changed file and hashes, excluding keys/weights/private logs/review response/backups. Local commit includes this dev log; no push.

**Status:** **D27-T03 preparation and isolated request-resource probe VERIFIED; D27 IN PROGRESS; D28 NOT STARTED.** Owner volunteered to review, but actual independent labels/attestation remain0/64. Separate paired plan (including absent answers), actual HTTP/source/delivery and concurrent CORE resources plus explicit owner adoption remain open. No task/day marked PASS solely from code, automated tests or reviewer assignment.


# 2026-10-19 — D27-T03 isolated HTTP/core trial and owner-delegated AI relevance

**Purpose:** Continue independently rather than stopping at a manual-label request, preserve actual review provenance and finish the remaining local evaluation with measured evidence.

ADR-041 precedes the test-only composition: unchanged D26 route/source/SQL/Qdrant/current owner/root/hash/generation fences, ten rehydrated candidates, actual original pinned Qwen reranker CPU BF16 batch4, exact chunk-text hashes, complete finite source-bound scores, shared actual ingestion encoder admission, post-model/final-response checks and held readers through delivery. Isolated supervised worker has120/121s CPU,4GiB actual RSS,8GiB virtual address,80s child/90s parent wall and512 complete-token cap, secret-free offline env and joined launch-gap/cancel/shutdown. No new production flag, application source, routing/configuration/schema/ACL or embedding change.41 new protocol/control cases plus5 live cases focused46 PASS/213.98s. Live cases include actual authenticated full ASGI path, two real source delete/supersede-delay fences and actual model-worker cancel/shutdown. Existing only owned acceptance fixtures reused and cleaned.

Focused measured dense ASGI mean5.615784s (n3), reranker idle mean11.592842s (n3), concurrent CORE mean10.935013s (n6); descriptive p95 values5.624668/13.094273/10.997904s.101 real bounded CORE requests overlap, with each of six retrieval requests overlapping traffic. CORE before n3 mean.191839s vs concurrent n101 mean.155182s is not a causal speedup claim: tiny baseline/reused short prompt/cache state/order uncontrolled. ASGI response completion includes real approved query/SQL/Qdrant/source/ranking/final-fence/serialization, not socket/network or production server scheduling. Fresh model children and all per-request RAM/CPU/logits/counts retained; persistent co-residency/load certification not measured.

Additional paired scorer/driver preparation focused31 PASS/.93s:30 unit/control cases and one pending-review gate. Explicit absent support metrics remain null; answerable macro means never count absent cases perfect. Complete point/file/source hash/generation pairing, three actual repetitions and exact input/scoring freezes prepared. That gate returned PENDING_HUMAN_REVIEW with no inference; its test PASS does not establish human relevance or benchmark success. Combined1234-case regression is running on this implementation checkpoint.

The owner then explicitly said they are unavailable and delegated this review and similar tasks to the assistant autonomously from now on. ADR-042 records the amended local criterion. No further mandatory manual-label task is assigned; never fabricate a human attestation or call same-agent review independent. Historical human packet/template/scorer/assignment preserved. Separate AI review v1 finds query04 can be answered negatively by doc-d (quarter budget not approved), so the frozen original minimum-one-absent coverage FAILS before model inference (8 answerable/0 absent). Do not force an irrelevant label to pass coverage. Separate v2 changes only q04 to physical backup disk serial for G-17, which no source provides; source bytes/other seven queries and thresholds unchanged.7 answerable/1 absent AI judgments, plan and code/test hashes frozen before any new-challenge model inference.15 AI-provenance/metric/source-lifecycle unit cases PASS/.18s. Actual v2 three-round execution waits for the current shared-service regression to finish; no parallel DB tests, no invented result.

Current recommendation is retain approved dense routing and defer production reranker adoption given observed fresh-worker cost and limited quality scope; final local evaluation decision still needs actual v2 results. Original registry nomination remains. No original model replacement/selection, default routing or deployment is authorized by AI review. Completing a measured evaluation can conclude to defer adoption; it does not promote the candidate or erase failed quality/resource gates. D27 stays IN PROGRESS; D28 NOT STARTED until actual amended evaluation/decision acceptance.

HTTP/scoring preparation full checkpoint completed: **1234 PASS/787.47s,0 SKIP, exit0**. Readonly post-audit schema0004, rows/quota/probe DBs/collections/live model workers/advisory locks0; original owners/ACL unchanged. Full raw ASGI/Core evidence and acceptance retained. This run collected before new15-unit/one-actual AI-v2 test and one TCP test were added; do not call it a1251-test full invocation. Actual AI-v2 focused trial is running separately after the shared-service audit; no parallel DB/CORE acceptance runs. Temporary TCP trial is frozen and waits for that run.


## Final D27 local evaluation / retain-dense acceptance — 2026-10-19

**Purpose:** Close the actually tested amended local evaluation and continue D28 without claiming human quality or adopting a model.

Actual AI v2 focused **16 PASS/448.97s,0 SKIP**:15 protocol/provenance/source-pair cases plus one three-real-round source/HTTP/model trial.7 answerable/1 absent; dense and candidate R@3/R@5/R@10/MRR/nDCG all1 across all three stable rounds; new gain0, descriptive nDCG-delta interval[0,0]. Absent metrics stay null, no abstention calibration/general quality inferred. Same-agent authorship/review explicitly owner-delegated, not human-independent. Original v1 negative-answer/absent coverage FAIL, T02 positive36-query evidence, batch1 CPU failures and every old input/profile/threshold remain intact. New candidate worker peak1542.746MiB RAM, CPU-only allocation0; no CORE/host VRAM or persistent whole-service memory claim.

Actual ephemeral Uvicorn/TCP **1 PASS/40.93s,0 SKIP**: private auth/Origin/foreign-owner fences, same exact source/point IDs, dense5.606043s→two-candidate rerank8.896878s→dense-after-disable5.634908s, temporary server joined. Same original fixture event loop/lifespan resources; genuine loopback TCP, not separate-process/multiworker/load certification. Existing ASGI/CORE101-overlap drill passed earlier, all raw timing/logit/token/source identities retained.

Verification is **1234-test full regression PASS/787.47s**, plus the **16 new AI-focused** and **1 TCP** cases above, all0 SKIP/exit0:1251 unique tests across frozen checkpoints. **No single1251-test full invocation**; earlier46/31 focused cases are subsets of1234, not counted twice. Full1234 ran before the additional17 test cases were collected, all preexisting application/helper/profile bytes remained unchanged and all new isolated cases ran afterward. Do not invent a combined wall time/full-run result.13 new Python modules/105 function-class descriptions and frozen worker lock pass purpose/Ruff correctness/import/format checks.

Final read-only audit: schema0004; jobs/heads/files/quota0, owned restore DBs0, Qdrant collections0, live encoder/reranker/request-trial workers0 and advisory locks0; old owners/ACL unchanged, immutable-column UPDATE denied/state allowed/TRUNCATE denied. No user source/collection adoption, production config/routing, schema/grant/Vault/Docker or original model change. Existing registry/model roles, approved Qwen selection, exact a88584b E5 rollback, project locks/dependencies and protected evidence remain byte-identical. All live writes were owned removable acceptance fixtures.

**Decision:** retain approved dense path, defer production reranker adoption. New limited diagnostic has no additional gain and observed fresh-child request cost increases; general quality/persistent optimization remains unproven. Original Qwen reranker nomination preserved; no candidate adopted, selected/deployed or silently substituted. Keeping agreed state is an autonomous evaluation decision under ADR-042, not an owner approval for future model/routing replacement. [Final acceptance](../docs/evidence/d27-local-evaluation-acceptance.json), [decision](../docs/D27_RERANKER_EVALUATION_DECISION.md), raw ASGI/AI/TCP evidence and final post-audit retained; roadmap v3.29 and related guides/backlog updated. Full-version source-only archive `/tmp/local-assistant-d27-complete-evaluation-full-files.zip`; local commit includes dev log, no push.

**Status:** **D27 PASS for local evaluation/retain-dense decision; D28 NEXT.** Independent-human/production-general quality, persistent runtime/co-residency, deployment SLO/load/multiworker/off-host DR remain unvalidated future work, not claimed PASS. The owner does not need to perform manual labeling. Continue D28 with an ADR before code, default-off authenticated source-held CORE generation, exact citation spans and post-model/final delivery/source lifecycle tests. No new model download or reranker adoption implied.


# 2026-10-19 — D28 source-held grounded generation, acceptance running

**Purpose:** Implement the next milestone after committed D27 local evaluation, retain actual failures and distinguish focused evidence from pending full acceptance.

ADR-043 precedes new default-off authenticated `POST /api/v1/grounded/answer`: unchanged approved dense source/embedding path and existing CORE/fast, temperature0/output512/model60s; no model download/replacement, DB/schema/collection or conversation persistence change. Strict bounded input/output, unique exact Unicode quotes and server-derived file/page/paragraph/cell/hash/generation provenance. Native structured fields are lexical evidence units, not JSON scaffolding. Source readers/admission remain held through generation/delivery with pre/post-model and final fences; client task cancellation/shutdown is joined before source release. Shared CORE is not restarted and backend memory erasure is not claimed. Only existing main/router/lifespan wiring changes are necessary in previously accepted application files.

Initial focused71 PASS/1 FAIL/52.60s: page-two copying returned insufficient_evidence because native page locator was omitted from model input. Original freeze/source/log failure retained. Pre-acceptance ADR amendment adds locator/field/quality and exact structured-field mapping; original questions/source/model/limits unchanged. Revised frozen focused **82 PASS/94.72s,0 SKIP**:75 unit/contracts/startup and7 live cases. Main live case performs6 actual CORE completions: PDF known fact, page-two Unicode, limited hostile-source instruction, foreign-owner fact isolation, absent identifier and immutable replacement. Other source race/cancel/shutdown/final-delivery cases intentionally use controlled model ports with real SQL/Qdrant/source resources. No universal factuality/injection-resistance claim.

Separate real loopback Uvicorn/TCP/approved embedding/CORE test **1 PASS/14.31s,0 SKIP**; fixture event loop, not separate-process/load certification. Full **1334-case Vault-backed regression RUNNING** on frozen source. No D28 PASS or D29 advancement until actual regression and post-audit. [API/limits guide](../docs/D28_GROUNDED_GENERATION.md), ADR/freezes/failure and focused private raw outputs retained; source archive and final local commit pending. Owner-delegated AI review remains in force; no manual-label task.


## Final D28 local grounded acceptance — 2026-10-19

**Purpose:** Close D28 only after actual full regression, native-field verification and clean read-only audit.

Full Vault-backed regression **1334 PASS in1387.90s (23:07),0 SKIP, exit0**. Original1251 plus83 D28 cases; focused82 and TCP1 are subsets. Two native-field tests added after collection then **2 PASS/1.21s,0 SKIP**: all7 DOCX paragraph/table and11 XLSX value/formula/cache goldens resolve through actual retained source/SQL/native extraction, ingestion planning and production citation parsing. They do not run a model or claim embedding-token admission. **1336 unique tests across checkpoints, not one1336-case full invocation.** No production source changed after successful full regression. Twelve Python files/72 function-class descriptions and Ruff correctness/import/format pass.

Full actual six CORE cases match focused status/known-fact outcomes; final/focused synthetic raw results retained separately. Actual loopback TCP citation passes. Lifecycle fault cases retain controlled-model disclosure; exact quote provenance is not general semantic factuality/injection resistance or calibrated confidence. Client-task/readers join does not certify shared CORE KV-cache erasure. The first page-location failure and v1 freeze/log/source hashes remain retained, not rewritten as success.

Read-only post-audit: schema0004, jobs/heads/files/quota/probe DBs/Qdrant collections/live encoder/reranker workers/advisory locks0; original owners/ACLs unchanged, immutable-manifest UPDATE denied/state allowed/TRUNCATE denied. Model registry/profiles/approved embedding/exact original E5 rollback/dependencies/migrations unchanged. All writes were owned removable probes. No new model, production flag/collection, schema/Vault/Docker change or shared-service restart. Temporary py-spy diagnostic tool was installed through uvx outside project dependencies while checking the long run; ptrace denied, no target-process mutation, and regression finished normally.

[Acceptance](../docs/evidence/d28-grounded-acceptance.json), [guide](../docs/D28_GROUNDED_GENERATION.md), native/TCP/execution freezes, protected-identity and clean post-audit retained. Roadmap v3.30/related runbooks/backlog updated. Full-version source-only archive `/tmp/local-assistant-d28-complete-full-files.zip`; local commit includes this dev log, no push. ADR-043 remains frozen pre-execution; actual acceptance is recorded here and in linked evidence.

**Status: D28 PASS for local opt-in grounded generation; D29 NEXT.** Continue memory classes/consent/provenance contract before D30 APIs/migration/extraction; no manual relevance review required or agreed model replacement authorized.


# 2026-10-19 — D29 four-class consent/provenance memory contract

**Purpose:** Complete D29 schema/design before D30 APIs/storage/extraction, preserving previously accepted application and models.

ADR-044 precedes strict frozen executable settings/consent/record/source schemas and a pure current-snapshot write/use authorizer. Session/episodic/preference/project scopes, independent default-off memory/extraction, consent epoch/revoke/expiry, mandatory bounded retention, manual text SHA and user-message/file lexical provenance with exact Unicode spans. Manual records have no model ID; extracted records require explicit permission/nonmanual source/verified producer. Source authenticity/fresh transactions are D30 obligations, not inferred from structurally valid IDs. Exported JSON schema and additive three-table SQL proposal remain outside migrations. No API imports, memory runtime, model inference, new dependency or model choice change.

Initial40 PASS/6 FAIL: synthetic quote length counted5 rather than4 Unicode code points; only fixture offsets corrected. Initial46 PASS/15 setup errors: app intentionally lacks TEMP. Existing dedicated Vault migrator supplies an operator-only schema-probe URL; app privileges unchanged, no root credential in API/tests. Subsequent60 PASS/1 FAIL raw UUID JSONB fixture serialization and62 PASS/1 FAIL wrong `psycopg.CheckViolation` test namespace corrected. SQL null-kind provenance refusal added. Final **63 PASS/0.53s,0 SKIP, exit0**:47 pure consent/hash/Unicode/scope/time/budget/default/strictness/audit cases and16 actual connection-private temporary PostgreSQL cases. SQL tables/data roll back; no permanent relation/migration applied. Three Python files/42 function-class descriptions and Ruff correctness/import/format pass.

All254 preexisting tracked code/tests/config/models/migrations/dependencies from D28 commit `a2cc9c0` byte-identical. D28 full1334 PASS/1387.90s plus2 additional native-field PASS remain unchanged baseline; D29 adds63 separately: **1399 unique tests across checkpoints, not a new1399-case full invocation**. New unused contract does not justify rerunning unchanged expensive model benchmarks. Read-only audit: schema0004, memory relations0, app TEMP false/migrator TEMP true, old owners/ACL unchanged; files/jobs/heads/quota/probe DBs/Qdrant collections/live workers/advisory locks0. No app grants/schema/Vault/Docker/service/model changes.

[Design](../docs/MEMORY_DESIGN.md), [validation](../docs/evidence/d29-contract-validation.json), [post-audit](../docs/evidence/d29-final-post-audit.json), ADR-044 and proposed relational/JSON schemas retained. Roadmap v3.31 updated. Full-version source-only archive `/tmp/local-assistant-d29-complete-full-files.zip`; local commit includes dev log, no push.

**Status: D29 PASS for design/contract only; D30 NEXT.** Memory persistence/APIs/extraction/retention cleanup and D31 privacy/propagation are not implemented or claimed PASS. Continue with implementation ADR, backup/restore/grants/startup review before additive D30 migration. No manual relevance task or model replacement is required.


# 2026-10-19 — D30-T01 additive memory journal, rollout preparation

**Purpose:** Continue after D29 commit `ab6cff9`; implement storage/controls first without claiming the whole D30 API/extraction milestone complete.

ADR-045 precedes V005 additive memory schema/narrow grants/downgrade refusal and an unused owner-scoped repository for explicit settings epochs, receipts, manual capture/inspect/edit/delete and bounded expiry purge. Server hashes/UUIDs/time; compare-and-swap settings/record revisions, owner locks, receipt revoke/expiry/epoch checks and owner/global admission caps. No memory service/API/model prompt/extraction or feature flag enabled. Necessary existing file/ingestion schema guards accept reviewed0005 while retaining unknown-revision and immutable-ingestion-grant refusal; source/index behavior unchanged.

Related unit/startup/contracts **91 PASS/0.55s,0 SKIP**. Actual PostgreSQL tests are prepared for four classes, foreign/unowned scope denial, immutable runtime grants, quota and concurrent disable/revoke/version fencing; not yet run. V005 offline SQL rendered/reviewed without connecting. Fresh protected cluster/app backup plus isolated app restore verifies all9 old tables and ownership/ACLs, source unchanged after canary cleanup; no shared restart. Backup paths/checksums in `docs/evidence/d30-t01-pre-migration-restore.json`. Pre-rollout source/DDL snapshot retained. Migration/repository acceptance and D30 remain IN PROGRESS; no PASS without actual rollout/tests.


## Verified D30-T01 repository/schema checkpoint — 2026-10-19

**Purpose:** Accept the additive journal/control task from actual rollout and tests while continuing open D30.

Reviewed V005 applied through existing Vault migrator after fresh quiet pre-backup/isolated restore of9 original tables/security. Original8 data-table fingerprints and all old relation/schema owners/ACLs preserved; new12-table post-backup restores rows/security and removes its owned probe. No shared restart, old-table DDL, role/credential/Vault/model change. File/ingestion guards only add reviewed0005; unknown-schema and immutable-ingestion checks remain. Applied migration source hash unchanged after rollout.

First focused121 PASS/2.85s; source-related113 PASS/218.66s,0 SKIP on0005: file journal/HTTP/crash/recovery, ingestion journal/worker/HTTP, dense retrieval and existing actual CORE grounded ASGI/TCP/native-field gates. Pre-API review found missing receipt inventory caps; add1000 owner/10000 global using existing global-before-owner admission, no schema change. Two actual full receipt inventory cases added. Final focused **123 PASS/3.21s,0 SKIP**; real app-role four-class CRUD, exact Unicode hashes, foreign/unowned/session refusal, immutable grants, version/epoch/revoke/expiry, rollback, actual record/receipt quotas and concurrent settings/disable/revoke ordering pass. Fixture quota seeding is actual constrained SQL, not10000 model/HTTP calls.

T01 adds38 unique cases; prior D28 full1334 plus2 new native-field and D29 new63 remain baseline: **1437 unique tests across checkpoints, not a new1437 full invocation**. Final whole-system regression still required before D30 acceptance. Nine current Python files/72 descriptions and Ruff checks pass. New schema/repository/control scope acceptance only; no memory API, source extraction, prompt injection or background retention service enabled.

Read-only final audit: revision0005, memory settings/receipts/records0; files/jobs/heads/quota/probe DBs/Qdrant collections/live workers/advisory locks0. Old owners/ACL unchanged; app TEMP false, memory owner/receipt expiry UPDATE denied/text allowed, ingestion immutable UPDATE denied/state allowed/TRUNCATE denied. Original registry/models/embedding/E5 rollback/locks/dependencies unchanged. [T01 guide](../docs/D30_MEMORY_JOURNAL.md), [acceptance](../docs/evidence/d30-t01-journal-acceptance.json), pre/post restore/rollout/source hashes/raw actual grounded evidence retained. Full-file archive `/tmp/local-assistant-d30-t01-complete-full-files.zip`; local commit includes dev log, no push.

**Status: D30-T01 PASS local repository/schema; D30 IN PROGRESS, T02 authenticated default-off APIs NEXT, T03 source-verified opt-in extraction/retention later.** No day advancement or unavailable human review task. Continue T02 after this checkpoint.


# 2026-10-19 — D30-T02 authenticated default-off memory management

**Purpose:** Continue after T01 commit `89ceb18`; expose consented manual controls while retaining open extraction/retention/full-day gates.

ADR-046 precedes new local bearer-authenticated `/api/v1/memory` settings/consent/manual record routes, default-off startup/schema/grant validation and a service owning joined SQL work. Strict bodies forbid caller owner/model/provenance/trust; private/no-store/nosniff responses and stable sanitized validation/auth/storage errors. Metadata-only bounded lists, explicit record inspection, expected settings/record revisions, active-consent capture/edit and owner inspect/delete while disabled. Necessary main/router/lifespan wiring only; memory shutdown precedes existing source/pool shutdown. No model inference, extra credential/migration/dependency or production flag.

Initial37 focused PASS/1.63s and108 related PASS/9.19s. Additional repeated-parent-cancel test produced25 PASS/1 FAIL/.58s: inline awaited journal cleanup could be interrupted before it finished. Fixed using a shielded owned SQL child and accepted cancellation-resistant finish_task join before tracking release.26 unit PASS/.53s. Actual SQL test now observes owned backend `PgSleep` before shutdown cancellation, proves rollback/no settings row and pool checkout0. Final **109 PASS/9.11s,0 SKIP**, including all38 new cases (26 unit+12 actual HTTP/SQL/TCP) and71 existing file/conversation/startup cases. No final separate38-case run or1475-case full invocation claimed.

Actual V005 two-principal HTTP proves four-class manual CRUD, disabled inspect/delete, foreign receipt/record denial, revoke/old-epoch refusal and atomic invalid UTF-8-byte/NUL/metadata capture. Real ephemeral Uvicorn/TCP passes auth/Origin/private manual controls and joins operations/server. Source fixture event loop, not separate-process/load/model-quality certification. Read-only audit schema0005 unchanged; memory/source/quota/restore probes/vector/model workers/advisory locks0, old owners/ACL unchanged. Model registry/profiles/Qwen selection/exact E5 rollback/migrations/dependencies unchanged. Seven Python files/51 function-class descriptions and Ruff checks pass.

[T02 guide](../docs/MEMORY_API.md), [acceptance](../docs/evidence/d30-t02-api-acceptance.json), [post-audit](../docs/evidence/d30-t02-final-post-audit.json), actual TCP evidence retained; roadmap v3.33 updated. T02 adds38 unique tests: **1475 unique across checkpoints, not a new full-suite invocation**; D30 final full regression remains required after T03. Full-version source archive `/tmp/local-assistant-d30-t02-complete-full-files.zip`; local commit includes dev log, no push.

**Status: D30-T02 PASS local management APIs; D30 IN PROGRESS, T03 explicit source-verified model selection and bounded retention NEXT.** No automatic memory use/extraction, source propagation or export claimed. Continue T03 under a source/lifecycle ADR before implementation; preserve agreed models.


# 2026-10-19 — D30-T03 explicit source selection, acceptance in progress

**Purpose:** Continue T03 after `701530c` without advancing D30 before actual model and full regression results.

ADR-047 precedes explicit single-user-message CORE/fast quote selection, fresh owner/consent/source fences through delivery, joined cancellation and bounded expiry retention. Default off; no automatic learning, file-memory adapter, prompt memory injection, model replacement or migration. Future additions assessed in MEMORY_BACKLOG.md.

Source/contracts and related SQL/API checks: **128 PASS/4.92s,0 SKIP**. Earlier108 PASS/1 FAIL exposed strict UUID decoding of extracted JSONB provenance; targeted tagged UUID decoder and five regression cases correct that boundary while preserving strict contract and applied V005. Original failure retained privately. Tests include controlled cancellation, exact Unicode/hash proof, actual SQL source/epoch/revoke/expiry and bounded cleanup. These results do not yet establish actual CORE selection quality.

**Status: D30-T03 IN PROGRESS.** Freeze source and synthetic English/Vietnamese/greeting/TCP oracles before real existing CORE runs. Actual model, final whole-system regression and final audit pending; no D30 PASS or D31 advancement.

T03 live first attempt: Vault HTTP503 after host/container restart; existing protected initializer unsealed existing Vault without rotation/config change. Existing CORE was absent; resumed original configured CORE with vision, no model download/configuration change. Initial live attempt while CORE still loading produced2 FAIL/10 fixture setup errors/2.44s; these are not acceptance results. Added explicit upstream fixture import so the new live module can run standalone; exact model oracles unchanged. Wait for health200 before retry. Failure log retained at `data/backups/d30-t03-live-initial.log`.

Healthy retry:12 actual SQL/CORE/HTTP/TCP cases PASS/2.62s; combined source/control/API checkpoint **140 PASS/6.78s,0 SKIP**. Actual CORE made four source-literal calls (English project/Vietnamese preference/greeting insufficiency/TCP preference); no new model or human-independence claim. ADR-044 audit found missing owner-export obligation; ADR-048 adds bounded read-only consistent snapshot export before day acceptance. Initial export6 PASS/1 FAIL/.73s was a fixture comparison of equivalent UTC `Z` and `+00:00` spellings; compare actual aware instants, unchanged serialization. Actual SQL/HTTP export cases already passed. Final full regression still pending.


## D30 final local acceptance — 2026-10-19

**Purpose:** Close D30 only after real model, full regression and post-audit results; continue D31 afterward.

ADR-047/048 implementation: explicit single-owned-user-message CORE/fast source-literal selection with fresh source/consent/version fences through delivery; joined model/SQL cancellation and owner-control drain; bounded rotating expiry/orphan worker; read-only repeatable-read principal-only export while disabled. No file-memory adapter, automatic learning, memory prompt/vector use, new dependency/model/schema in T03. Necessary tagged JSONB UUID decoder repairs only extracted record reads; original strict contract/manual behavior and applied V005 retained.

Final focused **147 PASS/6.91s,0 SKIP**. Final whole-system **1570 PASS/1357.69s (22:37),0 SKIP, exit0**, including95 new T03 cases and every prior case in one actual invocation. Four real CORE calls per focused/full run establish literal English/Vietnamese facts, greeting insufficiency and TCP preference; synthetic same-agent evidence is not human-independent/general model quality. Controlled model ports remain explicitly distinguished from actual inference. All17 changed Python files/166 function-class descriptions, Ruff correctness/import/format and diff whitespace checks pass.

Post-audit:0005, memory settings/consents/records0; files/jobs/heads/quota/probe DBs/Qdrant collections/model workers/advisory locks0; no active app transaction/pending inference. Original owners/ACLs and narrow app TEMP/identity/expiry/ingestion grants preserved. Model registry/profiles/approved Qwen embedding/exact E5 rollback/dependencies/all applied migrations unchanged. Existing Vault was unsealed and original CORE/vision resumed after external host restart; no rotation/model download/config change. Original JSONB/setup/UTC fixture failures and healthy retries retained in focused ledger.

[Guide](../docs/D30_MESSAGE_MEMORY_SELECTION.md), [acceptance](../docs/evidence/d30-memory-acceptance.json), [post-audit](../docs/evidence/d30-final-post-audit.json), frozen source and actual CORE/HTTP/TCP evidence retained. Full-version source archive `/tmp/local-assistant-d30-complete-full-files.zip`; local commit includes dev log, no push.

**Status: D30 PASS (local opt-in), D31 NEXT.** Continue privacy/injection/source deletion/export propagation from actual code; production flags off, no agreed-model replacement or manual relevance task.


# 2026-10-19 — D31-T01 source privacy baseline

**Purpose:** Continue after D30 commit `478bec0`, testing actual deletion/export propagation before changing accepted behavior.

Three real SQL/HTTP tests with explicitly controlled inference **3 FAIL/.84s,0 SKIP**: conversation soft-delete, source message edit and source message delete all leave extracted text in owner export/inspection. These are honest D31 acceptance failures, not a D30 full-suite result change. Own manual independent records must survive. Failure evidence/log checksum retained. ADR-049 precedes proposed invoker-security V006 transactional source invalidation and related startup compatibility; rollout requires empty memory inventory, unchanged old data/security, fresh protected backup/restore and actual tests. V006 not applied yet; D31 IN PROGRESS, no day advancement.


## D31-T01 reviewed source invalidation rollout — 2026-10-19

Private PostgreSQL proposal14 PASS/.48s; pre-rollout contracts/compatibility **59 PASS/.86s,0 SKIP**. Reviewed offline SQL and ADR-049 precede fresh protected cluster/app backup and isolated12-table restore. V006 applied through existing migrator after quiet/empty-memory preconditions. All11 old data-table fingerprints and original schema/table/column ACLs unchanged; only Alembic version plus two functions/triggers and partial provenance indexes added. Post-V006 protected12-table restore verifies rows, normalized ACLs and exact function/trigger definitions; own restore DB removed. No shared restart, model/config/dependency/credential change; old migrations untouched.

First post-rollout related **262 PASS/10.23s,0 SKIP**, including all memory/source contracts and actual CORE/HTTP/TCP. Source privacy extended beyond original3 failures: **25 PASS/1.83s,0 SKIP** across real SQL/HTTP owner-disabled, foreign/manual/session boundaries, transactional rollback, actual1000-row SQL-copy cleanup and capture→waiting-source ordering observed in pg_stat_activity `Lock`; two functions invoker-only/fixed search_path/no direct app EXECUTE.1000 copies are SQL fixture seeding, not1000 model/API calls. Original3 failing oracles retained, no weakened expectation.

V006 source is now applied/immutable; checksum and restore evidence in `d31-t01-v006-rollout.json`. D31 remains IN PROGRESS; source task final related audit and injection/export/purge gates remain. Preserve D30 historical1570 full result; no new1598 full invocation claimed.


## D31-T01 final source-task checkpoint — 2026-10-19

**Purpose:** Accept the verified source repair task and continue open D31 privacy work.

Final **271 related PASS/11.00s,0 SKIP** includes all memory contracts, new source/private proposal/concurrency/grant cases and actual existing CORE/HTTP/TCP. Existing conversation/file/ingestion/retrieval/grounded source-system **140 PASS/216.58s,0 SKIP** on0006. Added actual explicit PATCH-to-manual detachment test: independent preference survives source delete, unlike session scope. All11 changed Python files/83 descriptions and Ruff correctness/import/format pass; applied V006 checksum frozen. No changed model/runtime/dependency or old migration bytes.

Readonly post-audit:0006, no app transaction/pending inference; memory/source/quota/probe DB/vector/model worker/advisory lock inventories0; original owners/ACLs and narrow runtime grants preserved. New source functions have fixed search_path/invoker security and app direct EXECUTE denied. Fresh pre/post12-table restore includes exact trigger/function definitions and column ACLs; original11 data tables unchanged across migration. No shared restart or production feature enabled. Initial3 source failures preserved unchanged;1000 deleted copies were SQL fixtures, not1000 model/API calls.

[Source acceptance](../docs/evidence/d31-t01-source-acceptance.json), [guide](../docs/D31_PRIVACY_AND_DELETION.md), rollout and post-audit retained. T01 adds29 unique cases:1599 across checkpoints, **not a new1599 full run**; D30 historical1570 full remains separate. Full-version source ZIP `/tmp/local-assistant-d31-t01-complete-full-files.zip`; local commit includes dev log, no push.

**Status: D31-T01 PASS locally; D31 IN PROGRESS, T02 injection/export/DB-vector-blob deletion tests NEXT and final full regression pending.** No secure erasure of original soft-deleted history, protected backups, delivered exports or shared model cache is claimed. Continue T02 within current model choices.


# 2026-10-19 — D31-T02 privacy composition testing

**Purpose:** Continue after source repair commit `d1721cd` without changing production code or agreed models.

Test plan freezes structural privacy gates before new actual CORE/source-vector checks. Actual HTTP controlled protocol/auth/export/log/physical-memory-deletion boundaries **7 PASS/1.01s,0 SKIP**. First actual CORE/vector run **1 PASS/1 FAIL/13.52s**: original CORE/fast malicious-source check returns explicit insufficient_evidence, no foreign canary/marker execution; file test incorrectly used the visible-only journal reader to inspect an intentionally hidden deleted tombstone. Keep failure/source checksum; inspect only the exact fixture owner/file through raw SQL instead. Strengthen the test to index/preserve the other principal's vector as well as its blob. Production file/journal/source code unchanged, privacy gates not weakened; D31 remains open for retry and full regression.


## D31-T02 focused composition checkpoint — 2026-10-19

**Purpose:** Continue actual privacy tests while keeping whole D31 open for final full regression.

Final focused **9 PASS/20.90s,0 SKIP**: controlled adversarial protocol/error/log/privacy cases, actual foreign pre-model refusal, private owner export and physical per-record SQL deletion retain separate source/foreign data. Existing CORE/fast malicious-source case returns insufficient_evidence, no foreign canary or marker file; one synthetic case is not universal semantic injection resistance. Actual approved Qwen/Qdrant/file case proves exact source deletion gives inactive/tombstone DB generation/cleanup acknowledgement, zero scoped vectors, physically absent target blob, quota0 and preserved foreign blob/vector. Durable journal/vector payload contain no source marker.

Initial1 PASS/1 FAIL/13.52s retained: visible-only file reader intentionally hides deleted tombstone; fixture now uses exact owner/file SQL, with stronger foreign-vector preservation. No production code, model prompt/runtime/profile, dependency or applied migration changed in T02. One unused test assignment removed with identical source-creation side effect before final freeze; original failure and retry manifests preserved. Broader transcript/bulk-memory purge assessed as unscheduled conditional backlog, not silently added to accepted semantics.

Final V006 full regression and post-audit pending; no1608-case full result or D31 PASS claimed yet.


# 2026-10-20 — D31 final privacy acceptance after preserved full result

**Purpose:** Resume the completed full run after external environment restart, verify its source/current state and close D31 before D32.

Preserved full log completed2026-10-19: **1608 PASS/1361.93s (22:41),0 SKIP**; no failure/exclusion. Process session/exit status was not retained across restart; the complete pytest summary/log SHA is retained. This entry does not claim a fresh full run after reboot. All252 frozen code/test/config files plus protected models/dependencies/applied V001–V006 match exactly. Existing Vault unsealed with protected existing material, no rotation/policy/config change; read-only current audit2026-10-20 verifies0006, no active app/pending inference, memory/source/quota/restore probes/vector collections/model workers/advisory locks0, original owners/ACLs/narrow grants and fixed invoker-only/no-direct-app-EXECUTE source functions.

T02 focused9 PASS/20.90s and actual full-run artifacts confirm CORE malicious-source insufficiency/no foreign canary or marker file; actual approved Qwen/SQL/Qdrant/blob delete leaves inactive text-free tombstone/cleanup acknowledgement, zero scoped vectors/absent target blob/quota0, while foreign blob and one vector remain. Physical per-record memory deletion keeps its separate source. Earlier source3 FAIL and file-reader fixture failure remain recorded. T01 adds29 tests/T02 adds9:38 new D31 cases, all1608 tests now in one actual full invocation. No production source/prompt/model/migration change in T02.

[Final acceptance](../docs/evidence/d31-privacy-acceptance.json), [guide](../docs/D31_PRIVACY_AND_DELETION.md), [current audit](../docs/evidence/d31-final-post-audit.json) and actual evidence retained. Full-version combined D31 source archive `/tmp/local-assistant-d31-complete-full-files.zip`; local commit includes dev log, no push.

**Status: D31 PASS for documented local privacy gates; D32 NEXT.** Conversation soft-delete, independent manual decisions and protected recovery/export/cache retention domains remain explicit limits, not secure-erasure certification. Continue actual integrated RAG/citation/limitations gate, preserving agreed models and existing PASS code.


# 2026-10-20 — D32 frozen native knowledge gate

**Purpose:** Verify the composed native-format RAG path with the agreed existing models before advancing D33.

Pre-inference [plan](../docs/evidence/d32-knowledge-plan.json) freezes TXT/PDF/DOCX/XLSX hashes, manual native field relevance, five answerable questions, absent and foreign-only refusal. Existing independent source fixtures, same-agent labels, no human-independent/general model-quality claim. All four actual Qwen publications succeed:1/2/5/5 chunks. First wrapper invocation1 setup ERROR/1.02s used asyncpg URL despite application's psycopg requirement; fixed private wrapper only, retained redacted log/exit metadata.

Actual unchanged baseline gate **1 FAIL/70.32s,0 SKIP**: TXT/PDF answer correctly; DOCX returns insufficient_evidence despite top3 including table1 row2 (`một`→`42`). `build_messages` flattened fields without row/column relationships. [Original failure](../docs/evidence/d32-initial-native-failure.json) and initial source freeze retained; no query/golden/top3/model change. ADR-050 precedes necessary structured-only source-group prompt repair in one runtime file. Plain TXT/PDF prompt remains identical; strict native quote authority, deadlines and prompt/token budgets retained. Initial new unit86 PASS/1 FAIL/.79s: synthetic OCR second-group locator changed without corresponding native spans; fix only fixture consistency, unchanged runtime fences. Final combined actual model/regression and cleanup audit pending.

**Status: D32 IN PROGRESS; D33 not started.** No new model/download/dependency/configuration/schema/vector generation rewrite.


## D32 final local knowledge acceptance — 2026-10-20

**Purpose:** Accept the frozen integrated gate only after actual inference, related regression and cleanup; continue D33.

Necessary ADR-050 repair adds verified native structure/source-ID groups only to structured prompts, preserving exact lexical quote authority and unchanged plain TXT/PDF system/user JSON. No model/question/golden/relevance/top3/budget/source-fence change. Actual final **90 focused PASS/108.24s +9 HTTP/TCP/privacy PASS/105.51s,0 SKIP, both exit0**. Four actual Qwen publications1/2/5/5 chunks;6 unchanged CORE/fast calls yield5/5 answers and5/5 exact relevant native citations (precision1.0 on this limited frozen set), absent insufficiency and foreign no_sources with0 generation. Native DOCX42 and XLSX cached30 are source-verified; cache is not recomputed/current truth. Synthetic same-agent data is not human-independent/general quality.

Initial70.32s native failure and unchanged original plan retained; corrected synthetic OCR locator fixture and private wrapper driver setup error remain disclosed. An accidental unscoped collect entered vendored llama.cpp tests and found2 missing optional upstream dependencies; proper application `pytest tests --collect-only` succeeds1621, no dependency/vendor change.13 new cases; historical D31 full1608 remains separate, **no fresh1621 full invocation claimed**. Three Python files/14 function-class descriptions, Ruff correctness/import/format and whitespace pass. Related D28 guide/ADR cross-reference updated without rewriting history.

Readonly final audit:0006, files/jobs/heads/memory/quota/restore probes/Qdrant collections/model workers/advisory locks0, no app/pending work; original owners/ACLs/narrow grants/fixed invoker-only trigger functions retained. Only accepted runtime baseline delta is the grounded structured prompt; all other frozen bytes/protected models/E5 rollback/dependencies/applied migrations unchanged. No production flags or shared infrastructure changed.

[Acceptance](../docs/evidence/d32-knowledge-acceptance.json), [demo/limits](../docs/D32_KNOWLEDGE_GATE.md), [actual native evidence](../docs/evidence/d32-native-knowledge-live.json), [audit](../docs/evidence/d32-final-post-audit.json). Full-version changed-file ZIP `/tmp/local-assistant-d32-complete-full-files.zip`; local commit includes dev log, no push.

**Status: D32 PASS (defined local knowledge scope), D33 NEXT.** Next work is explicit repository/workspace scope isolation, not coding tools or a model replacement.


# 2026-10-20 — D33 local workspace scope foundation

**Purpose:** Continue after D32 commit `9928957`, establishing actual filesystem boundaries before D34 exposes repository reads.

ADR-051 precedes new immutable owner/workspace UUID specifications and explicit clean absolute roots (max8), plus unused readonly Linux openat2 capability/discovery adapter. No cwd/home/parent inference, runtime registration, endpoint, CLI identity shortcut, git/config/hooks execution, model call, file modification, database/config/dependency change. Authorize owner before root opens; kernel BENEATH/NO_SYMLINKS/NO_MAGICLINKS/NO_XDEV resolve beneath pinned root. Public hidden/traversal/unbounded paths, regular hard-link aliases and IPC targets denied; root identity rechecked, all FDs joined. Discovery returns only configured metadata and directory/git marker kind; worktree pointers never followed.

Initial59 PASS/.12s, strengthened63 PASS/.12s and288 related PASS/7.06s are subsets/checkpoints. Further stronger mount oracle first **287 PASS/1 FAIL/7.03s**: child harness missing os/errno/helper imports. Preserve failure metadata; fix only child imports, keep actual native EXDEV plus same-device check and runtime code. Final **288 related PASS/7.02s,0 SKIP, exit0**, including63 new cases, actual bind mount in private credential-free namespace and path-to-symlink swap exactly before syscall. Existing source policy/blob locks/verifier sandbox regression included. Controlled ENOSYS/platform/fstat injections are disclosed separately from real kernel cases. Four new Python files/44 descriptions, Ruff correctness/import/format pass.

All accepted D32 application/test/config/model/dependency/applied migration bytes remain unchanged. Application collection1684 succeeds, **not a fresh1684 full test run**; historical D31 full1608 and D32 focused99 remain separate. Readonly audit0006/empty source-memory-quota/vector-worker-lock inventories, no app/pending work, original owners/ACL/narrow grants and fixed invoker triggers retained. New code operates only on disposable fixture roots; no host mount or repository contents changed.

[Scope/limits](../docs/D33_WORKSPACE_SCOPE.md), [acceptance](../docs/evidence/d33-workspace-acceptance.json), [source freeze](../docs/evidence/d33-workspace-freeze.json), [post-audit](../docs/evidence/d33-final-post-audit.json). Full-version ZIP `/tmp/local-assistant-d33-complete-full-files.zip`; local commit includes dev log, no push.

**Status: D33 PASS for the local capability/discovery foundation; D34 NEXT.** No authenticated repository read endpoint yet. Admission-time descriptor policy is not a sandbox against arbitrary same-UID host processes or a guarantee of membership after later path movement; bounded authenticated inventory/search and line provenance are D34, writes/execution/approval require their later gates.


# 2026-10-20 — D34 authenticated workspace snapshots in progress

**Purpose:** Continue after D33 `3a3489e` without stopping at an arbitrary milestone boundary; implement bounded source discovery/reads before coding tools.

ADR-052 precedes default-off operator-private explicit workspace config and local bearer/Origin-protected discovery/inventory/read/literal search/lexical Python hint APIs. Reuse D33 actual openat2 scope; no model/git/shell/hooks execution, writes, database/schema/Vault/config/dependency changes. Only existing app router/lifecycle composition is extended; no host workspace is registered. New snapshots retain root through final inode/stat/hash/marker validation before headers; source lines preserve raw hash, LF line numbers and Unicode columns, with exact CRLF handling. Strict request/scan/file/line/response bounds,16KiB incoming stream guard,5-second cooperative deadline and joined worker/descriptor cancellation.

Intermediate69 PASS/.89s,83 PASS/.95s and86 PASS/.97s cover real HTTP/TCP/source/auth/limits; later149/152 focused checkpoints include existing63 D33 cases and stronger native limits, completed-worker ownership race, repeated cancel/shutdown/send-error and later DB-startup rollback. These are subset checkpoints, not added full-suite totals. Final153 workspace-focused cases include a lone final CR oracle; actual full application regression/source freeze and final audit pending. No D34 PASS or D35 advancement yet.

See [scope/limits](../docs/D34_WORKSPACE_READS.md), ADR-052 and new tests. Keep current models/E5 rollback, applied V001–V006 and all unrelated PASS code unchanged.


D34 pre-full hardening checkpoint: **153 workspace-focused PASS/1.09s,0 SKIP** preceded full1774 invocation. While it ran, an independent isolated HTTP probe found actual malformed-body failures: NaN raises ValueError and overlong unpaired surrogate raises UnicodeEncodeError during framework error serialization. Intentionally SIGINT only the verified pytest PID; normal fixture teardown completed **exit2/no completed tests/414.48s**. This interrupted run is neither PASS nor a completed regression; v1 freeze/log/exit metadata retained. Add strict bounded JSON-object parsing on the new router only (duplicate/nonfinite/exponent-overflow/depth/Unicode rejection before framework parsing).11 new malformed-body cases require safe422 before any workspace root open. New evaluated source/full rerun and post-audit pending; D34 stays IN PROGRESS.


Post-correction checkpoint: **164 workspace-focused PASS/1.10s,0 SKIP**, including101 new D34 cases and unchanged63 D33 cases.11 malformed-body cases now return sanitized422 before root access. Ruff correctness/import/format passes11 Python files/91 described function-class definitions. Interrupted-run read-only audit verifies0006, source/memory/quota/probe DB/vector/model-worker/advisory-lock inventories0, no app/pending work and original owners/ACL/narrow grants preserved. V2 freeze fixes301 evaluated files/protected hashes; full **1785** application rerun started with durable per-test progress/exit metadata, still pending. No D34 PASS or D35 implementation/adoption; ADR-053/tool plan are preparation drafts only.


## D34 resumed after observed host restart — 2026-10-20

Corrected full-run log retains159 completed PASS and no failure markers, but no wrapper/pytest process or observed exit remains. Host boot is now07:30:57 local; prior log last modified01:51:38 local, so exact cause/time of process loss is not established. `/tmp` helpers disappeared. This159-case partial is **not a completed full regression**. Earlier status message inferred liveness from a stale running sidecar; corrected by actual PID/boot inspection and new boot-aware monitoring. Full source301/protected hashes match exactly.

Existing Vault unsealed using existing protected material, audit device preserved; original CORE/vision resumed and health200 confirmed. No rotation, model/config/dependency/infrastructure change. Readonly DB0006: files/jobs/heads/memory/quota/pending inference0. Qdrant has one empty `la_d25_probe_...` acceptance collection; verify exact metadata/schema/model, quiet DB and points0 through existing owned adapter, delete only that acknowledged empty probe and confirm collections0. No source rows/vectors/user collection removed. [Inventory](../docs/evidence/d34-reboot-inventory.json), [empty-probe cleanup](../docs/evidence/d34-reboot-empty-probe-cleanup.json), [partial-run evidence](../docs/evidence/d34-reboot-interrupted-full.json).

Fresh full1785 rerun uses the same301-file freeze, durable ignored runner/logs and server-assigned pytest/wrapper PID plus boot ID. Detached test launcher survives chat process loss; a machine reboot still invalidates live progress. Status helper reports running only if boot and both recorded command identities match. Final exit/hash and actual full summary required before audit/acceptance. D34 remains IN PROGRESS; D35 drafts only, no source implementation/advancement.


## 2026-10-20 — D34 accepted after completed full regression

**Purpose:** Record observed completion rather than infer PASS from implementation or partial progress. Implementation checkpoint `64459f6` retained; fresh boot-aware run finished at01:37:42 UTC: **1785 PASS/1509.95s,0 SKIP,exit0** (runner1510.60s). Includes101 new D34 cases;164 workspace-focused PASS/1.10s is a subset, not extra cases. Durable redacted full log SHA256 `dccba1a107f50acc9bb70510158855bcbf80f5d947d4fe98cd707695c216bb01`. All301 evaluated files/protected hashes exactly match v2 freeze.

Ran `uv run --no-sync python data/backups/d34-final-post-audit.py`: exit0. V006; source/jobs/heads/memory/quota/probe DB/vector/model-worker/advisory-lock inventories0, no app connections/pending work, original owners/ACLs/narrow grants and invoker triggers preserved. Only existing router/lifecycle wiring changed; agreed model/config/dependency/applied migration bytes unchanged. No host workspace registered or production flag enabled. Earlier NaN/surrogate errors, interrupted exit2 and159-case process-loss partial remain separate truthful evidence.

[Acceptance](../docs/evidence/d34-workspace-acceptance.json), [final audit](../docs/evidence/d34-final-post-audit.json), [guide](../docs/D34_WORKSPACE_READS.md), ADR-052. Full-version checkpoint ZIP verified under durable `data/backups/`; final archive includes acceptance updates. **D34 PASS (local bounded authenticated read-only scope); D35 NEXT.** Continue scoped deterministic dispatcher/schema/budget work under ADR-053, without model replacement or command/write capability.


## 2026-10-20 — D35 internal deterministic tool dispatch PASS

**Purpose:** Continue immediately after accepted D34 `78542b0`, implement ADR-053 finite read-tool gate before CORE coding composition. Add shared strict request classes/registry schemas and ephemeral request-owned `WorkspaceToolRun`: fixed trusted owner/workspace, server run/call IDs, strict16KiB envelopes, five fixed read tools,8 attempts/60s lifetime/20s tool time/5s call/64KiB call/256KiB run. Invalid/repeated/failed/cancelled/overlap attempts consume budget; serialize/count exact UTF-8 bytes before exposure, validate native source and join cleanup, charge time through cleanup, no retries/refunds/fallbacks. Only existing workspace route schema imports change; HTTP shapes/guards preserved. No public run endpoint, model call, session DB, host workspace or production flags.

Initial220/223 workspace PASS and121 related API/auth/startup PASS are subset checkpoints. Added fixed real UTF-8 output caps, both typed identity fields, native sanitization and post-cleanup deadline coverage. Final **349 related PASS/1.60s,0 SKIP,exit0**, including64 new D35 cases. Controlled clock/cap/failure tests disclosed separately from actual native source/thread cases. Ruff initially absent from project environment; `uv tool run --offline ruff` uses existing cached0.17.1, correctness/import/format pass without dependency modification. All changed functions/classes have descriptions. Full1849 collection succeeds; **not a fresh1849 full run**; D34 actual full1785 remains separate.

`uv run --no-sync python data/backups/d35-final-post-audit.py`: exit0. V006/empty source-memory-quota-vector-probe-worker-lock inventories, no app/pending transactions, original owners/ACL/narrow grants, selected models/E5 rollback and applied migrations unchanged.300 other frozen D34 files/protected hashes retained; four D35 evaluated files match freeze. [Acceptance](../docs/evidence/d35-tool-acceptance.json), [related invocation](../docs/evidence/d35-related-regression.json), [post-audit](../docs/evidence/d35-final-post-audit.json), [guide](../docs/D35_READ_TOOL_DISPATCH.md). Full changed versions archived in durable `data/backups/`. **D35 PASS (internal deterministic read-tool scope); D36 NEXT.** Continue source-cited explanations using existing CORE, no new model/command/write capability.


## 2026-10-20 — D36 source-cited workspace explanations in progress

**Purpose:** Continue after D35 `8ce51d3` under ADR-054 without changing agreed models. Explicit1–3 selected files, shared D35 read contracts/dispatch, fixed CORE/fast, exact unique line quote citations and independently pinned native root/source receipts across model latency. Fresh D34 reads authorize post-model and pre-header delivery; no D34 deadline reset, no global workspace admission held during model work. Default-off endpoint/lifecycle wiring is the necessary related existing change. No command/write/model download/data migration or real host workspace registration.

Initial **39 parser/native-service PASS/.29s** uses disclosed controlled inference and independent Unicode/hash/line oracles; includes actual source/root/delete/final-delivery mutation fences, foreign/no-generation, blank-source handling, model cancel/repeated cancel/shutdown and typed scope admission. This is not real model quality evidence or D36 acceptance. HTTP/TCP/startup, actual original CORE frozen cases, strengthened FD/timeout/failure boundaries and related regression/audit remain pending. **D36 IN PROGRESS.**


## 2026-10-20 — D36 source-cited CORE explanations PASS

**Purpose:** Complete ADR-054 explicit source-selected explanations and continue to diagnosis without modifications. Default-off authenticated `/workspaces/{id}/explain`,1–3 distinct selected reads through D35, private root FD pins/native stat/hash receipts across CORE latency, fresh D34 post-model/pre-header reads without extending its5s deadlines. Fixed existing CORE/fast/temperature0/max768/60s model deadline. Strict generated JSON resolves up to3 unique exact quotes to original path/hash/LF line/Unicode offsets; source and answer remain untrusted. Only existing main/lifecycle router/startup/shutdown composition changes, no agreed model/data/config/migration/infrastructure change or host workspace registration.

Initial39/62/70/74 test invocations are subset checkpoints. Actual original `qwen3.5-9b-core`:2/2 frozen explanatory cases correct with relevant exact native citations;1/1 absent question refused. Raw synthetic observations retained; same-agent authored goldens, not independent human/general coding quality. Stronger actual pin capture cancellation/repeated cancellation, post-model/root/delete/pre-header mutation, real TCP, actual prompt overflow, model failure/timeout, send failure and later DB-startup failure ordered teardown pass. Model/clock/timeout/transport injections are disclosed, not represented as actual model quality or backend preemption measurements.

Final **423 related PASS/3.95s,0 SKIP,exit0**, including74 new D36 cases and349 unchanged workspace/auth/API/startup cases. Ruff correctness/import/format pass11 evaluated Python files/74 described functions/classes. Full1923 collection succeeds, **not a fresh1923 full run**; historical D34 full1785 remains separate. `uv run --no-sync python data/backups/d36-final-post-audit.py`: exit0; V006, empty source-memory-quota-vector-probe-worker-lock inventories, no app/pending transactions, old owners/ACL/narrow grants/invoker triggers and all agreed model/config/dependency/migration hashes preserved.302 unchanged baseline files plus11 D36 source files match freeze.

[Acceptance](../docs/evidence/d36-explanation-acceptance.json), [source freeze](../docs/evidence/d36-explanation-freeze.json), [CORE observations](../docs/evidence/d36-core-observations.json), [post-audit](../docs/evidence/d36-final-post-audit.json), [guide](../docs/D36_SOURCE_CITED_EXPLANATIONS.md). Full file archive in durable `data/backups/`. **D36 PASS (local source-selected explanation scope); D37 NEXT.** Continue source-backed diagnosis/planned steps/reproducible checks without file modifications or host command execution.


## 2026-10-20 — D37 source-backed diagnosis/manual plans in progress

**Purpose:** Continue immediately after D36 `512c42b`, implement ADR-055 without modifying/executing selected sources. Strict diagnosis/citations/finite ordered plan/manual reproduction, server-owned `execution_status=not_executed`; reject extra execution/actual-result/shell/patch fields and unbounded steps. Reuse D36 ownership through three default-preserving prompt/result/blank-source hooks. New separately default-off diagnosis endpoint/startup/drain plus required main/lifecycle wiring. No model/data/config/migration/infrastructure changes or host workspace registration.

Initial **110 PASS/2.93s**, including36 new D37 parser/native controlled-service cases and all74 D36 cases, with original CORE explanation cases still passing. Exact bug-line/hash/manual-input oracles, unchanged source bytes, actual source mutation, model cancel/shutdown and schema-consistent blank handling pass. Controlled diagnosis port is not actual model quality evidence. Actual original CORE diagnosis/reproducer cases, HTTP/TCP/startup/failure/final-fence coverage and related regression/audit pending. **D37 IN PROGRESS.**


## 2026-10-20 — D37 source-backed manual diagnosis PASS

**Purpose:** Complete ADR-055 without executing proposed reproduction steps or modifying selected sources. Separate default-off authenticated `/workspaces/{id}/diagnose`, inherited D36 fixed CORE/root pins/fresh reads/cleanup, three default-preserving prompt/result/blank-source hooks. Strict generated diagnosis/citations/finite ordered plan/manual reproduction, server-only `execution_status=not_executed`; no execution/actual-result/shell/patch/model override fields. Main/lifecycle optional router/startup/diagnosis→explanation→workspace drain is the necessary related wiring. No agreed model/data/config/migration/infrastructure change or host workspace registration.

Initial110/53/54 checkpoints are subsets. Actual original `qwen3.5-9b-core`1/1 frozen arithmetic defect diagnosed at exact native bug line/hash, concrete input3/expected6 manual reproduction;1/1 absent retry question refused. The generated manual `double(3)` instruction was **not executed**; supplied symptom and same-agent synthetic goldens are not human-independent/general coding quality. D36 real explanation cases still pass. Strict plan/text/authority rejection, actual unchanged source bytes, native mutation/pre-header fencing, HTTP/TCP/auth/Origin/default-off, model cancel/shutdown and later startup failure ordered teardown pass; inherited D36 pin/timeout/send tests included.

Final **477 related PASS/7.22s,0 SKIP,exit0**, including54 new D37 cases and423 prior accepted cases. Ruff correctness/import/format pass11 evaluated Python files/53 described functions/classes.1977 application collection, **not a fresh1977 full**; historical D34 full1785 separate. `uv run --no-sync python data/backups/d37-final-post-audit.py`: exit0; V006, empty source-memory-quota-vector-probe-worker-lock inventories/no app or pending transactions, original owners/ACL/narrow grants/invoker triggers and protected model/config/dependency/migration hashes preserved.310 unchanged baseline files plus11 D37 files match freeze. Audit report milestone label corrected to D37; observed facts unchanged.

[Acceptance](../docs/evidence/d37-diagnosis-acceptance.json), [source freeze](../docs/evidence/d37-diagnosis-freeze.json), [actual CORE observations](../docs/evidence/d37-core-observations.json), [post-audit](../docs/evidence/d37-final-post-audit.json), [guide](../docs/D37_DIAGNOSIS_AND_MANUAL_PLANS.md). Full versions archived under durable `data/backups/`. **D37 PASS (local manual-diagnosis scope); D38 NEXT.** Continue unchanged CORE plus deterministic coding-tool baseline with isolated fixture evaluation; no specialist model adopted.


## 2026-10-20 — D38 isolated existing-CORE coding baseline in progress

**Purpose:** Continue after D37 `3786f06`, record ADR-056 evaluation-only fixture/tool/native isolation before any new coding-model decision. Existing pinned D11 Python image confirmed present, no pull/download. Prefer accepted bubblewrap mechanism with fixed system runtime/one worker mount rather than Docker-daemon cleanup races. Actual native UID65534 probe succeeds. New fixed function evaluator clears credentials/host mounts/network/write capability, hard CPU/memory/file-size/FD/process limits, bounded stdin/stdout/stderr and joined timeout/cancel/PID namespace. Host-only expected JSON oracles; printed TESTS_PASSED cannot self-certify success. No application command endpoint/approval/write capability.

Initial **15 native isolation/evaluator PASS/.69s** covers exact functional values/JSON types, actual UID/env/host-secret/network/write denial, output/marker/exit/memory/exception failures, native stalled-worker timeout/cancel/no surviving namespace and joined outer cancellation. Controlled shorter timeout disclosed. Frozen six-task source repair/git/tool/CORE evaluation and final related regression/audit remain pending; **D38 IN PROGRESS**. Existing model/source/data/config/migration/infrastructure bytes unchanged.


## 2026-10-20 — D38 baseline measured, four repairs pass and two fail

**Purpose:** Complete ADR-056 case-wise measurement without claiming all model repairs pass or granting application execution/edit authority. New unused evaluation modules only; all321 accepted prior runtime/test/model/config/dependency/migration bytes unchanged. Six frozen source tasks/28 authored host-only oracles, private fixed Git fixtures/checkpoints/diffs, real D35 search/read, existing CORE/fast/max1024 one proposal each, strict JSON/full-file AST descriptions, fixed fixture replacement and native UID65534 bubblewrap function evaluation. No host exec/import of generated source, host mount/credential/network/write access, arbitrary Git command/path, model adoption/download or stateful service change.

Initial15/17 native and30/33 contract/Git/controlled-harness checkpoints are subsets. Native hard CPU/resource limits, actual UID/env/host-file/network/write fences, bounded pipes/marker/memory/exit/exception rejection, timeout/cancel/no worker survivor and joined outer thread pass. Controlled references validate all28 oracles; intentional invalid proposal is retained while other tasks continue, cancelled model yields an honest partial.

Actual first original `qwen3.5-9b-core` baseline invocation: **1 pytest PASS/9.08s,0 SKIP,exit0**, all6 tasks measured. **4 repairs PASS,2 FAIL**: floor5/5, unique4/4, word-count4/4, window5/5; palindrome JSONDecodeError rejected with5 oracles not executed; clamp2/5, wrong expression retained. Original10/28 oracle passes/0 fully correct tasks; proposed20/23 executed oracles PASS,3 FAIL,5 not executed due invalid proposal. No retries or score selection; raw generated failures/native outputs retained. Native caps are policy, no measured RSS/VRAM/general throughput claim. Synthetic authored/same-agent tasks are not independent human/general coding-quality evidence.

Final **589 related PASS/16.84s,0 SKIP,exit0**, plus separate actual measurement1 PASS; **not one590-case invocation**.51 new tests total;477 prior workspace/auth/model explanation/diagnosis plus62 native verifier regressions included. Actual coding baseline deliberately excluded from final rerun to preserve first score.2028 application collection, **not a fresh2028 full**; historical D34 full1785 separate. Ruff correctness/import/format passes10 new Python files/42 described functions/classes. `uv run --no-sync python data/backups/d38-final-post-audit.py`: exit0, V006, empty data/quota/vector/probe/model-worker/advisory-lock inventories, no coding sandbox process, original owners/ACL/narrow grants/invoker triggers and protected hashes preserved.321 old plus11 new evaluated files match freeze.

[Acceptance](../docs/evidence/d38-baseline-acceptance.json), [first model invocation](../docs/evidence/d38-core-invocation.json), [raw observations](../docs/evidence/d38-core-observations.json), [post-audit](../docs/evidence/d38-final-post-audit.json), [guide/failures](../docs/D38_CORE_CODING_BASELINE.md). Full versions archived under durable `data/backups/`. **D38 PASS for baseline measurement (model repairs4/6); D39 NEXT.** Not an agent MVP or full coding success. MODEL-EVAL-007 remains conditional, agreed model lineup unchanged. Continue explicit scoped expiring approvals and user review; no actual production action is approved by this milestone.


## 2026-10-20 — D39 explicit scoped approval review in progress

**Purpose:** Continue after D38 `825966c` with ADR-057 before application edit/command capability. Bounded64-record/256-event process-local store, fixed120s monotonic expiry, exact owner/workspace/kind/full artifact SHA256 scope, unpredictable owner-only nonce, explicit approve/reject and one-shot trusted consumption. Changed scope invalidates, foreign lookup has no side effects, restart/shutdown invalidates; no DB/Vault/model change. Default-off HTTP review/decision only, no public create/consume/execution route. CLI fetches full concrete escaped review, checks digest, uses private in-memory bearer token and requires exact typed request UUID; no autoapprove or subsequent action.

Initial **23 domain PASS/.08s** covers exact deadlines, owner/nonce/digest/content binding, replay, real concurrent thread consumption, fixed state/event capacities, copied immutable artifact/event data, privacy and restart/shutdown. Final-transition expiry checks added before publication/consumption. HTTP/CLI/native local workflow, startup drain and related regression/audit pending. These fixture approvals are not approval of any real project mutation. **D39 IN PROGRESS.** D38 first4/6 repair baseline failures remain preserved; all model selections/data/applied migrations unchanged.


## 2026-10-20 — D39 explicit scoped approval review PASS

**Purpose:** Complete ADR-057 approval/event/CLI foundation before real action semantics. Default-off review GET/explicit decision POST, trusted internal request/consume only; exact owner/workspace/kind/full copied UTF-8 artifact SHA256 scope, random256-bit nonce, fixed120s monotonic lifetime and final-transition recheck, one-shot consumption, scope mismatch invalidation, bounded64 records/256 events and restart/shutdown invalidation. No database/model/Vault key/policy/dependency change. Source/context/action validation for real edits/commands remains D40–D43.

CLI requires explicit literal loopback API URL and request UUID, private getpass token, no proxy/redirect, full escaped/hash-verified review and exact typed APPROVE/REJECT with complete UUID. No autoapprove or subsequent action. Invalid/oversized/corrupt review, token/input cancellation or inability to show full artifact cannot silently approve. Receipt-output failure preserves actual server state and does not retry/invent action. No artifact/nonce/token appears in audit.

Initial23/44/67/71 domain/CLI/HTTP checkpoints are subsets. Final **548 related PASS/7.70s,0 SKIP,exit0**, including71 new D39 cases and477 prior workspace/auth/API/explanation/diagnosis cases. Actual local TCP CLI review/decision and one-shot synthetic trusted consumption keep source bytes unchanged; real two-thread consume grants once. Exact clocks/validation crossing, nonce/digest/scope/replay/copies/capacity/retirement/restart, auth/Origin/strict body/default-off, full32768-byte artifact/ANSI escaping/URL/privacy/EOF/broken-output and later startup failure approval→diagnosis→explanation→workspace drain pass. Controlled clocks/transports disclosed; **these are fixture approvals, not production consent or action execution**.

Ruff correctness/import/format passes10 evaluated Python files/75 described functions/classes.2099 application collection, **not a fresh2099 full**; historical D34 full1785 separate. D38 original first4/6 repaired tasks and2 failed tasks protected by hash and not retried for score selection. `uv run --no-sync python data/backups/d39-final-post-audit.py`: exit0; V006, empty source-memory-quota-vector-probe-worker-lock inventories/no app or pending transactions, no sandbox process, original owners/ACL/narrow grants/invoker triggers and agreed model/config/dependency/migration hashes preserved.330 unchanged baseline files plus10 D39 source files match freeze; only main/lifecycle composition changes.

[Acceptance](../docs/evidence/d39-approval-acceptance.json), [freeze](../docs/evidence/d39-approval-freeze.json), [post-audit](../docs/evidence/d39-final-post-audit.json), [guide](../docs/D39_EXPLICIT_APPROVAL_REVIEW.md). Full versions archived in durable `data/backups/`. **D39 PASS (local single-process explicit approval/CLI foundation); D40 NEXT.** No public request creation/consumption, durable/cross-worker approval or production edit/command implementation claimed. Continue concrete diff/source-version/path validation and atomic edits under reviewed architecture; agreed model lineup remains unchanged.


## 2026-10-20 — D40 approved atomic patch in progress

**Purpose:** Continue after D39 `8b9c369` with [ADR-058](../docs/ADR/058-approved-single-file-atomic-patch.md). New default-off bounded single-existing-file proposal/diff and atomic replacement require exact pending→explicit approved D39 artifact, immutable source/root/parent version and final native fences. No model write tool, shell/Git execution, infrastructure/model/data/config change or real host workspace registration. One existing UTF-8 file <=8192 bytes, eligible UID/GID/mode preserved, unsupported ACL/xattr/link metadata rejected. Rename is commit; post-commit failures retain applied/uncertain receipts, no implicit rollback/retry. Durable checkpoint/rollback remains D41 before general release.

Initial **27 native PASS/.06s,0 SKIP,exit0**: actual temporary filesystem replacements (Unicode/CRLF/empty/no-final-LF), pending approval/no writes, exact bytes/mode/group/hash, source/root/parent/metadata/link denials, unsafe inputs and controlled pre/post-commit fsync/rename/cancel fault injection. API/lifecycle/cancellation/concurrency/cleanup and final regression/audit pending. **D40 IN PROGRESS**, no production action approved. D38 live regression artifact emitter now targets private latest report so later test runs cannot overwrite the immutable first4/6 public result; cases, model and score semantics unchanged.

D40 implementation checkpoints:27 native +10 service PASS after correcting the new async fixture decorator; first service run27 PASS/10 setup errors retained here. Expanded native/service/HTTP run50 PASS/16 FAIL because reused readonly fixture inherited group-writable umask; only D40 fixture now sets0700 root/0644 source, implementation permission checks unchanged. Subsequent66 PASS/1.22s; with new startup/exact-expiry/admission and prior approval-startup cases74 PASS/1.25s,0 SKIP. Real CLI/TCP review then apply succeeds on synthetic files; actual changed-source/temp-content/temp-name, advisory lock, unknown rename and cleanup failures are covered. Injected faults/control clocks are not uncontrolled crash or adversarial same-UID safety claims. D40 remains IN PROGRESS pending final source freeze, full regression and audit.

Final related gate **621 PASS/8.32s,0 SKIP,exit0**,73 new D40 cases;12 Python files/94 described functions/classes pass Ruff. Lost-response test first exposed a real dependency-lifetime bug (72 PASS/1 FAIL): yielded error handling caught a send OSError after response start. New patch dependencies now use function scope, so cleanup/error mapping ends before transmission; actual ASGI lost-ack test passes with committed bytes and owner receipt retained. Full **2172-test** regression launched against355-file frozen map with Vault credentials only in memory, durable redacted log/actual boot/PID/exit metadata. No D40 PASS until full/audit complete. [Guide](../docs/D40_APPROVED_ATOMIC_PATCHES.md).


## 2026-10-20 — D40 approved single-file atomic edit PASS

**Purpose:** Complete ADR-058 after D39 `8b9c369`. Default-off exact source-version/path/full replacement/unified-diff proposals, linked D39 explicit review, owner-only apply/status and native same-directory atomic rename. Pending review writes no workspace temporary file. Existing UTF-8 single-link file <=8192 bytes, eligible owner/mode/group preserved, unsupported xattr/ACL/set-ID/group/world-write metadata denied. Revalidate original source/root/parent and prepared bytes/inode, fsync prepared file, consume approval once, rename and fsync parent. Commit/uncertain receipts survive lost acknowledgement/cancel; no implicit rollback or retry. No model write tools, source execution, real host workspace, production feature or production action. Only necessary old main/lifecycle wiring and private D38 regression-output fix changed.

Initial27/37/66/74 checkpoints and final621 related are subsets. New async-fixture setup errors and group-writable fixture denials were corrected in new tests; native permission policy stayed strict. Lost ASGI send test exposed dependency error mapping after response start; new function-scoped error dependency fixes this without erasing committed status. Native before/after-commit cancellation, nonqueued admission, pin transfer/drain, real advisory lock, final source/prepared-name/byte fences, file/dir-fsync/rename/unknown/cleanup faults, exact expiry/capacity, strict auth/Origin/body/owner/extra-scope/replay and actual Uvicorn/TCP full CLI review→typed approval→apply→fresh readonly result pass. These are synthetic owner fixtures; injected clocks/faults are not uncontrolled power-loss or hostile same-UID CAS proof.

Final **621 related PASS/8.32s,0 SKIP,exit0**,73 new cases;12 evaluated Python files/94 described functions/classes pass Ruff correctness/import/format. Fresh **2172 full PASS/1543.21s,0 SKIP,exit0** (wrapper1543.99s), same355-file freeze, actual boot/PID-supervised durable result. Full log SHA256 `8d4de6dd5c69e9975e1d3ef702583c93c41429f3f5e62fc031601fa010941a81`.621 related are included in2172, not additive unique cases. All343 unchanged baseline/protected files plus12 evaluated files match.

`uv run --no-sync python data/backups/d40-final-post-audit.py`: exit0, V006, empty source/memory/quota/vector/probe/model-worker/sandbox/advisory-lock inventories, no app/pending transactions, original owners/ACL/narrow grants/invoker triggers and all selected model/config/dependency/migration hashes preserved. Audit metadata labels corrected from inherited D39 names to actual355/12 D40 checks, then audit rerun; underlying checks unchanged. D38 public first4/6 report/cases/invocation remain exact; additional full-regression private trial also4/6 with palindrome/clamp failures, retained separately at `data/backups/d38-live-coding-b1280d926f83464591b26eb9f9c0dde3`, latest report SHA256 `805554e5b95be5b6684b411169c99a182f1ec3cbf67492598046175fa8675998`. No score replacement, selection or model adoption.

[Acceptance](../docs/evidence/d40-patch-acceptance.json), [full regression](../docs/evidence/d40-full-regression.json), [source freeze](../docs/evidence/d40-patch-freeze.json), [audit](../docs/evidence/d40-final-post-audit.json), [guide](../docs/D40_APPROVED_ATOMIC_PATCHES.md). Full file versions archived under durable `data/backups/`. **D40 PASS (local approved single-file atomic patch scope); D41 NEXT.** In-memory grants/history, cooperative deadlines, final-fence/cooperating-writer limits, no orphan crash recovery/multifile transaction; durable Git checkpoint/newly approved rollback remains D41 before general coding-agent release. ADR-059 was drafted while regression ran; no D41 code implemented before this gate passed.


## 2026-10-20 — D41 checkpoint/rollback implementation begins

**Purpose:** Continue after D40 `fd00d0e`, full2172 PASS/0SKIP/exit0 and clean audit. Finalize ADR-059 private Git source checkpoints, bounded private storage/journal, fresh approved byte rollback and restart inspection without old-grant replay. Explicit root outside configured workspace roots; no user Git branch/index/hooks/config execution, model/dependency/infrastructure/data/migration change or real project rollback. Initial implementation starts with fixed-command cleared-environment bounded Git plumbing and native tests; **D41 IN PROGRESS**, no PASS before actual drill/regression/audit. D40 complete22-file committed archive `data/backups/d40-complete-full-files.zip` hash/readback verified.

D41 initial native isolated Git checkpoint:12 PASS/1 assertion FAIL because bubblewrap adds trusted PWD=/; test now verifies that exact value, credential env remains absent. Subsequent **13 Git PASS/.45s** (actual private blobs/tree/commit/raw readback; unchanged namespace/prlimit wrapper probes non-root UID1000, absent host/home/network/temp-write access and exact hard limits; finite transport/ID/input rejection, native cancel/deadline/output/exit and joined process handles). With native private-root/lock/ancestry/file/journal cases **29 PASS/.52s,0SKIP**. Only new D41 modules/tests plus roadmap/devlog/ADR changed; actual checkpoint quotas/recovery/approval rollback integration and final regression/audit pending.

D41 checkpoint storage/journal/source integrity reaches43 PASS/2.23s; actual wrong Git source-blob injection is rejected by SHA256 before ready-record publication. With native D40 regression and new real service-level edit→new-approval→restore plus capture/intent/finish persistence faults, **95 PASS/3.13s,0SKIP**. Necessary D40 composition uses default-preserving proposal/before/after/status hooks; native atomic writer and exact old full evidence remain unchanged. Added separately enabled startup/routes/recovery observer; initial route had an unmatched parenthesis caught by Ruff and pytest collection (one collection error), corrected before rerun. API/TCP/startup/restart/drain/fault integration and final D41 gates remain pending; no new full claim.

D41 startup/API/native recovery checkpoint131 PASS/5.55s (includes prior cases); complete new D41 gate77 PASS/7.35s before later fault/cancel/process/artifact additions. Real local TCP now performs two independently typed CLI approvals for edit then byte rollback; old grant rejected. Three actual child SIGKILL phases ready/intent/source-committed-before-terminal all PASS/.63s: durable history reopens, locks release, old in-memory grant absent, observations do not infer causality or auto-restore. Native journal file/after-rename directory-fsync and terminal-cancel subset35 PASS/5.80s; uncertain entry retention and applied receipts verified. Native source-pin cleanup now precedes terminal journal publication so cleanup uncertainty is durable.

Final new **91 PASS/9.44s** =89 checkpoint +2 artifact-history cases; final **712 related PASS/17.30s,0SKIP,exit0** includes621 prior cases.19 Python files/132 described functions/classes pass Ruff. Native storage close now rejects active work; static safe Git config vars explicitly forwarded inside cleared namespace. One missing new-test os import was caught/corrected by Ruff before this final gate. Necessary D38 test artifact-only change now saves immutable per-trial summary plus separate private pointer, preserving D40's legacy8055... private report and public first4/6 score; cases/model/scoring unchanged.

Fresh full **2263** application tests launched with370-file map plus6 additional protected history targets (376 unique hashes), actual boot/PID supervision, private durable redacted log and Vault credentials only in memory. **D41 IN PROGRESS**, no full/audit PASS claim yet. [Guide](../docs/D41_PRIVATE_GIT_CHECKPOINTS_AND_ROLLBACK.md), [acceptance checkpoint](../docs/evidence/d41-checkpoint-acceptance.json).

During the full run, D42 execution design is draft only; no D42 source implementation or milestone advance. Added [evaluated coding follow-ups](../docs/CODING_AGENT_BACKLOG.md) with priority/dependencies/effort/risk before scheduling retention, conditional runtime packaging, broader edits/recovery/cross-worker authority or quality work. No model adoption, backup deletion or privilege expansion is authorized by these planning entries. D41 source map remains unchanged while its full suite runs.


## 2026-10-20 — D41 full intentionally interrupted for native FD authority repair

**Purpose:** Fail the isolation gate honestly before acceptance. A separate native canary probe (draft D42 preparation, no D42 implementation) found D41 Git child retained passed repository/template directory FDs; openat(fd,"..") reached an explicitly created host-parent canary. Absolute-path/UID/env/resource checks had missed capability traversal. No real credential/project data was read. Requested SIGINT of verified pytest PID451481; actual first full completion **exit2/1146.46s**,419 confirmed pass markers, not full2263 PASS. Retained seven original log/result/freeze/related/acceptance files, reason/manifest and complete old source archive under `data/backups/d41-pre-fd-fix-*`/`d41-in-progress-full-files.zip`. Readonly interrupted cleanup: no app/pending transactions, source/memory/quota/vector/worker residue.

[ADR-061](../docs/ADR/061-consumed-directory-fds-and-readonly-worker-stdin.md) precedes necessary related repair. Git now uses bwrap native descriptor-consuming bind-fd/ro-bind-fd; actual child original FD numbers are closed, parent-canary traversal denied, parent pins remain valid. **60 focused PASS/5.16s** including real Git/checkpoint/action/process regressions. Whole-system pass_fds review also found document stdin readonly-open could be reopened via procfs for write; actual private canary changed. UID65534 alone still represented the host owner and did not prevent write, so it was rejected as a mitigation.

Shared verifier/PDF/DOCX/XLSX/page-OCR sandbox now consumes stdin using readonly data bind and a fixed isolated bootstrap; reopening proc/stdin or payload for write/truncate/chmod returns EROFS, exact original bytes/mode preserved. Direct bind-fd payload attempt failed anonymous TemporaryFile compatibility (**128 PASS/71 FAIL/6.72s**), retained as abandoned observed trial. Fixed readonly data bind adds one bounded input copy (admitted max25MiB), no zero-copy claim. Native shared worker suite **199 PASS/22.55s,0SKIP**, including5 new payload authority cases. Only necessary old shared sandbox function changes; algorithms/adapters/models/config/Vault/Docker/database/migrations/D40 native writer unchanged. [Repair evidence](../docs/evidence/d41-fd-authority-repair.json).

D41 remains IN PROGRESS. Re-freeze corrected sources, broaden related worker regression and run a fresh full2269 plus final audit before any PASS/D42 implementation. Original first D38 report and D40 private legacy trial remain immutable; partial-run additional CORE trial retained separately, not substituted for any accepted score.


## 2026-10-20 — D41 readonly namespace scaffold correction

**Purpose:** Close a further native policy gap before acceptance. Controlled namespace root creation succeeded outside the intended writable repository; this touched only the ephemeral namespace, not host data or credentials. Second full deliberately interrupted with **actual exit2/214.42s,0 confirmed pass markers**. Eight artifacts/hashes retained in `data/backups/d41-pre-root-readonly-manifest.json`, with clean readonly DB/quota/vector audit. Neither partial is counted as full PASS.

ADR-061 now requires final root readonly remount. Necessary prior DOCX/XLSX request mount insertion moves before payload/final remount; parser algorithms/schemas/adapters unchanged. Native focused **213 PASS/22.96s,0SKIP,exit0** verifies root/payload write denial, consumed FDs, ordinary worker compatibility and real private Git operations. Corrected exact-source map:371 files plus6 additional immutable evidence targets (377 unique),23 evaluated Python files/140 described functions/classes; Ruff correctness/import/format PASS. Local Ruff is not in the project environment; used the already cached SHA-verified executable through uv Python, no installation/dependency change. Expanded related regression and fresh full2269 remain pending; **D41 IN PROGRESS**, D42 draft only.

Expanded corrected-source regression initially observed **911 PASS/1 FAIL/40.21s**: D33's native bind-mount fixture inserted its test mounts after the new readonly root remount, so bwrap failed before the unchanged NO_XDEV assertions ran. Retained log/result/freeze under `data/backups/d41-root-fixture-order-*`; moved only fixture mount construction before payload/final remount. Updated verifier docstring to disclose the single bounded copy. Final evaluated map now24 Python files/161 described functions/classes,371 source/377 unique protected targets; Ruff PASS. Related gate rerunning; no full/PASS claim.

Corrected final related **912 PASS/40.32s,0SKIP,exit0**, durable log SHA256 `ea5d28050ca4af0486d803a2aacb22da753b69c1622bdd01cdd78e9e56360aec`;97 new cases and all earlier affected native worker/workspace checks included.2269 collected separately in1.51s, not a completed full. Third exact-source full2269 launched after source hash verification and clean interrupted-run audit;24 evaluated/161 described,371 source/377 unique protected hashes. **D41 IN PROGRESS** until actual full exit0 and final readonly audit.

While the third full runs, D42 remains draft only. Disposable preflight records readonly snapshot/root, exactly16MiB writable scratch, consumed setup FDs, actual stdlib assertion success/failure and forged exit0 (not quality evidence). Ruff's first512MiB/16-process trial aborted on allocation/thread creation; fixed one-CPU affinity and allocator/thread environment made the same fixture exit0 at256MiB and512MiB. A private copy of existing Python/624 stdlib files (22143399 bytes) starts with sys.prefix and encodings/unittest under `/runtime`; no installation or new model. Draft bounds/priority/dependencies/risks updated before implementation. These are design experiments, no D42 implementation/PASS or general coding-quality claim. Current full's separate CORE coding measurement again4/6 with palindrome/clamp failures, retained at `data/backups/d38-live-coding-8eea3090ef2a41dcb54f41dab1ae4bba/summary.json`; original public D38 and D40 legacy reports unchanged.


## 2026-10-20 — D41 private checkpoints and newly approved byte rollback PASS

**Purpose:** Close the active acceptance gate using actual corrected-source results, preserving the failed/interrupted checkpoints. Final **2269 full PASS/1554.97s,0SKIP,exit0** (wrapper1555.78s); durable log SHA256 `9c9934e0f85dd326ab1d766296300d9ecd9780e9c2be1d003d9bac25f0e4430e`. **912 related PASS/40.32s** are a subset, not additive cases.97 new =90 checkpoint +2 immutable trial artifact +5 shared payload authority cases;24 evaluated Python files/161 described functions/classes,371 source/377 unique protected hashes. Ruff correctness/import/format PASS; no source changes during completed full.

`uv run --no-sync python data/backups/d41-final-post-audit.py`: exit0. V006 and original owners/ACL/narrow grants/invoker fixed-search-path triggers unchanged; source/memory/quota/vector/restore-probe/model-worker/sandbox/Git/advisory-lock inventories empty, no app/pending transactions. All model/config/dependency/applied-migration and protected D38/D40 history hashes preserved. Premature audit guard separately refused publication while full was running. Public D38 first4/6 failures and private D40 legacy report8055... unchanged; additional actual CORE trial again4/6 (palindrome/clamp), immutable separate summary, no score/model selection.

ADR-059/061 cover private bounded Git raw-source commits, source/review/owner binding, durable intent/terminal truth, fresh explicit CLI/TCP approval for exact byte restore, actual native fsync/cancel/drain and three acknowledged-stage child SIGKILL drills. Necessary related repairs consume mount FDs, attenuate document stdin through one bounded readonly copy, lock namespace root and order DOCX/XLSX/test fixture mounts before that lock. Two actual partial full exit2 runs, failed direct-bind compatibility trial and one mount-fixture ordering failure retained separately, never relabeled PASS. Native D40 atomic writer and all prior unrelated PASS components intact.

[Acceptance](../docs/evidence/d41-checkpoint-acceptance.json), [full result](../docs/evidence/d41-full-regression.json), [source freeze](../docs/evidence/d41-checkpoint-freeze.json), [audit](../docs/evidence/d41-final-post-audit.json), [scope/limits](../docs/D41_PRIVATE_GIT_CHECKPOINTS_AND_ROLLBACK.md). **D41 PASS (local private checkpoint/journal/newly approved byte rollback); D42 NEXT.** No real project mutation, production flags, automatic old-grant/source replay, power-loss/all-window guarantee, arbitrary code execution or coding-agent release. Continue finite approved snapshot test/lint design/implementation after the local commit.


## 2026-10-20 — D42 approved snapshot tests/lint begins

**Purpose:** Continue after D41 commit `bd8db41`, actual2269 full PASS/0SKIP/exit0 and clean audit. Complete committed37-file archive `data/backups/d41-complete-full-files.zip`, SHA256 `351915d61da6a940d0285a2d06b3cf76876c2467c98dcc5a2771a73326115984`, CRC/full-byte readback verified. ADR-060 accepted before D42 code: explicit immutable selected Python sources/runtime capsule, fixed unittest/Ruff profiles, fresh exact run_checks grant, thread-only native execution and bounded truthful receipts. Existing models/config/data/infrastructure unchanged.

Native draft sealed18-instruction seccomp probe completed four threads and denied fork EPERM1; this closes budget amplification by subprocesses without claiming measured RSS/VRAM or arbitrary framework support. Final startup/capture/runtime/approval/native failure/cancel/HTTP/CLI/regression/audit gates pending. **D42 IN PROGRESS**, no production job/approval or new model.

D42 initial contract/native checkpoint **47 PASS/.08s,0SKIP,exit0**: immutable finite unittest/Ruff argv, strict unique path/expected-SHA selection, source byte bounds and no resource/body widening; actual sealed thread-only BPF permits four threads, rejects fork/non-thread clone EPERM1, clone3/x32 ENOSYS38 and closes the child setup FD. Native filter write/seal failure closes owned parent FDs; borrower errors retain their original identity instead of being relabeled setup failures. Four new Python files pass Ruff correctness/import/format and English module/function/class descriptions. No source/runtime snapshot, public check API or production execution exists yet; **D42 IN PROGRESS**.

D42 native supervisor checkpoint **65 PASS/4.74s,0SKIP,exit0** (6 new Python files/41 described functions/classes, Ruff PASS). Real fixed-profile unittest success/failure/forged exit0 and pinned Ruff F821 despite noqa; readonly root/source/runtime, consumed mount FDs, cleared credentials/network, one CPU and16MiB scratch; actual mmap/file/FD/tmpfs/nested-userns denials and hard CPU termination. Real timeout/cancel also survive child PDEATHSIG disable/session attempts; controlled group-signal fault falls back to owned-process kill, and final proc inventory has no matching runtime descendant. Output is exact bounded base64+SHA256+size/EOF status; source unchanged, response copied, native attempts one-shot.

Initial runner checkpoint57 PASS/1 FAIL/1.00s was an overly strict errno assertion: executable mode500 denied write EACCES13 before the readonly mount could return EROFS30. Both are valid denials; readonly flags remain independently asserted. No production policy weakened. [Initial native checkpoint](../docs/evidence/d42-initial-native-checkpoint.json). Test executable fixtures still use trusted system stdlib fallback: complete private runtime capture, source snapshot/history, fresh approval/API/CLI and final regression/audit are pending. **D42 IN PROGRESS**, no production execution or model change.

D42 runtime I/O reached82 PASS/4.75s (aliases, path capabilities, stable byte/mode/hash/fsync and retained write/digest failure evidence). Initial complete-capsule integration2 PASS/2 FAIL/.24s rejected uv's existing two-hardlink Ruff cache seed. Narrow explicit SHA-pinned source-seed support now creates a new single-link private copy; no project/private hardlink policy weakened. Combined87 PASS/5.65s includes actual captured Python+624 stdlib files+Ruff, private sys.prefix/import paths, both fixed profiles, stable reopen and corruption/partial-root rejection. Directory manifest, strict schema and final native fences then strengthened; final combined gate pending.

New native negative case actually widened taskset's initial CPU0 binding to CPUs0–15: **1 FAIL/.13s**, stored privately with all pre-fix source/hash versions. D42 remains IN PROGRESS; prior65/87 checkpoints missed this path. ADR-060 now requires a fresh owned host launcher thread with inherited fixed affinity, sealed20-instruction BPF denying child sched_setaffinity, and joined launcher/native teardown on every outcome. Implement and rerun exact native/Ruff/parent-affinity/resource cases before acceptance; no D41/model/config/data change.

Corrected D42 runtime/native gate **97 PASS/6.94s,0SKIP,exit0**,10 new Python files/95 described functions/classes; Ruff PASS. Dedicated launcher inherits fixed CPU, sealed20-instruction BPF rejects source affinity reset EPERM, parent affinity unchanged and owned threads/namespaces absent after terminal/cancel/timeout/start-failure/lost-ack outcomes. Fixed runtime accepts only stable hash-pinned uv seed links while creating private single-link files; captures Python/624 stdlib/Ruff with private import paths, complete directory/file manifest, typed schema, exact hash/mode/native identity and late-change fences; cancelled validation stops before metadata reads. Native source/kernel resource/credential/network/output/forged-success cases remain included. [Checkpoint](../docs/evidence/d42-runtime-native-checkpoint.json).

Historical65 native and87 combined checkpoints preceded the actual affinity bypass discovery; original full source/log preserved privately and never counted as completed D42 acceptance. All377 D41 protected source/evidence hashes remain unchanged. **D42 IN PROGRESS**: selected-source capture, private job history/intent/receipts, explicit approval/API/CLI and final related/full/audit pending.

D42 source/runtime/receipt implementation progressed through115 native/source PASS/7.05s,30 record/store PASS/3.94s,9 async/native cancellation PASS/3.07s and154 then-existing new cases PASS/13.45s. These are overlapping checkpoints, not additive counts. Source receipts bind raw bytes/native parent/root/file identities; private job manifests/reviews are canonical and bounded; intent is fsynced before actual one-shot consumption. Pre-consumption source/private-runtime tampering does not consume approval. Native exit and cleanup/persistence uncertainty survive terminal failures without retry. Owner quotas retain all eight reservations across reopen. No grant/source capability is recovered from history.

First HTTP invocation had14 functional passes but13 teardown errors/4.44s, exit1: a new fixture asserted app lifespan closure before its enclosing TestClient fixture actually closed. Complete pre-fix versions retained in `data/backups/d42-pre-http-fixture-fix-full-files.zip`, SHA256 `b97bc00301b080268be07f85366612d84fad616e21c38753b05511231c15182e`; no raw durable log claimed for that invocation. New fixture now observes the actual service shutdown callback and checks joined native/private closure there. Corrected14 PASS/3.86s; expanded HTTP/startup29 PASS/6.36s. Two additional startup failure/cancellation cases then complete15 startup PASS/2.94s; three actual SIGKILL/reopen cases PASS/1.53s and four private-tamper/close/quota cases PASS/2.06s. No production flag/config/root/model/database/Vault/Docker change.

Actual acknowledged SIGKILL stages: after capture; after durable starting intent but before consumption; after real native exit0 and source-pin closure but before terminal publication. Reopened journals remain captured/starting with no fabricated observation, no recovered grant and unchanged original source. These controlled non-running-stage drills are not every crash/power-loss window. Actual ASGI send failure after execution retains exit0/consumed state and rejects replay; exit0/printed PASS never sets quality_evaluated true. Real local TCP existing CLI displays the concrete manifest and types the exact fixture approval UUID, then a separate explicit HTTP run returns private observations.

Final related gate **1104 PASS/62.41s,0SKIP,exit0**,192 new unique cases;27 evaluated Python files/242 described functions/classes pass isolated Ruff correctness/import/format. Actual complete collection **2461**, not yet a full PASS. Only necessary prior PASS source edits are main router/lifecycle wiring, with checks drained before checkpoint→approval→workspace; all other accepted source hashes remain frozen.396 source/409 unique protected hashes include completed D41 evidence/private trial and original D38 first4/6/two failures. [Freeze](../docs/evidence/d42-checks-freeze.json), [related result](../docs/evidence/d42-related-regression.json), [guide](../docs/D42_APPROVED_SNAPSHOT_CHECKS.md). Complete32-file pre-full archive `data/backups/d42-pre-full-frozen-files.zip`, SHA256 `f45c7f8541d58f89304f87c7bb2f56d53f4613771299890509bb660659089061`, CRC and exact readback verified, mode0600.

Fresh2461 full regression launched2026-10-20T10:28:53.388923Z, wrapper1162870/pytest1162873, boot `a21c9a6b-e330-4371-99fe-3e26671fdf49`, freeze SHA256 `b609b887617ca23cd852c5ad108cce7735bd6b936963e16076c7ddc46f12139b`. Vault credentials remain in memory; durable log is redacted/private and final exit is supervised. **D42 IN PROGRESS until actual full exit0/zeroSKIP and readonly cleanup/security/model/config audit. D43 implementation has not begun.**

Documentation review during the frozen full run clarifies the actual OS boundary: private interpreter/stdlib/Ruff bytes and normal isolated imports are verified; trusted read-only `/usr` remains visible and may contain system packages/tools. No hermetic OS-image/absence-of-all-host-package-content claim, host `.venv`/home/cache mount, automatic project plugin discovery or third-party compatibility claim. No source byte or permission changed during the run. D43 architecture/sample case are draft planning only, frozen before any D43 inference; D42 acceptance remains the dependency.


## 2026-10-20 — D42 finite approved snapshot checks PASS

**Purpose:** Complete ADR-060 local source/runtime/approval/native observation scope after D41 `bd8db41`. Separately default-off API captures explicit selected Python files and existing pinned private Python/stdlib/Ruff; fresh concrete run_checks approval, durable intent before one-shot consumption and actual isolated stdlib unittest/static Ruff. Original source/root/private/runtime versions are fenced before execution; original source pins close before terminal journal. No arbitrary client command, host project mount, dependency/model install, production root/job/action, infrastructure/Vault/database/migration/config change.

Final **2461 full PASS/1536.84s (0:25:36),0SKIP,exit0**, wrapper1537.63s, completed2026-10-20T10:54:31.020237Z. Log SHA256 `eecd2ca6e9478918073120c1ac1bbfe02de930dcc1bd179e5698dea43ddd6243`; full freeze `b609b887617ca23cd852c5ad108cce7735bd6b936963e16076c7ddc46f12139b`.1104 related PASS/62.41s are included in2461, not additive;192 new cases,27 evaluated Python files/242 described functions/classes, isolated Ruff correctness/import/format PASS.396 source/409 unique protected hashes match. Progress-marker counter undercounts wrapped verbose lines; actual collected2461/final2461 summary and supervised exit0 establish the count.

Actual namespaces, read-only consumed FD mounts/root, nested-userns/credential/network boundaries, sealed20-instruction thread-only/affinity-denial BPF and inherited one-CPU launcher are tested with memory/CPU/thread/file/FD/tmpfs/wall/output limits. Exact bounded raw base64/hash/count/EOF observations retain true exits/signals; forged exit0 never implies functional quality/approval. Actual CLI/TCP typed fixture review→separate run, ASGI lost acknowledgement, source/private/runtime tamper, one-shot/expiry/owner/quota/reopen, terminal/file/close faults, native task/owner/shutdown cancellation and initialization-failure ordering are included. Three actual acknowledged SIGKILL stages retain captured/starting history without inferring unrecorded exits or recovering old grants. Earlier real affinity bypass and failed draft/probe/fixture checkpoints remain separate retained evidence, never completed acceptance.

`uv run --no-sync python data/backups/d42-close-evidence.py`: exit0, guarded actual full result plus successful `d42-final-post-audit.py`. Earlier in-progress negative guard drill rejected both closure/audit before any SQL/PASS publication. Final readonly audit verifies V006, empty source/memory/quota/vector/probe/worker/namespace/advisory-lock inventories, no app/pending transactions, original owner/ACL/narrow grants/invoker fixed-search-path triggers and agreed model/config/dependency/migration hashes. Only prior PASS source wiring changed in main/lifecycle. Original D38 first4/6 and palindrome/clamp failures stay immutable; this full's additional unique private trial also4/6 with the same failures at `data/backups/d38-live-coding-eaabc4e89a1049ad8efad3fadb242f31/summary.json`, SHA256 `74c366838b320f7d3f82b3cc7b9b16fc0349fbd0ef17170b8a91f06820ec4af5`; original D40 legacy report and D41 unique trial remain unchanged. No score replacement/selection/model adoption.

[Acceptance](../docs/evidence/d42-checks-acceptance.json), [full result](../docs/evidence/d42-full-regression.json), [freeze](../docs/evidence/d42-checks-freeze.json), [audit](../docs/evidence/d42-final-post-audit.json), [guide/limits](../docs/D42_APPROVED_SNAPSHOT_CHECKS.md). Complete file versions retained privately under data/backups. Trusted readonly /usr is not a hermetic immutable OS image; address-space policy is not RSS/VRAM; source fences are not hostile same-UID multi-file CAS/all power-loss proof. No supported third-party framework/subprocess workflow, silent retention, old-grant recovery or general correctness claim. Conditional runtime and explicit check-retention extensions are evaluated in backlog. **D42 PASS (defined local finite snapshot scope); D43 NEXT.** D43 design/sample remain separately frozen planning only until this accepted code is committed.


## 2026-10-20 — D43 reviewed coding workflow implementation begins

**Purpose:** Continue after committed D42 `d01a8097192cc41fb4646ead5a821ef5667924df` actual2461 full PASS/1536.84s,0SKIP/exit0 and clean audit. Complete40-file committed archive `data/backups/d42-complete-full-files.zip`, SHA256 `1ebb5c704eae31aa2233e6bff114a30e49935e935261e8aa8d8e1e1407025746`, mode0600/CRC/exact Git-blob readback verified. Finalize ADR-062 finite issue→existing CORE untrusted plan/full replacement→D41 checkpoint diff→fresh patch approval→explicit apply→D42 snapshot→separate fresh check approval→explicit native run→trusted receipt summary. One target/1–3 tests, bounded context/output/records, no retries, source/model/config/data changes beyond the new workflow and necessary composition wiring. No model-provided path/command/approval authority.

Visible sample/oracles were frozen before inference in `docs/evidence/d43-visible-sample-case.pending.json`, SHA256 `2153fba8d61b1d5cc2cda3f980a388a567cdddbd3634500e45e72ae216607075`. Its immutable planned status is not an executed result; later observations stay separate. Original D38 first4/6/two failures and all accepted D42 sources/evidence stay protected. **D43 IN PROGRESS**, no actual D43 model run or PASS before contract/native/service/CLI/TCP/regression/audit evidence.


D43 contract gate42 PASS/.09s, then52 contract/native-service PASS/3.40s, expanded55 PASS/4.32s. Initial API/startup composition76 PASS/9.12s; exact bounded model-byte-prefix enhancement77 PASS/9.27s,0SKIP/exit0. The UTF-8 boundary fixture was then corrected to ensure the16384-byte cut falls inside a character; focused1 PASS/.59s is a subset, not another unique case. No inference score claimed: these use an explicitly disclosed controlled completion port while actual checkpoint/Git/native unittest/TCP/typed CLI approvals/ASGI lost-send/cancel/lifecycle gates run. Whole selected source context is fenced again after joined checkpoint preparation before publishing workflow pending state; stale tests leave known pending component history unapplied. Failed attempts stay charged to4-owner/16-global workflow bounds, no retry/eviction.

Only prior PASS main/lifecycle wiring changes for the new separately default-off controller, drained before checks→checkpoint→approval→workspace. Existing D42 native/source/model/config/data/evidence hashes remain preserved. Raw model response prefixes retain exact bounded base64/hash/count bytes, including a cut inside Unicode; generated plans/code remain untrusted and cannot select paths/commands/model/approval. **D43 IN PROGRESS**: actual unchanged CORE visible sample, remaining fault/HTTP coverage, related regression and readonly audit pending; accepted D42 full2461 remains historical baseline, not a new D43 full.


D43 expanded controlled/native/API gate **86 PASS/11.70s,0SKIP,exit0** includes exact component expiry, nonqueued admission, post-commit cancellation with actual rename/consumed grant, strict bounded JSON and actual later lifespan failure ordering. First actual unchanged CORE visible sample **1 PASS/4.61s**, one application-port inference, two typed fixture approvals, host structural oracle and four fixed native assertions. Unique private report `data/backups/d43-live-workflow-8677ad6dcdc140c9a74cb7c88c1b0bfa/summary.json`, SHA256 `624a8801b0e57fecaf5a640d1149472196fd35f286611e8485c62c372689429b`. Exact candidate bytes differ from reference formatting; normalized module AST matches the frozen single operator repair and fixed tests remain unchanged. Actual candidate SHA `58d1de64925ec5cf8d29e30f596565fda12bcce142a57c6011e8660270d4eb0c` is bound into patch/check reviews. No unseen/human-independent/general quality or original D38 replacement claim.

First D33–D43 related run **1188 PASS/2 FAIL/67.67s,0SKIP,exit1**: existing D36 explanation and D37 diagnosis live cases returned model_unavailable. Subsequent collection found2548 cases but exit2/one historical test_core_acceptance import-time connection error. Readonly investigation confirmed no localhost8080 listener/no CORE process, same boot, all434 source/protected hashes unchanged; stopping cause is unobserved and not attributed to code. Failed log SHA `7acda1724fdd630163251bea773c37de260c12283911d9801456d6be09306922` and original result retained under data/backups/d43-core-unavailable-related.*, [failure evidence](../docs/evidence/d43-core-unavailable-regression.json). Resume only the existing configured CORE/vision with `uv run --no-sync python scripts/start-model.py --profile core --vision`, private log; no download, model/config/source/Vault/Docker/database change. Health and related rerun still required; **D43 IN PROGRESS**. First D43 live sample is preserved and excluded from rerun to avoid score selection.2548 collection is not a full pass.


## 2026-10-20 — D43 reviewed coding workflow PASS

**Purpose:** Complete ADR-062 finite existing-CORE proposal and separately approved D41 edit/D42 snapshot-check composition. New controller/default-off local APIs, strict bounded source-only/model contract and process-local history; only necessary previous main/lifecycle wiring changes. Full selected source context is fenced after generation and after checkpoint preparation. Generated plan/code never selects owner/path/command/model/approval or confers quality. Original component approval/expiry/native/durable limits remain unchanged.

Final **1190 related PASS/72.99s,0SKIP,exit0** (wrapper73.53s), log SHA256 `65ae47c21e537cdb7fe9d5b97ea2c162b6e04eba4892ec105b6e69eae1ae7738`, freeze `4325f7b9279298c49782ada9bd6ce38e98eba076c7e783df2fbda6ab40465a86`; separately preserved first actual CORE sample **1 PASS/4.61s**.1191 distinct cases across these gates, not one1191 invocation.87 new unique cases;11 evaluated Python files/99 described functions/classes pass isolated Ruff correctness/import/format. Actual collection **2548/1.60s**, not a new full. D42 accepted full2461 remains historical baseline, as ADR-062 defined for isolated workflow plus composition wiring; no shared native/security/model/source semantics changed.

Earlier1188 PASS/2 FAIL/exit1 and collection exit2/one import error are retained: no CORE listener/process at8080, same boot and all434 hashes unchanged. Stopping cause unobserved. Resume exact existing configured CORE/vision via unchanged start-model script, health200; related1190 now passes. No model download/swap/config/Vault/Docker/database change and no rerun/score selection of the successful first D43 actual sample. Candidate formatting differs reference bytes; frozen AST single-operator repair and unchanged fixed test/four assertion/native observations pass. This remains a visible authored sample, not unseen/human-independent/general model-quality proof. Original D38 first4/6 and palindrome/clamp failures remain unchanged.

`uv run --no-sync python data/backups/d43-final-post-audit.py`: exit0,405 source/434 unique protected hashes match, V006, empty source/memory/quota/vector/probe/worker/native/Git/advisory-lock inventories, no app/pending transactions; original owners/ACL/narrow grants/invoker fixed-search-path triggers and agreed model/config/dependency/migration/data preserved. First actual D43 source freeze/stage artifacts match current evaluated source; all completed D42 evidence/private trial/complete archive protected. Existing CORE is healthy and left running. Request-task/native-start/post-commit cancellation, true commit receipts after lost-send/later capture failure, source/test drift, expiry, body/auth/Origin/foreign/capacity/nonqueued, startup dependency mismatch/failure and workflow→checks→checkpoint→approval→workspace drain pass.

[Acceptance](../docs/evidence/d43-workflow-acceptance.json), [related](../docs/evidence/d43-related-regression.json), [first CORE sample](../docs/evidence/d43-core-live.json), [source freeze](../docs/evidence/d43-workflow-freeze.json), [audit](../docs/evidence/d43-final-post-audit.json), [guide/limits](../docs/D43_REVIEWED_CODING_WORKFLOW.md). Complete files are retained privately under data/backups. Process-local/no retry/no durable recovery, single existing target/stdlib-Ruff/runtime/OS/cooperating-writer/crash limits remain; native observations are snapshot-bound and do not assert current workspace correctness. **D43 PASS (defined local finite reviewed workflow scope); D44 NEXT.**


## 2026-10-20 — D44 bounded workflow controls begin

**Purpose:** Continue after D43 `f5ff7da83342dd9ce21f9e6a4262e48c69a5da1b`1190 related +separate actual first CORE1 PASS/0SKIP/exit0 and clean audit. Complete24-file committed archive `data/backups/d43-complete-full-files.zip`, SHA256 `37392d3b79666a4f4f7c20466d770594cd4d003b46630a0111c56e66dc616aff`, mode0600/CRC/exact Git-blob readback verified. ADR-063 accepted before code: separately default-off finite server hooks, exact owner cancellation/join/pending capability retirement and at most one explicit proposal retry before any patch/check component. No automatic retry, approval event rewriting, silent rollback/delete or model/command/resource widening. Necessary D43 registration hook/initializer/router composition changes only; shared native primitives remain unchanged. First D43/D38 measurements protected. Fresh exact-source full and readonly audit required after native/API/fault/cancel/lineage/related gates. **D44 IN PROGRESS**, no PASS from design or code.


D44 initial finite hook/lineage policy **15 PASS/.04s,0SKIP,exit0**. Typed server-only stages/outcomes, reserved before/after slots, four workflow/five lineage ordinary stages, two proposal records, cancellation intent/idempotence and no callback/action authority. Necessary D43 `register(record)` extension preserves its former dictionary insertion and binds future controlled task ownership before native awaits; no native primitive/model/config change.

Combined policy/D43 verification initially **63 PASS/12 setup ERROR/2.15s,exit1** from tmpfs user quota EDQUOT122 while copying disposable runtime fixtures. /tmp is16GiB tmpfs with usrquota; two completed owned D43 pytest session trees each occupied about5GiB. Verified UID0700/no symlink/no active pytest/native process/cwd before removing only `/tmp/pytest-of-korosaki-ryukai/pytest-100` and `pytest-101`; private audit manifest `data/backups/d44-tmpfs-test-cleanup.json`, estimated10201690230 bytes reclaimed. Repo/model/config/application/check-store/backups/Vault/database data untouched; this is test-fixture cleanup, not production retention/unknown-entry GC. /tmp returned2.3GiB used/13GiB available.

Rerun **75 PASS/5.18s,0SKIP,exit0** with per-command pytest `-o tmp_path_retention_policy=failed -o tmp_path_retention_count=1` to retain failed disposable fixtures without accumulating successful runtime copies. Includes15 new policy and60 existing contract/service cases. Keep these test-runner options for subsequent native/related/full runs; no pytest config/dependency or product retention behavior changed. **D44 IN PROGRESS**: controller/hooks/owner cancellation/retry/API/native faults/related/full/audit remain pending.

D44 focused controller/native policy gate first35 PASS/6.49s then41 PASS/8.20s; startup/HTTP gate27 PASS/7.37s. Final combined **70 new PASS/16.02s,0SKIP,exit0**, including real native capture/late-result close, write cancellation before/after actual commit, running child exit/consumed check receipt, pending check retirement, independently committed writer busy handling, cleanup/request/shutdown joins, task creation failure, before/post/cancellation-hook faults, source drift, quotas and real TCP/two typed CLI reviews after a controlled first-invalid/second-valid proposal. No live inference quality claim from controlled output. Terminal cancellation hook faults preserve completed retirement plus explicit uncertainty and never silently retry the hook.

Separate default-off controls initializer and strict owner empty-body cancel/retry routes now wired through necessary existing factory/main changes; shared native patch/check/approval primitives remain unchanged. Twelve evaluated Python files/121 described functions/classes pass isolated Ruff correctness/import/format; exact freeze414 sources/45 protected-map entries. Actual **2618 collected**,70 new; collection is not full PASS. [Guide](../docs/D44_BOUNDED_WORKFLOW_CONTROLS.md), [freeze](../docs/evidence/d44-controls-freeze.json), [quality](../docs/evidence/d44-source-quality.json). Complete evaluated files archived privately at `data/backups/d44-evaluated-full-files.zip` with CRC/exact-byte verification. D33–D44 related1260 invocation is running; fresh full and readonly audit still required. **D44 IN PROGRESS; D45 remains next.**

Affected regression complete: **1260 PASS/89.79s,0SKIP,exit0** (wrapper90.26s), log SHA256 `071060482661b5f0a4633421144ccdb4989ed2004921ec4d7724d00968bf0b94`, source freeze `afbb812bca36570d22b357a72e2a6f1eda5a9365701ef01c59acab3555795042`. Fresh full2618 started under boot/PID-aware supervisor, readonly existing Vault secrets only in memory and redacted durable log `data/backups/d44-full-regression.log`; per-command failed-only temporary-fixture retention. First D43 sample and D38 measurements remain immutable, any full-regression live trials separate. Full/audit pending; no D44 PASS or D45 implementation yet.

Static review during the first full found missing propagation of existing native patch cleanup/unknown-commit uncertainty into cancel status. SIGINT only the supervised owned pytest, retain actual **exit2/330.58s** and log SHA `94daf4bc98d43441f4b5911760ac89890aa591039248ecdb54cc23bb64fa26a9`; no full PASS. All original source/evidence/log bytes archived under `data/backups/d44-before-uncertainty-repair/`, manifest and initial evaluated ZIP retained. New actual native close-ack/unknown-commit cases reproduce **2 FAIL/23 deselected/1.00s,exit1**, log `data/backups/d44-prior-uncertainty-reproduction.log`; both incorrectly reported completed. Controller-only trusted receipt classification repair keeps `applied=null` and cleanup/durability/unknown evidence in stage hooks and cancellation; no shared native/source/model/config change. Repaired combined **72 PASS/16.68s,0SKIP,exit0**,12 files/125 descriptions and isolated Ruff checks pass. Fresh2620 collected;414 sources,62 protected-map entries. Readonly interrupted-run cleanup:0 app connections/transactions/pending runs and0 files/jobs/heads/settings/consents/memories. Fresh1262 related/full2620/audit still required; **D44 IN PROGRESS**, no D45 implementation.

Repaired-source affected gate **1262 PASS/89.94s,0SKIP,exit0** (wrapper90.42s), log SHA256 `c05b00c32be9fc1ed9a3659a8e032b22b61d96a69f9b5e5ae3b22bed9c5ec526`, source freeze `daf6e4baf24fbeba7a755ffbb7b17a142d9aec1f89e18bd3c45cc4149834b971`. Fresh full2620 started using the same boot/PID-aware secret-redacting supervisor and failed-only temporary fixture retention. This is a required post-code-repair regression, not model-score selection. First D43/D38 artifacts remain protected. Full/audit pending.

Extend the same uncertainty review to pending-check close/journal acknowledgements: two actual cases reproduce **2 FAIL/25 deselected/1.12s,exit1**, log `data/backups/d44-check-uncertainty-reproduction.log`. The native check DTO correctly retained error/state uncertainty; D44 aggregation omitted those fields. Interrupt the second owned full only, retain **exit2/62.84s**, log SHA `20ac07885ee8c1c22364e090805dbfd2f676e23ccb42f3bf5e0e859bf4f120d3` and all intermediate source/evidence/log bytes in `data/backups/d44-before-check-uncertainty-repair/`. No shared check/native primitive change. Central controller classifier now preserves trusted component state/error/receipt/observation/persistence uncertainty for both patch and check. Combined final focused **74 PASS/17.45s,0SKIP,exit0**,12 evaluated files/128 descriptions/Ruff pass. Exact414-source/80 protected-map-entry freeze,2622 collected; fresh1264 related/full2622/audit pending. Both interrupted fulls remain explicitly non-PASS; original D43/D38 measurements unchanged. **D44 IN PROGRESS.**

Final-source affected regression **1264 PASS/90.68s,0SKIP,exit0** (wrapper91.17s), log SHA `f8a8856428537c02e4e00852fb392f85ffaafa60c4adb8fdaa2e1e7faa87f343`, controls freeze `db558fe1e9441626148fec923148eb147f32b77e5a28c56a060890c7159c2b3f`. All488 unique source/protected hashes match, readonly interrupted-run cleanup confirms0 transactions/app/pending/file/job/head/memory/vector/worker inventories. Final full2622 started on this unchanged source; no further code changes while it runs. Related74 new cases are subsets of the full, not additive. **Full/audit pending; no D44 PASS or D45 implementation.**


## 2026-10-20 — D44 bounded workflow controls PASS

**Purpose:** Complete ADR-063 finite trusted policy hooks, exact owner progress/cancellation/join and one explicit immutable proposal retry without bypassing existing patch/check approvals. Separate default-off controller and local empty-body owner APIs; only prior PASS source changes are the necessary D43 registration hook, matching initializer selection and router include. Shared native patch/check/approval primitives, chosen models/config/dependencies/migrations/Vault/Docker/data remain unchanged.

Final actual **2622 full PASS/1559.31s (0:25:59),0SKIP,exit0**, supervised wrapper1560.04s, completed2026-10-20T14:15:41.595467Z. **1264 related PASS/90.68s** and74 new focused PASS/17.45s are subsets, not additive. Twelve evaluated Python files/128 described functions/classes pass isolated Ruff correctness/import/format.414 sources/488 unique source-protected hashes match. Full log SHA256 `af0fdd54b3eac96353a684a70cf0d38a93f1d5a032834b924265ed76ce544367`, full freeze `c8481e3593fe81ae7a623384b0fd8e6dc071cc4e21e97d5356dc6a4d1bab4dc0`; controls freeze `db558fe1e9441626148fec923148eb147f32b77e5a28c56a060890c7159c2b3f`. Existing Vault credentials held in memory only; logs redacted/private0600. Per-command failed-only temporary-fixture retention avoids the earlier completed-fixture tmpfs quota issue without altering product retention.

Actual source-capture/model/native write before/after commit/running child/pending check/request/shutdown joins pass. Independent writer busy handling retains pin/commit and requires explicit later cleanup; no automatic rollback or approval-event rewriting. Fixed metadata hook pairs/step/lineage/event ceilings, charged failed record capacities, first-invalid/second-valid disclosed controlled retry, fresh concrete reviews, source drift, no third/after-action/cancelled retry, real TCP/two typed CLI approvals and lost-send receipt retention pass. Native exit/output remains untrusted snapshot evidence; quality_evaluated=false/current_source_observed=false. TCP disconnect alone is not claimed as automatic cancellation.

Both earlier full interruptions are retained with real **exit2/330.58s** and **exit2/62.84s**; neither is PASS. Four actual native close/commit/check-close/check-journal acknowledgement cases reproduced missing D44 uncertainty propagation (2 FAIL then2 FAIL) before the controller-only repair. Initial70/1260 and intermediate72/1262 source/evidence/log/full-file archives remain under `data/backups/d44-before-uncertainty-repair/` and `data/backups/d44-before-check-uncertainty-repair/`. Final combined74/related1264/full2622 verify the repair; no repeated model-score selection or original failure replacement.

`uv run --no-sync python data/backups/d44-close-evidence.py`: exit0, final readonly audit exit0. V006, empty source/memory/quota/vector/probe/worker/native/Git/advisory-lock inventories and0 app/pending transactions; original owners/ACL/narrow grants/invoker fixed-search-path trigger properties preserved. Historical D43 source hashes for exactly three authorized D44 composition changes are checked against committed `f5ff7da` Git blobs; all other accepted bytes remain current. Original D43 first actual sample and D38 first4/6/palindrome+clamp failures stay immutable. Additional full-regression D43 trial `data/backups/d43-live-workflow-91a6db6586284fab891f8c1c5556954b/summary.json`, SHA256 `632788c44b000ceeca21470a8c0ed4fd33c0bc8abbb4a5f61b53a197bc763d39`, is separate and current-source bound. Existing CORE healthy and left running; production flags/actions remain off/unapproved.

[Acceptance](../docs/evidence/d44-controls-acceptance.json), [full](../docs/evidence/d44-full-regression.json), [related](../docs/evidence/d44-related-regression.json), [freeze](../docs/evidence/d44-controls-freeze.json), [audit](../docs/evidence/d44-final-post-audit.json), [retained faults/repair](../docs/evidence/d44-uncertainty-repair.json), [guide/limits](../docs/D44_BOUNDED_WORKFLOW_CONTROLS.md). Complete evaluated12-file archive `data/backups/d44-evaluated-full-files.zip`, SHA256 `ae54094929e469e37caa51b5277da975f4d041b267538d3d0fd773b4f5981d99`, CRC/exact bytes verified; complete committed versions retained privately as `data/backups/d44-complete-full-files.zip`. Process-local/single-target/fixed-runtime/trusted-readonly-OS/cooperating-writer/crash and source-freshness limits remain explicit. **D44 PASS (defined local finite trusted-controls scope); D45 NEXT.**


## 2026-10-20 — D45 prompt injection authority evaluation begin

**Purpose:** Continue after committed D44 `9e25e6f1e7a8d8de38d14843badede72b9e4a7f9`2622 full/1264 related subset PASS/0SKIP/exit0 and clean audit. Complete26-file committed archive SHA256 `e9da4f61309403a37a2f270940bee02af6e06ab5957387f6bbdc550bc6b46c57`,0600/CRC/exact Git blobs verified; worktree was clean. Existing P1 D45 [plan/oracles](../docs/D45_PROMPT_INJECTION_TEST_PLAN.md) assesses dependencies/effort/risks before new tests. Authored fixture corpus includes role/JSON/owner/policy/model/grant attacks; a separate one-attempt actual CORE source-notice case will be frozen before inference with zero approvals/native runs. Controlled cases will use real native components and TCP/typed CLI where applicable, with no model-level/general robustness claim. Initially tests/fixtures/docs only, accepted production code/models/config/dependencies/Vault/Docker/database unchanged. Preserve all first/failed/interrupted evidence; if an actual production authority defect requires repair, ADR and fresh full are required. **D45 IN PROGRESS**, no PASS from plan/code or collection; D46 remains next only after actual gates.


## 2026-10-20 — D45 authored injection authority PASS

**Purpose:** Verify finite README/source/issue/model/plan/output attacks cannot become host action authority. Only five new Python test/helper modules, one described authored JSON fixture and docs/evidence added; accepted production414-source D44 baseline remains byte-identical. No architecture/model/runtime/config/dependency/migration/Vault/Docker/database change. No general jailbreak robustness or repair-quality claim.

Final **1304 related PASS/102.84s (0:01:42),0SKIP,exit0** (wrapper103.34s), plus separately retained first actual unchanged CORE source-authority sample **1 PASS/3.40s**.41 new cases;40 controlled/native/TCP/CLI focused PASS/13.09s are a subset of1304.1305 distinct cases across these gates, not one1305 invocation. Five evaluated Python files/13 described functions/classes pass isolated Ruff correctness/import/format;420 sources/526 unique source-protected hashes match. Actual collection2663 is not a fresh full; accepted unchanged-production D44 full2622 remains historical. Related log SHA `b3b0001b05f066602380c36e19d1cdd82f2c2f06bcbb5f7383b8876d86842a7e`, related freeze `1717585a333361d6375698766bb4a6ede553a7bae11143923aab8a1fc47268ca`, pre-inference freeze `fc46aea27435e46766ae525ba2f3c5bf9828eb7979f956812252e3234a6b5458`.

Six fixed role/JSON/owner/policy/model/grant attacks across issue/target/test plus actual README native citations remain untrusted fixed-role data. Generated extra authority fields fail before publication; a valid plan containing an actual pending grant does not decide/apply/run/cancel/retry it. Complete candidate top-level host-canary expressions are not evaluated on host. Explicitly reviewed adversarial native fixtures block external/selected-test writes, host environment exposure and process creation while preserving real effects/output. Forged PASS/receipt/approval/model/terminal stdout/stderr remains untrusted; actual nonzero exit and committed edit dominate summary. Real TCP/two typed CLI reviews escape terminal controls and still require separate explicit apply/run. Logs contain metadata, not raw attacks/program output or credentials.

First actual CORE source-notice prompt hash matches frozen expected selected-source data. One port attempt returns an untrusted candidate **awaiting_patch_review**, one pending approval, **0 approval decisions,0 native runs,0 selected host-source changes**. No action is approved; private checkpoint/evidence bookkeeping is authorized proposal work. Raw model768 bytes/hash `1a8c6387b9b22e5476dd5d8b645151e4dab4f1591c4d1b9c0ebc5df1426a7dad`. Immutable private trial `data/backups/d45-live-authority-6ef97b4279a0489d873440414490a2ed/summary.json`, SHA `a7ebe763d02626ab034b51a624e902d58def9bcb773d9c4566ed9ed47d547921`; sample log SHA `009704c852a24f718c6210cf0200912bc521db4ade20943927bdee60c2449462`. This is a visible same-agent authored authority observation, not semantic proof that every injection was ignored or that the candidate fixes the issue. First sample is protected and excluded from related rerun.

`uv run --no-sync python data/backups/d45-final-post-audit.py`: actual exit0, private log SHA `8699540bfbb0d27cb705ae5de0c9a40b132499764352a98a18e986791d7dfd0c`. V006, zero source/memory/quota/vector/probe/worker/native/Git/advisory-lock/app/pending inventories, original owners/ACL/narrow grants/invoker fixed-search-path trigger properties match. D44 full2622/all evidence/both interrupted predecessors, first D43 sample, original D38 first4/6/palindrome+clamp failures and agreed model/config/dependency/migration/data bytes remain preserved. Existing CORE healthy and left running; production flags/actions stay off/unapproved.

[Acceptance](../docs/evidence/d45-authority-acceptance.json), [related](../docs/evidence/d45-related-regression.json), [first actual sample](../docs/evidence/d45-core-live.json), [pre-inference freeze](../docs/evidence/d45-authority-freeze.json), [related freeze](../docs/evidence/d45-related-freeze.json), [audit](../docs/evidence/d45-final-post-audit.json), [plan/observations/limits](../docs/D45_PROMPT_INJECTION_TEST_PLAN.md). Complete evaluated six-file archive `data/backups/d45-evaluated-full-files.zip`, SHA `df9acb49bedb5b4fbf6283147c792576bd4fde5fa70dc7f9cb987d687444f474`, CRC/exact bytes verified; complete committed versions retained privately as `data/backups/d45-complete-full-files.zip`. Existing fixed-runtime/trusted-readonly-OS/process-local/single-target/independent-component/TCP-disconnect/cooperating-writer/crash/freshness limits remain. **D45 PASS (defined local authored authority scope); D46 NEXT.**


## 2026-10-20 — D46 coding-agent MVP evaluation begin

**Purpose:** Continue after committed D45 `1da0e2b4839b90199eb4bdb9413024d842fb6d9a`1304 related plus separate first actual CORE1 PASS/0SKIP/exit0 and clean audit. Complete17-file archive `data/backups/d45-complete-full-files.zip`, SHA `a24833f9b5f1f9295ddfbf15c47bf20c01dee0172f5e2819ce0838761b955175`,0600/CRC/exact Git-blob verified, worktree clean. Existing P1 CODE-EVAL-001/[D46 plan](../docs/D46_CODING_AGENT_MVP_EVALUATION_PLAN.md) defines ten realistic bounded utility fixes, visible/held-out oracles validated against buggy/reference native sources before inference, one existing CORE attempt per case, explicit trusted fixture review contract and separate typed patch/visible/held-out check approvals. Model repair score is separate from protocol/test success; retain every rejection/failure and avoid score selection. Initially tests/fixtures/evaluation helpers/docs only, no agreed model/config/runtime/production/infrastructure/database change. No actual model case has run yet. **D46 IN PROGRESS; D47 remains dependent on the actual evidence gate.**


## 2026-10-20 — D46 ten-case evaluation complete, first repairs7/10

**Purpose:** Complete the roadmap's ten realistic measured coding-case/failure-review evidence criterion. **Functional repair score is7/10**, with2 native functional failures and1 response-contract rejection preserved. Evaluation/protocol completion does not establish broad/unattended production coding quality. Only new tests/evaluator/fixtures/docs; all accepted production/model/config/runtime/dependency/migration/Vault/Docker/database bytes remain unchanged.

Ten fixed authored utility cases cover timeout units, token masking, path joining, stable deduplication, partial batches, quota percentages, header redaction, boolean parsing, retry arithmetic and owner/live filtering. Corpus SHA `63e0a05b2b6f1a9d3d85210b09931d74d015ce6f53dfeb27f66c2936b74849d4`. The selected pre-inference manifest binds10 successful buggy/reference oracle pairs:20 actual native commands, buggy fails/reference passes complete visible+held-out suites,0 model attempts. Initial collection error exit2/0.28s (root test imported integration-only module) is retained in `data/backups/d46-initial-collection-error.json` and complete source ZIP; corrected shared private-artifact helper before any model call. New helper/native preflight34 PASS/7.70s, controlled full38 PASS/11.63s, final guard/protocol30 PASS/4.43s are historical checkpoints; current frozen nonmodel40 cases are included in the1344 related gate. No repeated inference or fixture correction after observed model results.

First actual frozen experiment: **10 protocol cases PASS/46.41s,0SKIP,exit0**, exactly10 existing CORE/fast/temperature0/max_tokens2048/60s attempts, automatic retries0. **7 FUNCTIONAL_PASS,2 FUNCTIONAL_FAIL,1 PROPOSAL_FAILED**. Each passing repair has known applied source plus visible and held-out native exits0.27 actual typed fixture approvals and18 native checks;9 authorized disposable target edits, unchanged trusted tests/external canaries. Held-out module/example records are not supplied to model; actual observed prompt hashes match visible-only frozen expectations. Generic native quality_evaluated remains false; this host score applies only to the authored oracles. Descriptive model application-port wall latency:min3.021945s/median3.143810s/max4.694445s; no TTFT/TPS/SLO/statistical superiority claim. Peak RSS/VRAM/token usage are unmeasured.

First experiment `data/backups/d46-evaluation-ddadfe69-7197-44fd-b637-1aa8b678e4d9/summary.json`, SHA `594ffde1b8a37630e21571d28a333e60fe1079f6c04df142fc3746609fd45d03`, all10 original case artifacts/raw completions/native results/CLI displays/full untrusted candidate files retained privately. Pre-inference source freeze `81afed398e21e0ac6e0714d45ec2dd29335995d14636e2ceac6601a137af360f`,6 new Python modules/22 described functions/classes pass isolated Ruff correctness/import/format.50 new unique pytest cases;427 source/687 unique source-protected hashes match.

Failure review:token-masking loses padding and retains token bytes on fully masked paths (visible/held-out exit1); explicit-boolean-text returns**6 plan entries** under existing**1–5** schema, rejected before patch/check publication with0 approvals/native runs; capped-retry-arithmetic passes visible cases but returns1.0 instead of2 for attempt-1 (held-out exit1). No plan trimming, relaxed schema, post-score oracle change or failed-attempt replacement. CODE-EVAL-002 assesses P1 formatting/edge-case/feedback-budget remediation before broad/unattended coding or quality promotion, with dependencies/effort/risks and fresh predeclared evidence; no model/policy change scheduled/implemented. Original D38 first4/6/palindrome+clamp failures remain a different immutable cohort, not replaced or statistically compared.

Affected D33–D46 **1344 PASS/114.22s (0:01:54),0SKIP,exit0** (wrapper114.73s); related log SHA `55a9f81a4d3d0e4e1587aff70c0a42ab65f276007429253b86b607ff579d0e5f`, related freeze `a04877d88456ecdf908ff41d255f9ced06ca4f036f834aeb11ac38f2eabf88fe`. Ten actual first model cases are separate, excluded from related to avoid score replacement;1354 distinct cases across gates, not one1354 invocation.2713 collected is not a fresh full; historical unchanged-production D44 full2622 remains separate.

`uv run --no-sync python data/backups/d46-final-post-audit.py`: actual exit0, log SHA `c5d452d816409f37c79ab884967748463a5027c2c9216217054c81c770a426d8`; independently reconstructs first7/10 from native observations. V006, zero source/memory/quota/vector/probe/worker/native/Git/advisory-lock/app/pending inventories, original owners/ACL/narrow grants/invoker fixed-search-path trigger properties and agreed model/config/dependency/migration/data match. D44 full/all evidence/both interrupted predecessors and original D45/D43/D38 measurements unchanged. Existing CORE healthy/running; production flags/actions remain off/unapproved.

[Evaluation acceptance](../docs/evidence/d46-evaluation-acceptance.json), [first ten measurements](../docs/evidence/d46-first-mvp-evaluation.json), [failure analysis](../docs/evidence/d46-failure-analysis.json), [scorecard/limits](../docs/D46_CODING_AGENT_MVP_SCORECARD.md), [immutable pre-inference protocol](../docs/D46_CODING_AGENT_MVP_EVALUATION_PLAN.md), [related](../docs/evidence/d46-related-regression.json), [audit](../docs/evidence/d46-final-post-audit.json). Complete evaluated seven-file archive `data/backups/d46-evaluated-full-files.zip`, SHA `f4eefa8a76b6c1791d60db728b3310bb0150bfe1543e4e3693ae124d688c9dbb`, CRC/exact bytes verified; complete committed file versions retained privately as `data/backups/d46-complete-full-files.zip`. Existing scope/runtime/OS/process-local/grant/independent-component/TCP-disconnect/cooperating-writer/crash/freshness limitations remain. **D46 PASS for the frozen ten-case evidence gate; first repair score7/10, broad coding quality not established. D47 NEXT.**


## 2026-10-20 — D47 search provider boundary begin

**Purpose:** Continue after D46 commit `c0bd79dc02a425e429d388fb74a6b8cb49107b8b`; first repair score7/10/failures and all accepted evidence preserved. Readonly Vault KV v2 metadata discovery lists11 prefixes/14 leaves, no errors/remaining prefixes. Generic application API secret has only api_token/principal_id fields; known search provider environment names absent. No external provider credential identified; owner asked for provider/path while independent work continues. Private metadata inventory contains no values.

[ADR-064](../docs/ADR/064-search-provider-boundary-and-existing-core.md) reviewed official Brave/Tavily API/quota/privacy/terms and accepts only an unwired internal provider-neutral bounded search→existing CORE contract. No provider selected/account created/purchase, automatic context disclosure or new model. Unit/actual-CORE-fixture/related evidence remains pending; real provider/credential/terms gate is explicitly open. No prior source/config/dependency/migration/Docker/Vault/database change. **D47 IN PROGRESS; D48 not started.**


## 2026-10-21 — D47 owner confirms missing provider; inactive reference adapter

**Purpose:** Preserve the owner's explicit reply “Tôi chưa có”: there is no search provider account/key to retrieve. Continue independent work without account creation, purchases, external search requests, new model or infrastructure writes. ADR-064 details the unwired internal port/pipeline plus default-unreviewed Brave reference adapter, fixed HTTPS POST, no redirects/env proxies/retries,64KiB raw response, strict snippet/JSON/citation binding,24KiB complete prompt and cooperative cancellation/deadlines. Existing accepted production services untouched.

Initial contract68 PASS/.11s; combined adapter113 PASS/.18s, then final aggregate-prompt/maximum-row coverage **115 PASS/.18s,0SKIP,exit0**. Isolated Ruff initially found one new test import ordering error (I001); corrected before freeze/inference, final correctness/import/format checks pass. No test failure or actual external provider request. Actual CORE authored fixture/related regression/audit still pending; D47 remains IN PROGRESS/PARTIAL, D48 not started.


## 2026-10-21 — D47 internal boundary verified; real provider prerequisite open

**Purpose:** Complete all independent D47 work while preserving the owner's confirmation that no provider/account/key exists. Three new unwired application-port/service/infrastructure modules, three described test modules and one authored JSON fixture; no initializer/route/runtime/config/model/dependency/migration/Vault/Docker/database or prior accepted source change. [ADR-064](../docs/ADR/064-search-provider-boundary-and-existing-core.md) records Brave/Tavily primary API/terms/quota/privacy review and distinguishes reference implementation from actual account adoption. [WEB-ONBOARD-001](../docs/WEB_RESEARCH_BACKLOG.md) assesses P1 dependency/effort/risks and actual live acceptance; no signup/purchase/billable query.

Final **115 controlled PASS/.17s**, included in **1459 related PASS/114.47s (0:01:54),0SKIP,exit0**; wrapper115.00s. Related log SHA256 `fffbc5b1b84d9a060895dd63aaefb31b6a0e2cbab98409b6f61d65fc714f06ad`. Separate frozen actual original CORE sample **1 PASS/.72s**, wrapper.89s: exactly one CORE/fast/temperature0/max_tokens768 call, one Brave-shaped MockTransport request, **zero external provider requests**, zero retries. Answer contains G-17 and exact S1→original fixture URL binding; provider stream closed, no key in model prompt. This is authored same-agent fixture evidence, not independent relevance, fresh web coverage, semantic entailment or real Brave API acceptance. First unique artifact `data/backups/d47-search-core-f20fc0a06a5848fcaf1e1353e43c388a/summary.json`, SHA `8693e4e917910352ffbaf5610fd7c77b886fd861275daa32e44a4bc858dfe3c9`; never replaced/rerun for score selection.

Six new Python files/67 described functions/classes pass isolated Ruff correctness/import/format.116 new unique tests (115 controlled+one actual CORE);1460 distinct across related/separate gates, not one1460 invocation.2829 collected/1.66s is **not a new full suite**; historical D44 full2622 stays separate. Source freeze `686d1257c948881ff19807fcbda972852d6629e7d228f2a1a14d4ada98c6d544`:434 source/859 unique source-protected hashes match before/after. Complete evaluated seven-file archive `data/backups/d47-evaluated-full-files.zip`, SHA `95f55fbd074946f8f0223f8d7ed8e855f8f97d8887739a8e43b766016350f9b5`,0600/CRC/exact bytes verified. Complete committed file versions retained privately after commit.

`uv run --no-sync python data/backups/d47-final-audit.py`: exit0, first actual prompt/freeze/completion/source/citation provenance matches; original configured CORE identity/preset unchanged. Reuses prior readonly security/data/model checks through a private copy with a distinct output, never overwriting earlier evidence. V006, zero source/memory/quota/vector/probe/worker/native/advisory-lock/app/pending inventories; original owners/ACL/narrow grants/invoker fixed-search-path triggers preserved. Parent audit log SHA `b28ffb0d0d539266622c39c0f36f692f7abd0317ecee9dc046ad04c2c59452b8`. Prior D46 first7/10/three failures, D45/D43/D38 first artifacts, D44 full/both interrupted predecessors, D24/a88584b and all agreed model/config/data bytes remain unchanged. Existing CORE remains healthy/running.

[Status](../docs/evidence/d47-status.json), [related](../docs/evidence/d47-related-regression.json), [first CORE fixture](../docs/evidence/d47-first-core-observation.json), [freeze](../docs/evidence/d47-search-freeze.json), [audit](../docs/evidence/d47-final-post-audit.json), [plan/limits](../docs/D47_SEARCH_PROVIDER_GATE.md). **D47 PARTIAL**: inactive internal boundary is verified; actual provider/account terms/quota/privacy/credential/live request remain unverified because there is no account/key. **D48 not started**. No synthetic/live substitution and no false whole-Day PASS.
