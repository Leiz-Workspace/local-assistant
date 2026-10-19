# LOCAL ASSISTANT — TECHNICAL DESIGN SPECIFICATION
## PostgreSQL Database Schema & Conversation Manager

**Document ID:** LA-TDS-015  
**Version:** 1.0 — Architecture Baseline  
**Date:** 2026-10-16  
**Status:** APPROVED FOR IMPLEMENTATION — Thiết kế đã chốt, chưa nghiệm thu triển khai  
**Project Root:** `~/Workspace/Server/ai`

> **Implementation checkpoint 2026-10-17:** This document preserves the original design baseline. T01–T04 have historical focused PASS evidence; T05 passed localhost acceptance: 4/4 real PostgreSQL integrations including CORE, full suite 94/94 and actual API process restart/history/replay. T06 passed authenticated-localhost acceptance on 2026-10-18 (151/151 tests): owner UUID stored in existing JSONB metadata, bearer principal filters at service/repository/manager locks, periodic pool metrics, protected restore of rows/owners/ACLs and shared DB restart. Unowned legacy records remain quarantined; no DDL or silent backfill. See ADR-018; older design status below is historical. The current roadmap is `docs/LOCAL_ASSISTANT_MASTER_ROADMAP.md`. ADR-016 specifies POST archive (superseding the PATCH row below), PATCH title/preset, environment credential injection and the direct localhost access boundary. Older “chưa triển khai” statements below describe the original baseline, not current progress.

---

## 1. Mục tiêu

Triển khai hệ thống hội thoại có khả năng lưu trữ bền vững (Persistent Conversation), quản lý lịch sử nhiều lượt (Multi-turn Conversation) và khôi phục dữ liệu sau khi FastAPI khởi động lại.

Các mục tiêu cụ thể:

1. Lưu trữ và quản lý nhiều cuộc hội thoại độc lập.
2. Bảo đảm thứ tự và tính toàn vẹn của các tin nhắn.
3. Hỗ trợ CORE và Unrestricted thông qua model profile hiện tại.
4. Tích hợp năm Runtime Presets: Auto, Fast, Balanced, Deep và Unlimited.
5. Quản lý Context Window 32K tokens.
6. Hỗ trợ Idempotency để chống xử lý lặp request.
7. Theo dõi inference runs, token usage, lỗi và trạng thái.
8. Khôi phục hội thoại sau khi restart API hoặc PostgreSQL.
9. Xây dựng nền tảng mở rộng cho Agent, MCP, Tool Calling và Memory.

**Nguyên tắc:** PostgreSQL là nguồn dữ liệu chính; model và inference engine không trực tiếp quản lý database.

---

## 2. Quyết định Technology Stack

| Thành phần | Công nghệ | Trạng thái | Vai trò |
|---|---|---|---|
| Application Framework | FastAPI | Đã có | REST API |
| Inference Engine | llama.cpp CUDA | Đã có | Model inference |
| Primary Database | PostgreSQL | Chốt | Persistent storage |
| Database Driver | psycopg 3 | Chốt | PostgreSQL connectivity |
| Connection Pool | psycopg_pool | Chốt | Connection management |
| Schema Migration | Alembic | Chốt | Versioned migrations |
| Cache / Coordination | Redis | Dự kiến | Cache, distributed coordination |
| Vector Database | Qdrant | Giai đoạn sau | Semantic memory |
| Object Storage | MinIO / Local FS | Giai đoạn sau | Binary files |
| Document Database | MongoDB | Không triển khai V1 | Chưa cần |

### 2.1. Vì sao PostgreSQL?

PostgreSQL hỗ trợ:

- ACID transactions.
- Foreign keys và relational integrity.
- Row-level locking.
- Unique constraints cho idempotency.
- JSONB cho metadata linh hoạt.
- Full-text search.
- Concurrent access.
- Migrations và indexing.

Khả năng mở rộng phù hợp với Conversation Engine hiện tại và Agent Engine trong tương lai.

### 2.2. Vai trò của Redis

Redis không phải nơi lưu conversation chính thức.

Các use case dự kiến:

- Cache conversation metadata.
- Cache token counts hoặc derived state có thể tính lại.
- Rate limiting.
- Distributed locks hoặc coordination khi có nhiều workers.
- Task queues, nếu kiến trúc job execution yêu cầu.

**Ngày 15 không phụ thuộc Redis.** Chỉ tích hợp khi có workload và tiêu chí kiểm thử cụ thể.

### 2.3. Vì sao chưa dùng MongoDB?

Conversation, message và inference run có quan hệ rõ ràng và yêu cầu transaction nhất quán.

