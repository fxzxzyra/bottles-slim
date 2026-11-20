from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bottles.backend.models.config import BottleConfig


def _make_view(config):
    return SimpleNamespace(config=config, switch_hdr=Mock())


def test_flatpak_addons_use_the_current_runtime_branch():
    from bottles.frontend.views.bottle_preferences import FLATPAK_INSTALL_COMMANDS

    assert set(FLATPAK_INSTALL_COMMANDS) == {
        "gamescope",
        "hdr",
        "vkbasalt",
        "lsfg_vk",
        "mangohud",
        "obsvkc",
    }
    assert all("remote-add" not in command for command in FLATPAK_INSTALL_COMMANDS.values())
    assert all(command.endswith("//26.08") for command in FLATPAK_INSTALL_COMMANDS.values())
    assert (
        "org.freedesktop.Platform.VulkanLayer.OBSVkCapture"
        in FLATPAK_INSTALL_COMMANDS["obsvkc"]
    )


def test_active_hdr_remains_available_to_disable_on_x11(monkeypatch):
    from bottles.frontend.views import bottle_preferences
    from bottles.frontend.views.bottle_preferences import PreferencesView

    config = BottleConfig()
    config.Parameters.hdr = True
    view = _make_view(config)
    monkeypatch.setattr(
        bottle_preferences.DisplayUtils, "display_server_type", lambda: "x11"
    )

    PreferencesView._PreferencesView__update_hdr_sensitivity(view)

    view.switch_hdr.set_sensitive.assert_called_once_with(True)


def test_hdr_requires_wayland_or_gamescope_when_inactive(monkeypatch):
    from bottles.frontend.views import bottle_preferences
    from bottles.frontend.views.bottle_preferences import PreferencesView

    config = BottleConfig()
    view = _make_view(config)
    monkeypatch.setattr(bottle_preferences.VulkanUtils, "check_support", lambda: True)
    monkeypatch.setattr(
        bottle_preferences.DisplayUtils, "display_server_type", lambda: "wayland"
    )
    monkeypatch.setattr(bottle_preferences, "gamescope_available", "gamescope")

    PreferencesView._PreferencesView__update_hdr_sensitivity(view)
    view.switch_hdr.set_sensitive.assert_called_with(False)

    config.Parameters.wayland = True
    PreferencesView._PreferencesView__update_hdr_sensitivity(view)
    view.switch_hdr.set_sensitive.assert_called_with(True)

    config.Parameters.wayland = False
    config.Parameters.gamescope = True
    PreferencesView._PreferencesView__update_hdr_sensitivity(view)
    view.switch_hdr.set_sensitive.assert_called_with(True)


def test_gamescope_toggle_refreshes_hdr_sensitivity():
    from bottles.frontend.views.bottle_preferences import PreferencesView

    view = SimpleNamespace()
    view._PreferencesView__toggle_feature = Mock()
    view._PreferencesView__update_hdr_sensitivity = Mock()

    PreferencesView._PreferencesView__toggle_gamescope(view, None, True)

    view._PreferencesView__toggle_feature.assert_called_once_with(
        state=True, key="gamescope"
    )
    view._PreferencesView__update_hdr_sensitivity.assert_called_once_with()

def test_unchanged_sync_does_not_update_bottle(monkeypatch):
    from bottles.frontend.views import bottle_preferences
    from bottles.frontend.views.bottle_preferences import PreferencesView

    config = BottleConfig()
    config.Parameters.sync = "ntsync"
    view = SimpleNamespace(
        config=config,
        combo_sync=Mock(),
        manager=Mock(),
        queue=Mock(),
    )
    view.combo_sync.get_selected.return_value = 3
    run_async = Mock()
    monkeypatch.setattr(bottle_preferences, "RunAsync", run_async)

    PreferencesView._PreferencesView__set_sync_type(view)

    run_async.assert_not_called()
    view.manager.update_config.assert_not_called()
    view.combo_sync.set_sensitive.assert_not_called()
    view.queue.add_task.assert_not_called()


