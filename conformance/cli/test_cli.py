"""The afkswitch command: the helper's transitions from any terminal, and a readable status."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts/afkswitch.py"


def run(state_dir: Path, *args: str):
    env = {**os.environ, "AFKSWITCH_STATE_DIR": str(state_dir), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, env=env, timeout=60)
    return done.returncode, done.stdout, done.stderr


def test_afk_and_back_are_the_helper_itself(tmp_path):
    code, out, _ = run(tmp_path, "afk", "--context", "sleep")
    first = json.loads(out)
    assert code == 0 and first["ok"] and first["status"] == "afk" and first["context"] == "sleep"
    code, out, _ = run(tmp_path, "back")
    second = json.loads(out)
    assert code == 0 and second["status"] == "available" and second["generation"] == first["generation"] + 1
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "available" and state["generation"] == second["generation"]


def test_status_reads_without_writing(tmp_path):
    code, out, _ = run(tmp_path, "status")
    assert code == 0 and out.startswith("no presence saved yet")
    assert not (tmp_path / "state.json").exists()
    run(tmp_path, "afk", "--context", "at work")
    code, out, _ = run(tmp_path, "status")
    assert code == 0 and out.startswith("AFK since ") and '"at work"' in out and out.rstrip().endswith("g1")
    code, out, _ = run(tmp_path, "status", "--json")
    assert code == 0 and json.loads(out)["status"] == "afk"


def test_helper_refusals_keep_their_exit_codes(tmp_path):
    code, out, _ = run(tmp_path, "afk", "--context", "bad\r\nline")
    assert code == 1 and json.loads(out)["ok"] is False
    assert not (tmp_path / "state.json").exists()


def test_unknown_command_is_a_usage_error(tmp_path):
    for args in ([], ["bogus"], ["status", "--verbose"]):
        code, out, err = run(tmp_path, *args)
        assert code == 2 and out == "" and err.startswith("usage: afkswitch")


def test_future_state_is_reported_not_rewritten(tmp_path):
    (tmp_path / "state.json").write_text('{"version": 99}', encoding="utf-8")
    code, out, _ = run(tmp_path, "status")
    assert code == 1 and json.loads(out)["error"] == "unsupported_state_version"
    assert (tmp_path / "state.json").read_text(encoding="utf-8") == '{"version": 99}'
