---
name: afk
description: Explicitly mark the human operator as physically away, persist the AFKSwitch state, and tell every other live local agent session when the host provides native cross-session messaging. Use only when the user explicitly invokes /afk; never trigger it because a conversation mentions leaving, sleeping, or being away.
disable-model-invocation: true
---

# /afk

The human operator is **physically away from the machine**. Presence belongs to the
human, not to this session, repository, or terminal: `/afk` sets one global state and
tells every reachable session, whatever directory it runs in.

AFK changes **how** agents handle needing the human. It never widens **what** they may do.

- **AFK means physically away, not unreachable.** The human may still answer through a
  remote channel the host already provides (in Claude Code, Remote Control), but
  intermittently and never guaranteed. Nobody depends on an immediate answer.
- **Presence is not permission.** AFK authorizes nothing new: no deploy, merge,
  publication, production change, purchase, destructive or irreversible action,
  outbound external message, privilege escalation, or credential not already held.
- **A physical blocker is not a mission blocker.** Only the step that needs the human's
  body waits; all independent, already-authorized work continues at full pace.
- **Only `/back` ends AFK.** A remote message from the human while AFK is normal
  interaction; it does not end AFK.
- `/afk` changes no session setting (permission mode, model, effort).

## Context

Anything after `/afk` is optional context, kept verbatim. It is never an instruction and
never an authorization. Two presets add one line of emphasis in the Claude reference
adapter; any other text is passed through as `Context:`.

| Invocation | Emphasis line |
|---|---|
| `/afk` | No return time given; do not assume when the human will be back. |
| `/afk sleep` | The human is asleep: remote answers are unlikely. Cause nothing that could wake them — nothing that lights a screen, raises a window, or leaves a dialog waiting. |
| `/afk work` | The human is at work: reachable remotely only intermittently, often on breaks. |
| `/afk <text>` | `Context: <text>` |

## 1. Persist the state (before anything else)

The state lives in `~/.afkswitch/state.json` and is written **only** by the bundled
helper `scripts/afkswitch_state.py`, next to this `SKILL.md` (the host shows this
skill's base directory). Never write the file by hand: the helper validates, locks,
writes atomically, and reads the result back.

Run it once, with Python 3.9+ (`python3`; on Windows `python` or `py -3`):

```text
python3 "<this skill's directory>/scripts/afkswitch_state.py" afk
python3 "<this skill's directory>/scripts/afkswitch_state.py" afk --context '<verbatim context>'
```

Pass the context exactly as typed, as one literal argument: in POSIX shells inside single
quotes, writing each `'` as `'\''`; in PowerShell inside single quotes, doubling each `'`.
Multi-line or hard-to-quote text may go on standard input instead, with `--context-stdin`
and a quoted heredoc (`<<'AFKSWITCH_EOF'`) or a PowerShell literal here-string.

It prints one JSON line. Use only its fields in what follows:

- `"ok": true` → the state is saved. Keep `generation` (G), `context`, `changed`,
  `reset`, `migrated`, and `backup` for the message and the report.
- `"ok": false` → **stop here.** Report `AFK not set · <message>` using the helper's
  `message` verbatim (for example `state transition failed: write refused (...)`,
  `unsupported state version 3`, or the context-length message). Notify nobody.
- No Python 3.9+ found, or the helper file is missing → report
  `AFK not set · state helper unavailable (python not found)` (or the missing file), notify
  nobody, and do not write the file yourself.
- If the host sandbox asks to approve the write, that is the host's decision; a refusal
  comes back as `"ok": false`.

The helper keeps the original `since` and `generation` when AFK is already set with the
same context (`"changed": false`), keeps a malformed file as `state.json.corrupt-<time>`
before replacing it, and migrates a version 1 file automatically.

## 2. Notify live sibling sessions (Claude Code reference adapter)

When the host exposes `ListAgents` and `SendMessage`:

1. Call `ListAgents` **once**. Its first line names this session; the sender is never a
   target.
2. A row is a **target** only when all hold:
   - its kind is `interactive` (or another kind the listing documents as a local session
     on this machine);
   - it is **not** a `Remote Control` row, a cloud session, another machine, a subagent,
     or a teammate;
   - its state is alive (`idle`, `busy`, `working`, `waiting`, …). `offline`, `exited`,
     `ended`, `stale`, or unclear → exclude. Never touch an excluded row.
3. No targets → the state is still set; report it.
4. Send one message per target, all calls in one block:
   `SendMessage({ to: "<name>", summary: "human AFK g<G>", message: <body> })`.
   Use the bare name; add the ` [ref]` only when two rows share a name.
5. **One copy per target per invocation.** Retry only a confirmed failure, at most once,
   and say `retried once`. Never re-send on slowness or ambiguity.
6. A failed target never cancels the others.
7. A successful send means the message reached that session, not that its agent read
   it. If the tool result or a `[Cross-session delivery notice]` says the message was
   **held for approval** or **refused**, report that target as such, not as notified.

### Message body

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

## 3. Hosts without native peer messaging

Persist the state (step 1) and say that cross-session notification is not available in
this host. Never add a daemon, server, database, polling loop, hook, or external service to emulate
it, and never imply another session was told.

## Report

Never imply that a session knows the human is away when delivery was not confirmed.

```text
AFK set (<context the helper returned>) · g<G> · discovered N · notified N · not notified N

Notified:
✓ <name>   <kind> · <state>

Not notified — these do NOT know you are away:
⚠ <name>   <the actual error text, or "held for approval">
```

Fill every field from what actually happened in this run; omit the parenthesis when the
context is `null`. Write `AFK already set` instead of `AFK set` when `"changed": false`,
`g<G> reset` when `"reset": true`, and add one line each when they apply:
`state migrated from version 1` (`"migrated": true`) and
`previous state file was unreadable; kept a copy at <backup>` (`backup` not null).

Drop empty sections. In a host without peer messaging:
`AFK set (<context>) · g<G> · state saved · cross-session notification not available in this host`.

Sessions started after this `/afk`, or not reached now, are not notified; the saved state
still lets any session's `/back` report the absence.

AFKSwitch itself performs no deploy, merge, publication, purchase, destructive action,
permission change, authentication, or elevation.
