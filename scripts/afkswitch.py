#!/usr/bin/env python3
"""`afkswitch afk|back|status`: presence from any terminal or OS hotkey, outside any agent.

afk and back are the state helper itself (same arguments, JSON line and exit codes); the
helper stays the only writer. status reads the state and prints one line for a person.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HELPER_PATH = Path(__file__).resolve().parents[1] / "skills/afk/scripts/afkswitch_state.py"
USAGE = "usage: afkswitch (afk | back) [--context TEXT | --context-stdin] | status [--json]"


def load_helper():
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True  # never leave bytecode in an installed copy
        spec = importlib.util.spec_from_file_location("afkswitch_state_cli", HELPER_PATH)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        return helper
    finally:
        sys.dont_write_bytecode = previous


def describe(helper, state: dict) -> str:
    """One line: `AFK since 14:02 (2h 5m) · "sleep" · g31`."""
    if state.get("status") is None:
        return "no presence saved yet · run `afkswitch afk` when you leave"
    since = helper.parse_since(state["since"])
    when = since.astimezone().strftime("%H:%M") if since else state["since"]
    parts = [f"{'AFK' if state['status'] == 'afk' else 'here'} since {when}"]
    if since:
        seconds = int((datetime.now(timezone.utc) - since).total_seconds())
        parts[0] += f" ({helper.format_duration(max(seconds, 0))})"
    if state.get("context"):
        parts.append(json.dumps(state["context"], ensure_ascii=False))
    parts.append(f"g{state['generation']}")
    return " · ".join(parts)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    helper = load_helper()
    if args and args[0] in ("afk", "back"):
        return helper.main(args)
    if args in (["status"], ["status", "--json"]):
        try:
            state = helper.read_command()
        except helper.HelperError as exc:
            print(json.dumps({"ok": False, "error": exc.code, "message": exc.message}))
            return 1
        print(json.dumps(state, ensure_ascii=True) if args[1:] else describe(helper, state))
        return 0
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
