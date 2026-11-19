# utils.py
#
# Copyright 2025 mirkobrombin <brombin94@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, in version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import webbrowser
from gettext import gettext as _


def format_runner_name(runner: str) -> str:
    from bottles.backend.utils.runners import RunnerRegistry

    info = RunnerRegistry.entries.get(runner)
    if info is None:
        return runner
    source = _("System") if info.source == "system" else _("User")
    return "{source} · {name}{version}".format(
        source=source, name=info.name,
        version=f" ({info.version})" if info.version else "",
    )


def open_doc_url(widget, page):
    webbrowser.open_new_tab(f"https://docs.usebottles.com/{page}")


def format_environment_name(environment: str) -> str:
    return {"Application": _("Application"), "Gaming": _("Gaming"),
            "Custom": _("Custom")}.get(environment, environment)
