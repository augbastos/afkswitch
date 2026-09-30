# Privacy

AFKSwitch runs no server and makes no network requests of its own. Messages between
sessions travel through the host's own mechanisms and are governed by the host.

## What the reference implementation does

- stores presence locally in `~/.afkswitch/state.json`: status, the time it began, your
  optional note, and a change counter (`generation`);
- keeps an unreadable old state file beside it as `state.json.corrupt-<time>`, so nothing
  you wrote is silently destroyed; you may delete those copies at any time;
- restricts that folder to your user where the operating system allows it without
  elevation (`0700` / `0600` on macOS and Linux; on Windows it inherits your profile's
  permissions and is never widened);
- in Claude Code, uses the host's own session messaging to tell your other local sessions;
- does not create an AFKSwitch account;
- does not send telemetry or run analytics;
- does not sell or share user data;
- does not require credentials.

Optional context supplied after `/afk` is stored locally and, in hosts with peer messaging,
is included in the messages the host delivers to your other sessions so they understand
your presence context.

Optional context after `/back` is event-only: it appears in the helper's JSON output and
peer messages when supported, while durable available state keeps context null. A generic
local host can read state once at a lifecycle boundary and keep generation, presence and
an opaque reset checkpoint in its session context. No watcher or background process is added.

The opt-in eval harness stores synthetic prompts' model outputs and results locally at
the chosen output path. It runs only when explicitly invoked; host data handling still
applies, and outputs should be reviewed before sharing.

## Host behavior

Version 0.6 replaces the earlier "no hooks" constraint with two read-only lifecycle
hooks, SessionStart and UserPromptSubmit, because sessions started after `/afk` and
changes from another host need current presence. `scripts/presence_hook.py` reads
`~/.afkswitch/state.json` through the existing helper and at most the last 256 KiB of
the session transcript to find its last AFKSwitch marker. It outputs only the universal
presence event (status, generation, AFK context and presence semantics) in host context,
never transcript contents. Antigravity's PreInvocation variant reads no transcript and
outputs an ephemeral AFK event only. Hooks never write state or transcripts, change
permissions, poll, run in the background or use the network. Any error exits 0 without
output; missing, invalid and future state versions also produce nothing. No database
or checkpoint file is created. Host transcript retention still follows host policy.

Agent hosts may process prompts, skills, messages, logs, or local files according to their
own terms and privacy policies. AFKSwitch does not control host-level data handling.

## Future changes

If a future adapter introduces network services, telemetry, authentication, or externally
stored data, this policy must be updated before that adapter is released.
