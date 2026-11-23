"""Exercise the actual native Aevra window against an explicitly synthetic backend without running any model."""

import argparse
import json
import logging
import os
from pathlib import Path
import time

from apps.desktop import runtime

LOGGER = logging.getLogger(__name__)


def probe(bootstrap, output, timeout=25):
    """Inspect native WebKit DOM, capture only this owned app window and close it after a bounded smoke test."""
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _, GLib, Gtk, WebKit2 = runtime.dependencies()
    from gi.repository import Gdk

    state = dict(
        ready=False, pending=False, observations=[], error=None, chat_sent=False
    )
    deadline = time.monotonic() + timeout
    script = """JSON.stringify({title:document.title,brand:!!document.getElementById('aevra-brand'),logo:document.querySelector('#aevra-brand img')?.getAttribute('src'),textarea:!!document.querySelector('textarea'),editable:!!document.querySelector('[contenteditable=true]'),buttons:Array.from(document.querySelectorAll('button')).map(b=>({label:b.getAttribute('aria-label'),title:b.title,text:b.innerText.slice(0,50)})).slice(-20),sidebar_logo:Array.from(document.querySelectorAll('button[aria-label=\"Expand navigation\"],button[aria-label=\"Collapse navigation\"]')).some(b=>getComputedStyle(b).backgroundImage.includes('/aevra/brand/icon.svg')),fixture:document.body.innerText.includes('fixture')})"""

    def close_window():
        """Close only windows created inside this native smoke process."""
        for window in Gtk.Window.list_toplevels():
            window.destroy()
        return False

    def submitted(view, result, data):
        """Check only that one synthetic input was submitted, without generating a second request on failure."""
        try:
            if not view.evaluate_javascript_finish(result).to_boolean():
                raise ValueError
        except Exception:
            state["error"] = "native_synthetic_submit_failed"
            GLib.idle_add(close_window)

    def inspected(view, result, window):
        """Retain redacted UI mechanics rather than raw cookies, nonce URLs or actual conversation data."""
        state["pending"] = False
        try:
            observed = json.loads(view.evaluate_javascript_finish(result).to_string())
            state["observations"].append(observed)
            if (
                observed["brand"]
                and "Aevra" in observed["title"]
                and observed["logo"] == "/aevra/brand/logo.svg"
                and observed["sidebar_logo"]
                and (observed["textarea"] or observed["editable"])
            ):
                if not state["chat_sent"]:
                    state["chat_sent"] = True
                    submit = """(() => {const input=document.querySelector('textarea');if(!input)return false;input.value='Aevra synthetic smoke';input.dispatchEvent(new Event('input',{bubbles:true}));setTimeout(()=>{const send=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Send');if(send)send.click();},150);return true;})()"""
                    view.evaluate_javascript(
                        submit, -1, None, None, None, submitted, None
                    )
                    return
                if not observed["fixture"]:
                    return
                state["ready"] = True
                pixbuf = Gdk.pixbuf_get_from_window(
                    window.get_window(),
                    0,
                    0,
                    window.get_allocated_width(),
                    window.get_allocated_height(),
                )
                if pixbuf is not None:
                    pixbuf.savev(str(output / "native-window.png"), "png", [], [])
                GLib.idle_add(close_window)
        except Exception:
            state["error"] = "native_dom_inspection_failed"
            GLib.idle_add(close_window)

    def inspect():
        """Poll only this application's loaded native view with a fixed deadline and no hidden retries of inference."""
        windows = [
            window
            for window in Gtk.Window.list_toplevels()
            if window.get_title() == "Aevra"
        ]
        if time.monotonic() >= deadline:
            state["error"] = "native_smoke_timeout"
            close_window()
            return False
        if windows and not state["pending"]:
            window = windows[0]
            view = window.get_child()
            if isinstance(view, WebKit2.WebView):
                state["pending"] = True
                view.evaluate_javascript(
                    script, -1, None, None, None, inspected, window
                )
        return not state["ready"]

    original_show = Gtk.ApplicationWindow.show_all

    def show_without_focus(window):
        """Keep QA from stealing keyboard focus or accepting unrelated input on the owner's desktop."""
        window.set_accept_focus(False)
        window.set_focus_on_map(False)
        original_show(window)

    Gtk.ApplicationWindow.show_all = show_without_focus
    try:
        GLib.timeout_add(500, inspect)
        code = runtime.run(bootstrap)
    finally:
        Gtk.ApplicationWindow.show_all = original_show
    result = dict(
        schema_version=1,
        product="Aevra",
        renderer="webkitgtk-4.1",
        external_browser=False,
        synthetic_backend=True,
        model_calls=0,
        synthetic_chat_submitted=state["chat_sent"],
        native_exit_code=code,
        ready=state["ready"],
        error=state["error"],
        observations=state["observations"],
    )
    descriptor = os.open(
        output / "summary.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
    )
    with os.fdopen(descriptor, "w") as stream:
        json.dump(result, stream, indent=2)
    LOGGER.info("aevra_native_smoke_finished ready=%s", state["ready"])
    return result


def main():
    """Consume a private one-use bootstrap file and emit only a safe native smoke status."""
    parser = argparse.ArgumentParser(description="Aevra synthetic-backend native smoke")
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = probe(
        runtime.validate_bootstrap(json.loads(args.bootstrap.read_bytes())), args.output
    )
    print(
        json.dumps(
            dict(
                ready=result["ready"],
                error=result["error"],
                native_exit_code=result["native_exit_code"],
            )
        )
    )
    return (
        0
        if result["ready"]
        and result["error"] is None
        and result["native_exit_code"] == 0
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
