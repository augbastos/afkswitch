"""Tests for the notify / fan-in reference checker: every example transcript gets the verdict it declares."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import checker  # noqa: E402

FILES = [HERE / "notify" / "scenarios.json", HERE / "fan-in" / "scenarios.json"]
SCENARIOS = [s for f in FILES for s in json.loads(f.read_text(encoding="utf-8"))["scenarios"]]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[f"{s['kind']}/{s['name']}" for s in SCENARIOS])
def test_example_transcript_gets_its_declared_verdict(scenario):
    violations = checker.check(scenario)
    if scenario["expect"] == "pass":
        assert violations == []
    else:
        assert scenario["violations"], "a failing example must name the violations it demonstrates"
        codes = {v.split(":", 1)[0] for v in violations}
        assert set(scenario["violations"]) <= codes, violations


def test_every_level_has_passing_and_failing_examples():
    for kind in ("notify", "fan-in"):
        verdicts = {s["expect"] for s in SCENARIOS if s["kind"] == kind}
        assert verdicts == {"pass", "fail"}


@pytest.mark.parametrize("known,generation,reset,action", [
    (None, 1, False, "apply"), (4, 5, False, "apply"), (5, 5, False, "repeat"),
    (6, 5, False, "ignore-stale"), (9, 1, True, "apply"), (5, 5, True, "apply"),
])
def test_receiver_action(known, generation, reset, action):
    assert checker.receiver_action(known, generation, reset) == action


def test_parse_reply_needs_the_generation_header():
    assert checker.parse_reply("afkswitch-status g3\nneeds-human: none")["generation"] == 3
    assert checker.parse_reply("dir: x\nneeds-human: none") is None


def test_cli_exits_nonzero_for_a_failing_recording(tmp_path):
    failing = next(s for s in SCENARIOS if s["expect"] == "fail")
    recording = dict(failing)
    recording.pop("expect")
    path = tmp_path / "recording.json"
    path.write_text(json.dumps({"scenarios": [recording]}), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(HERE / "checker.py"), str(path)], capture_output=True, text=True)
    assert proc.returncode == 1 and "FAIL" in proc.stdout


def test_cli_accepts_the_bundled_examples():
    proc = subprocess.run([sys.executable, str(HERE / "checker.py"), *map(str, FILES)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
