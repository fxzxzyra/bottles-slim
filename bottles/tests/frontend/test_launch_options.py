# ruff: noqa: E402
from types import SimpleNamespace


from bottles.frontend.windows.launchoptions import LaunchOptionsDialog


def test_arguments_toggle_disables_only_the_text_entry():
    editable = []
    dialog = SimpleNamespace(
        entry_arguments=SimpleNamespace(set_editable=editable.append),
        switch_arguments=SimpleNamespace(get_active=lambda: False),
    )

    LaunchOptionsDialog._LaunchOptionsDialog__toggle_arguments(dialog)

    assert editable == [False]


def test_cancel_post_script_picker_does_not_change_the_pre_script(monkeypatch):
    from gi.repository import GLib
    from bottles.frontend.windows import launchoptions
    changes, dialogs = [], []
    class Picker:
        def set_title(self, title):
            self.title = title
        def set_modal(self, modal):
            pass
        def open(self, parent, callback):
            dialogs.append(self)
            callback(self, object())
        def open_finish(self, result):
            raise GLib.Error("Dismissed", code=2)
    monkeypatch.setattr(launchoptions.Gtk.FileDialog, "new", Picker)
    dialog = SimpleNamespace(
        program={}, window=object(),
        action_pre_script=SimpleNamespace(set_subtitle=lambda value: changes.append(("pre", value))),
        action_post_script=SimpleNamespace(set_subtitle=lambda value: changes.append(("post", value))),
        _LaunchOptionsDialog__default_pre_script_msg="Before",
        _LaunchOptionsDialog__default_post_script_msg="After",
    )
    LaunchOptionsDialog._LaunchOptionsDialog__choose_post_script(dialog)
    assert changes == [("post", "After")]
    assert dialogs[0].title == launchoptions._("Select Post-run Script")
