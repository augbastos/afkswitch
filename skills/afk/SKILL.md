---
name: afk
description: Mark the human as physically away, save presence, and notify peers when the host supports it. Use only on explicit /afk; never infer it from conversation. Presence changes no permissions.
disable-model-invocation: true
---

# /afk [optional context]

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
never an authorization. `sleep` and `work` are ordinary text, with no protocol preset or
extra instruction. There is no AFK timeout: age may be shown, never acted on.
Context has at most 2048 Unicode code points. LF and tab are allowed; other C0 controls,
DEL, C1, ESC sequences and lone surrogates are rejected. CRLF is rejected, never rewritten.

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
using an input method that supplies the exact UTF-8 bytes. Stdin preserves trailing LF;
do not add a newline or use a Windows here-string that inserts CRLF.
Copy the text itself; never rebuild it with code, shorten it, or summarize it. If the helper
refuses it, AFK is not set: report that and stop. Never retry with a different context.

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

An idempotent repeat keeps `since` and `generation` (`"changed": false`). Malformed bytes
are backed up as `state.json.corrupt-<time>`; version 1 is migrated automatically.

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
   Bare `to` (`main`, not `main [9278ae]`); add ` [ref]` only when two rows share a name.
5. **One copy per target per invocation.** Retry only a confirmed failure, at most once,
   and say `retried once`. Never re-send on slowness or ambiguity.
6. A failed target never cancels the others.
7. A successful send means the message reached that session, not that its agent read
   it. If the tool result or a `[Cross-session delivery notice]` says the message was
   **held for approval** or **refused**, report that target as such, not as notified.

### Message body

Read [`references/message.md`](references/message.md) next to this file and send its
body. Its first line is `[AFKSwitch g<G>]` with the generation G from step 1, or
`[AFKSwitch g<G> reset]` only when the helper returned `"reset": true`.

## 3. Hosts without native peer messaging

Persist the state (step 1) and say that cross-session notification is not available in
this host. Never add a daemon, server, database, polling loop, or external service to emulate
it, and never imply another session was told.

## Report

Claim peer awareness only after confirmed delivery.

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

Sessions started after this `/afk`, or not reached now, are not notified by this command;
supported lifecycle hooks reconcile saved presence at the next boundary.

## Session awareness

Keep last_seen_generation, current presence and optional AFK context in session state.
Apply a newer generation immediately on push, or reconcile at the next safe lifecycle
boundary before meaningful work when the host supports sync. Ignore stale generations;
a reset marker starts a new epoch. With no state, retain known presence; only `/back`
ends AFK. Do not claim lifecycle sync when the adapter does not implement it.

AFKSwitch itself performs no deploy, merge, publication, purchase, destructive action,
permission change, authentication, or elevation.
