# Local Assistant — Documentation

Tài liệu mô tả các component của dự án theo cấu hình và code hiện có. Mỗi phần phân biệt chức năng đã triển khai với điều kiện vận hành và giới hạn của nó.

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">1. Model inference</h2></summary>

**Mục đích:** Tiếp nhận yêu cầu sinh văn bản, chọn đúng profile model, kiểm soát context/token budget, gọi backend local và kiểm tra phản hồi trước khi trả về cho component sử dụng.

Phần này mô tả inference của LLM. Embedding, reranker, ASR và TTS là các đường xử lý riêng, không được chọn bằng trường `profile` của API chat.

### 1.1. Model và runtime hiện tại

Nguồn cấu hình là [configs/models.yaml](../configs/models.yaml). Chiến lược model và trạng thái lựa chọn được ghi trong [Model Registry](progress/MODEL_REGISTRY.md).

| Thuộc tính | CORE | UNRESTRICTED |
|---|---|---|
| Profile trong API | `core` | `unrestricted` |
| Alias backend | `qwen3.5-9b-core` | `qwen3.5-9b-unrestricted` |
| Model | Qwen3.5-9B | Qwen3.5-9B-Uncensored-HauhauCS-Aggressive |
| Repository trọng số | `bartowski/Qwen_Qwen3.5-9B-GGUF` | `HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive` |
| Định dạng / quantization | GGUF / Q6_K | GGUF / Q6_K |
| Engine / backend | llama.cpp / CUDA | llama.cpp / CUDA |
| Context cấu hình | 32.768 token | 32.768 token |
| Số slot cấu hình | 1 | 1 |
| Trạng thái | Profile mặc định của API chat | Profile thử nghiệm, `status: testing` |

Cả hai profile trong YAML trỏ tới `127.0.0.1:8080`, với `gpu_layers: 99` và `reasoning: "off"` cho script native. [Docker Compose](../docker-compose.yaml) là một cách khởi động riêng: dùng `reasoning: auto`, Flash Attention auto, KV cache f16 và mmproj; CORE có `draft-mtp`, UNRESTRICTED dùng `none`. Không coi hai cách này là cùng một cấu hình benchmark. Cả hai cách đều chỉ phục vụ một profile trên cổng 8080 tại một thời điểm.

Chọn `profile="unrestricted"` không tự nạp hoặc thay model đang chạy. Nếu server chỉ quảng bá alias CORE, yêu cầu UNRESTRICTED bị từ chối với HTTP 409. Gateway không tự tải model, restart server hoặc chuyển sang profile khác. Profile UNRESTRICTED cũng không tự có thêm quyền sử dụng công cụ.

### 1.2. Các module tham gia

| Module | Trách nhiệm |
|---|---|
| [Model configuration](../apps/api/core/model_config.py) | Đọc profile từ YAML; cung cấp alias và địa chỉ backend loopback. |
| [Chat route](../apps/api/routes/chat.py) | Nhận yêu cầu chat stateless, xác thực trước khi đọc body và chuyển yêu cầu cho gateway. |
| [LlamaGateway](../apps/api/services/llama_gateway.py) | Kiểm tra alias đang nạp, xử lý Auto, đếm token, gọi completion và kiểm tra phản hồi. |
| [Runtime presets](../apps/api/runtime/presets.py) | Định nghĩa thinking/output budget và tính dung lượng context còn lại. |
| [LlamaInferenceAdapter](../src/infrastructure/inference/llama_adapter.py) | Chuyển kết quả gateway thành `CompletionResult` cho tầng application; chuẩn bị context và kiểm tra metadata. |
| [Conversation context](../src/application/services/conversation_context.py) | Chọn các lượt hội thoại nguyên vẹn và loại lượt cũ khi cần để vừa token budget. |
| [CORE launcher](../scripts/start-core.py) | Khởi động `llama-server` bằng profile CORE hiện có. |

### 1.3. Luồng xử lý một yêu cầu chat

```text
Client
  → POST /api/v1/chat/completions
  → Kiểm tra localhost, bearer token và JSON body
  → Đọc cấu hình profile
  → GET /v1/models để kiểm tra alias đang nạp
  → Chọn preset cụ thể, nếu yêu cầu Auto
  → POST /apply-template → POST /tokenize
  → Tính output budget
  → POST /v1/chat/completions tới llama-server
  → Kiểm tra completion và thêm metadata local_assistant
  → Trả kết quả cho client
```

API chat mặc định chọn `profile="core"`, `preset="balanced"`, `temperature=0.7`; body JSON tối đa 262.144 byte. Luồng này yêu cầu gọi trực tiếp từ localhost, có bearer hợp lệ và không có header Origin/proxy bị cấm. Xác thực chi tiết thuộc component API.

Chat stateless tính budget nhưng không tự cắt nội dung client gửi. Đường qua `LlamaInferenceAdapter` có bước fit context: giữ system instructions và lượt hiện tại, bỏ các cặp lịch sử cũ khi cần. Nếu phần bắt buộc vẫn vượt context, yêu cầu bị từ chối.

### 1.4. Runtime presets

`profile` chọn model/alias; `preset` chọn cách suy luận cho từng yêu cầu. Đổi preset không phải đổi model hoặc quantization.

| Preset | Thinking được yêu cầu | Reasoning budget | Trần output |
|---|---|---|---|
| `fast` | Tắt | Không gửi thinking budget | 4.096 token |
| `balanced` | Bật | 4.096 token | 8.192 token |
| `deep` | Bật | 8.192 token | 16.384 token |
| `unlimited` | Bật | `-1` | Dung lượng context còn lại |
| `auto` | Theo preset được chọn | Theo preset được chọn | Theo preset được chọn |

Auto chỉ chọn `fast`, `balanced` hoặc `deep`. Lời chào đơn giản đứng riêng có thể được chọn Fast bằng rule; các yêu cầu khác dùng một lượt phân loại ngắn bằng chính model đang chọn. Nếu phân loại lỗi hoặc nhãn không hợp lệ, Auto chọn Balanced. Auto không chọn Unlimited.

Gateway gửi `chat_template_kwargs.enable_thinking` và, khi yêu cầu thinking, `thinking_budget_tokens`. Hiệu lực của tham số thinking phụ thuộc build llama.cpp; metadata `thinking_requested` thể hiện yêu cầu đã gửi, không tự chứng minh chất lượng suy luận.

### 1.5. Context và token budget

Token đầu vào được đếm sau khi áp chat template bằng tokenizer của backend. Quy tắc hiện tại:

```text
available_output = 32768 - input_tokens - 256
max_tokens = min(available_output, preset_output_ceiling, requested_max_tokens nếu có)
```

- Dành 256 token làm context reserve và yêu cầu tối thiểu 512 token output.
- Balanced cần ít nhất 4.608 token output; Deep cần ít nhất 8.704 token để chứa reasoning budget cộng phần trả lời tối thiểu.
- `max_tokens` do client gửi là giới hạn bổ sung, không phải lệnh vượt trần preset/context.
- Unlimited vẫn bị giới hạn bởi context còn lại và `max_tokens` nếu client cung cấp.
- Budget không đủ trả HTTP 422; hệ thống không tự hạ từ Deep xuống Fast để tiếp tục.

### 1.6. Phản hồi và xử lý lỗi

Đường chat dùng preset chỉ chấp nhận phản hồi có `finish_reason="stop"` và nội dung văn bản không rỗng. `finish_reason="length"` được xem là chưa hoàn chỉnh. Metadata `local_assistant` ghi preset, số token đầu vào đã đếm, giới hạn output/thinking được yêu cầu và trạng thái kiểm tra. Khi dùng Auto, metadata bổ sung preset đã chọn và nguồn quyết định.

Gateway còn giữ đường nội bộ `preset=None` để tương thích caller cũ; đường này không áp dụng bước lập budget/kiểm tra completion theo preset. API chat công khai luôn chọn một preset. `LlamaInferenceAdapter` kiểm tra kết quả chặt hơn và không lưu `reasoning_content` vào lịch sử qua adapter này.

| HTTP | Tình huống inference |
|---|---|
| 409 | Alias yêu cầu chưa được nạp. |
| 422 | Preset hoặc token budget không hợp lệ/không đủ. |
| 502 | Phản hồi backend lỗi, không hợp lệ hoặc completion chưa đạt kiểm tra. |
| 503 | Backend không kết nối được hoặc cấu hình profile không sử dụng được. |
| 504 | Yêu cầu backend timeout. |

Route chat công khai trả lỗi inference đã được làm gọn, không đưa nguyên thông báo nội bộ ra client. Timeout đọc của gateway văn bản hiện là 1.200 giây; đây không phải cam kết thời gian phản hồi hoặc giới hạn 4 giây của voice.

### 1.7. Kết quả đo thực tế

Các số dưới đây lấy từ những lượt đo đã lưu, không phải benchmark mới khi viết tài liệu. Chúng có workload, đường gọi và trạng thái cache khác nhau; không gộp thành một kết quả cho mọi preset hoặc mọi yêu cầu. Microbenchmark sử dụng CUDA trên NVIDIA RTX 4070 Ti SUPER, build llama.cpp `5c8854fd8` (`11557`); commit runtime được lưu tại [llama-cpp-commit.txt](../configs/llama-cpp-commit.txt).

#### Token đầu tiên và thời gian hoàn tất — D83

[Báo cáo D83](progress/D83_INFERENCE_OBSERVABILITY.md) và [receipt số đo](evidence/d83-observability-verification.json) ghi một lượt streaming trực tiếp tới backend CORE đã nạp sẵn, 24 token đầu vào và 7 token đầu ra, kết thúc bằng `stop`.

| Chỉ số | Kết quả | Cách hiểu |
|---|---:|---|
| First output / client TTFT | 169.451 ms | Từ lúc bắt đầu yêu cầu tới phần văn bản đầu tiên không rỗng mà client nhận được. |
| Tổng thời gian client | 248.696 ms | Thời gian hoàn tất lượt yêu cầu. |
| Tốc độ sinh token do backend báo | 73.671 token/s | Native/server-reported decode rate. |
| Tốc độ output trên toàn thời gian client | 28.147 token/s | 7 token chia tổng thời gian; bao gồm thời gian chờ token đầu tiên. |
| Số content chunk | 6 | Chunk truyền tải không đồng nghĩa với từng token. |
| Tốc độ decode đo độc lập tại client | Chưa có | Không quan sát được ranh giới chính xác của từng token. |

TTFT ở đây bao gồm ảnh hưởng truyền tải/buffering và bỏ qua SSE event chỉ chứa role hoặc nội dung rỗng. Đây là **một mẫu warm ngắn**, không phải trung bình/p95, cold start hoặc thời gian nạp model. API chat công khai hiện trả nonstreaming; số TTFT này thuộc probe backend riêng, không chứng minh API đã hỗ trợ streaming.

#### Tốc độ xử lý prompt và sinh token — llama-bench

Các artifact cục bộ nằm trong [benchmark results](../benchmarks/results/) với tên `qwen3.5-9b-q6k-{512,4k,8k,16k}.txt` cho CORE và trong [UNRESTRICTED raw](../benchmarks/results/qwen3.5-9b-unrestricted/raw/) với tên `pp{512,4096,8192,16384}.txt` cho UNRESTRICTED. Đây là artifact bị Git bỏ qua; cần giữ riêng khi bàn giao kết quả.

| Test prompt processing | CORE prefill (token/s) | CORE `tg128` (token/s) | UNRESTRICTED prefill (token/s) | UNRESTRICTED `tg128` (token/s) |
|---|---:|---:|---:|---:|
| `pp512` | 5777.04 ± 189.17 | 79.76 ± 0.15 | 5492.73 ± 121.07 | 80.97 ± 0.46 |
| `pp4096` | 5837.81 ± 37.19 | 79.11 ± 0.70 | 5510.67 ± 27.60 | 80.39 ± 0.67 |
| `pp8192` | 5787.35 ± 25.94 | 79.79 ± 0.12 | 5427.26 ± 24.04 | 80.38 ± 0.61 |
| `pp16384` | 5603.16 ± 18.34 | 79.70 ± 0.15 | 5244.77 ± 9.78 | 80.32 ± 0.63 |

`ppN` đo xử lý prompt N token; `tg128` đo sinh 128 token. Đây là các test riêng của llama-bench: đặt cùng hàng không có nghĩa `tg128` được đo sau prompt N token tương ứng. Dấu `±` được giữ đúng theo output của công cụ, không gọi là p95 hoặc khoảng tin cậy. Các lượt hai profile chạy riêng; bảng không chứng minh chênh lệch chất lượng hoặc hiệu năng production. Prefill token/s cũng không phải TTFT của một yêu cầu HTTP.

#### Runtime inference và RAM/VRAM — gate D14 đã xác minh

[Kết quả D14 sau khắc phục](progress/D14_SEMANTIC_REMEDIATION_RESULT.md) và [receipt kiểm chứng](evidence/d14-contract-full-first-verification.json) ghi lượt ngày 2026-10-26: mỗi profile chạy 42 yêu cầu được chấm, dùng adapter reasoning **opt-in**, thinking budget 512 trong tổng output budget 1024 token, kèm contract đã khai báo.

| Chỉ số | CORE | UNRESTRICTED |
|---|---:|---:|
| Format và exact facts trên cohort này | 42/42 | 42/42 |
| Tổng thời gian 42 yêu cầu | 319.944 s | 314.539 s |
| Tổng output token, gồm reasoning và final | 21.375 | 21.601 |
| Peak RSS RAM toàn native worker, qua `wait4` | 10.204.712 KiB ≈ 9.73 GiB | 10.046.844 KiB ≈ 9.58 GiB |
| Peak VRAM quan sát qua lấy mẫu | 8884 MiB | 8548 MiB |

Tổng thời gian trên không bao gồm cold load, yêu cầu cancellation hoặc dọn worker. RAM và VRAM là hai loại bộ nhớ khác nhau; RSS có thể gồm trang shared/mapped, VRAM gồm trọng số, KV cache và workspace. Đây không phải dung lượng trọng số riêng, yêu cầu RAM tối thiểu hoặc true peak VRAM giữa các lần lấy mẫu.

Đường opt-in này không được tự bật trong API và không đại diện benchmark Fast/Balanced/Deep mặc định hiện tại. Kết quả 42/42 chỉ áp dụng cohort đã khai báo; mọi điểm và lượt FAIL D14 trước đó vẫn giữ nguyên. Thời gian nạp model riêng chưa có số đo trong các kết quả trích ở đây.

#### Context dài và độ trễ ứng dụng — D67

[Báo cáo D67](progress/D67_EXISTING_MULTIMODAL_BENCHMARK.md) ghi CORE Q6_K với mmproj, context 32.768 và một slot, đã nạp sẵn. Mỗi hàng có ba lượt tuần tự, giữ prompt cache; output chỉ là literal echo ngắn.

| Token đầu vào thực tế sau template | Min | Median | Max |
|---|---:|---:|---:|
| 191 | 0.086 s | 0.090 s | 0.176 s |
| 2111 | 0.097 s | 0.100 s | 0.564 s |
| 8255 | 0.119 s | 0.120 s | 1.293 s |
| 16447 | 0.150 s | 0.152 s | 1.776 s |
| 31563 | 0.207 s | 0.208 s | 3.417 s |

Thời gian này đo toàn đường gọi application port, gồm kiểm tra template/token nội bộ, nhưng không gồm bước đếm preflight riêng. Đây là warm cached latency, không phải uncached prefill hoặc benchmark chất lượng suy luận context dài. Input 34.063 token bị từ chối `context_overflow` sau 0.049 s, không phát sinh completion thành công.

Trong 81 mẫu tài nguyên của cùng process CORE, RSS RAM nằm trong 9283.812–10017.594 MiB; GPU allocation quan sát được là 9386 MiB. Workload/cấu hình đo khác D14 nên không gộp các mức bộ nhớ thành một baseline. D67 dùng nonstreaming nên **TTFT và client decode token/s chưa đo**. Các kết quả trên chưa xác lập cold-start latency, tải đồng thời, population p95/p99 hoặc SLO production.

#### Harness maintenance và first-text timing — HAR-008-Q2, 2026-11-10

[Kết quả Q2](HAR008_Q2_MAINTENANCE_RESULT.md), [receipt](evidence/har008-q2-maintenance-20261110.json): cùng CORE/Fast512 đã nạp, 96 first product-task calls, input thực 778–12.970 tokens. Sampled native RSS RAM tối đa **10.013.460 KiB ≈ 9,55 GiB**, GPU process allocation **8018 MiB ≈ 7,83 GiB**, trong 637 mẫu. Đây là footprint/allocations của tiến trình CORE ấm, không RAM riêng request, tổng toàn ứng dụng, tensor-only usage hay absolute peaks; không thay baseline D14/D67.

Tám replay streaming riêng đo first nonempty text delta: **0,416774–0,624449 s** ở sáu lượt ngắn và **2,371246–2,525117 s** ở hai lượt dài (12.315/12.379 input tokens). Đây là warm native client arrival, có cache/transport và sampling overhead; không phải TTFT của task API nonstreaming, cold start hoặc SLO. Giữ tất cả first outputs, không tính tám replay thành quality samples mới. Phần 13.6 ghi chất lượng và lỗi còn tồn đọng.

### 1.8. Cài đặt, tải model và khởi động từ đầu

Hướng dẫn dưới đây dành cho máy Linux mới hoặc checkout mới, không phải lệnh cập nhật đè lên runtime đang phục vụ. Các lệnh chạy ở thư mục gốc repository Local Assistant — chính là `ai/` trong workspace Home Server hiện tại. Không cần tải lại những file đã có và khớp checksum.

#### Bước 1 — Chuẩn bị môi trường dự án

Cần có Git, `uv`, Python từ 3.11 và driver NVIDIA hoạt động. Đường build native còn cần CUDA Toolkit, CMake, Ninja và bộ biên dịch tương thích. Máy tham chiếu dùng CUDA 12.4, GCC/G++ 13 và GPU compute capability 8.9; không áp nguyên cấu hình GPU này cho phần cứng khác. Đây là điều kiện cài đặt của máy, không phải dependency do `uv` cài hộ.

Chỉ clone nếu chưa có checkout; URL SSH bên dưới cần quyền truy cập GitHub tương ứng:

```bash
git clone git@github.com:DungeonLeiz/local-assistant.git local-assistant
cd local-assistant
uv sync --locked --dev
```

Nếu đã có repository, mở terminal tại `ai/` rồi chạy riêng `uv sync --locked --dev`. Lệnh dùng [pyproject.toml](../pyproject.toml) và [uv.lock](../uv.lock), không cập nhật phiên bản dependency. Kiểm tra công cụ của đường native:

```bash
uv --version
nvidia-smi
nvcc --version
cmake --version
ninja --version
gcc-13 --version
g++-13 --version
```

Thiếu driver/CUDA hoặc compiler thì hoàn tất cài đặt hệ thống trước bước build. Dung lượng đĩa phải chứa được trọng số, cache tải, môi trường Python và thư mục build; số RAM/VRAM ở mục 1.7 không phải dung lượng đĩa cần tải.

#### Bước 2 — Build đúng phiên bản llama.cpp cho native

Các lệnh sau chỉ dành cho thư mục `runtimes/llama.cpp` chưa tồn tại. Nếu đã có, kiểm tra commit/binary hiện tại, không clone đè hoặc tự chuyển revision của runtime đang chạy.

```bash
mkdir -p runtimes
git clone https://github.com/ggml-org/llama.cpp.git runtimes/llama.cpp
git -C runtimes/llama.cpp checkout --detach "$(cat configs/llama-cpp-commit.txt)"
git -C runtimes/llama.cpp rev-parse HEAD

cmake -S runtimes/llama.cpp -B runtimes/llama.cpp/build-cuda -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_CUDA=ON \
  -DCMAKE_C_COMPILER=/usr/bin/gcc-13 \
  -DCMAKE_CXX_COMPILER=/usr/bin/g++-13 \
  -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-13 \
  -DCMAKE_CUDA_ARCHITECTURES=89

cmake --build runtimes/llama.cpp/build-cuda \
  --target llama-server llama-bench --parallel 4
runtimes/llama.cpp/build-cuda/bin/llama-server --version
```

Commit mong đợi là `5c8854fd88319125125dc4b836c98b1b215b0f23`. Đường output trên khớp hai launcher hiện có; không thay bằng một build mới nhất tùy ý.

#### Bước 3 — Tải đúng trọng số CORE và kiểm tra checksum

Chỉ tải hai file cần thiết, không tải toàn bộ repository model. Revision dưới đây lấy từ metadata của lần tải đã lưu ở máy hiện tại; SHA-256 GGUF khớp cấu hình dự án. Đây là đối chiếu với artifact dự án đã dùng, không phải chứng nhận độc lập về nguồn phát hành.

```bash
mkdir -p models/core/qwen3.5-9b
uv run --no-sync hf download bartowski/Qwen_Qwen3.5-9B-GGUF \
  Qwen_Qwen3.5-9B-Q6_K.gguf \
  mmproj-Qwen_Qwen3.5-9B-bf16.gguf \
  --revision 182be2fd6c7bc44887d88a91cb03ff009cc9f549 \
  --local-dir models/core/qwen3.5-9b

sha256sum --check <<'SHA256'
073a9275e65d9c8cd2819cf5f77b99fbaa6e87ba591da6bbaa86ec073a64bfef  models/core/qwen3.5-9b/Qwen_Qwen3.5-9B-Q6_K.gguf
d89c4bc142d02ed64aeed5c0a358bdead9109f21f4ada03a6b2df17a1aa94d9e  models/core/qwen3.5-9b/mmproj-Qwen_Qwen3.5-9B-bf16.gguf
SHA256
```

Cần nhận `OK` cho cả hai file trước khi dùng vision hoặc Docker Compose. Nếu chỉ chạy text native, có thể bỏ file mmproj khỏi lệnh tải. Sai checksum thì dừng, không sửa checksum cấu hình để hợp thức hóa file vừa tải. [download-model-metadata.py](../scripts/download-model-metadata.py) chỉ tải metadata/projector, **không tải GGUF chính**; script đó còn truy vấn revision hiện tại trên Hub nên không thay thế lệnh tải đã pin ở trên.

#### Bước 4 — Chuẩn bị UNRESTRICTED khi cần thử profile này

Đây là profile thử nghiệm đã có trong cấu hình, không phải bước bắt buộc để chạy CORE:

```bash
mkdir -p models/unrestricted/qwen3.5-9b
uv run --no-sync hf download \
  HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive \
  Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf \
  mmproj-Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-BF16.gguf \
  --revision 0a41c68809d375475f954be12ba7c40efa56c2a9 \
  --local-dir models/unrestricted/qwen3.5-9b

sha256sum --check <<'SHA256'
c0ba7beb68fd3fe47891bd549486d38dcf62d00817296ea314ad37017f5a4986  models/unrestricted/qwen3.5-9b/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf
05f662501f8bd45607b079723a3e238a4e888fd085a10a53f4057a0e250f6934  models/unrestricted/qwen3.5-9b/mmproj-Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-BF16.gguf
SHA256
```

#### Bước 5 — Chọn một cách khởi động

**Native:** sau khi tải/build xong, chạy CORE text bằng launcher hiện có:

```bash
uv run --no-sync python scripts/start-core.py
```

Launcher kiểm tra file tồn tại rồi chạy theo YAML; không tải trọng số và không tự kiểm SHA-256. Launcher này không truyền `--mmproj`. Muốn dùng projector đã tải, thay lệnh trên bằng:

```bash
uv run --no-sync python scripts/start-model.py --profile core --vision
```

Để thử UNRESTRICTED, dừng process đang giữ cổng 8080 tại terminal đã khởi động bằng `Ctrl+C`, rồi chạy `uv run --no-sync python scripts/start-model.py --profile unrestricted`. Thêm `--vision` chỉ khi cần và đã có đúng projector. Không chạy đồng thời các lệnh launcher.

**Docker Compose:** là lựa chọn thay cho build/chạy native. Cần Docker Compose có hỗ trợ GPU và NVIDIA Container Toolkit đã cấu hình; không cần build binary native ở bước 2. [Dockerfile](../docker/llama.Dockerfile) tự build runtime từ đúng commit, CUDA 12.4.1 và architecture 89:

```bash
docker build -f docker/llama.Dockerfile \
  --build-arg LLAMA_COMMIT=5c8854fd88319125125dc4b836c98b1b215b0f23 \
  -t local-assistant/llama-cuda:5c8854fd8 .
docker network inspect home-net
docker compose --profile core up -d core
docker compose logs --tail 50 core
```

`home-net` là mạng external do hạ tầng Home Server quản lý. Nếu chưa có trên máy mới, hoàn tất bootstrap hạ tầng trước; Compose này không tạo mạng và hướng dẫn này không tạo thêm PostgreSQL/Vault/Qdrant. Docker yêu cầu cả GGUF và mmproj. Không khởi động Docker khi native đang giữ cổng 8080; không chạy đồng thời hai profile. Dừng riêng CORE bằng `docker compose --profile core stop core`. Khi đã dừng CORE và chủ đích thử UNRESTRICTED, dùng `docker compose --profile unrestricted up -d unrestricted`.

#### Bước 6 — Xác nhận backend trước khi gọi API

Ở terminal thứ hai, kiểm tra trực tiếp backend loopback:

```bash
curl --noproxy '*' --fail --silent --show-error http://127.0.0.1:8080/health
curl --noproxy '*' --fail --silent --show-error http://127.0.0.1:8080/v1/models
```

Đợi backend sẵn sàng và kiểm tra alias trả về đúng profile vừa nạp. Backend 8080 khác API ứng dụng 8000 ở phần 2. Backend không tự yêu cầu bearer của API; giữ cổng này trên loopback, không dùng nó làm API công khai.

Các kiểm thử logic inference có thể chạy riêng:

```bash
uv run --no-sync python -m pytest tests/test_llama_gateway.py tests/test_runtime_presets.py tests/test_llama_adapter.py tests/test_conversation_context.py -q
```

Đây là kiểm thử fixture/mock, không thay thế benchmark model thật. Các lệnh setup/tải/build trong mục này là hướng dẫn tái lập, chưa được chạy lại trên máy sạch khi viết tài liệu; số liệu ở mục 1.7 vẫn thuộc các lượt đo đã ghi nguồn.

### 1.9. Điều phối GPU và quy tắc thay đổi

[GPU admission](../src/application/services/gpu_admission.py) và [managed inference bindings](../apps/api/voice_admission.py) được dùng trong composition voice tùy chọn để tránh chat tranh GPU với nhóm voice đang giữ residency. Đây là điều phối các đường gọi đã đăng ký trong một tiến trình, không phải khóa GPU toàn máy; API chính thông thường không tự bật cơ chế này.

Việc thay model, quantization, context hoặc mặc định đã thống nhất phải tuân thủ quy tắc của chủ dự án: benchmark phù hợp, phân tích hiệu năng/tài nguyên, migration, rollback và phê duyệt trước khi áp dụng. Tài liệu này ghi lại triển khai hiện tại, không thay đổi cấu hình hay lựa chọn model.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">2. API và xác thực</h2></summary>

**Mục đích:** Cung cấp API ứng dụng cho client local, xác thực người gọi, gắn tài nguyên với đúng chủ sở hữu và từ chối yêu cầu ngoài phạm vi trước khi thực hiện công việc được bảo vệ.

### 2.1. Thành phần và địa chỉ

