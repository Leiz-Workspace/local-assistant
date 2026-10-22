"""Protect D63 visual answer association, missing-field abstention and complete unsupported-number rejection."""

import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.generate_vision_goldens import generate
from tests.vision_image_goldens import golden_match

CASES = json.loads(Path("tests/fixtures/vision/d63-cases.json").read_text())["cases"]


@pytest.mark.parametrize(
    "index,answer,uncertainties",
    [
        (0, "February: 30", ()),
        (1, "April is not shown.", ("April absent.",)),
        (2, "Số lượng: 5; Đơn giá: 18000 VND", ()),
        (2, "**Số lượng:** 5; **Đơn giá:** 18,000 VND", ()),
        (3, "Release: 2.4; Files: 12", ()),
        (3, "**Release:** 2.4; **File count:** 12", ()),
    ],
)
def test_declared_visual_answers_preserve_field_association_and_supported_numbers(
    index, answer, uncertainties
):
    """Accept visible facts, ordinary Markdown/grouping and an explicitly uncertain absent period."""
    assert golden_match(CASES[index], answer, uncertainties)


@pytest.mark.parametrize(
    "index,answer,uncertainties",
    [
        (0, "January: 30", ()),
        (0, "February: 20", ()),
        (0, "February: 30; March: 20", ()),
        (0, "February: 30; additional total 900", ()),
        (1, "April: 15", ("Estimated.",)),
        (1, "April not shown, perhaps 15", ("Unknown.",)),
        (1, "April not shown.", ()),
        (1, "February: 30", ("April absent.",)),
        (2, "Số lượng: 3; Đơn giá: 12000", ()),
        (2, "Số lượng: 18000; Đơn giá: 5", ()),
        (2, "Số lượng: 5; Đơn giá: 18000; Bút: 3", ()),
        (2, "5 and 18000", ()),
        (3, "Release: 12; Files: 2.4", ()),
        (3, "Release: 2.4; Files: 12; snapshot: 17", ()),
        (3, "Release: 2.5; Files: 12", ()),
        (3, "2.4 and 12", ()),
    ],
)
def test_wrong_associations_guesses_and_unsupported_tail_numbers_remain_failures(
    index, answer, uncertainties
):
    """Reject unrelated correct tokens, swapped values and missing uncertainty without trimming the answer tail."""
    assert not golden_match(CASES[index], answer, uncertainties)


def test_authored_generator_reproduces_all_three_complete_frozen_images(tmp_path):
    """Regenerate public fixture bytes exactly and verify their declared RGB layout without external input."""
    generate(tmp_path)
    for name, dimensions in [
        ("chart.png", (960, 640)),
        ("table.png", (1000, 440)),
        ("document.png", (1000, 620)),
    ]:
        assert (tmp_path / name).read_bytes() == (
            Path("tests/fixtures/vision/d63") / name
        ).read_bytes()
        with Image.open(tmp_path / name) as image:
            assert image.mode == "RGB" and image.size == dimensions


def test_whole_answer_scoring_logs_only_finite_outcome(caplog):
    """Keep complete authored/private answer content outside routine scorer audit logs."""
    caplog.set_level("INFO")
    assert not golden_match(CASES[0], "PRIVATE-ANSWER-CANARY 900", ())
    assert "PRIVATE-ANSWER-CANARY" not in caplog.text
    assert "image_golden_scored passed=False" in caplog.text
