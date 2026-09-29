# /afk peer message (Claude Code reference adapter)

The first line carries the generation G from step 1; write `[AFKSwitch g<G> reset]`
instead only when the helper returned `"reset": true`:

```text
[AFKSwitch g<G>] The human operator is AFK: physically away from the machine.
<emphasis line for the invocation>

Presence generation <G>. If you have already seen an AFKSwitch message with a higher
generation, this one is stale: ignore it. The same generation again is a repeat. When
unsure, the "generation" in ~/.afkswitch/state.json is the truth.

AFK means physically away, not unreachable, and it is not permission. Keep full progress
on work you were already authorized to do: do not stop, slow down, or become more
conservative. Nothing about your permissions changes. AFK never authorizes a deploy,
merge, publication, production change, purchase, destructive or irreversible action,
outbound external message, elevation, or credential you did not already hold.

Classify anything you need from the human:
1. REMOTE-BLOCKING: a decision you truly need now that they can make remotely. If the
   host already gives you an authorized remote channel, ask once, clearly, and keep doing
   independent work while you wait.
2. NON-URGENT: an answer would help but work remains. Record it; group questions.
3. PHYSICAL-BLOCKING: it needs the human at the machine — local visual QA, hardware, a
   desktop login, elevation/UAC, a credential or vault unlock, a passkey, MFA, or any
   interactive authentication or physical confirmation. Defer only that step.

Do not start anything that can predictably raise an interactive prompt, and do not run a
command just to find out whether it prompts: by then the prompt is open on an unattended
machine. A reasonable chance is enough to defer.

Record each deferred step in one line:
BLOCKED FOR HUMAN (<remote|physical>): <task> — stopped at <point> — needs <interaction> — resume with: <next action>

A remote message from the human while AFK is normal interaction and does not end AFK.
Only /back ends it.
```
