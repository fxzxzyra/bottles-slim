# ruff: noqa: E402
from types import SimpleNamespace

from gi.repository import Gio


from bottles.frontend.views import importer


def test_existing_bottle_registration_uses_the_dedicated_action(monkeypatch, tmp_path):
    (tmp_path / "bottle.yml").write_text("configuration")
    calls = []
    manager = SimpleNamespace(import_bottle=lambda **kwargs: calls.append(kwargs))
    view = SimpleNamespace(window=object(), import_manager=manager)
    view._ImporterView__finish = lambda *_args: None
    monkeypatch.setattr(importer, "RunAsync", lambda func, callback, **kwargs: func(**kwargs))
    dialog = SimpleNamespace(
        select_folder_finish=lambda _: Gio.File.new_for_path(str(tmp_path)),
        select_folder=lambda _parent, _cancel, callback: callback(dialog, object()),
    )
    monkeypatch.setattr(importer.Gtk, "FileDialog", lambda **_kwargs: dialog)
    importer.ImporterView._ImporterView__import_existing(view)
    assert calls == [{"path": str(tmp_path)}]
