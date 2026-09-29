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
5. **Idempotence.** Repeating `/afk` with the same context, or `/back`, changes nothing: `since` and `generation` stay as they were.
6. **Honest delivery.** An adapter must not claim another session knows the state unless notification was confirmed.
7. **Native first.** Adapters should reuse host-provided session discovery, messaging, lifecycle, and storage primitives before adding infrastructure.
8. **Model-independent.** The meaning of `/afk` and `/back` does not depend on which model a host runs. What varies between hosts is capability (state-only, notify, fan-in), which comes from the host's primitives, never from the model.
9. **No mandatory service.** The portable contract does not require a daemon, server, database, account, telemetry service, or network connection.
10. **State before messages.** No peer is told anything until the new state is saved and read back.

## AFK transition

`/afk [context]`:

1. validate the context (see [Validation](#validation)); reject, never truncate;
2. persist `status = afk`, a new `since`, the context, and the next `generation`
   (or keep all of them when already `afk` with the same context);
3. re-read and validate the saved state;
4. only then notify reachable peers, when the host provides a native mechanism;
5. communicate that work already authorized may continue and that physically-bound steps should be deferred.

AFK never means "unrestricted autonomy."

## Back transition

`/back`:

1. persist `status = available`, a new `since`, no context, and the next `generation`
   (or keep them when already `available`);
2. re-read and validate the saved state;
3. only then notify reachable peers, when supported;
4. optionally request and consolidate status, placing human-blocking work first.

Returning never means "approval granted."

## State protocol v2

### File

The reference location is `~/.afkswitch/state.json`, validated by
[`state.schema.json`](state.schema.json). An adapter may use a host-managed data directory
instead, with the same meaning. The state belongs to the human, not to the session that
wrote it.

```json
{ "version": 2, "status": "afk", "since": "2026-09-27T01:53:00+01:00", "context": "sleep", "generation": 7 }
```

- `generation` is an integer that increases by exactly one on every durable transition.
  It is the only ordering signal. `since` is informative (it gives the duration shown by
  `/back`) and is never used to decide which state is newer, so a wrong or changed clock
  cannot reorder presence.
- An idempotent repeat keeps `since` and `generation`.
- An `available` state has `context: null`.

### Transaction order (hard invariant)

1. Validate input.
2. Take the lock (below).
3. Read the prior state (with migration rules below).
4. Write the new state atomically: a temp file in the same directory, flush, `fsync`,
   then an atomic rename over `state.json` (`os.replace`).
5. Re-read `state.json` and validate it; it must equal what was written.
6. Release the lock.
7. Only then notify peers.

If any step from 2 to 5 fails, the adapter reports `state transition failed` with the
reason and notifies nobody. A failed write leaves the previous file intact.

On Windows, `os.replace` is `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING`: on the same
NTFS volume the old or the new file is visible, never a mix. It fails with "access denied"
while another process holds the target open without delete sharing (a reader, an indexer,
antivirus); the reference helper retries for up to about one second, then reports
failure.

### Locking

Transitions are serialised with one lock file, `state.json.lock`, created with `O_EXCL`
(atomic create-if-absent on every supported OS and file system). The holder deletes it when
done. A lock older than 10 seconds is treated as left by a crashed process and broken;
a transition holds it for milliseconds, and a waiter gives up with `state transition
failed: state is busy` after 15 seconds. Reads do not take the lock: they see the old or
the new file, because writes are atomic renames.

Why this and nothing bigger: it is standard library everywhere, needs no process running
between invocations, and cannot leave the state file half-written. The known limit: if
two processes break the same stale lock at the same instant, one may delete the other's
fresh lock. That needs a crash followed by two simultaneous transitions ten seconds
later; the worst outcome is the same as having no lock for that moment (last writer
wins, both files valid).

### Concurrency: what the user sees

Transitions are serialised, so two commands at the same moment behave as if one ran just
before the other. Which one goes first is not defined; the higher generation is the
current state, and every report shows its generation.

| At the same moment | Result |
|---|---|
| `/afk` + `/afk` (same context) | One transition, generation G. The other command finds it already done and reports the same G and `since`. Peers may get two copies tagged G and treat the second as a repeat. |
| `/afk work` + `/afk sleep` | Two transitions, G and G+1. The final context is the one with G+1; both reports are true for their moment. Peers that see G+1 ignore G whenever it arrives. |
| `/afk` + `/back` | Two transitions, G and G+1. The final status is whichever got G+1. A `/back` that went first reports no duration if nothing was AFK yet. |
| `/back` + `/back` | One transition, G. The second finds `available` and reports G without a duration. Each sends its own status request; peers answer each asker. |

### Validation

- `status` is `available` or `afk`.
- `since` is ISO 8601 with seconds and an explicit offset (`Z` or `±hh:mm`).
- `context` is `null` or text of at most **2048 Unicode code points**. Longer context is
  rejected with a clear message and nothing is saved or sent; it is never truncated.
  Empty context is stored as `null`. Multi-line and non-ASCII text is kept verbatim.
- `generation` is an integer ≥ 1.

### Missing, malformed, old, and newer files

| On disk | Read as | On the next transition |
|---|---|---|
| no file (or no directory) | no prior state | directory and file created; `generation` 1 |
| empty file | no prior state | replaced; `generation` 1 |
| malformed (not JSON, wrong fields, invalid values) | no prior state | the old bytes are kept as `state.json.corrupt-<UTC timestamp>` first, then replaced; `generation` 1; the report says a backup was made |
| version 1 | migrated in memory: same `status`, `since`, `context`, `generation` 1 | written back as version 2 (an idempotent repeat still writes, keeping `since`) |
| version 2 | as is | as specified above |
| version newer than the reader knows | **error** `unsupported state version N` | nothing is written, nobody is told, success is never claimed |

When the prior file was missing, empty, malformed or version 1, the generation line
restarts; the result says `reset`. `/back` reports no duration when there was no valid
prior `afk` state.

### Privacy of the file

Best effort, never requiring elevation: on POSIX the directory is `0700` and the file
`0600`; on Windows both inherit the user profile's ACL and are never widened.

## Peer messages and generations

Every peer message carries the generation it announces, in its first line:

```text
[AFKSwitch g7] ...
[AFKSwitch g1 reset] ...
```

A receiving agent remembers the highest generation it has seen in its conversation and:

- **ignores** a message whose generation is lower than one it has already seen: it is
  stale, overtaken by a later `/afk` or `/back`;
- treats a message with the **same** generation as a repeat: nothing new to do;
- applies a higher generation, or any message marked `reset` (the state file was
  recreated or migrated, so its numbering restarted);
- when unsure which is newer, reads `~/.afkswitch/state.json`: its `generation` is the
  truth.

A status reply starts with `afkswitch-status g<G>`, naming the generation of the request
it answers, so the asker can tell a reply to this `/back` from a late reply to an earlier
one.

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

Documentation must state the level actually supported by each host. The canonical list is
[`adapters/capabilities.json`](../adapters/capabilities.json); how to write and test an
adapter is in [`adapters/README.md`](../adapters/README.md).

<!-- capabilities:spec:start -->
| Host | Level |
|---|---|
| Claude Code (reference) | Fan-in via native `ListAgents` + `SendMessage` + `notify_when_idle` |
| OpenAI Codex | State-only |
<!-- capabilities:spec:end -->