| Thành phần | Vai trò |
|---|---|
| [FastAPI entry point](../apps/api/main.py) | Đăng ký router dưới `/api/v1`, OpenAPI và vòng đời tài nguyên. |
| [Bearer authentication](../apps/api/core/conversation_auth.py) | Đọc lại digest token, so sánh bằng `hmac.compare_digest` và trả principal UUID. |
| [Local access guard](../apps/api/routes/conversations.py) | Chỉ nhận peer loopback trực tiếp, chặn Origin và các proxy header đã quy định. |
| [Stateless chat route](../apps/api/routes/chat.py) | Kiểm tra local/bearer trước khi đọc body, giới hạn JSON và gọi inference gateway. |
| [Application lifespan](../apps/api/storage/lifecycle.py) | Khởi tạo các dịch vụ tùy chọn theo dependency, hủy/join công việc và đóng tài nguyên theo thứ tự. |
| [Logging configuration](../apps/api/core/logging_config.py) | Bật log audit INFO cho `apps.api` và `src`, giữ handler triển khai đã có. |

| Địa chỉ khi chạy theo hướng dẫn | Nội dung |
|---|---|
| `http://127.0.0.1:8000/api/v1` | API ứng dụng; endpoint được bảo vệ yêu cầu bearer và direct localhost. |
| `http://127.0.0.1:8000/api/v1/health` | Health công khai, chỉ phản ánh API còn phản hồi. |
| `http://127.0.0.1:8000/docs` | Swagger UI để xem hợp đồng API. |
| `http://127.0.0.1:8000/openapi.json` | OpenAPI schema. ReDoc bị tắt. |
| `http://127.0.0.1:8080` | Backend llama.cpp riêng, không phải API có xác thực ở cổng 8000. |

Health và trang schema không có bearer guard trong entry point hiện tại. `health=ok` không chứng minh token hợp lệ, database sẵn sàng hoặc model đã nạp. Việc giữ các trang này local phụ thuộc bind `127.0.0.1` khi khởi động.

### 2.2. Luồng xác thực và quyền sở hữu

```text
Client gọi trực tiếp 127.0.0.1
  → Kiểm tra peer loopback và Origin/proxy headers
  → Đọc ASSISTANT_AUTH_FILE
  → Kiểm tra file riêng tư và schema principals
  → Hash bearer token bằng SHA-256
  → So sánh digest và lấy principal UUID
  → Kiểm tra input và dịch vụ cần dùng
  → Giới hạn thao tác theo owner/principal và policy của component
  → Trả kết quả hoặc mã lỗi an toàn
```

Đây là bearer token local gắn với UUID, không phải luồng login/password, JWT hay Keycloak/OIDC của ứng dụng. Token hợp lệ xác định người gọi; quyền với file, hội thoại, workspace và approval vẫn do từng component kiểm tra. Đổi sang profile UNRESTRICTED không cấp thêm quyền.

Guard hiện từ chối peer không phải loopback, mọi header `Origin` kể cả `Origin: null`, cùng `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host` và `X-Real-IP`. Không có CORS mở để trình duyệt ở origin khác gọi trực tiếp các endpoint được bảo vệ. Có bearer đúng cũng không vượt qua các chặn này; mở `/docs` không có nghĩa mọi thao tác “Try it out” sẽ được phép.

Riêng chat stateless áp dụng local/bearer **trước khi đọc và parse body**. Không coi thứ tự này là bảo đảm chung về mọi parser ở tất cả router. Cấu hình reverse proxy, truy cập LAN, TLS, OIDC hoặc nhiều worker chưa được hướng dẫn này cấp quyền triển khai.

### 2.3. Cấu hình bearer credential

`ASSISTANT_AUTH_FILE` trỏ tới file JSON chứa **digest**, không chứa token nguyên văn:

```json
{
  "principals": [
    {
      "id": "<principal UUID>",
      "token_sha256": "<64 lowercase hexadecimal characters>"
    }
  ]
}
```

Các giá trị trong ví dụ là placeholder, không phải credential dùng được. File phải là regular file, thuộc UID chạy API, không cho group/other truy cập, không phải symlink ở thành phần cuối và không quá 65.536 byte. Schema nhận 1–100 bản ghi; mỗi bản ghi chỉ có `id`, `token_sha256`, digest không trùng nhau. Quyền `0600` là cấu hình phù hợp cho file.

Header phải xuất hiện đúng một lần, dạng `Authorization: Bearer <token>`. Token được chấp nhận về hình thức khi có 32–512 ký tự ASCII, không chứa khoảng trắng; credential được cấp nên là token ngẫu nhiên entropy cao. Hash đúng hình thức không tự cấp quyền nếu không khớp bản ghi đang có.

Instance hiện tại đã lưu credential tại Vault KV v2 `secret/server/local-assistant/api`, các trường `api_token` và `principal_id`; đây là địa chỉ logic secret, không phải URL API của Vault. API không tự đọc Vault: operator cung cấp file digest qua biến môi trường. Dùng lại đúng hai giá trị đã cấp, không tạo UUID mới cho cùng dữ liệu hiện có. Với instance mới hoàn toàn, cấp/lưu credential trong Vault trước; repository hiện không có endpoint đăng ký hoặc phát token.

Ví dụ tạo **file digest mới** từ credential đã cấp, chạy ở thư mục repository; đoạn này không đọc Vault tự động, không in token và từ chối ghi đè file đã tồn tại:

```bash
export ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json"
uv run --no-sync python - <<'PY'
"""Create a private digest file from an existing operator-issued credential."""
import getpass
import hashlib
import json
import logging
import os
from pathlib import Path
from uuid import UUID

logging.basicConfig(level=logging.INFO)
principal = str(UUID(getpass.getpass("Principal UUID from Vault (hidden): ").strip()))
token = getpass.getpass("API token from Vault: ")
if not 32 <= len(token) <= 512 or not token.isascii() or any(c.isspace() for c in token):
    raise SystemExit("Invalid token format")
path = Path(os.environ["ASSISTANT_AUTH_FILE"])
path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
payload = {"principals": [{"id": principal, "token_sha256": hashlib.sha256(token.encode()).hexdigest()}]}
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
    json.dump(payload, stream, indent=2)
    stream.write("\n")
logging.info("auth_digest_file_created principals=1")
PY
```

File được đọc lại mỗi request. Xóa binding digest sẽ thu hồi token cho các request xác thực sau đó mà không cần restart; không khẳng định nó tự hủy tác vụ đã được xác thực trước đó. Khi cập nhật file hiện có, giữ nguyên binding của người khác, UID/quyền và thay file nguyên vẹn để tránh trạng thái JSON đang ghi dở. Không ghi token vào URL, code, log, Git hoặc browser persistent storage.

### 2.4. Khởi động API

Sau bước cài dependency ở mục 1.8, dùng terminal riêng tại repository:

```bash
export ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json"
uv run --no-sync uvicorn apps.api.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

API đọc tên file từ môi trường; không tự tạo file hoặc credential khi khởi động. Thiếu cấu hình auth vẫn có thể mở health/schema, nhưng endpoint được bảo vệ trả `503 auth_unavailable`.

Chat stateless không cần database nhưng cần đúng model alias ở backend để sinh câu trả lời. Nếu không có `DATABASE_URL`, storage hội thoại/file/ingestion/retrieval/grounded/memory không được khởi tạo. Nếu có biến này, lifespan sẽ tạo pool và các tài nguyên liên quan; cấu hình không hợp lệ có thể làm startup thất bại. Không đặt URL giả chỉ để chạy health/chat và không tạo database mới thay cho hạ tầng dùng chung.

Các dịch vụ tùy chọn còn cần cờ bật và cấu hình riêng; có router trong OpenAPI không đồng nghĩa dịch vụ đã bật. `/voice` và grounded extraction dùng composition tùy chọn riêng, không được tự bật bởi lệnh chạy API cơ bản trên. Dừng API ở terminal bằng `Ctrl+C` để lifespan đóng tài nguyên.

### 2.5. Nhóm endpoint hiện có

| Nhóm | Ví dụ đường dẫn | Điều kiện sử dụng |
|---|---|---|
| Chat stateless | `POST /api/v1/chat/completions` | Local + bearer; đúng alias backend; không tự lưu hội thoại. |
| Hội thoại | `/api/v1/conversations` | Local + bearer + database; dữ liệu thuộc principal đã xác thực. |
| File và xử lý tài liệu | `/api/v1/files`, `/{file_id}/extract`, `/{file_id}/chunks` bên dưới prefix file | Cần file service và điều kiện processor tương ứng. |
| Index và retrieval | `POST /api/v1/files/{file_id}/index`, `GET /api/v1/ingestion/{job_id}`, `POST /api/v1/retrieval/search` | Cần dịch vụ, cấu hình index/model và nguồn được phép. |
| Trả lời theo nguồn | `/api/v1/grounded/answer` | Cần retrieval/grounded và các kiểm tra nguồn. |
| Memory | `/api/v1/memory` | Cần storage, policy và consent theo component. |
| Web search | `/api/v1/web/search` | Cần provider/service đã cấu hình. |
| Workspace và coding workflow | `/api/v1/workspaces` cùng các route con | Cần workspace service và approval/policy của từng thao tác. |

Đây là bảng nhóm chức năng, không phải danh sách method đầy đủ. Xem `/openapi.json` của đúng composition đang chạy để biết schema/method chi tiết; bearer không tự bật tool, approval, dịch vụ hoặc profile khác.

### 2.6. Kiểm tra sau setup

Kiểm tra API còn phản hồi và schema có sẵn, không cần token:

```bash
curl --noproxy '*' --fail --silent --show-error http://127.0.0.1:8000/api/v1/health
curl --noproxy '*' --fail --silent --show-error http://127.0.0.1:8000/openapi.json
```

Sau khi đã cấu hình file auth hợp lệ, gọi chat không có token phải nhận `401`; body sai JSON không được làm thay đổi kết quả xác thực này:

```bash
curl --noproxy '*' --silent --show-error -i \
  -H 'Content-Type: application/json' \
  --data '{' http://127.0.0.1:8000/api/v1/chat/completions
```

Ví dụ gọi chat có xác thực, nhập token kín thay vì đưa token vào lịch sử shell hoặc tham số command line:

```bash
uv run --no-sync python - <<'PY'
"""Probe authenticated local chat without exposing the bearer credential."""
import getpass
import logging
import httpx

logging.basicConfig(level=logging.INFO)
token = getpass.getpass("API token from Vault: ")
with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=1200) as client:
    response = client.post(
        "/api/v1/chat/completions",
        headers={"Authorization": "Bearer " + token},
        json={"profile": "core", "preset": "fast", "max_tokens": 512,
              "messages": [{"role": "user", "content": "Say hello in one short sentence."}]},
    )
    logging.info("authenticated_chat_probe_completed status=%d", response.status_code)
    response.raise_for_status()
    print(response.json()["choices"][0]["message"]["content"])
PY
```

Đây là yêu cầu inference thật khi operator chạy, không phải unittest. Muốn nhận câu trả lời cần CORE sẵn sàng ở 8080; `200` cùng câu trả lời hoàn chỉnh chứng minh request cụ thể này hoạt động, không chứng minh benchmark chất lượng hay SLO. Đường này nonstreaming nên thời gian hoàn tất không được ghi thành TTFT.

### 2.7. Lỗi, kiểm thử và giới hạn đã xác minh

| HTTP | Diễn giải ở ranh giới API |
|---|---|
| 401 | Thiếu/sai/thu hồi bearer hoặc nhiều Authorization header, khi file auth hợp lệ. |
| 403 | Peer không phải loopback hoặc có Origin/proxy header bị cấm. |
| 413 / 415 | Chat stateless vượt 262.144 byte hoặc không dùng `application/json`. |
| 422 | Input/schema/token budget không hợp lệ; giới hạn cụ thể tùy endpoint. |
| 409 / 429 | Xung đột trạng thái hoặc admission đang bận, tùy component. |
| 503 | Auth không có/không hợp lệ, dịch vụ chưa bật, hoặc tài nguyên phụ thuộc chưa sẵn sàng. |
| 502 / 504 | Lỗi completion/backend hoặc timeout inference; xem thêm mục 1.6. |

Body limit 262.144 byte thuộc chat stateless, không phải trần chung cho upload/file API. Route này thêm `Cache-Control: private, no-store` và `X-Content-Type-Options: nosniff` cho kết quả thành công và các lỗi được route gắn header; không mặc định coi mọi lỗi sớm của guard đã có cùng bộ header. Log ghi sự kiện/trạng thái và có thể có principal UUID, không dùng log làm nơi chứa token hoặc raw backend exception.

Chạy các kiểm thử liên quan, không cần tải model hoặc khởi động backend thật:

```bash
env -u DATABASE_URL uv run --no-sync python -m pytest \
  tests/test_conversation_auth.py tests/test_stateless_security.py \
  tests/test_api_health.py tests/test_application_logging.py -q
```

[ADR-018](ADR/018-conversation-identity-and-recovery.md) ghi identity/ownership và reload credential; [ADR-121](ADR/121-authenticated-bounded-stateless-inference.md) ghi việc bảo vệ chat trước body parsing. [D82 security review](progress/D82_THREAT_MODEL_SECURITY_REVIEW.md) và [receipt](evidence/d82-security-verification.json) giữ kết quả lịch sử 19 test mới/174 test liên quan PASS, gồm HTTP/TCP bằng process Uvicorn tạm và gateway fixture. Đây không phải chứng nhận penetration test độc lập hoặc cho phép đưa API lên Internet.

Kiểm tra lại khi cập nhật tài liệu ngày 2026-11-10: lệnh bốn file test ở trên cho **35 PASS, 0 FAIL, 0 SKIP trong 1.07 s**. Đây là kiểm thử phần mềm với credential tạm và gateway fixture, không có lượt inference thật, tải model hoặc khởi động lại dịch vụ đang dùng.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">3. Conversation</h2></summary>

**Mục đích:** Lưu và tiếp tục hội thoại theo đúng người dùng, quản lý lịch sử/context, tránh xử lý trùng yêu cầu và giữ trạng thái nhất quán khi inference lỗi, bị hủy hoặc worker chết.

Khác với chat stateless ở phần 1–2, đường Conversation lưu transcript và trạng thái inference trong PostgreSQL. Đây không phải long-term memory hay RAG; các component đó có nguồn dữ liệu và policy riêng.

### 3.1. Các module tham gia

| Module | Trách nhiệm |
|---|---|
| [Conversation routes](../apps/api/routes/conversations.py) | Schema HTTP, local/bearer guard, CRUD, lịch sử và gửi tin nhắn. |
| [ConversationService](../apps/api/services/conversations.py) | Gắn principal vào service theo request, xử lý lifecycle và chọn profile/preset đã lưu. |
| [ConversationManager](../src/application/services/conversation_manager.py) | Reservation/finalization, idempotency, heartbeat, cancellation và recovery. |
| [Context selection](../src/application/services/conversation_context.py) | Chọn nguyên lượt user/assistant và bỏ lượt cũ để vừa token budget. |
| [LlamaInferenceAdapter](../src/infrastructure/inference/llama_adapter.py) | Chuẩn bị context, gọi gateway và trả completion đã kiểm tra. |
| [Conversation repository](../src/infrastructure/repositories/conversation_repository.py) | Lưu hội thoại, lọc owner, khóa row và archive/soft-delete. |
| [Message repository](../src/infrastructure/repositories/message_repository.py) | Gán sequence, lưu tin nhắn, đọc lịch sử và tìm request key. |
| [Inference-run repository](../src/infrastructure/repositories/inference_run_repository.py) | Lưu kết quả, token/latency metadata và kiểm tra lease theo đồng hồ database. |
| [Database connection](../src/infrastructure/database/connection.py) | Tạo async engine/session với pool có giới hạn và ẩn SQL parameters. |

### 3.2. Dữ liệu được lưu và phạm vi sở hữu

| Dữ liệu trong schema `assistant` | Nội dung chính |
|---|---|
| `conversations` | UUID, title, profile, preset mặc định, trạng thái `active`/`archived`, timestamps và `deleted_at`. Owner UUID hiện nằm trong JSONB metadata. |
| `messages` | UUID, conversation UUID, sequence tăng dần, role, content và request key/metadata nội bộ. |
| `inference_runs` | User/assistant message IDs, model, preset yêu cầu/thực tế, trạng thái `pending`/`completed`/`failed`/`interrupted`, usage và thời gian. |

Principal từ bearer quyết định owner; client không được tự gửi `owner_id` hoặc metadata để nhận quyền. Đọc, sửa, gửi, replay và recovery đều được lọc theo owner của hội thoại. UUID không thuộc người gọi được che bằng `404`, không trả transcript của người khác. Hội thoại cũ không có owner giữ nguyên và bị ẩn khỏi HTTP, không được tự gán cho principal mới.

Ownership hiện được kiểm tra trong application bằng JSONB, không phải PostgreSQL Row-Level Security. Repository không truyền owner chỉ dành cho code maintenance được tin cậy, không phải đường bỏ qua xác thực cho client.

Transcript giữ content và khoảng trắng. HTTP không trả fingerprint, lease metadata hoặc reasoning trace; `reasoning_content` không được adapter lưu vào lịch sử. Các trường `input_tokens`, `output_tokens`, `reasoning_tokens`, `latency_ms` có thể `null` nếu nguồn không cung cấp. `latency_ms` đo trong adapter, gồm chuẩn bị context và completion, không gồm toàn bộ transaction/HTTP; nó không phải TTFT. Reply HTTP hiện trả IDs, content, model, preset và `cached`, không phải endpoint đọc toàn bộ metrics của inference run.

### 3.3. Hợp đồng API

Mọi đường dẫn dưới đây có prefix `/api/v1/conversations`, yêu cầu direct localhost, bearer hợp lệ và storage đã cấu hình.

| Method và path tương đối | Chức năng |
|---|---|
| `POST /` | Tạo hội thoại; trả `201`. Body nhận `title`, `profile`, `preset_default`. |
| `GET /` | Liệt kê; mặc định `limit=50`, tối đa 100; `offset=0`; chỉ lấy active nếu không bật `include_archived`. |
| `GET /{id}` | Đọc hội thoại còn hiển thị, kể cả archived. |
| `PATCH /{id}` | Đổi `title` hoặc `preset_default` của hội thoại active; không đổi profile. |
| `GET /{id}/messages` | Đọc lịch sử theo sequence tăng dần; mặc định 100, tối đa 500; `after_sequence` là cursor loại trừ. |
| `POST /{id}/messages` | Gửi tin nhắn và đợi completion hoặc nhận replay đã lưu. |
| `POST /{id}/archive` | Archive khi không có inference pending; vẫn giữ và đọc được lịch sử. |
| `DELETE /{id}` | Soft-delete; trả `204`, ẩn hội thoại/lịch sử, không xóa vật lý bản ghi. |

Hai dòng root trong bảng là đúng path `/api/v1/conversations`, không cần dấu `/` cuối. Không có endpoint unarchive, đổi profile, hard-delete hoặc cancel/recover riêng trong router hiện tại.

Title dài 1–200 ký tự nếu được gửi. Tạo mới mặc định `profile="core"`, `preset_default="balanced"`; bước tạo không gọi model. Body gửi tin nhắn nhận `content`, `preset`, `request_key`, `temperature`, `max_tokens`. Content không được rỗng/toàn khoảng trắng; request key dài 1–128 ký tự; temperature 0–2 và max tokens 1–32.768 trước bước kiểm tra budget thực tế. Các schema này từ chối field ngoài hợp đồng.

Nếu không gửi preset của lượt hiện tại, service dùng `preset_default` đã lưu. Profile lấy từ hội thoại, không lấy từ body gửi tin nhắn. Model alias chưa nạp vẫn có thể làm lượt gửi thất bại; tạo hội thoại thành công không chứng minh backend sẵn sàng.

### 3.4. Luồng gửi tin nhắn và chống xử lý trùng

```text
Xác thực owner → đọc profile/preset của hội thoại
  → Khôi phục lease đã hết hạn của hội thoại này, nếu có
  → Transaction A: khóa hội thoại active
      → Kiểm tra request key và pending run
      → Lưu user message + reservation/lease → commit
  → Ngoài transaction: fit context theo token budget → gọi model + heartbeat
  → Kiểm tra completion, model và preset
  → Transaction B: khóa lại hội thoại + kiểm lease
      → Lưu assistant message + complete run → commit
  → Trả reply có IDs và cached=false
```

Không giữ transaction database mở trong suốt thời gian model suy luận. Chỉ một inference được pending trên mỗi hội thoại; update/archive/delete gặp pending bị từ chối `409 conversation_busy`. Điều này không chứng nhận tổng tải đồng thời hoặc vận hành nhiều worker.

Client nên giữ một `request_key` ổn định cho một lượt gửi cần chống trùng. Fingerprint gồm content nguyên văn, profile, preset sau khi giải quyết mặc định, temperature và max tokens:

- Cùng key và fingerprint, lượt trước đã completed: trả nguyên câu trả lời/IDs đã lưu với `cached=true`, không gọi model lại.
- Cùng key nhưng đổi tham số: `409 idempotency_conflict`.
- Cùng key khi lượt trước pending/failed/interrupted: `409 request_already_exists`, không tự retry inference.
- Không gửi key: không có bảo đảm replay theo key; gửi lại có thể thành lượt mới.

Key có phạm vi trong từng hội thoại. Nếu muốn chủ đích thử lại sau thất bại, kiểm tra lịch sử/trạng thái và gửi một key mới; không đổi key tự động chỉ để né kết quả chưa rõ của request trước.

### 3.5. Lịch sử và context đưa vào model

Repository đọc tối đa 24 tin non-system mới nhất theo cấu hình mặc định của manager, cùng các system instructions đã có, thay vì chỉ đọc trang lịch sử đầu. Sau đó chọn những cặp user/assistant liền nhau hoàn chỉnh và tin user hiện tại; số tin thực tế có thể ít hơn 24. Những user turn cũ chưa có assistant không được ghép thành cặp giả.

Adapter giải quyết Auto một lần rồi dùng template/tokenizer của backend để tính budget như phần 1. Nếu vượt, bỏ cặp lịch sử cũ nhất cho tới khi vừa; giữ system và tin hiện tại. Không cắt chữ giữa tin nhắn, không xóa transcript và không tự tạo summary. Output budget sai bị từ chối trước khi bỏ lịch sử; nếu riêng system + tin hiện tại vẫn không vừa thì trả `422 context_overflow`.

Phân trang lịch sử và context là hai việc khác nhau: `GET messages?limit=500` không có nghĩa model nhận đủ 500 tin. Tin không được đưa vào context vẫn còn trong database và có thể đọc qua API nếu hội thoại còn hiển thị.

### 3.6. Hủy, lease và khôi phục

Manager mặc định cấp lease **120 giây**, heartbeat mỗi **30 giây**, dùng `clock_timestamp()` của PostgreSQL. Đây là thời gian giữ quyền xử lý, không phải timeout model, SLO hoặc giới hạn 4 giây của voice.

| Tình huống | Xử lý hiện có |
|---|---|
| Completion chưa hoàn chỉnh, lỗi backend/model/preset | Ghi `failed` bằng transaction riêng khi có thể; không thêm assistant giả. User message đã commit vẫn được giữ. |
| Coroutine request bị cancel | Hủy/join task inference và heartbeat; cố ghi `interrupted` với `request_cancelled`. |
| Worker chết trước khi cleanup | Sau khi lease hết hạn, lần gửi tiếp theo hoặc lời gọi nội bộ `recover_expired(id)` chuyển reservation sang `interrupted`. |
| Heartbeat lỗi/mất quyền lease | Dừng inference coroutine; không chấp nhận kết quả muộn từ owner đã mất lease. |
| Legacy pending không có lease owner | Giữ nguyên; operator phải xác minh trước khi sửa thủ công. |

Recovery là lazy theo hội thoại, không có startup sweep toàn bảng và không tự chạy lại prompt. Lease vẫn còn hạn không bị suy đoán là worker đã chết. Nếu cleanup ghi trạng thái lỗi thất bại, reservation đã commit vẫn có lease để phục hồi về sau.

Router không có nút/API cancel riêng; đóng tab hoặc mất kết nối client không được coi là bằng chứng coroutine server đã bị hủy hay GPU đã dừng. Không sửa trực tiếp trạng thái pending hoặc xóa row để vượt guard khi chưa kiểm tra worker.

### 3.7. Setup storage và chạy Conversation

Dùng lại setup inference ở mục 1.8 và auth ở phần 2. Conversation cần thêm PostgreSQL, không cần cờ `ASSISTANT_CONVERSATION_ENABLED`:

1. Dùng database `local_assistant`, schema `assistant` trên instance PostgreSQL dùng chung; host port hiện tại là 5433. Không tạo một container/database thay thế để chạy thử.
2. Lấy runtime credential từ Vault KV v2 `secret/server/local-assistant/postgresql`: `username`, `password`, `host`, `port`, `database`. Role API là `local_assistant_app`, không dùng superuser hoặc role migrator cho API.
3. Schema phải được provision/migrate trước khi chạy. Head migration trong checkout là `0006`; API không tự tạo schema hoặc chạy migration. Với môi trường mới, operator dùng quy trình migration riêng bằng `local_assistant_migrator`; không chạy migration tùy tiện trên instance đang dùng. [Runbook](progress/CONVERSATION_API_LOCAL_RUNBOOK.md) ghi prerequisite và role tương ứng.
4. Cấp `DATABASE_URL` qua môi trường terminal, định dạng `postgresql+psycopg://<user>:<password>@<host>:5433/local_assistant`; percent-encode thành phần credential có ký tự đặc biệt. API không tự đọc `.env` hoặc Vault.

Ví dụ nhập kín URL đã chuẩn bị, rồi khởi động API ở thư mục repository:

```bash
read -rs DATABASE_URL
export DATABASE_URL
export ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json"
uv run --no-sync uvicorn apps.api.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Không paste credential trực tiếp vào câu lệnh hoặc đưa URL vào log. Thiếu `DATABASE_URL` thì Conversation trả `503 storage_unavailable` sau xác thực; health/chat stateless vẫn có thể hoạt động. Pool hiện có size 5, overflow tối đa 5, pool timeout 10 giây và pre-ping; không diễn giải thành mức concurrency inference đã chứng nhận. API lifespan đóng pool khi shutdown.

### 3.8. Ví dụ tạo, gửi, replay và đọc lịch sử

Chạy ở terminal client sau khi API/database/CORE đã sẵn sàng. Ví dụ tạo một hội thoại mới thuộc principal, sinh **một** câu trả lời, replay cùng request key rồi archive. Đây là thao tác lưu dữ liệu/inference thật khi operator chạy; đoạn hướng dẫn không được thực thi trên database khi viết tài liệu.

```bash
uv run --no-sync python - <<'PY'
"""Exercise a persistent conversation and replay without exposing its credential."""
import getpass
import logging
import httpx