@pytest.mark.parametrize("error", (None, ValueError("winecfg failed")))
def test_windows_version_is_saved_only_after_winecfg_succeeds(monkeypatch, error):
    from gi.repository import Adw, GLib, Gtk

    from bottles.frontend.views import bottle_preferences
    from bottles.frontend.views.bottle_preferences import PreferencesView

    Adw.init()
    config = BottleConfig(Windows="win10")
    combo = Adw.ComboRow(model=Gtk.StringList.new(["Windows 10", "Windows 11"]))
    combo.set_selected(0)
    view = SimpleNamespace(
        config=config,
        combo_windows=combo,
        windows_versions={"win10": "Windows 10", "win11": "Windows 11"},
        manager=Mock(),
        queue=Mock(),
        spinner_windows=Mock(),
    )
    view._PreferencesView__set_windows = lambda *_args: (
        PreferencesView._PreferencesView__set_windows(view)
    )
    combo.connect("notify::selected", view._PreferencesView__set_windows)
    run_async = Mock()
    monkeypatch.setattr(bottle_preferences, "RunAsync", run_async)
    monkeypatch.setattr(bottle_preferences, "RegKeys", Mock())

    def persist(**kwargs):
        config.Windows = kwargs["value"]
        return SimpleNamespace(data={"config": config})

    view.manager.update_config.side_effect = persist
    combo.set_selected(1)

    assert config.Windows == "win10"
    view.manager.update_config.assert_not_called()
    assert not combo.get_sensitive()
    callback = run_async.call_args.kwargs["callback"]
    callback(None, error)
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)

    if error:
        assert config.Windows == "win10"
        assert combo.get_selected() == 0
        view.manager.update_config.assert_not_called()
    else:
        assert config.Windows == "win11"
        assert combo.get_selected() == 1
        view.manager.update_config.assert_called_once_with(
            config=config, key="Windows", value="win11"
        )
    assert run_async.call_count == 1
    assert combo.get_sensitive()
    view.queue.end_task.assert_called_once_with()
    view.spinner_windows.set_visible.assert_called_with(False)



def _make_graphics_view(config):
    from bottles.frontend.views.bottle_preferences import PreferencesView

    view = _component_view()
    view.config = config
    view.manager.dxvk_available = ["dxvk-old", "dxvk-new"]
    view.manager.vkd3d_available = ["vkd3d-old", "vkd3d-new"]
    view.manager.update_config = Mock()
    view.manager.set_dll_component = Mock()
    view.queue = Mock()
    view._PreferencesView__refresh_component_selection()
    view.set_dxvk_status = lambda **kwargs: (
        PreferencesView.set_dxvk_status.__wrapped__(view, **kwargs)
    )
    view.set_vkd3d_status = lambda **kwargs: (
        PreferencesView.set_vkd3d_status.__wrapped__(view, **kwargs)
    )
    return view


@pytest.mark.parametrize("component", ["dxvk", "vkd3d"])
def test_graphics_removal_does_not_save_while_pending(monkeypatch, component):
    from bottles.frontend.views import bottle_preferences
    from bottles.frontend.views.bottle_preferences import PreferencesView

    config = BottleConfig(DXVK="dxvk-old", VKD3D="vkd3d-old")
    setattr(config.Parameters, component, True)
    view = _make_graphics_view(config)
    combo = getattr(view, f"combo_{component}")
    handler = getattr(view, f"_PreferencesView__set_{component}")
    combo.handler_block_by_func(handler)
    combo.set_selected(0)
    combo.handler_unblock_by_func(handler)
    jobs = []
    monkeypatch.setattr(
        bottle_preferences, "RunAsync", lambda **kwargs: jobs.append(kwargs)
    )

    getattr(PreferencesView, f"_PreferencesView__set_{component}")(view)

    assert getattr(config.Parameters, component)
    view.manager.update_config.assert_not_called()
    assert not view.combo_dxvk.get_sensitive()
    assert not view.combo_vkd3d.get_sensitive()
    assert len(jobs) == 1 and jobs[0]["enabled"] is False


@pytest.mark.parametrize("component", ["dxvk", "vkd3d"])
def test_graphics_failure_restores_selector(component):
    from bottles.backend.models.result import Result

    config = BottleConfig(DXVK="dxvk-old", VKD3D="vkd3d-old")
    setattr(config.Parameters, component, True)
    view = _make_graphics_view(config)

    getattr(view, f"set_{component}_status")(status=Result(False, message="failed"))

    assert getattr(view, f"combo_{component}").get_selected() == 1
    assert getattr(config.Parameters, component)
    view.queue.end_task.assert_called_once()


