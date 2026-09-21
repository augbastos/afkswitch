# claude-session-comms

Presence and messaging between Claude Code sessions on one machine: `/broadcast`,
`/afk`, `/back`.

Three markdown skills. No hooks, no daemon, no server, no watcher, no database, no
state file. They drive the cross-session messaging that Claude Code already ships.

## The native mechanism

Claude Code (verified on **2.1.278**) exposes two tools that do all the work:

| Tool | What it gives |
|---|---|
| `ListAgents` | Every session you can message — in-process subagents, teammates, **other local Claude Code sessions**, and cloud sessions when the account has them. Each row: `name [ref]`, kind, busy/idle, age. The first line of the output names the current session. |
| `SendMessage` | `{ to, message, summary }`. `to` is the name exactly as `ListAgents` printed it. The message arrives in the other session wrapped as `<cross-session-message from="...">`. |

That is the whole substrate. These skills are instructions for using it consistently —
which sessions to target, what to say, what to report, and what not to promise.

## Commands

### `/broadcast <message>`

Sends one message from you to every other reachable session.

```
/broadcast the migration is done; ~/work is the source of truth now
```
```
Broadcast sent to 3 of 4 sessions.
✓ api-1f    busy · started 21m ago
✓ docs-3c    idle · started 15h ago
✓ web-7a    busy · started 51m ago
✗ cli-2e    session no longer accepting messages
```

The message is relayed verbatim. Nothing is added beyond a line marking it as
information from you rather than an instruction from a peer agent.

### `/afk [context]`

Tells every session you have stepped away, so they keep going instead of idling on a
question you will not answer.

```
/afk sleep
```
```
AFK status sent to 4 sessions.
✓ api-1f  ✓ docs-3c  ✓ web-7a  ✓ cli-2e

They were told to continue autonomously within existing permissions and to record
blockers rather than wait.
```

**AFK does not mean unrestricted autonomy.** The message says so explicitly. It changes
*how* a session handles needing you — preserve state, write the blocker down, move to
independent work — and changes nothing about what it is allowed to do. A session that
needed your approval before still needs it.

Nothing is persisted. `/afk` sends the away message; `/back` sends its inverse. The
receiving sessions hold the context in their own transcripts, which is the right place
for it.

### `/back [anything]`

Announces your return, asks each session for a four-line status, and consolidates the
replies.

```
/back
```
```
You're back. Status requested from 4 sessions.
✓ api-1f  ✓ docs-3c  ✓ web-7a  ✗ cli-2e — unreachable

Replies land as each session reaches its next tool call.
```

Then, as answers arrive:

```
api-1f
✓ completed  Supabase migration applied
→ current    running the RLS tests
⚠ blocked    none

cli-2e        no reply yet

⚠ Needs you
  docs-3c — wants a decision on the Stripe webhook retry window
```

Return notice and status request go out as **one** message per session, not two.

## Limitations — real ones, in this build

**Replies to `/back` are asynchronous.** `SendMessage` is fire-and-forget. A reply
arrives in your conversation whenever that session next reaches a tool call, which for a
busy session is long after `/back` has returned. `/back` therefore dispatches, reports,
and consolidates later. It never blocks, polls, or re-sends. A session that has not
answered is reported as *no reply yet* — unknown, not dead.

**Delivery is not readership.** A successful send means the message reached the session.
A session running in a different permission mode holds peer messages for its user's
approval and may let them expire; a session can refuse inbound messages outright. For
sessions on this machine a `[Cross-session delivery notice]` reports that. For Remote
Control, cloud, and Claude Desktop sessions nothing reports back at all — silence there
is not agreement.

**Session names are short handles, not project names.** `ListAgents` returns
`api-1f [c68a8d]`, derived from the working directory — so four sessions under
`~/work` all read as `ia-*`. There is no per-session project label or working
directory in the listing, so the friendly `Wavr — ~/work/api` form is not
available. The skills print the name with the kind, busy/idle state and age from the
same row, which is the most identifying information this build actually exposes.
`ListAgents` also accepts `channel` and `q` parameters that are inert in 2.1.278.

**Scope is local by default.** `ListAgents` can surface cloud sessions and, with Remote
Control connected, sessions on other machines — each row labelled by kind. These skills
target **peer sessions on this machine**. A cloud session receives a message but cannot
reply into your conversation, so including it in `/back` would guarantee a permanent
*no reply yet*.

## Safety

`/broadcast` transmits. `/afk` transmits absence. `/back` transmits return and asks a
question. None of them deploy, push, merge, publish, delete, change infrastructure,
grant permissions, or alter settings — and none instruct another session to.

Permission boundaries are per-session. Asking a peer to do something your own session
blocked would launder the permission decision around the user, so the broadcast bodies
state plainly that nothing has changed. Work a peer was already authorized to do, it
keeps doing.

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
way the commands are namespaced (`/session-comms:broadcast`).

## Why no hooks

Hooks were ruled out by design, not by limitation. `SessionStart`, `UserPromptSubmit`,
`PreToolUse` and `PostToolUse` all run on someone else's schedule and have a poor
history on Windows. Nothing here needs them: `ListAgents` and `SendMessage` are called
directly, when you type the command, and never otherwise. The repository contains no
hook definition, no background process and nothing that runs on a timer.
