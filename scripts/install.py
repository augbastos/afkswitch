#!/usr/bin/env python3
"""Cross-host AFKSwitch installer: copies one app dir and wires each detected host's hooks and skills.

Python 3.9+, stdlib only, no network. Every change is planned first, shown as a diff, and applied
only after a yes. Host configs are edited surgically (our entries or one managed block) and backed up.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ("claude", "codex", "hermes", "cursor", "copilot", "agy", "generic")
MARKERS = {"claude": ".claude", "codex": ".codex", "hermes": ".hermes", "cursor": ".cursor",
           "copilot": ".copilot", "agy": ".gemini/config"}
BEGIN = "# >>> afkswitch (managed, do not edit) >>>"
END = "# <<< afkswitch <<<"
BLOCK_RE = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
SKILL_MARK = "~/.afkswitch/state.json"
SKILLS = ("afk", "back")
PAYLOAD = ("skills/afk", "skills/back", "scripts/presence_hook.py", "scripts/afkswitch.py",
           "adapters/generic/presence_sync.py")
NEXT = {
    "claude": "Restart Claude Code (or /clear), then use /afk and /back.",
    "codex": "Open Codex and trust the new hooks with /hooks.",
    "hermes": "Hermes asks once to approve the hook (or set HERMES_ACCEPT_HOOKS=1).",
    "cursor": "Restart Cursor so it reloads hooks.",
    "copilot": "Start a new Copilot CLI session.",
    "agy": "Experimental: the layout is untested in a live Antigravity host.",
}


class Refuse(Exception):
    """A step that must not touch the user's files; the message says what to do by hand."""


def read(path: Path) -> str:
    # bytes, not read_text: keep CRLF so an untouched file stays byte-identical
    return path.read_bytes().decode("utf-8") if path.is_file() else ""


def posix(path) -> str:
    return Path(os.path.abspath(path)).as_posix()  # Hermes splits with shlex: no backslashes


def app_dir(home: Path) -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local") / "AFKSwitch"
    if sys.platform == "darwin":
        return home / "Library/Application Support/AFKSwitch"
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share") / "afkswitch"


def detect(home: Path) -> set:
    found = {h for h, d in MARKERS.items() if (home / d).is_dir()}
    if shutil.which("codex"):
        found.add("codex")
    return found


def tmpl(rel: str):
    return json.loads((ROOT / rel).read_text("utf-8"))


def fill(obj, subs):
    if isinstance(obj, str):
        for old, new in subs:
            obj = obj.replace(old, new)
        return obj
    if isinstance(obj, list):
        return [fill(x, subs) for x in obj]
    if isinstance(obj, dict):
        return {k: fill(v, subs) for k, v in obj.items()}
    return obj


def dump(doc, like: str = "") -> str:
    """JSON text; `like` (the file's old text) keeps its line endings and indent, so the
    diff a person reviews shows only what changed, not a reformatted file."""
    lead = re.search(r"\n([ \t]+)\S", like)
    indent = lead.group(1) if lead else 2
    text = json.dumps(doc, indent=indent, ensure_ascii=False) + "\n"
    return text.replace("\n", "\r\n") if "\r\n" in like else text


# --- editing rules -----------------------------------------------------------------------

def ours(entry, host: str) -> bool:
    if not isinstance(entry, dict):
        return False
    cmd = str(entry.get("command") or " ".join([str(entry.get("exec", "")), *map(str, entry.get("args", []))]))
    return "presence_hook.py" in cmd and f"--host {host}" in cmd


def strip(entries, host: str) -> list:
    out = []
    for e in entries:
        if isinstance(e, dict) and isinstance(e.get("hooks"), list):
            kept = [h for h in e["hooks"] if not ours(h, host)]
            if kept or not e["hooks"]:
                out.append(e if len(kept) == len(e["hooks"]) else {**e, "hooks": kept})
        elif not ours(e, host):
            out.append(e)
    return out


