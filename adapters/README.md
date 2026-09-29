# Writing an AFKSwitch adapter

An adapter makes `/afk` and `/back` work in one agent host. This page is everything you need;
the normative rules are in [`spec/presence.md`](../spec/presence.md).

## 1. The meaning (never changes between hosts)

- `/afk [context]`: the human is **physically away**. Not unreachable, and not permission.
  Agents keep doing already-authorized work; only a step that needs the human's body waits.
- `/back`: the human is present again. Returning is not approval either.
- Only these two commands. No extra commands, no richer states in the portable contract.
- Both are explicit only: never triggered because a conversation mentions leaving or sleeping.

## 2. Capability levels

Pick the highest level the host supports **natively**, and claim nothing more.

| Level | You must | Needs from the host |
|---|---|---|
| **State-only** | Save and read the state through the state protocol. | A way to run a local command or write a local file. |
| **Notify** | State-only, plus tell every live local peer session, and report delivery honestly. | Native session discovery and messaging the model can call. |
| **Fan-in** | Notify, plus request a status from each peer on `/back` and consolidate replies, human blockers first. | Messaging that can carry a reply back, ideally a native "tell me when idle" signal instead of polling. |

A host without native peer messaging is **state-only**. Do not emulate messaging with a
daemon, server, database, polling loop, file watcher, message broker, hook, or anything
that keeps running between commands. Say plainly that other sessions were not told.

## 3. The state contract

- File: `~/.afkswitch/state.json`, schema [`spec/state.schema.json`](../spec/state.schema.json)
  (version 2). All hosts on one machine share it: presence belongs to the human, not a host.
- Easiest path: **call the reference helper** (`skills/afk/scripts/afkswitch_state.py`,
  Python 3.9+ standard library) with `afk [--context TEXT]`, `back`, or `read`, and use its one
  JSON line. If you write your own, it must pass `conformance/state/` unchanged.
- Rules you must keep if you implement it yourself:
  - `generation` increases by exactly one per durable transition; an idempotent repeat keeps
    `since` and `generation`; clocks never decide order.
  - Order: validate → lock (`O_EXCL` lock file, stale after 10 s) → read → write temp file in
    the same directory, `fsync`, atomic rename → re-read and validate → unlock → only then
    notify.
  - Context: `null` or at most 2048 Unicode code points; reject longer, never truncate.
  - Version 1 files migrate (generation 1); a newer version is refused with
    `unsupported state version N` and never overwritten; a malformed file is backed up to
    `state.json.corrupt-<timestamp>` before it is replaced.
  - On any failure: report `state transition failed`, notify nobody, never claim success.

## 4. Messages and ordering (notify and fan-in)

- Targets: live, local, interactive peer sessions only. Never the sender, remote-control
  mirrors, cloud sessions, other machines, subagents, or anything offline.
- One message per target per invocation. Retry only a confirmed failure, once. One failure
  never stops the other sends.
- The first line carries the generation: `[AFKSwitch g<G>]`, or `[AFKSwitch g<G> reset]` when
  the helper reports `reset`. Receivers ignore a lower generation than one they have seen,
  treat the same one as a repeat, and apply a higher or `reset` one. The file is the truth.
- Status replies start with `afkswitch-status g<G>`. Count only replies to this `/back`, from
  sessions you asked, once each. A silent session is "no reply yet", nothing else.

## 5. Honest delivery

"Notified" means the host confirmed delivery. Held for approval, refused, failed, or
unknown are "not notified", and the report names those sessions. Sessions started after
`/afk` are not told unless the host has a native way to tell them.

## 6. Run the conformance suite

```text
python -m pip install pytest jsonschema
python -m pytest conformance
python conformance/checker.py your-notify-recording.json your-fan-in-recording.json
```

[`conformance/README.md`](../conformance/README.md) explains what PASS means for each level
and the transcript shape to record.

## 7. Declare support

1. Add the host to [`capabilities.json`](capabilities.json) with the level that passed, the
   commands users type, and the native primitives it relies on.
2. Run `python scripts/validate.py --write` to update the tables in the README, the details
   page and the spec; plain `python scripts/validate.py` fails if they drift.
3. Record only runs that really happened in [`docs/compatibility.md`](../docs/compatibility.md):
   host version, OS, what was run, and the result. Unrun is "pending", never PASS.

## 8. Native first, no fake parity

Reuse what the host already has (session list, messaging, idle notices, storage) before
writing anything. If a capability is missing, the adapter is a lower level, and the docs say
so. Presence never changes permissions, in any host.
