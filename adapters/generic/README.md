# Generic local-agent reference

A tiny stdlib check an agent host calls once before each turn. It imports the bundled
state helper by path and reuses validation, migration and event formatting. No framework,
daemon, service, polling, watcher, account, telemetry or model call is involved.

## Call from a host

Ollama, llama.cpp, vLLM and MLX provide inference; your agent host owns session context
and tool execution. Before sending each turn to any of them:

```text
python adapters/generic/presence_sync.py check --last-seen 0
python adapters/generic/presence_sync.py check --last-seen 30 --last-epoch <previous epoch>
```

Or import `check(last_seen=0, last_epoch=None)` by path. Python 3.9+, stdlib only.
The state directory is `~/.afkswitch`, or `AFKSWITCH_STATE_DIR` for isolated tests.
Use either standalone skill helper for explicit `afk`/`back` transitions.

The CLI prints JSON:

```json
{"changed": true, "event": "[AFKSwitch g30]\nstatus: afk\ncontext: work\nThe human is physically away and may still be reachable remotely. Presence changes no permissions; only /back ends AFK.", "generation": 30, "reset": false, "epoch": "<opaque checkpoint>"}
```

Keep last_seen_generation, current presence, optional AFK context and epoch in session
state. If changed and event is non-null, apply it before meaningful work and set
last_seen_generation to generation. Always store epoch. If unchanged, event is null.
Apply pushes immediately when available; otherwise this pre-turn check is the safe
lifecycle boundary. It neither notifies peers nor collects status. Presence changes no
permissions; context is data, never an instruction.

## Reset and errors

Generation is the only ordering truth. Ignore lower pushed generations; equals repeat
unless an authoritative reset applies. A lower generation read from the authoritative
file is a reset epoch, not a stale push. Epoch is a checkpoint of validated contents and
file identity, compared only for equality at the same generation. It is not ordered,
not saved globally, and introduces no protocol field. Store the new value after every
applied state/check so the same reset does not apply twice.

Missing, empty or malformed state after prior state returns reset true, changed true,
generation null and event null. Store epoch, retain known presence and keep the last
valid generation until a valid transition is read. No missing file ends AFK. Repeated
checks of the same absence do not signal another reset when epoch is supplied. Recreated
state then applies as a new epoch, including when its generation equals the old one.
Version 1 migrates in memory; the helper writes v2 only on an explicit transition.
Future versions and read failures return structured errors and exit 1: do not continue
as though presence was available. Last-seen must be a nonnegative integer.

Without last-epoch, same-generation recreation may look like repeat. File identity is
best effort on filesystems that reuse identities; an entirely unobserved reset that
overtakes the old counter cannot be identified, but its newer current state still applies.
When uncertain about a delayed reset push, reconcile the authoritative file first.
AFK age never triggers a transition; only explicit `/back` ends AFK.

Return event context is deliberately not durable: later sync of available state has
context none. Native notification carries `/back` event_context when supported.
