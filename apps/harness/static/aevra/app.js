import { ApiError, api, bootstrapSession, describe, request, session, sessionMessage, streamChat } from "./api.js";
import { MAX_BYTES, buildRequest, byteSize } from "./history.js";
import { classifyOmitted } from "./limits.js";
import { renderMarkdown } from "./markdown.js";
import { downloadConversation, loadSettings, onSettings, openSettings, settings } from "./settings.js";
import { deleteConversation, deleteMessages, exportConversations, listConversations, loadConversation, newId, saveConversation, saveMessages } from "./store.js";
import { addNode, latestLeaf, pathTo, removeSubtree, siblings, subtree } from "./tree.js";
import { createChatView } from "./ui/chat.js";
import { createComposer, estimateTokens } from "./ui/composer.js";
import { announce, confirmDialog, h, hasOpenDialog, icon, menu, promptDialog, toast } from "./ui/dom.js";
import { PANELS, handlePanelAction, refreshSettingsViews, renderPanel, stopPanels } from "./ui/panels.js";
import { createSidebar } from "./ui/sidebar.js";

const DRAFT = "draft";
const state = {
  conversations: [],
  active: null,
  panel: null,
  streams: new Map(),
  pending: new Set(),
  deleted: new Set(),
  sessionLost: false,
  draftPreset: null,
  draftSystemPrompt: null,
};
// The status chip reports the web session and CORE readiness (true, false or null when not known yet).
const connection = { web: false, core: null };

loadSettings();

const title = h("h1", { id: "title", tabindex: "-1", text: "Aevra" });
const subtitle = h("p", { id: "subtitle", text: "Local assistant" });
const statusChip = h("span", { class: "status-chip", role: "status" });
const conversationMenu = h("button", { type: "button", class: "icon-button", title: "Thao tác hội thoại", "aria-label": "Thao tác hội thoại", "aria-haspopup": "menu", hidden: true }, icon("more"));
const menuButton = h("button", { type: "button", class: "icon-button mobile-only", title: "Mở thanh bên", "aria-label": "Mở thanh bên", "aria-controls": "sidebar", "aria-expanded": "false" }, icon("sidebar"));
const panelHost = h("section", { class: "panel-view", hidden: true });
const dropOverlay = h("div", { class: "drop-overlay", hidden: true }, h("p", { text: "Thả tệp văn bản/code để đính kèm" }));

const activeId = () => state.active?.conversation.id || null;
const isBusy = (id) => Boolean(id && (state.streams.has(id) || state.pending.has(id)));

const chatView = createChatView({
  onCopy: (text) => copy(text),
  onEdit: (id, text) => editMessage(id, text),
  onEditAssistant: (id, text) => editAssistant(id, text),
  onRegenerate: (id) => regenerate(id),
  onDelete: (id) => deleteMessage(id),
  onFork: (id) => forkFrom(id),
  onSwitch: (id, delta) => switchVersion(id, delta),
  onRerender: () => renderChat(),
});

const composer = createComposer({
  getConversation: () => state.active?.conversation || null,
  getPreset: () => state.active?.conversation.preset || state.draftPreset || settings.preset,
  getSystemPrompt: () => (state.active ? state.active.conversation.systemPrompt || "" : state.draftSystemPrompt ?? settings.systemPrompt),
  onSend: (draft) => send(draft),
  onStop: () => state.streams.get(activeId())?.controller.abort(),
  setPreset: async (preset) => {
    if (state.active) {
      state.active.conversation.preset = preset;
      await updateConversation(state.active.conversation.id, { preset });
    } else {
      state.draftPreset = preset;
    }
  },
  setSystemPrompt: async (value) => {
    if (state.active) await updateConversation(state.active.conversation.id, { systemPrompt: value });
    else state.draftSystemPrompt = value;
  },
  openPanel: (name) => navigate(`#/panel/${name}`),
  onModels: (models) => {
    // The fallback list comes from the web process without probing CORE, so it says nothing about readiness.
    if (!models || models.fallback) return;
    const active = models.models?.find((model) => model.profile === models.active);
    connection.web = true;
    if (active?.online === false || active?.loaded === false) setCoreReady(false);
    else if (active?.online === true) setCoreReady(true);
    else showConnected();
  },
  exceedsTurn: (text, attachments) => {
    const system = (state.active ? state.active.conversation.systemPrompt : state.draftSystemPrompt ?? settings.systemPrompt)?.trim() || "";
    return envelopeBytes(system, attachments) + byteSize({ role: "user", content: text }) > MAX_BYTES;
  },
});

