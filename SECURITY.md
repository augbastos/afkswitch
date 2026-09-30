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
reconciled. They run `scripts/presence_hook.py`, read `~/.afkswitch/state.json` through
that helper and at most the last 256 KiB of the session transcript for the last AFKSwitch
marker, and output the universal presence event as host context only when needed.
Antigravity's PreInvocation variant reads state only and emits an ephemeral AFK event.
Hooks never write state or transcripts, change permissions, poll, run in the background
or use the network. Errors exit 0 with no output; a broken hook cannot block the host,
but may leave session awareness stale. Codex requires the user's hook trust.

Transcript markers and opaque presence context are informational, not authorization or
a security boundary. The bounded tail can omit an old marker; a same-generation state
recreation can be indistinguishable from a repeat without a checkpoint. The hook adds
no durable checkpoint, database or service. See the [sync contract](spec/presence.md#session-local-awareness-and-sync).

## Security model

`/afk` and `/back` must never be interpreted as authorization for a deploy, merge, publication, purchase, destructive operation, production change, credential use, or elevation that otherwise required approval.

Host adapters should prefer native messaging and permission primitives. A peer message must not be used to route around the permission decision of another session.

## Reporting a vulnerability

Please open a private GitHub security advisory for the repository when available. Do not include secrets, tokens, credentials, or sensitive personal data in a public issue.

For non-security bugs, use GitHub Issues.
