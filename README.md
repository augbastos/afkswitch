# AFKSwitch

![AFKSwitch](assets/wordmark-light.svg#gh-light-mode-only)
![AFKSwitch](assets/wordmark-dark.svg#gh-dark-mode-only)

**Tell your agents when you're away. Tell them when you're back.**

```text
/afk     I'm away from the machine
/back    I'm here again
```

Type `/afk` in one Claude Code session and every live Claude Code session on your machine is
told. They keep working, set aside only what truly needs you, and are told never to treat your
absence as permission. Type `/back` in any session and you get one summary: what needs you
first, then what got done.

## Install

### Claude Code

Install directly from this GitHub repository:

```text
/plugin marketplace add https://github.com/augbastos/afkswitch
/plugin install afkswitch@afkswitch
```

That first command is how Claude Code adds a plugin source; here the source is this
repository.

Then use `/afk` and `/back`.

### Codex

Install directly from this GitHub repository:

```text
codex plugin marketplace add https://github.com/augbastos/afkswitch
codex plugin add afkswitch@afkswitch
```

Codex uses the same mechanism: the plugin source is this repository.

Then use `$afkswitch:afk` and `$afkswitch:back`.

## Three rules

1. **Away is not unreachable.** You may still answer from your phone.
2. **Presence is not permission.** AFK never approves a deploy, merge, purchase, or anything
   that needed your OK before.
3. **Blocked on you is not blocked.** Only the step that needs you waits; the rest goes on.

## When you come back

```text
You're back · AFK (sleep) lasted 7h 12m · 3 sessions asked for status

Needs you now
  api     Elevation required to restart the local service.
Completed while AFK
  docs    Site build and link check complete.
No reply yet
  infra
```

## Where it works

| Host | What you get |
|---|---|
| Claude Code | Every live session is told, and `/back` collects a status from each. |
| Codex | Your presence is saved (once `~/.afkswitch` is writable, see [details](docs/details.md#codex-sandbox)). Codex cannot message its other sessions, so they are not told. |

## What AFKSwitch reads, writes, and sends

- **Writes** one local file, `~/.afkswitch/state.json`: status, time, and your optional note.
- **Sends**, in Claude Code only, short messages to your other Claude Code sessions on the
  same machine. Nothing goes to any server.
- **Runs** nothing: two Markdown skills, no hooks, scripts, or network calls.

## More

[Details and limits](docs/details.md) · [Spec](spec/presence.md) ·
[Privacy](PRIVACY.md) · [Security](SECURITY.md) · [Terms](TERMS.md) ·
[Support](SUPPORT.md) · [History](docs/history.md) · [Contributing](CONTRIBUTING.md)

MIT licensed.