def edit_json(path: Path, host: str, new_hooks, defaults=None):
    """Remove our entries, then append new_hooks (falsy = uninstall). Returns new text or None if unchanged."""
    text = read(path)
    try:
        doc, before = (json.loads(text) if text.strip() else {}), (json.loads(text) if text.strip() else {})
        hooks = doc.get("hooks", {})
        if not isinstance(hooks, dict) or not all(isinstance(v, list) for v in hooks.values()):
            raise ValueError("unexpected shape")
    except (ValueError, AttributeError):  # AttributeError: top level is not an object
        snippet = dump({"hooks": new_hooks}) if new_hooks else f"entries whose command has presence_hook.py --host {host}"
        raise Refuse(f"{path} is not plain JSON in the expected shape. Merge by hand:\n{snippet}") from None
    for k, v in ((defaults or {}).items() if new_hooks else ()):
        doc.setdefault(k, v)
    if new_hooks:
        hooks = doc.setdefault("hooks", {})
    for ev in list(hooks):
        hooks[ev] = strip(hooks[ev], host)
    for ev, groups in (new_hooks or {}).items():
        hooks[ev] = hooks.get(ev, []) + groups
    for ev in [e for e in hooks if not hooks[e]]:
        del hooks[ev]  # only ever our leftovers: empty lists are not worth keeping
    if "hooks" in doc and not hooks and before.get("hooks"):
        del doc["hooks"]
    return None if doc == before else dump(doc, text)


def edit_block(path: Path, body, foreign: re.Pattern, hint: str = ""):
    """Managed block between BEGIN/END (body None = remove). Returns new text or None if unchanged."""
    text = read(path)
    if body is None:
        new = re.sub(r"\n?" + BLOCK_RE.pattern + r"\n?", "", text, count=1, flags=re.S)
    else:
        block = f"{BEGIN}\n{body.rstrip(chr(10))}\n{END}"
        if foreign.search(BLOCK_RE.sub("", text)):
            raise Refuse(f"{path} already has this table/key outside our block. Merge by hand:\n{hint or block}")
        if BLOCK_RE.search(text):
            new = BLOCK_RE.sub(lambda m: block, text, count=1)
        else:
            new = text + ("" if not text or text.endswith("\n") else "\n") + ("\n" if text else "") + block + "\n"
    return None if new == text else new


def put(path: Path, text):
    if text is None:
        return []
    return [("remove", path, None)] if text == "" else [("write", path, text)]


def put_ours(path: Path, text: str):
    return [] if read(path) == text and path.is_file() else [("write", path, text)]


def skill(root: Path, name: str, un: bool):
    dest = root / name
    mine = (dest / "SKILL.md").is_file() and SKILL_MARK in read(dest / "SKILL.md")
    if un:
        return [("remove", dest, None)] if mine else []
    if dest.exists() and not mine and not (dest.is_dir() and not any(dest.iterdir())):
        raise Refuse(f"{dest} exists and is not an AFKSwitch skill. Move it away first, or use /afkswitch:{name}.")
    return [("copy", ROOT / "skills" / name, dest)]


# --- planning ----------------------------------------------------------------------------

class Plan:
    def __init__(self):
        self.ops, self.refused, self.notes, self.seen = [], [], {}, set()

    def step(self, host, fn, *args):
        try:
            self.ops += [(host, *op) for op in fn(*args)]
        except Refuse as e:
            self.refused.append((host, str(e)))

    def skills(self, host, root, un):
        for name in SKILLS:  # one step per skill: a foreign afk folder must not block back
            if (root, name) not in self.seen:
                self.seen.add((root, name))
                self.step(host, skill, root, name, un)

    def note(self, host, msg):
        self.notes.setdefault(host, []).append(msg)


def plugin_enabled(path: Path) -> bool:
    try:
        plugins = json.loads(read(path)).get("enabledPlugins") or {}
        return any(k.startswith("afkswitch@") and v is True for k, v in plugins.items())
    except (ValueError, AttributeError):
        return False


