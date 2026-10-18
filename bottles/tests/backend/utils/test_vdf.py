"""Text VDF manifests may contain several tokens on a single line."""

import pytest

from bottles.backend.utils import vdf


@pytest.mark.parametrize("text, expected", [
    ('"manifest" { "compatmanager_layer_name" "proton" }',
     {"manifest": {"compatmanager_layer_name": "proton"}}),
    ('"outer" { "a" { "b" "c" } "d" {} } "tail" "end"',
     {"outer": {"a": {"b": "c"}, "d": {}}, "tail": "end"}),
    ('"a" "{not a block}" "b" "//not a comment" // comment\n"c" "d"',
     {"a": "{not a block}", "b": "//not a comment", "c": "d"}),
    ('"block"\n{\n"key" "line one\nline two"\n}\n',
     {"block": {"key": "line one\nline two"}}),
    ('"block" { "one" "1" } "block" { "two" "2" }',
     {"block": {"one": "1", "two": "2"}}),
    ('bare { key value }', {"bare": {"key": "value"}}),
])
def test_text_layout(text, expected):
    assert vdf.loads(text) == expected


@pytest.mark.parametrize("text", ['"block" {', '}', '{ "key" "value" }',
                                 '"key" "unfinished', '"block" "value" }'])
def test_malformed_blocks_and_quotes(text):
    with pytest.raises(SyntaxError):
        vdf.loads(text)


def test_duplicate_blocks_can_replace_instead_of_merge():
    assert vdf.loads('"a" { "b" "1" } "a" { "c" "2" }',
                     merge_duplicate_keys=False) == {"a": {"c": "2"}}
