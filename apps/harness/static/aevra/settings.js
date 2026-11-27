/** Device-local preferences and the settings dialog. */
import { confirmDialog, dialog, h, toast } from "./ui/dom.js";
import { deleteAll, exportConversations, importConversations, listConversations, storage } from "./store.js";

export const PRESETS = [
  ["fast", "Fast", "Trả lời nhanh, không suy nghĩ dài"],
  ["balanced", "Balanced", "Cân bằng tốc độ và độ kỹ"],
  ["deep", "Deep", "Suy nghĩ kỹ, chậm hơn"],
  ["auto", "Auto", "Aevra tự chọn theo câu hỏi"],
  ["unlimited", "Unlimited", "Không giới hạn độ dài trả lời"],
];
export const STRATEGIES = [["evidence-first", "Evidence first"], ["recent-turns", "Recent turns"], ["strict", "Strict"]];
export const HISTORY = [["", "Giữ toàn bộ lịch sử"], ["sliding-window", "Sliding window"], ["token-budget", "Token budget"], ["extractive-compact", "Extractive compact (lưu archive, tối đa 16)"]];
export const THEMES = [["system", "Theo hệ thống"], ["dark", "Tối"], ["light", "Sáng"]];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const KEY = "aevra-settings";

const DEFAULTS = {
  theme: "system",
  sendOnEnter: true,
  showStats: true,
  showReasoning: true,
  autoScroll: true,
  pasteToFile: 2500,
  preset: "fast",
  strategy: "evidence-first",
  history: "",
  workspace: "",
  systemPrompt: "",
  alwaysShowSidebar: false,
};

export const settings = { ...DEFAULTS };
const listeners = new Set();

function valid(list, value, fallback) {
  return list.some(([key]) => key === value) ? value : fallback;
}

function sanitize(raw) {
  return {
    theme: valid(THEMES, raw.theme, DEFAULTS.theme),
    sendOnEnter: raw.sendOnEnter !== false,
    showStats: raw.showStats !== false,
    showReasoning: raw.showReasoning !== false,
    autoScroll: raw.autoScroll !== false,
    pasteToFile: Number.isInteger(raw.pasteToFile) && raw.pasteToFile >= 0 && raw.pasteToFile <= 100000 ? raw.pasteToFile : DEFAULTS.pasteToFile,
    preset: valid(PRESETS, raw.preset, DEFAULTS.preset),
    strategy: valid(STRATEGIES, raw.strategy, DEFAULTS.strategy),
    history: valid(HISTORY, raw.history, DEFAULTS.history),
    workspace: typeof raw.workspace === "string" && UUID.test(raw.workspace) ? raw.workspace : "",
    systemPrompt: typeof raw.systemPrompt === "string" ? raw.systemPrompt.slice(0, 8000) : "",
    alwaysShowSidebar: raw.alwaysShowSidebar === true,
  };
}

export function loadSettings() {
  let raw = {};
  try {
    raw = JSON.parse(localStorage.getItem(KEY) || "null") || JSON.parse(localStorage.getItem("aevra-prefs") || "{}") || {};
  } catch {
    raw = {};
  }
  Object.assign(settings, sanitize(raw));
  applyTheme();
}

export function updateSettings(patch) {
  Object.assign(settings, sanitize({ ...settings, ...patch }));
  try { localStorage.setItem(KEY, JSON.stringify(settings)); } catch { /* storage may be unavailable */ }
  applyTheme();
  listeners.forEach((listener) => listener(settings));
}

