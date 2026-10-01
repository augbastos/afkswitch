# AFKSwitch — details

The README keeps it short. This page has the rest.

## Usage

```text
/afk                       # physically away, no return time
/afk sleep                 # ordinary context: sleep
/afk work                  # ordinary context: work
/afk "walking the dog"     # any other context, kept verbatim
/back                      # present again, from any session
/back ready to review      # opaque context for this return event only
```

If another skill already answers to `/afk` or `/back`, use `/afkswitch:afk` and
`/afkswitch:back`. In Codex, always use `$afkswitch:afk` and `$afkswitch:back`: a bare
`$afk` can resolve to a different skill with the same name.

While you are away, each session records anything that needs you as one line:

```text
BLOCKED FOR HUMAN (physical): restart local service — stopped at elevation prompt — needs UAC — resume with: restart, then smoke test
```

A session that has not answered `/back` is *no reply yet* — never "done", "failed", or
"agreed".

## Host capabilities

<!-- capabilities:details:start -->
| Host | State | Sync | Notify | Fan-in | Visual switch | Notes | Evidence |
|---|---|---|---|---|---|---|---|
| Claude Code (reference) | yes | yes | yes | yes | yes | Read-only SessionStart and UserPromptSubmit sync; native notification and return status collection. Visual switch on terminal builds with function hooks; installed-marketplace module loading remains unverified. | hooks/hooks.json; hooks/switch.tsx and switch.test.ts; scripts/presence_hook.py; bundled skills: ListAgents, SendMessage, notify_when_idle. |
| Codex | yes | no | no | no | no | Experimental hook files shipped, not verified in a live host; no hooks pointer in default manifests. Notify NOT SUPPORTED: codex queue --thread <id> --message may start a turn (wake/credits); codex agents has no machine-readable listing or delivery receipt. FanIn NOT SUPPORTED: no reply channel. | hooks/codex.json; scripts/presence_hook.py; synthetic conformance/hooks tests only. |
| Antigravity CLI | yes | no | no | no | no | Experimental hook files shipped, not verified in a live host; no default hook wiring. Peer messaging reach between independent CLI sessions is unproven; notify and fanIn are not supported. | adapters/agy/ static plugin layout; synthetic conformance/hooks tests only. |
| Generic local agent | yes | yes | no | no | no | Sync via the reference helper when the host calls check before each turn. | adapters/generic/presence_sync.py; conformance/sync and conformance/cross-host. |
<!-- capabilities:details:end -->

Other hosts: contract only ([`spec/presence.md`](../spec/presence.md) +
[`spec/state.schema.json`](../spec/state.schema.json)); see
[writing an adapter](../adapters/README.md). The canonical matrix is
[`adapters/capabilities.json`](../adapters/capabilities.json). Versions actually tested are
in [compatibility](compatibility.md).

Capabilities: **state** reads/writes durable state; **sync** reconciles generations at a
lifecycle boundary before meaningful work; **notify** proactively delivers to running peers;
**fanIn** collects peer status on return; **visualSwitch** exposes explicit visual input
on the declared surfaces. Claude Code syncs at session start and prompt submission.
Codex and Antigravity hook files are experimental, not verified in a live host, and
both advertise sync=false. The root README table is retained unchanged for this change;
use the canonical matrix above for current support. Codex notify is
NOT SUPPORTED: `codex queue --thread <id> --message` may start a new turn in the target
session (wake/credits), and `codex agents` is an interactive browser with no
machine-readable listing, delivery receipt or reply channel. FanIn is NOT SUPPORTED
without a reply channel. [Generic local agents](../adapters/generic/README.md)
can call the reference sync helper before each turn, including with Ollama, llama.cpp,
vLLM or MLX. The helper runs once and exits; no background process is required.

## State

```text
~/.afkswitch/state.json
```

```json
{ "version": 2, "status": "afk", "since": "2026-09-27T01:53:00+01:00", "context": "sleep", "generation": 7 }
```