logging.basicConfig(level=logging.INFO)
token = getpass.getpass("API token from Vault: ")
with httpx.Client(
    base_url="http://127.0.0.1:8000/api/v1",
    headers={"Authorization": "Bearer " + token},
    trust_env=False,
    timeout=1200,
) as client:
    response = client.post("/conversations", json={
        "title": "Conversation smoke", "profile": "core", "preset_default": "fast",
    })
    response.raise_for_status()
    identifier = response.json()["id"]
    logging.info("conversation_demo_created conversation_id=%s", identifier)
    request = {
        "content": "Say hello in one short sentence.",
        "preset": "fast", "request_key": "smoke-turn-001", "max_tokens": 512,
    }
    first = client.post(f"/conversations/{identifier}/messages", json=request)
    first.raise_for_status()
    reply = first.json()
    print(reply["content"])
    replay = client.post(f"/conversations/{identifier}/messages", json=request)
    replay.raise_for_status()
    cached = replay.json()
    assert cached["cached"] is True
    assert cached["inference_run_id"] == reply["inference_run_id"]
    assert cached["assistant_message_id"] == reply["assistant_message_id"]
    assert cached["content"] == reply["content"]
    history = client.get(f"/conversations/{identifier}/messages", params={"after_sequence": 0})
    history.raise_for_status()
    assert [item["role"] for item in history.json()] == ["user", "assistant"]
    archived = client.post(f"/conversations/{identifier}/archive")
    archived.raise_for_status()
    assert archived.json()["status"] == "archived"
    retained = client.get(f"/conversations/{identifier}/messages")
    retained.raise_for_status()
    assert len(retained.json()) == 2
    logging.info("conversation_demo_verified conversation_id=%s cached=true messages=2 archived=true", identifier)
PY
```

Ghi lại UUID từ log client để đọc lại bằng `GET /api/v1/conversations/{id}` hoặc liệt kê với `include_archived=true`. Archived không gửi thêm được; muốn tiếp tục một cuộc trao đổi mới thì tạo hội thoại active mới. Xóa qua API chỉ soft-delete; retention, hard purge và adoption dữ liệu cũ là quyết định vận hành riêng.

### 3.9. Kiểm thử và giới hạn kết quả

Chạy kiểm thử phần mềm không cần database/model thật:

```bash
env -u DATABASE_URL uv run --no-sync python -m pytest \
  tests/test_conversation_api.py tests/test_conversation_context.py \
  tests/test_llama_adapter.py tests/test_conversation_auth.py -q
```

Kiểm tra ngày 2026-11-10: **69 PASS, 0 FAIL, 0 SKIP trong 0.91 s**. Phạm vi gồm hợp đồng HTTP/lifecycle, ownership dependency, lỗi an toàn, lựa chọn context, budget và completion adapter bằng fixture/mock. Đây không phải lượt kiểm chứng mới trên database thật hoặc chất lượng model.

[ADR-016](ADR/016-conversation-http-composition.md), [ADR-017](ADR/017-conversation-hardening.md) và [ADR-018](ADR/018-conversation-identity-and-recovery.md) giữ các quyết định và thứ tự bổ sung HTTP, lease/context, identity/recovery. ADR-018 ghi checkpoint D15 lịch sử **151/151 PASS**, có PostgreSQL/CORE, isolation, pool và recovery; các giới hạn PARTIAL trong ADR-016/017 được phần superseding của chúng cập nhật, không phải trạng thái D15 hiện tại.

Các test thật nằm tại [manager integration](../tests/integration/test_conversation_manager.py), [hardening integration](../tests/integration/test_conversation_hardening.py), [ownership integration](../tests/integration/test_conversation_ownership.py) và [HTTP persistence](../tests/integration/test_conversation_http_persistence.py). Chúng cần prerequisite riêng, có thể tạo/xóa dữ liệu probe và có test dùng CORE; không chạy chỉ để kiểm tra định dạng tài liệu. Không tính SKIP thành PASS hoặc lấy 69 fixture tests thay cho các gate đó. Multiworker/public deployment, off-host recovery và production load/SLO vẫn nằm ngoài phạm vi đã xác minh ở đây.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">4. Document pipeline</h2></summary>

**Mục đích:** Nhận và lưu file theo đúng chủ sở hữu, kiểm tra tính toàn vẹn/định dạng, rồi cung cấp các thao tác đọc, trích xuất, sửa có giới hạn và OCR với nguồn gốc rõ ràng.

Upload thành công không tự đính kèm file vào hội thoại, tạo embedding, index Qdrant hoặc gọi model. Chunking/indexing/retrieval thuộc **phần 5. RAG / Knowledge** theo bảng component; phần này mô tả việc nhận và xử lý file nguồn.

### 4.1. Các module tham gia

| Module | Trách nhiệm |
|---|---|
| [File routes](../apps/api/routes/files.py) | Reservation, upload raw bytes, metadata/download/delete, PDF extract và DOCX read/rewrite. |
| [XLSX routes](../apps/api/routes/xlsx.py), [OCR routes](../apps/api/routes/ocr.py) | Hợp đồng workbook và OCR từng trang. |
| [FileService](../apps/api/services/files.py) | Điều phối quota/lease, xác minh file, khóa nguồn, processor và recovery. |
| [Storage policy](../src/application/services/file_storage_policy.py) | Filename, extension, dung lượng, concurrency và hạn mức upload. |
| [File journal](../src/infrastructure/repositories/file_journal.py) | Trạng thái file và counters quota trong PostgreSQL. |
| [LocalBlobStorage](../src/infrastructure/local_blob_storage.py) | Blob/staging trên đĩa, namespace identity, descriptor/lock và durable publication. |
| [File verifier](../src/infrastructure/file_verifier.py) | Kiểm tra nội dung qua sandbox thay vì tin extension/Content-Type từ client. |
| [PDF extractor](../src/infrastructure/pdf_extractor.py) | Đọc native text theo trang bằng pypdf trong worker cô lập. |
| [DOCX processor](../src/infrastructure/docx_processor.py), [XLSX processor](../src/infrastructure/xlsx_processor.py) | Đọc cấu trúc OOXML và tạo bản sửa trong phạm vi contract. |
| [Page OCR](../src/infrastructure/page_ocr.py), [Vision OCR](../apps/api/services/vision_ocr.py) | Native PDF/Tesseract hoặc CORE VLM khi được chọn tường minh. |
| [Sandbox process](../src/infrastructure/sandbox_process.py) | Giới hạn vòng đời worker/namespace và hoàn tất cleanup trước khi trả timeout. |

### 4.2. File hỗ trợ và giới hạn mặc định

Policy hiện nhận `.pdf`, `.docx`, `.xlsx`, `.txt`, `.md`, `.csv`, `.png`, `.jpg`, `.jpeg`, `.webp`, trong tập con nội dung được verifier hỗ trợ. Đây không phải cam kết mở được mọi file có các extension đó. Tên hiển thị không được làm đường dẫn; storage key/UUID/owner do server cấp. Macro, mã thực thi, nội dung active/external link, mã hóa, archive/ảnh có cấu trúc ngoài giới hạn có thể bị từ chối.

| Hạn mức trong `StoragePolicy` | Mặc định |
|---|---:|
| Metadata reservation JSON | 8 KiB |
| Một file | 25 MiB; không nhận file rỗng |
| Quota mỗi owner / toàn hệ thống | 1 GiB / 10 GiB |
| Số file mỗi owner / toàn hệ thống | 1000 / 10.000 |
| Upload đang hoạt động mỗi owner / toàn hệ thống | 2 / 4 |
| Dung lượng đĩa trống dự phòng | 2 GiB |
| Chunk ghi blob | 64 KiB |
| Reservation / tổng thời gian upload | 300 s / 300 s |
| Chờ dữ liệu upload | Tối đa 30 s mỗi lần chờ chunk |
| Upload lease / heartbeat | 60 s / 15 s |
| Archive expansion / số entry / compression ratio | 100 MiB / 1000 / 100 |

MiB/GiB là đơn vị nhị phân. Đây là policy admission, không phải số đo RAM, tốc độ hoặc SLO. Quota giữ cả reservation, staging và tài nguyên đang chờ purge; chỉ hết lease không đủ để trả quota khi byte/lock còn tồn tại.

Các processor có admission riêng trong một service process: PDF extract tối đa 2, DOCX 2, XLSX 2, OCR 1; quá mức trả `429`, không xếp hàng vô hạn. Các slot không phải cam kết throughput tổng của hệ thống.

### 4.3. Luồng upload và vòng đời file

```text
Local + bearer → POST /files: filename, size_bytes, sha256, request_key tùy chọn
  → Kiểm metadata, quota và free space → reserved
  → PUT /files/{id}/content: raw bytes
      → Claim lease/lock → receiving → ghi staging có giới hạn
      → Đối chiếu size/hash → verifying → kiểm định dạng trong sandbox
      → Durable publish → ready
  → Client chủ động gọi download/extract/read/OCR khi cần
```

Không dùng multipart ở bước PUT. `Content-Length` chỉ là khai báo bổ sung; server vẫn đếm byte và kiểm SHA-256 thật, không tin filename/MIME tự khai. Blob ready là bất biến: PUT lần nữa bị xung đột, không ghi đè nguồn.

Reservation có request key: cùng owner/key và khai báo tương đương có thể nhận lại reservation còn hạn hoặc file ready mà không tính quota hai lần. Đổi khai báo hoặc dùng lại terminal key bị từ chối. Khi chưa rõ kết quả upload đã thành công chưa, đọc metadata/download để xác nhận; không tự PUT lại lên một file ready.

Lỗi hoặc hủy upload đi qua cleanup/purge; trạng thái cuối có thể là `rejected`, `interrupted` hoặc `deleted`, tùy nguyên nhân. `DELETE` chỉ trả `204` sau physical purge; nếu reader/processor còn giữ khóa hoặc cleanup chưa xong, trả `202` với `state="purging"` và vẫn giữ quota. Không coi xóa file giống soft-delete hội thoại ở phần 3.

### 4.4. API đọc và xử lý nội dung

Các path sau có prefix `/api/v1/files`, cùng local/bearer và owner policy của phần 2:

| Method và path tương đối | Kết quả |
|---|---|
| `POST` root | Reserve metadata; `201`. Root chính xác là `/api/v1/files`. |
| `PUT /{id}/content` | Upload raw bytes; `200` sau verify/publication. |
| `GET` root, `GET /{id}` | Metadata owner-scoped; list mặc định 50, tối đa 100, có offset. |
| `GET /{id}/content` | Download ready blob, private attachment với `nosniff`, size/hash được kiểm trước khi gửi header. |
| `DELETE /{id}` | Purge; `204` hoàn tất hoặc `202` còn chờ. |
| `POST /{id}/extract` | Native PDF text từng trang, không có request body. |
| `POST /{id}/docx/read`, `POST /{id}/docx/rewrite` | JSON cấu trúc hoặc DOCX attachment mới. |
| `POST /{id}/xlsx/read`, `POST /{id}/xlsx/rewrite` | JSON workbook hoặc XLSX attachment mới. |
| `POST /{id}/ocr?page=1&mode=auto` | Một trang PDF/ảnh với text, provenance và uncertainty. |

Nguồn phải thuộc owner, đúng namespace, ở trạng thái ready và khớp size/hash. Processor giữ reader/slot qua phần công việc được quản lý; DOCX/XLSX/OCR còn giữ tới hết response/cancellation. Nguồn thay đổi hoặc bị xóa trong lúc xử lý sẽ bị kiểm tra lại thay vì trả kết quả từ nguồn không còn hợp lệ.

Kết quả đọc có `file_id`, source SHA-256, processor/version và `content_trust="untrusted"`. Locator giữ nơi lấy dữ liệu: PDF/OCR dùng `file:<uuid>#page=<n>`, DOCX dùng paragraph/table, XLSX dùng sheet/cell. Text từ tài liệu là dữ liệu nguồn, không phải lệnh cấp quyền cho model/tool.

#### PDF native text

`/extract` trả page number một-based, text và trạng thái `native_text` hoặc `no_native_text`; trang không có native text vẫn giữ vị trí. `no_native_text` không chứng minh trang trống và không tự chạy OCR. Giới hạn gồm 1000 trang, 128 KiB UTF-8 text/trang và 1 MiB/document; vượt giới hạn bị từ chối thay vì cắt âm thầm. Reading order/font mapping có phạm vi hữu hạn; native text không tự khôi phục layout hoặc lưới bảng.

#### DOCX read/rewrite

Read trả paragraph, direct run, style và bảng main body. Rewrite chỉ đổi text của những direct run hợp lệ đã tồn tại, không nhận XML tùy ý hay tạo paragraph/table mới. Chọn `paragraph_id`/`run_index` từ read response; chỉ số một-based trong ví dụ cần thay bằng target thực tế:

```json
{
  "source_sha256": "<source SHA-256 from the read response>",
  "edits": [{"paragraph_id": 2, "run_index": 1, "text": "Updated text"}]
}
```

Plan tối đa 64 KiB, 1–100 target không trùng; hash nguồn cũ trả `409`. Paragraph có cấu trúc không hỗ trợ chỉnh như field/drawing/hyperlink/tracked changes có thể bị từ chối. Header/footer và phần package ngoài phạm vi không được coi là text đã trích xuất; không tính layout/style inheritance như Word.

Rewrite trả attachment mới cùng hash nguồn/output; nguồn không đổi, output chưa được lưu hoặc tính thành file mới trong journal. Nếu muốn lưu, dùng reservation/upload bình thường. Các package member không sửa được giữ nguyên byte theo contract, không tuyên bố mọi file Word bất kỳ sẽ roundtrip được.

#### XLSX read/rewrite

Read phân biệt literal value, formula và cached value; không chạy Excel/LibreOffice, macro hoặc tính công thức. Rewrite chỉ sửa literal cell đã tồn tại, không sửa formula cell. Chọn sheet/cell từ read response, ví dụ:

```json
{
  "source_sha256": "<source SHA-256 from the read response>",
  "edits": [{"sheet_id": 1, "cell": "B2", "kind": "number", "value": "42"}]
}
```

`kind` nhận `string`, `number`, `boolean`; number được truyền bằng chuỗi số hợp lệ, boolean bằng JSON boolean. Plan tối đa 64 KiB, 1–100 target không trùng. Công thức/style/package không thuộc target được giữ theo contract. Header `X-Formula-Cache-Status: preserved_not_recalculated` có nghĩa cached formula có thể cũ sau khi đổi literal; không dùng cached value như kết quả vừa tính. Attachment mới không tự ghi đè hoặc được lưu thành file nguồn mới.

#### OCR và CORE VLM

| Mode | Đường xử lý |
|---|---|
| `auto` | PDF có native text: trả native text; nếu không, render trang rồi Tesseract. Ảnh đi Tesseract. |
| `ocr` | Render/chuẩn hóa rồi Tesseract, kể cả PDF có native text. |
| `vlm` | Render/chuẩn hóa rồi gọi đúng CORE đang nạp với mmproj; không chọn model khác. |

`auto` **không tự chuyển sang VLM khi OCR kém**. Tesseract hiện hardcode `eng`; cài thêm language pack không tự bật tiếng Việt. VLM dùng model/projector đã có, không tải hoặc thay model; cần khởi động CORE có vision theo mục 1.8. Không dùng launcher text-only làm bằng chứng VLM đã hoạt động.

OCR nhận một trang mỗi request, page 1–1000 theo số trang thực tế; ảnh chỉ có trang 1. Word boxes dùng tọa độ rendered pixels, không phải tọa độ PDF gốc. Engine score Tesseract không phải xác suất đúng đã hiệu chuẩn. CORE trả confidence `null`, luôn cần review và bảng mang nhãn `unverified_vlm`; không được nâng dữ liệu này thành bảng đã xác nhận chỉ vì JSON hợp lệ. Kết quả không có text cũng chưa chứng minh ảnh trống.

### 4.5. Setup và kích hoạt

Dùng dependency `uv sync --locked --dev` ở mục 1.8, database/role ở mục 3.7 và bearer file ở phần 2. File service mặc định tắt; cần schema tương thích V002 trở lên mà code cho phép: `0002`–`0006`. Head của checkout hiện là `0006`; không downgrade schema đang có để khớp một runbook lịch sử.

Đường native cần `/usr/bin/bwrap` và unprivileged namespaces hoạt động. PDF/image OCR còn cần Poppler `pdftoppm`, Tesseract và dữ liệu `eng`. Trên máy Ubuntu mới chưa có các công cụ này, chuẩn bị dependency hệ thống:

```bash
sudo apt-get update
sudo apt-get install bubblewrap poppler-utils tesseract-ocr tesseract-ocr-eng
command -v bwrap pdftoppm tesseract
tesseract --list-langs
```

Không có isolation thì verifier/processor từ chối, không fallback sang parse file không cô lập trong API. Sandbox nhận nguồn readonly và runtime/code cần thiết, không nhận credential API/database, mạng hoặc toàn bộ host filesystem. Worker native có cap address space 512 MiB; đó không phải RAM RSS đo được hay VRAM. Wall timeout theo giai đoạn: verifier/PDF/DOCX/XLSX 10 s, OCR preparation 25 s; gọi CORE VLM có timeout riêng 45 s, không phải SLO cho toàn request.

Chuẩn bị thư mục cha `data/` rồi chạy từ repository, sau khi `DATABASE_URL` đã được cấp kín:

```bash
mkdir -p data
export ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json"
export ASSISTANT_FILES_ENABLED=1
export ASSISTANT_FILES_ROOT="$PWD/data/files"
uv run --no-sync uvicorn apps.api.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Service có thể tạo root cuối khi chưa tồn tại; root phải thuộc UID API, private `0700`, không đi qua symlink, blob private `0600`. `.storage-namespace` gắn thư mục với journal. Không thay root bằng một thư mục rỗng khi principal đang có allocation; startup từ chối namespace mismatch. Giữ marker và resource-lock directories khi backup/restore.

Không cần model để upload, PDF native, DOCX/XLSX hoặc Tesseract. Chỉ mode VLM cần CORE vision. Bật files không tự bật ingestion/retrieval/grounded hoặc tạo Qdrant collection. API không tự chạy migration hay tạo PostgreSQL/Vault mới.

### 4.6. Ví dụ upload và trích xuất PDF

Ví dụ dùng PDF fixture đã có trong repo, không cần tải tài liệu ngoài. Mỗi lần operator chạy tạo một file riêng trong storage/quota; không tự xóa dữ liệu sau demo. Đoạn này chưa được chạy trên database khi viết tài liệu.

```bash
uv run --no-sync python - <<'PY'
"""Upload a trusted PDF fixture and verify its download and native extraction."""
import getpass
import hashlib
import logging
from pathlib import Path
from uuid import uuid4
import httpx

logging.basicConfig(level=logging.INFO)
source = Path("tests/fixtures/pdf/native-pages.pdf")
payload = source.read_bytes()
digest = hashlib.sha256(payload).hexdigest()
token = getpass.getpass("API token from Vault: ")
with httpx.Client(
    base_url="http://127.0.0.1:8000/api/v1",
    headers={"Authorization": "Bearer " + token},
    trust_env=False,
    timeout=300,
) as client:
    reserved = client.post("/files", json={
        "filename": source.name, "size_bytes": len(payload), "sha256": digest,
        "request_key": "document-smoke-" + str(uuid4()),
    })
    reserved.raise_for_status()
    identifier = reserved.json()["id"]
    logging.info("document_demo_reserved file_id=%s", identifier)
    uploaded = client.put(f"/files/{identifier}/content", content=payload,
                          headers={"Content-Type": "application/octet-stream"})
    uploaded.raise_for_status()
    assert uploaded.json()["state"] == "ready"
    downloaded = client.get(f"/files/{identifier}/content")
    downloaded.raise_for_status()
    assert hashlib.sha256(downloaded.content).hexdigest() == digest
    extracted = client.post(f"/files/{identifier}/extract")
    extracted.raise_for_status()
    result = extracted.json()
    assert result["file_id"] == identifier and result["sha256"] == digest
    assert result["content_trust"] == "untrusted"
    logging.info("document_demo_verified file_id=%s bytes=%d pages=%d",
                 identifier, len(payload), len(result["pages"]))
PY
```

Client demo đọc fixture nhỏ vào RAM cho gọn; đây không phải hướng dẫn nạp mọi file lớn vào RAM phía server. API PUT vẫn nhận raw stream có giới hạn. Ghi lại file UUID từ log để đọc metadata/download hoặc chủ đích gọi DELETE sau demo; nếu nhận `202`, đợi/recheck cleanup thay vì tự trả quota hay xóa blob thủ công.

### 4.7. Kết quả đo đã lưu

[D23 mixed-document evaluation](progress/DOCUMENT_PIPELINE_EVALUATION.md) ghi **18/18 case gates**, gồm 11 accepted projections, 3 empty, 1 degraded và 3 expected rejections; 56/56 source fields được phủ, 32 chunks/7 empty records. Tổng thời gian corpus tuần tự **6401.331 ms** gồm verification, parse, mở kiểm tra độc lập, chunk repeat và scoring; không phải latency một request hay throughput production. Case OCR mờ vẫn CER/WER 1.0, không được đổi nhãn thành nhận dạng đúng để gọi gate PASS. Chunk metrics ở đây thuộc corpus liên thông D23, không chứng minh upload tự index.

[D62 OCR/CORE quality report](progress/D62_NATIVE_CORE_OCR_QUALITY.md) giữ lượt đo lịch sử trên corpus tự soạn nhỏ; native và CORE dùng nguồn/mode đã khai báo, không phải benchmark model thay thế:

| Case | Native CER / WER | CORE CER / WER | Native wall | CORE wall |
|---|---:|---:|---:|---:|
| PDF ASCII có text | 0 / 0 | 0 / 0 | 0.165 s | 3.838 s |
| Ảnh tiếng Anh rõ | 0 / 0 | 0 / 0 | 0.315 s | 0.892 s |
| Bảng tiếng Việt | 0.25 / 0.75 | 0 / 0 | 0.315 s | 1.583 s |
| Text mờ | 1.0 / 1.0 | 0.285714 / 0.5 | 0.265 s | 0.886 s |

CER/WER là tỷ lệ lỗi ký tự/từ theo oracle của bộ đó; thấp hơn tốt hơn. CORE giữ đúng 6 cell ở **một** bảng tiếng Việt, không chứng minh mọi bảng đều đúng. Cả lỗi OCR/VLM mờ và các lượt thất bại ban đầu được giữ nguyên trong evidence. Các số wall gồm preparation + inference của mode tương ứng, không gồm bước query tài nguyên riêng; không phải TTFT và không được coi là số đo lại cho source hiện tại.

Trong 32 điểm before/after của D62, CORE resident có RSS RAM **9426.879–9763.918 MiB**, GPU allocation **9234–9380 MiB**. CORE vẫn nạp cả khi native OCR chạy, nên không gán lượng VRAM này thành chi phí Tesseract. Đây không phải true peak hoặc yêu cầu RAM/VRAM tối thiểu; RSS worker native chưa được lấy mẫu. Corpus/warm/cache và authored labels giới hạn khả năng suy rộng; chưa có population p95, cold-start hay load SLO từ các số này.

### 4.8. Lỗi, recovery và bảo toàn nguồn

| HTTP | Ví dụ tình huống |
|---|---|
| 401 / 403 | Credential hoặc local/origin/proxy boundary không đạt. |
| 404 | File không hiển thị cho owner hoặc không thuộc namespace đúng. |
| 408 | Upload/request body chờ quá thời gian cho phép. |
| 409 | File chưa ready/không claim được, lease/nguồn thay đổi hoặc xung đột request key. |
| 413 | File/metadata/parse/output/resource vượt giới hạn; timeout processor có thể dùng mã này. |
| 415 | Định dạng/nội dung không hỗ trợ, sai processor hoặc body multipart ở upload. |
| 422 | Metadata/edit/page không hợp lệ hoặc target không hỗ trợ. |
| 429 | Quota upload concurrency hoặc slot processor đã bận, tùy guard. |
| 502 / 503 | VLM reply không đạt, sandbox/storage/model không sẵn sàng hoặc nguồn không qua kiểm toàn vẹn. |

HTTP/code cụ thể phụ thuộc guard; không phải mọi quota đều trả cùng một status. Log giữ IDs/count/version và stable code, không dùng file text, filename không tin cậy hoặc credential làm nội dung audit.

Startup và vòng recovery mỗi 5 s xử lý batch journal đã biết; không glob-delete hoặc nhận nuôi file lạ. Reader/writer còn giữ lock thì cleanup tiếp tục chờ và quota còn tính. Backup phải ghép **database + blob root + namespace/principal bindings**; backup database riêng của Conversation không đủ để phục hồi file. Quy trình restore dùng target cô lập trong [file runbook](progress/FILE_STORAGE_LOCAL_RUNBOOK.md), không tự restore đè hoặc restart instance dùng chung.

### 4.9. Kiểm thử và giới hạn phạm vi

Chạy các kiểm thử policy, storage, verifier, processor/OCR và lifecycle sandbox, không cần credential database hoặc model thật:

```bash
env -u DATABASE_URL uv run --no-sync python -m pytest \
  tests/test_file_storage_policy.py tests/test_local_blob_storage.py \
  tests/test_file_verifier.py tests/test_file_schema_compatibility.py \
  tests/test_pdf_extractor.py tests/test_docx_processor.py \
  tests/test_xlsx_processor.py tests/test_page_ocr.py \
  tests/test_vision_ocr.py tests/test_sandbox_process.py -q
