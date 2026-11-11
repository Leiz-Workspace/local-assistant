"""Verify native smoke orchestration and failure cleanup without a display, browser or model dependency."""

import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from benchmarks import aevra_desktop_smoke as smoke


def install_native_doubles(monkeypatch, fail=False):
    """Supply a deterministic native event loop that checks the smoke submits once and always closes its own window."""
    state = dict(sent=False, closed=False, focused=True, timer=None)

    class View:
        """Return controlled DOM observations through the same asynchronous callback interface as WebKit."""

        def evaluate_javascript(
            self, script, length, world, uri, cancel, callback, data
        ):
            """Distinguish the one synthetic submit from recurring read-only UI inspections."""
            submit = script.startswith("(() =>")
            if submit:
                assert not state["sent"]
                state["sent"] = True
            callback(self, submit, data)

        def evaluate_javascript_finish(self, result):
            """Return a WebKit-shaped scalar or fail the controlled DOM observation explicitly."""
            if fail:
                raise ValueError("fixture_failure")
            row = dict(
                title="Aevra",
                brand=True,
                logo="/aevra/brand/logo.svg",
                sidebar_logo=True,
                textarea=True,
                editable=False,
                fixture=state["sent"],
            )
            return SimpleNamespace(
                to_string=lambda: json.dumps(row), to_boolean=lambda: True
            )

    view = View()

    class Window:
        """Expose only the smoke-owned native window and its lifecycle state."""

        def get_title(self):
            """Identify the Aevra window without searching any external application."""
            return "Aevra"

        def get_child(self):
            """Return the controlled WebKit view."""
            return view

        def destroy(self):
            """Close the controlled window exactly as native smoke cleanup would."""
            state["closed"] = True

        def show_all(self):
            """Stand in for native presentation while allowing the no-focus wrapper to execute."""

        def set_accept_focus(self, enabled):
            """Record the nonintrusive QA presentation flag."""
            state["focused"] = enabled

        def set_focus_on_map(self, enabled):
            """Record that mapping does not steal the user's active keyboard focus."""
            assert enabled is False

        def get_window(self):
            """Return no actual display object in software-only tests."""
            return None

        def get_allocated_width(self):
            """Expose a deterministic capture width."""
            return 100

        def get_allocated_height(self):
            """Expose a deterministic capture height."""
            return 100

    window = Window()

    def timeout_add(interval, callback):
        """Schedule the finite test loop without sleeping or allocating a thread."""
        state["timer"] = callback

    def idle_add(callback):
        """Run owned-window cleanup immediately in this deterministic event loop."""
        return callback()

    def run(bootstrap):
        """Execute the actual smoke callbacks until their owned window is closed."""
        window.show_all()
        for _ in range(4):
            state["timer"]()
            if state["closed"]:
                return 0
        pytest.fail("Smoke failed to close its window")

    gtk = SimpleNamespace(
        ApplicationWindow=Window,
        Window=SimpleNamespace(
            list_toplevels=lambda: [] if state["closed"] else [window]
        ),
    )
    glib = SimpleNamespace(timeout_add=timeout_add, idle_add=idle_add)
    repository = ModuleType("gi.repository")
    repository.Gdk = SimpleNamespace(pixbuf_get_from_window=lambda *args: None)
    monkeypatch.setitem(sys.modules, "gi", ModuleType("gi"))
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    monkeypatch.setattr(
        smoke.runtime,
        "dependencies",
        lambda: (None, glib, gtk, SimpleNamespace(WebView=View)),
    )
    monkeypatch.setattr(smoke.runtime, "run", run)
    return state, Window.show_all


@pytest.mark.parametrize("fail", [False, True])
def test_native_smoke_is_bounded_and_restores_window_methods(
    tmp_path, monkeypatch, fail
):
    """Preserve first success/failure metadata, submit at most once, avoid focus theft and close the owned window."""
    state, original = install_native_doubles(monkeypatch, fail)
    output = tmp_path / "native"
    result = smoke.probe({}, output)
    assert state["closed"] and not state["focused"]
    assert result["model_calls"] == 0 and result["synthetic_backend"]
    assert result["ready"] is (not fail)
    assert result["error"] == ("native_dom_inspection_failed" if fail else None)
    assert json.loads((output / "summary.json").read_text()) == result
    assert smoke.runtime.dependencies()[2].ApplicationWindow.show_all is original
    with pytest.raises(FileExistsError):
        smoke.probe({}, output)
