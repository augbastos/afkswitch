#!/usr/bin/env python3
"""Read-only, one-shot presence hooks: lifecycle injection, and declining approval prompts while away.

Errors never block the host: any failure prints nothing, which leaves the host's own flow unchanged.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

# Tail sizes tried in order; a wider one is read only when the narrower one holds no marker.
WINDOWS = (256 * 1024, 4 * 1024 * 1024, 64 * 1024 * 1024)
NEEDLE = b"[AFKSwitch g"
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
    last = None
    with Path(path).open("rb") as transcript:
        size = transcript.seek(0, 2)
        for window in WINDOWS:
            last, cut = None, False
            transcript.seek(max(0, size - window))
            # Split on LF only: str.splitlines() would also cut a record at a raw U+2028.
            for line in transcript.read(window).split(b"\n"):
                if NEEDLE not in line:
                    continue  # Skips JSON parsing for almost every record.
                try:
                    record = json.loads(line.decode("utf-8", errors="replace"))
                except ValueError:
                    cut = True  # A marker record cut at the window's start: look wider.
                    continue
                for text in transcript_strings(record):
                    match = MARKER.match(text)
                    if match:
                        last = match  # Only the event header; carried context is opaque.
            if (last and not cut) or window >= size:
                break
    return (int(last.group(1)), bool(last.group(2))) if last else (0, False)


# PostToolUse runs after every tool call. It exists for a switch flipped during a running
# turn, so it skips the transcript scan unless the state changed within this window.
RECENT_SECONDS = 600


def recent(helper, since) -> bool:
    changed = helper.parse_since(since)
    return changed is not None and (datetime.now(timezone.utc) - changed).total_seconds() <= RECENT_SECONDS


GUIDANCE = re.compile(r"```text\n(.*?)```", re.S)


def guidance(status: str, generation: int) -> str:
    """The skill's own guidance block (keep working while away; present queued decisions on
    return), so a session learning by hook is told what a pushed message tells it. The /back
    status request is left out: a hook has no one to report to. Any problem: no guidance."""
    try:
        skill = "afk" if status == "afk" else "back"
        text = (HELPER_PATH.parents[2] / skill / "references/message.md").read_text("utf-8")
        blocks = GUIDANCE.findall(text.replace("\r\n", "\n"))
        if len(blocks) < 2:
            return ""
        block = blocks[1].replace("<G>", str(generation)).split("\nAt your next natural pause, reply to")[0]
        return "\n" + block.rstrip("\n")
    except (OSError, UnicodeDecodeError):
        return ""


DECLINED = ("AFKSwitch: the human is away, so nobody can answer this approval prompt. It was declined "
            "instead of leaving the session waiting. Do not retry it and do not look for another way to "
            "do the same thing. Record this step as deferred for the human and continue with work that "
            "needs no approval.")


# The helper run by /afk and /back: a Python interpreter, the helper's path, then afk, back or read.
# It may start the command or follow a single pipe (stdin carries the context).
# The interpreter may carry a path, with spaces only inside quotes.
_PYTHON = r"""(?:python3?|py)(?:\.exe)?"""
HELPER_CALL = re.compile(
    r"""(?:^|\|)\s*(?:&\s*)?"""
    rf"""(?:"[^"]*[\\/]{_PYTHON}"|'[^']*[\\/]{_PYTHON}'|(?:[^"'\s|]*[\\/])?{_PYTHON})\s+(?:-3\s+)?"""
    r"""["']?[^"'|;&\n]*afkswitch_state\.py["']?\s+(?:afk|back|read)(?:\s|$)""")
QUOTED = re.compile(r"""'[^']*'|"(?:[^"\\]|\\.)*\"""")
# Outside quoted text (the context), any of these would run a second command.
CHAINED = re.compile(r"[;\n`]|&&|\|\||\$\(|(?<!^)&")


def is_helper_command(command: str) -> bool:
    """True only for the state helper's own run, with nothing chained before or after it."""
    if not HELPER_CALL.search(command):
        return False
    bare = QUOTED.sub("''", command).strip()
    if bare.startswith("&"):
        bare = bare[1:]  # PowerShell's call operator
    return not CHAINED.search(bare) and bare.count("|") <= 1