```

Kiểm tra ngày 2026-11-10: **403 PASS, 0 FAIL, 0 SKIP trong 45.39 s**. Có sandbox/native fixture thật cùng test/mock của vision boundary; không gọi CORE, upload vào database hoặc chạy lại benchmark D23/D62. Đây là kiểm thử phần mềm trên phạm vi mười file, không phải full regression hoặc đánh giá tài liệu bất kỳ của người dùng.

Các integration [file HTTP](../tests/integration/test_file_http.py), [PDF](../tests/integration/test_pdf_extraction_http.py), [DOCX](../tests/integration/test_docx_http.py), [XLSX](../tests/integration/test_xlsx_http.py) và [OCR](../tests/integration/test_ocr_http.py) có prerequisite riêng; không lấy kết quả fixture thay cho các gate HTTP/database/model thật.

Quyết định được ghi trong [ADR-022](ADR/022-isolated-file-verification.md), [ADR-024](ADR/024-storage-root-identity.md), [ADR-025](ADR/025-file-recovery-and-paired-restore.md), [ADR-026](ADR/026-native-pdf-extraction.md), [ADR-027](ADR/027-bounded-docx-roundtrip.md), [ADR-028](ADR/028-bounded-xlsx-roundtrip.md), [ADR-029](ADR/029-page-ocr-and-local-vision.md) và [ADR-179](ADR/179-retire-sandbox-namespace-before-timeout-returns.md). Định dạng ngoài tập con, layout rendering đầy đủ, OCR đa ngôn ngữ tự động, formula recalculation và chất lượng tổng quát vẫn không được chứng minh bởi các kết quả trên.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">5. RAG / Knowledge</h2></summary>

**Mục đích:** Biến tài liệu đã xác minh thành các đoạn nguồn có định danh, lập vector index theo đúng owner, tìm lại nguồn còn hợp lệ và tùy chọn dùng CORE để trả lời hoặc trích xuất dữ liệu có citation.

RAG không huấn luyện lại model và không tự đưa mọi file/lịch sử vào prompt. Các bước chunk, index, retrieval, grounded answer và structured extraction có API/điều kiện bật riêng. Memory dài hạn thuộc component tiếp theo, không đồng nghĩa với vector index này.

### 5.1. Các module tham gia

| Module | Trách nhiệm |
|---|---|
| [Document chunks](../src/application/services/document_chunks.py), [source adapters](../src/application/services/chunk_sources.py) | Chunk theo nội dung/cấu trúc, giữ locator, spans, quality và định danh nguồn. |
| [Chunk service](../apps/api/services/chunks.py) | Đọc lại nguồn được phép và giữ reader/slot khi tạo projection. |
| [Ingestion contract](../src/application/services/ingestion_contract.py) | Tạo manifest/job/generation/point IDs xác định và kiểm source fence. |
| [IngestionService](../apps/api/services/ingestion.py), [journal](../src/infrastructure/repositories/ingestion_journal.py) | Admission, worker, lease/retry, publication và cleanup của generation. |
| [Qwen embedding](../src/infrastructure/qwen_embedding.py), [query adapter](../src/infrastructure/qwen_query.py) | Chạy encoder CPU offline có giới hạn, kiểm fingerprint/count/vector và định dạng query. |
| [Qdrant ingestion](../src/infrastructure/qdrant_ingestion.py), [retrieval](../src/infrastructure/qdrant_retrieval.py) | Ghi/xác minh vector trong collection được quản lý; tìm ứng viên với filter do server tạo. |
| [RetrievalService](../apps/api/services/retrieval.py) | Đối chiếu active generation với SQL, tái dựng text từ nguồn và giữ quyền đọc tới lúc trả response. |
| [GroundedService](../apps/api/services/grounded.py), [answer contract](../src/application/services/grounded_answer.py) | Gọi CORE với nguồn không tin cậy và gắn citation vào đoạn nguồn hợp lệ. |
| [Structured extraction protocol](../src/application/services/grounded_extract.py), [optional app](../apps/api/grounded_extract.py) | Trích xuất field có kiểu dưới protocol D81, tách khỏi API mặc định. |

### 5.2. Embedding, collection và trạng thái lựa chọn

Nguồn quyết định hiện tại là [embedding-selected.json](../configs/embedding-selected.json) cùng [approval record](evidence/model-eval-001-selection-approval.json). D24 ban đầu chọn E5; sau đó **MODEL-EVAL-001 đã thực sự so sánh E5 với Qwen** và chủ dự án phê duyệt lựa chọn Qwen. Không diễn giải benchmark sau này thành kết quả đã có từ D24 hoặc sửa lịch sử commit `a88584b`.

| Thuộc tính | Cấu hình Qwen được chọn | E5 giữ làm rollback |
|---|---|---|
| Model | `Qwen/Qwen3-Embedding-0.6B` | `intfloat/multilingual-e5-base` |
| Revision | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | `d128750597153bb5987e10b1c3493a34e5a4502a` |
| Runtime / trọng số | PyTorch CPU / BF16 | ONNX Runtime CPU / int8 |
| Vector dimension | 1024 | 768 |
| Pooling / normalization | Last attended token float32 / L2 | Attention-mask mean / L2 |
| Runtime input cap | 512 token, gồm instruction/special tokens | 512 token theo profile E5 |
| Similarity | Cosine | Cosine |

Qwen dùng batch 4, intra-op threads 2, inter-op threads 1; không dùng GPU. Context công bố trong candidate là 32.768 token nhưng runtime của dự án vẫn chặn **512**, không được tự nâng theo giới hạn model. Query dùng đúng prefix đã pin trong config, passage prefix rỗng; không tự đổi cách xuống dòng/prefix hoặc silent truncation.

Fingerprint Qwen là `77a5716028f187821f9e6aa198b5c5774b5d69b54d95093701a7f2dfaaa0bc9b`; collection logic là `la_chunks_<fingerprint>_v1`, named vector `dense` 1024 chiều, Cosine, on-disk. [E5 rollback config](../configs/embedding-e5-rollback.json) giữ fingerprint/collection 768 chiều riêng. Không ghi vector Qwen vào collection E5 hoặc dùng một model để query vector space của model kia.

File lựa chọn vẫn ghi `selected_not_deployed`: đây là trạng thái cấu hình đã phê duyệt, không có nghĩa code ingestion/retrieval chưa được viết. Các service đã có local opt-in acceptance nhưng mặc định tắt; tài liệu này không kiểm kê collection hoặc chứng minh production đang bật. Giữ nguyên các collection/dữ liệu hiện có; đổi model/fingerprint cần benchmark, migration/reindex riêng, rollback và phê duyệt.

### 5.3. Chunking và giữ nguồn gốc

`POST /api/v1/files/{id}/chunks` chỉ tạo projection theo nguồn đang đọc, không tự lưu chunk/index. Query nhận `max_bytes` mặc định 2048, trong khoảng 256–8192; `source=auto|ocr`, `page` và `ocr_mode` điều khiển projection theo contract file. Không phải mọi lựa chọn của API chunks đều có đường index tương ứng: ingestion hiện tái dựng auto projection, không nhận chunk do client gửi.

Chunker `structured-chunks-v1` giữ paragraph/page/section và hàng bảng trong phạm vi đã hỗ trợ. Chunk có text, locator, spans theo Unicode code point, cấu trúc/quality và ID gắn với owner, namespace, file/hash, processor, chunker và options. Đổi nguồn hoặc options có thể đổi chunk ID; không dùng ID như quyền truy cập.

Hàng cấu trúc là đơn vị nguyên vẹn: quá lớn có thể trả `413`, cấu trúc chưa hỗ trợ có thể `422`, không cắt hàng âm thầm để đạt benchmark. Phân biệt:

- `max_bytes` giới hạn byte UTF-8 của chunk, không phải số token.
- Index mặc định dùng **256 byte**, khác `/chunks` mặc định 2048 byte.
- Token preflight vẫn đếm đủ input Qwen và từ chối chunk vượt 512 token; byte nhỏ không tự chứng minh token hợp lệ.
- OCR uncertainty, formula/cache/review flags được giữ, không biến thành confidence đã hiệu chuẩn.

### 5.4. Indexing và vòng đời generation

```text
File ready thuộc owner
  → POST /files/{id}/index?max_bytes=256
  → Giữ nguồn, tái dựng chunks, đếm token thật → ghi job bất biến → 202
  → Worker giữ lock namespace/model và lease theo database
      → Kiểm lại nguồn/manifest → encode CPU offline
      → Upsert điểm xác định → đọc kiểm IDs/payload/vector → activate
      → Publish active generation trong SQL
  → GET /ingestion/{job_id}: status và active
```

`202` chỉ xác nhận admission; chưa chứng minh file tìm kiếm được. Chỉ dùng generation khi job `ready` và active pointer còn hợp lệ. Cùng source/projection/model được nhận diện thành durable job thay vì tạo điểm trùng; projection khác có generation mới. Ready lịch sử không đồng nghĩa còn active.

Qdrant payload giữ owner/namespace/file/hash, fingerprint, generation, state và digest nội dung/provenance; **không giữ source text đầy đủ**. PostgreSQL journal và blob nguồn vẫn cần thiết để tái dựng kết quả. Không coi backup vector database riêng là backup Knowledge đầy đủ.

Worker kiểm lease/source/latest-request trước publication, retry có giới hạn cho các lỗi theo policy và dùng cùng deterministic point IDs khi acknowledgement chưa rõ. Không có transaction phân tán SQL–Qdrant: chỉ active pointer được publish sau kiểm tra đầy đủ. File nguồn bị xóa sẽ mất visibility qua SQL ngay; cleanup vector vật lý là bất đồng bộ và tiếp tục sweep/tombstone để xử lý late writes. Không tự xóa tombstone hoặc đánh dấu cleanup xong chỉ từ một acknowledgement.

Nguồn là bất biến: thay nội dung bằng cách upload file mới, chủ đích index rồi xử lý file cũ; không có filesystem watcher hoặc cập nhật byte tại chỗ. [Ingestion guide](progress/INCREMENTAL_INGESTION.md) ghi chi tiết lifecycle và recovery.

### 5.5. Retrieval và grounded answer

| Endpoint | Hợp đồng chính |
|---|---|
| `POST /api/v1/retrieval/search` | `query`, `top_k` mặc định 5, khoảng 1–10; `file_ids` tùy chọn 1–16 UUID duy nhất. |
| `POST /api/v1/grounded/answer` | `query`, `top_k` mặc định/tối đa 3; `file_ids` tùy chọn cùng phạm vi narrowing. |

Query phải không trắng và tối đa 4096 byte UTF-8 sau kiểm tra service. Client không được gửi owner, namespace, model, vector, generation, filter hoặc citation để cấp quyền. `file_ids` chỉ thu hẹp tài nguyên của principal đã xác thực.

Retrieval encode query với Qwen đã chọn, dùng chung encoder admission với indexing. Qdrant tìm dense candidates bằng filter server: owner + namespace + model + private + untrusted + active, thêm file scope nếu có. Candidate budget là `max(20, 5 × top_k)`, tối đa 50; score Cosine không phải xác suất câu trả lời đúng.

Mỗi candidate vẫn phải qua kiểm active generation/point membership trong SQL và tái dựng source manifest/payload từ file còn hợp lệ. Text/provenance lấy từ nguồn đã kiểm, không tin text do vector store trả. Nguồn cũ/xóa bị bỏ qua; trong budget hữu hạn có thể nhận ít hơn `top_k`, không chứng minh đã tìm hết corpus. Reader được giữ và kiểm lại trước response headers. Retrieval không tự thêm text vào chat và không có reranker/hybrid search trong đường mặc định này.

Grounded answer giữ reader qua một lượt CORE `fast`, temperature 0, max output 512; model-only timeout mặc định 60 s. Không có hit thì trả `status="no_sources"`, answer `null`, không gọi model, `answer_trust="not_generated"`. Có nguồn nhưng model từ chối đúng contract có thể trả `insufficient_evidence`.

Citation phải trỏ source ID hợp lệ và quote xuất hiện nguyên văn, duy nhất trong evidence unit; server gắn file/hash/generation/locator/span thay vì tin metadata do model tự khai. Sai JSON, quote sai/mơ hồ hoặc completion chưa xong bị từ chối; không sửa câu trả lời để vượt validator. Trả lời có `answer_trust="model_generated"`, nguồn vẫn `untrusted`: kiểm citation chứng minh vị trí quote, **không chứng minh ngữ nghĩa toàn bộ answer đúng hoặc nguồn đáng tin**.

### 5.6. Structured extraction — composition D81 tùy chọn

`POST /api/v1/grounded/extract` chỉ có khi chạy factory riêng với `ASSISTANT_GROUNDED_EXTRACT_ENABLED=1`; không tự xuất hiện trong `apps.api.main:app`. Đây là protocol hẹp `d81-grounded-extract-v1`, không phải endpoint tự nhận mọi JSON schema.

Body nhận query và 1–3 field `{name, type, file_id}`; type chỉ `string` hoặc `integer`. Tên field và file UUID phải khác nhau giữa các field: hiện mỗi file chỉ được gán một field. Body tối đa 16 KiB; tên theo identifier contract, không dùng tên dành riêng `citations`.

Retrieval phải tìm đúng một plain chunk cho mỗi file được khai báo. Structured table/cell provenance, thiếu/trùng chunk/file hoặc text vượt bound bị từ chối trước model; không nối/sửa nguồn để hợp thức hóa. Query chỉ dùng tìm nguồn; prompt extraction được server tạo từ field contract và nguồn đã bind, không đưa nguyên query thành lệnh tự do cho model.

Ví dụ hình dạng request, cần thay UUID bằng nguồn thực tế đã index:

```json
{
  "query": "Mã phiên bản được ghi trong tài liệu",
  "fields": [
    {"name": "release", "type": "string", "file_id": "<owned file UUID>"}
  ]
}
```

CORE vẫn là model hiện có, fast/temperature 0/max output 512, dùng schema/literal-string checks của adapter. Không có nguồn không gọi model; endpoint này vẫn ghi `answer_trust="model_generated"` theo contract D81 kể cả `no_sources`, khác `/grounded/answer`. Nhãn đó không được diễn giải là thực sự đã có inference khi không có nguồn. Code/fixture PASS không đóng gate chất lượng extraction trên owner chunks hoặc full-flow acceptance D81; native v4 và product activation chưa được thực hiện bởi nhiệm vụ tài liệu này.

### 5.7. Setup model, runtime và dịch vụ

#### Chuẩn bị đúng embedding đã được chọn trên máy mới

Dùng file/auth/database đã có ở phần 2–4. Với môi trường embedding mới, chuẩn bị Python **3.12** và hai môi trường uv-script riêng; không cài Torch/Transformers vào API environment để thay các pin:

```bash
uv sync --frozen --python 3.12 --script scripts/qwen_ingestion_preflight.py
uv sync --frozen --python 3.12 --script scripts/qwen_ingestion_encoder.py
```

Hai lockfile cùng tên script giữ dependency CPU. Khi vận hành, parent gọi worker offline/frozen, không tải package/model, không cấp API/database/Qdrant credential hoặc GPU. Encoder có cap address space 8 GiB, CPU 480 s và parent wall timeout 600 s; đó là giới hạn bảo vệ, không phải RAM thực đo hoặc cam kết thời gian.

Trên máy mới thiếu artifact, lệnh dưới tải **chính candidate trong cấu hình đã phê duyệt**, kiểm size/SHA-256 và lưu đúng `models/embedding/<candidate id>/`. Nó không chạy benchmark, nạp model, tạo collection hoặc tải reranker/E5 thay thế:

```bash
uv run --no-sync python - <<'PY'
"""Provision only the exact selected embedding artifacts for a new installation."""
import json
import logging
from pathlib import Path
from scripts.embedding_runtime import provision

logging.basicConfig(level=logging.INFO)
selection = json.loads(Path("configs/embedding-selected.json").read_text())
provision(selection["candidate"])
logging.info("selected_embedding_artifacts_prepared")
PY
```

Manifest gồm 4 artifact, tổng **1.203.020.554 byte**; cần thêm đĩa cho runtime/cache. Máy đã có file khớp không cần tải lại. Các lệnh download/sync ở đây là hướng dẫn, không được thực thi trong lần cập nhật tài liệu này. Không đổi selection, dtype, token cap hoặc fingerprint để xử lý một lỗi setup.

#### Chuẩn bị Qdrant và private ingestion config

Dùng instance Qdrant có sẵn; adapter hiện trỏ cố định `http://127.0.0.1:6333`. PostgreSQL phải ở revision `0004`, `0005` hoặc `0006` được service chấp nhận; checkout head là `0006`. API role cần quyền đúng: không UPDATE immutable `ingestion_jobs.manifest_json`, có UPDATE state. Không dùng superuser để bỏ qua kiểm grant.

`ASSISTANT_INGESTION_CONFIG_FILE` trỏ file regular private `0600`, cùng UID API, không symlink, một hard link, tối đa 16 KiB, đúng hai key:

```json
{
  "owner_id": "<stable installation UUID>",
  "api_key": "<existing Qdrant credential>"
}
```

Đây là template, không phải credential thật. `owner_id` là identity quản lý collection của installation, không phải quyền cho client chọn owner tài liệu; payload vẫn dùng principal của file. Giữ installation UUID cũ khi dùng lại collection. Qdrant `api_key` khác bearer token của API; không đưa key vào Git/log/command line.

Startup kiểm hash `embedding-selected.json` với approval record. Ingestion giữ lock namespace/model và **có thể tạo collection/payload indexes hoặc reconcile collection đã được quản lý**; không phải startup chỉ đọc. Collection hiện có sai ownership/schema sẽ bị từ chối, không bị nhận nuôi hoặc xóa. Retrieval chỉ kiểm collection, không tự tạo nó.

#### Bật luồng RAG cơ bản

Chỉ chạy sau khi operator đã chuẩn bị đúng model/runtime, private config và hạ tầng; dùng terminal riêng với `DATABASE_URL` đã được cấp kín. Ví dụ đường config dưới đây là tên file operator cần tạo, API không tự tạo credential:

```bash
export ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json"
export ASSISTANT_FILES_ENABLED=1
export ASSISTANT_FILES_ROOT="$PWD/data/files"
export ASSISTANT_INGESTION_CONFIG_FILE="$PWD/data/auth/ingestion.json"
export ASSISTANT_INGESTION_ENABLED=1
export ASSISTANT_RETRIEVAL_ENABLED=1
export ASSISTANT_GROUNDED_ENABLED=1
uv run --no-sync uvicorn apps.api.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Không cần CORE cho chunk/index/retrieval CPU; grounded answer/extraction cần đúng CORE ở 8080. Các cờ mặc định tắt; thiếu dependency có thể làm startup thất bại thay vì chạy một phần âm thầm. Ví dụ này không bật Memory/Voice và chưa được dùng để kích hoạt service khi viết tài liệu.

Nếu chủ đích dùng structured extraction, giữ toàn bộ prerequisite trên, giữ `ASSISTANT_VOICE_ENABLED=0`, thêm `ASSISTANT_GROUNDED_EXTRACT_ENABLED=1` rồi **thay** lệnh uvicorn bằng:

```bash
uv run --no-sync uvicorn apps.api.grounded_extract:create_app --factory \
  --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Factory này từ chối thiếu DATABASE_URL/auth/ingestion config hoặc voice bật; không tự bật các flag còn thiếu. Không chạy hai API process cùng giữ cổng hoặc cùng worker scope để thử tính năng.

### 5.8. Ví dụ chunk, index, tìm và hỏi trên file đã upload

Dùng file UUID ready từ phần 4. Ví dụ khi operator thực thi sẽ tạo/reuse ingestion job, ghi vector nếu cần và gọi CORE một lượt grounded; không tự upload hoặc xóa nguồn. Đoạn này chưa chạy trên database/Qdrant/model trong nhiệm vụ tài liệu.

```bash
uv run --no-sync python - <<'PY'
"""Index one existing owned source and inspect retrieval and grounded-answer outcomes."""
import getpass
import logging
import time
from uuid import UUID
import httpx

logging.basicConfig(level=logging.INFO)
token = getpass.getpass("API token from Vault: ")
identifier = str(UUID(getpass.getpass("Ready file UUID (hidden): ").strip()))
with httpx.Client(
    base_url="http://127.0.0.1:8000/api/v1",
    headers={"Authorization": "Bearer " + token},
    trust_env=False,
    timeout=600,
) as client:
    chunks = client.post(f"/files/{identifier}/chunks", params={"max_bytes": 256})
    chunks.raise_for_status()
    logging.info("rag_demo_chunks_built chunks=%d", len(chunks.json()["chunks"]))
    indexed = client.post(f"/files/{identifier}/index", params={"max_bytes": 256})
    indexed.raise_for_status()
    job_id = indexed.json()["id"]
    logging.info("rag_demo_index_admitted job_id=%s", job_id)
    for attempt in range(60):
        status = client.get(f"/ingestion/{job_id}", timeout=15)
        status.raise_for_status()
        job = status.json()
        if job["status"] == "ready" and job["active"]:
            break
        if job["status"] not in {"pending", "running"}:
            raise SystemExit("Job is not active-ready; inspect status before continuing")
        time.sleep(2)
    else:
        raise SystemExit("Polling ended; inspect the existing job later without resubmitting")
    question = "What text is in this document?"
    found = client.post("/retrieval/search", json={
        "query": question, "top_k": 3, "file_ids": [identifier],
    })
    found.raise_for_status()
    logging.info("rag_demo_retrieval_completed hits=%d", len(found.json()["hits"]))
    answer = client.post("/grounded/answer", json={
        "query": question, "top_k": 3, "file_ids": [identifier],
    })
    answer.raise_for_status()
    result = answer.json()
    logging.info("rag_demo_grounded_completed status=%s citations=%d",
                 result["status"], len(result["citations"]))
    print(result["answer"])
PY
```

Polling có tối đa 60 lần kiểm tra, không phải cam kết job hoàn tất trong một thời hạn. `no_sources` hoặc `insufficient_evidence` là outcome cần xem xét, không tự đổi nhãn thành câu trả lời đúng hay retry model. Chunk rỗng, source không phù hợp hoặc job không active-ready cần xử lý theo trạng thái thật; không bỏ guard để demo có kết quả.

### 5.9. Kết quả benchmark và quyết định reranker

[MODEL-EVAL-001 receipt](evidence/model-eval-001-qwen-e5-comparison.json) giữ so sánh thực ngày 2026-10-18: **20 document, 40 query, 3 repetition**, cùng input, CPU/batch 4/two threads, không truncation. Hai cấu hình khác cả model/dimension/precision/runtime; không gọi chênh lệch là tác động của riêng architecture.

| Chỉ số trên corpus này | E5 int8 | Qwen BF16 |
|---|---:|---:|
| Recall@3 | 0.925 | 0.975 |
| Recall@5 | 0.925 | 1.0 |
| Recall@10 | 0.975 | 1.0 |
| MRR@10 | 0.874405 | 0.968750 |
| Warm query p95 lớn nhất trong 3 run | 6.744 ms | 113.928 ms |
| Peak child RSS RAM lớn nhất | 803.305 MiB | 1318.086 MiB |

Qwen tốt hơn trên các quality metrics của corpus này nhưng chậm và tốn RSS hơn E5; không suy ra mọi câu hỏi thực tế đều tốt hơn. Đây là timing encoder warm, không phải API/query end-to-end hoặc cold start. Cả hai CPU-only; không gán RSS thành VRAM. Qdrant ingest throughput/disk index không được đo trong so sánh này và không điền số ước đoán.

[D27 baseline](evidence/d27-retrieval-baseline.json) dùng corpus khác: 24 document/36 query, hai replay round/72 quan sát. Dense Recall@3/@5 **0.972222**, Recall@10 **1.0**, MRR@10 **0.949074**, nDCG@10 **0.961613**; cached-vector retrieval/rehydration p50 **110.446 ms**, p95 **116.020 ms**. Nó không gồm tokenizer/model startup mỗi request, HTTP hoặc serialization; không cộng với warm encoder p95 rồi gọi là API SLO. Child RSS/VRAM của replay đó không được lấy mẫu.

[D27 quyết định cuối](progress/D27_RERANKER_EVALUATION_DECISION.md): **giữ dense retrieval, hoãn adoption Qwen3-Reranker-0.6B**. Candidate vẫn là model được đề cử ban đầu và đã benchmark, không bị thay bằng model khác. Diagnostic đầu có cải thiện, nhưng challenge v2 mới do assistant đánh giá cho dense/reranker bằng nhau trên các case có đáp án; không bịa human review hoặc nâng kết quả nhỏ thành bằng chứng chất lượng phổ quát. Các lượt batch1 thất bại vẫn được giữ.

Lượt TCP tạm đo dense **5.606043 s**, hai-candidate reranking **8.896878 s**, trở về dense sau tắt **5.634908 s**. Đây là thử nghiệm nhỏ riêng, không phải đường reranker đang tích hợp hoặc production SLO. Reranker muốn được bật cần quyết định/benchmark và phân tích tài nguyên, migration/rollback/phê duyệt riêng; không đổi embedding hay reindex chỉ để thử một ranking stage.

### 5.10. Kiểm thử, rollback và giới hạn

Các test phần mềm liên quan, không cần database/Qdrant/model thật:

```bash
env -u DATABASE_URL uv run --no-sync python -m pytest \
  tests/test_document_chunks.py tests/test_ingestion_contract.py \
  tests/test_ingestion_schema_compatibility.py tests/test_ingestion_startup.py \
  tests/test_ingestion_adapters.py tests/test_retrieval_adapters.py \
  tests/test_retrieval_startup.py tests/test_grounded_answer.py \
  tests/test_grounded_service.py tests/test_grounded_startup.py \
  tests/test_grounded_source_groups.py tests/test_grounded_extract_contract.py \
  tests/test_grounded_extract_service.py tests/test_grounded_extract_startup.py \
  tests/test_grounded_extract_gpu_admission.py -q
```

Kiểm tra ngày 2026-11-10: **442 PASS, 0 FAIL, 0 SKIP trong 3.08 s**, phạm vi 15 file. Fixture/mock và bounded worker controls không thay thế live embedding/index/search/model hoặc chất lượng citation/extraction. Không tải weights, chạy lại benchmark, sửa config hoặc ghi vector/database trong lượt tài liệu này.

Các gate thật có [ingestion HTTP](../tests/integration/test_ingestion_http.py), [retrieval HTTP](../tests/integration/test_retrieval_http.py), [grounded HTTP](../tests/integration/test_grounded_http.py) và báo cáo/receipt riêng. Các checkpoint running/PARTIAL cũ trong guide cần đọc cùng final update; không tự cộng nhiều invocation thành một full-suite mới.

Rollback dịch vụ là tắt admission, drain/join công việc theo dependency và giữ file/journal/ownership/collection; không drop collection, xóa nguồn, sửa approved fingerprint hoặc downgrade database để rollback code. Cleanup/tombstone còn nghĩa vụ phải được giữ và kiểm theo runbook trước khi vô hiệu hóa worker. Model replacement, production enablement, multiworker/load/DR và rộng hơn về chất lượng cần đánh giá riêng.

Quyết định chính: [ADR-031](ADR/031-cpu-embedding-selection-and-vector-schema.md), [ADR-032](ADR/032-qwen-e5-comparison-and-transition-review.md), [ADR-036](ADR/036-ingestion-worker-and-terminal-sweeps.md), [ADR-037](ADR/037-acl-filtered-source-revalidated-retrieval.md), [ADR-043](ADR/043-source-held-grounded-generation.md), [ADR-177](ADR/177-proposed-d81-structured-excerpt-product-integration.md). [Retrieval guide](progress/RETRIEVAL.md) và [grounded guide](progress/D28_GROUNDED_GENERATION.md) ghi source/delivery fences và acceptance theo scope của từng component.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">6. Memory</h2></summary>

**Mục đích:** Lưu thông tin người dùng chủ đích cho phép ghi nhớ, gắn với owner, loại/phạm vi, consent, nguồn gốc và thời hạn; cung cấp quyền xem, sửa, export và xóa độc lập với việc bật sử dụng.

Memory lưu trong PostgreSQL, không phải lịch sử hội thoại, KV cache hoặc Qdrant Knowledge index. Hiện có manual capture và extraction tường minh từ user message; **chưa có memory-to-prompt injection trong Conversation**, tự học nền, file-to-memory adapter hoặc memory vector collection. Lưu thành công một preference chưa làm mọi câu trả lời sau đó tự tuân theo preference đó.

### 6.1. Các module và dữ liệu chính

| Module | Trách nhiệm |
|---|---|
| [Memory routes](../apps/api/routes/memory.py) | API owner-scoped, schema strict, response/error riêng tư và các thao tác quản lý. |
| [Memory startup](../apps/api/storage/memory.py) | Kiểm operator flag, schema V006 và grant trước khi tạo service/retention worker. |
| [MemoryService](../apps/api/services/memory.py), [joined work](../apps/api/services/memory_work.py) | Điều phối SQL, hủy/join công việc và dừng extraction sau control transaction đã commit. |
| [Memory contract](../src/application/services/memory_contract.py) | Kiểu dữ liệu, consent/retention, provenance và policy write/use. |
| [Memory journal](../src/infrastructure/repositories/memory_journal.py) | Settings epoch, consent, quota và manual CRUD trong transaction. |
| [Message-memory journal](../src/infrastructure/repositories/message_memory_journal.py) | Xác minh user message, capture/revalidate quote, export và retention. |
| [MemoryExtractor](../apps/api/services/memory_extraction.py), [selection contract](../src/application/services/memory_selection.py) | Một lượt CORE chọn tối đa một quote nguyên văn, không tóm tắt hoặc sáng tác memory. |
| [MemoryRetention](../apps/api/services/memory_retention.py), [export contract](../src/application/services/memory_export.py) | Cleanup có giới hạn và snapshot export chỉ của owner. |

