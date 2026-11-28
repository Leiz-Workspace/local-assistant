/** Chat composer: attachments, skill, system message, reasoning, model, context ring, mic, send/stop. */
import { api } from "../api.js";
import { MAX_ATTACHMENTS, MAX_ATTACHMENTS_TOTAL, MAX_ATTACHMENT_BYTES, PASTE_FILE_NAME, attachedBytes, evidenceBytes, pastePlacement } from "../limits.js";
import { PRESETS, labelOf, settings } from "../settings.js";
import { formatBytes, h, icon, menu, popover, promptDialog, toast } from "./dom.js";
import { loadModels } from "./panels.js";

const TEXT_EXTENSIONS = ["txt", "md", "markdown", "json", "jsonl", "csv", "tsv", "yaml", "yml", "toml", "ini", "cfg", "conf", "log", "xml", "html", "htm", "css", "scss", "js", "mjs", "cjs", "ts", "tsx", "jsx", "py", "rb", "go", "rs", "java", "kt", "c", "h", "cpp", "hpp", "cc", "cs", "php", "sh", "bash", "zsh", "sql", "swift", "dart", "lua", "r", "scala", "vue", "svelte", "tex", "rst", "adoc", "bib", "proto", "graphql", "gradle", "dockerfile", "makefile"];
const ACCEPT = TEXT_EXTENSIONS.map((extension) => `.${extension}`).join(",") + ",text/*";

export function estimateTokens(text) {
  return Math.ceil(String(text || "").length / 3);
}

function isTextFile(file) {
  const extension = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : file.name.toLowerCase();
  return file.type.startsWith("text/") || TEXT_EXTENSIONS.includes(extension) || file.type === "application/json";
}

function ring(percent, level) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", `ring ring-${level}`);
  svg.setAttribute("aria-hidden", "true");
  const circumference = 2 * Math.PI * 10;
  for (const [className, offset] of [["ring-track", 0], ["ring-value", circumference * (1 - Math.min(100, percent) / 100)]]) {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", "12");
    circle.setAttribute("cy", "12");
    circle.setAttribute("r", "10");
    circle.setAttribute("class", className);
    circle.setAttribute("stroke-dasharray", String(circumference));
    circle.setAttribute("stroke-dashoffset", String(offset));
    svg.append(circle);
  }
  return svg;
}