PostgreSQL JSONB cũng đủ đáp ứng metadata bán cấu trúc.

MongoDB chỉ được xem xét khi xuất hiện nhu cầu document-centric có lợi ích rõ ràng, không bổ sung chỉ để tăng số lượng công nghệ.

---

## 3. System Architecture

```text
Client / CLI
    |
    v
FastAPI
    |
    +-- Existing Stateless Chat API
    |       |
    |       +-- LlamaGateway
    |
    +-- Conversation API
            |
            v
     Conversation Manager
            |
            +-- Conversation Repository
            |       |
            |       v
            |   PostgreSQL
            |
            +-- Context Builder
            |
            +-- Runtime Preset / Auto Router
            |       |
            |       v
            +-- LlamaGateway
                    |
                    v
               llama.cpp CUDA
```

### Architecture Rules

- FastAPI chịu trách nhiệm HTTP validation.
- Conversation Manager điều phối nghiệp vụ.
- Repository chịu trách nhiệm truy cập dữ liệu và transaction.
- Context Builder chọn nội dung cần đưa vào model.
- LlamaGateway giữ nguyên trách nhiệm inference.
- Database không chứa logic inference.
- Không giữ database transaction mở trong thời gian LLM sinh câu trả lời.

---

## 4. PostgreSQL Schema V001

Database logic được tổ chức trong PostgreSQL schema `assistant`.

### 4.1. `assistant.conversations`

Lưu metadata của phiên hội thoại.

| Field | Kiểu | Quy định |
|---|---|---|
| id | UUID | Primary key |
| title | VARCHAR(200) | NOT NULL |
| profile | VARCHAR(32) | CORE / Unrestricted |
| preset_default | VARCHAR(32) | Default Balanced |
| status | VARCHAR(20) | active / archived |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |
| deleted_at | TIMESTAMPTZ | Nullable |
| metadata | JSONB | Default `{}` |

### 4.2. `assistant.messages`

Lưu transcript theo thứ tự.

| Field | Kiểu | Quy định |
|---|---|---|
| id | UUID | Primary key |
| conversation_id | UUID | Foreign key |
| sequence | BIGINT | Thứ tự trong conversation |
| role | VARCHAR(20) | system / user / assistant |
| content | TEXT | NOT NULL |
| request_key | VARCHAR(128) | Nullable |
| created_at | TIMESTAMPTZ | NOT NULL |
| metadata | JSONB | Default `{}` |

Constraints:

- Unique `(conversation_id, sequence)`.
- Unique `(conversation_id, request_key)` với request_key không NULL.
- Foreign key tới `conversations`.
- Không dùng client timestamp để quyết định thứ tự.

### 4.3. `assistant.inference_runs`

Theo dõi từng lần inference.

| Field | Kiểu | Quy định |
|---|---|---|
| id | UUID | Primary key |
| conversation_id | UUID | Foreign key |
| user_message_id | UUID | Foreign key |
| assistant_message_id | UUID | Nullable |
| preset_requested | VARCHAR(32) | NOT NULL |
| preset_selected | VARCHAR(32) | Nullable |
| model_id | TEXT | Nullable |
| status | VARCHAR(20) | pending / completed / failed / interrupted |
| input_tokens | INTEGER | Nullable |
| completion_tokens | INTEGER | Nullable |
| finish_reason | TEXT | Nullable |
| latency_ms | INTEGER | Nullable |
| error_code | TEXT | Nullable |
| created_at | TIMESTAMPTZ | NOT NULL |
| completed_at | TIMESTAMPTZ | Nullable |
| metadata | JSONB | Default `{}` |

Index đề xuất:

- Conversations theo `updated_at`, loại các record soft-deleted.
- Messages theo `(conversation_id, sequence)`.
- Inference runs theo `(conversation_id, created_at)`.
- Unique partial index để chỉ có tối đa một `pending` inference run trên mỗi conversation.

**Lưu ý:** V001 phục vụ chat text. Schema cần migration tiếp khi tool calls, multimodal messages hoặc nhiều agent execution được đưa vào vận hành.

---

## 5. Transaction & Consistency Design

### 5.1. Tạo conversation

1. Validate profile và preset.
2. Generate UUID.
3. INSERT conversation.
4. COMMIT.
5. Trả về conversation ID.

### 5.2. Gửi một tin nhắn

**Transaction A — Reserve**

1. Khóa conversation row bằng `SELECT ... FOR UPDATE`.
2. Kiểm tra conversation còn active.
3. Kiểm tra request_key đã tồn tại hay chưa.
4. Kiểm tra chưa có inference run pending.
5. Tính sequence tiếp theo.
6. INSERT user message.
7. INSERT inference run với status `pending`.
8. COMMIT.

