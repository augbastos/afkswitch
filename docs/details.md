# AFKSwitch — details

The README keeps it short. This page has the rest.

## Usage

```text
/afk                       # physically away, no return time
/afk sleep                 # asleep: remote answers unlikely, nothing that lights the screen
/afk work                  # at work: reachable only intermittently
/afk "walking the dog"     # any other context, kept verbatim
/back                      # present again, from any session
```

If another skill already answers to `/afk` or `/back`, use `/afkswitch:afk` and
`/afkswitch:back`. In Codex, always use `$afkswitch:afk` and `$afkswitch:back`: a bare
`$afk` can resolve to a different skill with the same name.

While you are away, each session records anything that needs you as one line:

```text
BLOCKED FOR HUMAN (physical): restart local service — stopped at elevation prompt — needs UAC — resume with: restart, then smoke test
```

A session that has not answered `/back` is *no reply yet* — never "done", "failed", or
"agreed".

## Support levels

<!-- capabilities:details:start -->
| Host | Level | Commands | Native primitives |
|---|---|---|---|
| Claude Code (reference) | **Fan-in** | `/afk` · `/back` | `ListAgents`, `SendMessage`, `notify_when_idle` |
| OpenAI Codex | **State-only** | `$afkswitch:afk` · `$afkswitch:back` | none (state only) |
<!-- capabilities:details:end -->

Other hosts: contract only ([`spec/presence.md`](../spec/presence.md) +
[`spec/state.schema.json`](../spec/state.schema.json)); see
[writing an adapter](../adapters/README.md). The canonical matrix is
[`adapters/capabilities.json`](../adapters/capabilities.json). Versions actually tested are
in [compatibility](compatibility.md).

Levels, as defined in the spec: **state-only** (durable state), **notify** (+ peer
notification), **fan-in** (+ status collection on return).

## State

```text
~/.afkswitch/state.json
```

```json
{ "version": 2, "status": "afk", "since": "2026-09-27T01:53:00+01:00", "context": "sleep", "generation": 7 }
```

`generation` goes up by one on every real change and orders changes without trusting
clocks; peer messages carry it as `[AFKSwitch g7]`, so a session that already heard about a
newer change ignores an older message. Repeating a command changes nothing. The full rules
(transaction order, locking, concurrency, migration) are in the
[spec](../spec/presence.md#state-protocol-v2).

### The state helper

Both skills save the state only through one bundled script,
`skills/afk/scripts/afkswitch_state.py` (`/back` reaches it through a two-line shim in
`skills/back/scripts/`). It needs **Python 3.9 or newer** and nothing else: standard library
only, no network, no background process.

```text
python3 skills/afk/scripts/afkswitch_state.py afk [--context TEXT | --context-stdin]
python3 skills/afk/scripts/afkswitch_state.py back
python3 skills/afk/scripts/afkswitch_state.py read
```

It prints one JSON line: the new status, generation, since, context, the previous state,
and whether it migrated a version 1 file, restarted the generation (`reset`) or kept a
`backup` of a malformed file; or `"ok": false` with an `error` and a readable `message`.
The skills notify peers only after `"ok": true`.

- Context longer than 2048 characters is refused with a clear message; nothing is saved.
- A file from AFKSwitch 0.4.x (version 1) is migrated automatically. Nothing to delete.
- A file written by a newer AFKSwitch is left alone: `unsupported state version N`.
- Without Python, the skills say `state helper unavailable (python not found)` and change
  nothing. They never write the file by hand.
- Writes go to a temp file in the same folder, then `fsync`, then an atomic rename. On
  Windows the rename replaces the old file in one step on the same volume; if another
  program holds the file open at that instant, the helper retries for about a second and
  then reports `state transition failed`.
- Privacy, best effort: on macOS and Linux the folder is `0700` and the file `0600`; on
  Windows they inherit your profile's permissions and are never widened.

## Claude Code behavior

- **Targets** are live local `interactive` sessions only. Remote Control rows, cloud
  sessions, other machines, subagents, and anything `offline` are never messaged.
- **State first.** Nobody is messaged unless the helper saved the state and read it back.
  Each message carries the generation; the `/afk` and `/back` reports show it as `g<G>`.
- **One message per session per invocation.** A confirmed failure is retried at most once;
  one failed session never stops the others.
- **Delivery is reported honestly.** A session in a different permission mode may hold a
  message for your approval; held or refused messages are reported as *not notified*.
- **`/back` never polls.** It uses the native one-shot `notify_when_idle` notice and folds
  replies in as they arrive.

### Known limitations

- A session started **after** `/afk`, or one that was unreachable, is not told you are away.
  That would need a startup hook, which AFKSwitch deliberately does not ship. The saved
  state still lets any session's `/back` report the absence.
- `ListAgents` does not expose working directories, so `/back` asks each session for its
  own `dir:` line.
- Two sessions with the same name need the ` [ref]` suffix; the skills handle it.

### Manual install (bare `/afk` and `/back` as personal skills)

```powershell
pwsh -File install.ps1              # install or update into ~/.claude/skills
pwsh -File install.ps1 -Uninstall   # remove
```

## Codex sandbox

Codex's default `workspace-write` sandbox refuses writes outside the current workspace, so
the first `$afkswitch:afk` either asks you to approve running the state helper with write
access to `~/.afkswitch` or reports `state transition failed: write refused` — it never
claims a state it could not save. To allow it for good,
add the absolute path of that folder to `~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
writable_roots = ["<absolute path of your home directory>/.afkswitch"]
```

On Windows, Codex runs `workspace-write` only when its Windows sandbox is configured
(`[windows] sandbox = "unelevated"` or `"elevated"`); otherwise the session is read-only and
`$afkswitch:afk` reports that the state was not saved.

## What AFKSwitch is not

Not an orchestration framework, fleet manager, scheduler, messaging server, permission
system, or autonomy framework. It is a two-command presence contract with host adapters.
