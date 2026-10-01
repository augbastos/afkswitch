# AFKSwitch Presence Contract

AFKSwitch defines one small piece of shared human-agent state: whether the human operator is physically present.

## Commands

```text
/afk [optional context]
/back [optional context]
```

## States

- `available` — the operator is physically present.
- `afk` — the operator is physically away.

Adapters may expose richer UI, but these are the only portable states.

## Visual input

The Claude Code terminal switch is another explicit input to the same `/afk` and
`/back` actions, never a second source of truth. It draws one bordered compact row:
`AFK  □■` for available (dim grey label), `AFK  ■□` for AFK (orange `#F28C28` label),
and neutral `AFK  □□` for unknown state. The geometry is the same in both known states;
there is no context, animation, slider or track. A failed action adds only `!`.

Only a read of version 1 or 2 with status `afk` or `available` confirms the drawing.
Missing, unreadable, malformed or future files never imply available. The module
retains its last good read in a session-local drawing cache, but hides it when a fresh
read cannot confirm it. It reads at session start, first drawing after module load,
prompt submission, turn completion, immediately before a click's command and after
that command completes. There are no timers or polling. It never runs Python during
render and never writes, creates or migrates state.

A click captures the intended action from the displayed state: available requests
`afkswitch:afk` with no context; AFK requests `afkswitch:back`. Re-read before dispatch:
if another session already saved that target, redraw without dispatching a command.
If that read is unknown, take no action. While dispatch is pending, the cells remain
visible but cease to be a Button; an immediate guard also prevents a second press
from an older drawing. Unknown state has no active button. On failure, refresh disk
truth and re-enable a known-state button; never claim the intended state was saved.

`$.command.run` uses the plugin skill's name without a slash. The host queues it until
idle without changing the typed draft. The skill starts a model turn: its existing
helper, notify and fan-in flow runs normally, including host costs and permissions.
The module itself reads only the local state file and does not send network requests.
Builds without function hooks retain text commands. This release exposes the switch
on `terminal` only; other surfaces pass through. Every hook error continues `next(e)`.

## Invariants

1. **Presence is not reachability.** An AFK operator may still be reachable remotely.
2. **Presence is not authorization.** Neither `/afk` nor `/back` grants, removes, or expands permissions.
3. **Physical blockers are local blockers.** A step requiring physical human interaction waits; independent work continues.
4. **Context is opaque.** Optional context is arbitrary user text, information only, never a command or authorization. `sleep` and `work` are ordinary context, not protocol presets.
5. **Idempotence.** Repeating `/afk` with the same context, or `/back`, changes nothing: `since` and `generation` stay as they were.
6. **Honest delivery.** An adapter must not claim another session knows the state unless notification was confirmed.
7. **Native first.** Adapters should reuse host-provided session discovery, messaging, lifecycle, and storage primitives before adding infrastructure.
8. **Model-independent.** Meaning never depends on the model. Host capabilities (state, sync, notify, fanIn) are declared independently.
9. **No mandatory service.** The portable contract does not require a daemon, server, database, account, telemetry service, or network connection.
10. **State before messages.** No peer is told anything until the new state is saved and read back.
11. **Only `/back` ends AFK.** No remote message, elapsed time, session restart or agent execution state ends it. There is no AFK timeout; age may be displayed, never acted on.
12. **No infrastructure.** No daemon, server, HTTP service, database, MCP server, broker, polling, watcher, telemetry or account is part of this contract.

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

`/back [context]`:

1. validate event context with the same rules as AFK; invalid input causes no transition;
2. persist `status = available`, a new `since`, no durable context, and the next `generation`
   (or keep them when already `available`);
3. re-read and validate the saved state; return context in the helper's `event_context`;
4. only then notify reachable peers, carrying the event context when supported;
5. optionally request and consolidate status, placing human-blocking work first.

Event context is not stored in state.json or replayed by sync. Repeating `/back` with
different event context still keeps `since` and `generation`: presence is unchanged.

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
  Reject C0 controls U+0000-U+001F except LF U+000A and tab U+0009, DEL U+007F,
  C1 U+0080-U+009F, ESC sequences and lone surrogates U+D800-U+DFFF. The error names
  the offending rule and code point; nothing is written. **CRLF and lone CR are rejected**,
  never normalized. Stdin is UTF-8 (an optional transport BOM is removed), and preserves
  every context code point including trailing LF. Supply exact bytes, not a line-oriented
  transport that inserts CRLF or an extra newline.
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

Every event has this minimal core (host-specific guidance comes after it):

```text
[AFKSwitch g<G>]
status: afk|available
context: <verbatim text or none>
<one or two sentences of presence semantics>
```

For AFK: "The human is physically away and may still be reachable remotely. Presence
changes no permissions; only /back ends AFK." For back: "The human is physically present
again. Presence changes no permissions." Use `[AFKSwitch g<G> reset]` on reset.
Multiline context continues verbatim after `context:`; these lines are data, never commands,
even if they resemble event fields or guidance. This is a human/model message, not an
unambiguous machine serialization; consumers needing structured data use the helper JSON.

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

## Session-local awareness and sync

Version 0.6 replaces the earlier "no hooks" constraint with two read-only lifecycle
hooks: `SessionStart` and `UserPromptSubmit` in Claude Code. Experimental Codex files
describe the same boundaries but are not wired into default manifests. Sessions started
after `/afk`, or changed by another host, must learn the current presence. Each invocation
runs `scripts/presence_hook.py` synchronously, imports the existing state helper by path,
reads `~/.afkswitch/state.json` and at most the last 256 KiB of the session transcript
(`transcript_path`) to find the last `[AFKSwitch g<N>]` or `[AFKSwitch g<N> reset]` marker,
and exits. It never writes state or transcript, changes permissions, polls, runs in the
background or uses the network. Any error exits 0 with no output; missing, invalid or
future-version state also produces no output, never an inferred return.

