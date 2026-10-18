# Bottles downstream

Run Windows applications and games on Linux. This is an independently maintained downstream of [Bottles](https://github.com/bottlesdevs/Bottles), based on version **65.4**. Release numbers and tags follow upstream; the feature selection remains based on 65.4. Official Bottles and Flathub packages do not contain these downstream changes.

The downstream gives ordinary applications and games equal priority. Existing-feature fixes are accepted; features added after 65.4 are reviewed individually. UMU and built-in remote runner installation/update management are excluded. System Wine runners are the primary path; locally supplied user runners remain available. Other component downloads remain supported.

Python modules use the selected interpreter's installation scheme. Resources, configuration, cache and state have separate Linux/XDG responsibilities. Vulkan detection uses the native API. See [installation layout](docs/linux-layout.md).

## Build and test

Build dependencies include Meson >= 1.5, Ninja, Blueprint compiler, gettext, GLib tools, Python, GTK >= 4.10, libadwaita >= 1.6, GtkSourceView 5 and libportal's GTK 4 bindings. Python dependencies are listed in `requirements.txt` and `requirements.dev.txt`.

```sh
meson setup build --prefix=/usr
meson compile -C build
DESTDIR="$PWD/stage" meson install -C build
```

The prefix and Python interpreter must match the intended packaging environment; Flatpak uses `/app`. The development Flatpak manifest is `build-aux/com.usebottles.bottles.Devel.json`.

```sh
meson setup build -Dtests=true
meson test -C build --print-errorlogs
```

For an existing build directory, enable tests using `meson configure build -Dtests=true`. GUI tests use Xvfb, a private D-Bus session and software rendering; physical GPU hardware is not required. See the [development guide](docs/development.md) for verification, test design and translations.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution and upstream integration rules.

## Contributions and upstream

Report downstream issues in this repository, including the commit, packaging environment and reproduction steps. Upstream documentation remains useful background, but downstream packaging and behavior can differ. Do not report downstream-specific regressions as official Bottles packaging bugs.

Upstream authorship and license notices are retained. The source is distributed under GPL-3.0; see [COPYING.md](COPYING.md). Bundled data and dependencies retain their own license notices.
