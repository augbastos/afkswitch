# AFKSwitch conformance

Model-independent checks for state, sync, notify and fanIn capabilities in
[`spec/presence.md`](../spec/presence.md). Nothing here starts a host, calls a model, or
touches your real `~/.afkswitch`.

## Run it

```text
python -m pip install pytest                # optional existing jsonschema checks skip if unavailable
python -m pytest conformance -q -p no:cacheprovider
python conformance/checker.py conformance/notify/scenarios.json conformance/fan-in/scenarios.json conformance/sync/scenarios.json conformance/cross-host/scenarios.json
```

Python 3.9 or newer. CI runs the same commands on Linux, Windows, and macOS.
Pytest uses the ignored `.test-conformance` directory in the checkout (overridable
with `--basetemp`) to avoid slow sandbox TEMP storage on Windows. Pytest replaces
that directory each run; run one suite per checkout at a time. Fixture matrices call
the helper's real `main()` in-process with isolated stdin/stdout and environment;
CLI smoke checks, independent skill execution and both six-process concurrency tests
still use real subprocesses. All file writes retain the production fsync and lock logic.
Setting `AFKSWITCH_HELPER` retains subprocess execution for alternative implementations.

## What PASS means, per capability

### Lifecycle hooks — `conformance/hooks/`

Synthetic state and transcripts prove startup AFK injection, default available silence,
generation deduplication, authoritative lower-generation and version-1 reset handling,
tail-only transcript reads, universal event formatting, Agy ephemeral AFK output and
fail-open behavior. State hashes and directory contents are unchanged. These tests
exercise the hook entry point and CLI, not installation or host trust decisions.

### State-only — `conformance/state/`

Executable tests against the state helper (by default the reference one,
`skills/afk/scripts/afkswitch_state.py`; set `AFKSWITCH_HELPER` to test another
command-compatible script). Each test uses its own temporary directory through
`AFKSWITCH_STATE_DIR`. PASS means all of these hold:

- `/afk` and `/back` write a valid version 2 state, creating missing parent directories.
- `/back [context]` keeps available context null and returns verbatim event_context.
- Repeating a command is idempotent: `since` and `generation` stay the same.
- Every durable transition raises `generation` by exactly one.
- Context of 0, 1 and 2048 code points (ASCII, accented, emoji, multi-line) is kept
  verbatim; 2049 is rejected with a clear message and nothing is written.
- Unsafe C0 (except LF/tab), DEL, C1, ESC, CR/CRLF and lone surrogates are rejected before
  any write, for both commands. Stdin preserves trailing LF. Fixtures include failing controls.
- Each skill helper is self-contained; the return skill runs without any sibling files.
- A missing or empty file is no prior state; a malformed one is backed up byte for byte to
  `state.json.corrupt-<timestamp>` before it is replaced; a version 1 file is migrated
  (generation 1); a newer version is refused with `unsupported state version N` and the
  file is left untouched.
- A failed write (injected failures of `os.replace`, `fsync`, a refused temp file, or a
  state that does not read back) reports `state transition failed` and leaves the previous
  file intact, with no temp or lock file left behind.
- On POSIX the directory ends up `0700` and the file `0600`.
- A stale lock is broken; a live one makes a waiter give up honestly.
- Six processes run 60 interleaved transitions: every result succeeds, the final file is
  valid, and the generations of the changing transitions are exactly 1..N with no
  duplicate. A mutation check runs the same fleet with the lock removed and requires that
  test to **fail**, proving it can.
  The Windows stress worker has test-only 300-second wait and 120-second stale budgets
  for slow sandbox I/O, plus a 600-second process deadline. It records lock timings in
  its temporary results. The shipped helper retains its 15-second busy deadline and
  10-second stale policy; separate tests still exercise those production limits.
- `test_schema.py`: [`state.schema.json`](../spec/state.schema.json) and the helper agree on
  every fixture in `state/fixtures/`, and the helper's output validates against the schema.

### Notify — `conformance/notify/scenarios.json`

Recorded transcripts checked by [`checker.py`](checker.py): the listing the host gave, each
send with its host result, what receivers did, and the adapter's report. PASS means:

- every live, local, interactive peer (not the sender, a Remote Control or cloud row, a
  subagent, or anything offline) got exactly one message, or two when the first one failed;
- nothing was sent when the state was not saved, and the report said `state transition failed`;
- every message carries the state's generation (and `reset` when the state says so);
- two sessions with the same name were addressed as `name [ref]`;
- only confirmed deliveries are reported as notified; held, refused and failed are listed
  as not notified; one failure never stops the other sends;
- a receiver ignores an older generation, treats the same one as a repeat, and applies a
  newer or `reset` one.

### Sync — `conformance/sync/`

The real generic reference reads isolated state through the same bundled helper. Tests
assert a session started after AFK reconciles before meaningful work, newer generation
applies, repeats do nothing, pushed stale generations are ignored, and reset epochs are
recognized. Missing state after prior state reports reset without inventing availability;
the next explicit transition can restart at generation 1. Checkpoints detect same-generation
recreation and prevent replaying the same reset. Future versions fail without writes.
Sync-only hosts never claim notification or fan-in. AFK age never triggers a transition.

Checker transcripts use last_seen_generation, presence, context and steps. Each step
contains state, action (apply/repeat/ignore-stale/reset-pending), local generation/status/context,
and optionally before_work. sync_only transcripts must not declare sends or requested peers.

### Cross-host — `conformance/cross-host/`

Fixture replay uses the real helpers with AFKSWITCH_STATE_DIR: host A writes g30 AFK,
host B syncs, host C writes g31 back with context, host A syncs. A future initial since
proves clocks do not order transitions. Delayed g30 pushes cannot overwrite g31.
Checker transcripts have initial state and steps with host/op (write/sync/push). Writes
include command/context/state; reconciliation includes action/local and optional state.
Failing examples cover wrong ordering, durable back context, lost event context and stale reads.

### Eval harness — `conformance/evals/`

Deterministic grader checks and a fake CLI exercise repetitions, metadata, timeout and
failure reporting. No real model is run. [Real-model evals](../evals/README.md) are opt-in,
local, and excluded from CI execution.

### Fan-in — `conformance/fan-in/scenarios.json`

PASS means:

- a reply counts only when it is addressed to this session, comes from a session this
  `/back` asked, and starts with `afkswitch-status g<G>` for this generation;
- a session is counted once, even if it answered twice; two sessions with the same name
  stay apart by ref;
- a silent session is "no reply yet", never completed, failed, or agreeing;
- a reply to an earlier `/back` is shown as late and never counted; a reply to another
  session's `/back` is not counted here;
- when anyone needs the human, "Needs you now" comes first; sections keep the fixed order.

Each file has passing **and** failing example transcripts; `test_checker.py` asserts every
example gets the verdict it declares.

## Checking your own adapter

1. State: point `AFKSWITCH_HELPER` at your helper, or port `state/test_state.py`.
2. Sync / cross-host / notify / fan-in: record a run in the transcript shape used by the scenario files
   (`listing`, `sends`, `receivers`, `report`; or `requested`, `replies`, `report`) and run
   `python conformance/checker.py your-recording.json`. It exits 1 on any violation.
3. Declare only capabilities that pass, with notes/evidence in [`adapters/capabilities.json`](../adapters/capabilities.json).

The checker verifies a transcript, not a live host: recording a real run honestly is the
adapter author's job, and [`docs/compatibility.md`](../docs/compatibility.md) lists only
runs that actually happened.