def decline_prompt(data: dict):
    """While AFK, answer the host's approval prompt with "not now". It never grants anything.

    Any doubt (no state, unreadable or future state, the opt-out) leaves the prompt as it is.
    """
    if os.environ.get("AFKSWITCH_KEEP_PROMPTS", "").strip().lower() in ("1", "true", "yes"):
        return None  # for people who approve prompts remotely while away
    if data.get("tool_name") == "AskUserQuestion":
        # A question to the human grants nothing: it waits for them instead of being declined, so a
        # session with nothing else to do stays on the question rather than ending without it.
        return None
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if isinstance(command, str) and is_helper_command(command):
        # /back and /afk run the state helper: declining that would lock the human out of
        # returning. The prompt is only left as it is, never approved. A command that merely
        # mentions the helper, or chains another command onto it, is declined like any other.
        return None
    helper = load_helper()
    prior = helper.load(helper.state_dir() / "state.json")
    if prior.state is None or prior.kind == "future" or prior.state["status"] != "afk":
        return None
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                   "decision": {"behavior": "deny", "message": DECLINED, "interrupt": False}}}


# How a host learns presence, per event:
#   transcript - the host keeps a transcript: tell once per generation, found by its marker
#                (and return to "available" is told too).
#   start      - a new session: tell only while away; nothing to remember.
#   ephemeral  - the text is not kept between calls: tell on every call while away, the short
#                event only (the guidance is about 1 KB and would repeat on every model call).
# SessionStart (claude, codex) is "start" for a fresh session and "transcript" for one that
# continues an old conversation (resume, compact, fork).
TRANSCRIPT, START, EPHEMERAL, BY_SOURCE = "transcript", "start", "ephemeral", "by-source"
_CLAUDE_STYLE = {"SessionStart": BY_SOURCE, "UserPromptSubmit": TRANSCRIPT, "PostToolUse": TRANSCRIPT}
HOSTS = {
    "claude": _CLAUDE_STYLE,
    "codex": _CLAUDE_STYLE,
    "agy": {"PreInvocation": EPHEMERAL},
    "hermes": {"pre_llm_call": EPHEMERAL},
    # Cursor and Copilot stay start-only until a live test shows the marker lands in their
    # transcript; without it, every later event would repeat the notice.
    "cursor": {"sessionStart": START},
    "copilot": {"sessionStart": START},
}


def output(host: str, event: str, text: str) -> dict:
    """Each host's own way to add context, as its hook docs define it."""
    if host == "agy":
        return {"injectSteps": [{"ephemeralMessage": text}]}
    if host == "hermes":
        return {"context": text}
    if host == "cursor":
        return {"additional_context": text}
    if host == "copilot":
        return {"additionalContext": text}
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def response(host: str, event: str, data):
    if host == "claude" and event == "PermissionRequest":
        return decline_prompt(data) if isinstance(data, dict) else None
    mode = HOSTS.get(host, {}).get(event)
    if mode is None:
        return None
    if mode == BY_SOURCE:
        source = data.get("source") if isinstance(data, dict) else None
        mode = START if source in ("startup", "clear") else TRANSCRIPT if source in ("resume", "compact", "fork") else None
        if mode is None:
            return None
    if mode == TRANSCRIPT and not isinstance(data, dict):
        return None
    helper = load_helper()
    prior = helper.load(helper.state_dir() / "state.json")
    state = prior.state
    if state is None or prior.kind == "future":
        return None
    generation = state["generation"]
    if event == "PostToolUse" and not recent(helper, state["since"]):
        return None  # an older change already reached this session at a prompt or start
    if mode == TRANSCRIPT:
        seen, seen_reset = last_marker(data.get("transcript_path"))
        reset = generation < seen or (prior.kind == "v1" and not (seen == generation and seen_reset))
        if generation <= seen and not reset:
            return None
    else:
        if state["status"] != "afk":
            return None
        reset = prior.kind == "v1"
    text = helper.core_event(state["status"], generation, state["context"], reset)
    if mode != EPHEMERAL:
        text += guidance(state["status"], generation)
    return output(host, event, text)


def main(argv=None) -> int:
    try:
        args = sys.argv[1:] if argv is None else argv
        if len(args) != 4 or args[0] != "--host" or args[2] != "--event":
            return 0
        if sys.version_info < (3, 9):
            return 0
        try:
            data = json.load(sys.stdin)
        except ValueError:
            data = None  # start and ephemeral hosts need no payload; the others then do nothing
        result = response(args[1], args[3], data)
        if result is not None:
            sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
    except (Exception, SystemExit):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
