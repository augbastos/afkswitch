# /back peer message (Claude Code reference adapter)

Replace `<this session>` with the name read from `ListAgents` and `<G>` with the
generation from step 1; write `[AFKSwitch g<G> reset]` in the first line only when the
helper returned `"reset": true`.

```text
[AFKSwitch g<G>] The human operator is back: physically present again. AFK has ended.

Presence generation <G>. If you have already seen an AFKSwitch message with a higher
generation, this one is stale: ignore it and do not reply. The same generation again is a
repeat of the notice, but still answer this status request. When unsure, the "generation" in ~/.afkswitch/state.json is the truth.

Nothing about your permissions changed while they were away, and nothing changes now.
You may reconsider steps you deferred, but do not execute them just because the human is
back; normal authorization rules still apply. If a step needs a credential, elevation,
or a decision, say so and wait.

At your next natural pause, reply to "<this session>" with SendMessage, under ~50 words,
in exactly these lines (no narrative):

afkswitch-status g<G>
dir: <your working directory or project>
needs-human: <anything waiting on a decision, credential, login, elevation, passkey, MFA, local confirmation, or other human interaction, with the exact resume step> (or none)
completed: <what finished while AFK> (or none)
running: <what is still running> (or none)
other-blockers: <problems that do not need the human> (or none)

Nothing to report is a fine answer; say it in one line.
```