const chatHost = h("section", { class: "chat-host" }, chatView.node, h("div", { class: "composer-dock" }, composer.node));

const sidebar = createSidebar({
  onOverlay: (open) => {
    main.inert = open;
    menuButton.setAttribute("aria-expanded", String(open));
    if (!open && menuButton.offsetParent) menuButton.focus();
  },
  onNewChat: () => navigate("#/"),
  onOpen: (id) => navigate(`#/chat/${id}`),
  onPanel: (name) => navigate(`#/panel/${name}`),
  onSettings: () => showSettings(),
  onLogout: () => logout(),
  onStop: (id) => state.streams.get(id)?.controller.abort(),
  onPin: (conversation) => updateConversation(conversation.id, { pinned: !conversation.pinned }),
  onRename: (conversation) => renameConversation(conversation),
  onExport: async (conversation) => downloadConversation(await exportConversations([conversation.id]), conversation.title),
  onDelete: (conversation) => removeConversation(conversation),
});

const main = h("main", { class: "main" },
  h("header", { class: "topbar" }, menuButton, h("div", { class: "heading" }, title, subtitle), h("div", { class: "topbar-actions" }, statusChip, conversationMenu)),
  h("div", { class: "workspace" }, chatHost, panelHost));
document.getElementById("app").replaceChildren(sidebar.node, sidebar.backdrop, main, dropOverlay);

function navigate(hash) {
  if (location.hash === hash) route(true);
  else location.hash = hash;
}

function setStatus(text, tone = "ok") {
  statusChip.textContent = text;
  statusChip.dataset.tone = tone;
  sidebar.setStatus(text, tone);
}


function showConnected() {
  if (state.sessionLost || session.signedOut || !connection.web) return;
  if (connection.core === false) setStatus("Web đã kết nối · CORE không phản hồi", "warn");
  else setStatus(connection.core ? "Đã kết nối · CORE sẵn sàng" : "Đã kết nối · local");
}

function setCoreReady(ready) {
  connection.core = ready;
  showConnected();
}

function webConnected() {
  connection.web = true;
  showConnected();
}

/** Plain text of a reply for screen readers, taken from the rendered (escaped) Markdown. */
function plain(text) {
  const node = document.createElement("div");
  node.innerHTML = renderMarkdown(text);
  node.querySelectorAll("pre").forEach((pre) => pre.replaceWith(" (khối code) "));
  return node.textContent.replace(/\s+/g, " ").trim().slice(0, 300);
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Đã sao chép.");
  } catch {
    const area = h("textarea", { value: text, class: "visually-hidden" });
    document.body.append(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    toast(ok ? "Đã sao chép." : "Không sao chép được.", ok ? "info" : "error");
  }
}

async function refreshConversations() {
  state.conversations = await listConversations();
  // The session screen shows no conversation, so none is highlighted until the user reconnects.
  sidebar.render({ conversations: state.conversations, activeId: state.sessionLost ? null : activeId(), panel: state.panel, streamingIds: new Set(state.streams.keys()) });
}

function titleFrom(text) {
  const line = text.split("\n").find((part) => part.trim()) || "Hội thoại mới";
  return line.trim().slice(0, 60);
}

