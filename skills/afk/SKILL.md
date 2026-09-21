---
name: afk
description: Tell every reachable local Claude Code session that the user has stepped away, so they keep working autonomously within existing permissions instead of waiting on him. Explicit invocation only - never trigger this from a conversation mentioning that the user is leaving, sleeping, or going away.
disable-model-invocation: true
---

# /afk

Tell every other reachable Claude Code session that the user is away from the computer.

This changes **how** those sessions handle needing him. It does **not** widen what they
are allowed to do.

Anything the user typed after `/afk` is optional context (`sleep`, `work`,
`volto em 3 horas`). There is no required argument.

## Procedure

1. Call `ListAgents`. Peer sessions only.
2. No peers → report `No other sessions reachable.` and stop.
3. Send to every peer in one block of `SendMessage` calls:

   ```
   SendMessage({ to: "<name>", summary: "user AFK", message: <body below> })
   ```

   Body — include the `Context:` line only when the user gave one:

   ```
   User broadcast: the user is AFK and not at the computer. Context: <argument>

   Keep working autonomously wherever that is safe and already authorized. Do not sit
   idle waiting for an immediate reply.

   If you hit something that genuinely needs him — a decision, credentials, an
   irreversible or destructive action, anything published externally, or a permission
   you do not already hold — preserve the current state, record the blocker plainly,
   and carry on with independent work instead.

   Being AFK grants no extra permissions. Do not do anything that would normally need
   his explicit approval just because he is away.
   ```
4. One failed send never fails the run. Note it and keep going.

## No state is stored

Nothing is written to disk. The broadcast **is** the feature: `/afk` sends the away
message, `/back` sends its inverse. Do not build a presence file, database, daemon or
watcher to track this — the receiving sessions hold the AFK message in their own
transcripts, which is where the context belongs.

## Report

```
AFK status sent to 4 sessions.
✓ api-1f    busy · started 21m ago
✓ docs-3c    idle · started 15h ago
✓ web-7a    busy · started 51m ago
✓ cli-2e    busy · started 7h ago
```

Close with one line stating what they were told: to continue autonomously within
existing permissions and to record blockers rather than wait.

Carry each row's state from `ListAgents` — a bare session name means nothing on its own.
