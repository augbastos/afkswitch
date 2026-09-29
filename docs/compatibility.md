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

The cloud runs above had no model session: they prove the plugin installs with its helper
and the helper works from there, not that a model follows the skills. That was then run
with real model sessions on one machine:

| Host | Version | What was run | Result |
|---|---|---|---|
| Claude Code | 2.1.284 | Disposable sessions in an isolated config: `/afkswitch:afk` saved generation 1 before any message and notified both peers; `/afkswitch:back` from a session that never saw the `/afk` saved generation 2, reported the right duration and collected every reply; an older generation-1 message delivered afterwards was ignored; a state file from a newer version was refused, left unchanged, and nobody was told | passed |
| Codex CLI | 0.156.1 | `$afkswitch:afk`, `$afkswitch:afk sleep` (repeated: generation unchanged), `$afkswitch:back` with the duration from the saved state, a version 1 file migrated, a newer version refused and left unchanged; with the state folder allowed as a writable root | passed |

In Codex's `workspace-write` sandbox without a writable root for `~/.afkswitch`, the write
was refused and the skill reported `state transition failed` without claiming anything.

Still **pending** with real sessions: two sessions running `/afk` or `/back` at the same
moment, and the 2048-character context limit. Both are covered by the conformance suite
against the helper, not yet by a live model session.

## AFKSwitch 0.4.x

| Host | Version | Level validated |
|---|---|---|
| Claude Code | 2.1.283 | Reference adapter (fan-in), on the 0.4.x line |
| Codex CLI | 0.156.1 | State-only, on the 0.4.x line |

## Weekly check

`.github/workflows/host-compat.yml` installs the latest Claude Code and Codex CLIs every
week and runs their non-interactive plugin checks. Checks that need a login are skipped
with a notice. Its results are not copied here automatically.
