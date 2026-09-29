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

## 1. Persist the state (before anything else)

The state lives in `~/.afkswitch/state.json` and is written **only** by the bundled
helper `scripts/afkswitch_state.py`, next to this `SKILL.md` (the host shows this
skill's base directory). Never read or write the file by hand for this step.

Run it once, with Python 3.9+ (`python3`; on Windows `python` or `py -3`):

```text
python3 "<this skill's directory>/scripts/afkswitch_state.py" back
```

It prints one JSON line. Use only its fields in what follows:

- `"ok": true` → the state is saved. Keep `generation` (G), `previous`, `afk_lasted`,
  `changed`, `reset`, `migrated`, and `backup`. `previous` is what was saved before this
  `/back` (`null` if nothing valid was): that is how a session that never saw the `/afk`
  reports what the human was doing and for how long.
- `"ok": false` → **stop here.** Report `Not marked back · <message>` using the helper's
  `message` verbatim (for example `state transition failed: ...` or
  `unsupported state version 3`). Notify nobody and request no status.
- No Python 3.9+ found, or the helper file is missing → report
  `Not marked back · state helper unavailable (python not found)` (or the missing file),
  notify nobody, and do not write the file yourself.

`/back` is idempotent: repeating it, or running it with no prior `/afk`, works normally
(`"changed": false` keeps `since` and `generation`).

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

   `SendMessage({ to: "<name>", summary: "human back g<G> + status request", notify_when_idle: true, message: <body> })`

5. **One copy per target per invocation.** Retry only a confirmed failure, at most once,
   and say `retried once`. A failed target never cancels the others. A message **held
   for approval** or **refused** is reported as such, not as delivered.

### Message body

Read [`references/message.md`](references/message.md) next to this file and send its
body, with `<this session>` replaced by the name read from `ListAgents`. Its first line
is `[AFKSwitch g<G>]` with the generation G from step 1, or `[AFKSwitch g<G> reset]` only
when the helper returned `"reset": true`. It asks for a reply that starts with
`afkswitch-status g<G>`.

`ListAgents` does not expose working directories, so the `dir:` line is how each
session is labelled by project.

### Bounded — never wait indefinitely

Report the dispatch immediately. Replies arrive asynchronously as cross-session messages
whenever each session reaches its next tool round; fold them in as they land. Never poll
`ListAgents`, never re-send, never send "are you done?", never hold the turn open.

A session that has not replied is **no reply yet** — not failed, not dead, not agreeing,
not finished.

Count a reply only when it comes from a session this `/back` asked and starts with
`afkswitch-status g<G>` for this G. A reply naming an older generation answers an earlier
`/back`: show it under `Late replies (earlier /back)`, never in the tally. When two
sessions share a name, keep them apart by the ` [ref]` you sent to.

## 3. Hosts without native peer messaging

Persist the state (step 1) and say that cross-session notification and status collection
are not available in this host:
`You're back · AFK (<context>) lasted <afk_lasted> · g<G> · state saved · cross-session notification not available in this host`. Add no infrastructure to emulate them.

## Report

Right after dispatch:

```text
You're back · AFK (<previous.context>) lasted <afk_lasted> · g<G> · discovered N · notified N · status requested from N
```

Take the context and the duration **only** from the helper's `previous.context` and
`afk_lasted`, never from this template or from memory. Omit the parenthesis when the
saved context was `null`, and omit the whole `AFK … lasted …` part when `afk_lasted` is
`null` (nothing valid was AFK). Write `Already back` instead of `You're back` when
`previous.status` was `available`, `g<G> reset` when `"reset": true`, and add one line each
when they apply: `state migrated from version 1` (`"migrated": true`) and
`previous state file was unreadable; kept a copy at <backup>` (`backup` not null).

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
