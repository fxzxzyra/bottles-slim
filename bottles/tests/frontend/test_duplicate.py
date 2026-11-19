from types import SimpleNamespace

import pytest


from bottles.backend.models.result import Result  # noqa: E402
from bottles.frontend.windows.duplicate import DuplicateDialog  # noqa: E402


class EntryStub:
    def __init__(self, text):
        self.text = text
        self.css_classes = set()

    def get_text(self):
        return self.text

    def add_css_class(self, css_class):
        self.css_classes.add(css_class)

    def remove_css_class(self, css_class):
        self.css_classes.discard(css_class)


@pytest.mark.parametrize(
    ("name", "existing_names", "expected_sensitive"),
    (
        ("", {}, False),
        ("   ", {}, False),
        ("Existing", {"1" * 32: SimpleNamespace(Name="Existing")}, False),
        ("  Existing  ", {"1" * 32: SimpleNamespace(Name="Existing")}, False),
        ("New Container", {}, True),
    ),
)
def test_duplicate_name_validation(name, existing_names, expected_sensitive):
    dialog = SimpleNamespace(
        entry_name=EntryStub(name),
        btn_duplicate=SimpleNamespace(
            set_sensitive=lambda value: setattr(dialog, "sensitive", value)
        ),
        parent=SimpleNamespace(manager=SimpleNamespace(local_bottles=existing_names)),
    )

    DuplicateDialog._DuplicateDialog__check_entry_name(dialog)

    assert dialog.sensitive is expected_sensitive
    assert ("error" in dialog.entry_name.css_classes) is not expected_sensitive


def _make_finish_dialog():
    dialog = SimpleNamespace(
        spinner=SimpleNamespace(stop=lambda: setattr(dialog, "spinning", False)),
        set_can_close=lambda value: setattr(dialog, "can_close", value),
        btn_cancel=SimpleNamespace(
            set_sensitive=lambda value: setattr(dialog, "close_enabled", value),
            set_label=lambda value: setattr(dialog, "close_label", value),
        ),
        spinning=True, can_close=False, close_enabled=False,
        parent=SimpleNamespace(
            manager=SimpleNamespace(
                update_bottles=lambda: setattr(dialog, "updated", True)
            )
        ),
        page_failed=SimpleNamespace(
            set_description=lambda value: setattr(dialog, "failure_message", value)
        ),
        stack_switcher=SimpleNamespace(
            set_visible_child_name=lambda value: setattr(dialog, "page", value)
        ),
        updated=False,
        failure_message=None,
        page=None,
    )
    return dialog


def test_duplicate_finish_shows_success_and_refreshes_bottles():
    dialog = _make_finish_dialog()

    DuplicateDialog.finish.__wrapped__(dialog, Result(status=True))

    assert dialog.can_close and dialog.close_enabled and not dialog.spinning
    assert dialog.updated
    assert dialog.page == "page_duplicated"
    assert dialog.failure_message is None


@pytest.mark.parametrize(
    ("result", "error", "expected_message"),
    (
        (Result(status=False, message="copy failed"), None, "copy failed"),
        (None, RuntimeError("disk full"), "disk full"),
    ),
)
def test_duplicate_finish_shows_failure_without_refreshing_bottles(
    result, error, expected_message
):
    dialog = _make_finish_dialog()

    DuplicateDialog.finish.__wrapped__(dialog, result, error)

    assert dialog.can_close and dialog.close_enabled and not dialog.spinning
    assert not dialog.updated
    assert dialog.page == "page_failed"
    assert dialog.failure_message == expected_message


@pytest.mark.parametrize("succeeds", [True, False])
def test_copy_keeps_native_dialog_open_until_worker_completes(monkeypatch, iterate_until, succeeds):
    from gi.repository import Adw, Gio
    from bottles.frontend.windows import duplicate as module

    pending, refreshed, chooser_parents = [], [], []
    owner = Adw.Window()
    parent = SimpleNamespace(
        window=owner, config=object(),
        manager=SimpleNamespace(local_bottles={}, update_bottles=lambda: refreshed.append(True)),
    )

    class DirectoryChooser:
        def __init__(self, **_kwargs):
            pass

        def select_folder(self, window, _cancellable, callback):
            chooser_parents.append(window)
            callback(self, None)

        def select_folder_finish(self, _result):
            return Gio.File.new_for_path("/selected/empty")

    monkeypatch.setattr(module.Gtk, "FileDialog", DirectoryChooser)
    monkeypatch.setattr(module, "resolve_bottles_directory", lambda _owner, path: path)
    monkeypatch.setattr(module, "RunAsync", lambda _task, **kwargs: pending.append(kwargs))
    dialog = DuplicateDialog(parent)
    owner.present()
    dialog.present(owner)
    try:
        dialog.entry_name.set_text("  Work Copy  ")
        dialog.btn_duplicate.emit("clicked")
        assert chooser_parents == [owner]
        assert pending[0]["name"] == "Work Copy"
        assert pending[0]["destination"] == "/selected/empty"
        assert not dialog.get_can_close()
        assert not dialog.btn_cancel.get_sensitive()
        assert dialog.spinner.get_spinning()
        dialog.close()
        assert owner.get_visible_dialog() is dialog
        assert dialog.stack_switcher.get_visible_child_name() == "page_duplicating"

        pending[0]["callback"](Result(status=succeeds, message="copy failed"), None)
        iterate_until(dialog.get_can_close)
        assert dialog.btn_cancel.get_sensitive()
        assert not dialog.spinner.get_spinning()
        assert refreshed == ([True] if succeeds else [])
        assert dialog.stack_switcher.get_visible_child_name() == (
            "page_duplicated" if succeeds else "page_failed"
        )
        dialog.btn_cancel.emit("clicked")
        iterate_until(lambda: owner.get_visible_dialog() is None)
    finally:
        dialog.force_close()
        owner.destroy()
