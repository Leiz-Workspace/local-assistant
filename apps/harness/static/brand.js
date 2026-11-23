/** Apply Aevra identity to upstream application chrome without editing conversation content or packaged assets. */
function applyAevraBrand() {
    const current = document.title;
    const replaced = current.replace(/llama(?:\.cpp|-ui)/gi, "Aevra");
    const next = !replaced ? "Aevra" : /Aevra/.test(replaced) ? replaced : replaced + " · Aevra";
    if (next !== current) document.title = next;
    if (!document.getElementById("aevra-brand")) {
        const brand = document.createElement("header");
        brand.id = "aevra-brand";
        brand.setAttribute("aria-label", "Aevra");
        const logo = document.createElement("img");
        logo.src = "/aevra/brand/logo.svg";
        logo.alt = "";
        logo.width = 32;
        logo.height = 32;
        const name = document.createElement("span");
        name.textContent = "Aevra";
        brand.append(logo, name);
        document.body.prepend(brand);
        console.info("aevra_ui_brand_ready");
    }
}

/** Track upstream title changes without observing or transforming user messages. */
function startAevraBrand() {
    applyAevraBrand();
    const title = document.querySelector("title");
    if (title) new MutationObserver(applyAevraBrand).observe(title, {childList: true, subtree: true, characterData: true});
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", startAevraBrand, {once: true});
else startAevraBrand();