def test_graphics_success_updates_both_selectors():
    from bottles.backend.models.result import Result

    view = _make_graphics_view(BottleConfig())
    updated = BottleConfig(DXVK="dxvk-new", VKD3D="vkd3d-new")
    updated.Parameters.dxvk = True
    updated.Parameters.vkd3d = True

    view.set_vkd3d_status(status=Result(True, data={"config": updated}))

    assert view.config is updated
    assert view.combo_dxvk.get_selected() == 2
    assert view.combo_vkd3d.get_selected() == 2
    view.queue.end_task.assert_called_once()


@pytest.mark.parametrize("layer, helper", [(False, False), (False, True),
                                         (True, False), (True, True)])
def test_vkbasalt_editor_is_optional(monkeypatch, layer, helper):
    from bottles.frontend.views import bottle_preferences as module

    view = SimpleNamespace(switch_vkbasalt=Mock(), btn_manage_vkbasalt=Mock())
    monkeypatch.setattr(module, "vkbasalt_available", layer)
    monkeypatch.setattr(module, "vkbasalt_config_available", helper)
    module.PreferencesView._PreferencesView__update_vkbasalt_sensitivity(view)
    view.switch_vkbasalt.set_sensitive.assert_called_once_with(layer)
    view.btn_manage_vkbasalt.set_sensitive.assert_called_once_with(layer and helper)
    if layer and not helper:
        view.btn_manage_vkbasalt.set_tooltip_text.assert_called_once()


@pytest.mark.parametrize("nvidia", (True, False))
@pytest.mark.parametrize("enabled", (True, False))
def test_nvapi_remains_manageable_after_gpu_change(monkeypatch, nvidia, enabled):
    from bottles.frontend.views import bottle_preferences
    from bottles.frontend.views.bottle_preferences import PreferencesView

    config = BottleConfig()
    config.Parameters.dxvk_nvapi = enabled
    view = SimpleNamespace(config=config, combo_nvapi=Mock())
    monkeypatch.setattr(bottle_preferences.GPUUtils, "is_gpu", lambda *_args: nvidia)

    PreferencesView._PreferencesView__update_nvapi_visibility(view)

    view.combo_nvapi.set_visible.assert_called_once_with(nvidia or enabled)


@pytest.mark.parametrize("success", [False, True])
def test_bottle_notes_are_kept_when_saving_fails(success):
    from gi.repository import Gtk
    from bottles.backend.models.result import Result
    from bottles.frontend.views.bottle_preferences import PreferencesView

    config = BottleConfig(Name="Test")
    text = Gtk.TextView()
    notes = "Installation notes\nDo not discard this text."
    text.get_buffer().set_text(notes)
    button = Gtk.Button()
    def save(_config, **kwargs):
        _config.Notes = kwargs["value"]
        return Result(success, {"config": _config})
    manager = SimpleNamespace(update_config=Mock(side_effect=save))
    view = SimpleNamespace(config=config, text_notes=text, btn_save_notes=button, manager=manager, window=SimpleNamespace(show_toast=Mock()))

    PreferencesView._PreferencesView__save_notes(view, button)

    manager.update_config.assert_called_once_with(config, key="Notes", value=notes)
    assert button.get_sensitive() is not success
    buffer = text.get_buffer()
    assert buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True) == notes
    assert view.window.show_toast.called is not success
    assert config.Notes == (notes if success else "")



@pytest.mark.parametrize("sync,compiled,visible", [("esync", False, True), ("esync", True, False), ("wine", False, False)])
def test_esync_warning_follows_selected_runner(monkeypatch, runner_factory, sync, compiled, visible):
    import shlex
    from bottles.frontend.views import bottle_preferences as module
    info = runner_factory()
    indicator = Mock()
    config = BottleConfig(Runner=info.identifier)
    view = SimpleNamespace(config=config, _esync_warning=indicator)
    probe = Mock(return_value=not compiled)
    monkeypatch.setattr(module, "is_esync_missing", probe)
    module.PreferencesView._PreferencesView__update_esync_warning(view, sync)
    probe.assert_called_once_with(shlex.quote(info.wine_for_arch(config.Arch)))
    indicator.set_visible.assert_called_once_with(visible)


