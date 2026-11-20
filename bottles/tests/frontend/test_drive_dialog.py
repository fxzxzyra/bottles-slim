from types import SimpleNamespace
from unittest.mock import Mock, call


from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result


def test_device_drive_shows_eject_action(tmp_path):
    from bottles.frontend.windows.drives import DriveEntry

    dosdevices = tmp_path / "dosdevices"
    dosdevices.mkdir()
    (dosdevices / "d:").symlink_to(tmp_path)
    (dosdevices / "d::").symlink_to("/dev/sr0")
    config = BottleConfig(Path=str(tmp_path))
    parent = SimpleNamespace(
        config=config,
        window=SimpleNamespace(manager=Mock()),
    )

    entry = DriveEntry(parent, ["D", str(tmp_path)])

    assert entry.btn_eject.get_visible() is True


def test_manually_entered_drive_path_is_saved(tmp_path):
    from bottles.backend.wine.drives import Drives
    from bottles.frontend.windows.drives import DriveEntry

    prefix = tmp_path / "prefix"
    devices = prefix / "dosdevices"
    devices.mkdir(parents=True)
    old = tmp_path / "old"
    new = tmp_path / "new path"
    old.mkdir()
    new.mkdir()
    (devices / "p:").symlink_to(old)
    config = BottleConfig(Path=str(prefix))
    parent = SimpleNamespace(config=config, window=SimpleNamespace(manager=Mock()))
    entry = DriveEntry(parent, ["P", str(old)])

    entry.set_text(str(new))
    assert entry.get_show_apply_button()
    entry.emit("apply")

    assert (devices / "p:").resolve() == new
    reopened = DriveEntry(parent, ["P", Drives(config).get_drive("P")])
    assert reopened.get_text() == str(new)
    assert not reopened.get_show_apply_button()


def test_drive_entry_runs_wine_eject(monkeypatch):
    from bottles.frontend.windows import drives as drives_module
    from bottles.frontend.windows.drives import DriveEntry

    config = BottleConfig()
    calls = []

    class FakeEject:
        def __init__(self, received_config):
            assert received_config is config

        def cdrom(self, drive):
            calls.append(drive)
            return Result(True)

    def run_async(task_func, callback, **kwargs):
        callback(task_func(**kwargs), None)

    monkeypatch.setattr(drives_module, "Eject", FakeEject)
    monkeypatch.setattr(drives_module, "RunAsync", run_async)
    entry = SimpleNamespace(
        config=config,
        drive=["D", "/run/media/disc"],
        btn_eject=Mock(),
        parent=SimpleNamespace(window=SimpleNamespace(show_toast=Mock())),
    )

    DriveEntry._DriveEntry__eject(entry)

    assert calls == ["D:"]
    assert entry.btn_eject.set_sensitive.call_args_list == [call(False), call(True)]
    entry.parent.window.show_toast.assert_called_once()


def test_relative_drive_path_is_not_marked_invalid_and_can_be_saved(tmp_path):
    from bottles.frontend.windows.drives import DriveEntry

    config = BottleConfig(Path=str(tmp_path))
    parent = SimpleNamespace(config=config, window=SimpleNamespace(manager=Mock()))
    entry = DriveEntry(parent, ["D", "../../old"])
    assert not entry.has_css_class("error")
    entry.set_text("../../disc")
    assert not entry.has_css_class("error")
    assert entry.get_show_apply_button()
    entry.emit("apply")
    assert (tmp_path / "dosdevices" / "d:").readlink().as_posix() == "../../disc"
    assert not entry.get_show_apply_button()
