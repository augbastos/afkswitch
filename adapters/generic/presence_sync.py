#!/usr/bin/env python3
"""One synchronous presence check. Import check(), or invoke `check --last-seen N`."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HELPER_PATH = Path(__file__).resolve().parents[2] / "skills/afk/scripts/afkswitch_state.py"
_spec = importlib.util.spec_from_file_location("afkswitch_state_sync", HELPER_PATH)
helper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helper)


def check(last_seen: int = 0, last_epoch: str | None = None) -> dict:
    """Read the authoritative file; never write it or infer availability from absence.

    epoch is an opaque checkpoint of file identity and validated contents, not an
    ordering signal. Keep it in host/session state alongside last_seen_generation.
    """
    if type(last_seen) is not int or last_seen < 0:
        raise helper.HelperError("invalid_last_seen", "last_seen must be an integer >= 0")
    path = helper.state_dir() / "state.json"
    try:
        # A bounded consistency retry protects the checkpoint from an atomic replacement.
        for _ in range(3):
            try:
                before = path.stat()
            except FileNotFoundError:
                before = None
            prior = helper.load(path)
            try:
                after = path.stat()
            except FileNotFoundError:
                after = None
            if before == after:
                break
        else:
            raise helper.HelperError("state_read_failed", "state changed during the presence check; retry at the next safe boundary")
    except OSError as exc:
        raise helper.HelperError("state_read_failed", f"state read failed: {exc.strerror or exc}")
    if prior.kind == "future":
        raise helper.HelperError("unsupported_state_version", f"unsupported state version {prior.version}")
    state = prior.state
    if state is None:
        epoch = prior.kind
        reset = last_seen > 0 and last_epoch != epoch
        return {"changed": reset, "event": None, "generation": None, "reset": reset, "epoch": epoch}
    identity = [after.st_dev, after.st_ino] if after else []
    epoch = hashlib.sha256(json.dumps([identity, state], sort_keys=True).encode("utf-8")).hexdigest()
    generation = state["generation"]
    # A lower *authoritative disk* generation is a reset, not a stale pushed event.
    reset = ((last_seen > 0 and last_epoch in ("missing", "empty", "malformed")) or
             generation < last_seen or
             (generation == last_seen and last_epoch is not None and last_epoch != epoch) or
             (prior.kind == "v1" and last_epoch != epoch))
    changed = reset or generation > last_seen
    return {"changed": changed,
            "event": helper.core_event(state["status"], generation, state["context"], reset) if changed else None,
            "generation": generation, "reset": reset, "epoch": epoch}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("check")
    command.add_argument("--last-seen", type=int, required=True)
    command.add_argument("--last-epoch")
    args = parser.parse_args(argv)
    try:
        result = check(args.last_seen, args.last_epoch)
    except helper.HelperError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "message": exc.message}))
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
