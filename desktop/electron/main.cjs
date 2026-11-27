const { app, BrowserWindow, session } = require("electron");
const { request } = require("node:http");
const path = require("node:path");

function webOrigin(value) {
  const parsed = new URL(value);
  if (parsed.protocol !== "http:" || parsed.hostname !== "127.0.0.1" || parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash) {
    throw new Error("AEVRA_WEB_URL must be a loopback HTTP origin such as http://127.0.0.1:7090");
  }
  return parsed.origin;
}

const origin = webOrigin(process.env.AEVRA_WEB_URL || "http://127.0.0.1:7090");
const healthUrl = new URL("/healthz", origin);
const START_COMMAND = "docker compose -f docker-compose.web.yaml up -d --build aevra-web";

function isReady() {
  return new Promise((resolve) => {
    const probe = request(healthUrl, { timeout: 1500 }, (response) => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    probe.on("error", () => resolve(false));
    probe.on("timeout", () => probe.destroy());
    probe.end();
  });
}

function statusPage(waitedSeconds) {
  const help = waitedSeconds >= 10
    ? `<p>Chưa thấy Aevra web tại <code>${origin}</code>.</p><p>Khởi động web trong thư mục dự án:</p><pre>${START_COMMAND}</pre><p>Cửa sổ sẽ tự kết nối khi web sẵn sàng.</p>`
    : `<p>Đang kết nối tới Aevra web tại <code>${origin}</code>…</p>`;
  const html = `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>Aevra</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#171923;color:#f4f5f7;font:15px/1.5 system-ui,sans-serif}main{max-width:560px;padding:24px;text-align:center}h1{font-size:28px;margin:0 0 12px}p{color:#a9b0c0;margin:8px 0}pre,code{font-family:ui-monospace,monospace;color:#d9b7ff}pre{background:#20232e;border:1px solid #3a3f50;border-radius:9px;padding:12px;white-space:pre-wrap}</style></head><body><main><h1>Aevra</h1>${help}</main></body></html>`;
  return "data:text/html;charset=utf-8," + encodeURIComponent(html);
}

async function connect(window) {
  const started = Date.now();
  let shown = -1;
  for (;;) {
    if (window.isDestroyed()) return;
    if (await isReady()) {
      await window.loadURL(origin + "/");
      return;
    }
    const waited = Math.floor((Date.now() - started) / 1000);
    const stage = waited >= 10 ? 10 : 0;
    if (stage !== shown) {
      shown = stage;
      await window.loadURL(statusPage(waited));
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    title: "Aevra",
    backgroundColor: "#171923",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webviewTag: false,
      spellcheck: false,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, url) => {
    if (new URL(url).origin !== origin) event.preventDefault();
  });
  window.webContents.on("did-fail-load", (_event, _code, _description, url, isMainFrame) => {
    if (isMainFrame && url.startsWith(origin)) connect(window).catch(() => {});
  });
  // Only clipboard writes from the Aevra origin are granted; camera, microphone and the rest stay denied.
  const fromAevra = (webContents) => webContents && new URL(webContents.getURL() || "about:blank").origin === origin;
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => callback(permission === "clipboard-sanitized-write" && fromAevra(webContents)));
  session.defaultSession.setPermissionCheckHandler((webContents, permission) => permission === "clipboard-sanitized-write" && fromAevra(webContents));
  // Downloads are limited to conversation exports (same-origin blobs) and generation artifacts; Electron shows a save dialog.
  session.defaultSession.on("will-download", (event, item) => {
    const url = item.getURL();
    const allowed = url.startsWith(`blob:${origin}/`) || url.startsWith(`${origin}/api/v1/harness/generations/`);
    if (!allowed) event.preventDefault();
  });
  connect(window).catch((error) => console.error("aevra_desktop_connect_failed", error.message));
}

app.whenReady().then(createWindow).catch((error) => {
  console.error("aevra_desktop_start_failed", error.message);
  app.exit(1);
});
app.on("window-all-closed", () => app.quit());
