/** Constrain upstream UI requests to the local authenticated gateway and add its CSRF marker. */
const originalFetch = window.fetch.bind(window);

/** Send an expired UI session back to local pairing instructions instead of asking for a stored API key. */
function handleSessionExpiry(response) {
    if (response.status === 401) {
        console.warn("harness_ui_session_expired");
        window.location.replace("/pair/");
    }
    return response;
}
window.fetch = function harnessFetch(input, options = {}) {
    /** Reject cross-origin endpoints before sending any browser-held state. */
    const target = new URL(input instanceof Request ? input.url : input, window.location.href);
    if (target.origin !== window.location.origin) {
        console.warn("harness_cross_origin_request_denied");
        return Promise.reject(new Error("Aevra supports same-origin requests only."));
    }
    const headers = new Headers(input instanceof Request ? input.headers : undefined);
    new Headers(options.headers).forEach((value, name) => headers.set(name, value));
    headers.set("X-Harness-UI", "1");
    headers.delete("Authorization");
    if (target.pathname === "/v1/chat/completions" && typeof options.body === "string") {
        // Upstream advertises browser tools separately; this product admits none of them.
        const body = JSON.parse(options.body);
        for (const key of ["tools", "tool_choice", "functions", "function_call"]) delete body[key];
        options = {...options, body: JSON.stringify(body)};
    }
    return originalFetch(input, {...options, headers, credentials: "same-origin", redirect: "error"}).then(handleSessionExpiry);
};
console.info("harness_ui_bridge_ready");

/** Hide upstream administration controls that the local gateway deliberately does not expose. */
function restrictCapabilities() {
    const style = document.createElement("style");
    style.textContent = 'button[aria-label="Models"],button[aria-label="MCP"],button[aria-label="Reasoning effort"]{display:initial!important}';
    document.head.appendChild(style);
    const notice = document.createElement("div");
    notice.textContent = "Aevra · Chế độ Fast · Chat lưu trên thiết bị · Task và skill qua CLI";
    notice.setAttribute("role", "note");
    notice.style.cssText = "position:fixed;bottom:0;left:0;right:0;text-align:center;font:11px system-ui;padding:2px;background:Canvas;color:CanvasText;z-index:20;pointer-events:none";
    document.body.appendChild(notice);
    console.info("harness_ui_capabilities_restricted");
}
if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", restrictCapabilities, {once: true});
}
