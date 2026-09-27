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

| Host | Level | What works today |
|---|---|---|
| Claude Code | **Reference adapter — fan-in** | Durable state; `/afk` reaches every live local session; `/back` reaches them and collects a status from each, human blockers first. Built on the native `ListAgents` + `SendMessage` tools. |
| OpenAI Codex | **State-only** | Explicit `$afkswitch:afk` / `$afkswitch:back` and the same durable state. Codex gives the model no tool to message other Codex sessions, so AFKSwitch does not claim cross-session delivery there. |
| Other hosts | **Contract only** | [`spec/presence.md`](../spec/presence.md) + [`spec/state.schema.json`](../spec/state.schema.json). |

Levels, as defined in the spec: **state-only** (durable state), **notify** (+ peer
notification), **fan-in** (+ status collection on return).

## State

```text
~/.afkswitch/state.json
```

```json
{ "version": 1, "status": "afk", "since": "2026-09-27T01:53:00+01:00", "context": "sleep" }
```

## Claude Code behavior

- **Targets** are live local `interactive` sessions only. Remote Control rows, cloud
  sessions, other machines, subagents, and anything `offline` are never messaged.
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
the first `$afkswitch:afk` either asks you to approve writing `~/.afkswitch/state.json` or reports
`state write refused` — it never claims a state it could not save. To allow it for good,
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
