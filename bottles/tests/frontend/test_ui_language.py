import os
from pathlib import Path

import pytest

from bottles.frontend.utils.localization import (
    UI_LANGUAGES,
    apply_ui_language,
    get_ui_language_environment,
)


def test_ui_languages_match_shipped_catalogs():
    linguas = (
        (Path(__file__).resolve().parents[3] / "po" / "LINGUAS")
        .read_text()
        .splitlines()
    )
    codes = [code for code, _name in UI_LANGUAGES]

    assert codes[:2] == ["system", "en"]
    assert set(codes[2:]) == set(linguas)
    assert len(codes) == len(set(codes))


@pytest.mark.parametrize("language", ["en", "lv"])
def test_ui_language_overrides_messages(monkeypatch, language):
    monkeypatch.setenv("LANGUAGE", "ja")

    apply_ui_language(language)

    assert os.environ["LANGUAGE"] == language


def test_system_ui_language_keeps_environment(monkeypatch):
    monkeypatch.setenv("LANGUAGE", "ja")

    apply_ui_language("system")

    assert os.environ["LANGUAGE"] == "ja"


def test_unknown_ui_language_keeps_environment(monkeypatch):
    monkeypatch.setenv("LANGUAGE", "de")

    apply_ui_language("not-a-language")

    assert os.environ["LANGUAGE"] == "de"


def test_relaunch_restores_inherited_language(monkeypatch):
    monkeypatch.setattr("bottles.frontend.utils.localization._INHERITED_LANGUAGE", "ja")
    monkeypatch.setenv("LANGUAGE", "en")

    environment = get_ui_language_environment("system")

    assert environment["LANGUAGE"] == "ja"
    assert os.environ["LANGUAGE"] == "en"


def test_relaunch_removes_application_override(monkeypatch):
    monkeypatch.setattr("bottles.frontend.utils.localization._INHERITED_LANGUAGE", None)
    monkeypatch.setenv("LANGUAGE", "en")

    environment = get_ui_language_environment("system")

    assert "LANGUAGE" not in environment
    assert os.environ["LANGUAGE"] == "en"


def test_relaunch_uses_selected_language(monkeypatch):
    monkeypatch.setenv("LANGUAGE", "ja")

    environment = get_ui_language_environment("en")

    assert environment["LANGUAGE"] == "en"
    assert os.environ["LANGUAGE"] == "ja"


def test_relaunch_keeps_unknown_language(monkeypatch):
    monkeypatch.setenv("LANGUAGE", "de")

    environment = get_ui_language_environment("not-a-language")

    assert environment["LANGUAGE"] == "de"
    assert os.environ["LANGUAGE"] == "de"


def test_relaunch_does_not_restore_gtk_theme(monkeypatch):
    monkeypatch.setenv("GTK_THEME", "broken-theme")

    environment = get_ui_language_environment("system")

    assert "GTK_THEME" not in environment
    assert os.environ["GTK_THEME"] == "broken-theme"


def test_startup_binds_python_and_gtk_to_the_same_catalog_before_loading_ui(tmp_path):
    import subprocess
    import sys
    import textwrap

    # Supply a message-only locale rather than requiring a system language pack.
    # Its ASCII encoding keeps this test about domain/catalog lookup; GTK and
    # Python still load the real MO file and must produce the same translation.
    charmap = tmp_path / "charmap"
    charmap.write_text(
        '<code_set_name> "ASCII"\n<mb_cur_min> 1\n<mb_cur_max> 1\n'
        '<escape_char> /\nCHARMAP\n'
        + "".join(f"<U{code:04X}> /x{code:02X}\n" for code in range(128))
        + 'END CHARMAP\n'
    )
    definition = tmp_path / "messages.locale"
    definition.write_text(
        'LC_MESSAGES\nyesexpr "^[yY]"\nnoexpr "^[nN]"\n'
        'yesstr "yes"\nnostr "no"\nEND LC_MESSAGES\n'
    )
    locale_root = tmp_path / "system-locales"
    message_locale = locale_root / "bottles_TEST"
    message_locale.mkdir(parents=True)
    compiled = subprocess.run([
        "localedef", "--no-archive", "--quiet", "-c",
        "-f", str(charmap), "-i", str(definition), str(message_locale),
    ], capture_output=True, text=True, timeout=30)
    # localedef returns 1 for the deliberately omitted, unused categories.
    assert compiled.returncode in (0, 1), compiled.stdout + compiled.stderr
    assert (message_locale / "LC_MESSAGES/SYS_LC_MESSAGES").is_file(), compiled.stderr

    po = tmp_path / "test.po"
    po.write_text(
        'msgid ""\nmsgstr "Content-Type: text/plain; charset=UTF-8\\nLanguage: fr\\n"\n\n'
        'msgid "Early UI label"\nmsgstr "Texte traduit"\n'
    )
    locale_dir = tmp_path / "locale"
    mo = locale_dir / "fr/LC_MESSAGES/com.usebottles.bottles.mo"
    mo.parent.mkdir(parents=True)
    subprocess.run(["msgfmt", "-o", str(mo), str(po)], check=True)
    script = textwrap.dedent('''        import sys
        from bottles.frontend.utils.localization import configure_translations
        configure_translations(sys.argv[1], "fr")
        from gettext import gettext as _
        assert _("Early UI label") == "Texte traduit"
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        Gtk.init()
        builder = Gtk.Builder.new_from_string(
            '<interface domain="com.usebottles.bottles">'
            '<object class="GtkLabel" id="label">'
            '<property name="label" translatable="yes">Early UI label</property>'
            '</object></interface>', -1)
        actual = builder.get_object("label").get_label()
        assert actual == "Texte traduit", repr(actual)
    ''')
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("LC_"):
            env.pop(key)
    env.update(LANG="C", LC_MESSAGES="bottles_TEST", LOCPATH=str(locale_root),
               PYTHONCOERCECLOCALE="0")
    env["PYTHONPATH"] = os.environ.get("BOTTLES_TEST_PACKAGE_ROOT", str(Path(__file__).resolve().parents[3]))
    completed = subprocess.run([sys.executable, "-c", script, str(locale_dir)],
                               cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr
