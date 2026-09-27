# AFKSwitch Presence Contract

AFKSwitch defines one small piece of shared human-agent state: whether the human operator is physically present.

## Commands

```text
/afk [optional context]
/back
```

## States

- `available` — the operator is physically present.
- `afk` — the operator is physically away.

Adapters may expose richer UI, but these are the only portable states.

## Invariants

1. **Presence is not reachability.** An AFK operator may still be reachable remotely.
2. **Presence is not authorization.** Neither `/afk` nor `/back` grants, removes, or expands permissions.
3. **Physical blockers are local blockers.** A step requiring physical human interaction waits; independent work continues.
4. **Context is opaque.** Optional context is carried as user-provided text. An adapter may recognize presets such as `sleep` or `work`, but other implementations must not depend on those presets.
5. **Idempotence.** Repeating `/afk` or `/back` is safe.
6. **Honest delivery.** An adapter must not claim another session knows the state unless notification was confirmed.
7. **Native first.** Adapters should reuse host-provided session discovery, messaging, lifecycle, and storage primitives before adding infrastructure.
8. **Model-independent.** The meaning of `/afk` and `/back` does not depend on which model a host runs. What varies between hosts is capability (state-only, notify, fan-in), which comes from the host's primitives, never from the model.
9. **No mandatory service.** The portable contract does not require a daemon, server, database, account, telemetry service, or network connection.

## AFK transition

`/afk [context]`:

1. persist `status = afk`;
2. record `since`;
3. preserve optional context;
4. notify reachable peers when the host provides a native mechanism;
5. communicate that work already authorized may continue and that physically-bound steps should be deferred.

AFK never means "unrestricted autonomy."

## Back transition

`/back`:

1. persist `status = available`;
2. record the new `since`;
3. clear AFK context;
4. notify reachable peers when supported;
5. optionally request and consolidate status, placing human-blocking work first.

Returning never means "approval granted."

## State file

The reference location is `~/.afkswitch/state.json`, validated by
[`state.schema.json`](state.schema.json). An adapter may use a host-managed data directory
instead, with the same meaning. Missing, empty, or malformed state is never an error:
`/afk` and `/back` replace it with a valid state, and `/back` then reports no duration.
The state belongs to the human, not to the session that wrote it.

## Delivery

"Notified" means the host confirmed delivery to that session. A message the host reports
as held for approval, refused, or failed is reported as not notified. A peer that has not
answered a status request is "no reply yet" — never failed, finished, or agreeing.

Peers that start after `/afk`, or were unreachable, are not notified. An adapter may close
that gap only with a native host mechanism; the reference adapter does not.

## Adapter capability levels

An adapter may implement:

- **State-only:** durable local state.
- **Notify:** state + peer notification.
- **Fan-in:** state + notification + status collection on return.

Documentation must state the level actually supported by each host. As of v0.4.0:

| Host | Level |
|---|---|
| Claude Code (reference) | Fan-in, via native `ListAgents` + `SendMessage` |
| OpenAI Codex | State-only |
