"""The cross-host installer: detection, planning, idempotent merges, refusals, uninstall."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("afkswitch_install", ROOT / "scripts/install.py")
inst = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inst)

ALL = ["claude", "codex", "hermes", "cursor", "copilot", "agy"]
PY = Path(sys.executable).as_posix()


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localapp"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("AFKSWITCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    return tmp_path


def run(root, *args, home=None):
    return inst.main(["--home", str(home or root / "home"), *args])


def snap(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def seed(home):
    for d in (".claude", ".codex", ".hermes", ".cursor", ".copilot", ".gemini/config"):
        (home / d).mkdir(parents=True, exist_ok=True)
    (home / ".claude/settings.json").write_text(json.dumps(
        {"theme": "dark", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}, "model": "x"}, indent=2) + "\n")
    (home / ".codex/hooks.json").write_text('{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo c"}]}]}}\n')
    (home / ".codex/config.toml").write_text('model = "x"\n')
    (home / ".hermes/config.yaml").write_text("model: x\n")
    (home / ".cursor/hooks.json").write_text('{"version": 1, "hooks": {"stop": [{"command": "echo u"}]}}\n')


def app_of(root):
    return inst.app_dir(root / "home")


@pytest.mark.parametrize("host,folder", [("claude", ".claude"), ("codex", ".codex"), ("hermes", ".hermes"),
                                         ("cursor", ".cursor"), ("copilot", ".copilot"), ("agy", ".gemini/config")])
def test_detection_matrix(env, host, folder):
    home = env / "home"
    assert inst.detect(home) == set()
    (home / folder).mkdir(parents=True)
    assert inst.detect(home) == {host}


def test_codex_detected_on_path(env, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "x" if name == "codex" else None)
    assert inst.detect(env / "home") == {"codex"}


def test_unknown_host_is_a_usage_error(env):
    assert run(env, "--host", "nope", "--yes") == 2
    assert run(env, "--bogus") == 2


def test_dry_run_changes_nothing(env):
    seed(env / "home")
    before = snap(env)
    assert run(env, "--dry-run") == 0
    assert snap(env) == before


def test_declining_the_prompt_writes_nothing(env, monkeypatch):
    seed(env / "home")
    before = snap(env)
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    assert run(env) == 0
    assert snap(env) == before


def test_install_all_hosts_fills_placeholders(env):
    home = env / "home"
    seed(home)
    assert run(env, "--yes") == 0
    app = inst.posix(app_of(env))
    claude = json.loads((home / ".claude/settings.json").read_text())
    cmd = claude["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert cmd.startswith(f'"{PY}" "{app}/scripts/presence_hook.py"') and "--host claude" in cmd
    assert "modules" not in claude
    codex = json.loads((home / ".codex/hooks.json").read_text())
    assert f'"{PY}" "{app}/scripts' in codex["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    cursor = json.loads((home / ".cursor/hooks.json").read_text())
    assert cursor["version"] == 1 and "--host cursor" in cursor["hooks"]["sessionStart"][-1]["command"]
    copilot = json.loads((home / ".copilot/hooks/afkswitch.json").read_text())
    assert copilot["hooks"]["sessionStart"][0]["exec"] == PY
    hermes = (home / ".hermes/config.yaml").read_text()
    assert f"'\"{PY}\" \"{app}/scripts/presence_hook.py\"" in hermes and "<python>" not in hermes and "\\" not in hermes
    plug = home / ".gemini/config/plugins/afkswitch"
    agy = json.loads((plug / "hooks.json").read_text())
    assert f'"{PY}" "{inst.posix(plug)}/scripts/presence_hook.py"' in agy["afkswitch-presence"]["PreInvocation"][0]["command"]
    for base in (home / ".claude/skills", home / ".agents/skills", home / ".gemini/config/skills"):
        assert (base / "afk/SKILL.md").is_file() and (base / "back/SKILL.md").is_file()
    assert not (home / ".hermes/skills").exists()
    assert (app_of(env) / "skills/afk/scripts/afkswitch_state.py").is_file()
    assert (app_of(env) / "install-manifest.json").is_file()
    assert not list(env.rglob("__pycache__")) and not list(env.rglob("*.pyc"))
    assert (app_of(env) / "bin/afkswitch.cmd").is_file() if os.name == "nt" else (home / ".local/bin/afkswitch").is_file()


def test_merge_keeps_unrelated_keys_and_order(env):
    home = env / "home"
    seed(home)
    run(env, "--yes")
    settings = json.loads((home / ".claude/settings.json").read_text())
    assert list(settings) == ["theme", "hooks", "model"]
    assert settings["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo hi"
    assert len(settings["hooks"]["SessionStart"]) == 1


def test_second_install_is_byte_identical(env):
    seed(env / "home")
    run(env, "--yes")
    first = {k: v for k, v in snap(env).items() if "install-manifest" not in k}
    assert run(env, "--yes") == 0
    assert {k: v for k, v in snap(env).items() if "install-manifest" not in k} == first


def test_unparseable_json_refuses_that_host_only(env, capsys):
    home = env / "home"
    seed(home)
    bad = '{\n  // comment\n  "theme": "dark"\n}\n'
    (home / ".claude/settings.json").write_text(bad)
    assert run(env, "--yes") == 1
    assert (home / ".claude/settings.json").read_text() == bad
    assert "presence_hook.py" in capsys.readouterr().out
    assert "--host codex" in (home / ".codex/hooks.json").read_text()


def test_foreign_hermes_hooks_key_refused(env):
    home = env / "home"
    seed(home)
    foreign = "hooks:\n  other: 1\n"
    (home / ".hermes/config.yaml").write_text(foreign)
    assert run(env, "--yes") == 1
    assert (home / ".hermes/config.yaml").read_text() == foreign
    assert "--host claude" in (home / ".claude/settings.json").read_text()


def test_managed_block_is_replaced_not_duplicated(env):
    home = env / "home"
    seed(home)
    run(env, "--yes")
    cfg = home / ".hermes/config.yaml"
    cfg.write_text(cfg.read_text().replace("pre_llm_call", "tampered"))
    assert run(env, "--yes") == 0
    text = cfg.read_text()
    assert text.count(inst.BEGIN) == 1 and "tampered" not in text and "pre_llm_call" in text


def test_backups_only_for_preexisting_files(env):
    home = env / "home"
    seed(home)
    run(env, "--yes")
    backups = {p.name.split(".afkswitch-backup-")[0] for p in home.rglob("*.afkswitch-backup-*")}
    assert backups == {"settings.json", "hooks.json", "config.yaml"}
    assert "afkswitch.json" not in backups
    assert not list((home / ".copilot").rglob("*backup*"))


def test_claude_plugin_enabled_adds_no_hooks(env):
    home = env / "home"
    (home / ".claude").mkdir(parents=True)
    text = json.dumps({"enabledPlugins": {"afkswitch@marketplace": True}}, indent=2) + "\n"
    (home / ".claude/settings.json").write_text(text)
    assert run(env, "--yes", "--host", "claude") == 0
    assert (home / ".claude/settings.json").read_text() == text
    assert (home / ".claude/skills/afk/SKILL.md").is_file()


def test_foreign_skill_folder_refused(env):
    home = env / "home"
    (home / ".claude/skills/afk").mkdir(parents=True)
    (home / ".claude/skills/afk/SKILL.md").write_text("somebody else's afk\n")
    assert run(env, "--yes", "--host", "claude") == 1
    assert (home / ".claude/skills/afk/SKILL.md").read_text() == "somebody else's afk\n"
    assert (home / ".claude/skills/back/SKILL.md").is_file()


def test_codex_writable_state_block_and_refusal(env):
    home = env / "home"
    seed(home)
    assert run(env, "--yes", "--host", "codex", "--codex-writable-state") == 0
    toml = (home / ".codex/config.toml").read_text()
    assert "WARNING" in toml and f'writable_roots = ["{Path(env / "state").as_posix()}"]' in toml
    (home / ".codex/config.toml").write_text("[sandbox_workspace_write]\nnetwork_access = true\n")
    assert run(env, "--yes", "--host", "codex", "--codex-writable-state") == 1
    assert (home / ".codex/config.toml").read_text() == "[sandbox_workspace_write]\nnetwork_access = true\n"


def test_hermes_skills_are_opt_in(env):
    (env / "home/.hermes").mkdir(parents=True)
    assert run(env, "--yes", "--host", "hermes", "--hermes-skills") == 0
    assert (env / "home/.hermes/skills/afk/SKILL.md").is_file()


def test_uninstall_restores_everything(env):
    home = env / "home"
    seed(home)
    state = env / "state"
    state.mkdir()
    (state / "state.json").write_text("{}")
    originals = {p: p.read_bytes() for p in (home / ".hermes/config.yaml", home / ".codex/config.toml")}
    objs = {p: json.loads(p.read_text()) for p in (home / ".claude/settings.json", home / ".codex/hooks.json",
                                                   home / ".cursor/hooks.json")}
    run(env, "--yes", "--codex-writable-state")
    assert run(env, "--uninstall", "--yes") == 0
    for p, data in originals.items():
        assert p.read_bytes() == data
    for p, obj in objs.items():
        assert json.loads(p.read_text()) == obj
    assert not (home / ".claude/skills/afk").exists() and not (home / ".agents/skills/afk").exists()
    assert not (home / ".gemini/config/plugins/afkswitch").exists()
    assert not (home / ".copilot/hooks/afkswitch.json").exists()
    assert not app_of(env).exists()
    assert not (home / ".local/bin/afkswitch").exists()
    assert (state / "state.json").read_text() == "{}"


def test_uninstall_leaves_foreign_skills(env):
    home = env / "home"
    (home / ".claude/skills/afk").mkdir(parents=True)
    (home / ".claude/skills/afk/SKILL.md").write_text("not ours\n")
    assert run(env, "--uninstall", "--yes", "--host", "claude") == 0
    assert (home / ".claude/skills/afk/SKILL.md").exists()


def test_home_with_a_space_and_installed_cli_runs(env, monkeypatch):
    spaced = env / "my home"
    (spaced / ".claude").mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(env / "app dir"))
    monkeypatch.setenv("XDG_DATA_HOME", str(env / "app dir"))
    assert run(env, "--yes", "--host", "claude", home=spaced) == 0
    app = inst.app_dir(spaced)
    cmd = json.loads((spaced / ".claude/settings.json").read_text())["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "app dir" in cmd
    child = {**os.environ, "AFKSWITCH_STATE_DIR": str(env / "state"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([sys.executable, str(app / "scripts/afkswitch.py"), "status"],
                          capture_output=True, text=True, env=child, timeout=60)
    assert done.returncode == 0 and done.stdout.strip()
    hook = subprocess.run([sys.executable, str(app / "scripts/presence_hook.py"), "--host", "claude", "--event", "SessionStart"],
                          input="{}", capture_output=True, text=True, env=child, timeout=60)
    assert hook.returncode == 0


def test_a_crlf_tab_indented_json_keeps_its_style_and_unrelated_bytes(env):
    # Someone's own hooks file: CRLF and tabs. Only our lines may change, so the reviewed diff is small.
    home = env / "home"
    seed(home)
    own = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "mine", "timeout": 3}]}]}}
    text = json.dumps(own, indent="\t").replace("\n", "\r\n") + "\r\n"
    path = home / ".codex/hooks.json"
    path.write_bytes(text.encode("utf-8"))
    assert run(env, "--yes", "--host", "codex") == 0
    after = path.read_bytes().decode("utf-8")
    assert "\r\n" in after and "\n" not in after.replace("\r\n", "")
    assert '\t\t"SessionStart": [' in after
    assert json.loads(after)["hooks"]["SessionStart"][0] == own["hooks"]["SessionStart"][0]
    assert run(env, "--yes", "--uninstall", "--host", "codex") == 0
    assert json.loads(path.read_bytes().decode("utf-8")) == own
