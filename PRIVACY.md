# Privacy

AFKSwitch is designed to work without an AFKSwitch-operated backend.

## Reference implementation

The reference local adapter:

- stores presence locally in `~/.afkswitch/state.json`;
- uses the agent host's own messaging primitives when available;
- does not create an AFKSwitch account;
- does not send telemetry to AFKSwitch;
- does not run analytics;
- does not sell or share user data;
- does not require credentials.

Optional context supplied after `/afk` is stored locally and may be sent to peer agent sessions by the host adapter so those sessions understand the operator's presence context.

## Host behavior

Agent hosts may process prompts, skills, messages, logs, or local files according to their own terms and privacy policies. AFKSwitch does not control host-level data handling.

## Future changes

If a future adapter introduces network services, telemetry, authentication, or externally stored data, this policy must be updated before that adapter is released.
