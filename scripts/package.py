"""Build dist/afkswitch-<version>.zip: the portable plugin (plugin.json, skills, assets, legal files)."""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

if DIST.exists():
    shutil.rmtree(DIST)
DIST.mkdir()

manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
version = manifest["version"]
out = DIST / f"afkswitch-{version}.zip"

include_files = [
    "plugin.json",
    ".codex-plugin/plugin.json",
    "LICENSE",
    "PRIVACY.md",
    "TERMS.md",
    "SUPPORT.md",
]
include_dirs = ["skills", "assets"]

with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for rel in include_files:
        z.write(ROOT / rel, rel)
    for directory in include_dirs:
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(ROOT).as_posix())

print(out)
