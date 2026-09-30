# AFKSwitch

![AFKSwitch](assets/wordmark-light.svg#gh-light-mode-only)
![AFKSwitch](assets/wordmark-dark.svg#gh-dark-mode-only)

**Tell your agents when you're away. Tell them when you're back.**

```text
/afk     I'm away from the machine
/back    I'm here again
```

Type `/afk` in one Claude Code session and every live Claude Code session on your machine that
the host can reach is told; the report names any it could not reach. They keep working, set
aside only what truly needs you, and are told never to treat your absence as permission. Type
`/back` in any session and you get one summary: what needs you first, then what got done.

## Install

### Claude Code

AFKSwitch is listed in the Claude plugin directory (Claude Code, Cowork, and the Claude
apps): search for **AFKSwitch**. The directory can lag behind the latest release here.

Or install directly from this GitHub repository:

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

### Requirement

Python 3.9 or newer on your `PATH` (`python3`, `python`, or `py -3`). A small bundled
script saves the state safely; without Python, `/afk` and `/back` say
`state helper unavailable (python not found)` and change nothing.

## Three rules

1. **Away is not unreachable.** You may still answer from your phone.
2. **Presence is not permission.** AFK never approves a deploy, merge, purchase, or anything
   that needed your OK before.
3. **Blocked on you is not blocked.** Only the step that needs you waits; the rest goes on.

## When you come back

```text
You're back · AFK (sleep) lasted 7h 12m · g8 · discovered 3 · notified 3 · status requested from 3

Needs you now
  api     Elevation required to restart the local service.
Completed while AFK
  docs    Site build and link check complete.
No reply yet
  infra
```

## Where it works

<!-- capabilities:readme:start -->
| Host | Level | What you get |
|---|---|---|
| Claude Code | Fan-in | Every live local session that the host confirms delivery to is told, and /back collects a status from each. |
| OpenAI Codex | State-only | Your presence is saved. Codex gives the model no tool to message its other sessions, so they are not told. |
<!-- capabilities:readme:end -->

Codex saves the state once `~/.afkswitch` is writable (see
[details](docs/details.md#codex-sandbox)). Tested versions: [compatibility](docs/compatibility.md).

## What AFKSwitch reads, writes, and sends

AFKSwitch runs no server and makes no network requests of its own. Messages between
sessions travel through the host's own mechanisms and are governed by the host.

- **Writes** one local file, `~/.afkswitch/state.json` (status, time, your optional note,
  and a counter that orders changes), through a bundled Python script that only reads and
  writes that folder. A lock file appears there for milliseconds while it writes; an
  unreadable old file is kept beside it as `state.json.corrupt-<time>`.
- **Sends**, in Claude Code only, short messages to your other Claude Code sessions on the
  same machine, using Claude Code's own messaging.
- **Runs** nothing in the background: no hooks, daemon, server, or telemetry. The script runs
  only when you type `/afk` or `/back`, and exits.

## More

[Details and limits](docs/details.md) · [Spec](spec/presence.md) ·
[Compatibility](docs/compatibility.md) · [Writing an adapter](adapters/README.md) ·
[Conformance tests](conformance/README.md) · [Privacy](PRIVACY.md) · [Security](SECURITY.md) · [Terms](TERMS.md) ·
[Support](SUPPORT.md) · [History](docs/history.md) · [Contributing](CONTRIBUTING.md)

MIT licensed.
