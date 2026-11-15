"""Storage contracts: explicit locations, ownership, portability and read-only discovery."""

import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from bottles.backend.globals import Paths
from bottles.backend.managers.importer import ImportManager
from bottles.backend.managers.manager import Manager
from bottles.backend.managers.storage import BottleIndex, bottle_directory, bottle_operation
from bottles.backend.models.config import BottleConfig


@pytest.fixture
def bottle(tmp_path):
    root = tmp_path / "selected"
    root.mkdir(mode=0o700)
    (root / "drive_c").mkdir()
    assert BottleConfig(Name="Office", Runner="system-wine").dump(str(root / "bottle.yml")).ok
    return root


def test_new_directory_is_exactly_the_selected_empty_directory(tmp_path):
    root = tmp_path / "Wine"
    root.mkdir()
    assert bottle_directory(str(root), empty=True) == str(root)
    assert list(root.iterdir()) == []
    assert not (root / "Wine").exists()


@pytest.mark.parametrize("path", ["", "relative"])
def test_missing_or_relative_directory_is_an_error(path):
    with pytest.raises(ValueError, match="absolute"):
        bottle_directory(path, empty=True)


def test_nonempty_directory_is_not_reused_or_renamed(tmp_path):
    root = tmp_path / "Wine"
    root.mkdir()
    marker = root / "personal-file"
    marker.write_bytes(b"keep")
    with pytest.raises(ValueError, match="empty"):
        bottle_directory(str(root), empty=True)
    assert marker.read_bytes() == b"keep"
    assert list(tmp_path.iterdir()) == [root]


def test_import_requires_a_private_root_without_changing_permissions(bottle):
    bottle.chmod(0o755)
    with pytest.raises(PermissionError, match="private"):
        bottle_directory(str(bottle))
    assert bottle.stat().st_mode & 0o777 == 0o755


