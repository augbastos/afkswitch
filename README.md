# claude-session-presence

Four tiny Claude Code skills that provide broadcast and human presence semantics on
top of native cross-session messaging.

`/broadcast` · `/afk` · `/back` · `/live`

## Why this exists

**Claude Code already supports cross-session communication. This plugin does not
replace it.**

The hard part — session discovery, addressing, delivery, inbox handling — is already
solved natively by the `ListAgents` and `SendMessage` tools. Re-implementing that would
mean a daemon, a database, a custom protocol and a polling loop, all to reach a place
the editor already reaches.

What is missing is not transport. It is the human layer on top: a consistent way to say
one thing to every terminal at once, to tell them you have walked away, and to find out
what happened while you were gone. That is all this is.

- `/broadcast` — tell every session something
- `/afk` — user is away
- `/afk sleep` — user is sleeping
- `/afk work` — user is away at work
- `/back` — user returned; collect what happened and what's waiting on them
- `/live` — list only the live local sessions (`name — status`). Its rule is the one
  definition of a live session that the other three apply before messaging anyone:
  offline, Remote Control, cloud and other-machine rows are never messaged.

> **AFK means you are physically away, not unreachable.** Sessions keep full progress,
> ask you through Remote Control only for decisions that truly block, group the rest,
> and defer only steps that need your body at the machine (authentication, elevation,
> credentials, local QA). A physical blocker is never a mission blocker.

```
Claude Code native session discovery + messaging
                      ↑
        /broadcast  /afk  /back
```

Not: our daemon → database → polling → hooks → custom protocol → messaging server.

## Global presence

**Presence belongs to the user, not to a repository or terminal.**

Run `/afk` from any Claude Code session and all reachable sessions are notified. Later
run `/back` from **any** Claude Code session — not necessarily the same one — to return
and collect status.

The terminal that ran `/afk` is not special and does not own anything. Close it, go to
sleep, come back in the morning, open a completely different project, and `/back` there
works exactly the same: it clears the state, tells every current session, asks for
status, and consolidates.

The commands are installed as personal skills, so they exist in every session on the
machine regardless of repository, working directory, workspace, project or which
terminal started them.

### The state file

One small JSON file, `~/.claude/session-presence/state.json`:

```json
{ "status": "afk", "mode": "sleep", "since": "2026-09-21T23:40:00+01:00", "message": null }
```

`mode` is `sleep`, `work`, or `null`. `/back` rewrites it as `{"status": "back", ...}`.

It exists for one reason: a session that never saw the `/afk` — a terminal opened this
morning — can still tell you *you were asleep for 7h 12m*. Without it, `/back` from a
fresh terminal knows nothing about the night.

It is a plain file read and written only by these three skills. No daemon, no database,
no watcher, no background process, no scheduled task, no hook — and it must never become
any of those. A missing, empty or corrupt file is never an error: the commands carry on
without the elapsed time.

**Idempotent.** `/afk sleep` twice, from the same terminal or different ones, is fine —
it overwrites and re-broadcasts, keeping the original `since` so elapsed time stays
true. `/back` twice is fine. `/back` with no prior `/afk` is fine. Presence is not a
fragile state machine.

`/broadcast` never touches it.

### Prior art

Tools in this space exist — **cc-dm**, **agent-chat**, **agent-bridge**,
**claude-relay**, **inter-session**, and a separate third-party **AFK plugin** with an
entirely different purpose. None are installed by this project and none are
dependencies; they were reviewed only to check which problems are already solved
elsewhere. The conclusion was the same each time: the native mechanism is sufficient,
so this stays a thin UX layer.

The third-party AFK plugin is unrelated to `/afk` here. The command name is kept; the
project name is different to avoid the collision.

## The native mechanism

Verified on Claude Code **2.1.278**:

