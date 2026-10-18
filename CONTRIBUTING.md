# Contributing

Report downstream problems in this repository. Include the source commit, package format, distribution, expected and actual behavior, and reproduction steps. Remove personal information from logs before sharing them. Keep discussions respectful and focused on the issue.

See the [development guide](docs/development.md) for builds, Meson tests and translations, and [Linux layout](docs/linux-layout.md) for installation and runtime directories.

Keep changes focused and test observable behavior, including failure cases. Run the relevant Meson suites and describe the validation performed. Do not commit credentials, personal data or generated build artifacts.

The feature baseline is Bottles 65.4. Ordinary applications and games have equal priority; new features are reviewed individually, while fixes to retained functionality can be integrated directly. Follow the current design without adding old-version compatibility layers.

Preserve upstream authorship and license notices. For upstream changes, retain the original commit reference through cherry-pick attribution or an `Upstream-commit` / `Upstream-fix-from` trailer, and describe any adaptation.
