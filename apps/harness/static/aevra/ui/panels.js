/** Workspace panels: context archives, memory, skills, runs/jobs and capabilities. */
import { API, ApiError, api, describe, post, remove, request } from "../api.js";
import { esc, renderMarkdown } from "../markdown.js";
import { HISTORY, PRESETS, STRATEGIES, isUuid, labelOf, settings, updateSettings } from "../settings.js";
import { confirmDialog, toast } from "./dom.js";

const TERMINAL = new Set(["succeeded", "failed", "cancelled", "interrupted"]);
export const PANELS = {
  context: ["Context", "Archive lịch sử bị rút gọn trong phiên local · lưu trong RAM và tự hết hạn"],
  memory: ["Memory", "Bộ nhớ ngắn hạn của phiên và chế độ lưu trữ"],
  skills: ["Skills", "Skill được owner review theo đúng hash trước khi cài"],
  runs: ["Runs / Jobs", "Task chỉ-đọc chạy nền và job tạo ảnh/video"],
  hooks: ["Hooks / Plugins", "Model, MCP, reasoning và các capability của máy chủ"],
};

let ticket = 0;
let refreshTimer = null;
let review = null;
const runStates = new Map();
let active = null;

function short(value) {
  return esc(String(value ?? "").slice(0, 8));
}

function bytes(value) {
  const number = Number(value) || 0;
  return number < 1024 ? `${number} B` : `${(number / 1024).toFixed(1)} KB`;
}

function duration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  return value < 60 ? `${value} giây` : `${Math.round(value / 60)} phút`;
}

function card(title, body) {
  return `<article class="card"><h2>${esc(title)}</h2>${body}</article>`;
}

function empty(text) {
  return `<p class="muted">${esc(text)}</p>`;
}

function badge(value) {
  return `<span class="badge" data-state="${esc(value)}">${esc(value)}</span>`;
}

function chips(values) {
  return (values || []).map((value) => `<span class="chip">${esc(value)}</span>`).join("");
}

function workspaceField(id) {
  return `<label class="field"><span>Workspace ID</span><input id="${id}" type="text" autocomplete="off" spellcheck="false" placeholder="UUID của workspace" value="${esc(settings.workspace)}"></label>`;
}

function readWorkspace(root, id) {
  const value = root.querySelector(`#${id}`).value.trim();
  if (!isUuid(value)) throw new ApiError("invalid_workspace_id", 0);
  updateSettings({ workspace: value });
  return value;
}

function archiveRow(archive) {
  return `<li class="row"><div class="row-main"><strong>${short(archive.id)}</strong><span class="muted">${bytes(archive.bytes)} · hết hạn sau ${duration(archive.expires_in_seconds)}</span></div><div class="actions"><button class="secondary" type="button" data-action="archive-view" data-id="${esc(archive.id)}">Xem</button><button class="danger" type="button" data-action="archive-delete" data-id="${esc(archive.id)}">Xóa</button></div><div class="detail" data-detail="${esc(archive.id)}" hidden></div></li>`;
}

function payloadHtml(payload) {
  const turns = Array.isArray(payload?.turns) ? payload.turns.flatMap((turn) => (Array.isArray(turn?.messages) ? turn.messages : [])) : null;
  const messages = turns || (Array.isArray(payload) ? payload : Array.isArray(payload?.messages) ? payload.messages : null);
  if (!messages) return `<pre class="raw">${esc(JSON.stringify(payload, null, 2))}</pre>`;
  return `<ol class="transcript">${messages.map((message) => `<li><span class="chip">${esc(message?.role ?? "?")}</span><div>${esc(typeof message?.content === "string" ? message.content : JSON.stringify(message?.content))}</div></li>`).join("")}</ol>`;
}

function strategyHtml() {
  const policy = settings.history ? labelOf(HISTORY, settings.history) : "";
  return `Context: <strong>${esc(labelOf(STRATEGIES, settings.strategy))}</strong> · Lịch sử: <strong>${esc(policy || "giữ toàn bộ")}</strong>`;
}

async function renderContext(root, current) {
  const archives = await api("/context/archives");
  if (!current()) return;
  const hint = settings.history === "extractive-compact"
    ? "Chưa có archive. Archive được tạo khi hội thoại gần chạm giới hạn context và phần cũ bị rút gọn."
    : "Chưa có archive. Chỉ chính sách lịch sử Extractive compact (trong Cài đặt) lưu phần hội thoại bị rút gọn tại đây.";
  root.innerHTML = card("Context archives", archives.length ? `<ul class="rows">${archives.map(archiveRow).join("")}</ul>` : empty(hint))
    + card("Chiến lược hiện tại", `<p data-strategy>${strategyHtml()}</p><p><button class="secondary" type="button" data-action="open-settings">Đổi trong Cài đặt</button></p>`);
}

