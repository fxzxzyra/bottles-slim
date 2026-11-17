# Development guide

Start with the build commands and dependencies in [README.md](../README.md). Use Meson to build and run tests; do not invoke pytest directly, because the suites depend on the configured package, resources and schemas.

## Build verification

The build environment needs the dependencies listed in README.md, plus pytest, Xvfb, dbus-run-session and Mesa software rendering. Python dependencies come from requirements.txt and requirements.dev.txt; GI typelibs and native libraries come from the build environment.

```sh
meson setup build --prefix=/usr -Dtests=true
meson compile -C build
meson test -C build --print-errorlogs
```

For an existing build directory, enable tests with `meson configure build -Dtests=true`. Select a prepared Python interpreter with `-Dpython_interpreter=/absolute/path/to/python` when configuring the build. Meson uses that interpreter for both installation and tests.

Meson runs the installation, backend, frontend, FVS and downstream suites. The installation test performs a temporary staged install and verifies the installed Python package, configured resource/runner paths and shared resources. It does not modify the host installation. Python modules use Meson's installation mapping; see [Linux layout](linux-layout.md).

Missing dependencies, failures and process crashes remain failures. Unhandled thread and unraisable exceptions fail tests; frontend tests also capture PyGObject callback exceptions. JUnit reports are under `build/meson-logs/pytest-*.xml`, with the complete log in `build/meson-logs/testlog.txt`. Record the tested commit and failure details rather than only a passing count.

GUI tests use a virtual display, private D-Bus session, isolated HOME/XDG directories and software rendering. Physical GPU and real Wine application testing are separate from the general suites. FVS tests exercise the Python wrapper, cancellation and locking with a controlled subprocess boundary; they do not prove end-to-end operation of the real fvs2 executable. vkbasalt-cli is optional: its absence disables only vkBasalt configuration editing. General tests do not require downloading Wine runners or Windows programs.

## Continuous integration

The Tests workflow runs on every branch or tag push, pull request and manual dispatch. It uses `ubuntu-latest` and the Flathub GNOME 50 container to build `build-aux/com.usebottles.bottles.Devel.json` directly with Flatpak Builder. The manifest enables Meson tests and runs them against the installed package through the `installed` test setup. Build or test failures fail the job; Meson logs and JUnit reports are retained as workflow artifacts even after failure.

## Test design and review

Define the observable result and the specific defect a test must detect before choosing test doubles. Test counts and pass rates do not establish test quality.

- Keep the tested method and the layer being verified real. Replace external boundaries such as network responses and Wine/FVS subprocesses when needed. Prefer autospec for interface doubles and fail on unexpected operations.
- Use temporary directories and real SQLite/files for persistence; use actual GTK controls and compiled templates for UI state. Small branch tests complement cross-layer checks.
- Derive expected values from the behavior contract and fixed inputs, not from the tested algorithm. Assert exact durations, event counts and complete known results rather than merely nonempty or positive values.
- Cover success, failure and forbidden side effects. Verify failure recovery, stale-result rejection and idempotent completion. Filters need nonmatching entries; cache invalidation tests must first establish that the cached value exists.
- Do not permanently skip failures, swallow assertions or loosen expectations to obtain passing results. Fix implementation defects; change a test only when its expectation conflicts with the intended behavior.
- Isolate mutable singletons, signals and storage for every test. Changing environment variables does not relocate already imported Paths. Fixtures must reclaim threads, windows and timers even after assertion failures.
- Use bounded condition waits and main-loop dispatch for asynchronous work. Avoid millisecond scheduling assumptions and propagate worker errors to the main test.

Existing cross-layer coverage includes (paths are relative to the repository root):

| Behavior | Defects to detect | Test files |
| --- | --- | --- |
| Executor lifecycle and persistence | Missing/incorrect events, wrong durations, unfinished sessions, empty Windows working directory | `bottles/tests/backend/integration/playtime/test_wine_executor_playtime.py` |
| Signal lifecycle and recovery | Unrelated exits, duplicate accumulation, lost statistics, incorrect last heartbeat | `bottles/tests/backend/integration/playtime/test_playtime_signals.py`, `bottles/tests/backend/integration/playtime/test_recovery.py`, `bottles/tests/backend/manager/test_playtime.py` |
| Installer list and dialog | Stale requests, ineffective filtering, preview leakage, shared controls, invalid progress, leaked timers | `bottles/tests/frontend/test_installer_list.py`, `bottles/tests/frontend/test_installer_dialog.py` |
| Playtime display and caching | Date boundaries, missing values, unescaped markup, ineffective or overbroad invalidation | `bottles/tests/frontend/test_playtime_service.py` |
| Event synchronization | Premature return, blocked completion, ineffective reset, unrelated event release | `bottles/tests/backend/state/test_events.py` |
| Schemas and test dependencies | Unconfigured schema IDs, missing schemas causing import crashes | `bottles/tests/frontend/test_settings_schema.py`, `tests/downstream/test_test_dependencies.py` |
| FVS cancellation and recovery | Running subprocesses, lost metadata, leftover blocks, premature lock release | `bottles/tests/fvs/test_repo.py` |

For important behavior changes, temporarily introduce a specific defect in a disposable worktree in the build environment, run the relevant suite, confirm the intended assertion fails and discard the worktree. Collection errors or missing dependencies do not demonstrate defect detection. Keep this focused on behavior rather than maintaining mutation scripts for every implementation detail.

## Flatpak development

The development manifest is `build-aux/com.usebottles.bottles.Devel.json`. Its runtime, permissions, extensions and application dependencies follow the release packaging. Development adds the Devel application ID/profile, local checkout source and offline test dependencies.

```sh
flatpak-builder --user --install-deps-from=flathub --force-clean --keep-build-dirs \
  --install build-dir build-aux/com.usebottles.bottles.Devel.json
flatpak run com.usebottles.bottles.Devel
```

Building the manifest also runs its Meson tests. Kept build directories contain logs under `.flatpak-builder/build/bottles*/_flatpak_build/meson-logs/`. After installing a native build, `meson test -C build --setup=installed --print-errorlogs` selects that installation instead of the build-tree package.

When Python requirements change, regenerate `build-aux/pypi-deps.yaml` or `build-aux/test-deps.json` using Flatpak dependency-generation tooling configured for the manifest's SDK and runtime. Test dependencies must match requirements.dev.txt; include their transitive dependencies. Review package versions, source URLs and checksums before building.

## Translations

Submit downstream translation changes to this repository. Upstream Weblate translations belong to the official project and do not automatically include downstream strings.

Keep `po/POTFILES` sorted and update it when translatable source files are added, moved or removed. Include the Blueprint sources and data templates used by the current build. `po/LINGUAS` lists shipped languages; keep corresponding `.po` files and the frontend language selector consistent.

After configuring a build, regenerate translation files with Meson:

```sh
meson compile -C build com.usebottles.bottles-pot
meson compile -C build com.usebottles.bottles-update-po
```

Remove obsolete entries after merging (for each actual `.po` file, excluding symlink aliases):

```sh
msgattrib --no-obsolete --output-file=po/<language>.po po/<language>.po
```

Review generated changes before committing. New or changed interface messages need usable translations in every supported language; empty or fuzzy entries are unfinished. Keep only messages used by the current sources, preserve valid translations and check contexts, plurals and format placeholders. Do not replace catalogs with unrelated upstream versions.

## Version metadata

The application version comes from `project(version:)` in `meson.build`; keep the root `VERSION` file in sync. Release notes belong in `data/com.usebottles.bottles.metainfo.xml.in.in`. A version change should describe the actual downstream release rather than imply it is an official upstream package.
