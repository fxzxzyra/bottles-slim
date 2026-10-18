<div align="center">
  <img src="https://raw.githubusercontent.com/bottlesdevs/Bottles/main/data/icons/hicolor/scalable/apps/com.usebottles.bottles.svg" width="64">
  <h1 align="center">Bottles</h1>
  <p align="center">Run Windows Software on Linux</p>
</div>

<br/>

<div align="center">
  <a href="https://flathub.org/apps/com.usebottles.bottles"><img alt="Flathub" src="https://img.shields.io/flathub/downloads/com.usebottles.bottles" /></a>
  <a href="https://hosted.weblate.org/engage/bottles"><img src="https://hosted.weblate.org/widgets/bottles/-/bottles/svg-badge.svg" /></a>
  <a href="https://www.codefactor.io/repository/github/bottlesdevs/bottles/overview/main"><img src="https://www.codefactor.io/repository/github/bottlesdevs/bottles/badge/main" /></a>
  <a href="https://github.com/bottlesdevs/Bottles/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue.svg"></a>
  <br>
  <a href="https://stopthemingmy.app" title="Please do not theme this app"><img src="https://stopthemingmy.app/badge.svg"></a>

  <hr />

  <a href="https://docs.usebottles.com">Documentation</a> ·
  <a href="https://github.com/orgs/bottlesdevs/discussions">Forums</a> ·
  <a href="https://discord.gg/wF4JAdYrTR">Discord</a>
</div>

<br/>

![Bottles Dark](docs/screenshot-dark.png#gh-dark-mode-only)![Bottles Light](docs/screenshot-light.png#gh-light-mode-only)

## Installation

<a href='https://flathub.org/apps/com.usebottles.bottles'><img width='240' alt='Download on Flathub' src='https://flathub.org/assets/badges/flathub-badge-en.png'/></a>

## Contributing

Refer to the [Contributing](CONTRIBUTING.md) page.

## Building

⚠️ Be sure to backup all your data before testing experimental builds of Bottles!

Use the development manifest in this repository when working on Bottles. To build a stable release locally, use the manifest maintained by Flathub.

### Development Flatpak

1. Install [`org.flatpak.Builder`](https://github.com/flathub/org.flatpak.Builder) from Flathub
2. Clone `https://github.com/bottlesdevs/Bottles.git` (or your fork)
3. Run `flatpak run org.flatpak.Builder --install --install-deps-from=flathub --default-branch=master --force-clean build-dir build-aux/com.usebottles.bottles.Devel.json` in the terminal from the root of the repository (use `--user` if necessary)
4. Run `flatpak run com.usebottles.bottles.Devel` to launch it

### Release Flatpak

The authoritative manifest for the stable package is maintained in the [Flathub repository](https://github.com/flathub/com.usebottles.bottles). It defines the Bottles source, dependencies, runtime, and permissions used for each release.

1. Install [`org.flatpak.Builder`](https://github.com/flathub/org.flatpak.Builder) from Flathub
2. Clone `https://github.com/flathub/com.usebottles.bottles.git`
3. Run the following command from the root of the cloned repository:

   ```shell
   flatpak run org.flatpak.Builder \
     --user \
     --install \
     --install-deps-from=flathub \
     --default-branch=local \
     --force-clean \
     build-dir \
     com.usebottles.bottles.yml
   ```

4. Run `flatpak run com.usebottles.bottles//local` to launch it

The `local` branch is installed alongside the Flathub branch. Both use the same application ID and Bottles data directory, so changes made by either build affect the other. To build an older release, use `git log -- com.usebottles.bottles.src.yaml` to find and check out its Flathub commit before running the build command.

### Meson

Since Bottles is primarily and officially distributed as a Flatpak, we only provide instructions to directly build it inside a Flatpak environment:

1. Download and install the latest build of Bottles: [bottles-x86_64.zip](https://nightly.link/bottlesdevs/Bottles/workflows/build_flatpak/main/bottles-x86_64.zip). Unzip it, and run `flatpak install bottles.flatpak` (use `--user` if necessary)
2. Run `flatpak run -d --filesystem=$PWD --command=bash com.usebottles.bottles.Devel` from the root of the repository, followed by `./build-aux/install.sh`. This will build Bottles and install it under the `build/` directory.
3. Run `./build/bin/bottles` to launch Bottles

Due to GNOME Builder limitations, Builder cannot build Bottles for the time being; see [GNOME/gnome-builder#2061](https://gitlab.gnome.org/GNOME/gnome-builder/-/issues/2061) for more context. This is the best workaround we can provide.

## Code of Conduct
This project follows the [GNOME Code of Conduct](https://wiki.gnome.org/Foundation/CodeOfConduct). You are expected to follow it in all Bottles spaces, such as this repository, the project's social media, messenger chats and forums. Bigotry and harassment will not be tolerated.
