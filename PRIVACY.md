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

## Host behavior

Agent hosts may process prompts, skills, messages, logs, or local files according to their
own terms and privacy policies. AFKSwitch does not control host-level data handling.

## Future changes

If a future adapter introduces network services, telemetry, authentication, or externally
stored data, this policy must be updated before that adapter is released.