Ba bảng chính trong schema `assistant`: `memory_settings` giữ epoch/flags của owner, `memory_consents` giữ receipt theo loại/scope/expiry và `memories` giữ record/provenance/version/expiry. Model không được tự cấp consent hoặc thay owner/expiry; UUID từ client chỉ là định danh, không phải quyền truy cập.

### 6.2. Bốn loại memory và retention

| Kind | Phạm vi | Consent mặc định | Giới hạn lifetime của class |
|---|---|---:|---:|
| `session` | UUID hội thoại active thuộc owner | 1 giờ | 24 giờ |
| `episodic` | Owner-wide; scope mặc định lấy từ principal | 30 ngày | 365 ngày |
| `preference` | Owner-wide; scope mặc định lấy từ principal | 30 ngày | 365 ngày |
| `project` | UUID label trong phạm vi owner, phải khai báo | 30 ngày | 365 ngày |

Project scope là label của memory, không chứng minh quyền với workspace/path của Coding agent. Session memory cũng là dữ liệu có thời hạn trong PostgreSQL, không chỉ là biến RAM sống cùng process.

Mỗi record gắn một consent cùng owner/kind/scope và không được sống lâu hơn consent. Khi tạo manual record, bỏ `seconds` để dùng đúng mốc expiry của receipt; nếu khai báo thì dùng thời hạn ngắn hơn phần còn lại. Ví dụ đặt receipt 3600 s rồi record cũng 3600 s có thể bị từ chối vì record được tạo muộn hơn. Sửa record không tự kéo dài expiry.

Text record không rỗng/toàn khoảng trắng, không NUL và tối đa **4096 byte UTF-8**, giữ nguyên nội dung, không tự normalize/truncate. Quota hiện tại là **1000 record và 1000 consent mỗi owner**, **10.000 mỗi loại toàn hệ thống**, tính các bản ghi còn được giữ trong bảng. Đây là giới hạn dữ liệu, không phải benchmark RAM/tốc độ.

### 6.3. Ba lớp opt-in và consent epoch

```text
Operator bật ASSISTANT_MEMORY_ENABLED=1 với đúng database/role
  → Owner GET settings: chưa có row thì revision=0, cả hai flag=false
  → Owner PUT settings với expected_revision hiện tại
      → enabled=true; extraction_enabled chỉ bật khi chủ đích
  → Owner POST consent cho kind/scope và settings revision đó
  → Capture chỉ được phép khi settings + receipt + source còn hợp lệ
```

`enabled` và `extraction_enabled` là hai lựa chọn của owner; extraction không được true khi memory false. Muốn gọi extraction còn cần receipt `allow_extraction=true`. Chỉ bật operator flag không đồng nghĩa mọi user đã cho phép capture.

Mỗi lần PUT settings thành công tăng revision/epoch, kể cả gửi lại cùng flags, làm receipt thuộc epoch cũ mất hiệu lực. CAS sai revision trả `409`. Tắt rồi bật lại không khôi phục consent cũ; cần receipt mới cho capture mới. Thu hồi một receipt giữ dấu revoked, không tự xóa ngay mọi record của receipt đó.

Khi owner tắt use hoặc receipt hết hạn/thu hồi, inspect/list/export/delete retained data vẫn dùng được **nếu operator service còn bật**. Nếu operator tắt cả service thì API Memory không được phục vụ, trả `503`; hai trạng thái này khác nhau. Code quản lý không tự suy ra consent từ lịch sử hoặc một câu model nói rằng người dùng đã đồng ý.

### 6.4. Hợp đồng API

Mọi path sau có prefix `/api/v1/memory`, direct localhost/bearer và principal của phần 2. Schema từ chối field ngoài hợp đồng, input lỗi được làm gọn thành stable code thay vì echo private text; response/error có `private, no-store` và `nosniff`.

| Method và path tương đối | Input / hành vi |
|---|---|
| `GET /settings` | Xem flags/revision; revision 0 không tự tạo row/consent. |
| `PUT /settings` | `expected_revision`, `enabled`, `extraction_enabled` tùy chọn, mặc định false. |
| `POST /consents` | `kind`, `expected_revision`, tùy chọn `scope_id`, `seconds`, `allow_extraction`; trả `201`. |
| `DELETE /consents/{id}` | Thu hồi receipt của owner; thao tác lặp giữ cùng dấu revoked nếu receipt còn được giữ. |
| `GET /records` | Metadata page: `limit=50`, tối đa 100, `after=<UUID>`; không trả bulk text/provenance. |
| `POST /records` | `consent_id`, literal `text`, tùy chọn `seconds`; manual capture, trả `201`, không gọi model. |
| `GET /records/{id}` | Inspect text/provenance/version của record owner còn được giữ. |
| `PATCH /records/{id}` | `expected_version` và text mới; cần consent còn hiệu lực. |
| `DELETE /records/{id}?expected_version=N` | Hard-delete đúng version của owner, trả `204`, dùng được khi owner use tắt. |
| `POST /extractions` | `consent_id`, `conversation_id`, `message_id`; chọn quote từ một user message được phép. |
| `GET /export` | JSON attachment `memory-export.json` của owner, không cần bật owner use. |

PATCH biến nội dung thành quyết định **manual** mới: tăng version, gắn hash text và bỏ model ID/derived provenance cũ. Không cho client ghi owner, model, source hash hoặc quote span để tự nhận là nguồn đã xác minh. Sai version trả conflict, không last-write-wins. Foreign/missing IDs bị che bằng `404`.

### 6.5. Luồng extraction từ user message

```text
POST /memory/extractions: chỉ gửi IDs
  → Kiểm owner settings + receipt + extraction flags
  → Khóa/đọc hội thoại active thuộc owner và message role=user
  → Snapshot text/hash → đóng transaction preflight
  → Một lượt CORE fast chọn quote hoặc insufficient_evidence
  → Kiểm quote nguyên văn, duy nhất trong snapshot
  → Transaction capture: kiểm lại source/consent/epoch/expiry/quota
  → Lưu record derived + provenance và model ID
  → Kiểm lại source/consent/record version trước response headers
```

Nguồn giới hạn **8192 byte**, quote tối đa **2048 byte**; không cắt bớt source để nạp vừa model. Không lấy assistant message hoặc message của hội thoại archived/khác owner làm nguồn capture này. Session consent còn phải trùng conversation scope. Contract có kiểu `file_quote`, nhưng hiện không có adapter/route capture từ file; kiểu dữ liệu tồn tại không chứng minh tính năng đã hoạt động.

Extractor dùng đúng CORE hiện có, preset fast, temperature 0, max output 512, model-only timeout 60 s. Một extraction slot không queue trong một service process; bận trả `429 memory_busy`. Manual CRUD/export không cần model. Không tải/thay model hoặc dùng embedding/reranker cho capture này.

Chỉ nhận JSON đúng shape với một quote khớp duy nhất; model báo `insufficient_evidence` thì không tạo record. Text bịa, quote trùng vị trí, JSON sai hoặc completion chưa xong bị từ chối, không sửa output để ghi thành công. Captured quote vẫn `content_trust="untrusted"`: nguyên văn và có consent không có nghĩa thông tin đúng ngoài đời hoặc được phép điều khiển tool.

Control settings/revoke commit trước rồi hủy/join những extraction đang chạy tương ứng. Các tác vụ SQL/model được theo dõi và join khi cancel/shutdown; nếu source/epoch/version đổi giữa chừng thì không trả response như thể snapshot cũ vẫn được phép. Không giữ transaction DB mở trong toàn bộ model delay.

### 6.6. Xóa nguồn, thu hồi, retention và export

[V006 / ADR-049](ADR/049-transactional-message-memory-invalidation.md) bổ sung invalidation bằng trigger trong transaction nguồn, không phụ thuộc cờ Memory hay worker đang bật:

| Thao tác | Hành vi dữ liệu |
|---|---|
| Conversation soft/hard-delete hoặc đổi owner | Xóa memory có exact message provenance của conversation, record session-scoped và receipt session đã orphan theo contract. |
| Message bị xóa hoặc đổi content/role/conversation/id | Xóa derived memory gắn đúng provenance cũ trong cùng transaction. |
| Đổi title/thứ tự, archive đơn thuần hoặc no-op content | Không tự xóa memory độc lập; archive vẫn chặn capture mới vì source cần active. |
| Record đã PATCH thành manual | Quyết định manual độc lập giữ lại khi nguồn cũ bị xóa, trừ quan hệ session-scope áp dụng riêng. |
| Owner disable hoặc revoke consent | Chặn write/use theo policy; không tự hard-delete mọi retained record. |
| `DELETE /records/{id}` | Xóa vật lý row Memory, không xóa user message/file gốc. |

Source mutation và derived removal cùng commit hoặc cùng rollback. Conversation DELETE của phần 3 vẫn soft-delete transcript; trigger không biến nó thành hard purge lịch sử. Không xóa record của principal/nguồn khác để hoàn tất một privacy operation.

Retention worker chạy khi operator Memory service bật, interval mặc định **30 s**. Mỗi tick tối đa 10 owner, mỗi owner tối đa 100 expired records và 100 orphan inactive receipts, xoay cursor để xử lý các batch sau. Unexpired records giữ receipt liên quan; receipt revoked/stale chỉ được purge khi không còn record tham chiếu. Expiry chặn write/use ngay theo policy, còn physical purge là eventual; không cam kết xóa đúng giây thứ 30 khi downtime/load. Worker vẫn xử lý expiry khi owner use tắt.

Export là snapshot owner-only `REPEATABLE READ, READ ONLY`, gồm settings, consents, retained records/provenance, `observed_at`, format `local-assistant-memory-v1`. Giới hạn **1000 receipts + 1000 records và 12 MiB UTF-8 JSON**; vượt thì từ chối, không cắt bớt dữ liệu để giả export đủ. Không kèm toàn bộ transcript/file/vector hoặc credential.

Snapshot được xếp trước một deletion đồng thời có thể chứa dữ liệu còn được giữ ở thời điểm snapshot; export đã giao cho owner không thu hồi lại được. Backup/WAL, transcript mềm và dữ liệu đã export là retention domain riêng; SQL DELETE không chứng nhận chúng đã bị xóa. Không có memory vector collection/file-to-memory path để tuyên bố đã purge.

### 6.7. Setup và bật Memory

Dùng dependency/API auth ở phần 1–2, database `local_assistant`/schema `assistant` và runtime role `local_assistant_app` ở mục 3.7. Không cần Qdrant, embedding hoặc files flag cho manual Memory; chỉ extraction cần CORE đã nạp.

Startup bắt buộc revision **`0006`** và đúng least-privilege grant tuple:

```text
version                                  = 0006
UPDATE memories.owner_id                 = false
UPDATE memories.text                     = true
UPDATE memory_consents.settings_revision = false
UPDATE memory_consents.revoked_at        = true
TRUNCATE memories                        = false
```

Role superuser hoặc V005 không đáp ứng điều kiện sẽ bị từ chối; không mở rộng grant hay hạ kiểm tra để chạy được. API không chạy migration tự động. Dùng [runbook prerequisite](progress/CONVERSATION_API_LOCAL_RUNBOOK.md) nếu schema/role chưa được provision; giữ database và trigger hiện có.

Sau khi `DATABASE_URL` đã được cấp kín, chạy từ repository:

```bash
export ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json"
export ASSISTANT_MEMORY_ENABLED=1
uv run --no-sync uvicorn apps.api.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Không cần thêm dependency/model download. Cờ trên chỉ tạo service/retention, chưa cấp consent cho owner. Client GET `/api/v1/memory/settings`, rồi chủ đích PUT theo revision vừa đọc; ví dụ cho owner mới hoàn toàn:

```json
{
  "expected_revision": 0,
  "enabled": true,
  "extraction_enabled": false
}
```

Không dùng revision 0 nếu owner đã có settings. Muốn extraction, chủ đích bật `extraction_enabled=true` bằng revision hiện tại, sau đó cấp **receipt mới** có `allow_extraction=true`; thay setting có thể làm mọi receipt cũ mất hiệu lực. Các lệnh/JSON này là hướng dẫn, không được dùng để bật hoặc đổi setting thật trong lần viết tài liệu.

### 6.8. Ví dụ manual capture, sửa, export và xóa

Ví dụ yêu cầu owner đã tự bật Memory; không tự PUT settings, không revoke receipt cũ hoặc thay memory khác. Khi operator chạy, nó tạo receipt/record demo, sửa, đọc snapshot export, xóa riêng record đó rồi revoke receipt demo. Nếu dừng giữa chừng, dùng ID đã log để kiểm tra và quản lý phần còn lại; receipt vẫn chịu expiry/retention.

```bash
uv run --no-sync python - <<'PY'
"""Exercise explicit manual memory controls without modifying existing owner settings."""
import getpass
import logging
import httpx

logging.basicConfig(level=logging.INFO)
token = getpass.getpass("API token from Vault: ")
with httpx.Client(
    base_url="http://127.0.0.1:8000/api/v1/memory",
    headers={"Authorization": "Bearer " + token},
    trust_env=False,
    timeout=60,
) as client:
    settings = client.get("/settings")
    settings.raise_for_status()
    current = settings.json()
    if not current["enabled"]:
        raise SystemExit("Owner memory is disabled; enable it explicitly before this demo")
    consent = client.post("/consents", json={
        "kind": "preference", "expected_revision": current["revision"],
        "seconds": 3600, "allow_extraction": False,
    })
    consent.raise_for_status()
    consent_id = consent.json()["id"]
    logging.info("memory_demo_consent_created consent_id=%s", consent_id)
    created = client.post("/records", json={
        "consent_id": consent_id, "text": "Prefer concise answers.", "seconds": 1800,
    })
    created.raise_for_status()
    record_id = created.json()["id"]
    logging.info("memory_demo_record_created record_id=%s", record_id)
    inspected = client.get(f"/records/{record_id}")
    inspected.raise_for_status()
    edited = client.patch(f"/records/{record_id}", json={
        "expected_version": inspected.json()["version"],
        "text": "Prefer concise answers with examples.",
    })
    edited.raise_for_status()
    version = edited.json()["version"]
    exported = client.get("/export")
    exported.raise_for_status()
    snapshot = exported.json()
    assert snapshot["format"] == "local-assistant-memory-v1"
    logging.info("memory_demo_export_observed records=%d", len(snapshot["records"]))
    deleted = client.delete(f"/records/{record_id}", params={"expected_version": version})
    deleted.raise_for_status()
    assert deleted.status_code == 204
    revoked = client.delete(f"/consents/{consent_id}")
    revoked.raise_for_status()
    logging.info("memory_demo_completed record_deleted=true consent_revoked=true")
PY
```

Đoạn này không gọi model hoặc lưu file export ra đĩa; đã export nghĩa là snapshot riêng tư được trả về client, nên không log toàn bộ nội dung. Muốn giữ bản export cần nơi lưu riêng tư theo policy của owner. Đây là ví dụ quản lý dữ liệu khi operator thực thi, không phải thao tác đã chạy trên database trong nhiệm vụ tài liệu.

Extraction dùng user message ID từ Conversation và receipt đã cho phép; request chỉ có IDs:

```json
{
  "consent_id": "<active extraction consent UUID>",
  "conversation_id": "<owned active conversation UUID>",
  "message_id": "<owned user message UUID>"
}
```

Gửi JSON đã thay placeholder tới `POST /api/v1/memory/extractions`. `captured` có record; `insufficient_evidence` có record null. Không tự đổi kind/source hoặc retry model chỉ để ép có memory; nhận `captured` cũng chưa chứng minh record đã được tích hợp vào chat context.

### 6.9. Kết quả đo và kiểm thử

[D30 CORE receipt](evidence/d30-t03-final-core.json) giữ ba lượt model thật trên nguồn synthetic, cùng CORE/fast, temperature 0, max output 512:

| Case | Outcome | Input / output token | Latency adapter đã ghi |
|---|---|---:|---:|
| Project fact tiếng Anh | `captured` | 200 / 19 | 428 ms |
| Preference tiếng Việt | `captured` | 200 / 18 | 310 ms |
| Preference không đủ evidence | `insufficient_evidence` | 193 / 13 | 244 ms |

Đây là ba quan sát lịch sử, không phải corpus độc lập hoặc production benchmark. Adapter latency không gồm toàn bộ SQL capture/HTTP delivery; không phải TTFT, p95 hoặc thời gian cold load. Chưa có số đo RSS/VRAM riêng cho toàn luồng Memory trong receipt này; không mượn số inference/RAG để điền vào. Exact quote chỉ là structural/source verification, không chứng minh khả năng chọn mọi thông tin nên ghi nhớ.

[D30 acceptance](evidence/d30-memory-acceptance.json) ghi **1570 full-suite PASS/1357.69 s, 0 SKIP** ở checkpoint lịch sử. [D31 privacy acceptance](evidence/d31-privacy-acceptance.json) ghi **1608 PASS/1361.93 s, 0 SKIP** từ summary đã giữ; process exit status của lượt đó không được giữ qua external restart. Không cộng hai checkpoint hoặc các focused subsets thành một full run mới; các lỗi ban đầu vẫn được giữ trong evidence.

Kiểm thử phần mềm có thể chạy riêng, không cần database/model thật:

```bash
env -u DATABASE_URL uv run --no-sync python -m pytest \
  tests/test_memory_contract.py tests/test_memory_journal.py \
  tests/test_memory_selection.py tests/test_memory_extraction.py \
  tests/test_memory_export.py tests/test_memory_api.py -q
```

Kiểm tra ngày 2026-11-10: **154 PASS, 0 FAIL, 0 SKIP trong 1.28 s** trên sáu file, dùng fixture/mock cho storage/model và boundary/lifecycle tests. Đây không phải full regression, live privacy audit hoặc lượt đo lại chất lượng CORE. Ví dụ client, API contracts và liên kết được kiểm tra riêng; không bật service, cấp/revoke consent thật hoặc sửa database trong lần cập nhật này.

Live gates có [consent/quota](../tests/integration/test_memory_consent_quota.py), [message selection](../tests/integration/test_memory_extraction_live.py), [source ordering](../tests/integration/test_memory_source_ordering.py), [export HTTP](../tests/integration/test_memory_export_http.py) và [privacy composition](../tests/integration/test_memory_privacy_boundaries.py); cần prerequisite/credential/phạm vi riêng, không tính SKIP thành PASS.

Quyết định và giới hạn được ghi trong [ADR-044](ADR/044-consent-bound-memory-contract.md), [ADR-045](ADR/045-memory-journal-and-control-transactions.md), [ADR-046](ADR/046-local-memory-management-api.md), [ADR-047](ADR/047-explicit-message-memory-selection-and-retention.md), [ADR-048](ADR/048-owner-memory-export.md), [ADR-049](ADR/049-transactional-message-memory-invalidation.md), [Memory API guide](progress/MEMORY_API.md) và [D31 privacy guide](progress/D31_PRIVACY_AND_DELETION.md). Rollback tắt/drain service, giữ tables/consent/provenance và source triggers; không downgrade populated schema hoặc coi tắt service là xóa dữ liệu.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">7. Coding agent</h2></summary>

**Mục đích:** Đọc code trong workspace được đăng ký, giải thích/chẩn đoán theo nguồn, tạo đề xuất sửa có thể review và chỉ thực hiện edit/check đã được cấp approval đúng phạm vi.

Đây là workflow local có giới hạn, không phải agent tự do chạy shell, cài dependency, sửa mọi file hoặc lặp đến khi test xanh. Component dùng CORE hiện có; model output, README, source, test và native stdout đều là dữ liệu không tin cậy, không có quyền tự cấp approval, đổi model hoặc mở rộng workspace.

### 7.1. Các module tham gia

| Module | Trách nhiệm |
|---|---|
| [Workspace catalog](../apps/api/storage/workspaces.py), [scope policy](../src/application/services/workspace_policy.py) | Đăng ký root theo owner/workspace UUID từ private config. |
| [Readonly workspace](../src/infrastructure/readonly_workspace.py), [reader](../src/infrastructure/workspace_reader.py) | Đọc qua descriptor/openat2, giới hạn scan và giữ source receipts. |
| [WorkspaceService](../apps/api/services/workspaces.py), [tool dispatch](../apps/api/services/workspace_tools.py) | Điều phối discover/inventory/read/search/symbols, xác minh nguồn trước delivery. |
| [Explanation](../apps/api/services/workspace_explanations.py), [diagnosis](../apps/api/services/workspace_diagnoses.py) | Gọi CORE với source được chọn và kiểm citation/plan theo contract. |
| [ApprovalStore](../src/application/services/approvals.py), [review CLI](../scripts/review_approval.py) | Giữ approval có expiry/scope/nonce và nhận quyết định owner tường minh. |
| [PatchService](../apps/api/services/patches.py), [patch policy](../src/application/services/patch_policy.py) | Full-file proposal, unified diff và một lần apply đúng file/version. |
| [CheckpointPatchService](../apps/api/services/checkpoint_patches.py), [checkpoint store](../src/infrastructure/checkpoints.py) | Checkpoint Git private, history/recovery và đề xuất rollback byte có approval mới. |
| [CheckService](../apps/api/services/checks.py), [runtime capsule](../src/infrastructure/check_runtime.py) | Capture snapshot/runtime và chạy profile kiểm tra cố định trong isolation. |
| [CodingWorkflowService](../apps/api/services/coding_workflows.py), [workflow contract](../src/application/services/coding_workflow.py) | Ghép issue → proposal → edit → checks thành tiến trình hữu hạn. |
| [Controlled workflow](../apps/api/services/controlled_coding_workflows.py) | Cancel/join và một retry-proposal có điều kiện, bật riêng. |

Workspace/approval/patch/checkpoint/check/workflow dùng config, descriptor và private local storage; không cần database, Memory hoặc Qdrant. Nếu API được cấp `DATABASE_URL`, lifespan vẫn khởi tạo phần DB theo cấu hình chung, nhưng đó không phải dependency của Coding agent.

### 7.2. Workspace scope, đọc code và giới hạn

Operator đăng ký tối đa **8 workspace**, mỗi root absolute gắn với đúng principal/workspace UUID. Client chỉ gửi UUID đã đăng ký và relative path; không tự gửi root/owner để nhận quyền. Linux x86_64/openat2 là nền tảng reader hiện có; path traversal, symlink/magic link và entry vượt mount boundary bị từ chối theo capability policy.

| Khả năng read-only | Hành vi |
|---|---|
| Discover | Metadata workspace/repository được phép; không chạy Git hook hoặc làm theo README. |
| Inventory | Liệt kê bounded regular-file metadata dưới directory tương đối tùy chọn. |
| Read | Đọc range một-based, mặc định 1–200, tối đa 200 dòng/lượt; source hash là hash raw file. |
| Search | Tìm literal query, tối đa 256 byte UTF-8; không nhận regex/command từ client. |
| Symbols | Gợi ý lexical Python `def`/`class`, không import/execute source và không phải semantic language server. |

Reader giới hạn 256 KiB/file, 4 MiB source được đọc trong snapshot, 1000 scanned entries, 256 files, depth 16, 8192 byte/dòng, tối đa 100 search/symbol results và deadline 5 s. Vượt bound bị từ chối; không coi phần kết quả không đầy đủ là đã khảo sát hết repository. Response được chặn ở 512 KiB.

Hidden entries bị bỏ qua; relative path có component bắt đầu bằng dấu chấm bị từ chối. Đây không phải secret scanner: credential nằm trong file không ẩn không tự trở thành an toàn, và `.gitignore` không thay thế scope đăng ký. Chọn đúng project root, không đăng ký thư mục cha chứa Vault/hạ tầng riêng hoặc toàn home để tiện truy cập.

Trước khi trả nội dung, service kiểm lại root/native identity và raw bytes/hash đã giữ. File thay đổi trong lúc đọc/model xử lý bị fenced, không trả source cũ như còn hiện hành. Các tool name được đăng ký hữu hạn: `workspace.discover`, `workspace.inventory`, `workspace.read`, `workspace.search`, `workspace.symbols`.

### 7.3. Giải thích và chẩn đoán theo nguồn

`POST /api/v1/workspaces/{id}/explain` nhận `question` và 1–3 source selections `{path, start_line, end_line}`. `/diagnose` nhận `symptom` và cùng source selection. Model không được tự chọn root, tool, command, budget hoặc profile khác từ nội dung tài liệu.

Hai đường này dùng CORE/fast, temperature 0, max output 768 và model deadline 60 s, giữ source receipts qua generation/delivery. Citation được resolve về source lines/hash/quote được phép; source drift hoặc output sai contract bị từ chối. Không có nguồn thì không bịa citation hay gọi model chỉ để có nội dung.

Diagnosis có plan/reproduction dạng hướng dẫn, server ghi `execution_status="not_executed"`; liệt kê bước chạy test không chứng minh đã chạy. Citation hợp lệ cũng không chứng minh chẩn đoán đúng về ngữ nghĩa. Explanation/diagnosis không sửa source, tạo approval hoặc chạy subprocess từ đề xuất model.

### 7.4. Approval, patch và checkpoint/rollback

```text
Đọc target và raw hash hiện tại
  → Tạo proposal: full replacement + complete diff + scope cụ thể
  → Owner GET/review artifact và quyết định approve/reject
  → POST apply với đúng linked approval ID
  → Kiểm lại source/root/hash/scope, consume quyền một lần
  → Atomic edit một file; ghi receipt/checkpoint theo composition