| Tool | What it gives |
|---|---|
| `ListAgents` | Every session you can message — subagents, teammates, **other local Claude Code sessions**, cloud sessions when the account has them. Each row: `name [ref]`, kind, busy/idle, age. Its first line names the current session, which is the reply address. |
| `SendMessage` | `{ to, message, summary, notify_when_idle }`. `to` is the name as printed. The message lands in the other session as `<cross-session-message from="..." from-name="...">`. `notify_when_idle` is a native one-shot idle notice — no polling. |

That is the whole substrate. These skills are instructions for using it consistently.

## Commands

### `/broadcast <message>`

```
/broadcast O deploy de staging terminou. Não mexam no banco ainda.
```
```
Discovered 4 · delivered 3 · failed 1

Sent:
✓ api-1f    interactive · busy · started 21m ago
✓ docs-3c    interactive · idle · started 15h ago
✓ web-7a    interactive · busy · started 51m ago

Unavailable:
⚠ cli-2e    session no longer accepting messages
```

Your text is relayed **verbatim**, wrapped as `[User broadcast] ...` and nothing more —
never summarized, rephrased, turned into a prompt, or read as a permission change.
Multi-line messages keep their line breaks. The single added footer tells the receiving
session that this is information, not an order and not new authorization.

### `/afk [context]`

| Command | Meaning |
|---|---|
| `/afk` | User is away. No return time — nothing is assumed about when he's back. |
| `/afk sleep` | User is sleeping. |
| `/afk work` | User is away at work; may take hours to answer. |
| `/afk volto amanhã` | Free context, passed through verbatim. |

```
/afk sleep
```
```
Discovered 4 · delivered 4 · unavailable 0

Sent:
✓ api-1f  ✓ docs-3c  ✓ web-7a  ✓ cli-2e

Sleep AFK sent to 4 sessions. They will continue safe autonomous work and avoid
actions that could trigger authentication, elevation or interactive prompts.
```

The operational policy is the same for every variant; only the emphasis changes. The
rule, in one line:

> **AFK means you are physically away, not unreachable.** Sessions keep full progress,
> ask you through Remote Control only for decisions that truly block, group the rest,
> and defer only steps that need your body at the machine (authentication, elevation,
> credentials, local QA). A physical blocker is never a mission blocker.

Sessions are told to keep reading, analysing, coding, fixing, testing, reviewing,
researching, documenting and running local work they are already authorized to do, at
full speed and without touching Auto Mode, model, effort or permission mode. You may
still answer from your phone: a question that truly blocks is asked once through
Remote Control (without waiting on it); non-urgent ones are grouped; and anything that
needs you physically at the machine waits for `/back`. Your messages during AFK are
normal interaction and do not end it. Only `/back` does.

What they defer: anything that could predictably raise an interactive prompt — a
password manager or vault unlock, a Windows password / PIN / Hello / fingerprint / face check,
a passkey, UAC or any elevation, a credential or browser auth popup, interactive OAuth
or device authorization, MFA/2FA or a phone push approval, or any physical
confirmation.

**And they don't run a command just to find out whether it prompts.** A reasonable
chance is enough to defer. "I'll run it and stop if it asks" has already failed — by
then the prompt is open, the screen is lit, and it stays that way until you're back.

A blocked step blocks only itself. Independent work continues, and the session records
a one-line blocker for `/back`:

```
BLOCKED FOR USER: Supabase CLI authentication required before deployment. Code, tests
and build are complete. Resume with: supabase login, then deploy.
```

**AFK does not mean unrestricted autonomy.** It is never authorization for a
destructive action, a deploy, a merge, a publication, a production change, a purchase,
an outbound external message, anything irreversible, or credentials not already held. A
session that needed your approval before still needs it.

Sessions that could not be reached are listed separately, under a heading saying they do
**not** know you are away. The report never implies otherwise.

### `/back [anything]`

```
/back
```
```
You're back. Status requested from 4 sessions.
Discovered 4 · delivered 4 · failed 0
```

then, as answers arrive — **what was waiting on you, first**:

