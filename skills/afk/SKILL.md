---
name: afk
description: Record that the user is physically away from the machine (he may still answer through Remote Control) and tell every live local Claude Code session, so they keep full progress, ask remotely only for decisions that truly block, and defer only physically-bound steps until /back. Explicit invocation only - never trigger this from a conversation mentioning that the user is leaving, sleeping, or going away.
disable-model-invocation: true
---

# /afk

The user is **not in front of the computer**. Presence belongs to the user, not to this
repository, terminal or project — so this sets a global state and tells every reachable
session, whatever directory any of them was started in.

This changes **how** sessions handle needing him. It does **not** widen what they may do.

## What AFK means (and does not)

```
PHYSICAL PRESENCE   = unavailable
REMOTE AVAILABILITY = possible, intermittent, never guaranteed
```

`/afk` means **only** that he is no longer physically at the laptop. The laptop may be
closed behind the screen locker, and every session stays on Remote Control. He often keeps
following from his phone, where he can read, send prompts, answer questions and decide.
He may also fall asleep or become unavailable without saying so.

AFK does **not** mean he is asleep, offline or unable to answer. It does not mean the
session lost access, and it does not mean work should be more conservative, slower or
stopped. **Nobody depends on an immediate answer from him.**

- **A physical blocker is not a mission blocker.** Only the one sub-step that needs his
  body is blocked; maximise progress around it.
- **A message from him through Remote Control during AFK is normal interaction.** It
  does not trigger `/back`, does not end AFK and does not by itself change his expected
  return. It only proves he is reachable right now. **Only `/back` ends AFK.**
- **Running `/afk` changes no session setting by itself.** It does not switch Auto
  Mode or the permission mode, and it does not touch model, effort or fast mode.
- **Model, effort and fast mode MAY change during AFK** when he asks for it (Remote
  Control included), when an already-authorised rule allows it, or for a valid
  operational reason. The danger to avoid is **state ambiguity**, so every change
  follows "Session power changes" below. Auto Mode and the permission mode stay as they
  are.
- Remote Control must stay available: assume he can appear and interact at any moment.

## Session power changes (model, effort, fast mode)

Applies whenever one of them changes during AFK, in any session:

1. Apply the change.
2. Confirm the **real** state of the session afterwards: read it from the local session
   (the status line, the command's own confirmation, or the session's reported model),
   not from the phone UI. A command that was sent is not a change that happened.
3. Report it short and explicit, before/after:

   ```
   model:  opus-5-5 → opus-5-5
   effort: medium → high
   fast:   off
   ```

4. If what was asked differs from what the session shows, say so plainly and keep the
   **known** state as the truth. Never pretend it worked.
5. A value you cannot confirm is `UNKNOWN`. Never infer it.

The control answers "what power is every session on?" with `/live power` (see
`~/.claude/skills/live/SKILL.md`).

## Variants

Anything after `/afk` is optional context. Three forms carry specific meaning; free text
is accepted and passed through.

| Form | Meaning | Extra emphasis in the message |
|---|---|---|
| `/afk` | Physically away | No return time. Remote answers possible but not guaranteed. |
| `/afk sleep` | He is asleep | Remote answers unlikely. Cause **no** interaction that could wake him — nothing that lights a screen, raises a window, or leaves a dialog open all night. |
| `/afk work` | At work | Reachable intermittently and unpredictably through Remote Control, often on breaks. |
| `/afk <free text>` | e.g. `volto amanhã`, `saí por algumas horas` | Passed through verbatim as `Context:`. |

The operational policy is identical in every case. Only the emphasis line changes.

## Procedure

1. **Write the global state** to `~/.claude/session-presence/state.json`
   (parent directory is created if missing):

   ```json
   {
     "status": "afk",
     "mode": "work",
     "since": "2026-09-21T09:40:00+01:00",
     "message": "chego em casa por volta de 18:30",
     "physical_presence": "unavailable",
     "remote_presence": "intermittent",
     "current_context": "work",
     "expected_physical_return": {"value": "18:30", "source": "user estimate",
                                  "confidence": "estimate"}
   }
   ```

   `mode` is `"sleep"`, `"work"`, or `null` for bare `/afk` and free text. `message` is
   the free-text argument, or `null`. `since` is the local time now, ISO 8601.
   `remote_presence` is `possible`, or `intermittent` for work, or `unlikely` for sleep.
   `current_context` is `work` | `away` | `sleep` | `unknown`. `expected_physical_return`
   is `null` unless a source gives it. It is **an estimate for planning, never a
   deadline or a precondition**. His own estimate (from the argument or a later Remote
   Control message) outranks an inferred one. A later message of his that states a new
   estimate may update this field; a message that says nothing about time does not.

   **Human context (control only, best effort).** The session running `/afk` is the
   control. When the work-roster integration is connected and already authorised, it may read his
   roster once, read-only: whether he works today, shift start and end, and breaks
   **only if the work-roster tool actually reports them**. It fills `current_context`, and
   `expected_physical_return` with `source: "work roster"`. Never invent a break, an
   arrival time or availability that the work-roster tool did not give. Commuting, delays and overtime
   happen. the work-roster tool unavailable → leave the fields `unknown`/`null` and carry on. Other
   sessions never query the work-roster tool; they receive only the summary line below.
   **`/afk` itself changes no session setting** (Auto Mode, permission mode, model,
   effort, fast mode).

   **Idempotent.** Already `afk`? Overwrite it anyway and re-broadcast — running
   `/afk sleep` twice, from the same terminal or a different one, must never break or
   refuse. Keep the *original* `since` when status and mode are unchanged, so the
   elapsed time stays true; reset it when the mode changes. If the file is missing,
   empty or unparseable, that is not an error: write a fresh one and carry on.
