# ruff: noqa: E402
from types import SimpleNamespace

from gi.repository import Gio


from bottles.frontend.views import importer


def test_selected_folder_is_forwarded_to_prefix_search():
    searches = []
    view = SimpleNamespace(
        btn_select_prefixes=object(),
        window=object(),
    )
    setattr(
        view,
        "_ImporterView__search_prefixes",
        lambda widget, paths: searches.append((widget, paths)),
    )
    dialog = SimpleNamespace(
        select_folder_finish=lambda _result: Gio.File.new_for_path(
            "/tmp/PlayOnLinux prefixes"
        )
    )

    importer.ImporterView._ImporterView__folder_selected(view, dialog, object())

    assert searches == [
        (view.btn_select_prefixes, ["/tmp/PlayOnLinux prefixes"]),
    ]


def test_existing_bottle_selection_registers_in_place(monkeypatch, tmp_path):
    (tmp_path / "bottle.yml").write_text("configuration")
    calls = []
    manager = SimpleNamespace(import_bottle=lambda **kwargs: calls.append(kwargs))
    view = SimpleNamespace(window=object(), import_manager=manager)
    view._ImporterView__finish = lambda *_args: None
    view._ImporterView__search_prefixes = lambda *_args: (_ for _ in ()).throw(
        AssertionError("An existing bottle must not enter the foreign-prefix copy flow")
    )
    monkeypatch.setattr(importer, "RunAsync", lambda func, callback, **kwargs: func(**kwargs))
    dialog = SimpleNamespace(select_folder_finish=lambda _: Gio.File.new_for_path(str(tmp_path)))
    importer.ImporterView._ImporterView__folder_selected(view, dialog, object())
    assert calls == [{"path": str(tmp_path)}]