async function ensureConversation() {
  if (state.active) return state.active;
  const now = Date.now();
  const conversation = { id: newId(), title: "Hội thoại mới", createdAt: now, updatedAt: now, currNode: null, pinned: false, preset: state.draftPreset || settings.preset, systemPrompt: state.draftSystemPrompt ?? settings.systemPrompt ?? "" };
  await saveConversation(conversation);
  state.active = { conversation, nodes: new Map() };
  state.draftPreset = null;
  state.draftSystemPrompt = null;
  // Anything typed while the new chat is being created now belongs to it.
  composer.rekeyDraft(DRAFT, conversation.id);
  history.replaceState(null, "", `#/chat/${conversation.id}`);
  await refreshConversations();
  return state.active;
}

/** Merge a patch into the stored conversation and every in-memory copy of it. */
async function updateConversation(id, patch) {
  for (const copyOf of [state.active, state.streams.get(id)?.active]) {
    if (copyOf?.conversation.id === id) Object.assign(copyOf.conversation, patch);
  }
  const stored = await loadConversation(id);
  if (!stored) return;
  await saveConversation({ ...stored.conversation, ...patch });
  await refreshConversations();
  if (!state.sessionLost) renderHeader();
}

async function renameConversation(conversation) {
  const value = await promptDialog({ title: "Đổi tên hội thoại", label: "Tên hội thoại", value: conversation.title, maxLength: 120 });
  if (value?.trim()) await updateConversation(conversation.id, { title: value.trim().slice(0, 120) });
}

function forget(id) {
  state.deleted.add(id);
  state.streams.get(id)?.controller.abort();
}

async function removeConversation(conversation) {
  if (!await confirmDialog({ title: "Xóa hội thoại", message: `Xóa "${conversation.title}" khỏi thiết bị này? Không thể hoàn tác.`, confirmLabel: "Xóa", danger: true })) return;
  forget(conversation.id);
  composer.dropDraft(conversation.id);
  chatView.discardEdit(conversation.id);
  await deleteConversation(conversation.id);
  toast("Đã xóa hội thoại.");
  const wasActive = activeId() === conversation.id;
  if (wasActive) state.active = null;
  await refreshConversations();
  // From a panel, stay on the panel; only the chat view moves to a new chat.
  if (wasActive && !state.panel) navigate("#/");
  // The deleted row held focus; keep the keyboard on the page heading instead of the body.
  else if (!document.activeElement || document.activeElement === document.body) title.focus();
}

function showSettings(section) {
  openSettings({
    section,
    onBeforeDeleteAll: () => {
      state.conversations.forEach((conversation) => forget(conversation.id));
      state.streams.forEach((_, id) => forget(id));
      state.active = null;
      state.draftPreset = null;
      state.draftSystemPrompt = null;
      composer.clearDrafts();
      chatView.discardEdit();
      if (location.hash.startsWith("#/chat/")) history.replaceState(null, "", "#/");
    },
    onDataChanged: () => refreshConversations().then(() => route(true)),
  });
}

function activePath() {
  return state.active ? pathTo(state.active.nodes, state.active.conversation.currNode) : [];
}

function renderHeader() {
  if (state.panel) {
    const [name, description] = PANELS[state.panel];
    title.textContent = name;
    subtitle.textContent = description;
    conversationMenu.hidden = true;
    return;
  }
  title.textContent = state.active?.conversation.title || "Chat mới";
  subtitle.textContent = "Aevra · local assistant";
  conversationMenu.hidden = !state.active;
}

function renderChat({ reveal = false } = {}) {
  const path = activePath();
  const id = activeId();
  const stream = id ? state.streams.get(id) : null;
  chatView.render({ conversation: state.active?.conversation || null, nodes: state.active?.nodes || new Map(), path, streamingId: stream?.messageId || null, busy: isBusy(id), reveal });
  const lastAssistant = [...path].reverse().find((message) => message.role === "assistant" && message.context);
  // A stopped answer has no usage frame; estimate its tokens because it is sent as history.
  const usage = lastAssistant?.usage || (lastAssistant ? { completion_tokens: estimateTokens(lastAssistant.content) } : null);
  composer.useDraft(id || DRAFT);
  composer.setContext(lastAssistant?.context ? { ...lastAssistant.context, usage } : null, estimateTokens(path.map((message) => message.content).join("")));
  composer.setBusy(isBusy(id));
  composer.refresh();
  renderHeader();
}

