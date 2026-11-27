/** Same-origin API client: session recovery, error codes and the chat stream reader. */
export const API = "/api/v1/harness";

export const ERRORS = {
  inference_unavailable: "CORE chưa phản hồi. Kiểm tra model CORE đã chạy và web kết nối được tới nó.",
  incomplete_completion: "Câu trả lời bị dừng trước khi hoàn tất.",
  stream_limit: "Câu trả lời vượt giới hạn kích thước stream.",
  special_literals_stale: "Model đang chạy không khớp cấu hình đã duyệt nên Aevra từ chối inference.",
  network_unavailable: "Không kết nối được tới Aevra web.",
  session_required: "Phiên local đã hết hạn.",
  request_limit: "Hội thoại quá dài. Hãy bắt đầu chat mới.",
  invalid_request: "Dữ liệu gửi lên không hợp lệ.",
  invalid_context_request: "Chính sách lịch sử không áp dụng được cho hội thoại này.",
  empty_answer: "Model trả về câu trả lời rỗng.",
  context_overflow: "Tin nhắn hoặc hội thoại vượt giới hạn context của model. Hãy rút ngắn hoặc bắt đầu chat mới.",
  complete_history_pairs_required: "Lịch sử gửi lên không đủ cặp hỏi/đáp. Hãy bắt đầu chat mới.",
  context_archive_capacity: "Bộ nhớ archive đã đầy (16 archive). Xóa bớt archive trong Context hoặc đổi chính sách lịch sử.",
  context_archive_entry_too_large: "Phần hội thoại bị rút gọn quá lớn để lưu archive (128 KB). Hãy bắt đầu chat mới hoặc dùng Sliding window.",
  run_capacity: "Đã đạt giới hạn số run đồng thời.",
  run_active: "Run đang chạy; hãy hủy trước khi xóa.",
  run_not_active: "Run đã kết thúc.",
  run_not_found: "Không tìm thấy run.",
  workspace_unavailable: "Máy chủ này chưa cấu hình workspace.",
  review_required: "Bản review đã hết hạn; hãy review lại.",
  skill_operation_denied: "Thao tác skill bị từ chối (hash, quyền hoặc review không hợp lệ).",
  skill_not_installed: "Skill không còn được cài.",
  context_artifact_not_found: "Archive đã hết hạn hoặc không tồn tại.",
  generation_capability_unavailable: "Máy chủ chưa bật backend tạo ảnh/video.",
  artifact_not_ready: "Artifact chưa sẵn sàng.",
  history_unavailable: "Lịch sử run tạm thời không khả dụng.",
  harness_unavailable: "Harness chưa sẵn sàng.",
  ui_csrf_required: "Yêu cầu bị chặn vì không đến từ giao diện Aevra.",
  local_session_required: "Chỉ chấp nhận truy cập trực tiếp từ máy local.",
  invalid_workspace_id: "Workspace ID phải là UUID hợp lệ.",
  auto_session_disabled: "Máy chủ đang tắt tự tạo phiên.",
  auth_unavailable: "Máy chủ không đọc được file principals (kiểm tra AEVRA_PRINCIPALS_FILE, quyền 0600 và uid của container).",
  single_local_principal_required: "Tự tạo phiên chỉ hỗ trợ file principals có đúng một principal.",
  inference_busy: "CORE đang bận trả lời yêu cầu khác. Hãy thử lại sau ít phút.",
  stream_timeout: "Câu trả lời quá thời gian cho phép và đã bị dừng.",
  attachment_too_large: "Tệp đính kèm vượt giới hạn (64 KB mỗi tệp, 192 KB tổng).",
  invalid_upstream_event: "CORE trả về dữ liệu không hợp lệ.",
  message_too_large: "Tin nhắn quá lớn cho một lượt.",
  strict_context_would_trim: "Chiến lược context Strict không cho cắt lịch sử; hãy đổi chiến lược hoặc bắt đầu chat mới.",
};

export class ApiError extends Error {
  constructor(code, status) {
    super(code);
    this.code = code;
    this.status = status;
  }
}

export function describe(error) {
  const code = error?.code || "request_failed";
  return `${ERRORS[code] || "Yêu cầu thất bại."} (${code})`;
}

