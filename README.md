# claude-session-presence

Three tiny Claude Code skills that provide broadcast and human presence semantics on
top of native cross-session messaging.

`/broadcast` · `/afk` · `/back`

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
- `/afk` — tell every session you're unavailable
- `/back` — tell every session you're back, and collect status

```
Claude Code native session discovery + messaging
                      ↑
        /broadcast  /afk  /back
```

Not: our daemon → database → polling → hooks → custom protocol → messaging server.

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

```
/afk sleep
```
```
Discovered 4 · delivered 4 · unavailable 0

Sent:
✓ api-1f  ✓ docs-3c  ✓ web-7a  ✓ cli-2e

They were told to continue autonomously within existing permissions and to record
blockers rather than wait.
```

The argument is optional — bare `/afk` works.

**AFK does not mean unrestricted autonomy.** The message says so explicitly. It changes
*how* a session handles needing you — preserve state, write the blocker down, move to
independent work — and changes nothing about what it may do. A session that needed your
approval before still needs it.

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

then, as answers arrive, **blockers first**:

```
3/4 sessions responded · 1 still busy

⚠ Needs you
  docs-3c — C:\work\billing
    decision on the payment webhook retry window

✓ Completed
  api-1f — C:\work\api              schema migration landed, tests green

→ In progress
  api-1f    running the RLS suite

No reply yet
  cli-2e    interactive · busy · started 7h ago
```

Return notice and status request go out as **one** message per session, not two.

## Limitations — real ones, in this build

**`/afk` reaches the sessions alive right now.** A terminal opened after you leave, or
one that was unavailable, has no idea you are away. There is no persistent presence and
new sessions inherit nothing — that would take a hook, a daemon or a watcher, all of
which are excluded by design. Accepted for v0.1; revisit only if a simple native
presence mechanism appears.

**`/back` requires no prior state**, precisely because none is stored. It works when
`/afk` was never run, when some sessions never got it, when sessions started or ended
while you were out, and after a restart.

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