function showChat({ reveal = false } = {}) {
  stopPanels();
  state.panel = null;
  panelHost.hidden = true;
  chatHost.hidden = false;
  renderChat({ reveal });
}

/** Bytes the request needs besides the history pairs: system message, attachments and envelope. */
function envelopeBytes(system, attachments) {
  return (system ? byteSize({ role: "system", content: system }) : 0) + (attachments.length ? byteSize(attachments.map(({ name, content }) => ({ name, content }))) : 0) + 2048;
}

function tooLarge(system, attachments, text) {
  if (envelopeBytes(system, attachments) + byteSize({ role: "user", content: text }) <= MAX_BYTES) return false;
  toast("Tin nhắn, system message và tệp đính kèm quá lớn cho một lượt (tổng tối đa khoảng 230 KB).", "error");
  return true;
}

async function persistAfterStream(active, assistant) {
  const { conversation } = active;
  if (state.deleted.has(conversation.id)) return false;
  const stored = await loadConversation(conversation.id);
  if (!stored) return false;
  // Keep fields changed elsewhere (title, pin, preset) and own only the tree position.
  Object.assign(conversation, { ...stored.conversation, currNode: conversation.currNode, updatedAt: Date.now() });
  await saveMessages([assistant]);
  await saveConversation({ ...conversation });
  return true;
}

async function generate(active, assistantId) {
  const { conversation, nodes } = active;
  const assistant = nodes.get(assistantId);
  const user = nodes.get(assistant.parent);
  const attachments = (user.attachments || []).map(({ name, content }) => ({ name, content }));
  const system = conversation.systemPrompt?.trim() || "";
  const controller = new AbortController();
  state.streams.set(conversation.id, { controller, messageId: assistant.id, active });
  state.pending.delete(conversation.id);
  state.pending.delete(DRAFT);
  const started = performance.now();
  let first = 0;
  try {
    sidebar.render({ streamingIds: new Set(state.streams.keys()) });
    if (state.active === active && !state.panel) renderChat({ reveal: true });
    const request = buildRequest(pathTo(nodes, user.id), system, MAX_BYTES - envelopeBytes(system, attachments));
    if (!request) throw new ApiError("request_limit", 413);
    if (request.droppedPairs > 0) toast(`Đã bỏ ${request.droppedPairs} cặp hỏi/đáp cũ nhất khỏi ngữ cảnh gửi model để vừa giới hạn.`);
    const body = { messages: request.messages, preset: conversation.preset || settings.preset, context_strategy: settings.strategy };
    if (settings.history) body.history_policy = { mode: settings.history };
    if (attachments.length) body.attachments = attachments;
    if (user.skill) body.skill = { installation_id: user.skill.installation_id, workspace_id: user.skill.workspace_id };
    await streamChat(body, {
      signal: controller.signal,
      onContext: (context) => {
        assistant.context = context;
        if (state.active === active) composer.setContext(context);
      },
      onDelta: ({ content, reasoning }) => {
        if ((content || reasoning) && !first) first = performance.now();
        assistant.content += content;
        assistant.reasoning += reasoning;
        if (state.active === active && !state.panel) chatView.updateStreaming();
      },
      onUsage: (usage) => { assistant.usage = usage; },
    });
    if (assistant.content.trim()) {
      assistant.status = "done";
      setCoreReady(true);
      if (state.active === active) announce(`Aevra trả lời: ${plain(assistant.content)}`);
      // Duplicates whose first copy was included reached the model once; the rest were left out.
      const { omitted, duplicates } = classifyOmitted(assistant.context, attachments);
      if (omitted) assistant.omitted = omitted;
      if (duplicates) assistant.duplicates = duplicates;
    } else {
      assistant.status = "error";
      assistant.error = "empty_answer";
    }
  } catch (error) {
    if (error?.name === "AbortError") {
      assistant.status = "stopped";
      if (state.active === active) announce("Đã dừng câu trả lời.");
    } else {
      assistant.status = "error";
      assistant.error = error?.code || "inference_unavailable";
      if (assistant.error === "inference_unavailable") setCoreReady(false);
      if (assistant.error !== "session_required" && state.active === active) announce(describe(error));
    }
  } finally {
    const ended = performance.now();
    assistant.timing = { totalMs: ended - started, firstTokenMs: first ? first - started : null, generationMs: first ? ended - first : null };
    state.streams.delete(conversation.id);
    await persistAfterStream(active, assistant).catch(() => false);
    await refreshConversations();
    if (state.active === active && !state.panel && !state.sessionLost) renderChat();
    else if (!state.panel && !state.sessionLost) composer.setBusy(isBusy(activeId()));
  }
}