async function renderMemory(root, current) {
  const [status, archives] = await Promise.all([api("/status"), api("/context/archives")]);
  if (!current()) return;
  root.innerHTML = card("Bộ nhớ phiên", `<ul class="facts"><li><span>Context archives</span><strong>${archives.length}</strong></li><li><span>Lưu lịch sử run</span><strong>${esc(status.persistence)}</strong></li><li><span>Lưu kết quả thô</span><strong>${status.raw_results_persisted ? "có" : "không"}</strong></li><li><span>Archive</span><strong>${esc(status.context_archive)}</strong></li><li><span>Summary phần bị cắt</span><strong>${esc(status.context_evicted_summary)}</strong></li></ul>`)
    + card("Summary cache", `<p class="muted">Tóm tắt các lượt bị rút gọn được cache trong RAM của tiến trình web.</p><p><button class="danger" type="button" data-action="purge-summaries">Xóa summary cache</button></p><p class="result" data-result="purge" role="status"></p>`)
    + card("Lịch sử hội thoại", empty("Hội thoại nằm trong IndexedDB của trình duyệt trên thiết bị này; xuất, nhập hoặc xóa trong Cài đặt › Dữ liệu."))
    + card("Memory dài hạn", empty("Memory bền vững (PostgreSQL) chưa có endpoint an toàn cho web; quản lý qua CLI/API. Giao diện không hiển thị nút giả."));
}

function skillRow(skill) {
  const key = `${skill.installation_id}|${skill.workspace_id}`;
  return `<li class="row"><div class="row-main"><strong>${esc(skill.id)}@${esc(skill.version)}</strong><span class="muted">workspace ${short(skill.workspace_id)} · sha256 ${short(skill.sha256)}</span><span>${chips(skill.permissions)}</span></div><div class="actions"><button class="secondary" type="button" data-action="skill-view" data-id="${esc(key)}">Chi tiết</button><button class="danger" type="button" data-action="skill-remove" data-id="${esc(key)}">Gỡ</button></div><div class="detail" data-detail="${esc(key)}" hidden></div></li>`;
}

function reviewHtml() {
  if (!review) return "";
  return `<div class="review"><h3>Kết quả review</h3><ul class="facts"><li><span>Quyền</span><span>${chips(review.permissions)}</span></li><li><span>SHA-256</span><code class="hash">${esc(review.sha256)}</code></li><li><span>Hết hạn</span><strong>${duration(review.expires_in_seconds)}</strong></li></ul><pre class="raw">${esc(review.manifest)}</pre><button class="primary" type="button" data-action="skill-install">Cài đặt đúng hash ${short(review.sha256)}</button></div>`;
}

async function renderSkills(root) {
  root.innerHTML = `<div data-host="skills"></div>`
    + card("Review và cài skill", `<form data-form="skill-review" class="stack">${workspaceField("skill-workspace")}<label class="field"><span>Manifest JSON</span><textarea id="skill-manifest" rows="8" spellcheck="false" placeholder='{"schema_version": 1, "id": "...", ...}'></textarea></label><div><button class="secondary" type="submit">Review manifest</button></div></form><div data-host="review">${reviewHtml()}</div><p class="muted">Cài đặt chỉ chấp nhận đúng hash vừa review; skill chỉ được quyền ghi trong manifest. Skill đã cài dùng được ngay ở nút + trong khung chat.</p>`);
  root.querySelector("[data-form='skill-review']").addEventListener("submit", async (event) => {
    event.preventDefault();
    const target = root.querySelector("[data-host='review']");
    try {
      const workspace = readWorkspace(root, "skill-workspace");
      const manifest = root.querySelector("#skill-manifest").value;
      if (!manifest.trim()) throw new ApiError("invalid_request", 0);
      review = { ...(await post("/skills/reviews", { workspace_id: workspace, manifest })), workspace_id: workspace };
      target.innerHTML = reviewHtml();
    } catch (error) {
      if (error.code !== "session_required") target.innerHTML = `<p class="error" role="alert">${esc(describe(error))}</p>`;
    }
  });
  await refreshSkills(root);
}

async function refreshSkills(root) {
  const skills = await api("/skills");
  const host = root.querySelector("[data-host='skills']");
  if (!host || active !== "skills") return;
  host.innerHTML = card("Skill đã cài", skills.length ? `<ul class="rows">${skills.map(skillRow).join("")}</ul>` : empty("Chưa có skill nào được cài trong phiên này."));
}

