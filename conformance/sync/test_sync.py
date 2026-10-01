"""Generic local lifecycle sync against real isolated state, never a model."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "adapters/generic/presence_sync.py"
spec = importlib.util.spec_from_file_location("presence_sync_tests", SYNC)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


@pytest.fixture
def sd(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    monkeypatch.setenv("AFKSWITCH_STATE_DIR", str(directory))
    return directory


def test_new_session_reconciles_afk_then_return(sd):
    afk = sync.helper.transition("afk", "  work\n夜\t")
    first = sync.check(0)
    assert first["changed"] is True and first["reset"] is False
    assert first["event"] == sync.helper.core_event("afk", afk["generation"], afk["context"])
    before = (sd / "state.json").read_bytes()
    same = sync.check(first["generation"], first["epoch"])
    assert same["changed"] is False and same["event"] is None
    assert (sd / "state.json").read_bytes() == before
    back = sync.helper.transition("back", "review now")
    returned = sync.check(first["generation"], first["epoch"])
    assert returned["generation"] == 2 and returned["reset"] is False
    assert "status: available\ncontext: none\n" in returned["event"]
    assert "review now" not in returned["event"] and back["event_context"] == "review now"


def test_missing_after_prior_marks_epoch_without_ending_afk(sd):
    sync.helper.transition("afk", "work")
    first = sync.check()
    (sd / "state.json").unlink()
    missing = sync.check(first["generation"], first["epoch"])
    assert missing == {"changed": True, "event": None, "generation": None, "reset": True, "epoch": "missing"}
    assert sync.check(first["generation"], missing["epoch"])["changed"] is False
    sync.helper.transition("afk", "work")
    recreated = sync.check(first["generation"], missing["epoch"])
    assert recreated["reset"] is True and recreated["changed"] is True
    assert "[AFKSwitch g1 reset]" in recreated["event"]
    assert sync.check(recreated["generation"], recreated["epoch"])["changed"] is False


def test_unobserved_same_generation_recreation_detected_by_checkpoint(sd):
    sync.helper.transition("afk", "work")
    first = sync.check()
    # Atomic replacement changes identity even with identical content and timestamps.
    sync.helper.write_atomic(sd / "state.json", sync.helper.load(sd / "state.json").state)
    recreated = sync.check(first["generation"], first["epoch"])
    assert recreated["reset"] is True and recreated["changed"] is True


def test_authoritative_lower_generation_is_reset_not_stale_push(sd):
    sync.helper.transition("afk", "work")
    result = sync.check(30)
    assert result["reset"] is True and result["generation"] == 1


@pytest.mark.parametrize("raw,epoch", [(b"", "empty"), (b"not json", "malformed")])
def test_invalid_state_does_not_write_or_infer_available(sd, raw, epoch):
    sd.mkdir()
    (sd / "state.json").write_bytes(raw)
    result = sync.check(30)
    assert result == {"changed": True, "event": None, "generation": None, "reset": True, "epoch": epoch}
    assert (sd / "state.json").read_bytes() == raw
    assert list(sd.iterdir()) == [sd / "state.json"]


def test_initial_missing_is_unknown_and_read_only(sd):
    assert sync.check() == {"changed": False, "event": None, "generation": None, "reset": False, "epoch": "missing"}
    assert not sd.exists()


def test_v1_read_migration_is_single_reset(sd):
    sd.mkdir()
    raw = (ROOT / "conformance/state/fixtures/valid-v1-afk-sleep.json").read_bytes()
    (sd / "state.json").write_bytes(raw)
    first = sync.check(30)
    assert first["reset"] is True and first["generation"] == 1
    assert sync.check(1, first["epoch"])["changed"] is False
    assert (sd / "state.json").read_bytes() == raw


def test_future_version_refused_via_import_and_cli(sd):
    sd.mkdir()
    raw = b'{"version": 99}'
    (sd / "state.json").write_bytes(raw)
    with pytest.raises(sync.helper.HelperError) as err:
        sync.check()
    assert err.value.code == "unsupported_state_version"
    proc = subprocess.run([sys.executable, str(SYNC), "check", "--last-seen", "0"], capture_output=True, text=True)
    assert proc.returncode == 1 and json.loads(proc.stdout)["error"] == "unsupported_state_version"
    assert (sd / "state.json").read_bytes() == raw


def test_sync_cli_and_import_agree(sd):
    sync.helper.transition("afk", "work")
    proc = subprocess.run([sys.executable, str(SYNC), "check", "--last-seen", "0"], capture_output=True, text=True)
    assert proc.returncode == 0 and json.loads(proc.stdout) == sync.check()


def test_read_failure_is_structured(sd, monkeypatch):
    def fail(path):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(sync.helper, "load", fail)
    with pytest.raises(sync.helper.HelperError) as err:
        sync.check()
    assert err.value.code == "state_read_failed"


def test_continuously_replaced_file_fails_bounded_check(sd, monkeypatch):
    sync.helper.transition("afk", "work")
    original = sync.helper.load
    calls = []

    def replace_during_read(path):
        prior = original(path)
        sync.helper.write_atomic(path, prior.state)
        calls.append(1)
        return prior

    monkeypatch.setattr(sync.helper, "load", replace_during_read)
    with pytest.raises(sync.helper.HelperError) as err:
        sync.check()
    assert err.value.code == "state_read_failed" and len(calls) == 3


@pytest.mark.parametrize("last_seen", [-1, True, "1"])
def test_invalid_session_generation_refused(sd, last_seen):
    with pytest.raises(sync.helper.HelperError) as err:
        sync.check(last_seen)
    assert err.value.code == "invalid_last_seen"


def test_clock_age_never_changes_afk(sd):
    sd.mkdir()
    state = {"version": 2, "status": "afk", "since": "1900-01-01T00:00:00Z", "context": "work", "generation": 30}
    sync.helper.write_atomic(sd / "state.json", state)
    result = sync.check(0)
    assert "status: afk" in result["event"] and result["generation"] == 30
    assert sync.helper.read_command()["status"] == "afk"
