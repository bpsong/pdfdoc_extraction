"""Verify pipeline orchestration with synthetic results, without model downloads."""

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "invoice_pipeline_experiment", Path(__file__).with_name("extract_invoice_pipeline.py")
)
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)


def test_pipeline_exports_pages_and_consumes_merged_generator(tmp_path, monkeypatch) -> None:
    calls = []

    class Result:
        def save_to_json(self, save_path: str) -> None:
            calls.append(("json", Path(save_path).name))

        def save_to_markdown(self, save_path: str) -> None:
            calls.append(("markdown", Path(save_path).name))

    class Pipeline:
        def __init__(self, **kwargs) -> None:
            assert kwargs["pipeline_version"] == "v1.6"
            assert kwargs["device"] == "cpu"
            assert kwargs["use_queues"] is False
            assert kwargs["markdown_ignore_labels"] == []

        def predict(self, input: str):
            assert Path(input) == pdf
            yield Result()
            yield Result()

        def restructure_pages(self, pages, **kwargs):
            assert len(pages) == 2
            assert kwargs == {"merge_tables": True, "concatenate_pages": True}
            yield Result()

    monkeypatch.setattr(script.importlib, "import_module", lambda name:
                        SimpleNamespace(PaddleOCRVL=Pipeline, __version__="test"))
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"synthetic input; inference mocked")
    args = argparse.Namespace(pdf=pdf, output=tmp_path / "output", device="cpu",
                              orientation=False, unwarp=False, no_merge_tables=False)
    script.run(args)
    assert calls == [("json", "pages"), ("markdown", "pages")] * 2 + [
        ("json", "merged"), ("markdown", "merged")]
    assert json.loads((args.output / "run.json").read_text())["pages"] == 2


def test_invalid_input_fails_before_loading_models(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "invalid.txt"
    pdf.write_text("synthetic")
    monkeypatch.setattr(script.importlib, "import_module", lambda name:
                        pytest.fail("Must validate input before model imports"))
    with pytest.raises(ValueError, match="PDF"):
        script.run(argparse.Namespace(pdf=pdf))