def test_notes_save_is_available_only_for_changed_text():
    from gi.repository import Gtk
    from bottles.frontend.views.bottle_preferences import PreferencesView

    config = BottleConfig(Notes="Saved notes")
    buffer = Gtk.TextBuffer()
    button = Gtk.Button()
    view = SimpleNamespace(config=config, btn_save_notes=button)
    buffer.connect("changed", lambda buffer: PreferencesView._PreferencesView__notes_changed(view, buffer))
    buffer.set_text("Saved notes")
    assert not button.get_sensitive()
    buffer.set_text("New notes")
    assert button.get_sensitive()
    buffer.set_text("Saved notes")
    assert not button.get_sensitive()


@pytest.mark.parametrize("failure", [None, "write", "exception"])
def test_sync_stays_locked_until_completion_and_restores_failed_selection(monkeypatch, failure):
    from gi.repository import Adw, Gtk
    from bottles.backend.models.result import Result
    from bottles.frontend.views import bottle_preferences as module

    config = BottleConfig()
    config.Parameters.sync = "wine"
    combo = Adw.ComboRow(model=Gtk.StringList.new(["Wine", "Esync", "Fsync", "Ntsync"]))
    combo.set_selected(1)
    view = SimpleNamespace(
        config=config, combo_sync=combo, manager=Mock(), queue=Mock(),
        window=SimpleNamespace(show_toast=Mock()),
        _PreferencesView__update_esync_warning=Mock(),
    )
    method = module.PreferencesView._PreferencesView__set_sync_type
    view._PreferencesView__set_sync_type = lambda *_args: method(view)
    combo.connect("notify::selected", view._PreferencesView__set_sync_type)
    jobs = []
    monkeypatch.setattr(module, "RunAsync", lambda *args, **kwargs: jobs.append(kwargs))

    method(view)
    assert not combo.get_sensitive()
    view.queue.end_task.assert_not_called()
    # The real manager mutates the config before attempting the write.
    config.Parameters.sync = "esync"
    jobs[0]["callback"](
        None if failure == "exception" else Result(failure is None, {"config": config}),
        OSError("Failed") if failure == "exception" else None,
    )
    assert config.Parameters.sync == ("esync" if failure is None else "wine")
    assert combo.get_selected() == (1 if failure is None else 0)
    assert combo.get_sensitive()
    assert len(jobs) == 1  # Reverting the selection must not submit another write.
    view.queue.end_task.assert_called_once()
    assert view.window.show_toast.called is (failure is not None)


def _component_view():
    from gi.repository import Adw, Gtk
    from bottles.frontend.views.bottle_preferences import PreferencesView

    view = SimpleNamespace(config=BottleConfig(), manager=SimpleNamespace())
    view.combo_runner = Adw.ComboRow()
    view._PreferencesView__set_components_busy = lambda busy: PreferencesView._PreferencesView__set_components_busy(view, busy)
    view._PreferencesView__set_component_status = lambda *args: PreferencesView._PreferencesView__set_component_status(view, *args)
    view._PreferencesView__change_component = lambda *args: PreferencesView._PreferencesView__change_component(view, *args)
    view.window = SimpleNamespace(show_toast=Mock())
    for name in ("d7vk", "dxvk", "vkd3d", "nvapi", "latencyflex"):
        model = Gtk.StringList.new([])
        combo = Adw.ComboRow(model=model)
        setattr(view.manager, f"{name}_available", ["latest"])
        setattr(view, f"str_list_{name}", model)
        setattr(view, f"combo_{name}", combo)
        setattr(view, f"spinner_{name}", Adw.Spinner(visible=False))
        def unexpected(*_args):
            pytest.fail("Refreshing installed components must not install anything")
        setattr(view, f"_PreferencesView__set_{name}", unexpected)
        combo.connect("notify::selected", unexpected)
    view._PreferencesView__refresh_component_selection = lambda: PreferencesView._PreferencesView__refresh_component_selection(view)
    return view


def test_imported_component_versions_remain_visible_without_the_source_cache():
    from bottles.frontend.views.bottle_preferences import PreferencesView

    view = _component_view()
    view.config.LatencyFleX = "installed-before-import"
    view.config.Parameters.latencyflex = True
    view.config.NVAPI = "latest"
    view.config.Parameters.dxvk_nvapi = True
    refresh = lambda: PreferencesView._PreferencesView__refresh_component_selection(view)
    refresh()
    assert view.combo_latencyflex.get_selected() == 2
    assert view.str_list_latencyflex.get_string(2) == "installed-before-import"
    # Cache index zero is a real version; the first UI item is Disabled.
    assert view.combo_nvapi.get_selected() == 1
    view.manager.latencyflex_available = []
    refresh()
    assert view.combo_latencyflex.get_selected() == 1
    assert view.str_list_latencyflex.get_string(1) == "installed-before-import"
    view.config.Parameters.dxvk_nvapi = False
    refresh()
    assert view.combo_nvapi.get_selected() == 0


