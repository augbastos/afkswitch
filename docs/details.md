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

While you are away, each session queues human decisions in its durable notes or ledger:
1-2 lines of context, options, recommendation and paused work per decision, grouping
dependencies. It records reversible defaults within existing authorization and continues
independent work. Authorized remote questions also enter the queue without stalling work.
At the next natural pause after `/back`, it presents all decisions together as
multiple-choice questions, recommended option first, using the host's structured question
tool when available. Then it returns to asking in real time. Status replies include
`decisions-queued` within the ~50-word budget; the full questions are presented separately.

Each session also records deferred steps as one line:

```text
BLOCKED FOR HUMAN (physical): restart local service — stopped at elevation prompt — needs UAC — resume with: restart, then smoke test
```

A session that has not answered `/back` is *no reply yet* — never "done", "failed", or
"agreed".

## Host capabilities

<!-- capabilities:details:start -->
| Host | State | Sync | Notify | Fan-in | Visual switch | Live-verified | Notes | Evidence |
|---|---|---|---|---|---|---|---|---|
| Claude Code (reference) | yes | yes | yes | yes | yes | yes | Read-only SessionStart, UserPromptSubmit and PostToolUse sync; native notification and return status collection; a read-only PermissionRequest hook declines approval prompts while away (AFKSWITCH_KEEP_PROMPTS=1 keeps them). Visual switch on the terminal and the desktop app, on builds with function hooks; terminal clicks live-tested on Windows with Claude Code 2.1.287. The desktop drawing, macOS and Linux are covered by the module tests, not by a live click. The Claude plugin directory copy currently omits the switch while mods are reviewed. | hooks/hooks.json; hooks/switch.tsx and switch.test.ts; scripts/presence_hook.py; bundled skills: ListAgents, SendMessage, notify_when_idle. |
| Codex | yes | no | no | no | no | no | Hooks for SessionStart, UserPromptSubmit and PostToolUse (transcript marker, like Claude Code); the installer writes them to ~/.codex/hooks.json and Codex asks you to trust them with /hooks. The default sandbox blocks $afk from writing ~/.afkswitch: use the afkswitch command or --codex-writable-state. Notify NOT SUPPORTED: codex queue --thread <id> --message may start a turn (wake/credits); codex agents has no machine-readable listing or delivery receipt. FanIn NOT SUPPORTED: no reply channel. | hooks/codex.json; scripts/presence_hook.py; scripts/install.py; synthetic conformance/hooks and conformance/install tests only. |
| Hermes Agent | yes | no | no | no | no | no | pre_llm_call shell hook in ~/.hermes/config.yaml, told on every call while away (short event only); Hermes asks once to approve it. Skills are not installed by default because Hermes has no manual-only flag and the model could change presence; --hermes-skills opts in. Notify and fanIn are not supported. | adapters/hermes/hooks.yaml; scripts/presence_hook.py; scripts/install.py; synthetic conformance/hooks and conformance/install tests only. |
| Cursor | yes | no | no | no | no | no | Skills from ~/.agents/skills; a sessionStart hook tells new sessions while away. Later events stay unwired until a live test shows Cursor keeps the marker in its transcript. Notify and fanIn are not supported. | adapters/cursor/hooks.json; scripts/presence_hook.py; scripts/install.py; synthetic conformance/hooks and conformance/install tests only. |
| GitHub Copilot CLI | yes | no | no | no | no | no | Skills from ~/.agents/skills; a sessionStart hook in ~/.copilot/hooks tells new sessions while away (userPromptSubmitted output is dropped by the host). Notify and fanIn are not supported. | adapters/copilot/afkswitch.json; scripts/presence_hook.py; scripts/install.py; synthetic conformance/hooks and conformance/install tests only. |
| Antigravity CLI | yes | no | no | no | no | no | PreInvocation hook, told on every call while away (short event only). The installer copies the plugin to ~/.gemini/config/plugins/afkswitch and the skills to ~/.gemini/config/skills. Skills may be auto-invoked: Antigravity documents no manual-only flag. Notify and fanIn are not supported. | adapters/agy/; scripts/install.py; synthetic conformance/hooks and conformance/install tests only. |
| Generic local agent | yes | yes | no | no | no | no | Sync via the reference helper when the host calls check before each turn. | adapters/generic/presence_sync.py; conformance/sync and conformance/cross-host. |
<!-- capabilities:details:end -->