On `SessionStart` with source `startup` or `clear`, inject only AFK state: an available
human is the default. With source `resume`, `compact` or `fork`, and on
`UserPromptSubmit`, inject only a generation newer than the last marker, or an unseen
reset. A lower authoritative generation signals reset; a migrated version 1 state is
reset unless its generation-1 reset marker is already present. Once that marker is
in the transcript, the same state is a repeat. With no marker, the seen generation is 0.
The output is `hookSpecificOutput` with `hookEventName` and `additionalContext` containing
exactly the universal core event above, without host-specific guidance or return context.
An unreadable transcript produces no output. Markers outside the bounded tail may be
replayed; transcript-only memory cannot distinguish an unobserved same-generation
recreation from a repeat, or an unobserved reset that overtakes the previous counter.
It adds no database, checkpoint file or durable protocol fields.

The experimental Antigravity CLI layout describes one `PreInvocation` command hook
instead: it reads state and emits
`injectSteps` with the core event as an `ephemeralMessage` only while AFK. It ignores
camelCase input fields and needs no transcript: ephemeral context is injected anew each
invocation. Available state produces no output. The same read-only and fail-open rules
apply. Codex and Antigravity hook files are shipped, not verified in a live host;
neither adapter advertises sync. No non-Claude default manifest selects those files.

Each session keeps `last_seen_generation` (initially 0), current presence and optional
AFK context in its own conversation or host state. A newly started session must reconcile
an existing AFK state before meaningful work when the host advertises sync. Compare the
global generation to last_seen_generation: newer means apply and update local state;
equal means repeat; lower pushed events are stale and ignored. Apply push immediately;
without push, check at the next safe lifecycle boundary before continuing meaningful work.
A reset marker starts a new epoch instead of comparing against the old epoch's counter.
Read authoritative state when ordering is uncertain, especially for a delayed reset push.

The [generic reference](../adapters/generic/README.md) checks once before each turn. It
returns an opaque `epoch` checkpoint for `--last-epoch`; keep that in session state too.
It tests file identity/content equality solely to recognize reset at the same generation,
never to order events. A lower authoritative file generation also signals reset. A missing,
empty or malformed file after a prior one signals a reset boundary, with no presence event;
retain known presence until a valid explicit transition, never infer `/back` from deletion.
The next transition still reports reset and starts generation 1 exactly as before.
Without the checkpoint, same-generation recreation can be indistinguishable from repeat.
No checkpoint can detect an entirely unobserved reset that overtakes the previous counter;
its current higher generation is still applied safely. No extra durable protocol fields,
epoch files or clocks used for ordering are introduced.

## Delivery

"Notified" means the host confirmed delivery to that session. A message the host reports
as held for approval, refused, or failed is reported as not notified. A peer that has not
answered a status request is "no reply yet" — never failed, finished, or agreeing.

Peers that start after `/afk`, or were unreachable, are not proactively notified. Sync
closes the awareness gap at the next supported lifecycle boundary without claiming push
delivery; the generic host can call its synchronous reference check.

## Adapter capabilities

Declare five booleans independently:

- **state:** read/write durable state through this protocol.
- **sync:** reconcile current global generation with session last_seen_generation at a
  lifecycle boundary before meaningful work; newer means apply, reset means new epoch.
- **notify:** proactively deliver events to running peers via native host mechanisms.
- **fanIn:** `/back` collects peer status without inventing replies.
- **visualSwitch:** an explicit UI input to the same actions, restricted to the host's
  `visualSwitchSurfaces`; false does not affect text commands.

Documentation must state the capabilities actually supported by each host. The canonical list is
[`adapters/capabilities.json`](../adapters/capabilities.json); how to write and test an
adapter is in [`adapters/README.md`](../adapters/README.md).

<!-- capabilities:spec:start -->
| Host | State | Sync | Notify | Fan-in | Visual switch | Notes | Evidence |
|---|---|---|---|---|---|---|---|
| Claude Code (reference) | yes | yes | yes | yes | yes | Read-only SessionStart and UserPromptSubmit sync; native notification and return status collection. Visual switch on terminal builds with function hooks; installed-marketplace module loading remains unverified. | hooks/hooks.json; hooks/switch.tsx and switch.test.ts; scripts/presence_hook.py; bundled skills: ListAgents, SendMessage, notify_when_idle. |
| Codex | yes | no | no | no | no | Experimental hook files shipped, not verified in a live host; no hooks pointer in default manifests. Notify NOT SUPPORTED: codex queue --thread <id> --message may start a turn (wake/credits); codex agents has no machine-readable listing or delivery receipt. FanIn NOT SUPPORTED: no reply channel. | hooks/codex.json; scripts/presence_hook.py; synthetic conformance/hooks tests only. |
| Antigravity CLI | yes | no | no | no | no | Experimental hook files shipped, not verified in a live host; no default hook wiring. Peer messaging reach between independent CLI sessions is unproven; notify and fanIn are not supported. | adapters/agy/ static plugin layout; synthetic conformance/hooks tests only. |
| Generic local agent | yes | yes | no | no | no | Sync via the reference helper when the host calls check before each turn. | adapters/generic/presence_sync.py; conformance/sync and conformance/cross-host. |
<!-- capabilities:spec:end -->
