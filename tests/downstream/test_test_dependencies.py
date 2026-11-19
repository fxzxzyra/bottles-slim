"""Dependency diagnostics without importing the application or requiring native UI libraries."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

SPEC = importlib.util.spec_from_file_location(
    "test_entry_point", Path(__file__).resolve().parents[2] / "tests/run.py"
)
entry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(entry)


def test_preflight_reports_python_and_gi_failures_together(monkeypatch):
    def require(namespace, version):
        if namespace == "GtkSource":
            raise ValueError("Namespace GtkSource not available")

    def load(name):
        if name == "yaml":
            raise ModuleNotFoundError("No module named 'yaml'")
        if name == "pycurl":
            raise ImportError("libcurl.so unavailable")
        if name == "gi":
            return SimpleNamespace(require_version=require)
        if name in ("gi.repository.Gtk", "gi.repository.Adw"):
            major = 4 if name.endswith("Gtk") else 1
            return SimpleNamespace(get_major_version=lambda: major, get_minor_version=lambda: 99)
        return SimpleNamespace()

    monkeypatch.setattr(entry.importlib, "import_module", load)
    problems = entry.check_dependencies()
    assert len(problems) == 3
    assert any("PyYAML (import yaml)" in item for item in problems)
    assert any("pycurl" in item and "libcurl.so" in item for item in problems)
    assert any("GI GtkSource-5" in item for item in problems)


def test_preflight_still_lists_all_python_failures_without_pygobject(monkeypatch):
    def load(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(entry.importlib, "import_module", load)
    problems = entry.check_dependencies()
    assert len(problems) == len(entry.PYTHON_DEPENDENCIES)
    assert any("PyGObject" in item for item in problems)
    assert any("pytest-mock" in item for item in problems)



def test_schema_preflight_reports_missing_id_without_constructing_settings():
    import os
    import pytest

    directory = Path(os.environ["GSETTINGS_SCHEMA_DIR"])
    from bottles.frontend.params import APP_ID

    assert entry.check_settings_schema(APP_ID, directory) is not None
    with pytest.raises(RuntimeError, match="is absent from"):
        entry.check_settings_schema("invalid.bottles.test.schema", directory)


def test_preflight_rejects_outdated_ui_libraries(monkeypatch):
    def load(name):
        if name == "gi":
            return SimpleNamespace(require_version=lambda *_args: None)
        if name == "gi.repository.Gtk":
            return SimpleNamespace(get_major_version=lambda: 4, get_minor_version=lambda: 8)
        if name == "gi.repository.Adw":
            return SimpleNamespace(get_major_version=lambda: 1, get_minor_version=lambda: 4)
        return SimpleNamespace()

    monkeypatch.setattr(entry.importlib, "import_module", load)
    assert entry.check_dependencies() == [
        "GI Gtk requires >= 4.10, found 4.8",
        "GI Adw requires >= 1.7, found 1.4",
    ]
