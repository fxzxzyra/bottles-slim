from types import SimpleNamespace
from unittest.mock import Mock

from bottles.frontend.windows.installer import InstallerDialog


def test_installer_progress_displays_percentage():
    dialog = SimpleNamespace(progressbar=Mock())

    InstallerDialog.update_progress.__wrapped__(dialog, 0.42)

    dialog.progressbar.set_fraction.assert_called_once_with(0.42)
    dialog.progressbar.set_text.assert_called_once_with("42%")
    dialog.progressbar.set_show_text.assert_called_once_with(True)


def test_installer_progress_restores_overall_progress():
    dialog = SimpleNamespace(
        progressbar=Mock(),
        _InstallerDialog__current_step=2,
        _InstallerDialog__steps=4,
    )

    InstallerDialog.update_progress.__wrapped__(dialog, None)

    dialog.progressbar.set_fraction.assert_called_once_with(0.5)
    dialog.progressbar.set_show_text.assert_called_once_with(False)


def test_installer_activity_displays_manifest_label():
    dialog = SimpleNamespace(label_activity=Mock())

    InstallerDialog.update_activity.__wrapped__(dialog, "Microsoft 365 setup")

    dialog.label_activity.set_label.assert_called_once_with(
        "Running Microsoft 365 setup..."
    )


def test_late_installer_step_does_not_overrun_completed_sections():
    dialog = SimpleNamespace(
        _InstallerDialog__current_step=1,
        _InstallerDialog__steps=1,
        _InstallerDialog__sections=["exe"],
        progressbar=Mock(),
    )
    InstallerDialog.next_step.__wrapped__(dialog)
    dialog.progressbar.set_fraction.assert_not_called()


def test_installed_dialog_can_be_closed():
    dialog = SimpleNamespace(
        _InstallerDialog__stop_activity=Mock(),
        set_deletable=Mock(),
        stack=Mock(),
        window=Mock(),
    )
    InstallerDialog._InstallerDialog__installed(dialog)
    dialog.set_deletable.assert_called_once_with(True)
    dialog._InstallerDialog__stop_activity.assert_called_once()
