"""Lightweight validation checks without downloading or loading TeleOCR."""

import argparse
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "teleocr_experiment", Path(__file__).with_name("extract_invoice_teleocr.py")
)
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)


def test_invalid_rendering_settings_fail_before_model_loading() -> None:
    with pytest.raises(ValueError, match="positive"):
        script.run(argparse.Namespace(dpi=0, max_pixels=1000, max_tokens=100))


def test_prompt_uses_separate_image_and_text_content() -> None:
    messages = script.build_messages("Recognize")
    assert messages[1]["content"] == [{"type": "image"}, {"type": "text", "text": "Recognize"}]


def test_repetition_loop_is_rejected_but_normal_invoice_is_accepted() -> None:
    assert script.has_repetition("#36258\nSeattle\n" * 20)
    assert not script.has_repetition("Invoice 1\nChair\n1\n48.71\n48.71\nTotal 50.10")
