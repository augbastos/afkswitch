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
SHIM = ROOT / "skills" / "back" / "scripts" / "afkswitch_state.py"
for script in (HELPER, SHIM):
    if not script.is_file():
        fail(f"state helper missing: {script.relative_to(ROOT).as_posix()}")
    try:
        compile(script.read_text(encoding="utf-8"), str(script), "exec")
    except SyntaxError as exc:
        fail(f"{script.relative_to(ROOT).as_posix()} does not compile: {exc}")
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
    runs = [([str(HELPER), "afk", "--context", "validate"], "afk"), ([str(SHIM), "back"], "available"),
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

# Nothing that runs by itself: no hooks, MCP servers, or apps in any manifest or folder.
for manifest in (portable, claude, legacy):
    for key in ("hooks", "mcpServers", "apps"):
        if key in manifest:
            fail(f"manifests must not declare {key!r}")
if (ROOT / "hooks").exists():
    fail("the plugin must not ship a hooks folder")

# One canonical capability matrix, rendered into the docs.
capabilities = load_json("adapters/capabilities.json")
LEVEL_NAMES = {"state-only": "State-only", "notify": "Notify", "fan-in": "Fan-in"}
for host in capabilities["hosts"]:
    if host["level"] not in capabilities["levels"]:
        fail(f"adapters/capabilities.json: unknown level {host['level']!r} for {host['id']}")


def host_label(host: dict) -> str:
    return f"{host['name']} (reference)" if host.get("reference") else host["name"]


def render(style: str) -> str:
    hosts = capabilities["hosts"]
    if style == "readme":
        lines = ["| Host | Level | What you get |", "|---|---|---|"]
        lines += [f"| {h['name']} | {LEVEL_NAMES[h['level']]} | {h['summary']} |" for h in hosts]
    elif style == "details":
        lines = ["| Host | Level | Commands | Native primitives |", "|---|---|---|---|"]
        lines += [f"| {host_label(h)} | **{LEVEL_NAMES[h['level']]}** | {' · '.join(f'`{c}`' for c in h['invoke'])} | "
                  f"{', '.join(f'`{n}`' for n in h['native']) or 'none (state only)'} |" for h in hosts]
    elif style == "spec":
        lines = ["| Host | Level |", "|---|---|"]
        lines += [f"| {host_label(h)} | {LEVEL_NAMES[h['level']]}"
                  f"{' via native ' + ' + '.join(f'`{n}`' for n in h['native']) if h['native'] else ''} |" for h in hosts]
    else:
        fail(f"unknown capabilities style {style!r}")
    return "\n".join(lines)


MARKER = re.compile(r"(<!-- capabilities:(\w+):start -->\n)(.*?)(<!-- capabilities:\2:end -->)", re.S)
rendered_docs = {"README.md": "readme", "docs/details.md": "details", "spec/presence.md": "spec"}
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
]
for path in required:
    if not (ROOT / path).is_file():
        fail(f"required file missing: {path}")

readme = (ROOT / "README.md").read_text(encoding="utf-8")
if "## What AFKSwitch reads, writes, and sends" not in readme:
    fail("README must disclose what the plugin reads, writes, and sends")

# Every relative Markdown link points at something that exists.
for md in ROOT.rglob("*.md"):
    if ".git" in md.parts or "dist" in md.parts:
        continue
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
for name in ["skills/afk/SKILL.md", "skills/back/SKILL.md", "skills/afk/agents/openai.yaml",
             "skills/afk/scripts/afkswitch_state.py", "skills/back/scripts/afkswitch_state.py",
             *(image.removeprefix("./") for image in images)]:
    if name not in names:
        fail(f"plugin archive is missing {name}")
if any(n.endswith((".mcp.json", ".app.json")) for n in names):
    fail("the skills-only plugin archive must not contain MCP or app definitions")
if any("__pycache__" in n or n.endswith(".pyc") for n in names):
    fail("the plugin archive must not contain Python bytecode")
with zipfile.ZipFile(zip_path) as z:
    if z.read("skills/afk/scripts/afkswitch_state.py") != HELPER.read_bytes():
        fail("the archived state helper differs from the repository copy")

print(f"AFKSwitch {version} validation passed.")
