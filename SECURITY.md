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

The only code AFKSwitch runs is `skills/afk/scripts/afkswitch_state.py`, a standard-library
Python script that runs when you type `/afk` or `/back`, reads and writes only the
`~/.afkswitch` folder, opens no network connection, starts no process, and exits.

## Security model

`/afk` and `/back` must never be interpreted as authorization for a deploy, merge, publication, purchase, destructive operation, production change, credential use, or elevation that otherwise required approval.

Host adapters should prefer native messaging and permission primitives. A peer message must not be used to route around the permission decision of another session.

## Reporting a vulnerability

Please open a private GitHub security advisory for the repository when available. Do not include secrets, tokens, credentials, or sensitive personal data in a public issue.

For non-security bugs, use GitHub Issues.
