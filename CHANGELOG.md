# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-21

First implementation: three tiny skills that provide broadcast and human presence
semantics on top of Claude Code's native cross-session messaging.

### Commands

- `/broadcast <message>` — relays one message **verbatim** to every reachable peer
  session, wrapped as `[User broadcast] ...` and nothing more. Multi-line preserved.
  Stateless: never reads or writes presence.
- `/afk` — user is away. No return time assumed.
- `/afk sleep` — user is sleeping. Extra emphasis on causing no interaction that could
  wake them: nothing that lights a screen, raises a window, or leaves a dialog open
  overnight.
- `/afk work` — user is away at work; may take hours to answer.
- `/afk <free text>` — passed through verbatim as context.
- `/back` — user returned. Clears the state, announces, requests status, consolidates.

### Absence policy

While AFK, sessions continue safe autonomous work but defer anything that may require
authentication, elevation, credentials or physical user interaction.

- They keep reading, analysing, coding, fixing, testing, reviewing, researching,
  documenting and running already-authorized local work, and do not message the user
  while he is away — it keeps for `/back`.
- They defer anything that could predictably raise an interactive prompt: password manager or
  any vault unlock, Windows password / PIN / Hello / fingerprint / face, passkey, UAC or
  elevation, credential or browser auth popup, interactive OAuth or device
  authorization, MFA/2FA or phone push approval, or any physical confirmation.
- **They do not run a command just to find out whether it prompts.** A reasonable chance
  is enough to defer; by the time a prompt is open the screen is already lit.
- AFK never grants permissions. Not for a destructive action, deploy, merge,
  publication, production change, purchase, outbound external message, anything
  irreversible, or credentials not already held.
- A blocked step blocks only itself. Independent work finishes, and the session records
  `BLOCKED FOR USER: <task> — stopped at <point> — needs <interaction> — resume with: <command>`.
- `/back` does not authorize either. Deferred steps may be reconsidered, not executed:
  "I need elevation to continue. Ready when you are."

### Global presence

- Presence belongs to the user, not to a repository or terminal. `/afk` from any session
  notifies all reachable sessions; `/back` from **any** session — not necessarily the
  same one — returns and collects status.
- No owner: the `/afk` terminal may be closed before `/back` runs.
- Minimal shared state at `~/.claude/session-presence/state.json`
  (`status`, `mode`, `since`, `message`), so a session that never saw the `/afk` can
  still report how long the user was gone. Plain file, read and written only by these
  skills.
- Idempotent: `/afk` twice, `/back` twice, and `/back` with no prior `/afk` all work.
  A missing or corrupt state file is never an error.

### `/back` output order

`Needs you now` → `Completed while AFK` → `Still running` → `Other blockers` →
`No reply yet`. The first section collects everything blocked on password manager, a password,
PIN, Windows Hello, UAC or elevation, MFA, a passkey, a login, a credential, a
confirmation or a human decision, each with where it stopped and how to resume.

### Design constraints held

- **Hooks added by this plugin: 0.** No `hooks` key in the manifest, no hook file, no
  background process, nothing on a timer. The state file did not change this.
- Built entirely on the native `ListAgents` and `SendMessage` tools, verified against
  Claude Code 2.1.278. No daemon, server, database, socket, watcher or custom protocol.
- No password manager integration, no credential handling, no control over Windows lock state,
  no elevation check, no prompt detection. The skill transmits policy; sessions apply it.
- At most one copy per target per invocation. Retry only after a confirmed failure, at
  most once, reported as `retried once`.
- Failure isolation: one bad target never cancels delivery to the rest. Every report
  closes with discovered / delivered / failed.
- `/back` is bounded by the turn, never by a polling loop, and uses the native one-shot
  `notify_when_idle` to distinguish a silent session from a slow one.

### Installation

- `install.ps1` installs the skills to `~/.claude/skills/` so they answer to the bare
  command names in any session on the machine, regardless of repository or working
  directory; `-Uninstall` removes them.
- `.claude-plugin/plugin.json` — the same three skills as a plugin.

### Known limitations

- The broadcast reaches sessions alive at that moment. Sessions started afterwards are
  not notified and nothing makes them read the state file on startup — that would need a
  `SessionStart` hook, excluded by design. The state record itself survives.
- `ListAgents` exposes no working directory or repository, so sessions appear as short
  handles (`api-1f`). `/back` works around it by asking each session for its own `dir:`.
- Delivery is not readership; cloud and Remote Control sessions never report back.