**Inference — Không giữ transaction**

9. Đọc lịch sử.
10. Xây dựng context.
11. Resolve runtime preset.
12. Gọi LlamaGateway.

**Transaction B — Complete**

13. Kiểm tra inference run vẫn hợp lệ và pending.
14. INSERT assistant message.
15. UPDATE inference run thành `completed`, ghi metadata và usage.
16. UPDATE conversation timestamp.
17. COMMIT.

Hai thao tác lưu assistant message và đánh dấu completed phải nằm trong cùng transaction.

### 5.3. Inference thất bại

- Giữ lại user message.
- Đánh dấu inference run là `failed`.
- Không tạo assistant response giả.
- Không lưu incomplete response như completed.
- Có thể bổ sung explicit retry API sau này.

### 5.4. Idempotency

`request_key` được scope trong một conversation.

Cùng key + cùng request parameters có ý nghĩa nghiệp vụ:

- Nếu completed: trả lại kết quả đã lưu.
- Nếu pending: trả 409 hoặc trạng thái đang xử lý.
- Nếu failed/interrupted: trả trạng thái hiện tại; không tự suy diễn request có thể chạy lại an toàn.
- Nếu key được dùng với nội dung hoặc tham số khác: trả 409.

V1 phải thống nhất fingerprint cho nội dung, preset, temperature và các generation parameters ảnh hưởng đến kết quả.

### 5.5. Crash Recovery

Khi service khởi động lại:

- Các completed runs giữ nguyên.
- Các pending runs từ tiến trình đã chết cần được đánh dấu interrupted sau khi xác minh quyền sở hữu hoặc lease hết hạn.
- Không tự động đánh dấu mọi pending run là interrupted nếu vẫn có worker khác đang hoạt động.

V1 triển khai single API worker trước; thiết kế lease và heartbeat sẽ được bổ sung trước khi mở rộng thành nhiều worker.

---

## 6. Conversation Manager

### Responsibilities

Conversation Manager chịu trách nhiệm:

- Create conversation.
- List conversations.
- Retrieve conversation.
- Retrieve message history.
- Send message.
- Archive conversation.
- Soft delete conversation.
- Resolve profile và preset.
- Invoke Context Builder.
- Invoke LlamaGateway.
- Persist completed inference.
- Handle inference failures.

### Design Principle

Conversation Manager không tự viết SQL và không implement lại model inference.

Repository là interface dữ liệu; LlamaGateway là interface inference.

Dependency Injection phải cho phép mock Repository/Gateway khi unit testing.

---

## 7. Context Window Management

Context capacity hiện tại là 32.768 tokens.

### Context Building

1. Đọc lịch sử conversation.
2. Xác định system instructions.
3. Chọn các lượt hội thoại theo thứ tự.
4. Đếm token qua tokenizer/template của llama.cpp.
5. Áp dụng Runtime Preset Token Budget Manager.
6. Nếu thiếu context, loại những lượt cũ hoàn chỉnh khỏi inference input.
7. Không xóa lịch sử gốc trong PostgreSQL.

Không loại user message hiện tại để giảm context.

Không chia tách tùy tiện một cặp user/assistant thuộc lượt hội thoại trước.

### Giới hạn V1

- Chưa có semantic summarization.
- Chưa có vector memory retrieval.
- Chưa có automatic compaction.
- Chưa lưu reasoning trace dài hạn.

Đó là các phần mở rộng cho những ngày tiếp theo.

---

## 8. REST API Contract

Giữ nguyên endpoint hiện tại:

`POST /api/v1/chat/completions`

Bổ sung:

| Method | Endpoint | Mục đích |
|---|---|---|
| POST | `/api/v1/conversations` | Tạo conversation |
| GET | `/api/v1/conversations` | Danh sách |
| GET | `/api/v1/conversations/{id}` | Chi tiết |
| GET | `/api/v1/conversations/{id}/messages` | Lịch sử |
| POST | `/api/v1/conversations/{id}/messages` | Gửi tin nhắn |
| PATCH | `/api/v1/conversations/{id}/archive` | Archive |
| DELETE | `/api/v1/conversations/{id}` | Soft delete |

Các endpoint phải dùng response schema rõ ràng, phân trang danh sách và mã lỗi nhất quán.

V1 chưa triển khai multi-user authentication. API chỉ được bind loopback hoặc mạng quản trị đáng tin cậy; không công khai trực tiếp PostgreSQL hay Conversation API ra Internet.

---

## 9. Deployment & Security

