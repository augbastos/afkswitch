"""Runs interleaved /afk and /back transitions in one process for the concurrency tests.

    python concurrency_worker.py <helper> <worker id> <count> <start at (epoch seconds)> [--no-lock]

Prints one JSON result per transition. A short sleep inside every write widens the window
between reading the prior state and replacing it, so a missing lock shows up reliably;
--no-lock replaces the lock with a no-op (the mutation check: the tests must then fail).
"""
import contextlib
import importlib.util
import json
import os
import random
import sys
import time

helper_path, worker, count, start_at = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
spec = importlib.util.spec_from_file_location("afkswitch_state", helper_path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

if os.name == "nt":
    # Stress-only budget: slow sandbox I/O can queue all 60 fsync writes. Keep the
    # production helper's 15-second policy and stale-lock handling unchanged.
    helper.LOCK_WAIT_SECONDS = 300.0
    helper.LOCK_STALE_SECONDS = 120.0

real_locked = helper.locked
timings = {}


@contextlib.contextmanager
def measured_lock(directory):
    requested = time.monotonic()
    with real_locked(directory):
        entered = time.monotonic()
        timings["test_lock_wait_seconds"] = entered - requested
        try:
            yield
        finally:
            timings["test_lock_held_seconds"] = time.monotonic() - entered


helper.locked = measured_lock

real_write = helper.write_atomic


def slow_write(path, state):
    time.sleep(0.003)
    real_write(path, state)


helper.write_atomic = slow_write
if "--no-lock" in sys.argv:
    helper.locked = lambda directory: contextlib.nullcontext()

while time.time() < start_at:
    time.sleep(0.001)

rng = random.Random(worker)
for i in range(count):
    args = ["afk", "--context", f"worker {worker} step {i}"] if i % 2 == 0 else ["back"]
    try:
        result = helper.run(args)
    except helper.HelperError as exc:
        result = {"ok": False, "error": exc.code, "message": exc.message}
    except Exception as exc:  # the mutation run may hit raw OS errors; report, don't crash
        result = {"ok": False, "error": type(exc).__name__, "message": str(exc)}
    result.update(timings)
    print(json.dumps(result), flush=True)
    time.sleep(rng.random() * 0.004)