export function onSettings(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function isUuid(value) {
  return UUID.test(value);
}

const media = window.matchMedia("(prefers-color-scheme: light)");
media.addEventListener?.("change", () => applyTheme());

function applyTheme() {
  const light = settings.theme === "light" || (settings.theme === "system" && media.matches);
  document.documentElement.dataset.theme = light ? "light" : "dark";
}

export function labelOf(list, value) {
  return (list.find(([key]) => key === value) || [value, value])[1];
}

function select(list, value, onChange) {
  const node = h("select", { on: { change: () => onChange(node.value) } }, list.map(([key, label]) => h("option", { value: key, text: label, selected: key === value })));
  return node;
}

function toggle(label, value, onChange, hint) {
  const input = h("input", { type: "checkbox", checked: value, on: { change: () => onChange(input.checked) } });
  return h("label", { class: "toggle" }, input, h("span", {}, h("span", { text: label }), hint ? h("small", { text: hint }) : null));
}

function field(label, control, hint) {
  return h("label", { class: "field" }, h("span", { text: label }), control, hint ? h("small", { class: "muted", text: hint }) : null);
}

function download(name, data) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const link = h("a", { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export async function exportAll() {
  const conversations = await listConversations();
  const data = await exportConversations(conversations.map((conversation) => conversation.id));
  download(`aevra-conversations-${new Date().toISOString().slice(0, 10)}.json`, data);
  toast(`Đã xuất ${data.conversations.length} hội thoại.`);
}

export function downloadConversation(data, title) {
  const safe = String(title || "hoi-thoai").replace(/[^\p{L}\p{N}_-]+/gu, "-").slice(0, 40) || "hoi-thoai";
  download(`aevra-${safe}.json`, data);
}

export async function openSettings({ onDataChanged, onBeforeDeleteAll = () => {} }) {
  const sections = {
    general: () => [
      field("Giao diện", select(THEMES, settings.theme, (value) => updateSettings({ theme: value }))),
      toggle("Enter để gửi", settings.sendOnEnter, (value) => updateSettings({ sendOnEnter: value }), "Tắt thì dùng Ctrl/Cmd+Enter để gửi."),
      toggle("Luôn mở sidebar trên desktop", settings.alwaysShowSidebar, (value) => updateSettings({ alwaysShowSidebar: value })),
      field("Dán văn bản dài thành file (ký tự)", h("input", { type: "number", min: 0, max: 100000, value: settings.pasteToFile, on: { change: (event) => updateSettings({ pasteToFile: Math.max(0, Math.min(100000, Number.parseInt(event.target.value, 10) || 0)) }) } }), "0 để tắt. Văn bản dán dài hơn sẽ thành tệp đính kèm."),
    ],
    display: () => [
      toggle("Hiện thống kê sau mỗi câu trả lời", settings.showStats, (value) => updateSettings({ showStats: value })),
      toggle("Hiện phần suy nghĩ của model", settings.showReasoning, (value) => updateSettings({ showReasoning: value })),
      toggle("Tự cuộn theo câu trả lời", settings.autoScroll, (value) => updateSettings({ autoScroll: value })),
    ],
    model: () => [
      field("Mức reasoning mặc định", select(PRESETS, settings.preset, (value) => updateSettings({ preset: value })), "Mỗi hội thoại có thể đổi riêng ngay ở khung chat."),
      field("Chiến lược context", select(STRATEGIES, settings.strategy, (value) => updateSettings({ strategy: value }))),
      field("Chính sách lịch sử", select(HISTORY, settings.history, (value) => updateSettings({ history: value })), "Chỉ Extractive compact lưu phần bị rút gọn vào Context."),
      field("System message mặc định", h("textarea", { rows: 4, maxlength: 8000, value: settings.systemPrompt, on: { change: (event) => updateSettings({ systemPrompt: event.target.value }) } }), "Áp dụng cho hội thoại mới."),
    ],
    workspace: () => {
      const input = h("input", { type: "text", spellcheck: false, placeholder: "UUID của workspace", value: settings.workspace });
      const result = h("small", { class: "muted", role: "status" });
      input.addEventListener("change", () => {
        const value = input.value.trim();
        if (value && !UUID.test(value)) {
          result.textContent = "Workspace ID phải là UUID hợp lệ.";
          return;
        }
        updateSettings({ workspace: value });
        result.textContent = "Đã lưu.";
      });
      return [field("Workspace mặc định", input, "Dùng cho skill và run."), result];
    },
    data: () => {
      const file = h("input", { type: "file", accept: "application/json,.json", hidden: true, on: { change: async () => {
        const chosen = file.files?.[0];
        if (!chosen) return;
        try {
          const count = await importConversations(JSON.parse(await chosen.text()));
          toast(`Đã nhập ${count} hội thoại.`);
          onDataChanged();
        } catch {
          toast("Tệp không đúng định dạng xuất của Aevra.", "error");
        }
        file.value = "";
      } } });
      return [
        h("p", { class: "muted", text: storage.persistent ? "Hội thoại được lưu trong IndexedDB của trình duyệt trên thiết bị này; không đồng bộ lên máy chủ." : "Trình duyệt không cho dùng IndexedDB: hội thoại chỉ giữ tới khi đóng tab." }),
        h("div", { class: "button-row" },
          h("button", { type: "button", class: "secondary", on: { click: () => exportAll() } }, "Xuất toàn bộ hội thoại"),
          h("button", { type: "button", class: "secondary", on: { click: () => file.click() } }, "Nhập hội thoại"),
          file,
          h("button", { type: "button", class: "danger", on: { click: async () => {
            if (!await confirmDialog({ title: "Xóa toàn bộ lịch sử", message: "Xóa mọi hội thoại đã lưu trên thiết bị này? Không thể hoàn tác.", confirmLabel: "Xóa tất cả", danger: true })) return;
            onBeforeDeleteAll();
            await deleteAll();
            toast("Đã xóa toàn bộ lịch sử.");
            onDataChanged();
          } } }, "Xóa toàn bộ lịch sử")),
        h("div", { class: "button-row" }, h("button", { type: "button", class: "secondary", on: { click: async () => {
          if (!await confirmDialog({ title: "Khôi phục mặc định", message: "Đưa mọi thiết lập về mặc định? Lịch sử hội thoại không bị xóa." })) return;
          localStorage.removeItem(KEY);
          localStorage.removeItem("aevra-prefs");
          Object.assign(settings, DEFAULTS);
          updateSettings({});
          toast("Đã khôi phục thiết lập mặc định.");
        } } }, "Khôi phục thiết lập mặc định")),
      ];
    },
  };
  const names = [["general", "Chung"], ["display", "Hiển thị"], ["model", "Model và context"], ["workspace", "Workspace"], ["data", "Dữ liệu"]];
  const content = h("div", { class: "settings-content" });
  const nav = h("nav", { class: "settings-nav", "aria-label": "Mục cài đặt" });
  const show = (name) => {
    content.replaceChildren(...sections[name]());
    nav.querySelectorAll("button").forEach((button) => button.setAttribute("aria-current", button.dataset.section === name ? "true" : "false"));
  };
  names.forEach(([name, label]) => nav.append(h("button", { type: "button", dataset: { section: name }, text: label, on: { click: () => show(name) } })));
  show("general");
  await dialog({ title: "Cài đặt", body: h("div", { class: "settings" }, nav, content), wide: true });
}
