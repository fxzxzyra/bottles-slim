"""Use the actual compiled schema; never hide missing IDs with a Settings stub."""

import os
from gi.repository import Gio

from bottles.frontend.params import APP_ID


def test_compiled_schema_has_configured_application_id_and_keys():
    source = Gio.SettingsSchemaSource.new_from_directory(
        os.environ["GSETTINGS_SCHEMA_DIR"], None, False,
    )
    assert "@" not in APP_ID
    assert source.lookup("@APP_ID@", False) is None
    schema = source.lookup(APP_ID, False)
    assert schema is not None, f"{APP_ID} is missing from the compiled test schema"
    settings = Gio.Settings.new_full(schema, None, None)
    assert settings.get_default_value("window-width").unpack() == 880
    assert settings.get_default_value("window-height").unpack() == 640
    assert settings.get_default_value("playtime-enabled").get_type_string() == "b"