def plan_host(h, a, home, app, py, plan, un):
    app_p = posix(app)
    subs = [("<python>", py), ("<app>", app_p)]
    agents = home / ".agents/skills"

    if h == "claude":
        settings = home / ".claude/settings.json"
        on = not un and plugin_enabled(settings)
        new = None if un or on else fill(tmpl("hooks/hooks.json")["hooks"],
                                        [('python3 "${CLAUDE_PLUGIN_ROOT}/', f'"{py}" "{app_p}/')])
        if on:
            plan.note(h, "the afkswitch plugin is enabled and already wires the hooks: none added to settings.json")
        plan.step(h, lambda: put(settings, edit_json(settings, h, new)))
        plan.skills(h, home / ".claude/skills", un)
    elif h == "codex":
        hooks = home / ".codex/hooks.json"
        new = None if un else fill(tmpl("hooks/codex.json")["hooks"], [('python3 "${PLUGIN_ROOT}/', f'"{py}" "{app_p}/')])
        plan.step(h, lambda: put(hooks, edit_json(hooks, h, new)))
        plan.skills(h, agents, un)
        toml, table = home / ".codex/config.toml", re.compile(r"^\s*\[sandbox_workspace_write\]", re.M)
        if un or a.codex_writable_state:
            state = posix(state_dir(home))
            body = None if un else ("# WARNING: any sandboxed Codex turn can now change your presence state.\n"
                                    f'[sandbox_workspace_write]\nwritable_roots = ["{state}"]')
            plan.step(h, lambda: put(toml, edit_block(toml, body, table, body or "")))
    elif h == "hermes":
        cfg = home / ".hermes/config.yaml"
        body = None
        if not un:
            body = fill((ROOT / "adapters/hermes/hooks.yaml").read_text("utf-8"), subs)
            if "'" in py + app_p:
                plan.refused.append((h, "a single quote in the interpreter or app path breaks the YAML; install elsewhere"))
                return
        plan.step(h, lambda: put(cfg, edit_block(cfg, body, re.compile(r"^hooks:", re.M), body or "")))
        if un or a.hermes_skills:
            plan.skills(h, home / ".hermes/skills", un)
    elif h == "cursor":
        hooks = home / ".cursor/hooks.json"
        new = None if un else fill(tmpl("adapters/cursor/hooks.json")["hooks"], subs)
        plan.step(h, lambda: put(hooks, edit_json(hooks, h, new, {"version": 1})))
        plan.skills(h, agents, un)
    elif h == "copilot":
        f = home / ".copilot/hooks/afkswitch.json"
        if un:
            plan.step(h, lambda: [("remove", f, None)] if f.is_file() else [])
        else:
            plan.step(h, lambda: put_ours(f, dump(fill(tmpl("adapters/copilot/afkswitch.json"), subs))))
        plan.skills(h, agents, un)
    elif h == "agy":
        plug = home / ".gemini/config/plugins/afkswitch"
        if un:
            plan.step(h, lambda: [("remove", plug, None)] if plug.exists() else [])
        else:
            hooks = fill(tmpl("adapters/agy/hooks.json"), [('python "<plugin dir>', f'"{py}" "{posix(plug)}')])
            plan.step(h, lambda: [("copy", ROOT / p, plug / p) for p in PAYLOAD]
                      + put_ours(plug / "plugin.json", (ROOT / "adapters/agy/plugin.json").read_text("utf-8"))
                      + put_ours(plug / "hooks.json", dump(hooks)))
        plan.skills(h, home / ".gemini/config/skills", un)
    elif h == "generic":
        plan.note(h, f'before each turn run: "{py}" "{app_p}/adapters/generic/presence_sync.py" check '
                     "--last-seen N --last-epoch E (see adapters/generic/README.md in the repo)")
    if h in NEXT and not un:
        plan.note(h, NEXT[h])


