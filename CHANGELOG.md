# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-21

First implementation: three tiny skills that provide broadcast and human presence
semantics on top of Claude Code's native cross-session messaging.

### Added

- `/broadcast <message>` — relays one message **verbatim** to every reachable peer
  session, wrapped as `[User broadcast] ...` and nothing more. Multi-line supported.
- `/afk [context]` — announces absence and asks sessions to continue autonomously
  within the permissions they already hold, recording blockers instead of waiting.
  Grants nothing. Argument optional. Unreached sessions are reported separately, under
  a heading stating they do not know the user is away.
- `/back [anything]` — announces return and requests a short status in a single message
  per session, then consolidates replies **blockers first**. Requires no prior `/afk`
  and no stored state. Asks each session for its own working directory, the only way to
  label a session by project.
- `install.ps1` — installs the skills to `~/.claude/skills/` so they answer to the bare
  command names from any working directory; `-Uninstall` removes them.
- `.claude-plugin/plugin.json` — the same three skills as a plugin.

### Design constraints held

- **Hooks added by this plugin: 0.** No `hooks` key in the manifest, no hook file, no
  background process, nothing on a timer.
- Built entirely on the native `ListAgents` and `SendMessage` tools, verified against
  Claude Code 2.1.278. No daemon, server, database, socket, watcher or custom protocol.
- No state persisted anywhere. `/afk` and `/back` are inverse broadcasts; the receiving
  sessions hold the context in their own transcripts.
- At most one copy per target per invocation. Retry only after a confirmed failure, at
  most once, reported as `retried once`.
- Failure isolation: one bad target never cancels delivery to the rest. Every report
  closes with discovered / delivered / failed.
- `/back` is bounded by the turn, never by a polling loop, and uses the native one-shot
  `notify_when_idle` to distinguish a silent session from a slow one.

### Known limitations

- `/afk` reaches the sessions alive at the moment it runs. Sessions started afterwards
  inherit nothing — persistent presence would require a hook or daemon, both excluded.
- `ListAgents` exposes no working directory or repository, so sessions appear as short
  handles (`api-1f`) rather than project names. `/back` works around this by asking.
- Delivery is not readership; cloud and Remote Control sessions never report back.
