"""Exclude the frozen HAR-006 v2 design tests at HEAD and reset the process-wide model binding per test."""

import pytest

from benchmarks.tests import har006_v2_pin as pin
from src.application.services.special_literals import reset_binding_for_tests


@pytest.fixture(autouse=True)
def unrecorded_special_literal_binding():
    """Start and end every test unrecorded, because application startup records the model binding process-wide."""
    reset_binding_for_tests()
    yield
    reset_binding_for_tests()


@pytest.fixture(autouse=True)
def warmed_v2_calibration(request):
    """Fill v2's cached calibration outside the event loop before an async test that reads it."""
    if (
        request.node.path.name == pin.MODULE
        and request.node.name in pin.WARM_CALIBRATION
    ):
        request.module.calibration()


def pytest_collection_modifyitems(config, items):
    """Skip exactly the pinned v2 tests while any v2 source differs from the recorded commit."""
    changed = pin.changed_sources()
    if not changed:
        return
    module = [item for item in items if item.path.name == pin.MODULE]
    marker = pytest.mark.skip(
        reason=f"{pin.REASON}; v2 sources changed: {len(changed)}"
    )
    marked = 0
    for item in module:
        if item.name in pin.PINNED:
            item.add_marker(marker)
            marked += 1
    if len(module) == pin.MODULE_TESTS and marked != len(pin.PINNED):
        raise pytest.UsageError("har006_v2_pin_mismatch")
