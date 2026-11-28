/** Collapsible sidebar: conversations, search, workspace tools, settings and session. */
import { settings } from "../settings.js";
import { MOD_KEY, h, icon, menu } from "./dom.js";

const KEY = "aevra-sidebar";
const TOOLS = [["context", "Context", "context"], ["memory", "Memory", "memory"], ["skills", "Skills", "skills"], ["runs", "Runs / Jobs", "runs"], ["hooks", "Hooks / Plugins", "hooks"]];

export function isMobile() {
  return window.matchMedia("(max-width: 767px)").matches;
}

export function createSidebar(handlers) {
  let expanded = true;
  try { expanded = localStorage.getItem(KEY) !== "collapsed"; } catch { expanded = true; }
  let query = "";
  let pendingFocusId = null;
  let searching = false;
  let model = { conversations: [], activeId: null, panel: null, streamingIds: new Set() };
  let mobile = isMobile();

  const toggleButton = h("button", { type: "button", class: "icon-button", on: { click: () => toggle() } }, icon("sidebar"));
  const logo = h("button", { type: "button", class: "brand", on: { click: () => {
    if (!isOpen()) {
      toggle(true);
      return;
    }
    handlers.onNewChat();
    if (isMobile()) toggle(false);
  } } }, h("img", { src: "/aevra/brand/logo.svg", alt: "" }), h("strong", { class: "label", text: "Aevra" }));
  const search = h("input", { type: "search", class: "sidebar-search", placeholder: "Tìm hội thoại…", "aria-label": "Tìm hội thoại", hidden: true, on: { input: () => { query = search.value.trim().toLowerCase(); renderList(); }, keydown: (event) => { if (event.key === "Escape") closeSearch(); } } });
  const listHost = h("div", { class: "conversation-list" });
  // On mobile the overlay closes first, so a dialog opened by the button returns focus to a reachable control.
  const navButton = (name, label, glyph, onClick, extra = {}, closesOverlay = true) => h("button", { type: "button", class: "nav", title: label, "aria-label": label, on: { click: () => { if (closesOverlay && isMobile()) toggle(false); onClick(); } }, ...extra }, icon(glyph), h("span", { class: "label", text: label }));
  const newChat = navButton("new", "Chat mới", "plus", () => handlers.onNewChat(), { title: `Chat mới (${MOD_KEY}+Shift+O)` });
  const searchButton = navButton("search", "Tìm kiếm", "search", () => openSearch(), { title: `Tìm kiếm (${MOD_KEY}+K)` }, false);
  const tools = TOOLS.map(([name, label, glyph]) => navButton(name, label, glyph, () => handlers.onPanel(name), { dataset: { panel: name } }));
  const status = h("span", { class: "status-line label" });
  const settingsButton = navButton("settings", "Cài đặt", "settings", () => handlers.onSettings());
  const logoutButton = navButton("logout", "Đăng xuất", "logout", () => handlers.onLogout());
  const node = h("aside", { class: "sidebar", id: "sidebar", "aria-label": "Thanh bên" },
    h("div", { class: "sidebar-head" }, logo, toggleButton),
    h("nav", { class: "nav-list", "aria-label": "Hội thoại" }, newChat, searchButton),
    search,
    listHost,
    h("nav", { class: "nav-list tools", "aria-label": "Công cụ workspace" }, h("p", { class: "nav-heading label", text: "Workspace" }), tools),
    h("div", { class: "sidebar-foot" }, settingsButton, logoutButton, status));
  const backdrop = h("div", { class: "sidebar-backdrop", hidden: true, on: { click: () => toggle(false) } });

  // "Luôn mở sidebar trên desktop" pins the sidebar open there; the saved rail state is left untouched.
  const pinnedOpen = () => settings.alwaysShowSidebar && !isMobile();
  const isOpen = () => expanded || pinnedOpen();

  function apply() {
    const open = isOpen();
    // A hidden mobile overlay must not be reachable by Tab or assistive tech.
    node.inert = isMobile() && !open;
    document.body.classList.toggle("sidebar-collapsed", !open);
    document.body.classList.toggle("sidebar-open", open);
    backdrop.hidden = !(open && isMobile());
    toggleButton.hidden = pinnedOpen();
    toggleButton.setAttribute("aria-expanded", String(open));
    toggleButton.setAttribute("aria-label", open ? "Thu gọn thanh bên" : "Mở thanh bên");
    toggleButton.title = open ? `Thu gọn thanh bên (${MOD_KEY}+B)` : `Mở thanh bên (${MOD_KEY}+B)`;
    logo.setAttribute("aria-label", open ? "Chat mới" : "Mở thanh bên");
    logo.title = open ? "Aevra" : "Mở thanh bên";
    if (!open) closeSearch();
  }

  function toggle(force) {
    if (pinnedOpen()) {
      apply();
      return;
    }
    expanded = typeof force === "boolean" ? force : !expanded;
    if (!isMobile()) {
      try { localStorage.setItem(KEY, expanded ? "expanded" : "collapsed"); } catch { /* storage may be unavailable */ }
    }
    apply();
    if (isMobile()) {
      handlers.onOverlay?.(expanded);
      if (expanded) newChat.focus();
    }
  }

  function openSearch() {
    toggle(true);
    searching = true;
    search.hidden = false;
    search.focus();
  }

  function closeSearch() {
    searching = false;
    query = "";
    search.value = "";
    search.hidden = true;
    renderList();
  }

  function row(conversation) {
    const active = conversation.id === model.activeId && !model.panel;
    const streaming = model.streamingIds.has(conversation.id);
    const more = h("button", { type: "button", class: "icon-button small row-more", title: "Thao tác", "aria-label": `Thao tác với ${conversation.title}`, "aria-haspopup": "menu", on: { click: (event) => {
      event.stopPropagation();
      menu(more, [
        { label: conversation.pinned ? "Bỏ ghim" : "Ghim", icon: "pin", onSelect: () => { pendingFocusId = conversation.id; handlers.onPin(conversation); } },
        { label: "Đổi tên", icon: "edit", onSelect: () => { pendingFocusId = conversation.id; handlers.onRename(conversation); } },
        { label: "Xuất JSON", icon: "download", onSelect: () => handlers.onExport(conversation) },
        { separator: true },
        { label: "Xóa", icon: "trash", danger: true, onSelect: () => handlers.onDelete(conversation) },
      ], { placement: "bottom" });
    } } }, icon("more"));
    return h("li", { class: `conversation${active ? " active" : ""}`, dataset: { id: conversation.id } },
      h("button", { type: "button", class: "conversation-open", "aria-current": active ? "page" : null, title: conversation.title, on: { click: () => { handlers.onOpen(conversation.id); if (isMobile()) toggle(false); } } },
        streaming ? h("span", { class: "spinner", role: "img", "aria-label": "Đang trả lời" }) : null,
        h("span", { class: "conversation-title", text: conversation.title })),
      streaming ? h("button", { type: "button", class: "icon-button small", title: "Dừng câu trả lời", "aria-label": `Dừng câu trả lời trong ${conversation.title}`, on: { click: (event) => { event.stopPropagation(); handlers.onStop(conversation.id); } } }, icon("stop")) : null,
      more);
  }

  function renderList() {
    const items = model.conversations.filter((conversation) => !query || conversation.title.toLowerCase().includes(query));
    const pinned = items.filter((conversation) => conversation.pinned);
    const recent = items.filter((conversation) => !conversation.pinned);
    const groups = [];
    if (searching && query) groups.push(h("p", { class: "nav-heading", text: items.length ? "Kết quả tìm kiếm" : "Không tìm thấy hội thoại" }));
    if (pinned.length) groups.push(h("p", { class: "nav-heading", text: "Đã ghim" }), h("ul", {}, pinned.map(row)));
    if (recent.length) groups.push(h("p", { class: "nav-heading", text: searching && query ? "" : "Gần đây" }), h("ul", {}, recent.map(row)));
    if (!model.conversations.length) groups.push(h("p", { class: "muted empty-list", text: "Chưa có hội thoại nào." }));
    const focusedRow = listHost.contains(document.activeElement) ? document.activeElement.closest(".conversation") : null;
    const focusedId = focusedRow?.dataset.id;
    const focusedMore = document.activeElement?.classList.contains("row-more");
    const pendingMenu = pendingFocusId;
    listHost.replaceChildren(...groups);
    // Re-rendering replaces the rows; keep keyboard focus on the same conversation and control.
    const restoreId = focusedId || pendingMenu;
    if (restoreId) {
      const rowNode = [...listHost.querySelectorAll(".conversation")].find((item) => item.dataset.id === restoreId);
      if (rowNode && (focusedId || document.activeElement === document.body)) rowNode.querySelector(focusedMore || pendingMenu ? ".row-more" : ".conversation-open")?.focus();
      pendingFocusId = null;
    }
    tools.forEach((button) => {
      const current = button.dataset.panel === model.panel;
      button.classList.toggle("active", current);
      if (current) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
  }

  window.addEventListener("resize", () => {
    const now = isMobile();
    if (now !== mobile) {
      mobile = now;
      if (now) expanded = false;
      else {
        try { expanded = localStorage.getItem(KEY) !== "collapsed"; } catch { expanded = true; }
      }
      handlers.onOverlay?.(false);
    }
    apply();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isMobile() && expanded && !document.querySelector(".overlay, .popover")) {
      event.preventDefault();
      toggle(false);
    }
  });
  if (mobile) expanded = false;
  apply();

  return {
    node,
    backdrop,
    toggle,
    openSearch,
    apply,
    render(next) {
      model = { ...model, ...next };
      renderList();
    },
    setStatus(text, tone = "ok") {
      status.textContent = text;
      status.dataset.tone = tone;
    },
  };
}
