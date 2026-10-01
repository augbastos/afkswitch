#!/usr/bin/env python3
"""Read-only, one-shot lifecycle presence injection. Errors never block the host."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

TAIL_BYTES = 256 * 1024
MARKER = re.compile(r"\A(?:<cross-session-message[^>\n]*>\n)?\[AFKSwitch g([1-9][0-9]*)( reset)?\]\nstatus: (?:afk|available)\ncontext: ")
HELPER_PATH = Path(__file__).resolve().parents[1] / "skills/afk/scripts/afkswitch_state.py"


@lru_cache(maxsize=1)
def load_helper():
    # Imports must not create bytecode in the plugin installation.
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location("afkswitch_state_hook", HELPER_PATH)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        return helper
    finally:
        sys.dont_write_bytecode = previous


def transcript_strings(value):
    """Walk message/attachment values, including JSON encoded in hook stdout."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from transcript_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == "stdout" and isinstance(item, str) and item.startswith("{"):
                try:
                    decoded = json.loads(item)
                except ValueError:
                    pass
                else:
                    yield from transcript_strings(decoded)
            yield from transcript_strings(item)


def last_marker(path):
    """Read at most the transcript tail; no transcript or checkpoint is written."""
    if not path:
        return 0, False
    with Path(path).open("rb") as transcript:
        transcript.seek(0, 2)
        transcript.seek(max(0, transcript.tell() - TAIL_BYTES))
        tail = transcript.read(TAIL_BYTES).decode("utf-8", errors="replace")
    last = None
    for line in tail.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue  # Includes a partial JSONL record at the bounded tail's start.
        for text in transcript_strings(record):
            match = MARKER.match(text)
            if match:
                last = match  # Only the event header; carried context is opaque.
    return (int(last.group(1)), bool(last.group(2))) if last else (0, False)


def response(host: str, event: str, data: dict):
    if not isinstance(data, dict):
        return None
    if host in ("claude", "codex"):
        if event not in ("SessionStart", "UserPromptSubmit"):
            return None
        if event == "SessionStart" and data.get("source") not in ("startup", "clear", "resume", "compact", "fork"):
            return None
    elif host != "agy" or event != "PreInvocation":
        return None
    helper = load_helper()
    prior = helper.load(helper.state_dir() / "state.json")
    state = prior.state
    if state is None or prior.kind == "future":
        return None
    generation = state["generation"]
    reset = False
    if host == "agy":
        if state["status"] != "afk":
            return None
        reset = prior.kind == "v1"
    elif event == "SessionStart" and data.get("source") in ("startup", "clear"):
        if state["status"] != "afk":
            return None
        reset = prior.kind == "v1"
    else:
        seen, seen_reset = last_marker(data.get("transcript_path"))
        reset = generation < seen or (prior.kind == "v1" and not (seen == generation and seen_reset))
        if generation <= seen and not reset:
            return None
    text = helper.core_event(state["status"], generation, state["context"], reset)
    if host == "agy":
        return {"injectSteps": [{"ephemeralMessage": text}]}
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def main(argv=None) -> int:
    try:
        args = sys.argv[1:] if argv is None else argv
        if len(args) != 4 or args[0] != "--host" or args[2] != "--event":
            return 0
        if sys.version_info < (3, 9):
            return 0
        data = json.load(sys.stdin)
        result = response(args[1], args[3], data)
        if result is not None:
            sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
    except (Exception, SystemExit):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