```
4/4 sessions responded

Needs you now
  docs-3c — C:\work\billing
    Supabase CLI authentication required before deploy. Code, tests and build
    complete. Resume with: supabase login, then deploy.
  api-1f — C:\work\api
    Windows elevation required to restart the service. Ready when you are.

Completed while AFK
  web-7a — C:\work\scpe        tests and build complete
  cli-2e — C:\work\locker   diagnostics complete

Still running
  api-1f    RLS suite, ~10 min left

Other blockers
  web-7a    upstream API returning 503, retrying with backoff

No reply yet
  ops-9d    interactive · busy · started 7h ago
```

The order is fixed: **Needs you now** → **Completed while AFK** → **Still running** →
**Other blockers**. The first section collects everything blocked on password manager, a
password, PIN, Windows Hello, UAC or elevation, MFA, a passkey, a login, a credential, a
confirmation or a human decision — each with where it stopped and how to resume.

Return notice and status request go out as **one** message per session, not two.

**`/back` does not authorize anything either.** Sessions may reconsider steps they
deferred, but not execute them on the strength of your return. A session needing
elevation says `I need elevation to continue. Ready when you are.` and waits.

#### The vault goes first

`/back` is the one moment a human is guaranteed to be at the machine — which is exactly
what the AFK policy spends all its effort avoiding the rest of the time. That makes it
the only safe moment to raise a credential prompt, and a locked vault is usually the
cheapest blocker to clear: one unlock releases every session at once.

So when any session reports a vault- or credential-shaped blocker, `/back` opens above
every other section with:

```
🔑 Unlock password manager now — re-arms the 24h signing window and releases the staged
   commits in cli-2e, api-1f and web-7a
```

It **tells you; it never unlocks**. That needs your body, not a command. It will not
trigger a signing operation to force the prompt either: on Windows each sub-shell needs
its own authorization from the app, so a prompt raised by a tool call authorizes a shell
that is about to exit — repeat that and you get a row of PIN prompts for nothing.

It also does not act on the other sessions: no "retry now" messages, no committing their
staged work. One unlock re-arms the window and each session picks it up by itself.

When nothing is blocked on credentials, the line does not appear at all.

## Limitations — real ones, in this build

**The broadcast reaches the sessions alive right now; the state file outlives them.**
A terminal opened after you leave, or one that was unavailable, is never notified — and
nothing makes it read the state file on startup, because that would need a
`SessionStart` hook, excluded by design. So a session started at 3am does not know you
are asleep. What *is* preserved is the record: any session running `/back` later reads
the state and reports how long you were gone, and the three commands consult the file
whenever they need it. Honest summary:

- sessions open at the moment of `/afk` receive the broadcast;
- the global state stays on record regardless;
- new sessions are not auto-synchronized, and no infrastructure is added to make them.

Revisit only if Claude Code grows a native presence mechanism — prefer that to the file.

**`/back` requires no prior `/afk`.** It works when `/afk` was never run, when some
sessions never got it, when sessions started or ended while you were out, after a
restart, and when the state file is missing or corrupt.

**Replies are asynchronous and bounded by the turn, not by a timer.** `SendMessage` is
fire-and-forget; a reply arrives whenever that session next reaches a tool call. `/back`
dispatches, reports, consolidates what arrived, and closes with `3/4 responded · 1 still
busy`. It never blocks, polls or re-sends. `notify_when_idle` supplies the one native,
one-shot signal that separates a silent session from a slow one. A session that has not
answered is reported as *no reply yet* — unknown, not dead.

**Delivery is not readership.** A successful send means the message reached the session.
A session in a different permission mode holds peer messages for its user's approval and
may let them expire; a session can refuse inbound messages outright. For sessions on
this machine a `[Cross-session delivery notice]` reports that. For Remote Control, cloud
and Claude Desktop sessions nothing reports back at all — silence there is not
agreement.

