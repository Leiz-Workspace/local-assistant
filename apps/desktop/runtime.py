"""Host the pinned Aevra chat interface inside a native WebKitGTK window with no Python bridge or external navigation."""

import hashlib
from contextlib import contextmanager
import fcntl
import json
import logging
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from apps.desktop.identity import APPLICATION_ID

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def validate_bootstrap(value):
    """Accept one finite direct-loopback pairing and an opaque profile scope without exposing application credentials."""
    if type(value) is not dict or set(value) != {"url", "code", "profile"}:
        raise ValueError("invalid_desktop_bootstrap")
    url = value["url"]
    parsed = urlsplit(url) if isinstance(url, str) else None
    if (
        parsed is None
        or parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid_desktop_origin")
    if (
        not isinstance(value["code"], str)
        or re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value["code"]) is None
        or not isinstance(value["profile"], str)
        or re.fullmatch(r"[a-f0-9]{64}", value["profile"]) is None
    ):
        raise ValueError("invalid_desktop_bootstrap")
    if parsed.port is not None and not 1024 <= parsed.port <= 65535:
        raise ValueError("invalid_desktop_origin")
    return {**value, "url": url.rstrip("/")}


def allowed_uri(uri, origin):
    """Allow only same-origin HTTP pages; deny local files, scripts, other ports and external destinations."""
    try:
        parsed, base = urlsplit(uri), urlsplit(origin)
        return (
            parsed.scheme == base.scheme == "http"
            and parsed.hostname == base.hostname
            and parsed.port == base.port
            and not parsed.username
            and not parsed.password
        )
    except (TypeError, ValueError):
        return False


def private_profile(scope):
    """Create owner-only application storage while refusing symlinked or permissive managed directories."""
    if not isinstance(scope, str) or re.fullmatch(r"[a-f0-9]{64}", scope) is None:
        raise ValueError("invalid_desktop_profile")
    root = Path.home() / ".local/state/aevra"
    for path in (root, root / "desktop", root / "desktop" / scope):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if (
            path.is_symlink()
            or path.resolve() != path.absolute()
            or path.stat().st_uid != os.getuid()
            or path.stat().st_mode & 0o077
        ):
            raise ValueError("unsafe_desktop_profile")
    LOGGER.info("aevra_desktop_profile_ready")
    return root / "desktop" / scope


def dependencies():
    """Load only the operating system's supported GTK3/WebKit2 4.1 bindings when the native desktop is requested."""
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gio, GLib, Gtk, WebKit2

    return Gio, GLib, Gtk, WebKit2


@contextmanager
def lock_profile(profile):
    """Prevent concurrent WebKit processes from writing the same owner/origin device history."""
    descriptor = os.open(
        profile / "window.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
    )
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("desktop_profile_in_use") from None
        LOGGER.info("aevra_desktop_profile_locked")
        yield
    finally:
        os.close(descriptor)


def icon_path():
    """Verify the packaged Aevra application icon before presenting it in native window chrome."""
    root = ROOT / "apps/branding/assets"
    manifest = json.loads((root / "manifest.json").read_text())
    path = root / "icon.png"
    if (
        path.is_symlink()
        or hashlib.sha256(path.read_bytes()).hexdigest()
        != manifest["files"]["icon.png"]
    ):
        raise ValueError("brand_resource_changed")
    return path


