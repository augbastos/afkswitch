---
name: back
description: Explicitly mark the human operator as physically present again from any session, persist the AFKSwitch state, tell every other live local agent session, request a short status from each when the host supports it, and consolidate what needs the human first. Use only when the user explicitly invokes /back; never trigger it because a conversation mentions returning.
disable-model-invocation: true
---

# /back

The human operator is **physically present again**. Presence belongs to the human, so
`/back` works from **any** session: one that never saw the `/afk`, one opened after it,
or after the session that ran `/afk` was closed. No session owns the AFK state; never ask
the human to find the terminal that ran `/afk`.

**Returning is not approval.** Every permission and authorization boundary that applied
before AFK still applies. Deferred steps may be reconsidered, not executed just because
the human is back.

## 1. Read, then persist the state

1. Read `~/.afkswitch/state.json` if it exists. If it is a valid `afk` state, keep its
   `since` and `context`: that is how a session that never saw the `/afk` reports what
   the human was doing and for how long. Missing, empty, or malformed → not an error;
   report no duration.
2. Write:

   ```json
   { "version": 1, "status": "available", "since": "<local time now, ISO 8601 with offset>", "context": null }
   ```

`/back` is idempotent: repeating it, or running it with no prior `/afk`, works normally.
If the host sandbox refuses the write, say so plainly.

## 2. Notify live sibling sessions and request status (Claude Code reference adapter)

When the host exposes `ListAgents` and `SendMessage`:

1. Call `ListAgents` **once**. Its first line names this session (`This session is
   <name> …`): that name is the reply address. The sender is never a target.
2. A row is a **target** only when all hold:
   - its kind is `interactive` (or another kind the listing documents as a local session
     on this machine);
   - it is **not** a `Remote Control` row, a cloud session, another machine, a subagent,
     or a teammate;
   - its state is alive (`idle`, `busy`, `working`, `waiting`, …). `offline`, `exited`,
     `ended`, `stale`, or unclear → exclude. Never touch an excluded row.
3. No targets → the state is still cleared; report it.
4. Send the return notice and the status request **as one message per target**, all
   calls in one block, with `notify_when_idle: true` (one native, one-shot notice when
   that session next goes idle — how a silent session is told from a slow one without
   polling):

   `SendMessage({ to: "<name>", summary: "human back + status request", notify_when_idle: true, message: <body> })`

5. **One copy per target per invocation.** Retry only a confirmed failure, at most once,
   and say `retried once`. A failed target never cancels the others. A message **held
   for approval** or **refused** is reported as such, not as delivered.

### Message body

Replace `<this session>` with the name read in step 1.

```text
[AFKSwitch] The human operator is back: physically present again. AFK has ended.

Nothing about your permissions changed while they were away, and nothing changes now.
You may reconsider steps you deferred, but do not execute them just because the human is
back; normal authorization rules still apply. If a step needs a credential, elevation,
or a decision, say so and wait.

At your next natural pause, reply to "<this session>" with SendMessage, under ~50 words,
in exactly these lines (no narrative):

dir: <your working directory or project>
needs-human: <anything waiting on a decision, credential, login, elevation, passkey, MFA, local confirmation, or other human interaction, with the exact resume step> (or none)
completed: <what finished while AFK> (or none)
running: <what is still running> (or none)
other-blockers: <problems that do not need the human> (or none)

Nothing to report is a fine answer; say it in one line.
```

`ListAgents` does not expose working directories, so the `dir:` line is how each
session is labelled by project.

### Bounded — never wait indefinitely

Report the dispatch immediately. Replies arrive asynchronously as cross-session messages
whenever each session reaches its next tool round; fold them in as they land. Never poll
`ListAgents`, never re-send, never send "are you done?", never hold the turn open.

A session that has not replied is **no reply yet** — not failed, not dead, not agreeing,
not finished.

## 3. Hosts without native peer messaging

Persist the state and say that cross-session notification and status collection are not
available in this host. Add no infrastructure to emulate them.

## Report

Right after dispatch:

```text
You're back · AFK (<context from the saved state>) lasted <now − saved since> · discovered N · notified N · status requested from N
```

Take the context and the duration **only** from the state file you read in step 1, never
from this template or from memory. Write the duration exactly (for example `51s`,
`7h 12m`). Omit the parenthesis when the saved context was `null`, and omit the whole
duration when the prior state gave no valid `afk` `since`. Never guess either.

Then consolidate replies in this fixed order, dropping empty sections:

```text
2/3 sessions replied

Needs you now
  api — ~/work/api
    Elevation required to restart the local service. Code and tests done.
    Resume with: restart the service, then run the smoke test.

Completed while AFK
  docs — ~/work/docs   site build and link check complete

Still running
  api   integration suite, ~10 min left

Other blockers
  docs  upstream API returning 503, retrying with backoff

No reply yet
  billing   interactive · busy
```

- **Needs you now comes first**: it is the only part that cannot proceed without the
  human. When one human action releases several sessions (for example, a single unlock
  or login), put it on the first line with the sessions it releases.
- Never perform that action yourself and never trigger the prompt to "help": it needs the
  human. Do not tell other sessions to retry or act on their blockers.
- Label each session by its reported `dir:`, falling back to its name. Keep a couple of
  lines per session. Report what sessions said; never soften a blocker into an approval.
