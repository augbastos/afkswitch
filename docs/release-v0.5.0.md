# AFKSwitch v0.5.0 (draft, not released)

**Presence state can no longer be corrupted or overtaken by stale messages.**

## Highlights

- One small bundled helper saves the state: validated, locked, written atomically, read
  back, and only then announced to other sessions. If saving fails, nobody is told.
- Every change gets a generation number. Messages carry it, so an older message that
  arrives late is ignored instead of undoing a newer `/afk` or `/back`.
- Two `/afk` or `/back` commands at the same moment can no longer corrupt the file.
- Context over 2048 characters is refused, never cut. An unreadable state file is kept as a
  backup before being replaced. A state file from a newer AFKSwitch is never overwritten.
- A conformance suite (state, notify, fan-in) that any future adapter can be tested
  against, and one support matrix that the docs are checked against.
- CI on Linux, Windows, and macOS.

Nothing changes in what `/afk` and `/back` mean: away is not unreachable, presence is not
permission, and a physical blocker is not a mission blocker.

## Requirement

Python 3.9 or newer on `PATH`. Without it, `/afk` and `/back` say
`state helper unavailable (python not found)` and change nothing.

## Upgrade

Claude Code (from a terminal), then restart your sessions:

```text
claude plugin marketplace update afkswitch
claude plugin update afkswitch@afkswitch
```

Codex:

```text
codex plugin marketplace upgrade afkswitch
codex plugin add afkswitch@afkswitch
```

Your existing `~/.afkswitch/state.json` (version 1) is migrated automatically the next time
you run `/afk` or `/back`. Nothing to delete. To roll back, reinstall 0.4.1; it will
overwrite the version 2 file with a version 1 file on its next write, and 0.5.0 migrates it
again later.

## Known limitations

- Sessions started after `/afk` are still not told (that would need a startup hook).
- Codex remains state-only: it gives the model no tool to message other Codex sessions.
- In Codex, saving the state needs `~/.afkswitch` as a writable root (or your approval);
  otherwise the skill reports that the write was refused.
- Tested with real sessions on one machine (Claude Code 2.1.284, Codex CLI
  0.156.1) and by CI on Linux, Windows, and macOS; see [compatibility](compatibility.md).