```

Approval bind owner/workspace, loại thao tác, artifact và scope digest; decision cần đúng digest và review nonce đã cấp. Proposal patch/check có lifetime 120 s; expired/foreign/pending/consumed hoặc scope khác không chạy được. ApprovalStore là state **trong process**, không phải consent bền vững có thể khôi phục sau restart. Review/approve không tự thực hiện action.

Patch API chỉ nhận relative path của **file đã tồn tại**, SHA-256 gốc và **toàn bộ replacement UTF-8**, tối đa 8192 byte, không NUL. Unified diff được server dựng để review; apply không nhận một bản text/path khác. Đây là single-file edit, không phải multi-file transaction, tạo/xóa file tùy ý hoặc apply một shell script. Cơ chế native/hash/lock có giới hạn với external writer không phối hợp; không gọi atomic rename là bảo đảm chống mọi concurrent writer.

Nếu bật checkpoint, snapshot nằm trong Git store private riêng; không dùng `.git` của project làm nơi lưu checkpoint hoặc chạy hook/config của project. Lịch sử before/after và operation receipts phục vụ xác minh, không tự cấp quyền. Rollback endpoint kiểm current source hash rồi **tạo proposal khôi phục byte**; owner cần review/approval mới và apply riêng. Nó không tự `git reset`, hoàn tác file khác hoặc tiếp tục action dựa trên grant cũ.

Outcome apply và acknowledgement có thể khác nhau: edit đã xảy ra nhưng response/journal báo uncertainty thì phải đọc receipt/recovery trước. Không tự retry một edit chưa rõ kết quả hoặc xóa evidence để xem như chưa từng thực hiện. Root private cũ phải được giữ khi restart; crash record không chứng minh target đã/ chưa bị sửa trong mọi power-loss window.

### 7.5. Checks trên snapshot cô lập

Checks có một approval **khác** approval sửa file. Owner chọn 1–16 file `.py` hiện có cùng raw hashes; mỗi file tối đa 8192 byte, tổng 128 KiB; path tối đa 4 component/256 byte. Snapshot và trusted runtime được capture riêng, live workspace không mount vào nơi chạy.

| Profile cố định | Phạm vi |
|---|---|
| `python_unittest` | Python 3.12 isolated, stdlib `unittest discover` trên selected snapshot; không phải pytest của toàn repo, không có third-party dependency/subprocess support. |
| `ruff_check` | Ruff isolated/no-cache/no auto-fix, target py312, kiểm `E9,F`; không tự đọc plugin/config của project. |

Client không được gửi command, environment, CPU/resource override hoặc lệnh cài package. Captured Python/stdlib/Ruff có path/hash do operator cung cấp; runtime không mount home, API `.venv` hoặc uv cache. Readonly `/usr` vẫn cung cấp OS support, nên không gọi đây là chứng minh mọi package/tool host đều hoàn toàn không nhìn thấy.

Native checks dùng namespace/seccomp và policy đã kiểm chứng: parent wall 10 s, address space 512 MiB, CPU soft/hard 2/3 s, một CPU được pin, tối đa 16 threads/64 FDs, tmpfs writable 16 MiB, stdout 16 KiB/stderr 4 KiB. Đây là cap, không phải RAM RSS/VRAM đo được. Thiếu isolation/runtime thì không fallback sang chạy source trên host. [Checks guide](progress/D42_APPROVED_SNAPSHOT_CHECKS.md) ghi rõ giới hạn nền tảng/UID và syscall.

Kết quả giữ actual exit/signal/timing, output bytes/hash/completeness và trạng thái persisted riêng. **Exit 0 hoặc dòng “PASS” do test in ra không chứng minh repair đúng**: source test cũng là untrusted và có thể không có assertion. Receipt giữ `quality_evaluated=false`, `output_is_untrusted=true`; functional oracle/held-out evaluation là gate khác.

### 7.6. Reviewed workflow và bounded controls

Workflow nhận issue, **một target Python**, 1–3 selected test files kèm hash và check profile. Trường `profile` ở request này là `python_unittest|ruff_check`, không phải lựa chọn CORE/UNRESTRICTED hoặc Fast/Deep.

CORE mặc định fast/temperature 0/max output 2048, deadline 60 s, sinh đúng object `{plan, replacement}`. Issue tối đa 2048 byte, selected sources/prompt có trần 32 KiB; full replacement tối đa 8192 byte, 1–5 plan strings tối đa 512 byte mỗi phần. Host kiểm syntax/module/function/class descriptions mà không import generated source trên host; kiểm cấu trúc không phải chứng nhận code an toàn hoặc đúng.

```text
POST workflow → một proposal từ model, chưa edit/chạy test
  → Review và approve linked patch
  → POST workflow/apply với approval patch đó
  → POST workflow/checks với JSON {} để capture snapshot/check proposal
  → Review và approve linked check, tách khỏi patch approval
  → POST workflow/run-checks với approval check đó
  → Đọc summary từ trusted component receipts, không tin lời model tự báo PASS
```

Base workflow có tối đa một model-port attempt, một admitted edit attempt, một check-capture attempt và một admitted native attempt. Không auto repair loop, tự sửa test/oracle hoặc rollback để thử lại. Quota history hiện 16 workflow toàn process/4 mỗi owner; checks private store 32 jobs/8 mỗi owner. Failed/cancelled attempts vẫn giữ evidence và không tự hoàn quota; không có GC tùy tiện để bỏ lịch sử lỗi.

`ASSISTANT_CODING_WORKFLOW_CONTROLS_ENABLED=1` chọn controller tùy chọn: cancel/join đúng workflow và một explicit retry-proposal từ failed proposal **chưa publish component**, với options/source fences giữ nguyên. Retry tạo lineage member mới, không viết lại attempt cũ hoặc reuse approval. Cancel không tự undo edit đã commit; lịch sử sau restart không khôi phục quyền execute. [D44 guide](progress/D44_BOUNDED_WORKFLOW_CONTROLS.md) ghi điều kiện cụ thể.

Các service nghiên cứu reasoning/feedback, gồm `coding_reasoning_v2`, có evidence riêng; không được chọn bằng field tự do của request trên và không phải default của main workflow factory. Chúng dùng model CORE đã có, không phải adoption một coding model mới.

### 7.7. API chính

Các path workspace trong bảng có prefix `/api/v1/workspaces/{workspace_id}`; tất cả cần local/bearer và registered owner scope.

| API | Chức năng |
|---|---|
| `GET` workspace root; `POST /inventory`, `/read`, `/search`, `/symbols` | Bounded read-only operations. |
| `POST /explain`, `/diagnose` | Model explanation/manual diagnostic theo source đã chọn. |
| `POST /patches`, `GET /patches/{id}`, `POST /patches/{id}/apply` | Concrete proposal, review receipt và explicit approved edit. |
| `GET /checkpoints`, `GET /checkpoints/{id}`, `GET /checkpoints/{id}/recovery` | Lịch sử/recovery observations từ private store. |
| `POST /checkpoints/{id}/rollback` | Tạo rollback proposal với `expected_sha256` hiện tại, chưa tự sửa file. |
| `POST /checks`, `GET /checks`, `GET /checks/{id}` | Capture và xem check jobs. |
| `POST /checks/{id}/run`, `/cancel` | Chạy đúng approved snapshot hoặc chủ đích hủy/join job. |
| `POST /coding-workflows`, `GET /coding-workflows`, `GET /coding-workflows/{id}` | Tạo/xem finite reviewed workflow. |
| `POST /coding-workflows/{id}/apply`, `/checks`, `/run-checks` | Các bước explicit edit/capture/check. |
| `POST /coding-workflows/{id}/cancel`, `/retry-proposal` | Chỉ dùng khi composition controls được bật. |

Approval dùng prefix riêng: `GET /api/v1/approvals/{request_id}` và `POST /api/v1/approvals/{request_id}/decision`. API không có endpoint client tự tạo một approval tùy ý rồi thực thi command. Route hiện trong OpenAPI không đồng nghĩa service/permission đã bật.

### 7.8. Setup workspace và bật tính năng

#### Read-only trước

Dùng uv/API auth đã setup ở phần 1–2. Tạo private JSON config regular file chính xác `0600`, thuộc UID API, một hard link, không đi qua symlink, tối đa 32 KiB. Ví dụ cần thay UUID/root bằng giá trị thật:

```json
{
  "description": "Explicit owner-approved project roots",
  "workspaces": [
    {
      "owner_id": "<principal UUID from the auth configuration>",
      "workspace_id": "<stable workspace UUID>",
      "root": "/absolute/path/to/project",
      "name": "Project workspace"
    }
  ]
}
```

Root phải tồn tại và đủ điều kiện reader; file config không tự clone repository hoặc nhận root từ model. Giữ owner đúng principal đã cấp, không tạo principal khác để nhận dữ liệu cũ. Ví dụ đường config bên dưới là file operator chuẩn bị, không phải file ứng dụng tự sinh:

```bash
export ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json"
export ASSISTANT_WORKSPACE_CONFIG_FILE="$PWD/data/auth/workspaces.json"
export ASSISTANT_WORKSPACE_ENABLED=1
export ASSISTANT_WORKSPACE_EXPLAIN_ENABLED=1
export ASSISTANT_WORKSPACE_DIAGNOSE_ENABLED=1
uv run --no-sync uvicorn apps.api.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Để chỉ đọc không gọi model, bỏ hai cờ EXPLAIN/DIAGNOSE; mặc định của chúng là 0. Cờ bật không tự nạp CORE; explain/diagnose cần đúng backend có sẵn. Không cần model download hoặc dịch vụ database/vector mới cho workspace.

#### Bổ sung quyền patch/check/workflow khi chủ đích sử dụng

Chuẩn bị hai private native roots **đã tồn tại**, owned `0700`, ngoài ancestry của mọi workspace và ngoài ancestry lẫn nhau/checkpoint theo policy. Không dùng thư mục `.git` project, không xóa/recreate root cũ để bỏ history. Bật `ASSISTANT_APPROVAL_ENABLED`, `ASSISTANT_PATCH_ENABLED` và `ASSISTANT_CHECKPOINT_ENABLED` cần cùng live workspace/approval dependencies.

| Biến operator cần cấp | Giá trị |
|---|---|
| `ASSISTANT_CHECKPOINT_ROOT` | Absolute path private checkpoint root đã chuẩn bị. |
| `ASSISTANT_CHECKS_ROOT` | Absolute path private check-job root riêng đã chuẩn bị. |
| `ASSISTANT_CHECKS_PYTHON_PATH` | Trusted existing Python 3.12 executable, canonical absolute path. |
| `ASSISTANT_CHECKS_PYTHON_SHA256` | SHA-256 executable đã review, không tự chấp nhận binary lạ chỉ vì hash được tính ra. |
| `ASSISTANT_CHECKS_STDLIB_ROOT` | Matching existing stdlib root. |
| `ASSISTANT_CHECKS_RUFF_PATH` | Trusted existing Ruff executable, absolute path. |
| `ASSISTANT_CHECKS_RUFF_SHA256` | Expected reviewed Ruff executable SHA-256. |

Runtime capsule được capture từ các file đã provision, không tự `uv sync` trong workspace, cài plugin/dependency hay chạy project installer. Cần Git cho private checkpoint cùng isolation prerequisites của [D42 setup](progress/D42_APPROVED_SNAPSHOT_CHECKS.md); thiếu runtime/namespace/security policy thì startup/run từ chối. Không giả định đường dẫn seed/hashes của máy khác còn đúng trên máy mới.

Sau khi cấp đủ các biến ở bảng và read-only config, **thay** process API cơ bản bằng composition chủ đích bật các cờ:

```bash
export ASSISTANT_APPROVAL_ENABLED=1
export ASSISTANT_PATCH_ENABLED=1
export ASSISTANT_CHECKPOINT_ENABLED=1
export ASSISTANT_CHECKS_ENABLED=1
export ASSISTANT_CODING_WORKFLOW_ENABLED=1
export ASSISTANT_CODING_WORKFLOW_CONTROLS_ENABLED=1
uv run --no-sync uvicorn apps.api.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Các cờ default-off độc lập, có dependency checks; controls cần base workflow. Không chạy hai API process cùng giữ cổng hoặc coi chỉ bật PATCH là đã có durable checkpoints/check execution. Những lệnh này là hướng dẫn, không được thực thi để bật quyền trên workspace hiện tại khi viết tài liệu.

### 7.9. Ví dụ đọc nguồn và quy trình review

Ví dụ client chỉ discover/read một file đã chọn, không gọi model, tạo approval hoặc sửa source. Relative path và UUID được nhập kín từ terminal; dùng đúng scope đã đăng ký:

```bash
uv run --no-sync python - <<'PY'
"""Inspect one registered workspace source without granting writes or executing project code."""
import getpass
import logging
from uuid import UUID
import httpx

logging.basicConfig(level=logging.INFO)
token = getpass.getpass("API token from Vault: ")
workspace = str(UUID(getpass.getpass("Registered workspace UUID (hidden): ").strip()))
path = getpass.getpass("Relative source path (hidden): ")
with httpx.Client(
    base_url="http://127.0.0.1:8000/api/v1",
    headers={"Authorization": "Bearer " + token},
    trust_env=False,
    timeout=15,
) as client:
    discovered = client.get(f"/workspaces/{workspace}")
    discovered.raise_for_status()
    result = client.post(f"/workspaces/{workspace}/read", json={
        "path": path, "start_line": 1, "end_line": 200,
    })
    result.raise_for_status()
    lines = result.json()["lines"]
    logging.info("coding_demo_source_read lines=%d", len(lines))
    if lines:
        print("Source SHA-256:", lines[0]["source_sha256"])
PY
```

Workflow proposal body có dạng sau; target/test path phải là file hợp lệ và hash là raw file hash vừa quan sát, không phải hash một đoạn text model trả:

```json
{
  "issue": "Repair the described behavior without changing the selected tests.",
  "target": {"path": "value.py", "expected_sha256": "<target raw SHA-256>"},
  "tests": [{"path": "test_value.py", "expected_sha256": "<test raw SHA-256>"}],
  "profile": "python_unittest"
}
```

POST tới `/api/v1/workspaces/{id}/coding-workflows` sẽ gọi CORE một lượt và tạo pending review nếu contract đạt, **chưa sửa file**. Đọc complete proposal/diff, lấy linked patch approval ID do server trả; không tự tạo UUID approval. Khi đã đặt `APPROVAL_ID` bằng ID đó, review bằng CLI:

```bash
uv run --no-sync python -m scripts.review_approval \
  --base-url http://127.0.0.1:8000/api/v1 --request-id "$APPROVAL_ID"
```

CLI nhập bearer bằng prompt kín, hiển thị scope/artifact đầy đủ và yêu cầu gõ `APPROVE <approval_id>` hoặc `REJECT <approval_id>` đúng yêu cầu. Model/source nói “đã được duyệt” không thay thế bước owner này. Quyết định chỉ được ghi nhận; muốn apply vẫn phải gọi action endpoint riêng với `{"approval_id":"<linked approved UUID>"}`.

Sau apply đã được xác nhận, POST workflow `/checks` với `{}` để tạo check review mới. Review lại đúng check approval, rồi gọi `/run-checks`. Giữ receipt/IDs và đọc lịch sử khi acknowledgement không rõ; không tự lặp apply/run hoặc approve mọi yêu cầu từ model. Dừng ở proposal/reject là outcome hợp lệ, không gọi là lỗi cần vượt guard để demo chạy hết.

### 7.10. Kết quả đo và giới hạn chất lượng

| Bằng chứng | Kết quả thực | Phạm vi |
|---|---|---|
| [D38 CORE baseline](evidence/d38-core-observations.json) | **4/6** repair đạt | Sáu bài synthetic ban đầu; giữ hai thất bại, không thay bằng score mới. |
| [D43 first live sample](evidence/d43-core-live.json) | Một model-port attempt, edit/check fixture có receipt | Không chứng minh unattended/general coding quality; summary vẫn `quality_evaluated=false`. |
| [D46 first evaluation](evidence/d46-first-mvp-evaluation.json) | **7/10** functional repairs, 10 model attempts, 0 auto retry | Bảy đạt, hai fail native assertions, một proposal không được admit. |
| [CE005 exact-first revalidation](evidence/ce005-exact-first-output-revalidation.json) | **12/12**, 0 new model request | Targeted cohort riêng, review được sửa theo ADR-141 rồi kiểm lại đúng output cũ; CE005 first 11/12 và D46 7/10 vẫn giữ nguyên. |

D46 ghi application-port wall trên 10 case: min **3.021945 s**, median **3.143810 s**, max **4.694445 s**. Đây không phải TTFT, token/s hoặc production SLO; không có token usage hay peak RSS/VRAM được đo trong receipt đó. Cap native 512 MiB và deadline generation 60 s không được thay vào ô tài nguyên/latency thực đo.

[D46 remediation record](progress/D46_D60_REMEDIATION_RESULT.md) phân biệt optional `coding_reasoning_v2`, corrected-review evidence và production approval; không có việc tự chọn model khác hoặc rewrite first outputs để nâng điểm. Các cohort do cùng agent soạn/chấm, lựa chọn runtime/review và tính độc lập của oracle đều hạn chế suy rộng. Một bài test xanh/quote hợp lệ không đủ đóng gate chất lượng toàn agent.

### 7.11. Kiểm thử, audit và rollback dịch vụ

Các kiểm thử phần mềm liên quan dùng fixture/mock và thư mục tạm, không cần database hoặc model thật:

```bash
env -u DATABASE_URL uv run --no-sync python -m pytest \
  tests/test_workspace_policy.py tests/test_workspace_reader.py \
  tests/test_workspace_tools.py tests/test_workspace_explanation.py \
  tests/test_workspace_diagnosis.py tests/test_approvals.py \
  tests/test_patch_service.py tests/test_checkpoint_patch_service.py \
  tests/test_check_service.py tests/test_check_policy.py \
  tests/test_coding_workflow.py tests/test_coding_workflow_service.py \
  tests/test_controlled_coding_workflow_service.py tests/test_workspace_startup.py \
  tests/test_approval_startup.py tests/test_patch_startup.py \
  tests/test_checkpoint_startup.py tests/test_check_startup.py \
  tests/test_coding_workflow_startup.py tests/test_review_approval_cli.py \
  tests/test_coding_injection_authority.py -q
```

Kiểm tra ngày 2026-11-10: **503 PASS, 0 FAIL, 0 SKIP trong 34.29 s**, phạm vi 21 file. Có fixture filesystem/private Git cùng mocked service/model boundaries; không sửa workspace của người dùng, gọi CORE, phát approval thật hoặc chạy lại D38/D46/CE005. Đây không phải full regression hay chứng nhận mọi native profile/hostile source; các gate [native checks](progress/D42_APPROVED_SNAPSHOT_CHECKS.md), [workflow](progress/D43_REVIEWED_CODING_WORKFLOW.md) và [controls](progress/D44_BOUNDED_WORKFLOW_CONTROLS.md) có scope/receipt riêng.

Log giữ operation/IDs/state/count/hash, không source/raw model/program output, bearer hoặc review nonce. Content trong artifact/check output chỉ được trả owner trong boundary riêng tư. Rollback tính năng là ngừng admission, cancel/drain/join workflow trước checks → checkpoint/approval → workspace, giữ private roots và evidence. Không tự rollback file chỉ vì shutdown/test fail, không xóa intent không rõ kết quả hoặc khôi phục approval từ lịch sử sau restart.

Quyết định chính: [ADR-051](ADR/051-readonly-workspace-capabilities.md), [ADR-052](ADR/052-bounded-authenticated-workspace-reads.md), [ADR-057](ADR/057-explicit-scoped-expiring-approval-events.md), [ADR-058](ADR/058-approved-single-file-atomic-patch.md), [ADR-059](ADR/059-private-git-checkpoints-and-approved-byte-rollback.md), [ADR-060](ADR/060-approved-snapshot-checks-without-host-execution.md), [ADR-062](ADR/062-finite-owner-reviewed-coding-workflow.md), [ADR-063](ADR/063-bounded-workflow-hooks-cancel-and-retry.md) và [ADR-141](ADR/141-pure-rfind-review-and-exact-first-reply-revalidation.md). Multi-file editing, package runtimes, durable execution authority, production load và broader independent coding quality cần scope/benchmark/phê duyệt riêng, không được suy từ số unittest PASS.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">8. Web research</h2></summary>

**Mục đích:** Tìm thông tin web theo yêu cầu tường minh, thu thập evidence có nguồn gốc, đánh giá claim và tạo báo cáo có thể kiểm tra lại. Search snippet, trang web và kết quả model luôn là dữ liệu không tin cậy.

### 8.1. Các đường xử lý đã có

| Thành phần | Vai trò và ranh giới |
|---|---|
| [Search API](../apps/api/routes/web_search.py), [service](../apps/api/services/web_search.py) | Endpoint local/bearer `POST /api/v1/web/search`, query tường minh và admission/quota. |
| [SearXNG adapter](../src/infrastructure/searxng_search.py), [search pipeline](../src/application/services/search_pipeline.py) | Gọi instance đã review rồi dùng CORE trả lời từ snippet được cung cấp. |
| [Fetch policy](../src/application/services/web_fetch_policy.py), [fetch adapter](../src/infrastructure/web_fetch.py) | Lấy nội dung public với URL/DNS/redirect/byte/time guards, không coi URL từ model là đã được phép. |
| [Readonly browser](../src/infrastructure/readonly_browser.py), [runtime pin](../configs/browser-readonly-runtime.json) | Dynamic-page text trong worker cô lập; host kiểm soát network fulfillment, không cấp browser profile đăng nhập. |
| [ResearchService](../src/application/services/research.py), [web evidence](../src/application/services/web_evidence.py) | Multi-query có budget và snapshot evidence/provenance/cache rõ ràng. |
| [Claim validation](../src/application/services/claim_validation.py), [report](../src/application/services/research_report.py) | Phân biệt supported/contradicted/insufficient evidence rồi tạo Markdown có citation. |
| [Export](../src/application/services/report_export.py), [research sessions](../src/application/services/research_sessions.py) | Export DOCX/PDF và giữ lịch sử artifact/receipts theo owner. |

Main API hiện đăng ký search route; fetch/browser/multi-query/report/export/session là các application capabilities có composition và gate riêng, không tự có HTTP endpoint chỉ vì tồn tại class. Search API cơ bản **không tự fetch các URL**, chạy browser hoặc xuất báo cáo.

### 8.2. Provider, query và trust

Adapter hiện cố định SearXNG `http://127.0.0.1:8889/search`, engine **Brave**. Đây là Brave website engine qua SearXNG tự host, không đồng nghĩa Brave Search API trả phí. Có adapter/provider khác trong code không có nghĩa được tự chuyển khi Brave lỗi; giữ provider theo quyết định của chủ dự án.

Body search chỉ có `query`: không trắng, tối đa 512 byte UTF-8 theo policy; client không chọn engine, model, owner hoặc tự cung cấp source metadata. Adapter kiểm bounded wire results rồi lấy tối đa 5 hits; search timeout 10 s, CORE deadline riêng 60 s, fast/temperature 0/max output 768. Các giá trị là cap, không phải SLO.

Query/title/URL/snippet là untrusted evidence. Citation phải trỏ ID từ batch được cấp, không nhận URL model tự bịa. `no_sources` không gọi CORE; `insufficient_evidence` không được biến thành câu trả lời có căn cứ bằng retry hoặc đổi provider. Snippet citation **không chứng minh đã mở trang, độ mới, quyền sử dụng hoặc nội dung đầy đủ của trang**.

Fetch/browser là bước khác: policy từ chối các đích nội bộ/credential-bearing hoặc không hợp lệ và kiểm lại đường mạng/redirect trong phạm vi đã thiết kế. Browser worker được pin image, readonly/network-none; request cần thiết đi qua host policy. Không tái sử dụng profile người dùng, cookie đăng nhập hoặc thao tác form để vượt một nguồn không truy cập được. Xem [fetch](progress/D49_BOUNDED_PUBLIC_FETCH.md) và [browser](progress/D50_ISOLATED_READONLY_BROWSER.md) để biết phạm vi chính xác.

### 8.3. Evidence, claim và báo cáo

Research dùng số query/attempt/time hữu hạn, giữ failed/partial outcomes và không tự lặp đến khi đủ coverage. URL discovery chỉ là locator; cache/archive không tự trở thành fresh live evidence. Parent→child publisher lineage phải thể hiện đúng đường quan sát; không gọi một link được tìm qua publisher là direct search hit.

Claim validator giữ riêng kết luận supported, contradicted và insufficient evidence cùng quote/provenance được bind. Citation/JSON hợp lệ chưa chứng minh semantic correctness hoặc nguồn là primary/fresh; các gate đó có corpus/protocol riêng. Report proof gắn owner/content/issuer/lifetime; restart hoặc proof hết hạn không cho phép tiếp tục hành động dựa trên authority cũ.

Export DOCX/PDF giữ source/claim/citation metadata và hash artifact; archived artifact có thể mở lại như dữ liệu sau khi issuer bị thu hồi, không hồi sinh quyền fetch/export/model. Model text không được dùng làm command hay HTML có authority. Xem [D55 reconciliation](progress/D55_PRIMARY_SOURCES_AND_RECONCILIATION.md), [D56 claims](progress/D56_CLAIM_CITATION_VALIDATION.md), [D58 export](progress/D58_AUTHENTICATED_DOCX_PDF_EXPORT.md), [D59 sessions](progress/D59_DURABLE_RESEARCH_SESSIONS.md).

### 8.4. Setup và gọi search API

Dùng instance SearXNG hiện có do hạ tầng Home Server quản lý, đúng engine/port đã review; không tạo thêm container hoặc tự sửa engine trong nhiệm vụ tài liệu. API không tự deploy SearXNG hay tải CORE. Sau setup auth/CORE phần 1–2, bật service trong terminal API:

```bash
export ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json"
export ASSISTANT_WEB_SEARCH_ENABLED=1
uv run --no-sync uvicorn apps.api.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Một query explicit khi operator chủ đích kiểm tra provider:

```bash
uv run --no-sync python - <<'PY'
"""Submit one explicit search without exposing the bearer credential or retrying upstream."""
import getpass
import logging
import httpx

logging.basicConfig(level=logging.INFO)
token = getpass.getpass("API token from Vault: ")
with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=90) as client:
    response = client.post(
        "/api/v1/web/search",
        headers={"Authorization": "Bearer " + token},
        json={"query": "Python official documentation for dictionaries"},
    )
    logging.info("web_demo_completed status=%d", response.status_code)
    response.raise_for_status()
    result = response.json()
    print(result["status"], result["answer"])
