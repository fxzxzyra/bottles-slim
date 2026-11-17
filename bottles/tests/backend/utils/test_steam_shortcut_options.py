"""Retained Steam metadata and ordinary shortcut launch option handling."""

import io

from bottles.backend.utils.steam import SteamUtils


def test_vdf_roundtrip_retains_shortcut_fields():
    data = {"shortcuts": {"0": {"appname": "Office", "exe": "bottles-cli", "LaunchOptions": "run -b Office"}}}
    stream = io.StringIO()
    SteamUtils.to_vdf(data, stream)
    assert SteamUtils.parse_vdf(stream.getvalue()) == data
    assert SteamUtils.parse_acf(stream.getvalue()) == data


def test_launch_options_preserve_environment_wrapper_and_arguments():
    prefix, arguments, environment = SteamUtils.handle_launch_options(
        "env LANG=en_US.UTF-8 gamescope %command% --fullscreen"
    )
    assert prefix == "env gamescope"
    assert arguments.strip() == "--fullscreen"
    assert environment == {"LANG": "en_US.UTF-8"}
