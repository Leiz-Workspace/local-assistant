/** Conversation view: messages, reasoning, statistics, actions and version navigation. */
import { describe } from "../api.js";
import { renderMarkdown } from "../markdown.js";
import { settings } from "../settings.js";
import { siblings } from "../tree.js";
import { MOD_KEY, confirmDialog, formatDuration, h, icon } from "./dom.js";

// Focus that was on a control which disappears after the action moves to the matching message action.
const FOCUS_ALIAS = { "edit-save": "edit", "edit-cancel": "edit", editor: "edit", retry: "refresh" };

function actionButton(name, label, onClick, extra = {}) {
  return h("button", { type: "button", class: "icon-button small", title: label, "aria-label": label, dataset: { act: name }, on: { click: onClick }, ...extra }, icon(name));
}

function addCodeCopy(container, onCopy) {
  container.querySelectorAll("pre").forEach((pre) => {
    if (pre.querySelector(".code-copy")) return;
    const code = pre.querySelector("code");
    pre.append(h("button", { type: "button", class: "code-copy", title: "Sao chép code", "aria-label": "Sao chép code", on: { click: () => onCopy(code?.textContent || "") } }, icon("copy")));
  });
}

function stats(message) {
  const parts = [];
  const tokens = message.usage?.completion_tokens;
  if (tokens) parts.push(`${tokens.toLocaleString("vi-VN")} token`);
  if (tokens && message.timing?.generationMs > 0) parts.push(`${(tokens / (message.timing.generationMs / 1000)).toFixed(1)} token/s`);
  if (message.timing?.totalMs) parts.push(formatDuration(message.timing.totalMs));
  if (message.timing?.firstTokenMs) parts.push(`token đầu ${formatDuration(message.timing.firstTokenMs)}`);
  if (message.context?.input_tokens) parts.push(`input ${Number(message.context.input_tokens).toLocaleString("vi-VN")}`);
  return parts.join(" · ");
}

