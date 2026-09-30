# Compatibility

Only versions that were actually run are listed. Anything not run is **pending**, never
assumed. The support levels themselves are in
[`adapters/capabilities.json`](../adapters/capabilities.json).

## AFKSwitch 0.6.0

| Host | Version | What was run | Result |
|---|---|---|---|
| Claude Code | 2.1.285 | `claude plugin validate --strict .` and validation of `.claude-plugin/plugin.json` | passed; no login or model session |
| Python | 3.14 | `conformance/hooks` with synthetic state and transcripts, including real CLI smoke checks | passed; read-only state hashes unchanged |

The hook tests prove script behavior, not host installation or model compliance.
End-to-end lifecycle injection in Claude Code, trusted Codex 0.159.0 plugins and
Antigravity CLI 1.2.13 remains unverified. Codex's manifest override and `PLUGIN_ROOT`
follow the [official packaging contract](https://developers.openai.com/plugins/build/plugins).
Installing the plugin alone does not trust its hooks. No peer notification or fan-in
is claimed for Codex or Antigravity.

## AFKSwitch 0.5.0

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

Then, with Claude Code 2.1.285 and disposable sessions:

- **Two sessions at the same moment.** A harness held the state lock until both sessions'
  helpers were waiting on it, then released it. `/afk work` + `/afk sleep` saved
  generations 1 and 2 in turn; `/afk sleep` + `/back` from generation 1 saved 2 and 3.
  The file stayed valid and the final state was the last writer's; each session reported
  what it saved, and the one that was overtaken said so. **Passed.**
- **Context limit.** 2048 characters were saved exactly; repeating them changed nothing.
  2049 characters first exposed a defect: a model rebuilt a repetitive text with code, and
  in another run cut a refused text to 2048 and retried. The `/afk` skill now forbids
  both. After the change, four 2049-character runs (repetitive and natural text) left the
  state file unchanged and reported that AFK was not set. **Passed.**

Load limit: with six processes each running ten transitions back to back, a transition can
wait longer than the helper's 15-second lock wait, and the helper refuses it with
`state is busy`. No stress run left a corrupt file or a duplicate generation.

## AFKSwitch 0.4.x

| Host | Version | Level validated |
|---|---|---|
| Claude Code | 2.1.283 | Reference adapter (fan-in), on the 0.4.x line |
| Codex CLI | 0.156.1 | State-only, on the 0.4.x line |

## Weekly check

`.github/workflows/host-compat.yml` installs the latest Claude Code and Codex CLIs every
week and runs their non-interactive plugin checks. Checks that need a login are skipped
with a notice. Its results are not copied here automatically.
