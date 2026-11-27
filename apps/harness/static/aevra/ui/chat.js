/** Conversation view: messages, reasoning, statistics, actions and version navigation. */
import { describe } from "../api.js";
import { renderMarkdown } from "../markdown.js";
import { settings } from "../settings.js";
import { siblings } from "../tree.js";
import { confirmDialog, formatDuration, h, icon } from "./dom.js";

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
      h("div", { class: "bubble", text: message.content }),
      h("div", { class: "message-meta" },
        navigator(nodes, message),
        h("span", { class: "message-actions" },
          actionButton("copy", "Sao chép", () => handlers.onCopy(message.content)),
          actionButton("edit", "Sửa và gửi lại", () => openEditor(message, (text) => handlers.onEdit(message.id, text), "Gửi bản sửa"), { disabled: busy }),
          actionButton("branch", "Tách nhánh thành hội thoại mới", () => handlers.onFork(message.id)),
          actionButton("trash", "Xóa", () => handlers.onDelete(message.id), { disabled: busy }))));
  }

  function openEditor(message, onSave, saveLabel) {
    const article = list.querySelector(`[data-id="${CSS.escape(message.id)}"]`);
    if (!article) return;
    const cancel = async () => {
      if (area.value !== message.content && !await confirmDialog({ title: "Bỏ thay đổi", message: "Bỏ nội dung vừa sửa?", confirmLabel: "Bỏ thay đổi", danger: true })) return;
      handlers.onRerender();
      list.querySelector(`[data-id="${CSS.escape(message.id)}"] [data-act="edit"]`)?.focus();
    };
    rawViews.delete(message.id);
    const area = h("textarea", { rows: Math.min(12, Math.max(3, message.content.split("\n").length)), "aria-label": "Sửa tin nhắn", value: message.content });
    const kept = message.role === "user" ? [...(message.attachments || []).map((file) => file.name), ...(message.skill ? [`Skill ${message.skill.label || ""}`] : [])] : [];
    const editor = h("form", { class: "message-editor", on: { submit: (event) => {
      event.preventDefault();
      const text = area.value.trim();
      if (text) onSave(text);
    } } }, area, kept.length ? h("p", { class: "muted", text: `Giữ nguyên: ${kept.join(", ")}` }) : null, h("div", { class: "button-row" }, h("button", { type: "button", class: "secondary", text: "Hủy", on: { click: cancel } }), h("button", { type: "submit", class: "primary", text: saveLabel })));
    const target = article.querySelector(":scope > .bubble, :scope > .answer");
    if (!target) {
      handlers.onRerender();
      return;
    }
    target.replaceWith(editor);
    area.focus();
    area.setSelectionRange(area.value.length, area.value.length);
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
  }

  function reasoningBlock(message, streaming) {
    if (!settings.showReasoning || !message.reasoning) return null;
    const details = h("details", { class: "reasoning", open: streaming }, h("summary", { text: streaming && !message.content ? "Đang suy nghĩ…" : "Suy nghĩ" }), h("div", { class: "md", html: renderMarkdown(message.reasoning) }));
    return details;
  }

  function assistantMessage(nodes, message, busy, streaming) {
    const raw = rawViews.has(message.id) && !streaming;
    const body = raw ? h("pre", { class: "raw answer", text: message.content }) : h("div", { class: "md answer", html: message.content ? renderMarkdown(message.content) : "" });
    if (!raw) addCodeCopy(body, handlers.onCopy);
    const notices = [];
    if (streaming && !message.content && !message.reasoning) notices.push(h("p", { class: "pending", text: "Aevra đang xử lý…" }));
    if (message.status === "stopped") notices.push(h("p", { class: "note", text: "Đã dừng theo yêu cầu." }));
    if (message.edited) notices.push(h("p", { class: "note muted", text: "Đã sửa tay." }));
    if (message.omitted) notices.push(h("p", { class: "note", text: `Model không nhận được ${message.omitted} tệp đính kèm (vượt ngân sách context hoặc kích thước).` }));
    if (message.status === "error") notices.push(h("div", { class: "message-error" }, h("p", { text: describe({ code: message.error }) }), h("button", { type: "button", class: "secondary", text: "Thử lại", disabled: busy, on: { click: () => handlers.onRegenerate(message.id) } })));
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
      h("p", { class: "muted", text: "Enter để gửi · Shift+Enter xuống dòng · nút + để thêm tệp, skill hoặc system message." }));
  }

  function render({ conversation, nodes, path, streamingId, busy, reveal = false }) {
    streamingNodes = null;
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
      const exact = article?.querySelector(`[data-act="${focusKey.act}"]:not([disabled])`);
      const target = exact || (busy ? null : article?.querySelector(".message-actions button:not([disabled])"));
      if (target) target.focus({ preventScroll: true });
      else {
        pendingFocus = focusKey;
        title?.focus({ preventScroll: true });
      }
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
        article.prepend(fresh);
      }
      if (message.content || message.reasoning) article.querySelector(".pending")?.remove();
      scrollToBottom();
    });
  }

  function resetFollow() {
    follow = true;
    toBottom.hidden = true;
  }

  return { node, render, updateStreaming, scrollToBottom, resetFollow };
}
