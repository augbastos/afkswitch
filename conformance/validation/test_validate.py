"""Mutation checks for standalone helpers and generated capability table drift."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("mutation,message", [
    ("helper", "byte-identical"),
    ("table", "README.md is out of date with adapters/capabilities.json"),
])
def test_validator_rejects_drift_in_an_isolated_copy(tmp_path, mutation, message):
    # Only these public source files are needed before the deliberate validation fault.
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in ("skills", "assets", "spec", ".claude-plugin", ".codex-plugin", "adapters", "docs", "hooks"):
        shutil.copytree(ROOT / name, repo / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("plugin.json", "CHANGELOG.md", "README.md"):
        shutil.copy2(ROOT / name, repo / name)
    (repo / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/validate.py", repo / "scripts/validate.py")
    if mutation == "helper":
        path = repo / "skills/back/scripts/afkswitch_state.py"
        path.write_bytes(path.read_bytes() + b"\n# deliberate drift\n")
    else:
        path = repo / "README.md"
        path.write_text(path.read_text(encoding="utf-8").replace("| Claude Code | yes |", "| Claude Code | no |"), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(repo / "scripts/validate.py")], capture_output=True,
                          text=True, env=dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path)))
    assert proc.returncode != 0 and message in proc.stderr
