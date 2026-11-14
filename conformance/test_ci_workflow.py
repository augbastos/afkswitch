"""Offline contracts for the CI matrix, base policy and aggregate check."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
JOBS = dict(re.findall(r"^  ([\w-]+):\n(.*?)(?=^  [\w-]+:|\Z)",
                       WORKFLOW.split("jobs:\n", 1)[1], re.M | re.S))
GIT = shutil.which("git")
BASH = (shutil.which("bash", path=str(Path(GIT).resolve().parents[1] / "bin")) if os.name == "nt" and GIT
        else shutil.which("bash"))


def test_workflow_contract():
    assert WORKFLOW.startswith("# CI profile: public\nname: CI\n")
    assert {p.name for p in (ROOT / ".github/workflows").glob("*.yml")} == {
        "ci.yml", "host-compat.yml", "dependabot-automerge.yml"}
    assert '  push:\n    branches: ["main"]' in WORKFLOW
    assert "types: [opened, synchronize, reopened, ready_for_review]" in WORKFLOW
    assert "  workflow_dispatch:" in WORKFLOW
    assert "permissions:\n  contents: read\n" in WORKFLOW
    assert "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}" in WORKFLOW
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in WORKFLOW
    assert "pull_request_target" not in WORKFLOW
    assert set(JOBS) == {"safety", "checks", "mod-tests", "windows-installer-smoke", "ci-passed"}
    for job in JOBS.values():
        assert "timeout-minutes:" in job
    for line in WORKFLOW.splitlines():
        if "uses:" in line:
            assert re.search(r"uses: actions/[\w-]+@[0-9a-f]{40} # v[\d.]+$", line)
    safety = JOBS["safety"]
    assert "name: Safety\n" in safety
    assert "if: github.event_name == 'pull_request'" in safety
    assert "ref: ${{ github.event.pull_request.base.sha }}" in safety
    assert "sparse-checkout: .github/scripts" in safety
    assert "if: hashFiles('base-policy/.github/scripts/safety.sh') == ''" in safety
    assert safety.count("persist-credentials: false") == 3
    assert "fetch-depth: 0" in safety
    assert "if [ -f base-policy/.github/scripts/safety.sh ]; then\n            bash base-policy/.github/scripts/safety.sh" in safety
    assert "bash bootstrap-policy/.github/scripts/safety.sh" in safety
    assert "needs: [safety, checks, mod-tests, windows-installer-smoke]" in JOBS["ci-passed"]
    assert "name: CI passed\n" in JOBS["ci-passed"]
    assert "if: always()" in JOBS["ci-passed"]


def test_supported_matrix_and_cached_test_steps():
    legs = re.findall(r'- os: (\S+)\n\s+platform: (\S+)\n\s+python: "([\d.]+)"', JOBS["checks"])
    assert legs == [("ubuntu-latest", "Ubuntu", "3.13"), ("windows-latest", "Windows", "3.13"),
                    ("macos-latest", "macOS", "3.13"), ("ubuntu-24.04", "Ubuntu", "3.9")]
    assert "name: Test (${{ matrix.platform }}, Python ${{ matrix.python }})" in JOBS["checks"]
    assert "name: Mod tests (${{ matrix.platform }})" in JOBS["mod-tests"]
    assert re.findall(r"- os: (\S+)\n\s+platform: (\S+)", JOBS["mod-tests"]) == [
        ("ubuntu-latest", "Ubuntu"), ("windows-latest", "Windows"), ("macos-latest", "macOS")]
    assert "name: Installer smoke (Windows)" in JOBS["windows-installer-smoke"]
    for text in ("cache: pip", "cache-dependency-path: .github/ci/requirements.txt",
                 "python scripts/validate.py", "python scripts/package.py", "python scripts/test_ci.py"):
        assert text in JOBS["checks"]
    for text in ("cache: npm", "cache-dependency-path: .github/ci/package-lock.json",
                 "npm ci --prefix .github/ci --no-audit --no-fund",
                 "claude plugin test .", "claude plugin validate --strict ."):
        assert text in JOBS["mod-tests"]


@pytest.mark.skipif(not BASH or not shutil.which("jq"), reason="Bash and jq required")
def test_actual_aggregate_rejects_failures_skips_and_cancellations():
    gate = textwrap.dedent(JOBS["ci-passed"].split("        run: |\n", 1)[1]).strip()
    commands = ["gate() {\n" + gate + "\n}"]
    # Exercise every job's non-success results on every trigger.
    cases = [(safety, "success", "success", "success")
             for safety in ("success", "failure", "skipped", "cancelled")]
    for index in range(1, 4):
        for result in ("failure", "skipped", "cancelled"):
            results = ["success"] * 4
            results[index] = result
            cases.append(tuple(results))
    for event in ("pull_request", "push", "workflow_dispatch"):
        for results in cases:
            expected = all(r == "success" for r in results[1:]) and (
                results[0] == "success" or (results[0] == "skipped" and event != "pull_request"))
            needs = json.dumps({key: {"result": value} for key, value in zip(
                ("safety", "checks", "mod-tests", "windows-installer-smoke"), results)})
            commands.append(f"EVENT_NAME='{event}' NEEDS_JSON='{needs}' gate >/dev/null 2>&1")
            commands.append(f'[ "$?" -eq {0 if expected else 1} ] || exit 99')
    result = subprocess.run([BASH], input="\n".join(commands), cwd=ROOT,
                            capture_output=True, text=True, timeout=60,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert result.returncode == 0, result.stderr


def test_safety_scan_pins_and_public_self_protection():
    script = (ROOT / ".github/scripts/safety.sh").read_text(encoding="utf-8")
    assert "/v8.21.2/gitleaks_8.21.2_linux_x64.tar.gz" in script
    assert "5bc41815076e6ed6ef8fbecc9d9b75bcae31f39029ceb55da08086315316e3ba" in script
    assert ('--log-opts="--text --no-textconv --no-ext-diff --diff-merges=first-parent '
            '$BASE..$HEAD_SHA"') in script
    rule = re.search(r"'([^']+) :: changes the merge safety check itself'", script)[1]
    for path in (".github/scripts/safety.sh", ".github/safety-critical.txt", ".github/workflows/ci.yml"):
        assert re.search(rule, path)
    assert not re.search(rule, "docs/ci.yml")
    assert "gh api --paginate" in script and ".previous_filename" in script
    assert "safety-critical.txt?ref=$BASE" in script
    assert "set -euo pipefail" in script
    assert "invalid critical-path rule on the base revision" in script



FAKES = {
    "curl": 'exit "${DOWNLOAD_STATUS:-0}"\n',
    "sha256sum": 'cat >/dev/null\nexit "${CHECKSUM_STATUS:-0}"\n',
    "tar": 'cp "$FAKE_GITLEAKS" "$4/gitleaks"\nchmod +x "$4/gitleaks"\n',
    "gitleaks": ('printf "%s\\n" "$*" > "$SCAN_ARGS"\n'
                 '[ -e .gitleaksignore ] || [ -e .gitleaks.toml ] && echo present >> "$SCAN_ARGS"\n'
                 'exit "${SCAN_STATUS:-0}"\n'),
    "git": 'printf "%s\\n" "${HEAD_SHA_FAKE:-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb}"\n',
    "gh": textwrap.dedent("""\
        case "$*" in
          *'/pulls/'*) printf '%s\\n' "$CHANGED_FILES" ;;
          *'/contents/.github?ref='*) printf '%s\\n' "$BASE_ENTRIES" ;;
          *) exit 99 ;;
        esac
        """),
}


def run_policy(tmp_path, **changes):
    """Run the real safety.sh against fake curl/tar/gitleaks/git/gh; returns (code, output, scan args)."""
    fake = tmp_path / "bin"
    fake.mkdir()
    if changes.pop("PLANT_GITLEAKS", None):
        for name in (".gitleaksignore", ".gitleaks.toml"):
            (tmp_path / name).write_text("allow everything\n")
    for name, content in FAKES.items():
        path = fake / name
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + content, newline="\n")
        path.chmod(0o755)
    env = dict(os.environ, FAKE_BIN=fake.as_posix(), PR_DIR=tmp_path.as_posix(),
               TMPDIR=tmp_path.as_posix(), REPO="test/repo", PR="123", BASE="a" * 40,
               FAKE_GITLEAKS=(fake / "gitleaks").as_posix(),
               SCAN_ARGS=(tmp_path / "scan-args").as_posix(), CHANGED_FILES="docs/test.md",
               BASE_ENTRIES="scripts\nworkflows")
    env.update(changes)
    # Resolve inside Bash so Windows drive colons never split the mock PATH.
    command = 'export PATH="$(cd "$FAKE_BIN" && pwd):$PATH"; exec bash .github/scripts/safety.sh'
    result = subprocess.run([BASH, "-c", command], cwd=ROOT, env=env, capture_output=True,
                            text=True, timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    args = (tmp_path / "scan-args").read_text() if (tmp_path / "scan-args").exists() else ""
    return result.returncode, result.stdout + result.stderr, args


@pytest.mark.skipif(not BASH, reason="Bash required")
def test_scan_uses_hardened_arguments_and_commit_range(tmp_path):
    code, output, args = run_policy(tmp_path)
    assert code == 0, output
    assert "--ignore-gitleaks-allow" in args
    assert "--config " in args
    assert "--gitleaks-ignore-path " in args
    assert ("--log-opts=--text --no-textconv --no-ext-diff --diff-merges=first-parent "
            + "a" * 40 + ".." + "b" * 40) in args
    assert "no critical effect" in output


@pytest.mark.skipif(not BASH, reason="Bash required")
def test_pr_cannot_configure_its_own_scanner(tmp_path_factory):
    # The PR's .gitleaksignore/.gitleaks.toml are gone before gitleaks runs,
    # and adding or changing them (or .gitattributes) needs the owner.
    code, output, args = run_policy(tmp_path_factory.mktemp("plant"), PLANT_GITLEAKS="1")
    assert code == 0, output
    assert "present" not in args
    for path in (".gitleaksignore", "sub/.gitleaks.toml", ".gitattributes"):
        code, output, _ = run_policy(tmp_path_factory.mktemp("changed"), CHANGED_FILES=path)
        assert code == 1, output
        assert "changes what the secret scan sees" in output


@pytest.mark.skipif(not BASH, reason="Bash required")
@pytest.mark.parametrize("changes", [{"BASE": "main"}, {"HEAD_SHA_FAKE": "HEAD"}])
def test_invalid_commit_ids_fail_closed(tmp_path, changes):
    code, output, _ = run_policy(tmp_path, **changes)
    assert code == 1, output
    assert "invalid base or head commit" in output
