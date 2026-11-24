/** Aevra product shell around the pinned llama.cpp UI. */
const AEVRA_API = "/api/v1/harness";

function el(tag, attrs = {}, text = "") {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (text) node.textContent = text;
    return node;
}

async function readJson(path) {
    const response = await fetch(AEVRA_API + path, {credentials: "same-origin"});
    if (!response.ok) throw new Error("request_failed");
    return response.json();
}

function panelSection(title, body) {
    const section = el("section", {class: "aevra-panel-section"});
    section.append(el("h3", {}, title), body);
    return section;
}

function listBlock(items, empty) {
    const list = el("ul", {class: "aevra-list"});
    if (!items || !items.length) list.append(el("li", {class: "aevra-muted"}, empty));
    else items.slice(0, 30).forEach(item => {
        const label = typeof item === "string" ? item : (item.name || item.id || item.identifier || item.run_id || "Item");
        list.append(el("li", {}, label));
    });
    return list;
}

async function loadProductPanel(panel, section) {
    panel.querySelectorAll(".aevra-panel-section.dynamic").forEach(node => node.remove());
    const loading = el("p", {class: "aevra-muted"}, "Đang tải…");
    panel.append(loading);
    try {
        let title, body;
        if (section === "context" || section === "memory") {
            const data = await readJson("/context/archives");
            title = section === "memory" ? "Memory / Archives" : "Context window";
            body = listBlock(data, "Chưa có archive trong phiên này.");
        } else if (section === "skills") {
            const data = await readJson("/skills");
            title = "Skills";
            body = listBlock(data, "Chưa có skill installation.");
        } else if (section === "runs") {
            const data = await readJson("/runs");
            title = "Runs / Jobs";
            body = listBlock(data, "Chưa có run nào.");
        } else {
            title = section === "personal" ? "Personalize" : "Hooks & Plugins";
            body = el("div", {class: "aevra-card"}, section === "personal"
                ? "Cài đặt cá nhân được quản lý trong CLI và profile local."
                : "Hooks/plugins cần approval flow; chưa có endpoint an toàn để bật trực tiếp từ web.");
        }
        loading.remove();
        const block = panelSection(title, body);
        block.classList.add("dynamic");
        panel.append(block);
    } catch {
        loading.textContent = "Không tải được dữ liệu phiên. Hãy pair lại UI.";
        loading.className = "aevra-muted aevra-error";
    }
}

function installProductShell() {
    if (document.getElementById("aevra-product-shell")) return;
    const toggle = el("button", {id: "aevra-product-toggle", type: "button", "aria-label": "Open Aevra product panel"}, "A");
    const panel = el("aside", {id: "aevra-product-shell", "aria-label": "Aevra product controls", hidden: ""});
    if (typeof toggle.addEventListener !== "function" || typeof document.body.append !== "function") {
        const brand = el("header", {id: "aevra-brand", "aria-label": "Aevra"});
        const logo = el("img"); logo.src = "/aevra/brand/logo.svg"; logo.alt = "";
        const name = el("span", {}, "Aevra"); brand.append(logo, name); document.body.prepend(brand); return;
    }
    const header = el("div", {class: "aevra-panel-header"});
    header.append(el("strong", {}, "Aevra"));
    const close = el("button", {type: "button", class: "aevra-close", "aria-label": "Close Aevra product panel"}, "×");
    header.append(close);
    panel.append(header, el("p", {class: "aevra-panel-kicker"}, "Product workspace"));
    const nav = el("nav", {class: "aevra-product-nav", "aria-label": "Aevra features"});
    [["context", "Context"], ["memory", "Memory"], ["skills", "Skills"], ["runs", "Runs"], ["personal", "Personal"], ["hooks", "Hooks / Plugins"]].forEach(([key, label]) => {
        const button = el("button", {type: "button", "data-aevra-section": key}, label);
        button.addEventListener("click", () => loadProductPanel(panel, key));
        nav.append(button);
    });
    panel.append(nav);
    toggle.addEventListener("click", () => { panel.hidden = !panel.hidden; if (!panel.hidden) loadProductPanel(panel, "context"); });
    close.addEventListener("click", () => { panel.hidden = true; });
    document.body.append(toggle, panel);
}

function applyAevraBrand() {
    const current = document.title;
    const replaced = current.replace(/llama(?:\.cpp|-ui)/gi, "Aevra");
    const next = !replaced ? "Aevra" : /Aevra/.test(replaced) ? replaced : replaced + " · Aevra";
    if (next !== current) document.title = next;
    installProductShell();
}

function startAevraBrand() {
    applyAevraBrand();
    const title = document.querySelector("title");
    if (title) new MutationObserver(applyAevraBrand).observe(title, {childList: true, subtree: true, characterData: true});
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", startAevraBrand, {once: true});
else startAevraBrand();
