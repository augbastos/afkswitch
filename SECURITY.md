# Security

## Scope

AFKSwitch communicates human presence. It is not a permission system, credential manager, sandbox, or security boundary.

The project intentionally avoids:

- credential collection;
- authentication bypass;
- privilege escalation;
- background daemons;
- network listeners;
- custom message brokers;
- telemetry;
- automatic destructive actions.

Explicit `/afk` and `/back` commands run the bundled standard-library state helper,
which reads and writes the `~/.afkswitch` folder and exits. Version 0.6 replaces the
earlier "no hooks" constraint with two read-only lifecycle hooks, `SessionStart` and
`UserPromptSubmit`, so sessions opened after `/afk` and changes from other hosts are
reconciled; in Claude Code it also runs on `PostToolUse`, so a running turn sees a click. They run `scripts/presence_hook.py`, read `~/.afkswitch/state.json` through
that helper and the end of the session transcript (the last 256 KiB, widening to 4 MiB and at most 64 MiB only while no marker is found) for the last AFKSwitch
marker, and output the universal presence event, plus the skill's fixed guidance text,
as host context only when needed.
Antigravity's PreInvocation variant reads state only and emits an ephemeral AFK event.
These hooks never write state or transcripts, change permissions, poll, run in the
background or use the network. In Claude Code a third read-only hook, `PermissionRequest`,
declines the host's own approval prompts while the saved state is `afk`: it outputs a deny
decision and never an allow, so the worst a forged state file can do is make prompts be
declined. It leaves the prompt alone only for the state helper's own run (a Python
interpreter, the helper, then `afk`, `back` or `read`, with nothing chained before or after
it outside quoted text; a command that merely mentions the helper is declined) and when
`AFKSWITCH_KEEP_PROMPTS` is `1`, `true` or `yes`. Errors exit 0 with no output; a broken hook cannot block the host,
but may leave session awareness stale. Codex and Antigravity hook files are experimental,
not selected by default manifests and not verified in a live host.

The optional Claude Code terminal function-hooks module reads the local state file and
the skills' own `references/message.md` through `$.fs.read`. It never writes, creates or
migrates the state file itself, reads a transcript, runs Python on render, starts a
background process or uses the network. Unknown state is neutral. A click is explicit
intent to run the bundled state helper once through `$.process.run` (no shell, fixed
arguments `afk` or `back`, no context, working directory the plugin's own folder so a
`python` planted in the open project is not picked up), so it takes effect even while a
turn is running. Only that helper writes state. After a change, the module lists sessions
with the host's `ListAgents` tool and sends each live local interactive session the
skill's fixed message through `$.session.send`. In its own session it writes one dim
`/afkswitch:afk` or `/afkswitch:back` line to the transcript (`$.ui.log`, never sent to
the model) and appends the same fixed message as a user-role row (`$.session.append`), so
the running turn reads the presence guidance. None of this grants anything, and every
session's permission rules are untouched. Pending actions cannot be pressed twice; failures display disk truth and
an error mark, never an assumed successful transition. Hook failures call `next(e)`.

Transcript markers and opaque presence context are informational, not authorization or
a security boundary. The bounded tail (at most 64 MiB) can omit an old marker; a same-generation state
recreation can be indistinguishable from a repeat without a checkpoint. The hook adds
no durable checkpoint, database or service. See the [sync contract](spec/presence.md#session-local-awareness-and-sync).

## Security model

`/afk` and `/back` must never be interpreted as authorization for a deploy, merge, publication, purchase, destructive operation, production change, credential use, or elevation that otherwise required approval.

Host adapters should prefer native messaging and permission primitives. A peer message must not be used to route around the permission decision of another session.

## Reporting a vulnerability

Please open a private GitHub security advisory for the repository when available. Do not include secrets, tokens, credentials, or sensitive personal data in a public issue.

For non-security bugs, use GitHub Issues.