const SIGNED_OUT = "aevra-signed-out";
function storedSignedOut() {
  try { return localStorage.getItem(SIGNED_OUT) === "1"; } catch { return false; }
}

/** An explicit logout survives reloads and other tabs until "Kết nối lại". */
export const session = {
  signedOut: storedSignedOut(),
  onRequired: () => {},
  onConnected: () => {},
  setSignedOut(value) {
    this.signedOut = value;
    try {
      if (value) localStorage.setItem(SIGNED_OUT, "1");
      else localStorage.removeItem(SIGNED_OUT);
    } catch { /* storage may be unavailable */ }
  },
};
window.addEventListener("storage", (event) => {
  if (event.key === SIGNED_OUT) session.signedOut = event.newValue === "1";
});

let bootstrapping = null;
export function bootstrapSession() {
  bootstrapping ??= fetch("/ui/session/bootstrap", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Harness-UI": "1" },
    body: "{}",
  }).then(async (response) => {
    if (response.ok) {
      session.onConnected();
      return { ok: true };
    }
    const body = await response.json().catch(() => ({}));
    return { ok: false, code: body?.detail?.code || `http_${response.status}` };
  }).catch(() => ({ ok: false, code: "network_unavailable" })).finally(() => { bootstrapping = null; });
  return bootstrapping;
}

export function sessionMessage(code) {
  if (session.signedOut) return "Đã đăng xuất phiên trên thiết bị này.";
  return ERRORS[code] || "Phiên local đã hết hạn hoặc chưa được tạo.";
}

async function errorFrom(response) {
  const body = await response.json().catch(() => ({}));
  const detail = body?.detail;
  const code = typeof detail === "string" ? detail : detail?.code || (Array.isArray(detail) ? "invalid_request" : body?.error?.code || "request_failed");
  return new ApiError(code, response.status);
}

async function send(url, options, retry) {
  const headers = { "X-Harness-UI": "1" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(url, { ...options, credentials: "same-origin", headers });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError("network_unavailable", 0);
  }
  if (response.status === 401) {
    // After an explicit logout the session is only re-created by "Kết nối lại".
    const bootstrap = retry && !session.signedOut ? await bootstrapSession() : { ok: false, code: "" };
    if (bootstrap.ok) return send(url, options, false);
    session.onRequired(sessionMessage(bootstrap.code));
    throw new ApiError("session_required", 401);
  }
  if (!response.ok) throw await errorFrom(response);
  return response;
}

export async function request(url, options = {}) {
  const response = await send(url, options, true);
  return response.status === 204 ? null : response.json();
}

export const api = (path, options) => request(API + path, options);
export const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body ?? {}) });
export const remove = (path) => api(path, { method: "DELETE" });

function parseEvent(raw) {
  let event = "message";
  const data = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  return { event, data: data.join("\n") };
}

/** Stream one chat completion; resolves on [DONE], rejects with ApiError, AbortError on stop. */
export async function streamChat(body, { signal, onContext, onDelta, onUsage }) {
  const response = await send(`${API}/chat/stream`, { method: "POST", body: JSON.stringify(body), signal }, true);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finish = null;
  for (;;) {
    let chunk;
    try {
      chunk = await reader.read();
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      throw new ApiError("network_unavailable", 0);
    }
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const { event, data } = parseEvent(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
      if (!data) continue;
      if (event === "error") {
        let code = "inference_unavailable";
        try { code = JSON.parse(data)?.code || code; } catch { /* keep default */ }
        throw new ApiError(code, 200);
      }
      if (data === "[DONE]") return { finish };
      let payload;
      try { payload = JSON.parse(data); } catch { continue; }
      if (event === "context") { onContext?.(payload); continue; }
      if (payload?.error) throw new ApiError(payload.error.code || "inference_unavailable", 200);
      if (payload?.usage) onUsage?.(payload.usage);
      const choice = payload?.choices?.[0];
      if (choice?.delta) onDelta?.({ content: choice.delta.content || "", reasoning: choice.delta.reasoning_content || "" });
      if (choice?.finish_reason) finish = choice.finish_reason;
    }
  }
  throw new ApiError("incomplete_completion", 200);
}
