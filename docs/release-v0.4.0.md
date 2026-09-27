# AFKSwitch v0.4.0

**Tell your agents when you're away. Tell them when you're back.**

AFKSwitch 0.4.0 is the first model-agnostic release of the project that began as
`claude-session-presence`.

## Highlights

- Two-command contract: `/afk [optional context]` and `/back`.
- Global presence in Claude Code: `/afk` in one session reaches every live local session;
  `/back` works from any session and collects a status from each, human blockers first.
- Durable, host-neutral state at `~/.afkswitch/state.json` with a versioned JSON Schema.
- Presence stays separate from permissions: AFK is never authorization.
- Claude Code is the reference adapter (fan-in), built on native `ListAgents` +
  `SendMessage`. OpenAI Codex ships as a state-only adapter.
- No AFKSwitch server, account, telemetry, daemon, database, hook, or polling loop.
- MIT licensed.

## Install

Directly from this GitHub repository.

Claude Code, then `/afk` and `/back`:

```text
/plugin marketplace add https://github.com/augbastos/afkswitch
/plugin install afkswitch@afkswitch
```

Codex, then `$afkswitch:afk` and `$afkswitch:back`:

```text
codex plugin marketplace add https://github.com/augbastos/afkswitch
codex plugin add afkswitch@afkswitch
```

## Philosophy

AFK means the human is physically away. It does **not** mean unreachable, unrestricted
autonomy, or new permission. A physically blocked step waits; independent work continues.

## Known limitations

- Sessions started after `/afk` are not notified (that would need a startup hook).
- Codex has no model-side cross-session messaging, so AFKSwitch there is state-only. Saving
  the state needs `~/.afkswitch` as a writable root (and, on Windows, a configured Codex
  sandbox); see `docs/details.md`.
- Tested with Claude Code 2.1.283 and codex-cli 0.156.1.

## History

The repository keeps the September 2026 Claude Code prototype's commits, followed by the
AFKSwitch 0.4.0 commit. See `docs/history.md`.