@pytest.mark.parametrize("component,field,flag", [
    ("d7vk", "D7VK", "d7vk"),
    ("dxvk", "DXVK", "dxvk"),
    ("vkd3d", "VKD3D", "vkd3d"),
    ("nvapi", "NVAPI", "dxvk_nvapi"),
    ("latencyflex", "LatencyFleX", "latencyflex"),
])
@pytest.mark.parametrize("success", [False, True])
def test_component_controls_share_worker_completion_and_failed_selection(monkeypatch, component, field, flag, success):
    from bottles.frontend.views import bottle_preferences as module
    from bottles.backend.models.result import Result

    view = _component_view()
    view.queue = SimpleNamespace(add_task=Mock(), end_task=Mock())
    view.window = SimpleNamespace(show_toast=Mock())
    setattr(view.config, field, "old")
    setattr(view.config.Parameters, flag, True)
    view._PreferencesView__refresh_component_selection()
    combo = getattr(view, f"combo_{component}")
    handler = getattr(view, f"_PreferencesView__set_{component}")
    combo.handler_block_by_func(handler)
    combo.set_selected(1)
    combo.handler_unblock_by_func(handler)
    spinner = getattr(view, f"spinner_{component}")
    pending = []
    monkeypatch.setattr(module, "RunAsync", lambda task_func, **kwargs: pending.append((task_func, kwargs)))
    view.manager.set_dll_component = Mock()
    callback = lambda status=None, error=None, pending=False: module.PreferencesView._PreferencesView__set_component_status(view, component, status, error, pending)
    module.PreferencesView._PreferencesView__change_component(view, component, callback)
    assert not combo.get_sensitive()
    assert not view.combo_runner.get_sensitive()
    assert not view.combo_dxvk.get_sensitive()
    assert not view.combo_latencyflex.get_sensitive()
    assert spinner.get_visible()
    assert getattr(view.config, field) == "old"
    view.queue.end_task.assert_not_called()
    assert len(pending) == 1
    task, arguments = pending[0]
    assert task is view.manager.set_dll_component
    assert arguments["version"] == "latest"
    assert arguments["enabled"]
    config = view.config.copy()
    if success:
        setattr(config, field, "latest")
    arguments["callback"](Result(success, {"config": config}, message="Installation failed"), None)
    assert combo.get_sensitive()
    assert not spinner.get_visible()
    assert combo.get_selected() == (1 if success else 2)
    assert view.window.show_toast.called is not success
    view.queue.end_task.assert_called_once()


@pytest.mark.parametrize("dialog_name", [
    "EnvironmentVariablesDialog", "DLLOverridesDialog", "DrivesDialog",
])
def test_feature_dialog_uses_native_presentation_signature(monkeypatch, tmp_path, dialog_name):
    from gi.repository import Adw, Gtk
    from bottles.frontend.views import bottle_preferences

    parent = Gtk.Window()
    parent.manager = Mock()
    config = BottleConfig(Path=str(tmp_path))
    presented = []
    monkeypatch.setattr(Adw.Dialog, "present", lambda dialog, parent: presented.append((dialog, parent)))
    monkeypatch.setattr(Gtk.Window, "present", lambda window: presented.append((window, None)))
    view = SimpleNamespace(window=parent, config=config)
    try:
        bottle_preferences.PreferencesView._PreferencesView__show_feature_dialog(
            view, None, getattr(bottle_preferences, dialog_name),
        )
        assert len(presented) == 1
        dialog, received_parent = presented[0]
        assert dialog.config is config
        if isinstance(dialog, Adw.Dialog):
            assert received_parent is parent
        else:
            assert received_parent is None
            assert dialog.get_transient_for() is parent
    finally:
        for dialog, _ in presented:
            if isinstance(dialog, Gtk.Window):
                dialog.destroy()
            else:
                dialog.close()
        parent.destroy()