def state_dir(home: Path) -> Path:
    return Path(os.environ.get("AFKSWITCH_STATE_DIR") or home / ".afkswitch")


def plan_shim(home, app, py, plan, un):
    if os.name == "nt":
        path = app / "bin/afkswitch.cmd"
        text = f'@"{os.path.abspath(py)}" "{app / "scripts/afkswitch.py"}" %*\r\n'
    else:
        path = home / ".local/bin/afkswitch"
        text = f'#!/bin/sh\nexec "{py}" "{posix(app)}/scripts/afkswitch.py" "$@"\n'
    if path.is_file() and "afkswitch.py" not in read(path):
        if not un:
            plan.refused.append(("cli", f"{path} exists and is not the AFKSwitch shim; move it away first"))
        return path
    if un:
        plan.ops += [("cli", "remove", path, None)] if path.is_file() else []
    else:
        plan.ops += [("cli", *op) for op in put_ours(path, text)]
    return path


# --- applying ----------------------------------------------------------------------------

def show(ops):
    for host, kind, a, b in ops:
        if kind == "write":
            old = read(a)
            # Compare without CR so a CRLF file's unchanged lines do not print as blank pairs.
            diff = difflib.unified_diff(old.replace("\r\n", "\n").splitlines(True),
                                        b.replace("\r\n", "\n").splitlines(True),
                                        str(a) if old else "(new file)", f"{a} (after)")
            print(f"[{host}] write {a}\n" + "".join(l if l.endswith("\n") else l + "\n" for l in diff))
        elif kind == "copy":
            print(f"[{host}] copy   {a} -> {b}")
        elif kind == "remove":
            print(f"[{host}] remove {a}")
        else:
            print(f"[{host}] add {a} to your user PATH")


def write_atomic(path: Path, text: str, stamp: str):
    backup = None
    if path.exists():
        backup = f"{path}.afkswitch-backup-{stamp}"
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
        if text.startswith("#!"):
            os.chmod(tmp, 0o755)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return backup


def remove(path: Path):
    shutil.rmtree(path) if path.is_dir() else path.unlink()


