const API = "/api/v1/harness";
const state = { messages: [], panel: "chat", status: null, prefs: { preset: "fast", strategy: "evidence-first" } };
const $ = (selector) => document.querySelector(selector);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
}

async function api(path, options = {}) {
  const response = await fetch(API + path, { credentials: "same-origin", ...options, headers: { "Content-Type": "application/json", "X-Harness-UI": "1", ...(options.headers || {}) } });
  if (response.status === 401) { window.location.assign("/pair/"); throw new Error("session"); }
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail?.code || "request_failed");
  return response.status === 204 ? null : response.json();
}

function setHeader(title, subtitle = "Aevra · local assistant") {
  $("#title").textContent = title;
  $("#subtitle").textContent = subtitle;
}

function card(title, body, className = "") { return `<article class="card ${className}"><h2>${esc(title)}</h2>${body}</article>`; }
function empty(text) { return `<p class="muted">${esc(text)}</p>`; }
function list(items, label) {
  if (!items?.length) return empty(`Chưa có ${label}.`);
  return `<ul class="list">${items.map((item) => `<li>${esc(item.name || item.id || item.identifier || item.run_id || item.state || "Item")}</li>`).join("")}</ul>`;
}

function renderChat() {
  return `<div class="chat"><div class="messages">${state.messages.length ? state.messages.map((m) => `<div class="msg ${m.role}">${esc(m.content)}</div>`).join("") : `<div class="empty-chat"><img src="/aevra/brand/logo.svg" alt=""><h2>Aevra</h2><p>Local assistant · dữ liệu giữ trên máy của bạn.</p></div>`}</div><form class="composer"><textarea id="prompt" placeholder="Nhắn với Aevra…" rows="2"></textarea><button class="primary" type="submit">Gửi</button></form></div>`;
}

async function renderPanel(panel) {
  state.panel = panel;
  document.querySelectorAll(".nav").forEach((button) => button.classList.toggle("active", button.dataset.panel === panel));
  const content = $("#content");
  content.innerHTML = `<div class="loading">Đang tải…</div>`;
  if (panel === "chat") { setHeader("New chat"); content.innerHTML = renderChat(); $(".composer").onsubmit = send; return; }
  try {
    if (panel === "context" || panel === "memory") {
      setHeader(panel === "memory" ? "Memory" : "Context", "Archives và trạng thái context của phiên local");
      const archives = await api("/context/archives");
      content.innerHTML = card(panel === "memory" ? "Memory / Archives" : "Context archives", list(archives, "archive")) + card("Privacy", empty("Process-local owner memory · không đồng bộ lên cloud."));
    } else if (panel === "skills") {
      setHeader("Skills", "Skill installations được owner review");
      content.innerHTML = card("Installed skills", list(await api("/skills"), "skill")) + card("Safety", empty("Install/remove cần review và exact hash."));
    } else if (panel === "runs") {
      setHeader("Runs / Jobs", "Readonly task và generation status");
      const [runs, generations] = await Promise.all([api("/runs"), api("/generations")]);
      content.innerHTML = card("Runs", list(runs, "run")) + card("Generations", list(generations, "generation"));
    } else if (panel === "personal") {
      setHeader("Personal", "Thiết lập local của phiên này");
      content.innerHTML = card("Preferences", `<label>Preset<select id="personal-preset"><option>fast</option><option>balanced</option><option>deep</option><option>auto</option><option>unlimited</option></select></label><label>Context strategy<select id="personal-strategy"><option value="evidence-first">Evidence first</option><option value="recent-turns">Recent turns</option><option value="strict">Strict</option></select></label><p class="muted">Preferences chỉ lưu trên thiết bị; credential không lưu trong UI.</p>`);
      $("#personal-preset").value = state.prefs.preset; $("#personal-strategy").value = state.prefs.strategy;
      [$("#personal-preset"), $("#personal-strategy")].forEach((element) => element.onchange = () => { state.prefs.preset = $("#personal-preset").value; state.prefs.strategy = $("#personal-strategy").value; try { localStorage.setItem("aevra-prefs", JSON.stringify(state.prefs)); } catch {} });
    } else if (panel === "hooks") {
      setHeader("Hooks / Plugins", "Capability status");
      content.innerHTML = card("Hooks", `<div class="status-row"><span class="dot off"></span>Approval flow required</div>`) + card("Plugins / MCP", `<div class="status-row"><span class="dot off"></span>No mutation endpoint enabled</div><p class="muted">Không hiển thị nút giả khi backend chưa có contract an toàn.</p>`);
    }
  } catch (error) { content.innerHTML = card("Aevra", `<p class="error">Không tải được dữ liệu: ${esc(error.message)}</p><button class="secondary" id="retry">Thử lại</button>`); $("#retry").onclick = () => renderPanel(panel); }
}

async function send(event) {
  event.preventDefault(); const prompt = $("#prompt"); const text = prompt.value.trim(); if (!text) return;
  state.messages.push({ role: "user", content: text }); prompt.value = ""; renderChat();
  try { const result = await api("/chat", { method: "POST", body: JSON.stringify({ messages: state.messages, preset: state.prefs.preset, context_strategy: state.prefs.strategy }) }); state.messages.push({ role: "assistant", content: result.result?.choices?.[0]?.message?.content || "(Không có nội dung)" }); }
  catch (error) { state.messages.push({ role: "assistant", content: `Không thể hoàn tất inference local (${error.message}).` }); }
  renderPanel("chat");
}

function loadPrefs() { try { Object.assign(state.prefs, JSON.parse(localStorage.getItem("aevra-prefs") || "{}")); } catch {} }
function boot() { loadPrefs(); document.querySelectorAll(".nav").forEach((button) => button.onclick = () => renderPanel(button.dataset.panel)); $("#preset").onchange = (event) => { state.prefs.preset = event.target.value; }; $("#logout").onclick = () => api("/ui/logout", { method: "POST" }).then(() => window.location.assign("/pair/")); renderPanel("chat"); api("/status").then((status) => { state.status = status; $("#connection").textContent = "Connected · local"; }).catch(() => { $("#connection").textContent = "Session unavailable"; }); }
boot();