The plugin-directory availability noted above is dated 2026-10-02: that channel's
`v0.6.3-directory` copy omitted the switch while mods were reviewed. See the
[installation-channel record](compatibility.md#marketplace-module-loading--2026-10-02)
for the tested version, platform, installation source and local-clone fallback.

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
both advertise sync=false. The root README summarizes these capabilities;
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

`python scripts/install.py --host claude` copies the two skills into `~/.claude/skills`
(see [Installer](#installer)). Personal-skill installation alone does not install the
visual switch, which comes with the plugin.

## Installer

`python scripts/install.py` (Python 3.9+, standard library only) wires every agent it
finds to the one presence file. Nothing is written until you have seen the change.

1. It finds the agents you have by their configuration folder (`~/.claude`, `~/.codex`,
   `~/.hermes`, `~/.cursor`, `~/.copilot`, `~/.gemini/config`) or, for Codex, its command.
   `--host claude,codex` limits the run.
2. It builds every change, prints a diff for each file and the folders it will copy, then
   asks `Apply? [y/N]`. `--dry-run` stops after the diff; `--yes` skips the question.
3. It copies AFKSwitch to a folder of its own, outside the state folder, so a sandboxed
   agent that may write presence can never rewrite the code its hooks run:
   `%LOCALAPPDATA%\AFKSwitch` on Windows, `~/Library/Application Support/AFKSwitch` on macOS,
   `$XDG_DATA_HOME/afkswitch` (or `~/.local/share/afkswitch`) on Linux.
4. Hook commands name the Python that ran the installer by its absolute path, so `python3`
   versus `python` never matters. Uninstalling that Python silently stops the hooks.

| Agent | Skills | Hook it adds | How the agent learns |
|---|---|---|---|
| Claude Code | `~/.claude/skills` | none when the plugin is enabled (it has its own); else `~/.claude/settings.json` | at once from the switch; at each prompt and tool call |
| Codex | `~/.agents/skills` | `~/.codex/hooks.json`: session start, each prompt, each tool call | next prompt or tool call; trust the hooks with `/hooks` first |
| Hermes Agent | none unless `--hermes-skills` | a managed block in `~/.hermes/config.yaml`: `pre_llm_call` | every model call while away; Hermes asks once to approve the hook |
| Cursor | `~/.agents/skills` | `~/.cursor/hooks.json`: `sessionStart` | new sessions while away |
| GitHub Copilot CLI | `~/.agents/skills` | `~/.copilot/hooks/afkswitch.json`: `sessionStart` | new sessions while away |
| Antigravity CLI | `~/.gemini/config/skills` | the plugin folder `~/.gemini/config/plugins/afkswitch`: `PreInvocation` | every model call while away |
| Local agent (Ollama and others) | none | none: it prints the `presence_sync.py check` call to make before each turn | when the agent calls the check |

Hermes gets no skills by default because it has no way to keep a skill manual-only: the
model could change your presence by itself. Use the `afkswitch` command there instead.

**How it edits.** JSON files are parsed and merged: other entries keep their order, its own
entries are replaced, and a second run writes the same bytes. A file it cannot parse (for
example one with comments) is left alone and the lines to paste are printed. YAML and TOML
get a block between `# >>> afkswitch (managed, do not edit) >>>` and `# <<< afkswitch <<<`;
if the same top-level key already exists outside that block, the file is left alone and
the lines are printed. Before its first write to an existing file it saves
`<file>.afkswitch-backup-<UTC time>`, and it records every edit in `install-manifest.json`
in its folder.

**The `afkswitch` command** lands in `~/.local/bin` (macOS, Linux) or in the installer's
`bin` folder on Windows; `--add-to-path` adds that folder to your user PATH. Bind
`afkswitch afk` to a keyboard shortcut to go away without opening an agent: a Windows
shortcut's "Shortcut key", a macOS Shortcuts "Run Shell Script" action, or a GNOME or KDE
custom shortcut.

**Removal.** `--uninstall` removes its hook entries and managed blocks, the skills it
installed (only folders whose `SKILL.md` names `~/.afkswitch/state.json`), the command and
its folder. It never restores a backup, because you may have edited the file since, and it
never touches your presence state.

## Claude Code visual switch

Requires Claude Code with function hooks; live-tested on 2.1.287 on Windows.
AFKSwitch is a Claude Code Mod. The
plugin ships [hooks/switch.tsx](../hooks/switch.tsx) under `modules` alongside the
existing command hooks in [hooks/hooks.json](../hooks/hooks.json). A build without
function hooks can still use the text skills. Strict plugin-manifest validation checks
this combined layout. Marketplace module loading was verified on 2.1.287 on
2026-10-02 in an isolated config with a local-directory marketplace, tested on Windows.
See the [dated installation-channel record](compatibility.md#marketplace-module-loading--2026-10-02)
for the separate Claude plugin directory limitation.
If your build does not load installed mods, use `claude --plugin-dir <clone>` or
`CLAUDE_CODE_PLUGIN_DIRS`. See [compatibility](compatibility.md) for the evidence.

The terminal's `AbovePrompt` band draws one compact bordered box, unchanged in size:
`AFK  □■` (available, dim grey label) or `AFK  ■□` (away, orange `#F28C28` border).
While it can be pressed, the whole inside of the border is one button.
Click it, or focus it with `ctrl+x tab` and press Enter.
The button label carries no context. `AFK  □□` is neutral unknown state.

While you are away, a dim label may follow the box, outside its border. It names
the kind of absence when your `/afk` text opens with a known word or phrase: only the first
four words before any comma or full stop count, and a hyphenated word never does. It is a
plain keyword hit, not understanding: it does not know "not", and when several kinds match,
the one that comes first wins. The lists are narrow on purpose, because a note is often about
the agent's work ("keep working", "finishing the sleep-tracker refactor"), not about you:

| Label | Words and phrases |
|---|---|
| `💼 at work` | `work` or `working` alone; at/to/from/for/after/before/off work; night shift, shift work, meeting, office; trabalho, trabalhando, turno, reunião, escritório, expediente, emprego |
| `💤 sleeping` | sleep, sleeping, sleepy, asleep, slept, nap, napping, bedtime, going to bed, in bed, good night; dormir, dormindo, sono, soneca, cochilo, cama, boa noite |
| `🛒 shopping` | shop, shopping, grocery, groceries, supermarket, mall; compras, comprar, comprando, mercado, supermercado |
| `🛫 traveling` | travel, traveling, trip to, business/road/weekend/day/work trip, flight, fly, flying, flew, airport, vacation, holiday; viagem, viajar, voo, aeroporto, férias, feriado, rodoviária |

A few look-alikes are left out: workout, post office, out of office, office hours, coffee
shop, sleep mode, flight sim, Mercado Livre. A note with no known word gets no label.

When you leave with no note at all (a click, or a bare `/afk`), an idle label appears on
every third prompt or finished turn and is gone 8 seconds later, always the same time. Its
emoji blinks for the first 3 seconds; kind labels never blink. The idle labels are
`🌳 at the park`, `💃 dancing`, `💬 chatting`, `☕ coffee break`, `🚶 out for a walk`,
`🎧 listening to music`, `🍜 grabbing a bite`, `📚 reading`, and sillier ones such as
`🦆 arguing with a duck` or `🧦 hunting the other sock`; about one in twenty is a rare one
such as `🛸 abducted, back soon`.
Your text itself is never drawn. Anyone who sees your screen sees the label.

One-time onboarding lines explain the switch; while an action is pending its cells
flash between the two states (same label, same width, nothing around it moves), and
a red `not switched` marks a failed or unconfirmed action (red, so a failed return never reads as the away orange).
Before first use, a definitely missing state file gives
the same neutral cells a button that starts AFK. Unreadable or invalid state is not
clickable and never implies available. The desktop app draws the same switch; other
surfaces continue the original render. Tests cover the drawing tree on terminal and
desktop and VS Code pass-through, not native pixel or glyph paint; nobody has yet
checked the desktop drawing by eye.
The cells distinguish presence without relying on color.

The module reads presence from `~/.afkswitch/state.json` using `$.fs.read`, with
`AFKSWITCH_STATE_DIR` taking priority over `HOME` or `USERPROFILE`. Only version 1/2 and
valid fields confirm a presence state. It never writes, creates or migrates state itself, and never runs
Python to draw. Onboarding uses the host's store separately. Its module-local cache
refreshes at `session.start`, first render after load, `prompt.submit`,
`turn.complete`, and before dispatch. A bad
read hides cached presence rather than implying available. No polling; the only timers are the two that blink and then hide an idle label, armed only while one shows.

Clicking a displayed available state runs the bundled state helper with `afk`; displayed
AFK runs it with `back`, without context, through `$.process.run` (`python3`, then
`python`, then `py -3`). Intent is captured when drawn; a fresh read that already has the
target means nothing runs. An unknown fresh read takes no action. Earlier versions ran
the slash command instead, which the host queues until the session is idle, so a click
during a long turn sat on `saving…` until that turn ended. The helper takes effect at once
and starts no model turn here. When the state changed, the switch lists sessions with
`ListAgents` and sends each live local interactive one the skill's own message (the core
event plus the guidance in `references/message.md`) through `$.session.send`. In this
session it writes a dim `/afkswitch:afk` or `/afkswitch:back` line in the transcript, as
the command's own row used to mark it, and appends the same message (without the `/back`
status request) as a row the model reads at its next step, without stopping the turn. Only a state read after the helper
exits confirms the displayed status; if it does not, the switch shows the failure message
until the next turn ends.

The API has no Button `disabled` prop. While pending, identical cells are drawn as
Text instead of a Button, with an immediate guard against old-drawing double presses.
On errors, the control refreshes disk truth and re-enables a button only for known
state or a definitely missing file. Registered hooks pass events through unchanged;
the engine skips a hook that throws. Tests intercept command dispatch. Live clicks
and peer notification were tested separately from marketplace module loading;
see [compatibility](compatibility.md).

## Lifecycle sync

Version 0.6 replaces the earlier "no hooks" constraint so sessions opened after `/afk`
and changes from another host reach the session. The two read-only `SessionStart` and
`UserPromptSubmit` command hooks run `scripts/presence_hook.py` once, read
`~/.afkswitch/state.json` through the existing helper and the end of the session
transcript (256 KiB, then 4 MiB, then 64 MiB while no marker is found) to find the last AFKSwitch marker, and return the universal core event in
`hookSpecificOutput.additionalContext` only when needed. Startup/clear injects only AFK;
resume/compact/fork and prompt submission inject newer generations or unseen resets.
They never write state or transcripts, poll, run in the background, change permissions
or use the network. Errors, missing/invalid state and future state versions exit 0
with no output. Transcript-only memory cannot detect same-generation recreation without
a changed marker, and markers older than the widest window can be replayed.

Claude Code discovers [hooks/hooks.json](../hooks/hooks.json). Codex's default manifests
have no `hooks` pointer; [hooks/codex.json](../hooks/codex.json) remains a documented
experimental file, using `--host codex` and `${PLUGIN_ROOT}`. It has only synthetic
tests and is not verified in a live host. Do not infer active sync from shipped files.

Both command manifests use `python3` and a 5-second timeout. On Windows, the Python
install manager provides `python3`; with the classic installer it may be absent or an
app execution alias: ensure it resolves to Python 3.9+, or adapt the
installed command to `python` or `py -3`. The explicit skills' interpreter discovery
does not change hook commands. No shell wrapper is bundled.

The experimental [Antigravity layout](../adapters/agy/README.md) describes `PreInvocation` and
returns `injectSteps[].ephemeralMessage` only for AFK; it reads no transcript and
available state emits nothing. Its peer messaging reach between independent CLI
sessions is unproven, so sync, notify and fanIn remain unsupported in the declared matrix.

## Approval prompts while away

While you are away, a third hook, `PermissionRequest`, answers "not now" to Claude Code's own
approval prompts: the call is declined with a note telling the session to defer that step and
keep working, instead of the session waiting all night for a click. It never approves anything,
reads only the state file, and does nothing when you are present or the state is unknown.
Set `AFKSWITCH_KEEP_PROMPTS` to `1`, `true` or `yes` to keep the prompts, for example if you
approve them remotely. The command that `/afk` and `/back` run is never declined, so you can
always come back. Only that exact run counts: a command that merely mentions the helper, or
chains another command onto it, is declined like any other.

The decline message asks the session not to retry and not to look for another way to do
the same thing. A session in a mode that never prompts is unaffected.

## Codex sandbox

Codex's default `workspace-write` sandbox refuses writes outside the current workspace, so
the first `$afkswitch:afk` either asks you to approve running the state helper with write
access to `~/.afkswitch` or reports `state transition failed: write refused` — it never
claims a state it could not save. The `afkswitch` command is not sandboxed and always
works. To let the skills write too, run the installer with `--codex-writable-state`, which
adds this block for you; any sandboxed Codex turn can then change your presence. Or add the
absolute path of that folder to `~/.codex/config.toml` yourself:

```toml
[sandbox_workspace_write]
writable_roots = ["<absolute path of your home directory>/.afkswitch"]
```

On Windows, Codex runs `workspace-write` only when its Windows sandbox is configured
(`[windows] sandbox = "unelevated"` or `"elevated"`); otherwise the session is read-only and
`$afkswitch:afk` reports that the state was not saved.

## Three rules

1. **One writer: the helper.** Only the bundled helper saves presence. The switch and
   sync hooks read it; peers are notified only after a successful save and read-back.
2. **Explicit actions only.** Only `/back` ends AFK, including through the switch.
   Time passing, a remote reply, or a session restart never means you returned.
3. **Presence is not permission.** Away never authorizes anything. In Claude Code, an
   approval prompt that opens while you are away is declined instead of left waiting
   (`AFKSWITCH_KEEP_PROMPTS=1` keeps the prompts; `/back` itself is never declined). Away does not mean unreachable. Only the step that needs you waits; independent authorized work continues.

## What AFKSwitch is not

Not an orchestration framework, fleet manager, scheduler, messaging server, permission
system, or autonomy framework. It is a two-command presence contract with host adapters.