PY
```

Đây là network/model request thật khi operator chạy; không được thực thi để dò Brave trong lượt viết tài liệu. Đừng dùng vòng retry để kiểm rate limit. Browser/report cần runtime và trusted composition riêng; bật search flag không cấp các capability đó.

### 8.5. Trạng thái D60 và giới hạn kết quả

[Fresh discovery receipt](evidence/d60-fresh-20261103-final-acceptance.json) giữ panel **4/8 valid**, coverage `FAILED_INCOMPLETE_FIRST_PANEL`, chưa xác lập verified freshness/semantic relevance. Một fresh report workflow đã có evidence/export được kiểm, nhưng không thay thế coverage panel thất bại. [Resumed panel](progress/D60_BRAVE_RESUMED_RESULT.md) là cohort khác: **3 valid / 1 error / 4 not-run**; không cộng hai cohort thành 7/8 hoặc 8/8.

D60 hiện **để pending theo yêu cầu owner**, giữ Brave; tài liệu này không đo availability/rate-limit mới và không khẳng định upstream đang phục hồi. Source/security gate, report workflow, search coverage, độ mới và độ ổn định production là các kết quả riêng. Các test phần mềm của phần này nằm trong lượt 910 PASS ở mục 12.7, không chứng minh Brave live đã đạt.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">9. Vision / Video</h2></summary>

**Mục đích:** Chuẩn hóa ảnh/video qua worker native có giới hạn, hỏi CORE từ ảnh, lấy frame có timestamp và ghép mô tả/timeline mà không bịa thông tin ngoài dữ liệu đã được cấp.

### 9.1. Module và đường tích hợp

| Module | Trách nhiệm |
|---|---|
| [VisionChatService](../src/application/services/vision_chat.py), [policy](../src/application/services/vision_chat_policy.py) | Nhận explicit image bytes/question, bind owner/source và kiểm response có uncertainties. |
| [CORE image adapter](../src/infrastructure/inference/core_vision_chat.py) | Gọi đúng CORE/mmproj đã có, không đổi model hoặc tự tải projector. |
| [NativeVideoSampler](../src/infrastructure/video_sampler.py), [contract](../src/application/services/video_contract.py) | Decode nguồn trong worker cô lập, trả frame PNG và decoded timestamp đã đối chiếu. |
| [Video description](../src/application/services/video_description.py) | Hỏi từng frame và giữ nguồn/timestamp thay vì diễn giải như đã xem mọi frame. |
| [OCR API](../apps/api/routes/ocr.py) | Đường HTTP hiện có cho PDF/image đã upload; xem phần 4. |

Image-chat/video services dùng application ports, không có generic `/vision` hoặc `/video` upload route trong main API hiện tại. Không gửi video vào `/chat/completions` rồi mặc định coi text route đã hỗ trợ media. Các port này không tự lookup arbitrary path/URL hoặc persist media.

### 9.2. Ảnh và nguồn không nhìn thấy

Image input tối đa 8 MiB; normalized PNG tối đa 4 MiB, được bind bằng hash/processor. Metadata/pixel normalization nằm trong native boundary; question và text trong ảnh không được làm system instruction hoặc chọn tool. CORE hiện có được hỏi với max output 1024; output là answer + uncertainties, không có confidence tự khai được coi là đã hiệu chuẩn.

Chữ mờ, nhãn chưa rõ hoặc field không nhìn thấy phải được giữ là không chắc/không có evidence; heading/logo không tự xác nhận một identity field khác. Validation shape/source không chứng minh nhận dạng mọi ảnh đúng. OCR/table extraction có contract riêng tại mục 4.4, không gộp mọi kết quả vision thành dữ liệu đã xác minh.

### 9.3. Sampling video và timeline

Video nhận explicit bytes tối đa 32 MiB; schedule có **1–3 timestamp duy nhất, tăng dần, trong 0–30.000 ms**. Sampler dùng FFmpeg/ffprobe qua sandbox; format/codec ngoài tập con bị từ chối. Frame output tối đa 1 MiB/frame, bounded whole output; mốc timestamp lấy từ decoded clock/rational metadata, không chỉ gán lại số client yêu cầu.

Mô tả video là suy luận từ những frame đã lấy, không phải dense temporal understanding hoặc nhận dạng mọi sự kiện giữa frame. Service giữ source digest, owner và timestamp qua từng bước; một frame/model fail không được che bằng mô tả đầy đủ giả.

[D66 provided-transcript timeline](progress/D66_PROVIDED_TRANSCRIPT_FRAME_TIMELINE.md) ghép frame với transcript/timestamp **được cung cấp**; ASR attempts của lượt đó là 0. Normalized audio không tự làm transcript trở thành lời nói đã xác minh, và timeline join repeat-identical không chứng minh live ASR chính xác. Video audio/Voice là các đường xử lý riêng.

### 9.4. Setup và kết quả đã đo

Dùng native sandbox prerequisites ở phần 4, thêm FFmpeg/ffprobe đã provision và CORE chạy **có mmproj** theo mục 1.8. Không tải vision model mới; launcher `start-core.py` text-only không đủ để chứng minh vision sẵn sàng. Trên máy Ubuntu mới thiếu media tools, chuẩn bị rồi kiểm binary:

```bash
sudo apt-get install ffmpeg
ffmpeg -version
ffprobe -version
```

Ghép application ports phải do trusted host gọi với owner/source bytes và budget; không có flag main API tự bật toàn bộ video capabilities. Để dùng HTTP đã có, upload ảnh/PDF rồi gọi `/files/{id}/ocr?mode=vlm` theo phần 4. Không chạy lại native/model benchmark để kiểm định dạng tài liệu.

| Receipt lịch sử | Quan sát thực | Giới hạn |
|---|---|---|
| [D63 image goldens](evidence/d63-first-image-goldens-result.json) | 4 native image attempts, 4 image CORE attempts, cohort wall **4.513 s** | Synthetic goldens; `semantic_validation=false`, không human-independent. |
| [D64 frame sampling](evidence/d64-first-video-sampling-result.json) | 2 sample records, 0 model attempts, cohort wall **0.931 s** | Chỉ native sampling/metadata, không phải chất lượng mô tả. |
| [D65 frame descriptions](evidence/d65-first-frame-description-result.json) | 3 image CORE attempts, cohort wall **2.700 s** | Frame thưa và oracle hẹp; không p95 hoặc video-wide accuracy. |
| [D66 transcript/frame](evidence/d66-first-transcript-frame-result.json) | 3 image CORE attempts, **0 ASR**, cohort wall **2.994 s** | Provided transcript, không live speech recognition. |

Các wall durations là toàn cohort được protocol đó đo, không phải TTFT hoặc latency một frame. D62 OCR quality và D67 RAM/VRAM/context đã được phân tích ở phần 1/4; không cộng các cohort hoặc dùng cap worker làm RSS thực đo. Test software hiện tại thuộc mục 12.7; full multimodal/UI/product acceptance có scope riêng.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">10. Voice</h2></summary>

**Mục đích:** Thu âm có chủ đích, nhận diện speech, ASR → CORE → TTS, phát lại audio và quản lý phiên/cancellation/resource ownership. Đường Voice chính là **composition đánh giá tùy chọn**, mặc định tắt, không phải một dịch vụ sản phẩm đã được bật tự động.

### 10.1. Module và model/runtime hiện tại

| Thành phần | Triển khai của đường main voice |
|---|---|
| [Factory](../apps/api/voice.py), [routes](../apps/api/voice_routes.py) | Ghép UI/session vào API hiện có khi flag/purpose/manifest hợp lệ. |
| [Browser client](../apps/web/voice/recorder.mjs), [session client](../apps/web/voice/session.mjs) | Capture/stop/cancel và quản lý audio/UI cùng origin. |
| [VoiceSession](../src/application/services/voice_session.py), [pipeline](../src/application/services/voice_pipeline.py) | Identity-bound admission, vòng đời prepare/turn/release và stage ownership. |
| [NativeRuntime](../src/infrastructure/voice/native.py), [manifest](../src/infrastructure/voice/manifest.py) | Dùng đúng artifact/SDK/source được pin, worker offline, không tự chọn/download model. |
| VAD | Silero ONNX CPU theo artifact đã pin, kết hợp các presence checks của runtime. |
| ASR | Đường main hiện dùng **Qwen3-ASR-0.6B**, CUDA FP32 theo [runtime](../src/infrastructure/voice/asr_runtime.py). Có code/candidate Whisper không đồng nghĩa được main tự chọn. |
| CORE | Borrow đúng `qwen3.5-9b-core` đang phục vụ, không sở hữu quyền thay/stop original backend. |
| TTS | **VieNeu v3 Turbo**, ONNX FP32 CPU, 8 threads; [reading policy](../src/infrastructure/voice/reading_policy.py) dùng giọng **Trúc Ly**. |

ASR allocator có cap riêng; đó không phải số VRAM thực đo. TTS CPU không đồng nghĩa whole Voice không dùng GPU: ASR và CORE vẫn dùng GPU. Qwen3-TTS/Piper của D70 là các lượt so sánh lịch sử, không phải model TTS main hiện tại.

Mục tiêu owner hiện là tiếng Việt, giọng nữ miền Bắc, ngưỡng chờ mong muốn 4 s. English/custom-language mở rộng và quyết định model/voice/default sản phẩm vẫn cần scope riêng. Reading policy giữ display text và speech rendering/phone edits riêng để đọc ngày/giờ, thuật ngữ English và số La Mã; không coi một bản sửa phát âm là thay model hoặc đã đạt mọi ngữ cảnh.

### 10.2. UI, pairing và ranh giới xác thực

UI main ở **`/voice` trên cùng API origin**, chỉ có khi factory Voice được bật. Nó có boundary cùng-origin riêng; không mở CORS hoặc bỏ chặn Origin của các API ở phần 2.

| Đường dẫn | Identity / mục đích |
|---|---|
| `POST /api/v1/voice/pairing` | Direct-local bearer; body phải rỗng, cấp pairing code một lần, TTL 120 s. |
| `/api/v1/voice/status`, `/prepare`, `/release`, `/turn`, `/cancel` | Operator API dùng bearer; method GET cho status, POST cho các action còn lại. |
| `POST /ui/voice/pair` | Trình duyệt redeem code và nhận opaque HttpOnly session cookie, TTL 900 s. |
| `/ui/voice/status`, `/prepare`, `/release`, `/turn`, `/cancel` | UI cookie-bound; mutation cần same-origin và header `X-Voice-Submit: 1`. |
| `GET /voice`, `/voice/assets/{asset}` | UI/assets allowlist, CSP và private headers. |

Browser không nhận permanent bearer để lưu localStorage. Session/grant được giữ trong RAM, revalidate credential binding theo principal file; revoke token hoặc restart có thể làm phiên không còn dùng được. Pairing không tự prepare/nạp workers. Microphone yêu cầu thao tác/quyền người dùng trên localhost phù hợp; không tự thu khi mở/reload trang.

### 10.3. Prepare, lượt nói và dừng

```text
Operator bearer → pairing code → owner ghép trên /voice
  → Prepare: kiểm manifest/CORE/resources, nạp đúng nhóm worker
  → Owner bắt đầu thu → Stop → gửi một lượt audio
  → Normalize/presence/VAD → ASR → CORE → reading policy → TTS
  → Trả text/audio có source/operation identity → browser phát
  → Cancel hoặc Release: hủy/join đúng công việc và trả ownership
```

Recorder có auto-stop 30 s; Stop/Hủy/Escape/chuyển tab có cleanup capture theo luồng đã kiểm. Không coi browser stop là bằng chứng mọi native process đã được giải phóng; server cancel/release và worker receipts xác nhận phần đó. Audio/recording là ephemeral trong flow, không tự lưu vào Conversation/Memory hoặc file journal.

No-speech/không đủ presence phải được từ chối trước ASR/CORE/TTS; không tạo câu trả lời từ silence. Input/media/stage limits cụ thể còn phụ thuộc manifest/adapter, không chứng minh mọi recording dài 30 s đều được backend chấp nhận. Một chủ phiên giữ resource group; request cạnh tranh trả busy thay vì tự nạp thêm model/queue vô hạn.

[GPU admission](../apps/api/voice_admission.py) điều phối các đường gọi được đăng ký trong một process. Nếu cleanup/resource state không còn chứng minh an toàn thì quarantine; không refund budget hoặc chạy tiếp chỉ để đạt kết quả. CORE borrowed vẫn phải còn sống sau release/shutdown khi runtime không sở hữu process đó.

### 10.4. Setup và mở trang

Repo có các UI/evaluation entry point cũ tại `apps/voice` và `apps/voice_trial`; chúng không tự thay cho main Voice. Đường dưới yêu cầu artifact/SDK đã provision và private manifest còn hợp lệ với đúng source/artifact/runtime hiện tại. **Chưa có installer tổng hợp Voice cho máy trắng** trong hướng dẫn này; không dùng tải model latest hoặc sửa manifest hashes chỉ để vượt gate. [Integration review](progress/D74_VOICE_INTEGRATION_REVIEW.md) và [native reading result](progress/D74_NATIVE_READING_WORKFLOW_RESULT.md) ghi các prerequisite/approval đã dùng.

CORE phải sẵn sàng riêng; cung cấp auth file và absolute path manifest đánh giá đã được chuẩn bị. Từ repository, dùng terminal API riêng:

```bash
export ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json"
export ASSISTANT_VOICE_MANIFEST="/absolute/path/to/reviewed-voice-manifest.json"
export ASSISTANT_VOICE_PURPOSE=integration_evaluation
export ASSISTANT_VOICE_ENABLED=1
uv run --no-sync uvicorn apps.api.voice:create_app --factory \
  --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Thay manifest placeholder trước khi chạy. Factory mặc định trả main app khi flag 0; flag/purpose/prerequisite sai bị từ chối. `apps.api.main:app` không tự đọc flag này để tạo UI Voice. Giữ một worker; không chạy đồng thời extraction factory phần 5 như thể hai composition tự hợp nhất.

Để cấp một pairing code khi operator chủ đích mở phiên đánh giá:

```bash
uv run --no-sync python - <<'PY'
"""Request one temporary pairing code without sharing the permanent API credential with the browser."""
import getpass
import logging
import httpx

logging.basicConfig(level=logging.INFO)
token = getpass.getpass("API token from Vault: ")
with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=10) as client:
    response = client.post("/api/v1/voice/pairing", headers={"Authorization": "Bearer " + token})
    response.raise_for_status()
    result = response.json()
    logging.info("voice_pairing_code_requested ttl_seconds=%d", result["expires_seconds"])
    print("Temporary pairing code:", result["code"])
PY
```

Mở `http://127.0.0.1:8000/voice` trên cùng máy, nhập code trong 120 s, rồi Prepare. Code là capability tạm, không chia sẻ công khai; không paste bearer vào trang. Hết phiên dùng Release và chờ trạng thái idle; shutdown không tự dừng original CORE. Các lệnh này là hướng dẫn, không tạo session/nạp model thực trong lượt viết tài liệu.

### 10.5. Kết quả đã kiểm chứng và gate còn mở

[D70 owner listening](progress/D70_OWNER_LISTENING_20261103.md) ghi owner nghe đủ 24 clip bằng loa và không có lỗi âm thanh kỹ thuật, kèm nhận xét chất lượng/ngôn ngữ; không xóa các sai phát âm hoặc gọi mọi candidate đạt tự nhiên. [D70 status](progress/D70_ACCEPTANCE_STATUS.md) và [D74 feedback](progress/D74_OWNER_VOICE_FEEDBACK_20261103.md) giữ từng mốc thay vì dùng automated reviewer thất bại để giả hearing PASS.

[B3 ADR178 receipt](evidence/d74-main-voice-b3-adr178-result.json) ngày 2026-11-07: **4/4 speech exact-complete PCM**, server **2.608–3.747 s**, **2/2 negative** từ chối đúng; stage counts VAD 6/ASR 4/CORE 4/TTS 4, ba worker join sạch, release HTTP 200/idle và borrowed CORE còn sống. Prepare khoảng **51.449 s** được đo riêng, không nằm trong warm turn latency. Các lượt B3 trước chưa đạt được giữ nguyên; đây là panel giới hạn, không mọi mic/room/noise hoặc cold-start SLO.

[B4 owner acceptance](progress/D74_B4_OWNER_ACCEPTANCE.md) ngày 2026-11-08 là **owner chấp nhận kèm ghi chú** phần first-audible thiết bị thật. Physical first-audible ≤4 s khách quan vẫn **chưa đo**; server time/page/software markers không thay thế âm thanh thực tới tai. Quyết định cuối model/giọng/default/rights/product activation vẫn mở. B3/B4 gắn source snapshots của chúng; có thay đổi nguồn sau đó cần đọc ghi chú preservation/manifest, không coi score là một panel chạy lại trên mọi checkout.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">11. Tool orchestration</h2></summary>

**Mục đích:** Kết nối skill, tool và MCP qua contract hữu hạn, host-owned scope, hook controls và checkpoint/resume mà không biến model output thành quyền thực thi.

### 11.1. Skill contract và trust

[Skill contract](../src/application/services/skill_contract.py) nhận manifest version 1, tối đa 32 KiB: ID/version/description/instructions/permissions. Permissions chỉ từ tool catalog được host hỗ trợ. [source-reader.v1.json](../configs/skills/source-reader.v1.json) là **ví dụ inert**, không tự install/activate vì nằm trong repository.

Host tạo review gắn owner/workspace/exact raw digest/permissions, rồi nhận exact-content trust confirmation trước installation; review TTL 120 s, một lần, cap 32 pending/64 installations. Sửa version/nội dung/quyền cần review mới. SHA-256 hoặc ID tác giả tự khai không chứng minh publisher authenticity; đây không phải marketplace/plugin installer tự động.

Ví dụ chỉ parse/kiểm schema của manifest, không cài hoặc cấp quyền:

```bash
uv run --no-sync python - <<'PY'
"""Validate the inert repository skill example without installing or activating it."""
import logging
from pathlib import Path
from src.application.services.skill_contract import parse_manifest

logging.basicConfig(level=logging.INFO)
parse_manifest(Path("configs/skills/source-reader.v1.json").read_bytes())
logging.info("skill_manifest_validated installation_performed=false")
PY
```

### 11.2. MCP allowlist boundary

[MCP adapter](../src/application/services/mcp_adapter.py) bind server/owner, exact tool/schema hashes và trusted local validators. Peer tool list/schema không được tự mở rộng allowlist. Giới hạn adapter gồm 8 requests và 64 KiB output; trả text là untrusted data, không mở authority cho callbacks/approval/model routing.

[Stdio transport](../src/infrastructure/mcp_stdio.py) sở hữu process/request cleanup và explicit host configuration. Runtime không tự spawn một executable/argv lấy từ manifest, README hoặc model; không có production MCP server tự đăng ký hoặc endpoint install công khai trong main API. Việc component đã kiểm thử không chứng minh một server ngoài chưa được review đáng tin cậy. [D76 guide](progress/D76_MCP_ALLOWLIST_ADAPTER.md) ghi protocol, transport và những gì chưa triển khai.

### 11.3. Hooks, plans và recovery

[GuardedToolRun](../src/application/services/tool_hooks.py) thực hiện trusted pre/post/error/stop checks với owner/run identity và finite effects. Source/model không được thay hook/policy. Stop/cancel/close join phần công việc sở hữu trước khi trả admission; native child vẫn là trách nhiệm của adapter/handler sở hữu nó.

[Run planner](../src/application/services/run_planner.py) nhận plan version 1 tối đa **8 typed steps**, **120 s kể cả pause**, **12 tổng attempts**, tối đa **2/step**, output budget **262.144 byte**. Attempt budget không phải lệnh tự retry; bước tiếp theo/retry/resume cần action host tường minh. Sau write bị lỗi/mất acknowledgement/stop hoặc output không hợp lệ, trạng thái có thể là **uncertain** và không dispatch tiếp để đoán kết quả.

[Plan checkpoints](../src/infrastructure/plan_checkpoints.py) giữ state/budget/identity được xác thực theo protocol. Restore không khôi phục file descriptors, live source pins hoặc approval grants. Host phải kiểm lại binding/tool revision/nguồn/quyền hiện tại; không replay write đã xong hoặc chưa rõ chỉ từ một checkpoint. Xem [D77 hooks](progress/D77_TRUSTED_TOOL_HOOKS.md), [D78 recovery](progress/D78_BOUNDED_PLANS_RECOVERY.md).

### 11.4. Routing qua capability hiện có

[HarnessToolRun](../apps/api/services/harness_tools.py) map tên tool cố định tới workspace read và các action patch/check đã có. Host attach đúng action/target approval reference riêng; attach không approve pending/expired/rejected request. PatchService/CheckService vẫn là nơi kiểm/consume one-shot grant thật.

Reference bị lấy ra trước action attempt, không được phục hồi từ model/checkpoint. Read result, skill instruction, MCP text hoặc chữ “đã duyệt” không cấp quyền shell, patch, network hoặc model replacement. [D79 routing](progress/D79_DETERMINISTIC_TOOL_ROUTING.md) giữ evidence về actual fixture-approved patch/read và pinned Ruff, không phải blanket permission cho mọi tool.

### 11.5. Setup và giới hạn triển khai

Không có một cờ “bật tất cả tools” trong main API. Chuẩn bị workspace/action services ở phần 7, rồi trusted application code mới bind owner, catalog, skill review, MCP server/validators, hooks và checkpoint store theo từng capability. Không tự tải server package/plugin hoặc đăng ký skill chỉ để hoàn thiện tài liệu.

Các component D75–D79 có local verified scope, nhưng chưa đồng nghĩa production installation, autonomous agent loop hoặc API tool execution mở cho client. Các test trong mục 12.7 dùng trusted fixtures và local child controls; một transport/plan PASS không chứng nhận mọi external server/model response an toàn.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">12. Vận hành và chất lượng</h2></summary>

**Mục đích:** Vận hành có audit, đo hiệu năng đúng nguồn, kiểm resource/cleanup, backup/restore và phân biệt software gates với model, thiết bị và quyết định release.

### 12.1. Entry points và dependency vận hành

| Entry point / tài nguyên | Vai trò |
|---|---|
| `apps.api.main:app` | API cơ bản; feature flags default-off, storage tùy DATABASE_URL. |
| `apps.api.grounded_extract:create_app --factory` | Structured extraction optional, prerequisite/voice exclusion ở phần 5. |
| `apps.api.voice:create_app --factory` | Main Voice integration evaluation, manifest/purpose ở phần 10. |
| `scripts/start-core.py`, `scripts/start-model.py`, Compose | Cách khởi động inference đã phân biệt ở phần 1, một profile/cổng 8080. |
| PostgreSQL, Vault, Qdrant, SearXNG | Hạ tầng dùng chung đã có; không tự tạo instance thứ hai để bỏ qua lỗi cấu hình. |
| Private roots/backups/runtime/model assets | Có lifecycle/pin/permission riêng, không thuộc bundle source công khai. |

Chạy `uv sync --locked --dev` từ repository để tái lập dependency ứng dụng. Python 3.12 là môi trường operator được dùng cho các worker/SDK và Vault-read paths đã ghi; không tự nâng môi trường để vượt lỗi TLS hoặc đổi package pin. API không tự đọc `.env`, chạy migration, unseal Vault hoặc tải model khi startup.

### 12.2. Log, health và metrics

[Application logging](../apps/api/core/logging_config.py) bật INFO cho `apps.api`/`src`, giữ deployment handlers sẵn có. Log dùng IDs/state/count/finite codes; không dùng prompt, audio/transcript, raw program/model output hoặc credential làm audit payload. Private artifacts có thể chứa nội dung cần bảo vệ và không tự trở thành file có thể commit.

[Pool telemetry](../src/infrastructure/database/pool_telemetry.py) phục vụ quan sát pool, còn [InferenceObservability](../src/application/services/inference_observability.py) là wrapper tùy chọn với started/completed/failed/cancelled/active/peak, token usage và wall latency. Trace ID không chứa body và không phải quyền truy cập dữ liệu. Không có public metrics endpoint/Prometheus deployment được suy ra từ class này.

Health API chỉ kiểm request được trả, không chứng minh database/model/provider readiness. Phân biệt backend `/health`/`/v1/models`, private API auth, nguồn dữ liệu và feature readiness. D83 ở mục 1.7 đo TTFT **169.451 ms** bằng một warm direct-backend stream; nonstreaming TTFT/client decode không đo phải để unavailable, không gán tổng wall thành TTFT hoặc dùng 0 thay số thiếu.

### 12.3. Resource policy và failure handling

Native parsers/checks/media, embedding worker, GPU admission và application quotas có bound khác nhau. Address-space cap/RLIMIT, Python allocator cap, RSS RAM, VRAM allocation, model size và đĩa là các đại lượng khác nhau; không dùng thay nhau trong báo cáo. Sampled maximum không chứng minh true peak hoặc minimum hardware requirement.

[D85 bounded faults](progress/D85_BOUNDED_FAILURE_LOAD_POLICY.md) đã kiểm MemoryError/ENOSPC trong worker/tmpfs nhỏ cô lập, không làm đầy đĩa host hoặc thử host/model OOM. Cohort 100 simultaneous native reads cho **1 accepted, 7 busy, 92 attempt-limit denials**; không phải 100 successful requests/s. Không tăng cap/retry để biến một admission failure thành PASS.

Cancellation phải join owned task/process/namespace trước khi đóng capability; timeout trả về không tự chứng minh child đã chết nếu không có receipt. [ADR-179](ADR/179-retire-sandbox-namespace-before-timeout-returns.md) ghi việc chờ namespace retirement. Với write uncertainty, kiểm authoritative receipt và source hiện tại trước action mới; cleanup metadata không phải rollback đã sửa file.

### 12.4. Backup và restore

| Miền dữ liệu | Nội dung cần giữ cùng nhau |
|---|---|
| Conversation/Memory | Database/schema, identity/ownership, grant và source invalidation definitions. |
| File/RAG | Database + blob root/namespace + principal bindings + collection/fingerprint/job/tombstone obligations. |
| Coding/research/plan history | Private roots, artifact bytes/hashes và metadata; không coi recovered history là execution grant. |
| Model/runtime/config | Đúng artifact revisions/digests, approved selection, rollback config và runtime pins. |

[D84 restore drill](progress/D84_ISOLATED_RESTORE_DRILL.md) đã restore PostgreSQL dump vào **probe database cùng cluster**, khớp 12 application tables/ACL; Qdrant gốc rỗng, chỉ dùng hai canary collections với 3 vector 8 chiều; blob fixture 39 byte và bốn config không secret được roundtrip riêng. Không gọi đây là restore một populated production index/user blob store hoặc off-host disaster recovery.

[PostgreSQL recovery script](../scripts/postgres_recovery_acceptance.py), [paired file recovery](../scripts/file_storage_recovery_acceptance.py) và [release recovery drill](../scripts/release_recovery_drill.py) có preflight/scope riêng. Không chạy chúng chỉ để kiểm Markdown, restore đè original stores, xóa backup cũ hoặc restart dịch vụ dùng chung ngoài phạm vi đã được duyệt. Backup chứa data/role hashes phải giữ private; RPO/RTO, retention/encryption/off-host failover chưa được suy ra từ same-cluster probe PASS.

### 12.5. Tests, CI và full regression

| Loại kiểm chứng | Chứng minh điều gì |
|---|---|
| Fixture/unit/contract tests | Logic boundary, schema, lifecycle và các fault được mô phỏng; không tự đo chất lượng model/provider. |
| Native fixture tests | Parser/process/isolation thật trong phạm vi fixture; không phải mọi file/media ngoài đời. |
| Live integration | Database/Qdrant/CORE/provider thật theo prerequisites và source freeze của lượt đó. |
| Model evaluation | Cùng corpus/oracle/options, giữ failures và uncertainty; cần tách khỏi pytest harness PASS. |
| Owner/device acceptance | Nhận xét/quan sát của owner trên thiết bị, không tự biến thành phép đo vật lý hoặc general quality. |

Lệnh focused chạy theo từng phần; lệnh phát triển rộng là `uv run --no-sync python -m pytest tests benchmarks/tests -q`, nhưng live prerequisites/flags quyết định những gì thực sự chạy. SKIP, deselection hoặc collection thành công không thay thế acceptance.

[CI workflow](../.github/workflows/ci.yml) chạy lint/format, tests với [hosted exclusions](../.github/ci/hosted-runner-exclusions.txt) và [quarantine](../.github/ci/hosted-runner-quarantine.txt), rồi build/promote artifacts theo workflow. Scope hosted CI khác full local; không cộng counts hoặc dùng một green CI để nói mọi native/model/database gate đều đã chạy. Branch promotion/artifact không tự là tag/GitHub Release hay Home Server deployment.

Full kiểm chứng thật dùng [full_regression.py](../scripts/full_regression.py) và [D87 runbook](progress/D87_FULL_REGRESSION_20261106_RUNBOOK.md). Chỉ chạy khi operator đã chuẩn bị credential/runtime/quiet host và directory mới; script đọc secret qua workflow hiện có trong memory, redacts log và kiểm source scope trước/sau:

```bash
uv run --no-sync python -m scripts.full_regression data/backups/CHOOSE_A_NEW_PRIVATE_RUN_DIRECTORY
```

Đây là full live run có thể tạo/cleanup owned fixtures và kéo dài hàng chục phút, không phải bước đã chạy trong lần viết tài liệu. Không dùng skip/exclusion, tăng CPU cap hoặc sửa oracle để gọi full PASS.

### 12.6. Snapshot chất lượng và release

[D87 retained result](progress/D87_CURRENT_FULL_RESULT.md) ngày 2026-11-09, source tree của `production` `dd7fac3` (`5f2653d`): run 3 **6233 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, pytest **1830.43 s**, 821 source files không đổi. Run 2 trên cùng source **6232 PASS / 1 FAIL** do reranker chạm trần CPU vẫn được giữ. Đây là lịch sử gắn source freeze, không khẳng định local Git ref hôm nay đã được đổi hoặc full đã chạy lại trên mọi commit tài liệu.

Rủi ro CPU margin của reranker khoảng 1–3% vẫn được ghi, không tăng cap hoặc chọn score cũ thay failed run. Source changes phải được đối chiếu với execution scope; quyết định chấp nhận docs-only delta cho tag thuộc owner theo D90, không tự đánh dấu release.