function send({ text, attachments, skill }) {
  const key = activeId() || DRAFT;
  if (isBusy(key) || state.sessionLost) return false;
  const system = (state.active ? state.active.conversation.systemPrompt : state.draftSystemPrompt ?? settings.systemPrompt)?.trim() || "";
  if (tooLarge(system, attachments, text)) return false;
  state.pending.add(key);
  composer.setBusy(true);
  let started = null;
  (async () => {
    const active = await ensureConversation();
    const { conversation, nodes } = active;
    started = conversation.id;
    state.pending.add(conversation.id);
    const now = Date.now();
    const userId = newId();
    addNode(nodes, { id: userId, convId: conversation.id, parent: conversation.currNode, children: [], role: "user", content: text, attachments, skill, createdAt: now });
    const assistantId = newId();
    addNode(nodes, { id: assistantId, convId: conversation.id, parent: userId, children: [], role: "assistant", content: "", reasoning: "", status: "streaming", createdAt: now + 1 });
    conversation.currNode = assistantId;
    if (conversation.title === "Hội thoại mới") conversation.title = titleFrom(text);
    await saveMessages([nodes.get(userId), nodes.get(assistantId)]);
    await saveConversation(conversation);
    await refreshConversations();
    await generate(active, assistantId);
  })().catch((error) => {
    state.pending.delete(key);
    if (started) state.pending.delete(started);
    toast(describe(error), "error");
    composer.setBusy(isBusy(activeId()));
  });
  return true;
}

async function regenerate(assistantId) {
  const active = state.active;
  if (!active || isBusy(active.conversation.id)) return;
  const { conversation, nodes } = active;
  const old = nodes.get(assistantId);
  const user = old?.parent ? nodes.get(old.parent) : null;
  if (!user) return;
  if (tooLarge(conversation.systemPrompt?.trim() || "", user.attachments || [], user.content)) return;
  state.pending.add(conversation.id);
  try {
    const id = newId();
    addNode(nodes, { id, convId: conversation.id, parent: user.id, children: [], role: "assistant", content: "", reasoning: "", status: "streaming", createdAt: Date.now() });
    conversation.currNode = id;
    await saveMessages([nodes.get(id)]);
    await saveConversation(conversation);
    await generate(active, id);
  } catch (error) {
    toast(describe(error), "error");
  } finally {
    state.pending.delete(conversation.id);
  }
}

