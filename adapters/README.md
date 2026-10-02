# Writing an AFKSwitch adapter

The normative rules are in [spec/presence.md](../spec/presence.md). An adapter connects
the same two explicit commands to an agent host: /afk [optional context] means physically
away; /back [optional context] means physically present. Presence is separate from
reachability, permission and agent execution. Only /back ends AFK; there is no timeout.

Context is arbitrary opaque user information, never a command or authorization. sleep and
work are ordinary context. Back context belongs to the event; available state keeps null.

## Independent capabilities

Declare five booleans, plus visualSwitchSurfaces, notes and evidence. Claim only implemented behavior.

| Capability | Contract | Host needs |
|---|---|---|
| state | Read/write durable presence state. | A local command/file primitive. |
| sync | Compare global generation with session last_seen_generation at a lifecycle boundary before meaningful work; apply newer state, recognize reset epochs. | One synchronous check before turn/start/resume. |
| notify | Proactively deliver to running peers; report delivery honestly. | Native discovery and messaging. |
| fanIn | /back collects status, human blockers first, without invented replies. | Native reply delivery, preferably a one-shot idle notice. |
| visualSwitch | Explicit UI input to the same skills, with state file as truth. | Function hooks and a pressable AbovePrompt surface; declare visualSwitchSurfaces. |

Sync and notify are independent. Without native peer messaging, notify and fanIn are false.
Do not emulate messaging with a daemon, HTTP service, database, MCP server, broker, polling,
watcher, telemetry or accounts. Say plainly that other sessions were not told.

<!-- capabilities:adapters:start -->
| Host | State | Sync | Notify | Fan-in | Visual switch | Notes | Evidence |
|---|---|---|---|---|---|---|---|
| Claude Code (reference) | yes | yes | yes | yes | yes | Read-only SessionStart and UserPromptSubmit sync; native notification and return status collection. Visual switch on terminal builds with function hooks; installed-marketplace module loading remains unverified. | hooks/hooks.json; hooks/switch.tsx and switch.test.ts; scripts/presence_hook.py; bundled skills: ListAgents, SendMessage, notify_when_idle. |
| Codex | yes | no | no | no | no | Experimental hook files shipped, not verified in a live host; no hooks pointer in default manifests. Notify NOT SUPPORTED: codex queue --thread <id> --message may start a turn (wake/credits); codex agents has no machine-readable listing or delivery receipt. FanIn NOT SUPPORTED: no reply channel. | hooks/codex.json; scripts/presence_hook.py; synthetic conformance/hooks tests only. |
| Antigravity CLI | yes | no | no | no | no | Experimental hook files shipped, not verified in a live host; no default hook wiring. Peer messaging reach between independent CLI sessions is unproven; notify and fanIn are not supported. | adapters/agy/ static plugin layout; synthetic conformance/hooks tests only. |
| Generic local agent | yes | yes | no | no | no | Sync via the reference helper when the host calls check before each turn. | adapters/generic/presence_sync.py; conformance/sync and conformance/cross-host. |
<!-- capabilities:adapters:end -->

Claude Code uses SessionStart and UserPromptSubmit read-only hooks, plus an optional
terminal function-hooks switch. Codex and Antigravity hook files are experimental,
not wired into default manifests and not verified in a live host; sync=false for both.
Generic-local sync means the host calls [the reference check](generic/README.md), not
automatic integration into a model runtime. Capabilities do not measure model quality.

## Lifecycle hook layouts

