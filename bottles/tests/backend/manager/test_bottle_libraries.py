"""Libraries and cover files belong to each registered bottle, not global app data."""

import pytest

from bottles.backend.globals import Paths
from bottles.backend.managers.library import LibraryManager
from bottles.backend.managers.storage import BottleIndex
from bottles.backend.managers.steamgriddb import SteamGridDBManager
from bottles.backend.models.config import BottleConfig
from bottles.backend.utils import yaml


@pytest.fixture
def registered_bottle(tmp_path):
    path = tmp_path / "Office"
    path.mkdir(mode=0o700)
    (path / "drive_c").mkdir()
    config = BottleConfig(Name="Office", Path=str(path))
    assert config.dump(str(path / "bottle.yml")).ok
    BottleIndex().register(str(path))
    return config, path


def test_library_refresh_preserves_prefix_and_cover_files(registered_bottle):
    config, path = registered_bottle
    (path / "grids").mkdir()
    cover = path / "grids/cover.png"
    cover.write_bytes(b"cover")
    data = {"entry": {"name": "Writer", "id": "writer", "thumbnail": "grid:cover.png"}}
    (path / "library.yml").write_text(yaml.dump(data))
    manager = LibraryManager()
    manager.load_library()
    manager.save_library()
    assert cover.read_bytes() == b"cover"
    assert (path / "bottle.yml").is_file()
    assert yaml.load((path / "library.yml").read_text()) == data
    assert manager.get_library()["entry"]["bottle"] == {"name": config.Name, "path": str(path)}


def test_bottle_library_roundtrips_and_deduplicates(registered_bottle, monkeypatch):
    config, path = registered_bottle
    monkeypatch.setattr(SteamGridDBManager, "get_game_grid", lambda *_args: None)
    entry = {"name": "Writer", "id": "writer"}
    first = LibraryManager()
    identifier = first.add_to_library(entry, config)
    assert identifier
    second = LibraryManager()
    assert second.add_to_library(dict(entry), config) is None
    assert len(second.get_library()) == 1
    assert second.get_library()[identifier]["id"] == "writer"
    stored = yaml.load((path / "library.yml").read_text())
    assert stored[identifier]["id"] == "writer"
    assert "bottle" not in stored[identifier]
    assert (path / "library.yml").stat().st_mode & 0o777 == 0o600


def test_global_library_is_neither_read_nor_modified(registered_bottle, tmp_path, monkeypatch):
    _config, path = registered_bottle
    global_data = tmp_path / "app-data"
    global_data.mkdir()
    global_file = global_data / "library.yml"
    sentinel = b"old file remains untouched: [invalid YAML"
    global_file.write_bytes(sentinel)
    monkeypatch.setattr(Paths, "base", str(global_data))
    manager = LibraryManager()
    assert manager.get_library() == {}
    manager.save_library()
    assert global_file.read_bytes() == sentinel
    assert not (path / "library.yml").exists()


def test_same_program_id_in_two_bottles_is_not_a_duplicate(registered_bottle, tmp_path, monkeypatch):
    first_config, first_path = registered_bottle
    second_path = tmp_path / "Other"
    second_path.mkdir(mode=0o700)
    (second_path / "drive_c").mkdir()
    second_config = BottleConfig(Name="Other", Path=str(second_path))
    assert second_config.dump(str(second_path / "bottle.yml")).ok
    BottleIndex().register(str(second_path))
    monkeypatch.setattr(SteamGridDBManager, "get_game_grid", lambda *_args: None)
    manager = LibraryManager()
    first_id = manager.add_to_library({"name": "Writer", "id": "writer"}, first_config)
    second_id = manager.add_to_library({"name": "Writer", "id": "writer"}, second_config)
    assert first_id and second_id and first_id != second_id
    entries = LibraryManager().get_library()
    assert {entry["bottle"]["path"] for entry in entries.values()} == {str(first_path), str(second_path)}
    assert set(yaml.load((first_path / "library.yml").read_text())) == {first_id}
    assert set(yaml.load((second_path / "library.yml").read_text())) == {second_id}
