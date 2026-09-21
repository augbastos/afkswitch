---
name: afk
description: Tell every reachable local Claude Code session that the user has stepped away, so they keep working autonomously within existing permissions instead of waiting on him. Explicit invocation only - never trigger this from a conversation mentioning that the user is leaving, sleeping, or going away.
disable-model-invocation: true
---

# /afk

Tell every other reachable Claude Code session that the user is away from the computer.

This changes **how** those sessions handle needing him. It does **not** widen what they
are allowed to do.

Anything typed after `/afk` is optional context — `sleep`, `work`, `volto em 3 horas`,
`fui dormir, volto amanhã`. There is no required argument; bare `/afk` is valid and
simply omits the context line.

## Procedure

1. Call `ListAgents`. Peer sessions only. This session is never listed, so the sender
   is excluded automatically — it already knows.
2. No peers → report `No other sessions reachable.` and stop.
3. Send to every peer, all `SendMessage` calls in one block:

   ```
   SendMessage({ to: "<name>", summary: "user AFK", message: <body below> })
   ```

   Body — include the `Context:` sentence only when the user gave an argument:

   ```
   [User broadcast] The user is AFK and not at the computer. Context: <argument>

   Keep working autonomously wherever that is safe and already authorized. Do not sit
   idle waiting for an immediate reply.

   If you hit something that genuinely needs him — a decision, credentials, an
   irreversible or destructive action, anything published externally, or a permission
   you do not already hold — preserve the current state, record the blocker plainly,
   and carry on with independent work instead.

   Being AFK grants no extra permissions. Do not do anything that would normally need
   his explicit approval just because he is away.
   ```
4. **One copy per target per invocation.** Do not re-send because a call was slow, a
   result read ambiguously, or you re-ran `ListAgents`. Re-send only after a confirmed
   failure for that target, at most once, and say so in the report (`retried once`).
5. A failed target never cancels the run.

## No state is stored

Nothing is written to disk. The broadcast **is** the feature: `/afk` sends the away
message, `/back` sends its inverse. Do not build a presence file, database, daemon or
watcher to track this — the receiving sessions hold the message in their own
transcripts, which is where the context belongs.

## Report

Never imply a session knows he is away when it does not. Split the two groups:

```
Discovered 4 · delivered 3 · unavailable 1

Sent:
✓ api-1f    interactive · busy · started 21m ago
✓ docs-3c    interactive · idle · started 15h ago
✓ web-7a    interactive · busy · started 51m ago

Unavailable — these do NOT know you are away:
⚠ cli-2e    <the actual error text>
```

Close with one line saying what the reached sessions were told: continue autonomously
within existing permissions, record blockers rather than wait. Drop an empty section.

Then state the standing limitation plainly whenever any session was unavailable, and
whenever the user is likely to open a terminal while away:

> `/afk` reaches the sessions alive **right now**. A session started after this, or one
> that was unavailable, has no idea you are away.

That is accepted for v0.1 — do not build synchronization to fix it.
