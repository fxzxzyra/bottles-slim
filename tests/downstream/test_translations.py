"""Keep runtime messages extractable when UI source files move or are added."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_translation_sources_exist_and_are_sorted():
    paths = [line for line in (ROOT / "po/POTFILES").read_text().splitlines()
             if line and not line.startswith("#")]
    assert paths == sorted(set(paths))
    assert all((ROOT / path).is_file() for path in paths)


def test_all_python_and_blueprint_translation_sources_are_listed():
    listed = set((ROOT / "po/POTFILES").read_text().splitlines())
    missing = []
    for directory in ("bottles/backend", "bottles/frontend"):
        for path in (ROOT / directory).rglob("*"):
            if path.suffix not in (".py", ".blp"):
                continue
            source = path.read_text()
            if path.suffix == ".blp":
                translated = "_(" in source
            else:
                translated = any(
                    isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("_", "gettext", "ngettext", "pgettext", "npgettext")
                    for node in ast.walk(ast.parse(source))
                )
            if translated and path.relative_to(ROOT).as_posix() not in listed:
                missing.append(path.relative_to(ROOT).as_posix())
    assert missing == []


def _catalog_entries(path):
    import re

    entries = {}
    data, field = {}, None
    def finish():
        if "msgid" not in data:
            return
        key = (data.get("msgctxt"), data["msgid"])
        assert key not in entries, (path, key)
        entries[key] = dict(data)
    for line in path.read_text().splitlines() + [""]:
        assert not line.startswith("#~"), f"Obsolete translation in {path}"
        if not line:
            finish()
            data, field = {}, None
        elif line.startswith("#,"):
            data.setdefault("_flags", []).extend(flag.strip() for flag in line[2:].split(","))
        elif line.startswith("#"):
            continue
        elif line.startswith('"'):
            assert field is not None, path
            data[field] += ast.literal_eval(line)
        else:
            match = re.fullmatch(r'(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?) (".*")', line)
            assert match, (path, line)
            field = match[1]
            data[field] = ast.literal_eval(match[2])
    return entries


def test_language_catalogs_match_the_template_without_obsolete_entries():
    import re

    template = _catalog_entries(ROOT / "po/bottles.pot")
    for path in sorted((ROOT / "po").glob("*.po")):
        if path.is_symlink():
            continue
        catalog = _catalog_entries(path)
        assert catalog.keys() == template.keys(), path
        header = catalog[None, ""]["msgstr"]
        match = re.search(r"nplurals\s*=\s*(\d+)", header)
        assert match, path
        expected = {f"msgstr[{index}]" for index in range(int(match[1]))}
        for key, value in catalog.items():
            assert value.get("msgid_plural") == template[key].get("msgid_plural"), (path, key)
            if "msgid_plural" in value:
                assert {field for field in value if field.startswith("msgstr")} == expected, (path, key)


def test_python_messages_are_literals_before_interpolation():
    for directory in ("bottles/backend", "bottles/frontend"):
        for path in (ROOT / directory).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                    continue
                call = node.func.id
                if call not in ("_", "gettext", "ngettext", "pgettext", "npgettext"):
                    continue
                count = {"ngettext": 2, "pgettext": 2, "npgettext": 3}.get(call, 1)
                assert len(node.args) >= count, (path, node.lineno)
                assert all(isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                           for arg in node.args[:count]), (path, node.lineno)


def test_runner_registration_and_import_actions_have_usable_translations_in_every_language():
    messages = (
        "Register Runner", "Edit Runner", "Register an Existing Container",
        "Register", "Choose Directory…", "No Wine Prefixes Found",
        "No Programs in Library", "Create",
    )
    for path in sorted((ROOT / "po").glob("*.po")):
        catalog = _catalog_entries(path)
        for message in messages:
            entry = catalog[None, message]
            assert entry.get("msgstr", "").strip(), (path, message)
            assert "fuzzy" not in entry.get("_flags", []), (path, message)


def test_application_name_is_not_translatable_metadata():
    import xml.etree.ElementTree as ET
    metadata = ET.parse(ROOT / "data/com.usebottles.bottles.metainfo.xml.in")
    name = metadata.find("name")
    assert name.text == "Bottles"
    assert name.get("translate") == "no"


def test_new_script_picker_titles_are_translated_in_all_shipped_languages():
    for language in (ROOT / "po/LINGUAS").read_text().split():
        catalog = _catalog_entries(ROOT / "po" / (language + ".po"))
        for message in ("Select Pre-run Script", "Select Post-run Script"):
            entry = catalog[None, message]
            assert entry["msgstr"].strip(), (language, message)
            assert "fuzzy" not in entry.get("_flags", []), (language, message)


def test_chinese_catalogs_have_no_missing_or_unreviewed_translations():
    for language in ("zh_Hans", "zh_Hant"):
        for key, entry in _catalog_entries(ROOT / "po" / (language + ".po")).items():
            if not key[1]:
                continue
            assert "fuzzy" not in entry.get("_flags", []), (language, key)
            for field, value in entry.items():
                if field.startswith("msgstr"):
                    assert value.strip(), (language, key, field)
                    assert "酒瓶" not in value and "瓶子" not in value, (language, key)


def test_primary_actions_and_terms_are_translated_in_all_supported_languages():
    messages = ("Log", "Keyboard Shortcuts", "Cache", "Usage Time Tracking", "Preset", "Wine Containers",
                "System", "User", "System Runners", "User Runners")
    for language in (ROOT / "po/LINGUAS").read_text().split():
        catalog = _catalog_entries(ROOT / "po" / (language + ".po"))
        for message in messages:
            entry = catalog[None, message]
            assert entry["msgstr"].strip(), (language, message)
            assert "fuzzy" not in entry.get("_flags", []), (language, message)
        assert "Bottles" in catalog[None, "About Bottles"]["msgstr"], language
        assert "Wine" in catalog[None, "Wine Containers"]["msgstr"], language


def test_translated_format_arguments_match_the_message():
    import re
    import string

    def braces(value):
        return sorted(str(name) for _, name, _, _ in string.Formatter().parse(value) if name is not None)

    for path in sorted((ROOT / "po").glob("*.po")):
        if path.is_symlink():
            continue
        for key, entry in _catalog_entries(path).items():
            if not key[1]:
                continue
            for field, value in entry.items():
                if not field.startswith("msgstr") or not value:
                    continue
                source = entry.get("msgid_plural", key[1]) if field not in ("msgstr", "msgstr[0]") else key[1]
                assert braces(source) == braces(value), (path, key, field)
                assert re.findall(r"%(?:\([^)]+\))?[sdf]", source) == re.findall(r"%(?:\([^)]+\))?[sdf]", value), (path, key, field)


def test_application_name_is_not_reused_as_a_translated_container_title():
    catalog = _catalog_entries(ROOT / "po/bottles.pot")
    assert (None, "Bottles") not in catalog
    assert (None, "Wine Containers") in catalog


def test_runner_translations_do_not_describe_athletes():
    import re
    forbidden = {
        "de": r"Läufer", "fr": r"coureur", "es": r"corredor", "it": r"corridor",
        "pt": r"corredor", "pt_BR": r"corredor", "hi": r"धावक",
        "nl": r"hardloper", "fi": r"juoksij", "sv": r"löpare", "tr": r"koşucu",
    }
    for language, pattern in forbidden.items():
        for key, entry in _catalog_entries(ROOT / "po" / (language + ".po")).items():
            if re.search(r"\brunners?\b", key[1], re.I):
                assert not re.search(pattern, entry.get("msgstr", ""), re.I), (language, key)


def test_appstream_is_not_a_translation_source():
    import xml.etree.ElementTree as ET
    sources = (ROOT / "po/POTFILES").read_text().splitlines()
    assert not any("metainfo.xml" in source for source in sources)
    metadata = ET.parse(ROOT / "data/com.usebottles.bottles.metainfo.xml.in")
    assert not any("{http://www.w3.org/XML/1998/namespace}lang" in element.attrib
                   for element in metadata.iter())