function runRow(run) {
  const running = !TERMINAL.has(run.state);
  const actions = `<button class="secondary" type="button" data-action="run-view" data-id="${esc(run.id)}">Chi tiết</button>${running ? `<button class="secondary" type="button" data-action="run-cancel" data-id="${esc(run.id)}">Hủy</button>` : `<button class="danger" type="button" data-action="run-remove" data-id="${esc(run.id)}">Xóa</button>`}`;
  return `<li class="row"><div class="row-main"><strong>Run ${short(run.id)}</strong>${badge(run.state)}<span class="muted">workspace ${short(run.workspace_id)} · ${(run.events || []).length} sự kiện</span></div><div class="actions">${actions}</div><div class="detail" data-detail="${esc(run.id)}" hidden></div></li>`;
}

function generationRow(job) {
  const id = esc(job.id);
  const running = !TERMINAL.has(job.state);
  const download = job.state !== "succeeded" ? "" : `<a class="button secondary" href="${API}/generations/${encodeURIComponent(job.id)}/artifact" download>Tải artifact</a>`;
  const actions = running ? `<button class="secondary" type="button" data-action="generation-cancel" data-id="${id}">Hủy</button>` : `<button class="danger" type="button" data-action="generation-remove" data-id="${id}">Xóa</button>`;
  return `<li class="row"><div class="row-main"><strong>${esc(job.kind || "generation")} ${short(job.id)}</strong>${badge(job.state)}</div><div class="actions">${download}${actions}</div></li>`;
}

function runDetail(run) {
  const answer = run.result?.choices?.[0]?.message?.content;
  const events = `<ol class="events">${(run.events || []).map((event) => `<li>${badge(event.state)}</li>`).join("")}</ol>`;
  const result = typeof answer === "string" ? `<div class="md">${renderMarkdown(answer)}</div>` : run.result_available === false ? empty("Chưa có kết quả.") : `<pre class="raw">${esc(JSON.stringify(run.result ?? null, null, 2))}</pre>`;
  return `${events}${result}`;
}

let runStatus = null;
async function renderRuns(root) {
  runStatus = await api("/status").catch(() => runStatus);
  root.innerHTML = card("Tạo run", `<form data-form="run" class="stack">${workspaceField("run-workspace")}<label class="field"><span>Yêu cầu</span><textarea id="run-task" rows="3" placeholder="Ví dụ: Giải thích cấu trúc module apps/harness"></textarea></label><label class="field"><span>Preset</span><select id="run-preset">${PRESETS.map(([value, label]) => `<option value="${esc(value)}"${value === settings.preset ? " selected" : ""}>${esc(label)}</option>`).join("")}</select></label><div><button class="primary" type="submit">Chạy</button></div><p class="result" data-result="run" role="status"></p></form>`) + `<div data-host="runs"></div>`;
  root.querySelector("[data-form='run']").addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = root.querySelector("[data-result='run']");
    try {
      const workspace = readWorkspace(root, "run-workspace");
      const task = root.querySelector("#run-task").value;
      if (!task.trim()) throw new ApiError("invalid_request", 0);
      await post("/runs", { workspace_id: workspace, task, preset: root.querySelector("#run-preset").value, context_strategy: settings.strategy });
      root.querySelector("#run-task").value = "";
      result.textContent = "Đã tạo run.";
      await refreshRuns(root);
    } catch (error) {
      if (error.code !== "session_required") result.textContent = describe(error);
    }
  });
  await refreshRuns(root);
}

function scheduleRuns(root, delay) {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => {
    if (active !== "runs") return;
    refreshRuns(root).catch((error) => {
      const host = root.querySelector("[data-host='runs']");
      if (error.code === "session_required" || !host || active !== "runs") return;
      host.querySelector(".stale")?.remove();
      host.insertAdjacentHTML("afterbegin", `<p class="error stale" role="alert">Không làm mới được danh sách: ${esc(describe(error))}. Đang thử lại…</p>`);
      scheduleRuns(root, 5000);
    });
  }, delay);
}