- PostgreSQL được chạy dưới dạng Docker service, có named volume để lưu trữ bền vững.
- Database không publish cổng công khai.
- Nếu FastAPI chạy trực tiếp trên Ubuntu host, chỉ bind PostgreSQL vào `127.0.0.1` và một cổng nội bộ được kiểm tra trước khi triển khai.
- Dùng dedicated PostgreSQL database và role riêng cho Local Assistant.
- Không dùng PostgreSQL superuser cho ứng dụng.
- Password lưu qua environment/secret, không commit vào Git.
- Database connections có timeout và connection pool giới hạn.
- Bật healthcheck, logging và backup.
- Không log nội dung hội thoại nhạy cảm theo mặc định.
- Cấu hình backup phải bao gồm kiểm thử restore, không chỉ tạo file dump.

Không thay đổi các container hoặc database của ứng dụng home server khác.

---

## 10. Implementation Plan

### D15-T01 — PostgreSQL Infrastructure

- Docker Compose service hoặc stack riêng.
- Database, role và permission.
- Persistent volume.
- Healthcheck.
- Local-only access.
- Kiểm tra restart và volume persistence.

### D15-T02 — Migration V001

- Tạo PostgreSQL schema.
- Tạo ba bảng chính.
- Constraints, indexes và foreign keys.
- Alembic migration và rollback policy.

### D15-T03 — Conversation Repository

- CRUD.
- Transaction management.
- Sequence allocation.
- Idempotency.
- Soft delete.
- Inference run lifecycle.

### D15-T04 — Conversation Manager

- Multi-turn orchestration.
- Gateway integration.
- Runtime preset integration.
- Failure handling.
- Context trimming.

### D15-T05 — Conversation REST API

- Request/response schemas.
- Router.
- HTTP status codes.
- Validation.
- Dependency injection.

### D15-T06 — Tests & Acceptance

- Unit tests.
- Integration tests với PostgreSQL thật.
- Concurrent request tests.
- Restart persistence.
- Context overflow.
- Existing runtime regression tests.

---

## 11. Acceptance Criteria

Ngày 15 chỉ được đánh dấu DONE khi:

- PostgreSQL khởi động thành công.
- Migration V001 áp dụng thành công.
- Có thể tạo conversation và lưu tin nhắn.
- Multi-turn sử dụng đúng lịch sử trước đó.
- Restart FastAPI không mất conversation.
- Restart PostgreSQL container không mất dữ liệu.
- Request cùng idempotency key không sinh trùng assistant message.
- Đồng thời hai request không phá thứ tự message.
- Inference lỗi không tạo completed run giả.
- `finish_reason="length"` không được lưu thành câu trả lời hoàn chỉnh.
- Context vượt giới hạn được xử lý có kiểm soát.
- Không ghi `reasoning_content` theo mặc định.
- Endpoint chat cũ vẫn hoạt động.
- Các regression tests hiện hữu PASS.

---

## 12. Out of Scope

Không triển khai trong Ngày 15:

- Redis cache service.
- MongoDB.
- Qdrant.
- RAG.
- Long-term semantic memory.
- MinIO integration.
- Distributed Agent Queue.
- MCP execution.
- Multi-worker coordination.
- UI riêng.
- Automatic summarization.

---

## 13. Final Architecture Decision

**ADR-015 — Persistent Storage Architecture**

**Decision:** PostgreSQL là Primary Database cho Local Assistant.

**Supporting technologies:** Redis, Qdrant và MinIO được bổ sung theo từng giai đoạn, không phải điều kiện bắt buộc của Conversation Engine V1.

**Rejected for current implementation:** SQLite làm primary database và MongoDB làm core document database.

**Rationale:** PostgreSQL đáp ứng transaction consistency, relational integrity, JSONB và khả năng mở rộng cho Agent Engine.

**Implementation status:** Chưa triển khai PostgreSQL Schema V001 và Conversation Manager mới.

**Supersedes:** Tài liệu Day 15 SQLite trước đó. Source SQLite đã cung cấp không còn là baseline triển khai được chốt.

**Next Action:** Bắt đầu D15-T01 — PostgreSQL Infrastructure, sau đó Migration V001.


## D29 memory contract checkpoint — 2026-10-19

**Purpose:** Link the separately consented memory design without changing accepted conversation-history ownership or persistence.

[MEMORY_DESIGN.md](MEMORY_DESIGN.md) and ADR-044 define four classes/consent/provenance/retention. D29 design/contract63 cases PASS; proposed JSON/SQL schemas are not an applied migration or runtime feature. Conversation history does not grant memory consent; existing JSONB owner locking and quarantine of unowned history remain unchanged. D30 needs actual source authorization, default-off APIs/extraction and reviewed backup/migration/grants; D31 privacy/export/deletion remains later.