export function createComposer(handlers) {
  const state = { attachments: [], skill: null, busy: false, context: null, models: null, historyTokens: 0 };
  // One unsent draft (text, files, skill) per conversation, so nothing follows the user into another chat.
  const drafts = new Map();
  let draftKey = null;
  const textarea = h("textarea", { rows: 1, placeholder: "Nhắn với Aevra…", "aria-label": "Tin nhắn", spellcheck: true });
  const chips = h("div", { class: "composer-chips" });
  const fileInput = h("input", { type: "file", multiple: true, accept: ACCEPT, hidden: true });
  const plusButton = h("button", { type: "button", class: "icon-button", title: "Thêm tệp, skill hoặc system message", "aria-label": "Thêm tệp, skill hoặc system message", "aria-haspopup": "menu" }, icon("plus"));
  const reasoningButton = h("button", { type: "button", class: "pill", "aria-haspopup": "menu", title: "Mức reasoning" });
  const modelButton = h("button", { type: "button", class: "pill", "aria-haspopup": "menu", title: "Model" });
  const ringButton = h("button", { type: "button", class: "icon-button ring-button", "aria-haspopup": "dialog" });
  const micButton = h("button", { type: "button", class: "icon-button mic-button", "aria-disabled": "true", title: "Nhập bằng giọng nói: cần bật ASR local (đang chờ owner duyệt)", "aria-label": "Nhập bằng giọng nói (chưa bật)" }, icon("mic"));
  const sendButton = h("button", { type: "submit", class: "send-button", title: "Gửi", "aria-label": "Gửi" }, icon("send"));
  const form = h("form", { class: "composer", "aria-label": "Soạn tin nhắn" },
    chips,
    textarea,
    h("div", { class: "composer-actions" },
      h("div", { class: "composer-left" }, plusButton, fileInput, reasoningButton, modelButton),
      h("div", { class: "composer-right" }, ringButton, micButton, sendButton)));

  function resize() {
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, window.innerHeight * 0.4)}px`;
    updateRing();
  }

  function renderChips() {
    const items = state.attachments.map((attachment) => h("span", { class: "chip-file" }, icon("file"), h("span", { class: "chip-name", text: attachment.name, title: attachment.name }), h("small", { text: formatBytes(attachment.size) }), h("button", { type: "button", class: "chip-remove", "aria-label": `Bỏ tệp ${attachment.name}`, title: "Bỏ", on: { click: () => removeAttachment(attachment.id) } }, icon("close"))));
    if (state.skill) items.push(h("span", { class: "chip-file chip-skill" }, icon("skills"), h("span", { class: "chip-name", text: `Skill ${state.skill.label}` }), h("button", { type: "button", class: "chip-remove", "aria-label": "Bỏ skill", title: "Bỏ", on: { click: () => { state.skill = null; renderChips(); } } }, icon("close"))));
    if (handlers.getSystemPrompt()) items.push(h("span", { class: "chip-file chip-system" }, icon("system"), h("button", { type: "button", class: "chip-link", text: "System message", title: "Sửa system message", on: { click: () => editSystemPrompt() } })));
    chips.replaceChildren(...items);
    chips.hidden = items.length === 0;
    updateRing();
  }

  function removeAttachment(id) {
    state.attachments = state.attachments.filter((attachment) => attachment.id !== id);
    renderChips();
  }

  /** Attach files to the draft that was open when they were chosen, even if the user switches chats while they load. */
  async function addFiles(files) {
    const key = draftKey;
    const listFor = () => (key === draftKey ? state.attachments : drafts.get(key)?.attachments || []);
    for (const file of files) {
      if (listFor().length >= MAX_ATTACHMENTS) {
        toast(`Tối đa ${MAX_ATTACHMENTS} tệp mỗi lượt.`, "error");
        break;
      }
      if (!isTextFile(file)) {
        toast(`${file.name}: hiện chỉ hỗ trợ tệp văn bản/code. Ảnh và PDF cần owner duyệt.`, "error");
        continue;
      }
      const text = await file.text().catch(() => null);
      if (text === null || text.includes("\u0000")) {
        toast(`${file.name}: không đọc được dưới dạng văn bản.`, "error");
        continue;
      }
      if (!text.trim()) {
        toast(`${file.name}: tệp rỗng.`, "error");
        continue;
      }
      const name = file.name.slice(0, 256);
      const bytes = evidenceBytes(name, text);
      if (bytes > MAX_ATTACHMENT_BYTES) {
        toast(`${file.name}: vượt ${MAX_ATTACHMENT_BYTES / 1024} KB văn bản cho một tệp.`, "error");
        continue;
      }
      // Reading is asynchronous, so check the target draft again after the await.
      const list = listFor();
      if (list.length >= MAX_ATTACHMENTS) {
        toast(`Tối đa ${MAX_ATTACHMENTS} tệp mỗi lượt.`, "error");
        break;
      }
      if (attachedBytes(list) + bytes > MAX_ATTACHMENTS_TOTAL) {
        toast(`${file.name}: tổng tệp đính kèm vượt ${MAX_ATTACHMENTS_TOTAL / 1024} KB.`, "error");
        continue;
      }
      attach(key, { id: crypto.randomUUID(), name, size: file.size, content: text });
    }
    if (key === draftKey) renderChips();
  }

  function attach(key, attachment) {
    if (key === draftKey) {
      state.attachments.push(attachment);
      return;
    }
    const stored = drafts.get(key) || { text: "", attachments: [], skill: null };
    drafts.set(key, { ...stored, attachments: [...stored.attachments, attachment] });
  }

  async function chooseSkill() {
    let skills = [];
    try {
      skills = await api("/skills");
    } catch (error) {
      if (error.code !== "session_required") toast("Không tải được danh sách skill.", "error");
      return;
    }
    if (!skills.length) {
      menu(plusButton, [{ label: "Chưa có skill nào được cài", disabled: true }, { label: "Mở Skills để review và cài", icon: "skills", onSelect: () => handlers.openPanel("skills") }], { toggle: false });
      return;
    }
    menu(plusButton, skills.map((skill) => ({
      label: `${skill.id}@${skill.version}`,
      description: `workspace ${String(skill.workspace_id).slice(0, 8)} · ${(skill.permissions || []).join(", ")}`,
      icon: "skills",
      checked: state.skill?.installation_id === skill.installation_id,
      onSelect: () => {
        state.skill = { installation_id: skill.installation_id, workspace_id: skill.workspace_id, label: `${skill.id}@${skill.version}` };
        renderChips();
        textarea.focus();
      },
    })), { toggle: false });
  }

  async function editSystemPrompt() {
    const value = await promptDialog({ title: "System message", label: "Chỉ dẫn hệ thống cho hội thoại này", value: handlers.getSystemPrompt(), multiline: true, maxLength: 8000 });
    if (value === null) return;
    await handlers.setSystemPrompt(value.trim());
    renderChips();
  }

  function preset() {
    return handlers.getPreset();
  }

  function renderReasoning() {
    reasoningButton.replaceChildren(icon("brain"), h("span", { text: labelOf(PRESETS, preset()) }), icon("chevronDown"));
    reasoningButton.setAttribute("aria-label", `Mức reasoning: ${labelOf(PRESETS, preset())}`);
  }

  function renderModel() {
    const active = state.models?.models?.find((model) => model.profile === state.models.active);
    const online = active ? active.online !== false && active.loaded !== false : null;
    modelButton.replaceChildren(h("span", { class: `dot ${online === null ? "unknown" : online ? "on" : "off"}`, "aria-hidden": "true" }), h("span", { class: "model-name", text: active?.id || "Model" }), icon("chevronDown"));
    modelButton.setAttribute("aria-label", `Model: ${active?.id || "chưa rõ"}${online === false ? " (không phản hồi)" : ""}`);
  }

  async function refreshModels() {
    try {
      state.models = await loadModels();
    } catch {
      state.models = null;
    }
    renderModel();
    handlers.onModels?.(state.models);
  }

  function limit() {
    return state.context?.input_limit || state.context?.context_size || 32000;
  }

  function updateRing() {
    const draft = textarea.value + state.attachments.map((attachment) => attachment.content).join("");
    // The next request also carries the last answer, so its tokens count as used context.
    const base = state.context ? Number(state.context.input_tokens || 0) + Number(state.context.usage?.completion_tokens || 0) : state.historyTokens;
    const used = base + estimateTokens(draft);
    const percent = Math.round((used / limit()) * 100);
    const level = percent >= 95 ? "critical" : percent >= 80 ? "warning" : "normal";
    ringButton.replaceChildren(ring(percent, level));
    ringButton.setAttribute("aria-label", `Context đã dùng khoảng ${percent}%`);
    ringButton.title = `Context: khoảng ${percent}% (${used.toLocaleString("vi-VN")} / ${limit().toLocaleString("vi-VN")} token)`;
  }

  function contextDetails() {
    const context = state.context;
    const draft = estimateTokens(textarea.value + state.attachments.map((attachment) => attachment.content).join(""));
    const rows = [
      ["Preset", labelOf(PRESETS, context?.preset_selected || preset())],
      ["Input lần gửi gần nhất", context ? `${Number(context.input_tokens).toLocaleString("vi-VN")} token` : `~${state.historyTokens.toLocaleString("vi-VN")} token (ước tính)`],
      ["Giới hạn input", `${limit().toLocaleString("vi-VN")} token`],
      ["Context của model", context?.context_size ? `${Number(context.context_size).toLocaleString("vi-VN")} token` : "32.768 token"],
      ["Output tối đa", context?.max_tokens ? `${Number(context.max_tokens).toLocaleString("vi-VN")} token` : "theo preset"],
      ["Bản nháp và tệp", `~${draft.toLocaleString("vi-VN")} token (ước tính)`],
    ];
    if (context?.usage) rows.push(["Token lần trả lời gần nhất", `${context.usage.prompt_tokens ?? "?"} vào · ${context.usage.completion_tokens ?? "?"} ra`]);
    return h("div", { class: "context-popover" }, h("h3", { text: "Context" }), h("dl", {}, rows.map(([label, value]) => [h("dt", { text: label }), h("dd", { text: value })])), h("p", { class: "muted", text: "Số liệu chính xác lấy từ máy chủ sau mỗi lần gửi; phần bản nháp là ước tính." }));
  }

  function setBusy(busy) {
    state.busy = busy;
    sendButton.replaceChildren(icon(busy ? "stop" : "send"));
    sendButton.title = busy ? "Dừng" : "Gửi";
    sendButton.setAttribute("aria-label", busy ? "Dừng tạo câu trả lời" : "Gửi");
    sendButton.classList.toggle("stop", busy);
  }

  function submit() {
    if (state.busy) {
      handlers.onStop();
      return;
    }
    const text = textarea.value.trim();
    if (!text) {
      textarea.focus();
      return;
    }
    const attachments = state.attachments.map(({ name, content, size }) => ({ name, content, size }));
    const accepted = handlers.onSend({ text, attachments, skill: state.skill ? { ...state.skill } : null });
    if (accepted === false) return;
    // Files and the skill belong to the message just sent; only the system message stays.
    textarea.value = "";
    state.attachments = [];
    state.skill = null;
    renderChips();
    resize();
  }

  function hasDraft() {
    return Boolean(textarea.value || state.attachments.length || state.skill);
  }

  function restoreDraft(draft) {
    textarea.value = draft?.text || "";
    state.attachments = draft?.attachments || [];
    state.skill = draft?.skill || null;
    resize();
    renderChips();
  }

  /** Switch the composer to another conversation's draft, keeping the current one for later. */
  function useDraft(key) {
    if (key === draftKey) return;
    if (draftKey !== null) {
      if (hasDraft()) drafts.set(draftKey, { text: textarea.value, attachments: state.attachments, skill: state.skill });
      else drafts.delete(draftKey);
    }
    draftKey = key;
    restoreDraft(drafts.get(key));
    drafts.delete(key);
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });
  textarea.addEventListener("input", resize);
  textarea.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.isComposing || event.keyCode === 229) return;
    const modifier = event.ctrlKey || event.metaKey;
    if (modifier || (settings.sendOnEnter && !event.shiftKey)) {
      event.preventDefault();
      if (!state.busy) submit();
    }
  });
  textarea.addEventListener("paste", (event) => {
    const files = [...(event.clipboardData?.files || [])];
    if (files.length) {
      event.preventDefault();
      addFiles(files);
      return;
    }
    const text = event.clipboardData?.getData("text/plain") || "";
    if (settings.pasteToFile > 0 && text.length > settings.pasteToFile) {
      event.preventDefault();
      const placement = pastePlacement({ attachments: state.attachments, text, draft: textarea.value });
      if (placement === "attach") {
        // The text is already in memory and every limit was checked, so attach it at once.
        state.attachments.push({ id: crypto.randomUUID(), name: PASTE_FILE_NAME, size: new TextEncoder().encode(text).length, content: text });
        renderChips();
      } else if (placement === "inline") {
        // It cannot be attached (count, size or total limit): paste it inline while the message stays small enough.
        document.execCommand("insertText", false, text);
        if (handlers.exceedsTurn?.(textarea.value, state.attachments)) toast("Đã dán trực tiếp, nhưng tin nhắn và tệp đính kèm đang vượt giới hạn một lượt. Bỏ bớt tệp hoặc rút ngắn trước khi gửi.", "error");
        else toast("Không đính kèm được nên đã dán trực tiếp vào tin nhắn.");
      } else {
        toast("Văn bản dán quá lớn cho một tin nhắn. Hãy rút ngắn hoặc chia nhỏ.", "error");
      }
    }
  });
  fileInput.addEventListener("change", () => {
    addFiles([...fileInput.files]);
    fileInput.value = "";
  });
  plusButton.addEventListener("click", () => menu(plusButton, [
    { label: "Thêm tệp văn bản/code", description: `Tối đa ${MAX_ATTACHMENTS} tệp, mỗi tệp ${MAX_ATTACHMENT_BYTES / 1024} KB`, icon: "file", onSelect: () => fileInput.click() },
    { label: "Dùng skill", description: "Skill đã review và cài", icon: "skills", onSelect: () => chooseSkill() },
    { label: "System message", description: "Chỉ dẫn hệ thống cho hội thoại này", icon: "system", onSelect: () => editSystemPrompt() },
    { separator: true },
    { label: "Ảnh / PDF", description: "Cần owner duyệt vision và trích PDF", icon: "upload", disabled: true },
  ]));
  reasoningButton.addEventListener("click", () => menu(reasoningButton, PRESETS.map(([value, label, description]) => ({
    label,
    description,
    checked: value === preset(),
    onSelect: async () => {
      await handlers.setPreset(value);
      renderReasoning();
      updateRing();
    },
  }))));
  let modelClicks = 0;
  modelButton.addEventListener("click", async () => {
    // Decide open or close now; the model probe below is asynchronous.
    if (modelButton.getAttribute("aria-expanded") === "true") {
      modelClicks += 1;
      menu(modelButton, []);
      return;
    }
    const click = ++modelClicks;
    await refreshModels();
    if (click !== modelClicks) return;
    const models = state.models?.models || [];
    menu(modelButton, models.length ? models.map((model) => ({
      label: model.id,
      description: [model.profile, model.status, model.loaded === true ? "đang chạy" : model.online === false ? "CORE không phản hồi" : "", model.selectable ? "" : "Đổi profile phải khởi động lại CORE dùng chung, cần owner duyệt"].filter(Boolean).join(" · "),
      icon: "cpu",
      checked: model.profile === state.models.active,
      disabled: !model.selectable,
    })) : [{ label: "Không đọc được danh sách model", disabled: true }], { toggle: false });
  });
  ringButton.addEventListener("click", () => popover(ringButton, contextDetails(), { label: "Chi tiết context" }));
  micButton.addEventListener("click", () => popover(micButton, h("div", { class: "context-popover", "aria-label": "Nhập bằng giọng nói" }, h("h3", { text: "Nhập bằng giọng nói" }), h("p", { text: "Cần một bộ nhận dạng giọng nói chạy local. Aevra không gửi âm thanh ra dịch vụ bên ngoài, nên nút này chỉ bật sau khi owner duyệt ASR local." })), { label: "Nhập bằng giọng nói" }));

  renderReasoning();
  renderModel();
  renderChips();
  setBusy(false);
  refreshModels();

  return {
    node: form,
    focus: () => textarea.focus(),
    setBusy,
    addFiles,
    setContext(context, historyTokens = 0) {
      state.context = context;
      state.historyTokens = historyTokens;
      updateRing();
    },
    refresh() {
      renderReasoning();
      renderChips();
      updateRing();
    },
    refreshModels,
    useDraft,
    /** Hand the current draft to a key without swapping, for a new chat that just got its conversation id. */
    rekeyDraft(from, to) {
      if (draftKey === from) draftKey = to;
      else if (drafts.has(from)) {
        drafts.set(to, drafts.get(from));
        drafts.delete(from);
      }
    },
    /** Prefill another conversation's draft, used when a fork opens with the forked question and its files. */
    seedDraft(key, draft) {
      const seeded = { text: draft.text || "", attachments: draft.attachments || [], skill: draft.skill || null };
      if (key === draftKey) restoreDraft(seeded);
      else drafts.set(key, seeded);
    },
    dropDraft(key) {
      drafts.delete(key);
      if (draftKey === key) draftKey = null;
    },
    clearDrafts() {
      drafts.clear();
      draftKey = null;
    },
  };
}
