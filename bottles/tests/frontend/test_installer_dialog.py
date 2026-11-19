"""Progress must reach real widgets through the GLib dispatch wrappers."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from gi.repository import GLib, Gtk

from bottles.backend.models.config import BottleConfig
from bottles.backend.utils.threading import RunAsync
from bottles.frontend.windows import installer as module
from bottles.frontend.windows.installer import InstallerDialog


@pytest.fixture
def dialog(monkeypatch, iterate_until):
    jobs = []

    def run(*args, **kwargs):
        job = RunAsync(*args, **kwargs)
        jobs.append(job)
        return job

    monkeypatch.setattr(module, "RunAsync", run)
    window = Gtk.Window()
    window.manager = SimpleNamespace(installer_manager=SimpleNamespace(get_icon_url=lambda _name: None))
    window.page_details = SimpleNamespace(
        view_bottle=SimpleNamespace(update_programs=Mock()), go_back_sidebar=Mock(),
    )
    dialog = InstallerDialog(
        window, BottleConfig(Name="Office"), ("editor", {"Name": "Editor"}),
    )
    yield dialog
    context = GLib.MainContext.default()
    try:
        iterate_until(lambda: all(not job.is_alive() for job in jobs) and not context.pending())
    finally:
        # Cleanup must work even when the dialog's own stop method is broken.
        source_id = dialog._InstallerDialog__elapsed_source
        source = context.find_source_by_id(source_id) if source_id else None
        if source is not None:
            source.destroy()
        dialog.destroy()
        window.destroy()



@pytest.mark.parametrize("requested, expected, label", [
    (0.42, 0.42, "42%"), (-0.5, 0.0, "0%"), (1.7, 1.0, "100%"),
])
def test_installer_progress_reaches_widgets(dialog, iterate_until, requested, expected, label):
    dialog.update_progress(requested)
    iterate_until(lambda: dialog.progressbar.get_show_text())
    assert dialog.progressbar.get_fraction() == expected
    assert dialog.progressbar.get_text() == label


def test_steps_restore_overall_progress_ignore_late_steps_and_reset(dialog, iterate_until):
    dialog.set_steps({"total": 2, "sections": ["deps", "exe"]})
    dialog.next_step("Fonts")
    iterate_until(lambda: dialog.progressbar.get_fraction() == 0.5)
    assert dialog.label_activity.get_label() == "Installing dependency: Fonts"
    dialog.update_progress(0.2)
    iterate_until(dialog.progressbar.get_show_text)
    dialog.update_progress(None)
    iterate_until(lambda: not dialog.progressbar.get_show_text())
    assert dialog.progressbar.get_fraction() == 0.5
    dialog.next_step()
    iterate_until(lambda: dialog.progressbar.get_fraction() == 1.0)
    # Queue a fence behind the late call: it must execute without throwing.
    complete = []
    dialog.next_step()
    GLib.idle_add(lambda: complete.append(True))
    iterate_until(lambda: bool(complete))
    assert dialog.progressbar.get_fraction() == 1.0
    dialog.set_steps({"total": 2, "sections": ["params", "checks"]})
    dialog.next_step()
    iterate_until(lambda: dialog.progressbar.get_fraction() == 0.5)
    assert dialog.label_activity.get_label() == "Configuring the container…"


def test_empty_steps_do_not_divide_by_zero(dialog, iterate_until):
    dialog.set_steps({"total": 0, "sections": []})
    dialog.update_progress(0.5)
    iterate_until(dialog.progressbar.get_show_text)
    dialog.next_step()
    dialog.update_progress(None)
    iterate_until(lambda: not dialog.progressbar.get_show_text())
    assert dialog.progressbar.get_fraction() == 0.0


def test_activity_and_log_keep_last_200_lines(dialog, iterate_until):
    dialog.update_activity("Office setup")
    iterate_until(lambda: dialog.label_activity.get_label() == "Running Office setup...")
    for index in range(205):
        dialog.add_log(f"line {index}")
    buffer = dialog.details_view.get_buffer()
    iterate_until(lambda: buffer.get_line_count() == 200)
    # A fence ensures all 205 callbacks ran, not just the first 200.
    done = []
    GLib.idle_add(lambda: done.append(True))
    iterate_until(lambda: bool(done))
    assert buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).splitlines() == [
        f"line {index}" for index in range(5, 205)
    ]
    assert dialog.btn_details.get_visible()


def test_completed_dialog_stops_timer_and_can_be_closed(dialog):
    dialog.set_deletable(False)
    source = GLib.timeout_add_seconds(3600, lambda: True)
    dialog._InstallerDialog__elapsed_source = source
    dialog._InstallerDialog__installed()
    assert dialog.get_deletable()
    assert dialog.stack.get_visible_child_name() == "page_installed"
    assert GLib.MainContext.default().find_source_by_id(source) is None
    dialog.window.page_details.view_bottle.update_programs.assert_called_once_with(force_update=True)
    dialog.window.page_details.go_back_sidebar.assert_called_once_with()
