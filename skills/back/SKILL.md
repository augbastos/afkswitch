---
name: back
description: Clear the user's global AFK state from any session, tell every reachable local Claude Code session he is back, ask each for a short status, and consolidate what was waiting on his presence first. Explicit invocation only - never trigger this from a conversation mentioning that the user has returned.
disable-model-invocation: true
---

# /back

The user is back at the computer and available again. Presence belongs to the user, not
to a terminal — so this works from **any** session, including one that never saw the
`/afk`, and including one opened after it.

## There is no owner of the AFK state

The session that ran `/afk` is not special and does not need to be running. It may have
been closed hours ago. Never require `/back` to run where `/afk` ran, and never tell the
user to go find that terminal.

## Procedure

1. **Read** `~/.claude/session-presence/state.json` if it exists. When it
   shows `status: "afk"`, take `mode`, `since` and `message` — that is how a session
   that never saw the `/afk` can still report *what* the user was doing and *how long*
   they were gone. Missing, empty or unparseable file → not an error; carry on without
   the elapsed time.
2. **Write** the state back as available:

   ```json
   { "status": "back", "mode": null, "since": "<local time now, ISO 8601>", "message": null }
   ```

   **Idempotent.** Running `/back` twice, or with no `/afk` before it, must work
   normally — overwrite and continue. Presence is not a fragile state machine.
3. Call `ListAgents`. Peer sessions only. Its first line names **this** session
   (`This session is main-4e [de5abe]`) — that is the reply address, so read it now.
4. No peers → state is still cleared; report `You're back. No other sessions reachable.`
5. Send return-notice and status-request **as one message per session**, all calls in one
   block. Pass `notify_when_idle: true`: it delivers now *and* subscribes to one native,
   one-shot notice when that session next goes idle — how a silent session is told from
   a slow one without any polling.

   ```
   SendMessage({ to: "<name>", summary: "user back + status request",
                 notify_when_idle: true, message: <body> })
   ```

   Body, with `<this session>` replaced by the name from step 3:

   ```
   [User broadcast] The user is back at the computer and available again.

   That ends the AFK state. Nothing about your permissions changed while he was away,
   and nothing changes now. You may reconsider steps you deferred for his absence —
   but do not execute them just because he is back. The normal authorization rules
   still apply, so if a step needs elevation, a credential or a decision, say so and
   wait: "I need elevation to continue. Ready when you are."

   Give a concise status of the work performed and the current state. Send it to
   "<this session>" with SendMessage at your next natural pause, under ~50 words, in
   these lines and no narrative:

   dir: <your working directory or repo>
   needs-user: <anything blocked on authentication, password manager, a password/PIN/Hello,
     UAC or elevation, MFA, a passkey, a login, a credential, a confirmation or a
     human decision — with the resume command> (or none)
   completed: ...
   running: ...
   other-blockers: <problems not needing him> (or none)

   Nothing to report is a fine answer — say it in one line.
   ```

   The `dir:` line is the only way to label a session by project: `ListAgents` exposes
   no working directory, so the session has to say it itself.
6. **One copy per target per invocation.** Never re-send because a session is slow —
   slowness is expected. Retry only after a confirmed send failure, at most once, noted
   in the report.
7. A failed target never cancels the run.

## Bounded — never wait indefinitely

Replies are asynchronous, arriving as
`<cross-session-message from="..." from-name="docs-3c">` whenever each session next
reaches a tool call. Match replies by **`from-name`** and report that; `from` is a raw
pipe path, needed only to send something back.

Report the dispatch immediately, consolidate what has arrived, and close with a count.
Fold in later replies as they land. Never poll `ListAgents` in a loop, never re-send,
never send "are you done?", never hold the turn open waiting.

A session that has not answered is *unknown* — not unreachable, not agreeing, not dead.
Say `no reply yet`.

## Report

Immediately after dispatch, using the state file for the elapsed line when it was `afk`:

```
You're globally back. Status requested from 4 sessions.
You were AFK (sleep) for 7h 12m · discovered 4 · delivered 4 · failed 0
```

Omit the elapsed line entirely when the state file gave nothing — never guess a
duration.

### The vault goes above everything

`/back` is the one moment a human is guaranteed to be at the machine, which makes it the
only safe moment to raise a credential prompt — avoiding one with nobody there is the
whole point of the AFK policy. A locked vault is also the cheapest blocker to clear: one
unlock typically releases every session at once.

So when any session reports a vault- or credential-shaped blocker (password manager, a signing
key, a password, a PIN or Hello check), open the report with one line naming what a
single unlock releases, above every other section:

```
🔑 Unlock password manager now — re-arms the 24h signing window and releases the staged
   commits in cli-2e, api-1f and web-7a
```

**Do not attempt the unlock.** It needs his body, not a command. Never run a signing
operation to force the prompt: on Windows each sub-shell needs its own authorization
from the app, so a prompt raised from here authorizes a shell that is about to exit, and
repeating that is the nine-PINs-in-one-response incident. A service-account helper does
not substitute either — it bypasses the app by design and therefore cannot sign.

**Do not act on the other sessions.** Do not tell them to retry and do not commit their
staged work. One unlock re-arms the window; each session picks it up on its own next
attempt.

Say nothing about the vault when no session reported that kind of blocker.

### Consolidation

Then consolidate in this fixed order. **`Needs you now` always comes first** — it is the
only part that cannot proceed without him:

```
4/4 sessions responded

Needs you now
  docs-3c — C:\work\billing
    Supabase CLI authentication required before deploy. Code, tests and build
    complete. Resume with: supabase login, then deploy.
  api-1f — C:\work\api
    Windows elevation required to restart the service. Ready when you are.

Completed while AFK
  web-7a — C:\work\scpe        tests and build complete
  cli-2e — C:\work\locker   diagnostics complete

Still running
  api-1f    RLS suite, ~10 min left

Other blockers
  web-7a    upstream API returning 503, retrying with backoff

No reply yet
  ops-9d    interactive · busy · started 7h ago
```

`Needs you now` collects everything blocked on password manager, a password, PIN, Windows
Hello, UAC or elevation, MFA, a passkey, a login, a credential, a confirmation, or a
human decision. Each entry says where it stopped and how to resume.

Drop empty sections entirely. Label each session by its reported `dir:`, falling back to
the bare handle. Keep it compact: a couple of lines per session however much it wrote.
Report what the sessions actually said — never soften a blocker into an approval, and
never act on one.