def copy(src: Path, dst: Path):
    if dst.exists():
        remove(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        shutil.copy2(src, dst)


def add_to_path(folder: Path):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
        try:
            value, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            value, kind = "", winreg.REG_EXPAND_SZ
        if str(folder).lower() not in [p.lower() for p in value.split(";")]:
            winreg.SetValueEx(key, "Path", 0, kind, (value.rstrip(";") + ";" if value else "") + str(folder))


def apply(ops, stamp):
    done, failed = [], []
    for host, kind, a, b in ops:
        try:
            if kind == "write":
                done.append({"path": str(a), "backup": write_atomic(a, b, stamp)})
            elif kind == "copy":
                copy(a, b)
            elif kind == "remove":
                remove(a)
            else:
                add_to_path(a)
        except (OSError, ImportError) as e:
            failed.append((host, f"{kind} {a}: {e}"))
    return done, failed


def write_manifest(app: Path, hosts, edited, ops):
    path = app / "install-manifest.json"
    try:
        old = {f["path"]: f for f in json.loads(read(path)).get("files", [])}
    except ValueError:
        old = {}
    old.update({f["path"]: f for f in edited})  # keep earlier runs' backups for files untouched now
    folders = sorted({str(b) for _, k, _, b in ops if k == "copy"})
    version = json.loads((ROOT / "plugin.json").read_text("utf-8"))["version"]
    doc = {"version": version, "time": datetime.now(timezone.utc).isoformat(), "hosts": sorted(hosts),
           "files": list(old.values()), "folders": folders}
    path.write_text(dump(doc), "utf-8")


# --- main --------------------------------------------------------------------------------

def parser():
    p = argparse.ArgumentParser(prog="install.py", description="Install AFKSwitch for every detected agent host.")
    p.add_argument("--host", help="comma list from: " + ", ".join(HOSTS) + " (default: detected hosts)")
    p.add_argument("--yes", action="store_true", help="skip the Apply? question")
    p.add_argument("--dry-run", action="store_true", help="show the changes, write nothing")
    p.add_argument("--uninstall", action="store_true", help="remove what this installer added (never ~/.afkswitch)")
    p.add_argument("--codex-writable-state", action="store_true", help="let Codex's sandbox write the state dir")
    p.add_argument("--hermes-skills", action="store_true", help="also install the skills into Hermes")
    p.add_argument("--add-to-path", action="store_true", help="Windows: add the shim folder to your user PATH")
    p.add_argument("--home", help=argparse.SUPPRESS)
    return p


def main(argv=None) -> int:
    try:
        a = parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    home = Path(os.path.abspath(a.home)) if a.home else Path.home()
    names = [n.strip() for n in a.host.split(",") if n.strip()] if a.host else None
    if names is not None and (bad := [n for n in names if n not in HOSTS]):
        print(f"unknown host: {', '.join(bad)} (choose from {', '.join(HOSTS)})", file=sys.stderr)
        return 2
    un = a.uninstall
    hosts = names if names is not None else ([h for h in HOSTS if h != "generic"] if un else sorted(detect(home)))
    if not hosts:
        print("No supported host detected. Pass --host NAME to install anyway.")
        return 0

    app, py, plan = app_dir(home), os.path.abspath(sys.executable), Plan()
    py_posix = Path(py).as_posix()
    if sys.prefix != sys.base_prefix and not un:
        print(f"warning: running inside a virtual environment; hooks will call {py_posix}, which disappears with it.")
    real = [h for h in hosts if h != "generic"]
    if real and not un:
        plan.step("app", lambda: [("copy", ROOT / p, app / p) for p in PAYLOAD])
    shim = plan_shim(home, app, py_posix, plan, un) if real else None
    if shim and not un and a.add_to_path and os.name == "nt":
        if str(shim.parent).lower() not in [p.lower() for p in os.environ.get("PATH", "").split(";")]:
            plan.ops.append(("cli", "path", shim.parent, None))
    elif shim and not un and str(shim.parent) not in os.environ.get("PATH", "").split(os.pathsep):
        plan.note("cli", f"add {shim.parent} to PATH to use `afkswitch` from any terminal"
                         + (" (or rerun with --add-to-path)" if os.name == "nt" else ""))
    for h in hosts:
        plan_host(h, a, home, app, py_posix, plan, un)
    if un and names is None:
        if app.is_dir():
            plan.ops.append(("app", "remove", app, None))

    show(plan.ops)
    for host, msg in plan.refused:
        print(f"[{host}] REFUSED: {msg}\n")
    if not plan.ops:
        print("Nothing to change.")
    elif a.dry_run:
        print("Dry run: nothing written.")
        return 0
    elif not a.yes and input("Apply? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Declined: nothing written.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    edited, failed = apply(plan.ops, stamp)
    if not un and plan.ops and app.is_dir() and not any(h == "app" for h, _ in failed):
        write_manifest(app, hosts, edited, plan.ops)

    print("\nSummary")
    refused = {h for h, _ in plan.refused}
    bad_hosts = refused | {h for h, _ in failed}
    for h in dict.fromkeys(["app", "cli", *hosts]):
        mine = [o for o in plan.ops if o[0] == h]
        state = ("refused" if h in refused else "failed" if h in bad_hosts else "ok" if mine else "unchanged")
        if h in hosts or mine or h in bad_hosts:
            print(f"  {h}: {state}")
            for note in plan.notes.get(h, []):
                print(f"    - {note}")
    for h, msg in failed:
        print(f"  write failed [{h}]: {msg}")
    return 1 if bad_hosts else 0


if __name__ == "__main__":
    sys.exit(main())
