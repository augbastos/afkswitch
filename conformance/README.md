# AFKSwitch conformance

Model-independent checks for the three capability levels in
[`spec/presence.md`](../spec/presence.md). Nothing here starts a host, calls a model, or
touches your real `~/.afkswitch`.

## Run it

```text
python -m pip install pytest jsonschema     # jsonschema is optional; without it the schema checks skip
python -m pytest conformance                # everything below
python conformance/checker.py conformance/notify/scenarios.json conformance/fan-in/scenarios.json
```

Python 3.9 or newer. CI runs the same commands on Linux, Windows, and macOS.

## What PASS means, per level

### State-only — `conformance/state/`

Executable tests against the state helper (by default the reference one,
`skills/afk/scripts/afkswitch_state.py`; set `AFKSWITCH_HELPER` to test another
command-compatible script). Each test uses its own temporary directory through
`AFKSWITCH_STATE_DIR`. PASS means all of these hold:

- `/afk` and `/back` write a valid version 2 state, creating missing parent directories.
- Repeating a command is idempotent: `since` and `generation` stay the same.
- Every durable transition raises `generation` by exactly one.
- Context of 0, 1 and 2048 code points (ASCII, accented, emoji, multi-line) is kept
  verbatim; 2049 is rejected with a clear message and nothing is written.
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
2. Notify / fan-in: record a real run in the transcript shape used by the scenario files
   (`listing`, `sends`, `receivers`, `report`; or `requested`, `replies`, `report`) and run
   `python conformance/checker.py your-recording.json`. It exits 1 on any violation.
3. Declare only the levels that pass, in [`adapters/capabilities.json`](../adapters/capabilities.json).

The checker verifies a transcript, not a live host: recording a real run honestly is the
adapter author's job, and [`docs/compatibility.md`](../docs/compatibility.md) lists only
runs that actually happened.