def run(bootstrap):
    """Run one native application window with scoped device history and an ephemeral authenticated server session."""
    value = validate_bootstrap(bootstrap)
    profile = private_profile(value["profile"])
    Gio, GLib, Gtk, WebKit2 = dependencies()
    GLib.set_application_name("Aevra")
    GLib.set_prgname("aevra")
    initialized, _ = Gtk.init_check([])
    if not initialized:
        raise ValueError("desktop_display_unavailable")
    application = Gtk.Application(
        application_id=APPLICATION_ID, flags=Gio.ApplicationFlags.NON_UNIQUE
    )
    state = {"window": None, "view": None}

    def decide(view, decision, kind):
        """Keep all navigation inside this app's authenticated origin and reject popup windows."""
        if kind == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
            decision.ignore()
            LOGGER.warning("aevra_desktop_popup_denied")
            return True
        if kind == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            uri = decision.get_navigation_action().get_request().get_uri()
        elif kind == WebKit2.PolicyDecisionType.RESPONSE:
            uri = decision.get_response().get_uri()
            if not decision.is_mime_type_supported():
                decision.ignore()
                LOGGER.warning("aevra_desktop_download_denied")
                return True
        else:
            decision.ignore()
            return True
        if not allowed_uri(uri, value["url"]):
            decision.ignore()
            LOGGER.warning("aevra_desktop_navigation_denied")
            return True
        decision.use()
        return True

    def deny_permission(view, request):
        """Deny native-device permissions until a separately tested product flow is implemented."""
        request.deny()
        LOGGER.warning("aevra_desktop_permission_denied")
        return True

    def deny_download(context, download):
        """Prevent implicit downloads or filesystem writes initiated by page content."""
        download.cancel()
        LOGGER.warning("aevra_desktop_download_denied")

    def load_failed(view, event, uri, error):
        """Show a finite local error page without logging the pairing URL or underlying error details."""
        LOGGER.warning("aevra_desktop_page_load_failed")
        view.load_html(
            "<!doctype html><html><head><title>Aevra</title></head><body><h1>Aevra</h1><p>Không kết nối được giao diện. Đóng cửa sổ và mở lại Aevra.</p></body></html>",
            value["url"] + "/",
        )
        return True

    def create_window(app):
        """Create branded native chrome and an isolated WebKit context without embedding application secrets or APIs."""
        if state["window"] is not None:
            state["window"].present()
            return
        window = Gtk.ApplicationWindow(application=app, title="Aevra")
        window.set_default_size(1180, 820)
        window.set_icon_from_file(str(icon_path()))
        header = Gtk.HeaderBar(title="Aevra", show_close_button=True)
        logo = Gtk.Image.new_from_file(str(icon_path()))
        logo.set_pixel_size(28)
        from gi.repository import GdkPixbuf

        logo.set_from_pixbuf(
            GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon_path()), 28, 28, True)
        )
        header.pack_start(logo)
        window.set_titlebar(header)
        manager = WebKit2.WebsiteDataManager(
            base_data_directory=str(profile / "data"),
            base_cache_directory=str(profile / "cache"),
        )
        manager.set_persistent_credential_storage_enabled(False)
        manager.set_network_proxy_settings(WebKit2.NetworkProxyMode.NO_PROXY, None)
        context = WebKit2.WebContext.new_with_website_data_manager(manager)
        context.connect("download-started", deny_download)
        view = WebKit2.WebView.new_with_context(context)
        settings = view.get_settings()
        settings.set_enable_developer_extras(False)
        settings.set_enable_write_console_messages_to_stdout(False)
        settings.set_allow_file_access_from_file_urls(False)
        settings.set_allow_universal_access_from_file_urls(False)
        settings.set_javascript_can_open_windows_automatically(False)
        view.connect("decide-policy", decide)
        view.connect("permission-request", deny_permission)
        view.connect("load-failed", load_failed)
        window.add(view)
        state.update(window=window, view=view)
        view.load_uri(value["url"] + "/pair/#" + value["code"])
        window.show_all()
        LOGGER.info("aevra_desktop_window_opened")

    def activate(app):
        """Fail visibly and quit if native initialization cannot create a usable window."""
        try:
            create_window(app)
        except Exception:
            state["failed"] = True
            LOGGER.error("aevra_desktop_window_initialization_failed")
            for window in app.get_windows():
                window.destroy()
            app.quit()

    application.connect("activate", activate)
    with lock_profile(profile):
        result = application.run([])
    if state.get("failed") or state["view"] is None:
        raise ValueError("native_desktop_window_unavailable")
    LOGGER.info("aevra_desktop_window_closed")
    return result