/** Edit a user turn into a sibling branch and regenerate; returns false when the edit is refused. */
function editMessage(userId, text) {
  const active = state.active;
  if (!active || isBusy(active.conversation.id)) return false;
  const { conversation, nodes } = active;
  const original = nodes.get(userId);
  if (!original) return false;
  if (tooLarge(conversation.systemPrompt?.trim() || "", original.attachments || [], text)) return false;
  state.pending.add(conversation.id);
  (async () => {
    try {
      const now = Date.now();
      const editedId = newId();
      addNode(nodes, { ...original, id: editedId, children: [], content: text, createdAt: now });
      const assistantId = newId();
      addNode(nodes, { id: assistantId, convId: conversation.id, parent: editedId, children: [], role: "assistant", content: "", reasoning: "", status: "streaming", createdAt: now + 1 });
      conversation.currNode = assistantId;
      await saveMessages([nodes.get(editedId), nodes.get(assistantId)]);
      await saveConversation(conversation);
      await generate(active, assistantId);
    } catch (error) {
      toast(describe(error), "error");
    } finally {
      state.pending.delete(conversation.id);
    }
  })();
  return true;
}

/** Replace an answer's text locally; returns false when the edit is refused. */
function editAssistant(id, text) {
  const active = state.active;
  if (!active || isBusy(active.conversation.id)) return false;
  const message = active.nodes.get(id);
  if (!message) return false;
  message.content = text;
  message.edited = true;
  if (message.status === "error") message.status = "done";
  saveMessages([message]).catch(() => toast("Không lưu được bản sửa trên thiết bị này.", "error")).finally(() => {
    if (state.active === active && !state.panel) renderChat();
  });
  return true;
}

async function deleteMessage(id) {
  const active = state.active;
  if (!active || isBusy(active.conversation.id)) return;
  const { conversation, nodes } = active;
  const count = subtree(nodes, id).length;
  if (!await confirmDialog({ title: "Xóa tin nhắn", message: count > 1 ? `Xóa tin nhắn này và ${count - 1} tin nhắn sau nó trong nhánh? Không thể hoàn tác.` : "Xóa tin nhắn này? Không thể hoàn tác.", confirmLabel: count > 1 ? `Xóa ${count} tin nhắn` : "Xóa", danger: true })) return;
  const { removed, next } = removeSubtree(nodes, id);
  await deleteMessages(removed);
  conversation.currNode = next;
  await updateConversation(conversation.id, { currNode: next, updatedAt: Date.now() });
  renderChat();
}

async function forkFrom(id) {
  const active = state.active;
  if (!active) return;
  const target = active.nodes.get(id);
  const draft = target?.role === "user" ? target.content : "";
  const path = target?.role === "user" ? pathTo(active.nodes, target.parent) : pathTo(active.nodes, id);
  const now = Date.now();
  const conversation = { ...active.conversation, id: newId(), title: `Nhánh của ${active.conversation.title}`.slice(0, 120), createdAt: now, updatedAt: now, pinned: false };
  if (!path.length && !draft) return;
  const ids = new Map(path.map((message) => [message.id, newId()]));
  const messages = path.map((message, index) => ({ ...message, id: ids.get(message.id), convId: conversation.id, parent: index ? ids.get(path[index - 1].id) : null, children: index < path.length - 1 ? [ids.get(path[index + 1].id)] : [], status: message.status === "streaming" ? "stopped" : message.status }));
  conversation.currNode = messages.length ? messages[messages.length - 1].id : null;
  conversation.forkedFrom = active.conversation.id;
  if (messages.length) await saveMessages(messages);
  await saveConversation(conversation);
  await refreshConversations();
  toast("Đã tách thành hội thoại mới.");
  // A fork from a question reopens it as the draft, with the same files and skill.
  if (draft) composer.seedDraft(conversation.id, { text: draft, attachments: (target.attachments || []).map((file) => ({ ...file, id: newId() })), skill: target.skill ? { ...target.skill } : null });
  navigate(`#/chat/${conversation.id}`);
}

async function switchVersion(id, delta) {
  if (!state.active) return;
  const { conversation, nodes } = state.active;
  const ids = siblings(nodes, id);
  const target = ids[ids.indexOf(id) + delta];
  if (!target) return;
  const currNode = latestLeaf(nodes, target);
  conversation.currNode = currNode;
  await updateConversation(conversation.id, { currNode });
  renderChat();
}

