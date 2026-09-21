---
name: back
description: Tell every reachable local Claude Code session that the user is available again, ask each for a short status, and consolidate the replies as they arrive. Explicit invocation only - never trigger this from a conversation mentioning that the user has returned.
disable-model-invocation: true
---

# /back

Tell the other sessions the user is available again, ask each for a short status, and
consolidate what comes back.

Anything typed after `/back` is optional and ignorable (`voltei`).

## No prior state required

`/back` never fails for lack of an AFK state, because no AFK state exists anywhere. It
works identically when `/afk` was never run, when some sessions never received it, when
a session started or ended while the user was away, and after Claude Code restarted. It
only ever does three things: announce availability, ask the sessions alive **now** for
status, consolidate the answers.

## Procedure

1. Call `ListAgents`. Peer sessions only. Its first line names **this** session
   (`This session is main-4e [de5abe]`) — that is the reply address, so read it now.
2. No peers → report `No other sessions reachable.` and stop.
3. Send return-notice and status-request **as one message per session**, all calls in
   one block. Two sends would cost a round trip for nothing. Pass
   `notify_when_idle: true`: it delivers now *and* subscribes to one native, one-shot
   notice when that session next goes idle, which is how a silent session gets
   distinguished from a slow one without any polling.

   ```
   SendMessage({ to: "<name>", summary: "user back + status request",
                 notify_when_idle: true, message: <body> })
   ```

   Body, with `<this session>` replaced by the name from step 1:

   ```
   [User broadcast] The user is back and available again.

   That ends the AFK state. Nothing about your permissions changed while he was away,
   and nothing changes now.

   Give a concise status of the work performed and the current state — especially
   anything completed, currently running, or blocked on user input. Send it to
   "<this session>" with SendMessage at your next natural pause, under ~40 words,
   in these lines and no narrative:

   dir: <your working directory or repo>
   completed: ...
   current: ...
   blocked: ... (or none)
   notable: ... (or none)

   Nothing to report is a fine answer — say it in one line.
   ```

   The `dir:` line is the only way to label a session by project: `ListAgents` does not
   expose a working directory, so the session has to tell you itself.
4. **One copy per target per invocation.** No re-sending because a session is slow to
   answer — slowness is expected. Re-send only after a confirmed send failure, at most
   once, and note it in the report.
5. A failed target never cancels the run.

## Bounded — never wait indefinitely

Replies are asynchronous. They arrive as
`<cross-session-message from="..." from-name="docs-3c">` whenever each session next
reaches a tool call, which for a busy session can be long after `/back` returns. Match
replies by **`from-name`** and report that; `from` is a raw pipe path, needed only to
send something back.

So: **report the dispatch immediately**, consolidate whatever has arrived, and close the
turn with a count. Fold in later replies as they land. Never poll `ListAgents` in a
loop, never re-send, never send "are you done?", never hold the turn open waiting.

A session that has not answered is *unknown*, not unreachable, not agreeing, not dead.
Say `no reply yet`.

## Report

Immediately after dispatch:

```
You're back. Status requested from 4 sessions.
Discovered 4 · delivered 4 · failed 0

Replies land as each session reaches its next tool call.
```

Then consolidate, **blockers first** — they are the only part that needs him:

```
3/4 sessions responded · 1 still busy

⚠ Needs you
  docs-3c — C:\work\billing
    decision on the payment webhook retry window

✓ Completed
  api-1f — C:\work\api                   schema migration landed, tests green
  web-7a — C:\work\docs                  nothing since you left

→ In progress
  api-1f    running the RLS suite
  web-7a    idle

✗ Errors
  api-1f    one flaky Playwright spec, retried and passed

No reply yet
  cli-2e    interactive · busy · started 7h ago
```

Order is fixed: blockers, completed, in progress, errors, silent. Label each session by
its reported `dir:` when it gave one, falling back to the bare handle. Drop empty
sections entirely — no `Errors` heading when nothing errored.

Keep it compact: a few words per session, never paragraphs, and never more than a
couple of lines each no matter how much a session wrote. Report what the sessions
actually said — never soften a blocker into an approval, and never act on one. Surface
it and stop.