async function refreshRuns(root) {
  clearTimeout(refreshTimer);
  const [runs, generations] = await Promise.all([api("/runs"), api("/generations")]);
  const host = root.querySelector("[data-host='runs']");
  if (!host || active !== "runs") return;
  const open = new Map([...host.querySelectorAll(".detail:not([hidden])")].map((node) => [node.dataset.detail, node.innerHTML]));
  const generationNote = runStatus && !runStatus.image_generation && !runStatus.video_generation ? empty("Máy chủ chưa bật backend tạo ảnh/video.") : "";
  host.innerHTML = card("Runs", runs.length ? `<ul class="rows">${runs.map(runRow).join("")}</ul>` : empty("Chưa có run nào."))
    + card("Generations", (generations.length ? `<ul class="rows">${generations.map(generationRow).join("")}</ul>` : empty("Chưa có generation nào.")) + generationNote);
  const states = new Map(runs.map((run) => [run.id, run.state]));
  open.forEach((html, id) => {
    const node = host.querySelector(`[data-detail="${CSS.escape(id)}"]`);
    if (!node) return;
    node.hidden = false;
    node.innerHTML = html;
    if (states.has(id) && runStates.get(id) !== states.get(id)) {
      api(`/runs/${encodeURIComponent(id)}`).then((run) => { if (node.isConnected) node.innerHTML = runDetail(run); }).catch(() => {});
    }
  });
  runStates.clear();
  states.forEach((value, key) => runStates.set(key, value));
  if ([...runs, ...generations].some((item) => !TERMINAL.has(item.state))) scheduleRuns(root, 2000);
}

function capability(label, enabled, detail = "") {
  return `<li class="status-row"><span class="dot ${enabled ? "on" : "off"}" aria-hidden="true"></span><span>${esc(label)}</span><span class="muted">${esc(enabled ? "bật" : "tắt")}${detail ? ` · ${esc(detail)}` : ""}</span></li>`;
}

export async function loadModels() {
  try {
    return await api("/models");
  } catch (error) {
    if (error.code === "session_required") throw error;
    const fallback = await request("/v1/models").catch(() => null);
    const id = fallback?.data?.[0]?.id;
    return id ? { active: "core", fallback: true, models: [{ profile: "core", id, status: "approved", selectable: true, loaded: null, online: null, reason: "" }] } : { active: "core", fallback: true, models: [] };
  }
}

async function renderHooks(root, current) {
  const [status, models] = await Promise.all([api("/status"), loadModels()]);
  if (!current()) return;
  const rows = (models.models || []).map((model) => `<li class="status-row"><span class="dot ${model.online && model.loaded ? "on" : "off"}" aria-hidden="true"></span><code>${esc(model.id)}</code><span class="muted">${esc(model.profile)} · ${esc(model.status || "")}${model.loaded === true ? " · đang chạy" : model.online === false ? " · CORE không phản hồi" : ""}${model.selectable ? "" : " · đổi profile phải khởi động lại CORE dùng chung, cần owner duyệt"}</span></li>`).join("");
  root.innerHTML = card("Model", `<ul class="statuses">${rows || empty("Không đọc được danh sách model.")}</ul><p class="muted">Đổi model cần benchmark và owner duyệt; web không tải hay đổi model.</p>`)
    + card("Reasoning", `<p>Mặc định: <strong>${esc(labelOf(PRESETS, settings.preset))}</strong>. Mỗi hội thoại đổi được ngay ở khung chat.</p>`)
    + card("Capabilities", `<ul class="statuses">${capability("Workspace tools (chỉ đọc)", status.workspace_tools)}${capability("Tạo ảnh", status.image_generation)}${capability("Tạo video", status.video_generation)}${capability("Tự chọn tool", status.autonomous_tool_selection)}${capability("Resume bền vững", status.durable_resume)}</ul>`)
    + card("Hooks", `<ul class="statuses">${capability("Hooks", false, "cần approval flow")}</ul>`)
    + card("Plugins / MCP", `<ul class="statuses">${capability("MCP", false, "chưa có endpoint an toàn")}${capability("Plugins", false, "chưa có endpoint an toàn")}</ul><p class="muted">Không hiển thị nút bật/cài giả khi backend chưa có contract an toàn.</p>`);
}

const RENDERERS = { context: renderContext, memory: renderMemory, skills: renderSkills, runs: renderRuns, hooks: renderHooks };

/** Update the parts of an open panel that show settings, in place so focus and other content stay put. */
export function refreshSettingsViews(name, root) {
  if (name !== active) return;
  const strategy = root.querySelector("[data-strategy]");
  if (strategy) strategy.innerHTML = strategyHtml();
}

export function stopPanels() {
  active = null;
  ticket += 1;
  clearTimeout(refreshTimer);
}

export async function renderPanel(name, root) {
  active = name;
  const mine = ++ticket;
  const current = () => mine === ticket;
  clearTimeout(refreshTimer);
  root.innerHTML = `<div class="loading" role="status">Đang tải…</div>`;
  try {
    await RENDERERS[name](root, current);
  } catch (error) {
    if (error.code === "session_required" || !current()) return;
    root.innerHTML = card("Không tải được dữ liệu", `<p class="error" role="alert">${esc(describe(error))}</p><button class="secondary" type="button" data-action="reload">Thử lại</button>`);
  }
}

