---
name: afk
description: Set the user's global presence to away and tell every reachable local Claude Code session, so they keep working autonomously within existing permissions and defer anything needing authentication, elevation, credentials or physical presence until /back. Explicit invocation only - never trigger this from a conversation mentioning that the user is leaving, sleeping, or going away.
disable-model-invocation: true
---

# /afk

The user is **not in front of the computer**. Presence belongs to the user, not to this
repository, terminal or project — so this sets a global state and tells every reachable
session, whatever directory any of them was started in.

This changes **how** sessions handle needing him. It does **not** widen what they may do.

## Variants

Anything after `/afk` is optional context. Three forms carry specific meaning; free text
is accepted and passed through.

| Form | Meaning | Extra emphasis in the message |
|---|---|---|
| `/afk` | Generic absence | No return time. Do not assume when he is back. |
| `/afk sleep` | He is asleep | Cause **no** interaction that could wake him — nothing that lights a screen, raises a window, or leaves a dialog open all night. |
| `/afk work` | At work, away from the machine | May take several hours to answer. |
| `/afk <free text>` | e.g. `volto amanhã`, `saí por algumas horas` | Passed through verbatim as `Context:`. |

The operational policy is identical in every case. Only the emphasis line changes.

## Procedure

1. **Write the global state** to `~/.claude/session-presence/state.json`
   (parent directory is created if missing):

   ```json
   {
     "status": "afk",
     "mode": "sleep",
     "since": "2026-09-21T23:40:00+01:00",
     "message": "volto amanhã"
   }
   ```

   `mode` is `"sleep"`, `"work"`, or `null` for bare `/afk` and free text. `message` is
   the free-text argument, or `null`. `since` is the local time now, ISO 8601.

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
[User broadcast] The user is AFK and not at the computer. <variant line>

Keep working autonomously. Read, analyse, code, fix, test, review, research, document,
and run local work you are already authorized to do. Do not sit idle just because he is
away, and do not message him while he is gone — save it for /back.

Defer any step that could need him present. Specifically, do not start anything that
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

A blocked step blocks only itself. Finish every independent part of the work, then stop
in the best state available and record the blocker in one line:

BLOCKED FOR USER: <task> — stopped at <exact point> — needs <which interaction> —
resume with: <next command or action>
```

Variant lines:

- bare → `No return time given, so do not assume when he will be back.`
- `sleep` → `He is asleep. Be especially careful to cause no interaction with the computer that could wake him — nothing that lights a screen, pulls a window to the foreground, or leaves a dialog waiting overnight.`
- `work` → `He is at work and away from the machine; he may take several hours to answer.`
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

- `/afk` → `Global AFK sent to N sessions. They will continue autonomously and defer anything requiring user interaction, authentication, elevation or password manager until /back.`
- `/afk sleep` → `Global AFK (sleep) sent to N sessions. They will continue safe autonomous work and avoid actions that could trigger authentication, elevation or interactive prompts.`
- `/afk work` → `Global AFK (work) sent to N sessions. They will continue safe autonomous work and queue user-dependent steps for /back.`

Drop an empty section. Then, whenever any session was unavailable:

> Broadcast reaches the sessions alive **right now**. A session started after this, or
> one that was unavailable, is not notified — though the global state remains on record
> for `/back`.

Accepted — do not add a hook, watcher or daemon to fix it.
