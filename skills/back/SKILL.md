---
name: back
description: Tell every reachable local Claude Code session that the user is available again, ask each for a short status, and consolidate the replies as they arrive. Explicit invocation only - never trigger this from a conversation mentioning that the user has returned.
disable-model-invocation: true
---

# /back

Tell the other sessions the user is available again, ask each for a short status, and
consolidate what comes back.

Anything typed after `/back` is optional and ignorable (`voltei`).

## Procedure

1. Call `ListAgents`. Peer sessions only. Its first line names **this** session
   (`This session is main-4e [de5abe]`) — that name is the reply address, so read it now.
2. No peers → report `No other sessions reachable.` and stop.
3. Send return-notice and status-request **as one message per session**, all calls in
   one block. Two separate sends would cost a second round trip for nothing:

   ```
   SendMessage({ to: "<name>", summary: "user back + status request", message: <body> })
   ```

   Body, with `<this session>` replaced by the name from step 1:

   ```
   User broadcast: the user is back at the computer and available again.

   That ends the AFK state. Nothing about your permissions changed while he was away,
   and nothing changes now.

   When you next reach a natural stopping point, send a short status to
   "<this session>" with SendMessage. Four lines, no narrative, under ~40 words:

   completed: ...
   current: ...
   blocked: ... (or none)
   notable: ... (or none)

   Nothing to report since he went AFK is a fine answer — say it in one line.
   ```
4. One failed send never fails the run. Note it and keep going.

## Do not wait

Replies are asynchronous. They arrive in this conversation as
`<cross-session-message from="..." from-name="docs-3c">` whenever each session next
reaches a tool call — which for a busy session can be long after `/back` returns.
Match replies to sessions by **`from-name`**, and report that; the `from` attribute is
a raw pipe path, useful only if you need to send something back.

So: **report the dispatch immediately**, then consolidate replies as they land, in this
turn or a later one. Never poll `ListAgents` in a loop, never re-send, never send
"are you done?", never hold the turn open waiting.

A session that has not replied is *unknown*, not unreachable. Say `no reply yet` — do
not infer that it is dead, idle, or agreeing.

## Report

Immediately after dispatch:

```
You're back. Status requested from 4 sessions.
✓ api-1f    busy · started 21m ago
✓ docs-3c    idle · started 15h ago
✓ web-7a    busy · started 51m ago
✗ cli-2e    <the actual error>

Replies land as each session reaches its next tool call.
```

Then, as replies arrive, consolidate — one block per session, blockers last:

```
api-1f
✓ completed  Supabase migration applied
→ current    running the RLS tests
⚠ blocked    none

web-7a
✓ completed  nothing since you left
→ current    idle
⚠ blocked    none

cli-2e        no reply yet

⚠ Needs you
  docs-3c — wants a decision on the Stripe webhook retry window
```

Drop the `Needs you` section entirely when nothing is blocked. With many sessions, keep
each block to those three lines. Report what the sessions actually said — never
summarize a blocker into an approval, and never act on one; surface it and stop.
