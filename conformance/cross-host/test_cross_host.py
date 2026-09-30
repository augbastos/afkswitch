"""Drive the portable cross-host scenario through actual helpers in an isolated directory."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "conformance"))
import checker


def test_cross_host_generations_with_real_helpers(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("AFKSWITCH_STATE_DIR", str(state_dir))
    scenarios = json.loads(Path(__file__).with_name("scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    transcript = copy.deepcopy(next(s["transcript"] for s in scenarios if s["expect"] == "pass"))
    (state_dir / "state.json").write_text(json.dumps(transcript["initial"]), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("sync_cross_host", ROOT / "adapters/generic/presence_sync.py")
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    sessions, current = {}, transcript["initial"]
    for step in transcript["steps"]:
        host = step["host"]
        if step["op"] == "write":
            name = "back" if step["command"] == "back" else "afk"
            helper = ROOT / "skills" / name / "scripts/afkswitch_state.py"
            helper_spec = importlib.util.spec_from_file_location("cross_host_state", helper)
            module = importlib.util.module_from_spec(helper_spec)
            helper_spec.loader.exec_module(module)
            result = module.run([step["command"], "--context", step["context"]])
            for key, expected in step["state"].items():
                assert result[key] == expected
            step["state"] = result
            current = result
            sessions[host] = {"generation": result["generation"], "status": result["status"], "context": result["context"]}
        elif step["op"] == "sync":
            prior = sessions.get(host, {"generation": 0})
            result = sync.check(prior["generation"])
            assert result["changed"] is True and result["reset"] is False
            assert result["generation"] == current["generation"]
            assert result["event"] == sync.helper.core_event(current["status"], current["generation"], current["context"])
            if current["status"] == "available":
                assert "ready" not in result["event"]
            sessions[host] = step["local"]
            step["state"] = dict(current, reset=result["reset"])
        else:
            prior = sessions[host]
            assert checker.receiver_action(prior["generation"], step["state"]["generation"], False) == step["action"]
            assert step["local"] == prior
    assert checker.check_cross_host(transcript) == []
    durable = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    assert durable["generation"] == 31 and durable["status"] == "available" and durable["context"] is None