[Release candidate status](progress/RELEASE_CANDIDATE_STATUS.md), [outstanding ledger](progress/OUTSTANDING_WORK_STATUS.md), [D88 provenance](progress/D88_MODEL_PROVENANCE_SCORECARD.md), [D89 checklist](progress/D89_MANUAL_ACCEPTANCE_CHECKLIST.md) và [D90 dossier](progress/D90_RELEASE_DECISION_DOSSIER.md) là nguồn theo dõi gate. Dự án vẫn **engineering candidate / NOT RELEASED**: D60 deferred, D81 full-flow/native-quality scope còn mở, quyết định cuối model/voice/rights/default/product và D89/D90 chưa được tài liệu này đóng. D88 distribution rehearsal chỉ được diễn giải đúng scope khi phân phối.

Không đổi lựa chọn model/provider/default, không tạo tag/release/deploy hoặc điền owner form chỉ vì đã viết đủ 12 component. Thay đổi kiến trúc phải có ADR; thay model cần benchmark/performance/resource/migration/rollback và phê duyệt như phần 1.

### 12.7. Kiểm tra cho đợt hoàn thiện phần 8–12

Lệnh đã chạy ngày 2026-11-10, phạm vi 34 file, credential/model/provider runtime không được gọi thật:

```bash
env -u DATABASE_URL uv run --no-sync python -m pytest \
  tests/test_web_search_policy.py tests/test_search_pipeline.py \
  tests/test_searxng_search.py tests/test_web_search_startup.py \
  tests/test_web_fetch_policy.py tests/test_browser_policy.py \
  tests/test_research_policy.py tests/test_claim_validation_policy.py \
  tests/test_research_report_policy.py tests/test_research_session_policy.py \
  tests/test_vision_chat_policy.py tests/test_vision_chat.py \
  tests/test_vision_chat_ports.py tests/test_video_sampler.py \
  tests/test_video_description.py tests/test_vision_quality_cases.py \
  tests/test_voice_pipeline.py tests/test_main_voice_identity.py \
  tests/test_main_voice_routes.py tests/test_main_voice_admission.py \
  tests/test_main_voice_extraction.py tests/test_main_voice_session.py \
  tests/test_skill_contract.py tests/test_skill_tools.py \
  tests/test_mcp_adapter.py tests/test_mcp_stdio.py \
  tests/test_tool_hooks.py tests/test_run_planner.py \
  tests/test_plan_checkpoints.py tests/test_harness_tools.py \
  tests/test_inference_observability.py tests/test_full_regression.py \
  tests/test_release_recovery_drill.py tests/test_application_logging.py -q
```

**910 PASS, 0 FAIL, 0 SKIP trong 13.38 s** trên lượt combined này; không phải 910 tests riêng cho mỗi component. Có native media/local child fixtures và mocked transport/model boundaries, không có fresh Brave probe, nghe audio, load/download weights hoặc full live regression mới. Các counts ở phần 1–7 và các checkpoint lịch sử là những invocation khác, không được cộng thành một full run.

Các ví dụ command/client/manifest và liên kết được kiểm tra riêng; chỉ cập nhật `DOCUMENTATION.md`. Nội dung phần 1–7, model/source code/config/Docker/Vault/database và dữ liệu người dùng không thay đổi trong đợt hoàn thiện này.

### 12.8. Khoảng trống sản phẩm: harness, CLI/UI, context và generation

Đối chiếu ban đầu ngày 2026-11-10 phát hiện thiếu CLI/product surface/context composer/skill binding và generation. Sau yêu cầu triển khai của owner, **v1 opt-in đã có CLI và task-run API readonly**, skill instruction binding và ba context priorities. Semantic compaction, automatic memory, durable product resume và server Conversation sync còn pending. Vision/video understanding cũ không bị đổi thành generation.

[Thiết kế sản phẩm harness](HARNESS_PRODUCT_DESIGN.md) là target architecture; [runbook v1](HARNESS_CLI_DESKTOP_RUNBOOK.md) phân biệt command đã chạy được với phần còn thiếu. UI assets llama.cpp đúng pin đã tải/checksum; local cookie gateway có real SSE. Desktop hiện là isolated Brave/Chromium app-window, chưa phải native installer; UI history vẫn IndexedDB, không tự có PostgreSQL Conversation semantics.

[Backlog HAR-001–015](progress/HARNESS_PRODUCT_BACKLOG.md) ghi priority, dependency, effort, risk, AC và trạng thái PARTIAL cụ thể. [ADR-180](ADR/180-proposed-unified-harness-product-surface.md) đã được cho triển khai theo giai đoạn; [ADR-181](ADR/181-checkout-cli-desktop-and-readonly-specialist-runs.md) ghi slice hiện tại. Generation có contract/jobs/ACL/cancel qua synthetic tests, nhưng không có adapter/model được chọn nên actual image/video vẫn unavailable.

Các task này bổ sung phạm vi phát triển sau baseline; không đổi lựa chọn model, không tự đóng D60/D81/release gates hoặc biến test của component cũ thành PASS cho chức năng mới.

</details>

<details open>
<summary><h2 style="display: inline; margin: 0; border-bottom: 0;">13. CLI, chat UI và desktop</h2></summary>

**Mục đích:** Cung cấp một entrypoint sử dụng các component qua CLI và giao diện chat local. [Hướng dẫn đầy đủ](HARNESS_CLI_DESKTOP_RUNBOOK.md), [source CLI](../apps/cli/main.py), [optional app factory](../apps/harness/main.py).

### 13.1. Khởi động

```bash
uv sync --locked --dev
uv run --no-sync la doctor
uv run --no-sync la init
uv run --no-sync la ui prepare
uv run --no-sync la serve
```

`init` chỉ dành cho principal local mới, từ chối overwrite; dùng đúng credential/identity hiện có nếu cần tích hợp dữ liệu cũ. CORE phải đang chạy theo phần 1. Backend mặc định `127.0.0.1:7090`; terminal khác mở:

```bash
uv run --no-sync la desktop
```

Tài nguyên UI local đã có 70 file/10,074,640 byte giải nén; không tải model mới. Desktop là cửa sổ riêng Brave/Chromium, backend vẫn chạy riêng; chưa có native installer. Có thể dùng `la ui open` để mở trong browser thông thường. Pairing không đưa app bearer vào URL/localStorage.

### 13.2. Harness, context và skill thực tế

CLI có status/chat/run/runs/context/skills/jobs và generation commands. Task v1 tối đa 4 readonly tool calls được chỉ định rõ + một CORE completion, deadline 120 giây; không shell/write/autonomous tool loop. Skill review/install/show/remove bind exact hash/owner/workspace, được recheck trước/sau execution và thực sự chèn instructions dưới host policy.

Context hỗ trợ `evidence-first`, `recent-turns`, `strict`, exact tokenizer fit, whole-turn selection, source dedup và omission receipts. Chưa có semantic summary/automatic memory. Mặc định state process-local; optional state-dir chỉ archive run metadata/digests, không lưu raw results hoặc phục hồi grants/execution. UI chỉ chat text CORE/Fast và lưu history bằng IndexedDB, chưa sync Conversation DB.

### 13.3. Kiểm chứng và phần còn mở

209 focused/related tests PASS trong 2.38 s; invocation riêng 50 auth/security/preset tests PASS trong 0.80 s. Actual CLI→review/install skill→native read synthetic source→CORE trả đúng port 7443 kèm line citation; native SSE trả `STREAM-READY`. Browser đã hiển thị UI upstream và fixture response; desktop launch đã chạy, chưa có physical native-window acceptance. Các thất bại/giới hạn và lệnh test chi tiết nằm trong runbook, không là full regression mới.

Generation job/API/CLI đã có software contract; actual model backend **chưa được duyệt/cấu hình**, nên `generate image/video` báo unavailable. Không dùng synthetic artifacts làm bằng chứng sinh ảnh/video thật. [Candidate screening](GENERATION_CANDIDATE_SCREENING.md) không đổi Model Registry. [Backlog](progress/HARNESS_PRODUCT_BACKLOG.md) giữ toàn bộ AC chưa đạt; D87 cũ không bao phủ source additions mới và release gates vẫn mở.

### 13.4. Follow-up v1.1: đánh giá thật và metadata qua restart

[HAR-008 paired result](HAR008_PAIRED_EVALUATION_RESULT.md): 12 case/24 native attempts, baseline strict success 5/12, skill 6/12; giữ format/quote/null failures và một baseline false positive. Measurement complete, promotion NOT_QUALIFIED; không kết luận ngang model lớn.

[Native context packing](HAR006_NATIVE_CONTEXT_PACKING_RESULT.md) đã đo history 24,131 tokens qua tokenizer/template thật. Evidence-first giữ source và bỏ history; recent-turns/strict giữ history và bỏ source với reason rõ. Zero completions trong probe này; chưa là semantic-quality hoặc peak-RAM/VRAM benchmark.

[Signed metadata history](HARNESS_METADATA_HISTORY.md), [ADR-182](ADR/182-opt-in-signed-harness-metadata-history.md): bật tùy chọn bằng `uv run --no-sync la serve --state-dir data/harness-history`. Giữ IDs/state/events và request/result/context hashes trong private signed snapshots; không task/answer/source text, skill hoặc approval token. Restart biến active run thành interrupted, không replay. Archive chỉ có metadata, `result_available=false`; muốn chạy lại phải tạo task mới và fresh trust.

Final combined **294 tests PASS / 0 FAIL / 0 SKIP, 3.80 s**, có actual subprocess SIGKILL recovery, post-rename fsync fault, owner isolation và privacy checks. Separate-process native CORE probe trên 7092 khôi phục đúng result/context hashes; probe đã dừng, desktop 7090 giữ nguyên. Đây là partial recovery scope, không đồng bộ Conversation, durable resume hoặc full regression/release.

### 13.5. Follow-up v1.2: JSON có ràng buộc nguồn

[ADR-183](ADR/183-opt-in-source-bound-json-output-contract.md), [hướng dẫn](HARNESS_CLI_DESKTOP_RUNBOOK.md#8-source-backed-json-opt-in), [kết quả thật](HAR008_OUTPUT_CONTRACT_RESULT.md): `la run --output-contract source-value-quote-v1` là mode tùy chọn cho readonly workspace.read. Host tạo catalog nguyên dòng từ source snapshots đã retained, bỏ ASCII indentation ở nguồn trước inference và gửi schema đúng nested wrapper của runtime đang pin. Sau đó kiểm tra nguyên phản hồi đầu, không trim/cast/bóc fence/retry. Thiếu bằng chứng phải null/null; output lỗi bị giữ failed cùng owner-only ephemeral diagnostic. History chỉ có digest/state; default text, model, UI streaming và skill manifests không đổi.

Fresh R3: **48 first native calls**, text baseline/skill **8/12 mỗi nhóm**, constrained baseline/skill **12/12 mỗi nhóm**, 24/24 schema/catalog/content/provenance checks khớp. Giữ nguyên original 5/12–6/12, R1 envelope integration error và R2 sai schema binding; không sửa điểm cũ. Bộ nhỏ cùng tác giả chưa chứng minh broad quality hoặc skill giúp model giỏi hơn; HAR-008 vẫn NOT_QUALIFIED cho promotion. Final related software **323 PASS / 0 FAIL / 0 SKIP, 3.89 s**, không gọi model trong pytest, chưa full D87 mới.

Server thử7092 đã dừng; desktop7090 vẫn process v1 cũ, muốn dùng option mới cần process từ checkout mới. Không restart CORE/desktop hoặc đổi default trong lượt này. Đây là checkpoint v1.2; kết quả Q2 tiếp theo được ghi riêng ở 13.6. Compaction/memory, durable execution/catalog, media generation adapters và release gates vẫn pending.

### 13.6. Follow-up v1.3: maintenance, caller context và tài nguyên thật

[HAR-008-Q2 result](HAR008_Q2_MAINTENANCE_RESULT.md), [ADR-184](ADR/184-controlled-maintenance-and-observed-resource-evaluation.md): 24 controlled cases/34 source files, 96 first product-API calls, bốn nhóm cùng CORE/Fast512/strict/skill cũ. Text strict **11/24 mỗi nhóm**, constrained baseline **21/24**, constrained skill **23/24**. All48 constrained schema/catalog/source-origin checks valid nhưng bốn gold semantic/localization errors giữ nguyên. Skill chọn đúng quote `if not raw.isdigit():` nhưng value5 thay vì line4: hợp lệ về nguồn chưa là đáp án đúng. Không repair/rerun hoặc gọi bộ do cùng tác giả tạo là independent qualification.

Đã đo 637 resource samples và tám native streaming timing replays/58 samples riêng, không chấm lại chất lượng. Native RSS peak lấy mẫu **9,55 GiB**, GPU allocation **7,83 GiB**; first-text **0,42–0,62 s** với ca ngắn, **2,37–2,53 s** với ca dài. Scope/units/cache/limits và số gốc ở phần 1.7 và báo cáo; không task-API TTFT hoặc resource SLO.

**349 related PASS / 0 FAIL / 0 SKIP, 4.07 s**, 29 file, không model calls trong pytest. Chỉ thêm benchmark/tests/docs, không đổi production source/model/config/defaults hoặc restart primary/CORE; probe7092 đã dừng. Q2 bounded measurement complete, broad promotion NOT_QUALIFIED. Task kế tại checkpoint v1.3 là HAR-008-L1; kết quả mới ghi riêng ở 13.7, không thay model hoặc sửa điểm cũ. Các HAR/release gates khác vẫn mở.

### 13.7. Follow-up v1.4: ràng buộc target, số dòng và quote

[ADR-185](ADR/185-opt-in-target-bound-review-line-quote-contract.md), [result](HAR008_L1_REVIEW_PAIR_RESULT.md): thêm hai chế độ **opt-in nghiên cứu** `review-line-quote-v1` (value trước) và `review-quote-line-v1` (quote trước), đều cần `--review-target PATH` trùng một explicit workspace.read. Host chỉ đưa các cặp số dòng gốc–quote từ đúng target đã retained vào schema, giữ nguyên numbering khi đọc giữa file; duplicate quotes giữ từng occurrence, snapshot mâu thuẫn/schema quá lớn bị chặn. Không sửa output hoặc cấp thêm quyền read từ target field. Generic source-value-quote và default text giữ nguyên.

Đã đo hai bộ mới **48 + 72 first quality calls**, tổng124 native calls gồm bốn development controls riêng. All72 bound replies đúng cặp nguồn, nhưng chất lượng chưa ổn định: bộ đầu generic10/12 baseline/8/12 skill, value-first8/12 mỗi nhóm; bộ sau generic6/12,7/12, value-first11/12,9/12, quote-first10/12,7/12. Giữ mọi regressions/false positives, không gộp đổi cohort để quảng bá gain, không tự bật mặc định hoặc gọi source-valid là review đúng. Tại checkpoint L1, Q3 semantic rubric/workflow là bước tiếp theo; kết quả Q3 được ghi riêng ở13.8.

Final **389 related PASS / 0 FAIL / 0 SKIP, 4.63 s**, không model calls trong pytest; packaged source đúng byte, chưa full regression/release. CORE lúc đầu chưa chạy; đã xác minh checksum/pin rồi chạy đúng model/cấu hình cũ cho trial và dừng cùng app7092 sau khi lưu bằng chứng. Không tải/đổi model, không restart primary hoặc đổi Docker/Vault/DB/Qdrant. Chi tiết CLI, scope và giới hạn ở [runbook](HARNESS_CLI_DESKTOP_RUNBOOK.md#10-target-bound-review-research-modes).

### 13.8. Follow-up v1.5: phản ví dụ và tự kiểm tra có giới hạn

[ADR-186](ADR/186-native-only-finite-semantic-review-prototype.md), [Q3 result](HAR008_Q3_SEMANTIC_RESULT.md): prototype benchmark-only, không đổi workflow sản phẩm. Mười hai case mới có bốn probe cố định/case: năm lỗi, năm control phù hợp, hai caller contract chưa rõ. Hàm đối chiếu trusted chỉ thực hiện các phép toán đã đăng ký trên input cố định, không execute/import snippets hoặc code model. Model phải đưa claim code, vị trí hợp lệ và expected/observed đúng kiểu, thực sự khác nhau; các supporting locations được chốt trước. Title prose chưa được chấm ý nghĩa.

48native calls,24 initial candidates mỗi candidate có đúng một self-check đã định trước; không gold feedback/retry-until-pass. Tổng điểm single6/12→checked5/12 baseline,5/12→6/12 skill, nhưng **0/5 complete proofs trên nhóm có lỗi ở cả bốn nhóm**. Phần lớn điểm đạt từ safe controls. Giữ raw errors như đảo expected/observed, sai loại exception và thiếu caller units; không gọi source-valid hay self-review là bằng chứng độc lập hoặc bật mặc định.

**407 related PASS / 0 FAIL / 0 SKIP,4.50s**,34files, không native calls trong pytest; chưa full regression/release. Checked workflow có thêm một lượt512output tokens: median1.379s baseline/1.579s skill, không chỉ latency của lượt thứ hai.270resource samples, native RSS peak lấy mẫu khoảng7.85GiB/GPU process allocation7.83GiB; workload/process khác nên không là tối ưu RAM so với L1. Existing CORE được xác minh/chạy cho trial và đã dừng; model/config/skill/defaults và product source giữ nguyên. Q4 observation-assisted evidence design được assessed tiếp theo, semantic/adoption gate vẫn mở.

### 13.9. Follow-up v1.6: context vượt ngân sách

[Hướng dẫn và bảng bảy chiến lược](CONTEXT_MANAGEMENT_STRATEGIES.md), [ADR-187](ADR/187-opt-in-pinned-history-and-extractive-compaction.md): CLI/API có policy opt-in `sliding-window` và `extractive-compact`, độc lập với ba source priorities. Giữ nguyên current task/system/skill/pinned pairs, bỏ trọn cặp cũ theo token budget thật; compact chỉ trích nguyên văn, gắn nguồn và cache các cặp bị bỏ trong RAM owner-only, không dùng LLM viết summary. Có `la context archives/recall/forget`; TTL30phút, quota hữu hạn, không persist raw text hoặc restore consent/approval. Browser/default paths giữ nguyên.

```bash
uv run --no-sync la chat --history-policy sliding-window --history-window 8 --pin-turn 1
uv run --no-sync la chat --history-policy extractive-compact --history-window 8
uv run --no-sync la context archives
```

**462 related PASS/0FAIL/0SKIP,4.75s**,38files,55tests mới. Tám kịch bản actual-tokenizer preparation có expected retention/rejection: sliding173tokens bỏ dữ kiện cũ, pin215/compact460/recall395tokens giữ được; long pressure còn20328tokens với pin giữ nguyên. Zero completions; đây là context-presence verification, chưa phải answer quality/TTFT/peak RAM/VRAM. Compact có overhead và không luôn ngắn hơn sliding. LLM summary, file-RAG tự nối chat, layered consented memory, durable offload, tool/task-state compaction và UI controls **PENDING**; HAR-009 chỉ đóng experimental mechanics, không đóng adoption/full project gates. Ưu tiên context hiện tại làm Q4 research deferred. Existing CORE được chạy riêng rồi dừng, không tải/đổi model hoặc sửa Docker/Vault/DB/Qdrant.

### 13.10. Aevra và desktop native độc lập

Tên sản phẩm/CLI/package hiện tại là **Aevra**, command `aevra` và `aevra-desktop`; `la` vẫn là alias. Rồng trắng do owner cung cấp được dùng chung cho CLI, web/sidebar/favicon và native window/launcher, có source hashes; không vẽ lại logo hoặc thay70upstream UI files. [Guide](AEVRA_DESKTOP.md), [ADR-188](ADR/188-aevra-brand-and-native-webkit-desktop.md).

```bash
uv run --no-sync aevra logo
uv run --no-sync aevra ui open
uv run --no-sync aevra desktop
```

Desktop dùng **GTK/WebKit nhúng trong process/cửa sổ riêng**, không mở Brave/Chromium. Menu Linux đã có launcher Aevra. Khi backend chưa chạy, app kiểm identity rồi khởi động backend của nó; đóng/lỗi app dọn đúng owned children. Backend có sẵn không bị thay thế/dừng; CORE không tự được tải/nạp/dừng. Credential locations cũ giữ nguyên; history native có profile riêng và lock, không tự import Brave hoặc phục hồi approval.

**498 related PASS/0FAIL/0SKIP/5.14s**,41files,36tests mới; native WebKit thật đã load UI/brand và nhận synthetic stream/exit0,0model calls. Owned backend lifecycle kiểm riêng,23packaged files byte-match,18Python files lint/format/descriptions PASS. [Receipt](evidence/aevra-native-desktop-20261111.json), [native screenshot](evidence/aevra-native-desktop-20261111.png). Đây là Linux native implementation trên host hiện tại, chưa fully bundled AppImage/Windows/macOS hoặc release qualification. Model/config/provider/data và context/skill authorities giữ nguyên; context optimization B1 và các TODO trước còn mở.

### 13.11. HAR-009-B1: đo khả năng giữ context

[Protocol](HAR009_B1_RETENTION_PROTOCOL.md), [kết quả](HAR009_B1_RETENTION_RESULT.md), [receipt](evidence/context-retention-b1-20261111.json). Benchmark `benchmarks/context_retention.py`: 12 hội thoại tổng hợp 16 cặp (dữ kiện sớm, ràng buộc ở lượt 1, mâu thuẫn cũ–mới, việc dở kèm phiếu; mỗi loại một case tiếng Việt), 5 nhánh `full`/`legacy`/`window3`/`window3_pin1`/`compact3`, cùng CORE/preset `fast`/512 token, chấm câu trả lời đầu tiên theo token bắt buộc và token cũ bị cấm, kiểm riêng dữ kiện có trong context.

Kết quả 60/60 lượt native, không retry: đúng nghiêm ngặt `full` 11/12, `legacy` 3/12, `window3` 1/12, `window3_pin1` 3/12, `compact3` 12/12. `full` và `compact3` đều giữ đủ dữ kiện (chênh 12/11 do luật chấm chữ số); trong các cửa sổ 3 lượt, `compact3` giữ được nhiều nhất nhưng dùng trung vị trên 1210 token input so với 564 của `full`. Corpus làm truy xuất từ khóa dễ, nên đây là cận trên. 15 test mới không gọi model. Đây là đo đạc trên dữ liệu tổng hợp, không đổi default/model/config.

### 13.12. HAR-009-B2: lịch sử theo ngân sách token

[ADR-189](ADR/189-opt-in-token-budget-history-window.md), [protocol](HAR009_B2_TOKEN_BUDGET_PROTOCOL.md), [kết quả](HAR009_B2_TOKEN_BUDGET_RESULT.md), [receipt](evidence/context-budget-b2-20261111.json). Chế độ opt-in mới `history_policy.mode = "token-budget"`:

```bash
uv run --no-sync la chat --history-policy token-budget --history-budget-ratio 0.8
```

- Lịch sử vừa ngưỡng mềm (mặc định 80% ngân sách input) thì giữ hết, không còn mốc cố định 11 cặp.
- Khi thiếu chỗ:
  - giữ system, pin và câu hỏi hiện tại;
  - giữ cặp mới nhất còn vừa;
  - giữ dãy cặp gần nhất liền mạch trong tối đa nửa phần còn trống;
  - giữ các cặp cũ hơn có tin nhắn user mở đầu bằng marker (`Rule:`, `Decision:`, `Quy tắc:`, `Quyết định:`…), thử tối đa 8 cặp;
  - nới dãy gần nhất tới hết ngưỡng.
- Receipt ghi lý do từng cặp, không chứa nội dung. `--history-window` bị từ chối với chế độ này.
- `context_overflow` khi phần bắt buộc vượt giới hạn cứng; `strict` từ chối mọi việc bỏ lượt.

Benchmark `benchmarks/context_budget.py`: 12 hội thoại tổng hợp (8 case lượt dài chứa log khoảng 2.900 token/cặp, vượt giới hạn cứng; 4 case 40 lượt ngắn), 3 nhánh `legacy`/`budget`/`compact`, kiểm tra vị trí cửa sổ bằng tokenizer thật trước khi đóng băng. Chạy 2 lần × 36 lượt native, không retry (lần 2 trên code đã sửa lỗi thứ tự chọn lượt do review độc lập phát hiện; kết quả chấm giống hệt): đúng nghiêm ngặt `legacy` 3/12, `budget` 7/12, `compact` 11/12. `budget` thắng legacy ở 40 lượt ngắn (4/4 so với 0/4) và rule có marker (2/2 so với 0/2), nhưng trả lời giá trị cũ ở cả 2 case quyết định có marker bị đính chính sau không có marker (2 regression). Compact giữ đủ dữ kiện 12/12, 0 câu trả lời cũ. 20 test reduction/CLI và 19 test benchmark mới không gọi model. Đây là đo đạc trên dữ liệu tổng hợp, không đổi default/model/config.

### 13.13. HAR-009-C1: working state mang qua các cửa sổ

[ADR-190](ADR/190-opt-in-source-bound-working-state.md), [protocol](HAR009_C1_WORKING_STATE_PROTOCOL.md), [kết quả](HAR009_C1_WORKING_STATE_RESULT.md), [receipt](evidence/context-state-c1-20261111.json). Tùy chọn opt-in `history_policy.working_state: true` (với `sliding-window` hoặc `token-budget`):

```bash
uv run --no-sync la chat --history-policy token-budget --working-state
```

- **Mục state.** Mỗi dòng user mở đầu bằng marker (`Goal:`, `Rule:`, `Decision[db-region]:`, `Todo[cert]:`, `Done[cert]:`, `Correction:`, `Mục tiêu:`, `Quyết định:`…) thành một mục nguyên văn, có số cặp tuyệt đối và SHA-256 của cặp gốc.
- **Khóa và đóng việc.** Mục sau cùng khóa thay thế mục trước; `Done[key]` đóng `Todo[key]`.
- **Freshness.** Cặp mới hơn chia sẻ ít nhất 3 từ có nghĩa được ghi trong `newer_mentions`; với `token-budget`, cặp mới nhất như vậy của mỗi mục được giữ (`newer_related`, tối đa 8 lần thử, trong ngưỡng mềm). Với `sliding-window` chỉ ghi chú, không giữ thêm.
- **Giới hạn.** State là JSON không tin cậy, tính vào phần bắt buộc; quá 64 mục đang hiệu lực hoặc 32 KiB thì bỏ mục cũ (`note`/`correction` trước) và báo trong `dropped_active`. Dòng marker sai cú pháp được báo trong `skipped_lines`. Lời assistant không bao giờ thành mục.
- **CLI.** CLI mang state sang request sau và khi chạm 256 message thì bỏ 32 cặp cũ nhất thay vì dừng (khi có `--pin-turn` thì vẫn dừng như cũ).

Đo 2 lần × 54 lượt native, không retry (lần 2 trên code đã sửa sau review độc lập, cùng kế hoạch context):
- **Corpus B2:** `budget_state` đúng 9/12 rồi 7/12. Lời đính chính được giữ ở cả 4 lượt thuộc case cũ-mới; trả lời đúng 3/4, lượt còn lại nêu cả giá trị mới lẫn cũ nên bị tính là giá trị cũ. `budget` không state đúng 0/4; legacy vẫn giữ cặp 6 trong cửa sổ 11 cặp nên đúng 4/4.
- **Hội thoại 200 lượt bỏ cửa sổ 3 lần:** 5/5 case có marker ở cả 2 lần, so với 0/5 khi không có state; control không marker hỏng ở mọi nhánh.

Có 29 test working state và 10 test benchmark mới, không gọi model. Không đổi default, model hay config.

</details>
