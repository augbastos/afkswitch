"""Build dist/afkswitch-<version>.zip: manifests, skills, hooks and experimental adapters."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

DIST.mkdir(exist_ok=True)

manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
version = manifest["version"]
out = DIST / f"afkswitch-{version}.zip"

include_files = [
    "plugin.json",
    ".codex-plugin/plugin.json",
    ".claude-plugin/plugin.json",
    "scripts/presence_hook.py",
    "LICENSE",
    "PRIVACY.md",
    "SECURITY.md",
    "TERMS.md",
    "SUPPORT.md",
]
include_dirs = ["skills", "assets", "hooks", "adapters/agy"]

# Each skill is independently usable; reject an accidental return-helper drift.
helpers = [ROOT / "skills" / name / "scripts" / "afkswitch_state.py" for name in ("afk", "back")]
if helpers[0].read_bytes() != helpers[1].read_bytes():
    raise SystemExit("afk/back state helpers differ; package requires byte-identical copies")
hook_manifest = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))
if "modules" in hook_manifest or (ROOT / "hooks/switch.tsx").exists():
    raise SystemExit("directory build must not ship the switch module")

with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for rel in include_files:
        z.write(ROOT / rel, rel)
    for directory in include_dirs:
        for path in sorted((ROOT / directory).rglob("*")):
            if (path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
                    and ".test." not in path.name):
                z.write(path, path.relative_to(ROOT).as_posix())

print(out)
