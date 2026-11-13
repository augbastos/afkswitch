"""The CI runner preserves discovery, isolation and failing process exits."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("ci_runner", Path(__file__).resolve().parents[1] / "scripts/test_ci.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize("exit_code", [0, 1, 2, 5])
def test_all_modules_run_and_any_nonzero_exit_fails(tmp_path, monkeypatch, exit_code):
    modules = [tmp_path / "conformance" / p for p in ("test_a.py", "nested/test_b.py")]
    for module in modules:
        module.parent.mkdir(parents=True, exist_ok=True)
        module.touch()
    seen = []

    def run(module):
        seen.append(module)
        return module, exit_code if module == modules[0] else 0, "output", 0.01

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "run_module", run)
    monkeypatch.setattr(runner.os, "cpu_count", lambda: 1)
    assert runner.main() == int(exit_code != 0)
    assert set(seen) == set(modules)


def test_empty_collection_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    assert runner.main() == 1


def test_processes_have_distinct_temp_dirs_and_preserve_output(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    calls = []

    def run(command, **kwargs):
        assert Path(command[-1]).parent.is_dir()
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=2, stdout="collection failed")

    monkeypatch.setattr(runner.subprocess, "run", run)
    for module in ("state/test_state.py", "hooks/test_hooks.py"):
        _, code, output, _ = runner.run_module(runner.ROOT / "conformance" / module)
        assert code == 2 and output == "collection failed"
    assert calls[0][0][-1] != calls[1][0][-1]
    assert all(call[1]["cwd"] == runner.ROOT for call in calls)
