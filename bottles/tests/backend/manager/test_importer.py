from pathlib import Path
from types import SimpleNamespace

from bottles.backend.globals import Paths, TrdyPaths
from bottles.backend.managers.importer import ImportManager
from bottles.backend.models.result import Result


def _disable_default_locations(monkeypatch, tmp_path):
    monkeypatch.setattr(TrdyPaths, "wine", str(tmp_path / "missing-wine"))
    monkeypatch.setattr(TrdyPaths, "lutris", str(tmp_path / "missing-lutris"))
    monkeypatch.setattr(
        TrdyPaths,
        "playonlinux",
        str(tmp_path / "missing-playonlinux"),
    )


def test_search_wineprefixes_accepts_selected_root_or_prefix(tmp_path, monkeypatch):
    _disable_default_locations(monkeypatch, tmp_path)
    root = tmp_path / "PlayOnLinux [prefixes]"
    first = root / "First Prefix"
    first.joinpath("drive_c").mkdir(parents=True)
    direct = tmp_path / "Direct Prefix"
    direct.joinpath("drive_c").mkdir(parents=True)

    result = ImportManager.search_wineprefixes([str(root), str(direct)])

    assert result.status
    assert [
        (prefix["Name"], prefix["Manager"], Path(prefix["Path"]))
        for prefix in result.data["wineprefixes"]
    ] == [
        ("First Prefix", "Manual", first),
        ("Direct Prefix", "Manual", direct),
    ]


def test_foreign_prefix_copy_uses_exact_selected_target(tmp_path, monkeypatch):
    from bottles.backend.managers.storage import BottleIndex
    source = tmp_path / "Prefix With Spaces"
    source.joinpath("drive_c").mkdir(parents=True)
    source.joinpath(".registry").write_text("hidden")
    source.joinpath("dosdevices").mkdir()
    source.joinpath("dosdevices", "c:").symlink_to("../drive_c")
    destination = tmp_path / "selected"
    destination.mkdir()
    destination.chmod(0o750)
    manager = SimpleNamespace(get_default_runner=lambda: "system-wine", update_bottles=lambda **kw: None)
    result = ImportManager(manager).import_wineprefix(
        {"Name": "Office", "Path": str(source)}, str(destination),
    )
    assert result.ok
    assert destination.stat().st_mode & 0o777 == 0o750
    assert destination.joinpath(".registry").read_text() == "hidden"
    assert destination.joinpath("dosdevices", "c:").readlink() == Path("../drive_c")
    assert source.joinpath(".registry").read_text() == "hidden"
    assert not source.joinpath("bottle.lock").exists()
    assert not source.joinpath("bottle.yml").exists()
    assert BottleIndex().entries() == {str(destination): "Office"}


def test_foreign_prefix_cannot_overwrite_a_nonempty_target(tmp_path):
    source = tmp_path / "source"
    (source / "drive_c").mkdir(parents=True)
    destination = tmp_path / "selected"
    destination.mkdir()
    (destination / "keep").write_text("existing")
    importer = ImportManager(SimpleNamespace())
    result = importer.import_wineprefix({"Name": "Office", "Path": str(source)}, str(destination))
    assert not result.ok
    assert (destination / "keep").read_text() == "existing"
