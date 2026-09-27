---
name: live
description: "List live local Claude Code sessions, excluding offline or stale Remote Control entries. Canonical session source for /afk, /back and /broadcast."
---

# /live

Lists the Claude Code sessions on **this machine** that are alive right now and can
receive a message. This file is also **the** definition of a live session. /afk, /back
and /broadcast read "The rule" below and apply it exactly. They never keep a copy of it.

## The rule (canonical — the other skills point here)

Call `ListAgents` once. Its first line names this session, and it is never a peer.
From the peer rows, a row is a **live session** only when **all** of these hold:

1. **It is a local Claude Code session.** Its kind column reads `interactive`, or
   another kind that `ListAgents` documents as a local session on this machine.
   A row that says "also connected via Remote Control" is still local.
2. **It is not a Remote Control row.** Exclude any row whose kind is `Remote Control`.
   These are stale entries or sessions on another machine, even if a name matches a
   local project.
3. **It is not a cloud session, an in-process subagent or a teammate.** Only sibling
   terminal sessions count.
4. **Its state is alive.** `idle`, `busy`, `working`, `waiting`, `needs-input`, or an
   equivalent running state. Any row that says `offline`, `exited`, `ended`,
   `unreachable` or `stale` is excluded. When in doubt, exclude it.

A local row that `ListAgents` lists is reachable by construction: it has a local
inbox. There is no second probe. Anything that fails the rule is **not live**: never
send it a message, an AFK or back notice, a status request or a checkpoint query.
Never delete, archive, reconnect or otherwise touch a non-live entry either. Leave it
exactly as it is.

## Procedure

1. Call `ListAgents` and apply the rule.
2. Print one line per live session, and nothing else:

   ```
   wavr — idle
   guardian — working
   luckycat — idle
   ```

   - **Name:** exactly as the row prints it, without the ` [ref]`; add it only when
     two live rows share a name.
   - **Status:** the row's state, with `busy` shown as `working`; any other state
     verbatim.
3. No live sessions → print `No live sessions.`
4. Do not list the excluded rows, do not explain them, and do not message anyone.
   Plain `/live` is read-only; only `/live power` sends a question.

## `/live power` — current session power

Answers "what model / effort / fast mode is each live session on?":

1. Take the live sessions from the rule above.
2. For **this** session, report only what it can confirm locally: the model from its own
   context, effort and fast mode from the harness or status line. Anything it cannot
   confirm is `UNKNOWN`.
3. Ask each live session once, in one block:
   `SendMessage({to: "<name>", summary: "power status", message: "[From <this session>] Reply to <this session> with one line, only what you can confirm locally (never infer): model | effort | fast on/off. Unconfirmed value = UNKNOWN."})`
4. Print what has arrived, and mark every row that has not answered, or any value it
   could not confirm, as `UNKNOWN`:

   ```
   CURRENT SESSION POWER
   wavr      opus-5-5 | high    | fast off
   guardian  opus-5-5 | medium  | fast off
   luckycat  UNKNOWN  | UNKNOWN | UNKNOWN   (no reply yet)
   control   opus-5-5 | medium  | fast off
   ```

   Fold in later replies as they land. Never re-send, never poll, and never fill a value
   in from memory or from what was requested.