/** Rebuild children from parent pointers so stale persisted lists (other tabs, imports) cannot hide branches. */
function buildNodes(messages) {
  const nodes = new Map(messages.map((message) => [message.id, { ...message, children: [] }]));
  [...nodes.values()].sort((a, b) => a.createdAt - b.createdAt).forEach((message) => {
    if (message.parent && nodes.has(message.parent) && message.parent !== message.id) nodes.get(message.parent).children.push(message.id);
    else message.parent = null;
  });
  // A reply interrupted by a reload or crash is shown as stopped, never as still streaming.
  nodes.forEach((message) => {
    if (message.status === "streaming") {
      message.status = message.content ? "stopped" : "error";
      if (!message.content) message.error = "incomplete_completion";
    }
  });
  return nodes;
}

async function openConversation(id) {
  const streaming = state.streams.get(id);
  if (streaming) {
    state.active = streaming.active;
    chatView.resetFollow();
    showChat();
    return;
  }
  const loaded = await loadConversation(id);
  if (!loaded) {
    toast("Không tìm thấy hội thoại trên thiết bị này.", "error");
    navigate("#/");
    return;
  }
  const nodes = buildNodes(loaded.messages);
  const conversation = { ...loaded.conversation };
  if (!nodes.has(conversation.currNode)) {
    const roots = [...nodes.values()].filter((message) => !message.parent);
    conversation.currNode = roots.length ? latestLeaf(nodes, roots[roots.length - 1].id) : null;
  }
  state.active = { conversation, nodes };
  chatView.resetFollow();
  showChat({ reveal: true });
}

function showSessionRequired(message) {
  state.sessionLost = true;
  stopPanels();
  state.panel = null;
  chatHost.hidden = true;
  panelHost.hidden = false;
  conversationMenu.hidden = true;
  title.textContent = "Kết nối phiên";
  subtitle.textContent = "Aevra · local assistant";
  setStatus("Chưa có phiên", "warn");
  panelHost.replaceChildren(h("article", { class: "card" },
    h("h2", { text: "Cần kết nối phiên local" }),
    h("p", { text: message }),
    h("p", { class: "muted" }, "Nếu máy chủ tắt tự tạo phiên, chạy ", h("code", { text: "aevra ui open" }), " để mở phiên bằng token của owner. Lịch sử hội thoại vẫn nằm trên thiết bị này."),
    h("p", {}, h("button", { type: "button", class: "primary", text: "Kết nối lại", on: { click: () => reconnect() } }))));
  // No conversation is open on this screen, so none is highlighted.
  sidebar.render({ panel: null, activeId: null });
}

async function reconnect() {
  session.setSignedOut(false);
  const result = await bootstrapSession();
  if (!result.ok) {
    showSessionRequired(sessionMessage(result.code));
    return;
  }
  state.sessionLost = false;
  showConnected();
  composer.refreshModels();
  await route(true, { resume: true });
  title.focus();
}

async function logout() {
  session.setSignedOut(true);
  state.streams.forEach((stream) => stream.controller.abort());
  try {
    await request("/ui/logout", { method: "POST", body: "{}" });
  } catch { /* the session may already be gone */ }
  showSessionRequired(sessionMessage(""));
}

async function showPanel(name) {
  if (!PANELS[name]) {
    navigate("#/");
    return;
  }
  state.panel = name;
  chatHost.hidden = true;
  panelHost.hidden = false;
  renderHeader();
  sidebar.render({ panel: name });
  announce(`Đã mở ${PANELS[name][0]}`);
  await renderPanel(name, panelHost);
}

