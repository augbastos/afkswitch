from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
if f"## [{version}]" not in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"):
    fail(f"CHANGELOG.md has no [{version}] section")

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
    otext = (skill_root / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if "CODEX" not in otext or "allow_implicit_invocation: false" not in otext:
        fail(f"skills/{name}/agents/openai.yaml must be explicit-invocation CODEX metadata")

if schema.get("properties", {}).get("status", {}).get("enum") != ["available", "afk"]:
    fail("state schema status enum changed unexpectedly")
if schema.get("properties", {}).get("version", {}).get("const") != 1:
    fail("state schema version must remain 1 for this release")

# Legacy product surface stays out of current docs and skills (CHANGELOG keeps history).
current = ["README.md", "install.ps1", "spec/presence.md", *map(str, skill_root.rglob("*.md"))]
for path in current:
    text = (ROOT / path).read_text(encoding="utf-8")
    for legacy in ["~/.claude/session-presence", "/broadcast", "/live"]:
        if legacy in text:
            fail(f"legacy product surface {legacy!r} remains in {path}")

required = [
    "LICENSE", "PRIVACY.md", "SECURITY.md", "SUPPORT.md", "TERMS.md", "CONTRIBUTING.md",
    "CHANGELOG.md", "spec/presence.md", "spec/state.schema.json", "docs/history.md",
    "docs/details.md",
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
             *(image.removeprefix("./") for image in images)]:
    if name not in names:
        fail(f"plugin archive is missing {name}")
if any(n.endswith((".mcp.json", ".app.json")) for n in names):
    fail("the skills-only plugin archive must not contain MCP or app definitions")

print(f"AFKSwitch {version} validation passed.")
