"""Read-only lifecycle hooks against synthetic state and transcripts, without hosts."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/presence_hook.py"
spec = importlib.util.spec_from_file_location("presence_hook_tests", SCRIPT)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


@pytest.fixture
def files(tmp_path, monkeypatch):
    sd = tmp_path / "state"
    sd.mkdir()
    monkeypatch.setenv("AFKSWITCH_STATE_DIR", str(sd))
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")
    return sd / "state.json", transcript


def state(path, status="afk", generation=5, context="work\n夜\t"):
    path.write_text(json.dumps({"version": 2, "status": status, "generation": generation,
                                "since": "2026-09-30T12:00:00Z",
                                "context": context if status == "afk" else None}), encoding="utf-8")


def call(files, monkeypatch, host="claude", event="UserPromptSubmit", source=None, raw=None):
    path, transcript = files
    original = path.read_bytes() if path.exists() else None
    digest = hashlib.sha256(original).hexdigest() if original is not None else None
    names = sorted(p.name for p in path.parent.iterdir())
    data = {"transcript_path": str(transcript), "session_id": "synthetic"}
    if source is not None:
        data["source"] = source
    stdout, stderr = io.StringIO(), io.StringIO()
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdin", io.StringIO(json.dumps(data) if raw is None else raw))
        patch.setattr(sys, "stdout", stdout)
        patch.setattr(sys, "stderr", stderr)
        assert hook.main(["--host", host, "--event", event]) == 0
    assert stderr.getvalue() == ""
    assert sorted(p.name for p in path.parent.iterdir()) == names
    if digest is not None:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    else:
        assert not path.exists()
    return json.loads(stdout.getvalue()) if stdout.getvalue() else None


@pytest.mark.parametrize("host", ["claude", "codex"])
@pytest.mark.parametrize("source", ["startup", "clear"])
def test_startup_only_afk(files, monkeypatch, host, source):
    path, _ = files
    state(path)
    result = call(files, monkeypatch, host, "SessionStart", source)
    helper = hook.load_helper()
    assert result == {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                            "additionalContext": helper.core_event("afk", 5, "work\n夜\t")}}
    state(path, "available")
    assert call(files, monkeypatch, host, "SessionStart", source) is None


@pytest.mark.parametrize("host", ["claude", "codex"])
@pytest.mark.parametrize("event,source", [("UserPromptSubmit", None), ("SessionStart", "resume"),
                                         ("SessionStart", "compact"), ("SessionStart", "fork")])
def test_generation_dedup_and_return(files, monkeypatch, host, event, source):
    path, transcript = files
    transcript.write_text(json.dumps({"message": "[AFKSwitch g5]"}) + "\n", encoding="utf-8")
    state(path)
    assert call(files, monkeypatch, host, event, source) is None
    state(path, generation=6)
    result = call(files, monkeypatch, host, event, source)
    assert result["hookSpecificOutput"] == {"hookEventName": event,
                                           "additionalContext": hook.load_helper().core_event("afk", 6, "work\n夜\t")}
    state(path, "available", 7)
    result = call(files, monkeypatch, host, event, source)
    assert result["hookSpecificOutput"]["additionalContext"] == hook.load_helper().core_event("available", 7, None)


@pytest.mark.parametrize("host", ["claude", "codex"])
def test_reset_is_applied_once_and_last_marker_wins(files, monkeypatch, host):
    path, transcript = files
    transcript.write_text('[AFKSwitch g30]\n', encoding="utf-8")
    state(path, generation=1)
    result = call(files, monkeypatch, host)
    assert result["hookSpecificOutput"]["additionalContext"].startswith("[AFKSwitch g1 reset]\n")
    transcript.write_text('[AFKSwitch g30]\n[AFKSwitch g1 reset]\n', encoding="utf-8")
    assert call(files, monkeypatch, host) is None
    state(path, generation=2)
    assert call(files, monkeypatch, host)["hookSpecificOutput"]["additionalContext"].startswith("[AFKSwitch g2]\n")


def test_v1_reset_once_without_disk_migration(files, monkeypatch):
    path, transcript = files
    path.write_bytes((ROOT / "conformance/state/fixtures/valid-v1-afk-sleep.json").read_bytes())
    transcript.write_text("[AFKSwitch g1]\n", encoding="utf-8")
    assert call(files, monkeypatch)["hookSpecificOutput"]["additionalContext"].startswith("[AFKSwitch g1 reset]\n")
    transcript.write_text("[AFKSwitch g1 reset]\n", encoding="utf-8")
    assert call(files, monkeypatch) is None


@pytest.mark.parametrize("host,event", [("claude", "UserPromptSubmit"), ("codex", "UserPromptSubmit"), ("agy", "PreInvocation")])
@pytest.mark.parametrize("raw", [None, b"", b"not json", b'{"version":99}', b'{"version":2}', b"\xff"])
def test_missing_invalid_future_state_is_silent(files, monkeypatch, host, event, raw):
    if raw is not None:
        files[0].write_bytes(raw)
    assert call(files, monkeypatch, host, event) is None


@pytest.mark.parametrize("raw", ["", "broken", "[]", "null", "123", '"text"'])
def test_bad_stdin_is_silent(files, monkeypatch, raw):
    state(files[0])
    assert call(files, monkeypatch, raw=raw) is None


def test_agy_ephemeral_only_afk(files, monkeypatch):
    path, transcript = files
    state(path)
    transcript.unlink()  # Agy never opens a transcript.
    result = call(files, monkeypatch, "agy", "PreInvocation", raw='{"sessionId":"synthetic","userPrompt":"hi"}')
    assert result == {"injectSteps": [{"ephemeralMessage": hook.load_helper().core_event("afk", 5, "work\n夜\t")}]}
    state(path, "available")
    assert call(files, monkeypatch, "agy", "PreInvocation") is None


def test_bounded_tail_and_marker_at_end(files, monkeypatch):
    path, transcript = files
    state(path)
    transcript.write_bytes(b"[AFKSwitch g5]\n" + b"x" * hook.TAIL_BYTES)
    assert call(files, monkeypatch) is not None  # Old marker lies outside the bounded tail.
    with transcript.open("ab") as stream:
        stream.write(b'\n{"message":"[AFKSwitch g5]"}\n')
    assert call(files, monkeypatch) is None


def test_unreadable_transcript_and_state_fail_open(files, monkeypatch):
    state(files[0])
    files[1].unlink()
    assert call(files, monkeypatch) is None
    with monkeypatch.context() as patch:
        patch.setattr(hook, "load_helper", lambda: (_ for _ in ()).throw(PermissionError("synthetic")))
        assert call(files, patch) is None


@pytest.mark.parametrize("host,event,raw", [("claude", "SessionStart", '{"source":"startup"}'),
                                         ("codex", "UserPromptSubmit", '{}'),
                                         ("agy", "PreInvocation", '{}'),
                                         ("claude", "UserPromptSubmit", 'broken')])
def test_real_cli_json_and_fail_open(files, host, event, raw):
    state(files[0])
    before = files[0].read_bytes()
    proc = subprocess.run([sys.executable, "-B", str(SCRIPT), "--host", host, "--event", event],
                          input=raw, capture_output=True, text=True, env=os.environ.copy())
    assert proc.returncode == 0 and proc.stderr == ""
    if raw == "broken":
        assert proc.stdout == ""
    else:
        assert isinstance(json.loads(proc.stdout), dict)
    assert files[0].read_bytes() == before


def test_bad_arguments_are_silent(files, monkeypatch, capsys):
    state(files[0])
    for args in ([], ["--help"], ["--host", "unknown", "--event", "SessionStart"]):
        with monkeypatch.context() as patch:
            patch.setattr(sys, "stdin", io.StringIO("{}"))
            assert hook.main(args) == 0
    assert capsys.readouterr() == ("", "")