def test_foreign_owner_is_rejected(bottle, monkeypatch):
    from bottles.backend.managers import storage
    original = storage.os.stat
    def foreign_owner(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if str(path) == str(bottle):
            return SimpleNamespace(st_mode=info.st_mode, st_uid=os.getuid() + 1)
        return info
    monkeypatch.setattr(storage.os, "stat", foreign_owner)
    with pytest.raises(PermissionError, match="belong"):
        bottle_directory(str(bottle))


def test_register_is_in_place_and_forget_preserves_contents(bottle):
    before = {p.relative_to(bottle): p.read_bytes() for p in bottle.rglob("*") if p.is_file()}
    index = BottleIndex()
    config = index.register(str(bottle))
    assert config.Path == str(bottle)
    assert index.entries() == {str(bottle): "Office"}
    assert Path(Paths.bottle_index).stat().st_mode & 0o777 == 0o600
    index.forget(str(bottle))
    assert index.entries() == {}
    after = {p.relative_to(bottle): p.read_bytes() for p in bottle.rglob("*") if p.is_file()}
    assert after == before


def test_duplicate_registration_and_duplicate_names_are_errors(bottle, tmp_path):
    index = BottleIndex()
    index.register(str(bottle))
    with pytest.raises(sqlite3.IntegrityError):
        index.register(str(bottle))
    other = tmp_path / "other"
    other.mkdir(mode=0o700)
    (other / "drive_c").mkdir()
    assert BottleConfig(Name="Office").dump(str(other / "bottle.yml")).ok
    with pytest.raises(sqlite3.IntegrityError):
        index.register(str(other))
    assert index.entries() == {str(bottle): "Office"}


def test_register_rejects_invalid_config_without_registering(bottle):
    (bottle / "bottle.yml").write_text("Name: Office\nParameters: invalid\n")
    with pytest.raises(ValueError):
        BottleIndex().register(str(bottle))
    assert BottleIndex().entries() == {}


def test_import_does_not_run_wine_or_rewrite_the_bottle(bottle):
    refresh = []
    importer = ImportManager(SimpleNamespace(update_bottles=lambda **kw: refresh.append(kw)))
    config_path = bottle / "bottle.yml"
    before = config_path.read_bytes(), config_path.stat().st_mtime_ns
    result = importer.import_bottle(str(bottle))
    assert result.ok
    assert (config_path.read_bytes(), config_path.stat().st_mtime_ns) == before
    assert sorted(p.name for p in bottle.iterdir()) == ["bottle.yml", "drive_c"]
    assert refresh == [{"silent": True}]


def test_discovery_keeps_offline_registration_and_does_not_repair_configs(bottle, tmp_path):
    index = BottleIndex()
    index.register(str(bottle))
    moved = tmp_path / "moved"
    bottle.rename(moved)
    manager = object.__new__(Manager)
    manager.is_cli = True
    manager.settings = SimpleNamespace(get_boolean=lambda _key: False)
    manager.check_bottles()
    assert manager.local_bottles == {}
    assert str(bottle) in manager.unavailable_bottles
    assert index.entries() == {str(bottle): "Office"}
    index.forget(str(bottle))
    index.register(str(moved))
    before = (moved / "bottle.yml").stat().st_mtime_ns
    manager.check_bottles()
    assert manager.local_bottles["Office"].Path == str(moved)
    assert (moved / "bottle.yml").stat().st_mtime_ns == before
    assert sorted(p.name for p in moved.iterdir()) == ["bottle.yml", "drive_c"]


def test_operations_exclude_other_callers_without_leaving_lock_files(tmp_path):
    with bottle_operation(str(tmp_path)):
        with pytest.raises(RuntimeError, match="Another"):
            with bottle_operation(str(tmp_path)):
                pytest.fail("the second operation acquired an exclusive lock")
    with bottle_operation(str(tmp_path)):
        assert list(tmp_path.iterdir()) == []


def test_each_user_index_is_independent(bottle, tmp_path, monkeypatch):
    first = str(tmp_path / "first/bottles.sqlite")
    second = str(tmp_path / "second/bottles.sqlite")
    monkeypatch.setattr(Paths, "bottle_index", first)
    BottleIndex().register(str(bottle))
    monkeypatch.setattr(Paths, "bottle_index", second)
    assert BottleIndex().entries() == {}
    assert not Path(second).exists()
    monkeypatch.setattr(Paths, "bottle_index", first)
    assert BottleIndex().entries() == {str(bottle): "Office"}


def test_runtime_history_is_per_bottle_and_is_opened_lazily(bottle, tmp_path):
    import threading
    from bottles.backend.utils.gsettings_stub import GSettingsStub
    index = BottleIndex()
    index.register(str(bottle))
    second = tmp_path / "second"
    second.mkdir(mode=0o700)
    (second / "drive_c").mkdir()
    assert BottleConfig(Name="Viewer").dump(str(second / "bottle.yml")).ok
    index.register(str(second))
    manager = object.__new__(Manager)
    manager.settings = GSettingsStub()
    manager.is_cli = True
    manager._playtime_trackers = {}
    manager._playtime_lock = threading.RLock()
    manager.check_bottles()
    assert not (bottle / "process_metrics.sqlite").exists()
    assert not (second / "process_metrics.sqlite").exists()
    first = manager.get_playtime_tracker(manager.local_bottles["Office"].identifier)
    other = manager.get_playtime_tracker(manager.local_bottles["Viewer"].identifier)
    try:
        assert first.db_path == str(bottle / "process_metrics.sqlite")
        assert other.db_path == str(second / "process_metrics.sqlite")
        assert first is manager.get_playtime_tracker(manager.local_bottles["Office"].identifier)
        assert first is not other
        assert Path(first.db_path).stat().st_mode & 0o777 == 0o600
    finally:
        first.shutdown()
        other.shutdown()


def test_failed_import_reports_error_without_refreshing_or_registering(bottle):
    refresh = []
    (bottle / "bottle.yml").write_text("Name: [broken\n")
    importer = ImportManager(SimpleNamespace(update_bottles=lambda **kw: refresh.append(kw)))
    result = importer.import_bottle(str(bottle))
    assert not result.ok
    assert result.message
    assert refresh == []
    assert BottleIndex().entries() == {}


def test_forgetting_an_unavailable_bottle_does_not_need_its_directory(bottle, tmp_path):
    index = BottleIndex()
    index.register(str(bottle))
    moved = tmp_path / "unmounted-copy"
    bottle.rename(moved)
    index.forget(str(bottle))
    assert index.entries() == {}
    assert (moved / "bottle.yml").is_file()


def test_library_records_move_with_the_bottle(bottle, tmp_path, monkeypatch):
    from bottles.backend.managers.library import LibraryManager
    from bottles.backend.managers.steamgriddb import SteamGridDBManager
    index = BottleIndex()
    config = index.register(str(bottle))
    monkeypatch.setattr(SteamGridDBManager, "get_game_grid", lambda *_args: None)
    library = LibraryManager()
    key = library.add_to_library({"name": "Editor", "id": "editor"}, config)
    from bottles.backend.utils import yaml
    saved = yaml.load((bottle / "library.yml").read_text())
    assert saved[key]["name"] == "Editor"
    assert "bottle" not in saved[key]
    moved = tmp_path / "moved"
    bottle.rename(moved)
    index.forget(str(bottle))
    index.register(str(moved))
    loaded = LibraryManager().get_library()[key]
    assert loaded["bottle"] == {"name": "Office", "path": str(moved)}
    assert loaded["id"] == "editor"


def test_identity_survives_name_change_and_cannot_be_registered_twice(bottle, tmp_path):
    import shutil
    index = BottleIndex()
    config = index.register(str(bottle))
    original = config.identifier
    config.Name = "Renamed"
    assert config.dump(str(bottle / "bottle.yml")).ok
    index.rename(str(bottle), config.Name)
    assert BottleConfig.load(str(bottle / "bottle.yml")).data.identifier == original
    copy = tmp_path / "manual-copy"
    shutil.copytree(bottle, copy)
    config.Name = "Copy"
    assert config.dump(str(copy / "bottle.yml")).ok
    with pytest.raises(sqlite3.IntegrityError):
        index.register(str(copy))
    assert index.entries() == {str(bottle): "Renamed"}


def test_copy_rejects_a_destination_inside_the_source(bottle):
    from bottles.backend.managers.storage import copy_bottle_contents
    destination = bottle / "nested"
    destination.mkdir()
    with pytest.raises(ValueError, match="outside"):
        copy_bottle_contents(str(bottle), str(destination))
    assert list(destination.iterdir()) == []
