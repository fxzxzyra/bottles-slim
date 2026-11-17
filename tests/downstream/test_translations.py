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
        "Register Runner", "Edit Runner", "Register an Existing Bottle",
        "Register", "Choose Directory…", "No Wine Prefixes Found",
        "No Programs in Library", "Manage Runners…",
    )
    for path in sorted((ROOT / "po").glob("*.po")):
        catalog = _catalog_entries(path)
        for message in messages:
            entry = catalog[None, message]
            assert entry.get("msgstr", "").strip(), (path, message)
            assert "fuzzy" not in entry.get("_flags", []), (path, message)
