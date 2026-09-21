# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-21

First implementation.

### Added

- `/broadcast <message>` — relays one message verbatim to every reachable peer session.
- `/afk [context]` — announces absence and asks sessions to continue autonomously
  within existing permissions, recording blockers instead of waiting. Grants nothing.
- `/back [anything]` — announces return and requests a four-line status in a single
  message per session, then consolidates replies as they arrive.
- `install.ps1` — installs the three skills to `~/.claude/skills/` so they answer to
  the bare command names; `-Uninstall` removes them.
- `.claude-plugin/plugin.json` — the same three skills as a plugin.

### Notes

- Built entirely on the native `ListAgents` and `SendMessage` tools, verified against
  Claude Code 2.1.278.
- No hooks, no daemon, no server, no watcher, no database, no state file. `/afk` and
  `/back` persist nothing; the broadcast itself is the feature.
- `/back` never blocks, polls or re-sends. Replies are asynchronous; sessions that have
  not answered are reported as *no reply yet*.
