"""Error-path and file-path coverage for the YAML parser."""

from __future__ import annotations

from pathlib import Path
import builtins
from unittest.mock import Mock, patch

import pytest
import ruamel.yaml

from tools.config_check.yaml_parser import YAMLParser


def test_pyyaml_file_load_success_empty_root_and_non_mapping(tmp_path: Path) -> None:
    parser = YAMLParser(prefer_ruamel=False)
    valid = tmp_path / "valid.yaml"
    valid.write_text("value: 1\n", encoding="utf-8")
    assert parser.load(valid)[0] == {"value": 1}

    empty = tmp_path / "empty.yaml"
    empty.write_text("# comment\n", encoding="utf-8")
    assert "empty" in (parser.load(empty)[1] or "")

    sequence = tmp_path / "sequence.yaml"
    sequence.write_text("- value\n", encoding="utf-8")
    assert "must be a mapping" in (parser.load(sequence)[1] or "")


def test_pyyaml_file_load_reports_yaml_and_io_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parser = YAMLParser(prefer_ruamel=False)
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("value: [\n", encoding="utf-8")
    assert "YAML parse error" in (parser.load(invalid)[1] or "")

    with patch.object(parser, "_load_with_pyyaml", side_effect=OSError("bad path")):
        data, error = parser.load("anything.yaml")
    assert data is None
    assert "Failed to read file" in (error or "")


def test_pyyaml_string_parser_covers_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = YAMLParser(prefer_ruamel=False)
    assert parser.loads("a: 1")[0] == {"a": 1}
    assert "empty" in (parser.loads("# only comments")[1] or "")
    assert "must be a mapping" in (parser.loads("- one")[1] or "")
    assert "YAML parse error" in (parser.loads("a: [")[1] or "")

    import yaml

    monkeypatch.setattr(yaml, "safe_load", lambda _stream: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "Error parsing YAML" in (parser.loads("a: 1")[1] or "")


def test_ruamel_parser_errors_and_non_mapping_fallback(tmp_path: Path) -> None:
    parser = YAMLParser()
    assert parser._use_ruamel is True

    class Loader:
        def __init__(self, value):
            self.value = value

        def load(self, _stream):
            if isinstance(self.value, BaseException):
                raise self.value
            return self.value

    parser._yaml_loader = Loader(ruamel.yaml.YAMLError("bad yaml"))
    assert "YAML parse error" in (parser.loads("bad", "source")[1] or "")

    parser._yaml_loader = Loader(RuntimeError("boom"))
    assert "Error parsing YAML" in (parser.loads("bad", "source")[1] or "")

    parser._yaml_loader = Loader(["not", "mapping"])
    assert "must be a mapping" in (parser.loads("list", "source")[1] or "")

    valid = tmp_path / "valid.yaml"
    valid.write_text("value: 1\n", encoding="utf-8")
    parser._yaml_loader = Loader({"value": 1})
    assert parser.load(valid)[0] == {"value": 1}


def test_ruamel_file_non_mapping_reparse_error(tmp_path: Path) -> None:
    parser = YAMLParser()
    parser._yaml_loader = type("Loader", (), {"load": lambda self, _stream: ["bad"]})()
    path = tmp_path / "list.yaml"
    path.write_text("- bad\n", encoding="utf-8")
    data, error = parser.load(path)
    assert data is None
    assert "must be a mapping" in (error or "")


def test_parser_initialization_failure_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = YAMLParser.__new__(YAMLParser)
    parser.prefer_ruamel = False
    parser._yaml_loader = None
    parser._use_ruamel = False
    monkeypatch.setitem(__import__("sys").modules, "yaml", None)
    with pytest.raises(ImportError, match="Neither ruamel.yaml"):
        parser._init_pyyaml()


def test_yaml_parser_fallback_and_exception_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parser = YAMLParser.__new__(YAMLParser)
    parser.prefer_ruamel = True
    parser._yaml_loader = None
    parser._use_ruamel = False
    original_import = builtins.__import__

    def fail_ruamel(name, *args, **kwargs):
        if name.startswith("ruamel"):
            raise ImportError("ruamel unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_ruamel)
    parser._init_ruamel()
    assert parser._use_ruamel is False

    parser._use_ruamel = False
    parser._load_with_pyyaml = lambda _path: (_ for _ in ()).throw(RuntimeError("outer"))
    parser._loads_with_pyyaml = lambda _content, _source: (_ for _ in ()).throw(RuntimeError("outer"))
    assert "Failed to parse YAML" in (parser.loads("x: 1")[1] or "")

    monkeypatch.setattr(builtins, "__import__", original_import)

    parser._yaml_loader = type("EmptyLoader", (), {"load": lambda self, _stream: None})()
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    assert "empty" in (parser._load_with_ruamel(str(path))[1] or "")
    parser._yaml_loader = type("ListLoader", (), {"load": lambda self, _stream: ["bad"]})()
    monkeypatch.setattr(parser, "_loads_with_ruamel", Mock(side_effect=RuntimeError("reparse")))
    assert "must be a mapping" in (parser._load_with_ruamel(str(path))[1] or "")
    parser._load_with_pyyaml = YAMLParser._load_with_pyyaml.__get__(parser, YAMLParser)
    parser._loads_with_ruamel = YAMLParser._loads_with_ruamel.__get__(parser, YAMLParser)

    monkeypatch.setattr(builtins, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("read")))
    parser._yaml_loader = type("Loader", (), {"load": lambda self, _stream: {}})()
    assert "Error reading" in (parser._load_with_ruamel(str(path))[1] or "")
    assert "Error reading" in (parser._load_with_pyyaml(str(path))[1] or "")
    parser._yaml_loader = type("StringLoader", (), {"load": lambda self, _stream: None})()
    assert "empty" in (parser._loads_with_ruamel("", "source")[1] or "")
    parser._yaml_loader = type("StringMappingLoader", (), {"load": lambda self, _stream: {"value": 1}})()
    assert parser._loads_with_ruamel("value: 1", "source")[0]["value"] == 1


def test_yaml_parser_remaining_ruamel_file_and_string_paths(tmp_path: Path) -> None:
    parser = YAMLParser()
    path = tmp_path / "invalid.yaml"
    path.write_text("value: 1\n", encoding="utf-8")

    parser._yaml_loader = type(
        "YamlErrorLoader",
        (),
        {"load": lambda self, _stream: (_ for _ in ()).throw(ruamel.yaml.YAMLError("bad"))},
    )()
    assert "YAML parse error" in (parser._load_with_ruamel(str(path))[1] or "")

    parser._yaml_loader = type("EmptyLoader", (), {"load": lambda self, _stream: None})()
    assert "empty" in (parser._loads_with_ruamel("", "source")[1] or "")
    parser._yaml_loader = type("MappingLoader", (), {"load": lambda self, _stream: {"value": 1}})()
    assert parser._loads_with_ruamel("value: 1", "source")[0] == {"value": 1}
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportOptionalSubscript=false