async function toggleDetail(root, id, loader) {
  const target = root.querySelector(`[data-detail="${CSS.escape(id)}"]`);
  if (!target) return;
  if (!target.hidden) {
    target.hidden = true;
    return;
  }
  target.hidden = false;
  target.innerHTML = `<p class="muted">Đang tải…</p>`;
  try {
    target.innerHTML = await loader();
  } catch (error) {
    if (error.code !== "session_required") target.innerHTML = `<p class="error" role="alert">${esc(describe(error))}</p>`;
  }
}

async function act(promise, refresh) {
  try {
    await promise;
    await refresh();
  } catch (error) {
    if (error.code !== "session_required") toast(describe(error), "error");
  }
}

async function confirmThen(title, message, label, run) {
  if (await confirmDialog({ title, message, confirmLabel: label, danger: true })) return run();
  return undefined;
}

/** Handle a click on a [data-action] button inside a panel. */
export async function handlePanelAction(button, root, { openSettings }) {
  const id = button.dataset.id;
  const [installation, workspace] = (id || "").split("|");
  switch (button.dataset.action) {
    case "reload": return renderPanel(active, root);
    case "open-settings": return openSettings();
    case "archive-view":
      return toggleDetail(root, id, async () => payloadHtml((await api(`/context/archives/${encodeURIComponent(id)}`)).payload));
    case "archive-delete":
      return confirmThen("Xóa archive", "Xóa archive này khỏi bộ nhớ phiên? Không thể hoàn tác.", "Xóa", () => act(remove(`/context/archives/${encodeURIComponent(id)}`), () => renderPanel("context", root)));
    case "purge-summaries":
      return confirmThen("Xóa summary cache", "Xóa toàn bộ summary cache của phiên? Không thể hoàn tác.", "Xóa", async () => {
        const target = root.querySelector("[data-result='purge']");
        try {
          const result = await remove("/context/summaries");
          target.textContent = `Đã xóa ${result?.purged ?? 0} mục.`;
        } catch (error) {
          if (error.code !== "session_required") target.textContent = describe(error);
        }
      });
    case "skill-view":
      return toggleDetail(root, id, async () => {
        const skill = await api(`/skills/installations/${encodeURIComponent(installation)}?workspace_id=${encodeURIComponent(workspace)}`);
        return `<p>${esc(skill.description)}</p><ul class="facts"><li><span>Quyền</span><span>${chips(skill.permissions)}</span></li><li><span>SHA-256</span><code class="hash">${esc(skill.sha256)}</code></li></ul><pre class="raw">${esc(skill.instructions)}</pre>`;
      });
    case "skill-remove":
      return confirmThen("Gỡ skill", "Gỡ skill này khỏi workspace? Các run và chat sau sẽ không dùng được skill.", "Gỡ", () => act(remove(`/skills/installations/${encodeURIComponent(installation)}?workspace_id=${encodeURIComponent(workspace)}`), () => refreshSkills(root)));
    case "skill-install": {
      if (!review) return undefined;
      const target = root.querySelector("[data-host='review']");
      try {
        await post("/skills/installations", { workspace_id: review.workspace_id, review_id: review.review_id, sha256: review.sha256 });
        review = null;
        target.innerHTML = `<p class="result" role="status">Đã cài skill.</p>`;
        await refreshSkills(root);
      } catch (error) {
        if (error.code !== "session_required") target.insertAdjacentHTML("beforeend", `<p class="error" role="alert">${esc(describe(error))}</p>`);
      }
      return undefined;
    }
    case "run-view":
      return toggleDetail(root, id, async () => runDetail(await api(`/runs/${encodeURIComponent(id)}`)));
    case "run-cancel":
      return act(post(`/runs/${encodeURIComponent(id)}/cancel`), () => refreshRuns(root));
    case "run-remove":
      return confirmThen("Xóa run", "Xóa run và kết quả của nó? Không thể hoàn tác.", "Xóa", () => act(remove(`/runs/${encodeURIComponent(id)}`), () => refreshRuns(root)));
    case "generation-cancel":
      return act(post(`/generations/${encodeURIComponent(id)}/cancel`), () => refreshRuns(root));
    case "generation-remove":
      return confirmThen("Xóa generation", "Xóa generation và artifact? Không thể hoàn tác.", "Xóa", () => act(remove(`/generations/${encodeURIComponent(id)}`), () => refreshRuns(root)));
    default:
      return undefined;
  }
}