async function route(force = false, { resume = false } = {}) {
  // A logout or a lost session holds until "Kết nối lại", whatever the route.
  if (session.signedOut) {
    showSessionRequired(sessionMessage(""));
    return;
  }
  if (state.sessionLost && !resume) return;
  const [, kind, value] = (location.hash || "#/").split("/");
  if (kind === "panel") {
    await showPanel(value);
  } else if (kind === "chat" && value) {
    if (force || activeId() !== value || state.panel || chatHost.hidden) await openConversation(value);
    composer.focus();
  } else {
    // The new chat keeps its own preset and system message until it becomes a conversation.
    state.active = null;
    chatView.resetFollow();
    showChat();
    composer.focus();
  }
  sidebar.render({ activeId: activeId(), panel: state.panel });
}

panelHost.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (button && state.panel) handlePanelAction(button, panelHost, { openSettings: () => showSettings("model") });
});

conversationMenu.addEventListener("click", () => {
  const conversation = state.active?.conversation;
  if (!conversation) return;
  menu(conversationMenu, [
    { label: "Đổi tên", icon: "edit", onSelect: () => renameConversation(conversation) },
    { label: conversation.pinned ? "Bỏ ghim" : "Ghim", icon: "pin", onSelect: () => updateConversation(conversation.id, { pinned: !conversation.pinned }) },
    { label: "Xuất JSON", icon: "download", onSelect: async () => downloadConversation(await exportConversations([conversation.id]), conversation.title) },
    { separator: true },
    { label: "Xóa hội thoại", icon: "trash", danger: true, onSelect: () => removeConversation(conversation) },
  ], { placement: "bottom" });
});
menuButton.addEventListener("click", () => sidebar.toggle(true));

document.addEventListener("keydown", (event) => {
  const modifier = event.ctrlKey || event.metaKey;
  if (!modifier || hasOpenDialog()) return;
  const key = event.key.toLowerCase();
  if (key === "b" && !event.shiftKey) {
    event.preventDefault();
    sidebar.toggle();
  } else if (key === "k" && !event.shiftKey) {
    event.preventDefault();
    sidebar.openSearch();
  } else if (key === "o" && event.shiftKey) {
    event.preventDefault();
    navigate("#/");
  }
});

let dragDepth = 0;
const hasFiles = (event) => [...(event.dataTransfer?.types || [])].includes("Files");
document.addEventListener("dragenter", (event) => {
  if (!hasFiles(event) || chatHost.hidden || hasOpenDialog()) return;
  dragDepth += 1;
  dropOverlay.hidden = false;
});
// Without this the browser opens a file dropped anywhere outside the composer and unloads Aevra.
document.addEventListener("dragover", (event) => {
  if (hasFiles(event)) event.preventDefault();
});
document.addEventListener("dragleave", () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) dropOverlay.hidden = true;
});
document.addEventListener("drop", (event) => {
  dragDepth = 0;
  dropOverlay.hidden = true;
  if (!hasFiles(event)) return;
  event.preventDefault();
  if (hasOpenDialog() || chatHost.hidden || !main.contains(event.target)) {
    if (event.dataTransfer?.files?.length) toast("Chỉ thả tệp vào khung chat.", "error");
    return;
  }
  if (event.dataTransfer?.files?.length) composer.addFiles([...event.dataTransfer.files]);
});

session.onRequired = (message) => showSessionRequired(message);
session.onConnected = () => webConnected();
onSettings(() => {
  sidebar.apply();
  if (state.panel) refreshSettingsViews(state.panel, panelHost);
  else if (!state.sessionLost) renderChat();
});
window.addEventListener("hashchange", () => route());

async function checkStatus() {
  try {
    await api("/status");
    webConnected();
  } catch (error) {
    if (error instanceof ApiError && error.code === "session_required") return;
    setStatus(error?.code === "network_unavailable" ? "Không kết nối được máy chủ" : `Máy chủ báo lỗi (${error?.code})`, "warn");
  }
}

setStatus("Đang kết nối…", "warn");
await refreshConversations();
await route(true);
checkStatus();
