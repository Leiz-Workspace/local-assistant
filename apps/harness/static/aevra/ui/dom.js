/** Small DOM toolkit: safe element builder, toasts, dialogs, popovers and menus. */

export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "html") node.innerHTML = value;
    else if (key === "on") Object.entries(value).forEach(([event, handler]) => node.addEventListener(event, handler));
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "value") node.value = value;
    else if (key in node && typeof value !== "string") node[key] = value;
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  append(node, children);
  return node;
}

function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function icon(name, label) {
  const paths = ICONS[name] || ICONS.dot;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", label ? "false" : "true");
  if (label) svg.setAttribute("aria-label", label);
  for (const d of paths) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

const ICONS = {
  dot: ["M12 12h.01"],
  plus: ["M12 5v14", "M5 12h14"],
  chat: ["M4 5h16v11H8l-4 4z"],
  search: ["M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z", "M20 20l-4-4"],
  sidebar: ["M4 4h16v16H4z", "M9 4v16"],
  context: ["M12 3a9 9 0 1 0 9 9", "M12 7v5l3 2"],
  memory: ["M6 4h12v16H6z", "M9 8h6", "M9 12h6", "M9 16h3"],
  skills: ["M14 4l6 6-10 10H4v-6z", "M13 5l6 6"],
  runs: ["M5 4l14 8-14 8z"],
  hooks: ["M8 4v6a4 4 0 0 0 8 0V4", "M12 14v6"],
  settings: ["M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z", "M4 12h2", "M18 12h2", "M12 4v2", "M12 18v2", "M6.3 6.3l1.4 1.4", "M16.3 16.3l1.4 1.4", "M6.3 17.7l1.4-1.4", "M16.3 7.7l1.4-1.4"],
  logout: ["M15 4h4v16h-4", "M10 8l-4 4 4 4", "M6 12h10"],
  mic: ["M12 4a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V7a3 3 0 0 0-3-3z", "M6 11a6 6 0 0 0 12 0", "M12 17v3"],
  send: ["M4 12l16-8-6 16-3-6z"],
  stop: ["M7 7h10v10H7z"],
  file: ["M7 3h7l5 5v13H7z", "M14 3v5h5"],
  close: ["M6 6l12 12", "M18 6L6 18"],
  copy: ["M9 9h11v11H9z", "M5 15V4h11"],
  edit: ["M4 20h4L19 9l-4-4L4 16z"],
  refresh: ["M20 11a8 8 0 1 0-2.3 5.7", "M20 4v7h-7"],
  trash: ["M4 7h16", "M9 7V4h6v3", "M6 7l1 13h10l1-13"],
  more: ["M6 12h.01", "M12 12h.01", "M18 12h.01"],
  pin: ["M9 4h6l-1 6 3 3H7l3-3z", "M12 13v7"],
  chevronLeft: ["M15 6l-6 6 6 6"],
  chevronRight: ["M9 6l6 6-6 6"],
  chevronDown: ["M6 9l6 6 6-6"],
  brain: ["M9 4a3 3 0 0 0-3 3v1a3 3 0 0 0-2 5 3 3 0 0 0 3 5h2V4z", "M15 4a3 3 0 0 1 3 3v1a3 3 0 0 1 2 5 3 3 0 0 1-3 5h-2V4z"],
  cpu: ["M7 7h10v10H7z", "M10 10h4v4h-4z", "M9 3v4", "M15 3v4", "M9 17v4", "M15 17v4", "M3 9h4", "M3 15h4", "M17 9h4", "M17 15h4"],
  system: ["M4 6h16", "M4 12h10", "M4 18h7"],
  download: ["M12 4v12", "M7 11l5 5 5-5", "M5 20h14"],
  upload: ["M12 20V8", "M7 13l5-5 5 5", "M5 4h14"],
  arrowDown: ["M12 5v14", "M6 13l6 6 6-6"],
  check: ["M5 12l5 5 9-10"],
  code: ["M9 8l-4 4 4 4", "M15 8l4 4-4 4"],
  branch: ["M6 4v10", "M6 14a4 4 0 0 0 4 4h4", "M18 6a2 2 0 1 0 0 .01", "M6 8c0 4 12 0 12 6"],
};

const toastHost = document.body.appendChild(h("div", { class: "toasts", role: "status", "aria-live": "polite" }));
export function toast(message, tone = "info") {
  const node = h("div", { class: `toast toast-${tone}`, text: message });
  toastHost.append(node);
  window.setTimeout(() => node.classList.add("leaving"), 3200);
  window.setTimeout(() => node.remove(), 3600);
}

/* Layers (popovers and dialogs) form a stack: Escape and outside clicks affect only the top one. */
const layers = [];

function top() {
  return layers[layers.length - 1] || null;
}

function closeTop() {
  top()?.close();
}

function closePopovers() {
  while (top()?.kind === "popover") closeTop();
}

function focusables(root) {
  return [...root.querySelectorAll("button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])")].filter((node) => !node.hidden && node.offsetParent !== null);
}

function setInert(except) {
  const changed = [];
  for (const child of document.body.children) {
    if (child === except || child === toastHost || child.id === "announcer" || child.inert) continue;
    child.inert = true;
    changed.push(child);
  }
  return () => changed.forEach((child) => { child.inert = false; });
}

document.addEventListener("keydown", (event) => {
  const layer = top();
  if (!layer) return;
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    closeTop();
  } else if (event.key === "Tab" && layer.kind === "popover") {
    // Tab leaves a popover: close it and return focus to the control that opened it.
    event.preventDefault();
    closeTop();
  } else if (event.key === "Tab" && layer.kind === "dialog") {
    const items = focusables(layer.node);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
}, true);
document.addEventListener("mousedown", (event) => {
  const layer = top();
  if (layer?.kind === "popover" && !layer.node.contains(event.target) && !layer.anchor?.contains(event.target)) closeTop();
});

export function popover(anchor, content, { placement = "top", className = "", role = "dialog", label = "" } = {}) {
  closePopovers();
  const node = h("div", { class: `popover ${className}`, role, "aria-label": label || null, tabindex: "-1" }, content);
  document.body.append(node);
  const rect = anchor.getBoundingClientRect();
  const width = node.offsetWidth;
  const height = node.offsetHeight;
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
  const top = placement === "top" && rect.top - height - 8 > 8 ? rect.top - height - 8 : Math.min(rect.bottom + 8, window.innerHeight - height - 8);
  node.style.left = `${left}px`;
  node.style.top = `${Math.max(8, top)}px`;
  anchor.setAttribute("aria-expanded", "true");
  const layer = {
    kind: "popover",
    node,
    anchor,
    close: ({ restoreFocus = true } = {}) => {
      const index = layers.indexOf(layer);
      if (index === -1) return;
      layers.splice(index, 1);
      const hadFocus = node.contains(document.activeElement) || document.activeElement === document.body;
      node.remove();
      anchor.setAttribute("aria-expanded", "false");
      if (restoreFocus && hadFocus && anchor.isConnected) anchor.focus();
    },
  };
  layers.push(layer);
  const preferred = node.querySelector("[aria-checked='true']:not([disabled])") || focusables(node).find((item) => item !== node) || node;
  preferred.focus();
  return () => layer.close();
}

export function menu(anchor, items, options = {}) {
  const buttons = [];
  const list = h("div", { class: "menu" }, items.filter(Boolean).map((item) => {
    if (item.separator) return h("div", { class: "menu-separator", role: "separator" });
    const radio = item.checked !== undefined;
    const button = h("button", {
      type: "button",
      role: radio ? "menuitemradio" : "menuitem",
      "aria-checked": radio ? String(Boolean(item.checked)) : null,
      class: `menu-item${item.danger ? " danger" : ""}${item.checked ? " checked" : ""}`,
      disabled: item.disabled || false,
      title: item.hint || null,
      on: { click: () => { top()?.close({ restoreFocus: !item.keepFocusAway }); item.onSelect?.(); } },
    }, item.icon ? icon(item.icon) : null, h("span", { class: "menu-label" }, h("span", { text: item.label }), item.description ? h("small", { text: item.description }) : null), item.checked ? icon("check") : null);
    buttons.push(button);
    return button;
  }));
  list.addEventListener("keydown", (event) => {
    const enabled = buttons.filter((button) => !button.disabled);
    const index = enabled.indexOf(document.activeElement);
    const move = { ArrowDown: index + 1, ArrowUp: index - 1, Home: 0, End: enabled.length - 1 }[event.key];
    if (move === undefined || !enabled.length) return;
    event.preventDefault();
    enabled[(move + enabled.length) % enabled.length].focus();
  });
  return popover(anchor, list, { className: "menu-popover", role: "menu", label: options.label || anchor.getAttribute("aria-label") || "", ...options });
}

export function dialog({ title, body, actions = [], wide = false, initialFocus = null, describedBy = null }) {
  closePopovers();
  return new Promise((resolve) => {
    const previous = document.activeElement;
    let restoreInert = () => {};
    let done = false;
    const finish = (value) => {
      if (done) return;
      done = true;
      const index = layers.indexOf(layer);
      if (index !== -1) layers.splice(index, 1);
      restoreInert();
      overlay.remove();
      if (previous?.isConnected) previous.focus();
      resolve(value);
    };
    const titleId = `dialog-${Math.random().toString(36).slice(2)}`;
    const buttons = actions.map((action) => h("button", {
      type: action.submit ? "submit" : "button",
      class: action.tone === "danger" ? "danger" : action.tone === "primary" ? "primary" : "secondary",
      text: action.label,
      dataset: { role: action.role || "" },
      on: action.submit ? {} : { click: () => finish(action.value) },
    }));
    const form = h("form", { class: `dialog${wide ? " wide" : ""}`, role: "dialog", "aria-modal": "true", "aria-labelledby": titleId, "aria-describedby": describedBy, on: { submit: (event) => {
      event.preventDefault();
      const submit = actions.find((action) => action.submit);
      finish(typeof submit?.value === "function" ? submit.value(form) : submit?.value);
    } } }, h("header", { class: "dialog-head" }, h("h2", { id: titleId, text: title }), h("button", { type: "button", class: "icon-button", "aria-label": "Đóng", title: "Đóng", on: { click: () => finish(undefined) } }, icon("close"))), h("div", { class: "dialog-body" }, body), buttons.length ? h("footer", { class: "dialog-actions" }, buttons) : null);
    const overlay = h("div", { class: "overlay", on: { mousedown: (event) => { if (event.target === overlay) finish(undefined); } } }, form);
    const layer = { kind: "dialog", node: form, close: () => finish(undefined) };
    layers.push(layer);
    document.body.append(overlay);
    restoreInert = setInert(overlay);
    const target = (initialFocus && form.querySelector(initialFocus)) || form.querySelector("[autofocus]") || form.querySelector("input, textarea, select") || form.querySelector(".dialog-actions button:last-child");
    target?.focus();
  });
}

export async function confirmDialog({ title, message, confirmLabel = "Xác nhận", danger = false }) {
  const describedBy = `confirm-${Math.random().toString(36).slice(2)}`;
  const result = await dialog({
    title,
    body: h("p", { id: describedBy, text: message }),
    describedBy,
    actions: [{ label: "Hủy", value: false, role: "cancel" }, { label: confirmLabel, value: true, tone: danger ? "danger" : "primary", submit: true }],
    // Destructive confirmations start on the safe choice.
    initialFocus: danger ? "[data-role='cancel']" : null,
  });
  return result === true;
}

export async function promptDialog({ title, label, value = "", multiline = false, maxLength = 200 }) {
  const field = multiline
    ? h("textarea", { rows: 6, maxlength: maxLength, autofocus: true })
    : h("input", { type: "text", maxlength: maxLength, autofocus: true });
  field.value = value;
  const result = await dialog({
    title,
    body: h("label", { class: "field" }, h("span", { text: label }), field),
    actions: [{ label: "Hủy", value: null }, { label: "Lưu", tone: "primary", submit: true, value: () => field.value }],
  });
  return typeof result === "string" ? result : null;
}

export function hasOpenDialog() {
  return layers.some((layer) => layer.kind === "dialog");
}

export function announce(text) {
  const node = document.getElementById("announcer");
  if (!node) return;
  node.textContent = "";
  window.setTimeout(() => { node.textContent = String(text).slice(0, 300); }, 50);
}

export function formatDuration(ms) {
  if (!Number.isFinite(ms)) return "";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function formatBytes(value) {
  const number = Number(value) || 0;
  if (number < 1024) return `${number} B`;
  if (number < 1048576) return `${(number / 1024).toFixed(1)} KB`;
  return `${(number / 1048576).toFixed(1)} MB`;
}
