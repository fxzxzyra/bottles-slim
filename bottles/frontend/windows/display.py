# display.py
#
# Copyright 2025 Bottles Developers
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from functools import partial
from gettext import gettext as _

from gi.repository import Adw, Gtk

from bottles.backend.logger import Logger
from bottles.backend.models.result import Result
from bottles.backend.utils.threading import RunAsync
from bottles.backend.wine.reg import Reg
from bottles.backend.wine.regkeys import RegKeys

logging = Logger()

renderers = ["gl", "gdi", "vulkan"]
dpi_scaling_modes = ["default", "application", "system"]


@Gtk.Template(resource_path="/com/usebottles/bottles/dialog-display.ui")
class DisplayDialog(Adw.Window):
    __gtype_name__ = "DisplayDialog"

    # Region Widgets
    btn_save = Gtk.Template.Child()
    expander_virtual_desktop = Gtk.Template.Child()
    spin_width = Gtk.Template.Child()
    spin_height = Gtk.Template.Child()
    switch_mouse_capture = Gtk.Template.Child()
    switch_take_focus = Gtk.Template.Child()
    switch_mouse_warp = Gtk.Template.Child()
    switch_decorated = Gtk.Template.Child()
    spin_dpi = Gtk.Template.Child()
    combo_renderer = Gtk.Template.Child()
    combo_dpi_scaling = Gtk.Template.Child()

    def __init__(
        self, parent_window, config, details, queue, widget, spinner_display, **kwargs
    ):
        super().__init__(**kwargs)
        self.set_transient_for(parent_window)

        # Common variables and references
        self.window = parent_window
        self.manager = parent_window.manager
        self.config = config
        self.queue = queue
        self.widget = widget
        self.spinner_display = spinner_display

        # Connect signals
        self.btn_save.connect("clicked", self.__save)

        self.__update(config)

    def __update(self, config):
        self.parameters = config.Parameters

        self.expander_virtual_desktop.set_enable_expansion(
            self.parameters.virtual_desktop
        )
        self.switch_mouse_capture.set_active(self.parameters.fullscreen_capture)
        self.switch_take_focus.set_active(self.parameters.take_focus)
        self.switch_mouse_warp.set_active(self.parameters.mouse_warp)
        self.switch_decorated.set_active(self.parameters.decorated)
        self.spin_dpi.set_value(self.parameters.custom_dpi)
        mode = self.parameters.dpi_scaling
        self.combo_dpi_scaling.set_selected(
            dpi_scaling_modes.index(mode) if mode in dpi_scaling_modes else 0
        )
        self.dpi_scaling = None
        self.combo_dpi_scaling.set_sensitive(False)

        def loaded(result, error):
            if error or result is None or not result.ok:
                self.window.show_toast(_("Could not read the DPI scaling mode."))
                return
            self.dpi_scaling = result.data
            self.combo_dpi_scaling.set_selected(dpi_scaling_modes.index(result.data))
            self.combo_dpi_scaling.set_sensitive(True)

        RunAsync(RegKeys(config).get_dpi_scaling, loaded)

        """Set resolution"""
        virtual_desktop_res = self.parameters.virtual_desktop_res
        resolution = virtual_desktop_res.split("x")
        self.spin_width.set_value(float(resolution[0]))
        self.spin_height.set_value(float(resolution[1]))

        """Set renderer"""
        for index, renderer in enumerate(renderers):
            if self.parameters.renderer == renderer:
                self.combo_renderer.set_selected(index)
                break

    def __save(self, *_args):
        """Capture the controls once and apply registry changes in order."""
        parameters = self.parameters
        rk = RegKeys(self.config)
        tasks = []

        def add(changes, operation):
            if any(getattr(parameters, key) != value for key, value in changes.items()):
                tasks.append((changes, operation))

        desktop = self.expander_virtual_desktop.get_enable_expansion()
        resolution = f"{int(self.spin_width.get_value())}x{int(self.spin_height.get_value())}"
        desktop_changes = {"virtual_desktop": desktop}
        if desktop:
            desktop_changes["virtual_desktop_res"] = resolution
        add(desktop_changes, partial(rk.toggle_virtual_desktop, state=desktop, resolution=resolution))
        add({"mouse_warp": self.switch_mouse_warp.get_active()},
            partial(rk.set_mouse_warp, state=self.switch_mouse_warp.get_active()))
        dpi = int(self.spin_dpi.get_value())
        add({"custom_dpi": dpi}, partial(rk.set_dpi, value=dpi))
        scaling = dpi_scaling_modes[self.combo_dpi_scaling.get_selected()]
        if self.dpi_scaling is not None and scaling != self.dpi_scaling:
            tasks.append(({"dpi_scaling": scaling}, partial(rk.set_dpi_scaling, mode=scaling)))
        renderer = renderers[self.combo_renderer.get_selected()]
        add({"renderer": renderer}, partial(rk.set_renderer, value=renderer))
        reg = Reg(self.config)
        for control, key, registry_key in (
            (self.switch_mouse_capture, "fullscreen_capture", "GrabFullscreen"),
            (self.switch_take_focus, "take_focus", "UseTakeFocus"),
            (self.switch_decorated, "decorated", "Decorated"),
        ):
            state = control.get_active()
            add({key: state}, partial(
                reg.add, key=r"HKEY_CURRENT_USER\Software\Wine\X11 Driver",
                value=registry_key, data="Y" if state else "N",
            ))

        self.close()
        if not tasks:
            return
        self.btn_save.set_sensitive(False)
        self.widget.set_sensitive(False)
        self.spinner_display.start()
        self.queue.add_task()
        self.window.show_toast(_("Updating display settings, please wait…"))

        def apply():
            results = []
            for changes, operation in tasks:
                try:
                    result = operation()
                except Exception as error:
                    logging.error(f"Display settings update failed: {error}")
                    result = Result(False, message=str(error))
                results.append((changes, result))
            return results

        def completed(results, error):
            failed = bool(error)
            try:
                previous = self.config.Parameters
                parameters = previous.copy()
                changed = False
                for changes, result in results or []:
                    if not result.ok:
                        failed = True
                        logging.error(result.message)
                        continue
                    for key, value in changes.items():
                        setattr(parameters, key, value)
                    changed = True
                if changed:
                    try:
                        saved = self.manager.update_config(
                            config=self.config, key="Parameters", value=parameters,
                        )
                    except Exception:
                        self.config.Parameters = previous
                        raise
                    if not saved.ok:
                        # update_config mutates before writing; retain the saved values.
                        self.config.Parameters = previous
                        failed = True
                    else:
                        self.config = saved.data["config"]
                        self.parameters = self.config.Parameters
            except Exception as exception:
                failed = True
                logging.error(f"Could not save display settings: {exception}")
            finally:
                self.widget.set_sensitive(True)
                self.spinner_display.stop()
                self.queue.end_task()
                self.window.show_toast(
                    _("Some display settings could not be updated.")
                    if failed else _("Display settings updated")
                )

        RunAsync(apply, completed)
