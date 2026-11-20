import os

from bottles.backend.models.config import BottleConfig
from bottles.backend.wine.drives import Drives


def test_device_backed_drive_is_ejectable(tmp_path):
    dosdevices = tmp_path / "dosdevices"
    dosdevices.mkdir()
    (dosdevices / "d:").symlink_to(tmp_path)
    (dosdevices / "d::").symlink_to("/dev/sr0")
    config = BottleConfig(Path=str(tmp_path))
    drives = Drives(config)

    assert drives.is_ejectable("D") is True
    assert drives.is_ejectable("E:") is False


def test_set_drive_path_replaces_broken_symlink(tmp_path):
    bottle_path = tmp_path / "bottle"
    dosdevices_path = bottle_path / "dosdevices"
    dosdevices_path.mkdir(parents=True)
    drive_path = dosdevices_path / "h:"
    drive_path.symlink_to("/missing/portal/path", target_is_directory=True)

    config = BottleConfig(
        Name="Test",
        Path=str(bottle_path),
    )

    Drives(config).set_drive_path("H", "/home/test/Games")

    assert drive_path.is_symlink()
    assert os.readlink(drive_path) == "/home/test/Games"


def test_drive_mappings_exclude_wine_device_links_and_reflect_external_removal(tmp_path):
    devices = tmp_path / "dosdevices"
    devices.mkdir()
    (devices / "d:").symlink_to("../../disc")
    (devices / "d::").symlink_to("/dev/sr0")
    (devices / "e::").symlink_to("/dev/sr1")
    (devices / "x").symlink_to("/unrelated")
    drives = Drives(BottleConfig(Path=str(tmp_path)))

    assert drives.get_all() == {"D": "../../disc"}
    (devices / "d:").unlink()
    assert drives.get_all() == {}


def test_relative_drive_mapping_is_preserved(tmp_path):
    drives = Drives(BottleConfig(Path=str(tmp_path)))
    drives.set_drive_path("D", "../../disc")
    assert os.readlink(tmp_path / "dosdevices" / "d:") == "../../disc"
    assert drives.get_drive("D") == "../../disc"