`generation` goes up by one on every real change and orders changes without trusting
clocks; peer messages carry it as `[AFKSwitch g7]`, so a session that already heard about a
newer change ignores an older message. Repeating a command changes nothing. The full rules
(transaction order, locking, concurrency, migration) are in the
[spec](../spec/presence.md#state-protocol-v2).

### The state helper

Each skill ships its own byte-identical `scripts/afkswitch_state.py`, so it works by itself.
Validation rejects drift between these copies. It needs **Python 3.9 or newer**: standard library
only, no network, no background process.

```text
python3 skills/afk/scripts/afkswitch_state.py afk [--context TEXT | --context-stdin]
python3 skills/back/scripts/afkswitch_state.py back [--context TEXT | --context-stdin]
python3 skills/afk/scripts/afkswitch_state.py read
```

It prints one JSON line: the new status, generation, since, context, the previous state,
and whether it migrated a version 1 file, restarted the generation (`reset`) or kept a
`backup` of a malformed file; or `"ok": false` with an `error` and a readable `message`.
The skills notify peers only after `"ok": true`.

- Context longer than 2048 characters is refused with a clear message; nothing is saved.
- Other than LF/tab, C0 controls, DEL, C1, ESC sequences and lone surrogates are refused.
  CRLF is rejected, never rewritten; stdin preserves trailing LF. Both commands validate
  before any write. `/back` context appears only in `event_context`, never durable state.
- `sleep` and `work` are ordinary opaque AFK context. Only `/back` ends AFK: no timeout,
  remote reply or session restart can end it. Presence changes no permissions.
- A file from AFKSwitch 0.4.x (version 1) is migrated automatically. Nothing to delete.
- A file written by a newer AFKSwitch is left alone: `unsupported state version N`.
- Without Python, the skills say `state helper unavailable (python not found)` and change
  nothing. They never write the file by hand.
- Writes go to a temp file in the same folder, then `fsync`, then an atomic rename. On
  Windows the rename replaces the old file in one step on the same volume; if another
  program holds the file open at that instant, the helper retries for about a second and
  then reports `state transition failed`.
- Privacy, best effort: on macOS and Linux the folder is `0700` and the file `0600`; on
  Windows they inherit your profile's permissions and are never widened.

## Claude Code behavior

- **Targets** are live local `interactive` sessions only. Remote Control rows, cloud
  sessions, other machines, subagents, and anything `offline` are never messaged.
- **State first.** Nobody is messaged unless the helper saved the state and read it back.
  Each message carries the generation; the `/afk` and `/back` reports show it as `g<G>`.
- **One message per session per invocation.** A confirmed failure is retried at most once;
  one failed session never stops the others.
- **Delivery is reported honestly.** A session in a different permission mode may hold a
  message for your approval; held or refused messages are reported as *not notified*.
- **`/back` never polls.** It uses the native one-shot `notify_when_idle` notice and folds
  replies in as they arrive.

### Known limitations

- A session started **after** `/afk`, or one that was unreachable, receives state at its
  next lifecycle sync boundary. This is reconciliation, not confirmed peer delivery.
- `ListAgents` does not expose working directories, so `/back` asks each session for its
  own `dir:` line.
- Two sessions with the same name need the ` [ref]` suffix; the skills handle it.

### Manual install (bare `/afk` and `/back` as personal skills)

```powershell
pwsh -File install.ps1              # install or update into ~/.claude/skills
pwsh -File install.ps1 -Uninstall   # remove
```

Personal-skill installation alone does not install plugin hooks or the visual switch.

## Claude Code visual switch

Requires a Claude Code build with the early-access function-hooks API enabled. The
plugin ships [hooks/switch.tsx](../hooks/switch.tsx) under `modules` alongside the
existing command hooks in [hooks/hooks.json](../hooks/hooks.json). A build without
function hooks can still use the text skills. Strict plugin-manifest validation checks
this combined layout; testing installed-marketplace module loading remains pending.

The terminal's `AbovePrompt` band draws one compact bordered row, unchanged in size:
`AFK  □■` (available, dim grey label) or `AFK  ■□` (away, orange `#F28C28` label).
No context or other words appear. `AFK  □□` is neutral unknown state; `!` marks a
failed or unconfirmed action. Unknown state is not clickable. Desktop and other
surfaces continue the original render without drawing the switch in this release;
tests cover terminal drawing and desktop pass-through, not native pixel or glyph paint.

The module reads only `~/.afkswitch/state.json` using `$.fs.read`, with
`AFKSWITCH_STATE_DIR` taking priority over `HOME` or `USERPROFILE`. Only version 1/2 and
status are needed to draw. It never writes, creates or migrates state, and never runs
Python to draw. Its module-local cache refreshes at `session.start`, first render after
load, `prompt.submit`, `turn.complete`, before dispatch and after completion. A bad
read hides cached presence rather than implying available. No timers or polling.

Clicking a displayed available state requests `$.command.run({ command:
'afkswitch:afk' })`; displayed AFK requests `afkswitch:back`, without context or slash.
Intent is captured when drawn; a fresh read that already has the target means no
command is needed. An unknown fresh read takes no action. The host queues commands
while busy without touching the typed draft. Each skill invokes a model turn and
uses its normal helper, notification and return-status flow; host permissions, costs
and data handling apply. Dispatch settling is not proof of a saved transition: only
another state read confirms the displayed status, and turn completion refreshes again.

The API has no Button `disabled` prop. While pending, identical cells are drawn as
Text instead of a Button, with an immediate guard against old-drawing double presses.
On errors, the control refreshes disk truth and re-enables only a known-state button.
Every registered hook has a `next(e)` fallback, including a replay-safe `.catch`.
Tests intercept command dispatch: actual skill resolution from a module in an
installed model session still needs verification.

## Lifecycle sync

Version 0.6 replaces the earlier "no hooks" constraint so sessions opened after `/afk`
and changes from another host reach the session. The two read-only `SessionStart` and
`UserPromptSubmit` command hooks run `scripts/presence_hook.py` once, read
`~/.afkswitch/state.json` through the existing helper and the last 256 KiB of the session
transcript to find the last AFKSwitch marker, and return the universal core event in
`hookSpecificOutput.additionalContext` only when needed. Startup/clear injects only AFK;
resume/compact/fork and prompt submission inject newer generations or unseen resets.
They never write state or transcripts, poll, run in the background, change permissions
or use the network. Errors, missing/invalid state and future state versions exit 0
with no output. Transcript-only memory cannot detect same-generation recreation without
a changed marker, and old markers outside the tail can be replayed.

Claude Code discovers [hooks/hooks.json](../hooks/hooks.json). Codex's default manifests
have no `hooks` pointer; [hooks/codex.json](../hooks/codex.json) remains a documented
experimental file, using `--host codex` and `${PLUGIN_ROOT}`. It has only synthetic
tests and is not verified in a live host. Do not infer active sync from shipped files.

Both command manifests use `python3` and a 5-second timeout. On Windows, `python3` may
be absent or an app execution alias: ensure it resolves to Python 3.9+, or adapt the
installed command to `python` or `py -3`. The explicit skills' interpreter discovery
does not change hook commands. No shell wrapper is bundled.

The experimental [Antigravity layout](../adapters/agy/README.md) describes `PreInvocation` and
returns `injectSteps[].ephemeralMessage` only for AFK; it reads no transcript and
available state emits nothing. Its peer messaging reach between independent CLI
sessions is unproven, so sync, notify and fanIn remain unsupported in the declared matrix.

## Codex sandbox

Codex's default `workspace-write` sandbox refuses writes outside the current workspace, so
the first `$afkswitch:afk` either asks you to approve running the state helper with write
access to `~/.afkswitch` or reports `state transition failed: write refused` — it never
claims a state it could not save. To allow it for good,
add the absolute path of that folder to `~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
writable_roots = ["<absolute path of your home directory>/.afkswitch"]
```

On Windows, Codex runs `workspace-write` only when its Windows sandbox is configured
(`[windows] sandbox = "unelevated"` or `"elevated"`); otherwise the session is read-only and
`$afkswitch:afk` reports that the state was not saved.

## What AFKSwitch is not

Not an orchestration framework, fleet manager, scheduler, messaging server, permission
system, or autonomy framework. It is a two-command presence contract with host adapters.
