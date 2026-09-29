"""The JSON Schemas in spec/ and the reference helper agree on every fixture.

Needs the jsonschema package (CI installs it); skipped without it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_state import FIXTURES, ROOT, load_module, run

jsonschema = pytest.importorskip("jsonschema")

V2 = jsonschema.Draft202012Validator(json.loads((ROOT / "spec" / "state.schema.json").read_text(encoding="utf-8")))
V1 = jsonschema.Draft202012Validator(json.loads((ROOT / "spec" / "state.v1.schema.json").read_text(encoding="utf-8")))


def parsed_fixtures():
    out = []
    for path in sorted(FIXTURES.iterdir()):
        try:
            out.append((path.name, json.loads(path.read_bytes().decode("utf-8-sig"))))
        except ValueError:
            continue  # not JSON at all: nothing for a schema to say
    return out


@pytest.mark.parametrize("name,obj", parsed_fixtures(), ids=[n for n, _ in parsed_fixtures()])
def test_schema_and_helper_agree(name, obj):
    helper = load_module()
    kind = helper.load(FIXTURES / name).kind
    assert V2.is_valid(obj) == (kind == "v2"), name
    if isinstance(obj, dict) and obj.get("version") == 1:
        assert V1.is_valid(obj) == (kind == "v1"), name


def test_helper_output_validates_against_the_schema(tmp_path):
    sd = tmp_path / ".afkswitch"
    for args in (["afk", "--context", "é\nline"], ["back"], ["afk"]):
        run(sd, *args)
        V2.validate(json.loads((sd / "state.json").read_text(encoding="utf-8")))