export function createChatView(handlers) {
  const list = h("div", { class: "messages", role: "log", "aria-label": "Hội thoại", "aria-live": "off" });
  const toBottom = h("button", { type: "button", class: "to-bottom", title: "Xuống cuối", "aria-label": "Xuống cuối hội thoại", hidden: true, on: { click: () => scrollToBottom(true) } }, icon("arrowDown"));
  const scroller = h("div", { class: "chat-scroll" }, list);
  const node = h("div", { class: "chat-view" }, scroller, toBottom);
  let follow = true;
  const rawViews = new Set();
  let streamingNodes = null;
  let pendingFocus = null;
  let pendingFrame = 0;
  // The open inline editor; its text lives here, so any re-render restores it instead of dropping it.
  let editing = null;

  scroller.addEventListener("scroll", () => {
    const distance = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    follow = distance < 80;
    toBottom.hidden = follow;
  });

  function scrollToBottom(force = false) {
    if (force || (follow && settings.autoScroll)) {
      scroller.scrollTop = scroller.scrollHeight;
      follow = true;
      toBottom.hidden = true;
    }
  }

  function navigator(nodes, message) {
    const ids = siblings(nodes, message.id);
    if (ids.length < 2) return null;
    const index = ids.indexOf(message.id);
    return h("span", { class: "versions", role: "group", "aria-label": "Phiên bản" },
      actionButton("chevronLeft", "Phiên bản trước", () => handlers.onSwitch(message.id, -1), { disabled: index === 0 }),
      h("span", { class: "version-count", text: `${index + 1}/${ids.length}` }),
      actionButton("chevronRight", "Phiên bản sau", () => handlers.onSwitch(message.id, 1), { disabled: index === ids.length - 1 }));
  }

  function speaker(name) {
    return h("h3", { class: "visually-hidden", text: name });
  }

  function userMessage(nodes, message, busy) {
    const files = (message.attachments || []).map((file) => h("span", { class: "chip-file" }, icon("file"), h("span", { class: "chip-name", text: file.name })));
    if (message.skill) files.push(h("span", { class: "chip-file chip-skill" }, icon("skills"), h("span", { class: "chip-name", text: `Skill ${message.skill.label || ""}` })));
    return h("article", { class: "message user", dataset: { id: message.id } },
      speaker("Bạn"),
      files.length ? h("div", { class: "message-files" }, files) : null,
      editing?.id === message.id ? editorFor(message, busy) : h("div", { class: "bubble", text: message.content }),
      h("div", { class: "message-meta" },
        navigator(nodes, message),
        h("span", { class: "message-actions" },
          actionButton("copy", "Sao chép", () => handlers.onCopy(message.content)),
          actionButton("edit", "Sửa và gửi lại", () => openEditor(message, (text) => handlers.onEdit(message.id, text), "Gửi bản sửa"), { disabled: busy }),
          actionButton("branch", "Tách nhánh thành hội thoại mới", () => handlers.onFork(message.id)),
          actionButton("trash", "Xóa", () => handlers.onDelete(message.id), { disabled: busy }))));
  }

  async function openEditor(message, onSave, saveLabel) {
    if (editing?.id === message.id) {
      list.querySelector('[data-act="editor"]')?.focus();
      return;
    }
    if (editing && editing.value !== editing.original && !await confirmDialog({ title: "Bỏ thay đổi", message: "Bỏ nội dung đang sửa ở tin nhắn khác?", confirmLabel: "Bỏ thay đổi", danger: true })) return;
    rawViews.delete(message.id);
    editing = { id: message.id, convId: message.convId, value: message.content, original: message.content, onSave, saveLabel, start: message.content.length, end: message.content.length, focus: true };
    handlers.onRerender();
  }

  function editorFor(message, busy) {
    const current = editing;
    const remember = () => {
      current.value = area.value;
      current.start = area.selectionStart;
      current.end = area.selectionEnd;
    };
    const area = h("textarea", { rows: Math.min(12, Math.max(3, current.value.split("\n").length)), "aria-label": "Sửa tin nhắn", dataset: { act: "editor" }, value: current.value, on: { input: remember, select: remember, keyup: remember, mouseup: remember } });
    // Focus is on the editor or its Hủy button here; the re-render moves it to the message's edit action
    // (or parks it on the title while that action is disabled).
    const cancel = async () => {
      if (current.value !== current.original && !await confirmDialog({ title: "Bỏ thay đổi", message: "Bỏ nội dung vừa sửa?", confirmLabel: "Bỏ thay đổi", danger: true })) return;
      if (editing === current) editing = null;
      handlers.onRerender();
    };
    const kept = message.role === "user" ? [...(message.attachments || []).map((file) => file.name), ...(message.skill ? [`Skill ${message.skill.label || ""}`] : [])] : [];
    const editor = h("form", { class: "message-editor", on: { submit: (event) => {
      event.preventDefault();
      const text = area.value.trim();
      if (!text || busy) return;
      // The editor closes only when the app accepts the edit; a refused edit keeps the text.
      if (current.onSave(text) === false) return;
      if (editing === current) editing = null;
    } } },
    area,
    kept.length ? h("p", { class: "muted", text: `Giữ nguyên: ${kept.join(", ")}` }) : null,
    h("div", { class: "button-row" },
      h("button", { type: "button", class: "secondary", text: "Hủy", dataset: { act: "edit-cancel" }, on: { click: cancel } }),
      h("button", { type: "submit", class: "primary", text: current.saveLabel, dataset: { act: "edit-save" }, disabled: busy, title: busy ? "Đợi câu trả lời hiện tại xong" : null })));
    area.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        editor.requestSubmit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        cancel();
      }
    });
    return editor;
  }

  function retryButton(message, busy) {
    return h("button", { type: "button", class: "secondary", text: "Thử lại", dataset: { act: "retry" }, disabled: busy, on: { click: () => handlers.onRegenerate(message.id) } });
  }

  function reasoningBlock(message, streaming) {
    if (!settings.showReasoning || !message.reasoning) return null;
    const details = h("details", { class: "reasoning", open: streaming }, h("summary", { text: streaming && !message.content ? "Đang suy nghĩ…" : "Suy nghĩ" }), h("div", { class: "md", html: renderMarkdown(message.reasoning) }));
    return details;
  }

  function assistantMessage(nodes, message, busy, streaming) {
    const raw = rawViews.has(message.id) && !streaming;
    const editingThis = editing?.id === message.id && !streaming;
    const body = editingThis ? editorFor(message, busy)
      : raw ? h("pre", { class: "raw answer", text: message.content })
        : h("div", { class: "md answer", html: message.content ? renderMarkdown(message.content) : "" });
    if (!raw && !editingThis) addCodeCopy(body, handlers.onCopy);
    const notices = [];
    if (streaming && !message.content && !message.reasoning) notices.push(h("p", { class: "pending", text: "Aevra đang xử lý…" }));
    if (message.status === "stopped") notices.push(h("div", { class: "message-note" }, h("p", { class: "note", text: "Đã dừng theo yêu cầu." }), retryButton(message, busy)));
    if (message.edited) notices.push(h("p", { class: "note muted", text: "Đã sửa tay." }));
    if (message.omitted) notices.push(h("p", { class: "note", text: `Model không nhận được ${message.omitted} tệp đính kèm (vượt ngân sách context hoặc kích thước).` }));
    if (message.duplicates) notices.push(h("p", { class: "note muted", text: `${message.duplicates} tệp đính kèm trùng nội dung với tệp khác nên chỉ gửi cho model một lần.` }));
    if (message.status === "error") notices.push(h("div", { class: "message-error" }, h("p", { text: describe({ code: message.error }) }), retryButton(message, busy)));
    const info = settings.showStats && !streaming && message.status === "done" ? stats(message) : "";
    const article = h("article", { class: `message assistant${streaming ? " streaming" : ""}`, dataset: { id: message.id }, "aria-busy": streaming ? "true" : null },
      speaker("Aevra"),
      reasoningBlock(message, streaming),
      body,
      notices,
      h("div", { class: "message-meta" },
        navigator(nodes, message),
        streaming ? null : h("span", { class: "message-actions" },
          actionButton("copy", "Sao chép", () => handlers.onCopy(message.content), { disabled: !message.content }),
          actionButton("refresh", "Tạo lại câu trả lời", () => handlers.onRegenerate(message.id), { disabled: busy }),
          actionButton("edit", "Sửa câu trả lời (không gửi lại)", () => openEditor(message, (text) => handlers.onEditAssistant(message.id, text), "Lưu"), { disabled: busy || !message.content }),
          actionButton("code", raw ? "Xem dạng Markdown" : "Xem dạng thô", () => { if (raw) rawViews.delete(message.id); else rawViews.add(message.id); handlers.onRerender(); }, { "aria-pressed": String(raw), disabled: !message.content }),
          actionButton("branch", "Tách nhánh thành hội thoại mới", () => handlers.onFork(message.id)),
          actionButton("trash", "Xóa", () => handlers.onDelete(message.id), { disabled: busy })),
        info ? h("span", { class: "message-stats", text: info }) : null));
    if (streaming) streamingNodes = { article, body, message };
    return article;
  }

  function emptyState(conversation) {
    return h("div", { class: "empty-chat" },
      h("img", { src: "/aevra/brand/logo.svg", alt: "" }),
      h("h2", { text: conversation ? conversation.title : "Aevra" }),
      h("p", { text: "Local assistant · dữ liệu giữ trên máy của bạn." }),
      h("p", { class: "muted", text: `${settings.sendOnEnter ? "Enter để gửi · Shift+Enter xuống dòng" : `${MOD_KEY}+Enter để gửi · Enter xuống dòng`} · nút + để thêm tệp, skill hoặc system message.` }));
  }

  function render({ conversation, nodes, path, streamingId, busy, reveal = false }) {
    streamingNodes = null;
    // An editor whose message was deleted from this conversation has nothing left to restore.
    if (editing && conversation && editing.convId === conversation.id && !nodes.has(editing.id)) editing = null;
    if (reveal) follow = true;
    // Re-rendering replaces every message; remember which action had focus to restore it.
    const focused = list.contains(document.activeElement) ? document.activeElement : null;
    const title = document.getElementById("title");
    // While an answer streams its actions are disabled, so focus parks on the title and
    // returns to the same action once the re-render after the stream enables it again.
    const parked = !focused && pendingFocus && (document.activeElement === title || document.activeElement === document.body);
    const focusKey = focused?.dataset.act
      ? { act: focused.dataset.act, role: focused.closest(".message")?.classList.contains("user") ? "user" : "assistant", index: [...list.querySelectorAll(".message")].indexOf(focused.closest(".message")) }
      : parked ? pendingFocus : null;
    pendingFocus = null;
    if (!path.length) {
      list.replaceChildren(emptyState(conversation));
      return;
    }
    list.replaceChildren(...path.filter((message) => message.role !== "system").map((message) => (message.role === "user"
      ? userMessage(nodes, message, busy)
      : assistantMessage(nodes, message, busy, message.id === streamingId))));
    scrollToBottom(reveal);
    if (focusKey) {
      const messages = [...list.querySelectorAll(".message")];
      const article = messages[focusKey.index] || messages.filter((item) => item.classList.contains(focusKey.role)).at(-1);
      const alias = FOCUS_ALIAS[focusKey.act];
      const exact = article?.querySelector(`[data-act="${focusKey.act}"]:not([disabled])`) || (alias ? article?.querySelector(`[data-act="${alias}"]:not([disabled])`) : null);
      const target = exact || (busy ? null : article?.querySelector(".message-actions button:not([disabled])"));
      if (target) target.focus({ preventScroll: true });
      else {
        pendingFocus = focusKey;
        title?.focus({ preventScroll: true });
      }
    }
    // Restore the open editor's caret, and focus it when it was just opened.
    const area = editing ? list.querySelector('[data-act="editor"]') : null;
    if (area && (editing.focus || document.activeElement === area)) {
      if (editing.focus) area.focus({ preventScroll: true });
      area.setSelectionRange(editing.start, editing.end);
      editing.focus = false;
    }
  }

  function updateStreaming() {
    if (pendingFrame) return;
    pendingFrame = window.requestAnimationFrame(() => {
      pendingFrame = 0;
      if (!streamingNodes?.article.isConnected) return;
      const { article, body, message } = streamingNodes;
      body.innerHTML = renderMarkdown(message.content);
      addCodeCopy(body, handlers.onCopy);
      const existing = article.querySelector(".reasoning");
      const fresh = reasoningBlock(message, true);
      if (existing && fresh) {
        existing.querySelector("summary").textContent = message.content ? "Suy nghĩ" : "Đang suy nghĩ…";
        existing.querySelector(".md").innerHTML = renderMarkdown(message.reasoning);
      } else if (fresh) {
        // Keep the reading order of a full render: heading, reasoning, then the answer.
        body.before(fresh);
      }
      if (message.content || message.reasoning) article.querySelector(".pending")?.remove();
      scrollToBottom();
    });
  }

  function resetFollow() {
    follow = true;
    toBottom.hidden = true;
  }

  /** Drop the open editor for a deleted conversation, or any editor when no conversation is given. */
  function discardEdit(convId) {
    if (!convId || editing?.convId === convId) editing = null;
  }

  return { node, render, updateStreaming, scrollToBottom, resetFollow, discardEdit };
}
