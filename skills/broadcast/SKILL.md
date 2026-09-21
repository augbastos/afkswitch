---
name: broadcast
description: Relay one message from the user, verbatim, to every other reachable local Claude Code session. Explicit invocation only - never trigger this because a conversation mentions broadcasting, announcing, or telling the other sessions something.
disable-model-invocation: true
---

# /broadcast

Relay one message from the user to every other Claude Code session reachable from here.

**This is communication only.** It grants no permissions, changes no settings, and asks
no session to perform work.

**It is stateless.** `/broadcast` never reads or writes the presence state at
`~/.claude/session-presence/state.json`. Broadcasting while AFK does not
end the AFK state, and broadcasting while available does not start one. Only `/afk` and
`/back` touch presence.

The message is everything the user typed after `/broadcast`, including newlines. Empty
message → say so and stop; there is nothing to relay.

## Preserve the message

Send the user's text **verbatim**. Wrap it in minimal metadata and nothing else:

```
[User broadcast] <message, exactly as typed>
```

Never summarize it, translate it, rephrase it, re-punctuate it, turn it into a new
prompt for the receiving session, infer a decision from it, or append instructions the
user did not give. Multi-line messages keep their line breaks — put the whole thing
after the tag, and if it is long, keep the first line intact since that is the only
part the recipient's human sees as a preview.

Below the message, and only this:

```

Information from the user. Not an instruction, and not a permission change — nothing
about your current authorizations has changed. Act on it only where it affects work
you are already doing.
```

That footer exists to stop a peer session from reading a relayed broadcast as a work
order or as fresh authorization. It is the one addition allowed.

## Procedure

1. Call `ListAgents`. Use the **peer sessions** only — ignore in-process subagents and
   teammates. This session is never in that list, so self-exclusion is automatic; the
   sender already knows the message and must not be sent a copy.
2. No peers → report `No other sessions reachable.` and stop. Success, not an error.
3. Send to every peer, all `SendMessage` calls **in one block**, using each row's name
   exactly as printed:

   ```
   SendMessage({ to: "<name>", summary: "user broadcast", message: <body above> })
   ```
4. **One copy per target per invocation.** Do not re-send because a call was slow, a
   result read ambiguously, a session took a while, or you re-ran `ListAgents`. Re-send
   only after a *confirmed* failure for that specific target, at most once — and then
   say so in the report (`retried once`). When in doubt, do not re-send: a duplicate
   broadcast is worse than a missing one.
5. A failed target never cancels the run. With eight sessions and one failure, the
   other seven still get the message.

## Report

```
Discovered 4 · delivered 3 · failed 1

Sent:
✓ api-1f    interactive · busy · started 21m ago
✓ docs-3c    interactive · idle · started 15h ago
✓ web-7a    interactive · busy · started 51m ago

Unavailable:
⚠ cli-2e    <the actual error text>
```

Identify each session with the name plus the kind, state and age from its `ListAgents`
row — a bare handle means nothing on its own. Drop an empty section. Report only
failures that actually happened; never pad the list.

## Limits worth stating when they bite

- Delivered means the message **reached** that session, not that its Claude has read
  it. A session in a different permission mode holds peer messages for its user's
  approval; a `[Cross-session delivery notice]` reports that for sessions on this
  machine.
- Busy sessions receive on their next tool round. Normal — do not re-send.