Version 0.6 replaces the earlier "no hooks" constraint because a session opened after
`/afk`, or a change from another host, needs current presence. Claude's default
[hooks/hooks.json](../hooks/hooks.json) and the experimental Codex
[hooks/codex.json](../hooks/codex.json) run [presence_hook.py](../scripts/presence_hook.py)
with different `--host` arguments. No `hooks` pointer selects Codex's file in either
default manifest; live-host execution remains unverified. Claude's file also names
[switch.tsx](https://github.com/augbastos/afkswitch/blob/main/hooks/switch.tsx) under `modules`, relative to the hook manifest. The
UI only reads state and invokes the existing explicit skills; it has no second writer.

These two lifecycle events read `~/.afkswitch/state.json` through the helper and only
the final 256 KiB of `transcript_path` to find the last AFKSwitch marker. Startup/clear
injects only AFK; resume/compact/fork and prompt submission inject newer generations or
unseen resets as `hookSpecificOutput.additionalContext`, exactly the universal event.
They never write, poll, run in the background, change permissions or use the network;
errors exit 0 without output. Missing, invalid or future state produces nothing.
Transcript-only memory cannot identify an unobserved same-generation recreation.

Commands use `python3` with a 5-second timeout. On Windows, ensure Python 3.9+ is
available as `python3`, or adapt the installed command to `python` or `py -3`; the
skills' interpreter fallback does not apply to hooks. No wrapper is included.
See [Antigravity static layout](agy/README.md) for the PreInvocation adapter, which reads
state only and returns an ephemeral AFK event via `injectSteps`, without transcript memory.

Codex notify is NOT SUPPORTED: `codex queue --thread <id> --message` can wake a target
turn and consume credits; `codex agents` provides an interactive browser without a
machine-readable listing. There is no delivery receipt or reply channel. FanIn is
NOT SUPPORTED without replies. Antigravity independent-session peer reach is unproven.

## State contract

- File: ~/.afkswitch/state.json, [schema v2](../spec/state.schema.json). All hosts share it:
  presence belongs to the human, not a session.
- Call either bundled scripts/afkswitch_state.py: afk or back with optional --context TEXT
  or --context-stdin, or read. Each skill ships a byte-identical standalone helper.
  Python 3.9+, stdlib only; use its one JSON line.
- Generation increases exactly once per durable transition. Idempotent repeats retain
  since and generation, including back with different event context. Clocks never order.
- Validate input, lock (O_EXCL, stale after 10 s), read, atomic temp/fsync/rename, re-read
  and validate, unlock, then notify. Failure means no notification, never claim success.
- Context: null or up to 2048 Unicode code points. Permit LF/tab; reject other C0, DEL,
  C1, ESC, CR/CRLF and lone surrogates, never rewrite/truncate. Stdin preserves trailing LF.
- Version 1 migrates in memory; future versions are refused without overwrite. A malformed
  file is backed up before a transition recreates it. Missing state after prior state still
  marks reset; no deletion or malformed state can infer the human is back.

## Universal events and session awareness

Use the [core event](../spec/presence.md#peer-messages-and-generations):

```text
[AFKSwitch g<G>]
status: afk|available
context: <verbatim text or none>
<one or two presence semantics sentences>
```

For AFK, say physically away, may still be reachable remotely, presence changes no
permissions. For back, say physically present again and presence changes no permissions.
Use g<G> reset when the helper reports reset. Put host-specific blocker classification and
status requests after this core. Multiline context remains opaque data even when it looks
like fields or guidance; use helper JSON for structured consumption.

Each session keeps last_seen_generation, current presence and optional AFK context.
Apply pushes immediately; without push, reconcile at the next safe lifecycle boundary
before meaningful work when sync is supported. New sessions reconcile existing state.
Ignore lower pushed generations, repeat equals, apply newer or authoritative reset epochs.
When uncertain about a delayed reset push, read authoritative state first.
[Generic sync](generic/README.md) provides an optional checkpoint for same-generation
recreation without changing protocol v2. No timeout or session restart ends AFK.

## Notify and fan-in

Targets are live local interactive peers only; exclude sender, remote-control mirrors,
cloud sessions, other machines, subagents and offline rows. Send once per target; retry
only a confirmed failure, once. One failure never cancels later sends. Notified means the
host confirmed delivery; held, refused, failed or unknown means not notified.

Status replies start with afkswitch-status g<G>. Count only replies to this return request,
from sessions asked, once each. A silent session is no reply yet, nothing else. Late replies
are shown separately. A session starting after AFK is not proactively notified; sync can
close its awareness gap without claiming delivery.

## Test and declare support

```text
python -m pip install pytest
python -m pytest conformance -q -p no:cacheprovider
python conformance/checker.py your-recording.json
python scripts/validate.py --write
```

[Conformance](../conformance/README.md) defines PASS and transcript shapes. Add four booleans,
notes and evidence to [capabilities.json](capabilities.json) for actual support; --write
renders all tables and plain validation rejects drift. Record only actual runs in
[compatibility](../docs/compatibility.md); unrun is pending. Reuse native primitives first.