**Session names are short handles, not project names.** `ListAgents` returns
`api-1f [c68a8d]`, derived from the working directory — so several sessions rooted in
the same parent folder all read as the same short prefix. The listing carries no
working-directory or repository field, so a friendly `api — C:\work\api` cannot be
built from discovery alone.
Two consequences: `/broadcast` and `/afk` label sessions with name + kind + state + age,
the most identifying data the listing exposes; and `/back` asks each session to report
its own `dir:`, which is the one reliable way to get a project label. `ListAgents` also
accepts `channel` and `q` parameters that are inert in 2.1.278.

**Scope is local by default.** `ListAgents` can surface cloud sessions and, with Remote
Control connected, sessions on other machines, each row labelled by kind. These skills
target peer sessions **on this machine**. A cloud session receives a message but cannot
reply into your conversation, so including it in `/back` would guarantee a permanent
*no reply yet*.

**At most one copy per target per invocation.** Messages are not re-sent because a call
was slow, a result was ambiguous, a session took its time, or the session list was
refreshed. A retry happens only after a confirmed failure, at most once, and is
reported as `retried once`.

## Safety

`/broadcast` transmits. `/afk` transmits absence. `/back` transmits return and asks a
question. None of them deploy, push, merge, publish, delete, change infrastructure,
grant permissions or alter settings — and none instruct another session to.

Permission boundaries are per-session. Asking a peer to do what your own session blocked
would launder the permission decision around you, so every message body states that
nothing has changed. Work a peer was already authorized to do, it keeps doing.

A failure is isolated to its target. With eight sessions and one bad target, the other
seven are still delivered, and the report closes with discovered / delivered / failed.

**`/afk` transmits a policy; it does not enforce one.** There is no password manager
integration, no credential handling, no control over Windows lock state, no elevation
check and no prompt detection anywhere in this project — and none should be added. The
receiving sessions apply the policy themselves. That is the whole point of keeping this
a messaging layer.

## Install

```powershell
pwsh -File install.ps1
```

Copies the three skills to `~/.claude/skills/{broadcast,afk,back}`, which is what makes
the bare `/broadcast`, `/afk` and `/back` work in any session on the machine. Restart
Claude Code (or `/clear`) afterwards.

Once installed they are self-contained — nothing reads back into this repository, so
they work from any working directory.

Remove with `pwsh -File install.ps1 -Uninstall`.

As a plugin instead, `.claude-plugin/plugin.json` declares `./skills`; installed that
way the commands are namespaced (`/session-presence:broadcast`).

## Hooks: zero

```
Hooks added by this plugin: 0
```

Hooks were ruled out by design, not by limitation. `SessionStart`, `UserPromptSubmit`,
`PreToolUse` and `PostToolUse` all run on someone else's schedule and have a poor
history on Windows. Nothing here needs them: `ListAgents` and `SendMessage` are called
directly, when you type the command, and never otherwise.

`.claude-plugin/plugin.json` contains no `hooks` key. The repository contains no hook
definition, no background process, and nothing that runs on a timer. Verify with:

```powershell
Select-String -Pattern 'hook|SessionStart|UserPromptSubmit|PreToolUse|PostToolUse' -Path .claude-plugin\plugin.json
```

## Size

| | |
|---|---|
| Skills | 3 |
| Files | 7 |
| Runtime code | 0 lines — the skills are markdown; `install.ps1` is ~30 lines of file copying |
| Dependencies added | 0 |
| Processes, daemons, servers, databases, state files | 0 |

Small on purpose. The hard part is native; the contribution here is UX and presence
semantics.

## Windows

Built and tested on Windows, on one machine. `install.ps1` is PowerShell (`pwsh`), uses
`Join-Path` and `$HOME` rather than POSIX path assumptions, and copies rather than
symlinks — a junction or symlink would need admin rights or Developer Mode for three
markdown files. Nothing in the project requires Bash, WSL or a POSIX shell.
