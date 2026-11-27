import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
ELECTRON = ROOT / "desktop/electron"


def test_electron_package_targets_deb_and_pins_security_surface():
    package = json.loads((ELECTRON / "package.json").read_text())
    assert package["build"]["appId"] == "com.aevra.desktop"
    assert package["build"]["linux"]["target"] == ["deb"]
    assert package["devDependencies"]["electron"] == "39.2.6"
    assert package["build"]["afterPack"] == "after-pack.cjs"
    assert (ELECTRON / "after-pack.cjs").read_text().find("0o4755") >= 0

    main = (ELECTRON / "main.cjs").read_text()
    assert "contextIsolation: true" in main
    assert "sandbox: true" in main
    assert "nodeIntegration: false" in main
    assert "webviewTag: false" in main
    assert 'new URL("/healthz", origin)' in main
    assert 'window.loadURL(origin + "/")' in main
    assert 'parsed.pathname !== "/"' in main and "parsed.search" in main
    assert "spawn" not in main and "child_process" not in main
    assert 'permission === "clipboard-sanitized-write" && fromAevra' in main
    assert "blob:${origin}/" in main and "/api/v1/harness/generations/" in main
    assert "Authorization" not in main
    assert "token" not in main.lower()


def test_electron_renderer_only_receives_non_sensitive_product_metadata():
    preload = (ELECTRON / "preload.cjs").read_text()
    assert "contextBridge.exposeInMainWorld" in preload
    assert "ipcRenderer" not in preload
    assert "process.env" not in preload
