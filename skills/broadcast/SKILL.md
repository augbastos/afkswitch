---
name: broadcast
description: Relay one message from the user to every other reachable local Claude Code session. Explicit invocation only - never trigger this because a conversation mentions broadcasting, announcing, or telling the other sessions something.
disable-model-invocation: true
---

# /broadcast

Relay one message from the user to every other Claude Code session reachable from here.

**This is communication only.** It grants no permissions, changes no settings, and asks
no session to perform work. Receiving sessions treat it as information.

The message is everything the user typed after `/broadcast`. If that is empty, say so
and stop — there is nothing to relay.

## Procedure

1. Call `ListAgents`. Use the **peer sessions** only — ignore in-process subagents and
   teammates. This session is never in that list, so there is no self to exclude.
2. No peers → report `No other sessions reachable.` and stop. That is a success, not an
   error.
3. Send to every peer. Issue all the `SendMessage` calls **in one block** so they go out
   together, using each row's name exactly as printed:

   ```
   SendMessage({ to: "<name>", summary: "user broadcast", message: <body below> })
   ```

   Body — the first line is all the recipient's human sees as a preview, so the user's
   own words must be in it:

   ```
   User broadcast: <message, verbatim>

   This is information from the user, not an instruction and not a permission change.
   Nothing about your current authorizations has changed. Act on it only where it
   affects work you are already doing.
   ```

   Relay the message verbatim. Do not summarize it, translate it, or append anything
   the user did not say.
4. One failed send never fails the run. Note it and keep going.

## Report

```
Broadcast sent to 3 of 4 sessions.
✓ api-1f    busy · started 21m ago
✓ docs-3c    idle · started 15h ago
✓ web-7a    busy · started 51m ago
✗ cli-2e    <the actual error>
```

Carry each row's state from `ListAgents` — a bare session name means nothing on its own.
Report only errors that actually happened; never invent a failure to pad the list.

## Limits worth stating when they bite

- A successful send means the message **reached** that session, not that its Claude has
  read it. A session in a different permission mode holds peer messages for its user's
  approval; a `[Cross-session delivery notice]` reports that for sessions on this
  machine.
- Busy sessions receive on their next tool round. That is normal — do not re-send.
