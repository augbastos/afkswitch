"""Run independent conformance modules in processes within one CI job."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def run_module(module):
    # Each module owns its pytest temp tree; fixtures isolate state, env and copies.
    relative = module.relative_to(ROOT)
    temp = ROOT / ".test-ci" / relative.with_suffix("")
    temp.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(relative), "-q", "-p", "no:cacheprovider",
         "--basetemp", str(temp)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return relative, result.returncode, result.stdout, time.monotonic() - start


def main():
    modules = sorted((ROOT / "conformance").rglob("test_*.py"))
    if not modules:
        print("No conformance modules found", file=sys.stderr)
        return 1
    failed = False
    with ThreadPoolExecutor(max_workers=min(len(modules), os.cpu_count() or 1)) as pool:
        for module, code, output, seconds in pool.map(run_module, modules):
            print(f"\n{module}: {seconds:.2f}s (exit {code})\n{output}", flush=True)
            failed |= code != 0
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