2. Get the **live sessions**: read "The rule" in `~/.claude/skills/live/SKILL.md` and apply
   it exactly to one `ListAgents` call. Only live sessions are targets. Offline rows,
   Remote Control rows, cloud sessions and other machines are never messaged. This
   session is never listed, so the sender is excluded automatically — it already knows.
3. No live sessions → still write the state, then report `State set. No other sessions
   reachable.` The global state is the durable part; the broadcast is best-effort.
4. Send to every live session, all `SendMessage` calls in one block:

   ```
   SendMessage({ to: "<name>", summary: "user AFK", message: <body below> })
   ```
5. **One copy per target per invocation.** No re-send on a slow call, an ambiguous
   result, or a refreshed listing. Retry only after a confirmed failure, at most once,
   and say so (`retried once`).
6. A failed target never cancels the run.

## Message body

Open with the variant line, then the policy:

```
[User broadcast] The user is AFK: physically away from the machine. <variant line>
<context line, only when known: "Context: work until ~18:30 (work roster, estimate)." or "Expected back ~18:30 (his estimate)." — planning only, never a deadline>

Physical presence: unavailable. Remote availability: possible but intermittent and never
guaranteed; he may answer from his phone through Remote Control. Keep full progress: do
not slow down, stop, or become more conservative. Auto Mode and the permission mode stay
as they are. Model, effort and fast mode may change when he asks, when an authorised
rule allows it or for a valid operational reason; after any change, confirm the REAL
state and report "model: a → b / effort: a → b / fast: on|off", flag any mismatch, and
say UNKNOWN when you cannot confirm. Never depend on an immediate answer. A message from
him during AFK is normal interaction and does NOT end AFK; only /back does.

Classify anything you need from him:
1. REMOTE-BLOCKING: a decision you truly need now that he can make from a phone. Ask it
   through Remote Control, once and clearly. Do not wait on it: keep doing independent
   work. If he doesn't answer, it becomes pending-human; come back to it only when it
   is really needed.
2. NON-URGENT: his answer would help, but independent work remains. Record it and group
   it with the others; do not send one message per question.
3. PHYSICAL-BLOCKING: it needs his body at the machine (local QA, visual/local
   interaction Remote Control can't give, desktop login, a local GUI prompt, hardware).
   Mark only that sub-step for /back and continue everything else.

Physical prompts are PHYSICAL-BLOCKING. Do not start anything that
could predictably raise an interactive prompt: a password manager or other vault unlock, a
Windows password / PIN / Hello / fingerprint / face check, a passkey, UAC or any
elevation or "run as administrator", a credential or browser authentication popup,
interactive OAuth or device authorization, MFA/2FA or a phone push approval, or any
physical confirmation.

Do not run a command just to find out whether it will prompt. A reasonable chance is
enough — defer that step instead. "I'll run it and stop if it asks" has already failed:
by then the prompt is open, the screen is lit, and it stays that way until he is back.

Being AFK grants no extra permissions. It is not authorization for a destructive action,
a deploy, a merge, a publication, a production change, a purchase, an outbound external
message, anything irreversible, or credentials you did not already hold.

A physical blocker is not a mission blocker: it blocks only its own sub-step. Finish
every independent part of the work, then record each blocker in one line:

BLOCKED FOR USER (<remote|physical>): <task> — stopped at <exact point> — needs
<which interaction> — resume with: <next command or action>
```

Variant lines:

- bare → `No return time given, so do not assume when he will be back. He may still answer remotely.`
- `sleep` → `He is asleep, so remote answers are unlikely. Be especially careful to cause no interaction with the computer that could wake him — nothing that lights a screen, pulls a window to the foreground, or leaves a dialog waiting overnight.`
- `work` → `He is at work. He often checks in on breaks and may answer through Remote Control, intermittently and unpredictably.`
- free text → `Context: <text, verbatim>`

## Scope of this skill

It **transmits a policy and records a state**. It enforces nothing. There is no
password manager integration, no credential handling, no control over Windows lock state, no
elevation check and no prompt detection — and none should be added. The receiving
sessions apply the policy themselves.

The state file is a plain JSON file written by these skills and read by them. It is not
backed by a daemon, database, watcher, background process, scheduled task or hook, and
must never become one.

## Report

Never imply a session knows he is away when it does not.

```
Global AFK (sleep) set · discovered 4 · delivered 3 · unavailable 1

Sent:
✓ api-1f    interactive · busy · started 21m ago
✓ docs-3c    interactive · idle · started 15h ago
✓ web-7a    interactive · busy · started 51m ago

Unavailable — these do NOT know you are away:
⚠ cli-2e    <the actual error text>
```

Close with the line matching the variant:

- `/afk` → `Global AFK sent to N sessions. They keep full progress, ask you through Remote Control only for decisions that truly block, and defer only physically-bound steps (authentication, elevation, password manager, local QA) until /back.`
- `/afk sleep` → `Global AFK (sleep) sent to N sessions. They keep full progress and avoid anything that could light the screen or raise a prompt.`
- `/afk work` → `Global AFK (work) sent to N sessions. They keep full progress, group non-urgent questions, and may reach you on breaks through Remote Control.`

Drop an empty section. Then, whenever any session was unavailable:

> Broadcast reaches the sessions alive **right now**. A session started after this, or
> one that was unavailable, is not notified — though the global state remains on record
> for `/back`.

Accepted — do not add a hook, watcher or daemon to fix it.
