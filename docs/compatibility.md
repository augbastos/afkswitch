# Compatibility

Only versions that were actually run are listed. Anything not run is **pending**, never
assumed. The support levels themselves are in
[`adapters/capabilities.json`](../adapters/capabilities.json).

## AFKSwitch 0.5.0 (unreleased)

| Host | Version | Where | What was run | Result |
|---|---|---|---|---|
| Claude Code | 2.1.284 | Linux cloud container, no login | `claude plugin validate --strict .`; `claude plugin marketplace add <repo>` + `claude plugin install afkswitch@afkswitch`; the state helper and the `/back` shim run from the installed plugin cache | passed; both helper files present in the cache and ran |
| Codex CLI | 0.159.0 | Linux cloud container, no login | `codex plugin marketplace add <repo>` + `codex plugin add afkswitch@afkswitch` + `codex plugin list`; the state helper and the shim run from the installed plugin cache | passed; both helper files present in the cache and ran |
| Python | 3.9, 3.13 | GitHub Actions: Linux, Windows, macOS | `scripts/validate.py`, `scripts/package.py`, `python -m pytest conformance` | passed on the pull request CI (all jobs green) |

**Full host validation of 0.5.0 is pending a local host run**: a real Claude Code fleet
(`/afk`, `/back`, notify, fan-in, stale generations, persistence failure before notify,
concurrency) and Codex state-only use (`$afkswitch:afk`, `$afkswitch:back`, migration,
refusal of a newer state version, context limits). The cloud runs above had no model
session: they prove the plugin installs with its helper and the helper works from there,
not that a model follows the skills.

## AFKSwitch 0.4.x

| Host | Version | Level validated |
|---|---|---|
| Claude Code | 2.1.283 | Reference adapter (fan-in), on the 0.4.x line |
| Codex CLI | 0.156.1 | State-only, on the 0.4.x line |

## Weekly check

`.github/workflows/host-compat.yml` installs the latest Claude Code and Codex CLIs every
week and runs their non-interactive plugin checks. Checks that need a login are skipped
with a notice. Its results are not copied here automatically.
