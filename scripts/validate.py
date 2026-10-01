"""Validate the repository; `--write` first renders adapters/capabilities.json into the docs."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITE = "--write" in sys.argv[1:]


def load_json(path: str):
    with (ROOT / path).open("r", encoding="utf-8") as f:
        return json.load(f)


def fail(message: str) -> None:
    raise SystemExit(f"AFKSwitch validation failed: {message}")


portable = load_json("plugin.json")
claude = load_json(".claude-plugin/plugin.json")
market = load_json(".claude-plugin/marketplace.json")
schema = load_json("spec/state.schema.json")
version = portable.get("version", "")

# Names and versions agree everywhere.
for label, doc in [("portable plugin", portable), ("Claude plugin", claude), ("Claude marketplace", market)]:
    if doc.get("name") != "afkswitch":
        fail(f"{label} name must be afkswitch")
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    fail("plugin version is not semver")
entries = market.get("plugins", [])
if len(entries) != 1 or entries[0].get("name") != "afkswitch":
    fail("Claude marketplace must expose exactly one AFKSwitch plugin")
if not (claude.get("version") == entries[0].get("version") == version):
    fail("plugin/marketplace versions differ")
changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
if f"## [{version}]" not in changelog and f"## [Unreleased] ({version})" not in changelog:
    fail(f"CHANGELOG.md has no [{version}] or [Unreleased] ({version}) section")

# Codex CLIs that predate the portable manifest load .codex-plugin/plugin.json; keep it in step.
legacy = load_json(".codex-plugin/plugin.json")
for key in ["name", "version", "description", "license"]:
    if legacy.get(key) != portable.get(key):
        fail(f".codex-plugin/plugin.json {key} differs from plugin.json")
if legacy.get("skills") != "./skills/":
    fail('.codex-plugin/plugin.json must declare "skills": "./skills/"')
portable_ui = {k: v for k, v in portable["extensions"]["com.openai"]["interface"].items() if k != "supportURL"}
if legacy.get("interface") != portable_ui:
    fail(".codex-plugin/plugin.json interface differs from plugin.json (supportURL excepted)")

# Codex interface metadata in the portable manifest stays within the host's field limits.
ui = portable.get("extensions", {}).get("com.openai", {}).get("interface", {})
limits = {"displayName": 30, "shortDescription": 30, "developerName": 80, "longDescription": 4000}
for key, limit in limits.items():
    if not ui.get(key) or len(ui[key]) > limit:
        fail(f"interface.{key} missing or longer than {limit}")
if ui["developerName"] != portable.get("author", {}).get("name"):
    fail("interface.developerName must equal author.name")
prompts = ui.get("defaultPrompt", [])
if len(prompts) > 3 or any(len(p) > 128 for p in prompts):
    fail("interface.defaultPrompt allows at most 3 prompts of 128 chars")
for key in ["websiteURL", "privacyPolicyURL", "termsOfServiceURL", "supportURL"]:
    if not str(ui.get(key, "")).startswith("https://"):
        fail(f"interface.{key} must be an https URL")
images = [ui.get("logo", ""), ui.get("composerIcon", "")]
for image in images:
    if not image or not (ROOT / image).is_file():
        fail(f"interface icon {image!r} is missing")

# The product is exactly /afk + /back, explicit-only on every host.
skill_root = ROOT / "skills"
skill_dirs = sorted(p.name for p in skill_root.iterdir() if p.is_dir())
if skill_dirs != ["afk", "back"]:
    fail(f"core skills must be exactly afk/back, got {skill_dirs}")
for name in skill_dirs:
    text = (skill_root / name / "SKILL.md").read_text(encoding="utf-8")
    front = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not front:
        fail(f"skills/{name}/SKILL.md is missing YAML frontmatter")
    meta = dict(line.split(": ", 1) for line in front.group(1).splitlines() if ": " in line)
    if meta.get("name") != name:
        fail(f"skills/{name}/SKILL.md has the wrong name")
    if not 0 < len(meta.get("description", "")) <= 1024:
        fail(f"skills/{name}/SKILL.md description missing or over 1024 chars")
    if meta.get("disable-model-invocation") != "true":
        fail(f"skills/{name}/SKILL.md must be explicit-only (disable-model-invocation: true)")
    if "~/.afkswitch/state.json" not in text:
        fail(f"skills/{name}/SKILL.md does not use the AFKSwitch state path")
    # Codex truncates a skill's main prompt at 8,000 bytes; measure with CRLF, as a Windows
    # checkout would deliver it, and keep a margin.
    size = len(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
    if size > 7800:
        fail(f"skills/{name}/SKILL.md is {size} bytes with CRLF; Codex truncates skills at 8000")
    if not (skill_root / name / "references" / "message.md").is_file():
        fail(f"skills/{name}/references/message.md (the peer message body) is missing")
    otext = (skill_root / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if "CODEX" not in otext or "allow_implicit_invocation: false" not in otext:
        fail(f"skills/{name}/agents/openai.yaml must be explicit-invocation CODEX metadata")

# State protocol v2: the schemas, the helper, and the skills agree.
schema_v1 = load_json("spec/state.v1.schema.json")
props = schema.get("properties", {})
if props.get("status", {}).get("enum") != ["available", "afk"]:
    fail("state schema status enum changed unexpectedly")
if props.get("version", {}).get("const") != 2:
    fail("state schema version must be 2")
if schema.get("required") != ["version", "status", "since", "context", "generation"]:
    fail("state schema must require version, status, since, context, generation")
if schema_v1.get("properties", {}).get("version", {}).get("const") != 1:
    fail("spec/state.v1.schema.json must stay the version 1 schema")
HELPER = ROOT / "skills" / "afk" / "scripts" / "afkswitch_state.py"
BACK_HELPER = ROOT / "skills" / "back" / "scripts" / "afkswitch_state.py"
for script in (HELPER, BACK_HELPER):
    if not script.is_file():
        fail(f"state helper missing: {script.relative_to(ROOT).as_posix()}")
    try:
        compile(script.read_text(encoding="utf-8"), str(script), "exec")
    except SyntaxError as exc:
        fail(f"{script.relative_to(ROOT).as_posix()} does not compile: {exc}")
if HELPER.read_bytes() != BACK_HELPER.read_bytes():
    fail("afk/back must ship byte-identical, self-contained state helpers")
spec_ = importlib.util.spec_from_file_location("afkswitch_state_validate", HELPER)
helper = importlib.util.module_from_spec(spec_)
sys.dont_write_bytecode = True
spec_.loader.exec_module(helper)
if helper.STATE_VERSION != 2 or tuple(props["status"]["enum"]) != helper.STATUSES:
    fail("helper and schema disagree on version or statuses")
for label, doc in (("state.schema.json", schema), ("state.v1.schema.json", schema_v1)):
    if doc["properties"]["context"].get("maxLength") != helper.MAX_CONTEXT:
        fail(f"{label} context maxLength differs from the helper's limit")
helper_text = HELPER.read_text(encoding="utf-8")
if re.search(r"^\s*(import|from)\s+(?!(?:__future__|contextlib|datetime|json|os|pathlib|random|re|sys|time|uuid)\b)\S+",
             helper_text, re.M):
    fail("the state helper must import only the standard library modules it already uses")
if re.search(r"socket|urllib|http\.client|subprocess|threading", helper_text):
    fail("the state helper must not open sockets, start processes, or run threads")
with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ, AFKSWITCH_STATE_DIR=str(Path(tmp) / ".afkswitch"))
    runs = [([str(HELPER), "afk", "--context", "validate"], "afk"),
            ([str(BACK_HELPER), "back", "--context", "returned"], "available"),
            ([str(HELPER), "read"], "available")]
    for args, status in runs:
        proc = subprocess.run([sys.executable, "-B", *args], capture_output=True, text=True, env=env)
        try:
            out = json.loads(proc.stdout)
        except ValueError:
            fail(f"state helper printed no JSON line for {args[1:]}: {proc.stdout!r} {proc.stderr!r}")
        if not out.get("ok") or out.get("status") != status:
            fail(f"state helper smoke run failed for {args[1:]}: {out}")
skill_needs = {
    "afk": ["scripts/afkswitch_state.py", "state helper unavailable (python not found)", "state transition failed",
            "[AFKSwitch g<G>]", "[AFKSwitch g<G> reset]"],
    "back": ["scripts/afkswitch_state.py", "state helper unavailable (python not found)", "state transition failed",
             "[AFKSwitch g<G>]", "[AFKSwitch g<G> reset]", "afkswitch-status g<G>"],
}
for name, needles in skill_needs.items():
    text = (skill_root / name / "SKILL.md").read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            fail(f"skills/{name}/SKILL.md must mention {needle!r}")

# One-shot command hooks and an optional function-hooks UI; no MCP servers or apps.
for manifest in (portable, claude, legacy):
    for key in ("mcpServers", "apps"):
        if key in manifest:
            fail(f"manifests must not declare {key!r}")
if "hooks" in legacy or any("hooks" in extension for extension in portable["extensions"].values()):
    fail("default non-Claude manifests must not wire experimental hooks")
if claude.get("description") != "AFKSwitch by augbastos — Tell your agents when you're away and when you're back.":
    fail("Claude plugin description changed unexpectedly")
for host, path, variable in (("claude", "hooks/hooks.json", "CLAUDE_PLUGIN_ROOT"),
                             ("codex", "hooks/codex.json", "PLUGIN_ROOT")):
    if not (ROOT / path).is_file():
        fail(f"required hook manifest missing: {path}")
    manifest = load_json(path)
    if host == "claude":
        if (manifest.get("modules") != ["./switch.tsx"] or set(manifest) != {"modules", "hooks"}
                or not (ROOT / "hooks/switch.tsx").is_file()):
            fail("Claude hook manifest must combine command hooks with ./switch.tsx")
    elif "modules" in manifest:
        fail("experimental Codex hooks must not load the Claude UI module")
    hooks = manifest.get("hooks", {})
    if set(hooks) != {"SessionStart", "UserPromptSubmit"}:
        fail(f"{path} must declare exactly the two lifecycle hooks")
    for event, entries in hooks.items():
        expected = {"type": "command", "command": f'python3 "${{{variable}}}/scripts/presence_hook.py" --host {host} --event {event}', "timeout": 5}
        if entries != [{"hooks": [expected]}]:
            fail(f"{path} {event} must reference scripts/presence_hook.py with a 5-second timeout")
agy = load_json("adapters/agy/hooks.json")
if agy != {"afkswitch-presence": {"PreInvocation": [{"type": "command", "command": 'python "<plugin dir>/scripts/presence_hook.py" --host agy --event PreInvocation', "timeout": 5}]}}:
    fail("Agy PreInvocation hook must reference scripts/presence_hook.py")
if load_json("adapters/agy/plugin.json") != {"name": "afkswitch", "version": version}:
    fail("Agy plugin name/version differs")

# One canonical capability matrix, rendered into the docs.
capabilities = load_json("adapters/capabilities.json")
CAPABILITY_KEYS = ("state", "sync", "notify", "fanIn", "visualSwitch")
if set(capabilities.get("capabilities", {})) != set(CAPABILITY_KEYS):
    fail("capability definitions must be state, sync, notify, fanIn, visualSwitch")
ids = [host.get("id") for host in capabilities["hosts"]]
if len(ids) != len(set(ids)):
    fail("capability host ids must be unique")
for host in capabilities["hosts"]:
    for key in CAPABILITY_KEYS:
        if type(host.get(key)) is not bool:
            fail(f"{host['id']}: {key} must be a boolean")
    for key in ("notes", "evidence"):
        if not isinstance(host.get(key), str) or not host[key]:
            fail(f"{host['id']}: {key} must be a nonempty string")
    if (host["sync"] or host["notify"] or host["fanIn"]) and not host["state"]:
        fail(f"{host['id']}: capabilities require state")
    if host["fanIn"] and not host["notify"]:
        fail(f"{host['id']}: fanIn requires notify")
    expected_surfaces = ["terminal"] if host["id"] == "claude-code" else []
    if host["visualSwitch"] != bool(expected_surfaces) or host.get("visualSwitchSurfaces") != expected_surfaces:
        fail(f"{host['id']}: visualSwitch is terminal-only in Claude Code")
    if host["id"] in {"codex", "agy"} and host["sync"]:
        fail(f"{host['id']}: experimental hooks do not claim live-host sync")


def host_label(host: dict) -> str:
    return f"{host['name']} (reference)" if host.get("reference") else host["name"]


def render(style: str) -> str:
    hosts = capabilities["hosts"]
    if style not in ("readme", "details", "spec", "adapters"):
        fail(f"unknown capabilities style {style!r}")
    extra = ["Notes"] if style == "readme" else ["Notes", "Evidence"]
    headers = ["Host", "State", "Sync", "Notify", "Fan-in", "Visual switch", *extra]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for host in hosts:
        cells = [host["name"] if style == "readme" else host_label(host)]
        cells += ["yes" if host[key] else "no" for key in CAPABILITY_KEYS]
        cells += [host["notes"]]
        if style != "readme":
            cells += [host["evidence"]]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


MARKER = re.compile(r"(<!-- capabilities:(\w+):start -->\n)(.*?)(<!-- capabilities:\2:end -->)", re.S)
# The root README is explicitly frozen for this delivery; do not rewrite its
# historical capability snapshot or treat it as the current canonical matrix.
rendered_docs = {"docs/details.md": "details", "spec/presence.md": "spec",
                 "adapters/README.md": "adapters"}
for path, style in rendered_docs.items():
    text = (ROOT / path).read_text(encoding="utf-8")
    blocks = MARKER.findall(text)
    if [b[1] for b in blocks] != [style]:
        fail(f"{path} needs exactly one capabilities:{style} block")
    fresh = MARKER.sub(lambda m: m.group(1) + render(m.group(2)) + "\n" + m.group(4), text)
    if fresh != text:
        if WRITE:
            (ROOT / path).write_text(fresh, encoding="utf-8", newline="\n")
        else:
            fail(f"{path} is out of date with adapters/capabilities.json; run python scripts/validate.py --write")

# Privacy wording matches what the code does.
PRIVACY_LINE = ("AFKSwitch runs no server and makes no network requests of its own. Messages between sessions "
                "travel through the host's own mechanisms and are governed by the host.")
for path in ("README.md", "PRIVACY.md"):
    if PRIVACY_LINE not in " ".join((ROOT / path).read_text(encoding="utf-8").split()):
        fail(f"{path} must carry the privacy statement verbatim")

# No personal paths in anything tracked.
PERSONAL = re.compile(r"[A-Za-z]:\\\\?Users\\|/home/[a-z]|/Users/[A-Za-z]|\bV:\\|/tmp/")
tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
for rel in tracked:
    path = ROOT / rel
    if rel == "scripts/validate.py" or not path.is_file() or path.suffix in {".png", ".ico"}:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    if PERSONAL.search(text):
        fail(f"personal path in {rel}")

# Legacy product surface stays out of current docs and skills (CHANGELOG keeps history).
current = ["README.md", "install.ps1", "spec/presence.md", *map(str, skill_root.rglob("*.md"))]
for path in current:
    text = (ROOT / path).read_text(encoding="utf-8")
    for legacy in ["~/.claude/session-presence", "/broadcast", "/live"]:
        if legacy in text:
            fail(f"legacy product surface {legacy!r} remains in {path}")

required = [
    "LICENSE", "PRIVACY.md", "SECURITY.md", "SUPPORT.md", "TERMS.md", "CONTRIBUTING.md",
    "CHANGELOG.md", "spec/presence.md", "spec/state.schema.json", "spec/state.v1.schema.json",
    "docs/history.md", "docs/details.md", "docs/compatibility.md", "adapters/README.md",
    "adapters/capabilities.json", "conformance/README.md", "conformance/checker.py",
    "conformance/notify/scenarios.json", "conformance/fan-in/scenarios.json",
    "conformance/state/test_state.py",
    "conformance/sync/scenarios.json", "conformance/sync/test_sync.py",
    "conformance/cross-host/scenarios.json", "conformance/cross-host/test_cross_host.py",
    "adapters/generic/README.md", "adapters/generic/presence_sync.py",
    "scripts/presence_hook.py", "hooks/hooks.json", "hooks/codex.json",
    "hooks/switch.tsx", "hooks/switch.test.ts",
    "adapters/agy/README.md", "adapters/agy/plugin.json", "adapters/agy/hooks.json",
    "conformance/hooks/test_hooks.py",
    "evals/README.md", "evals/run.py", "evals/scenarios.json",
]
for path in required:
    if not (ROOT / path).is_file():
        fail(f"required file missing: {path}")

readme = (ROOT / "README.md").read_text(encoding="utf-8")
if "## What AFKSwitch reads, writes, and sends" not in readme:
    fail("README must disclose what the plugin reads, writes, and sends")
if "OpenAI" in readme:
    fail("README host wording must use Codex without vendor branding")
if any(command not in readme for command in ("/afk [optional context]", "/back [optional context]")):
    fail("README must show optional context on both commands")

# Every relative Markdown link points at something that exists.
for md in ROOT.rglob("*.md"):
    if ".git" in md.parts or "dist" in md.parts:
        continue
    if md.relative_to(ROOT).parts[0].startswith(".test-"):
        continue  # Local pytest --basetemp copies are not repository documentation.
    for target in re.findall(r"\]\(([^)#\s]+)", md.read_text(encoding="utf-8")):
        if not re.match(r"[a-z]+:", target) and not (md.parent / target).exists():
            fail(f"broken link {target!r} in {md.relative_to(ROOT)}")

# The plugin archive builds with one plugin root, '/' separators, and no MCP/app payloads.
zip_path = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "package.py")],
    check=True, capture_output=True, text=True,
).stdout.strip()
names = zipfile.ZipFile(zip_path).namelist()
if "plugin.json" not in names or "\\" in "".join(names):
    fail("plugin archive must have plugin.json at its root and '/' separators")
for name in ["SECURITY.md", "skills/afk/SKILL.md", "skills/back/SKILL.md", "skills/afk/agents/openai.yaml",
             "skills/afk/scripts/afkswitch_state.py", "skills/back/scripts/afkswitch_state.py",
             "scripts/presence_hook.py", "hooks/hooks.json", "hooks/codex.json", "hooks/switch.tsx",
             ".claude-plugin/plugin.json", "adapters/agy/README.md", "adapters/agy/plugin.json", "adapters/agy/hooks.json",
             *(image.removeprefix("./") for image in images)]:
    if name not in names:
        fail(f"plugin archive is missing {name}")
if any(n.endswith((".mcp.json", ".app.json")) for n in names):
    fail("the plugin archive must not contain MCP or app definitions")
if any("__pycache__" in n or n.endswith(".pyc") for n in names):
    fail("the plugin archive must not contain Python bytecode")
if any(".test." in Path(n).name for n in names):
    fail("the plugin archive must not contain function-hook tests")
with zipfile.ZipFile(zip_path) as z:
    for script in (HELPER, BACK_HELPER, ROOT / "hooks/switch.tsx", ROOT / "hooks/hooks.json"):
        if z.read(script.relative_to(ROOT).as_posix()) != script.read_bytes():
            fail("an archived helper or function-hook file differs from its repository copy")

print(f"AFKSwitch {version} validation passed.")
