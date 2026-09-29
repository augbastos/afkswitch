#!/usr/bin/env python3
"""AFKSwitch state helper: the only code that reads and writes ~/.afkswitch/state.json.

    afkswitch_state.py afk [--context TEXT | --context-stdin]
    afkswitch_state.py back
    afkswitch_state.py read

Prints exactly one JSON line (ASCII-escaped) and exits 0 on success, 1 on a reported
error, 2 on a usage error. Standard library only, Python 3.9+. No network, no background
process: it runs, prints, and exits.

The rules it implements are in spec/presence.md ("State protocol v2"). In short: validate
input, take a small O_EXCL lock file, read the prior state, write the new state to a temp
file in the same directory (flush + fsync + os.replace), re-read and validate it, release
the lock, and only then report success. Callers notify peers only after an "ok": true.

AFKSWITCH_STATE_DIR overrides the state directory (used by the conformance tests).
"""
from __future__ import annotations

import sys

if sys.version_info < (3, 9):  # pragma: no cover - checked on the oldest interpreters only
    sys.stdout.write('{"ok": false, "error": "python_too_old", '
                     '"message": "state helper unavailable (Python 3.9 or newer is required)"}\n')
    sys.exit(1)

import json
import os
import random
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

STATE_VERSION = 2
MAX_CONTEXT = 2048  # Unicode code points, as JSON Schema maxLength counts them.
STATUSES = ("available", "afk")
LOCK_STALE_SECONDS = 10.0  # A transition holds the lock for milliseconds; older means a crash.
LOCK_WAIT_SECONDS = 15.0   # Longer than the stale timeout, so a crashed holder never blocks us.
IS_WINDOWS = os.name == "nt"

_SINCE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})")


class HelperError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------- paths and time

def state_dir() -> Path:
    override = os.environ.get("AFKSWITCH_STATE_DIR")
    return Path(override) if override else Path.home() / ".afkswitch"


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def parse_since(value) -> datetime | None:
    """ISO 8601 date-time with seconds and an explicit offset; None when invalid."""
    if not isinstance(value, str) or not _SINCE.fullmatch(value):
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    if "." in text:  # fromisoformat before 3.11 accepts only 3 or 6 fraction digits
        head, rest = text.split(".", 1)
        digits, offset = rest[:-6], rest[-6:]
        text = f"{head}.{(digits + '000000')[:6]}{offset}"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


# ---------------------------------------------------------------- validation

def context_problem(context) -> str | None:
    if context is None:
        return None
    if not isinstance(context, str):
        return "context must be text or null"
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in context):
        return "context is not valid Unicode text"
    if len(context) > MAX_CONTEXT:
        return (f"context is {len(context)} characters; the limit is {MAX_CONTEXT}. "
                "Nothing was saved; shorten it and try again")
    return None


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def problems_v2(obj) -> list:
    if not isinstance(obj, dict):
        return ["state is not a JSON object"]
    found = []
    keys = {"version", "status", "since", "context", "generation"}
    if set(obj) != keys:
        found.append(f"keys must be exactly {sorted(keys)}")
    if obj.get("version") != STATE_VERSION or not _is_int(obj.get("version")):
        found.append("version must be 2")
    if obj.get("status") not in STATUSES:
        found.append("status must be available or afk")
    if parse_since(obj.get("since")) is None:
        found.append("since must be ISO 8601 with an offset")
    problem = context_problem(obj.get("context"))
    if problem:
        found.append(problem)
    if obj.get("status") == "available" and obj.get("context") is not None:
        found.append("an available state has no context")
    generation = obj.get("generation")
    if not _is_int(generation) or generation < 1:
        found.append("generation must be an integer >= 1")
    return found


def problems_v1(obj) -> list:
    if not isinstance(obj, dict):
        return ["state is not a JSON object"]
    found = []
    if set(obj) != {"version", "status", "since", "context"}:
        found.append("keys must be exactly version, status, since, context")
    if obj.get("version") != 1 or not _is_int(obj.get("version")):
        found.append("version must be 1")
    if obj.get("status") not in STATUSES:
        found.append("status must be available or afk")
    if parse_since(obj.get("since")) is None:
        found.append("since must be ISO 8601 with an offset")
    problem = context_problem(obj.get("context"))
    if problem:
        found.append(problem)
    return found


# ---------------------------------------------------------------- reading

class Prior:
    """What was on disk: kind is missing, empty, malformed, v1, v2 or future."""

    def __init__(self, kind: str, state: dict | None = None, raw: bytes = b"",
                 version=None, problem: str = ""):
        self.kind = kind
        self.state = state  # a valid v2 dict (v1 already migrated) or None
        self.raw = raw
        self.version = version
        self.problem = problem


def _read_bytes(path: Path) -> bytes | None:
    for attempt in range(20):
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None
        except PermissionError:
            # Windows refuses to open a file for the instant another process replaces it.
            if not IS_WINDOWS or attempt == 19:
                raise
            time.sleep(0.02)
    return None


def load(path: Path) -> Prior:
    raw = _read_bytes(path)
    if raw is None:
        return Prior("missing")
    if raw.startswith(b"\xef\xbb\xbf"):
        raw_text = raw[3:]
    else:
        raw_text = raw
    try:
        text = raw_text.decode("utf-8")
    except UnicodeDecodeError:
        return Prior("malformed", raw=raw, problem="not UTF-8 text")
    if not text.strip():
        return Prior("empty", raw=raw)
    try:
        obj = json.loads(text)
    except ValueError:
        return Prior("malformed", raw=raw, problem="not valid JSON")
    version = obj.get("version") if isinstance(obj, dict) else None
    if _is_int(version) and version > STATE_VERSION:
        return Prior("future", raw=raw, version=version)
    if version == 1 and _is_int(version):
        found = problems_v1(obj)
        if found:
            return Prior("malformed", raw=raw, problem="; ".join(found))
        migrated = {
            "version": STATE_VERSION,
            "status": obj["status"],
            "since": obj["since"],
            "context": obj["context"] if obj["status"] == "afk" else None,
            "generation": 1,
        }
        return Prior("v1", state=migrated, raw=raw, version=1)
    found = problems_v2(obj)
    if found:
        return Prior("malformed", raw=raw, problem="; ".join(found))
    return Prior("v2", state=obj, raw=raw, version=STATE_VERSION)


# ---------------------------------------------------------------- writing

def ensure_dir(directory: Path) -> None:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not IS_WINDOWS:
        try:  # best effort: narrow to the owner, never widen
            os.chmod(directory, 0o700)
        except OSError:
            pass
    # On Windows the folder inherits the user profile's ACL; nothing is changed.


@contextmanager
def locked(directory: Path):
    """Hold state.json.lock (created with O_EXCL) for the whole transition."""
    path = directory / "state.json.lock"
    token = f"{os.getpid()} {uuid.uuid4().hex}\n".encode("ascii")
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    refused_since = None
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            refused_since = None
            if _lock_is_stale(path):
                _break_stale_lock(path)
                continue
        except PermissionError:
            # Windows reports a lock file that is being deleted as "access denied".
            # A real refusal (read-only sandbox) persists and is raised after a second.
            if not IS_WINDOWS:
                raise
            refused_since = refused_since or time.monotonic()
            if time.monotonic() - refused_since > 1.0:
                raise
        else:
            try:
                os.write(fd, token)
            finally:
                os.close(fd)
            break
        if time.monotonic() > deadline:
            raise HelperError("state_transition_failed",
                              "state transition failed: state is busy (lock held by another /afk or /back)")
        time.sleep(0.002 + random.random() * 0.01)
    try:
        yield
    finally:
        for attempt in range(50):
            try:
                os.unlink(path)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                if not IS_WINDOWS or attempt == 49:
                    raise
                time.sleep(0.01)


def _lock_is_stale(path: Path) -> bool:
    try:
        return time.time() - os.stat(path).st_mtime > LOCK_STALE_SECONDS
    except OSError:
        return False


def _break_stale_lock(path: Path) -> None:
    # Rename first so only one breaker can take a given stale file.
    aside = path.with_name(f"{path.name}.stale-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    try:
        os.rename(path, aside)
        os.unlink(aside)
    except OSError:
        pass


def replace_file(src: Path, dst: Path) -> None:
    """os.replace: rename(2) on POSIX; MoveFileExW(MOVEFILE_REPLACE_EXISTING) on Windows.

    On Windows the replace fails with "access denied" while another process has the target
    open without delete sharing (a reader, an indexer, antivirus), so it is retried briefly.
    """
    for attempt in range(50):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not IS_WINDOWS or attempt == 49:
                raise
            time.sleep(0.02)


def write_atomic(path: Path, state: dict) -> None:
    data = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        replace_file(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if not IS_WINDOWS:  # best effort: make the rename itself durable
        try:
            dfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass


def write_backup(path: Path, raw: bytes) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for n in range(1000):
        candidate = path.with_name(f"{path.name}.corrupt-{stamp}" + (f"-{n}" if n else ""))
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        return candidate
    raise OSError("could not choose a backup file name")


# ---------------------------------------------------------------- commands

def public(state: dict | None) -> dict | None:
    if state is None:
        return None
    return {k: state[k] for k in ("status", "generation", "since", "context")}


def afk_lasted(previous: dict | None) -> tuple:
    if not previous or previous["status"] != "afk":
        return None, None
    started = parse_since(previous["since"])
    seconds = int((datetime.now(timezone.utc) - started).total_seconds()) if started else -1
    if seconds < 0:  # a clock moved backwards: informative only, so say nothing
        return None, None
    return format_duration(seconds), seconds


def read_command() -> dict:
    path = state_dir() / "state.json"
    try:
        prior = load(path)
    except OSError as exc:
        raise HelperError("state_read_failed", f"state read failed: {exc.strerror or exc}")
    if prior.kind == "future":
        raise HelperError("unsupported_state_version", f"unsupported state version {prior.version}")
    state = prior.state
    return {
        "ok": True, "command": "read",
        "status": state["status"] if state else None,
        "generation": state["generation"] if state else None,
        "since": state["since"] if state else None,
        "context": state["context"] if state else None,
        "found": prior.kind, "migrated": prior.kind == "v1",
        "malformed": prior.kind == "malformed", "state_file": str(path),
    }


def transition(command: str, context: str | None = None) -> dict:
    # 1. Validate input before touching anything.
    if command == "afk":
        if context == "":
            context = None  # an empty context is no context
        problem = context_problem(context)
        if problem:
            raise HelperError("context_too_long" if len(context or "") > MAX_CONTEXT else "invalid_context",
                              problem)
    directory = state_dir()
    path = directory / "state.json"
    try:
        ensure_dir(directory)
        with locked(directory):
            prior = load(path)
            if prior.kind == "future":
                raise HelperError("unsupported_state_version", f"unsupported state version {prior.version}")
            previous = prior.state
            base_generation = previous["generation"] if previous else 0
            if command == "afk":
                same = previous is not None and previous["status"] == "afk" and previous["context"] == context
                target = {"status": "afk", "context": context}
            else:
                same = previous is not None and previous["status"] == "available"
                target = {"status": "available", "context": None}
            if same:
                new = dict(previous)
            else:
                new = {"version": STATE_VERSION, "status": target["status"], "since": now_iso(),
                       "context": target["context"], "generation": base_generation + 1}
            # 2. Write atomically (a v1 file is rewritten as v2 even when nothing else changes).
            backup = None
            if prior.kind != "v2" or not same:
                if prior.kind == "malformed":
                    backup = write_backup(path, prior.raw)
                write_atomic(path, new)
            # 3. Re-read and validate before anyone is told.
            check = load(path)
            if check.kind != "v2" or check.state != new:
                raise HelperError("state_transition_failed",
                                  "state transition failed: the saved state did not read back as written")
    except HelperError:
        raise
    except PermissionError as exc:
        raise HelperError("state_transition_failed",
                          f"state transition failed: write refused ({exc.filename or directory})")
    except OSError as exc:
        raise HelperError("state_transition_failed", f"state transition failed: {exc.strerror or exc}")
    lasted, lasted_seconds = afk_lasted(previous) if command == "back" else (None, None)
    return {
        "ok": True, "command": command, "changed": not same,
        "status": new["status"], "generation": new["generation"],
        "since": new["since"], "context": new["context"],
        "previous": public(previous),
        "afk_lasted": lasted, "afk_lasted_seconds": lasted_seconds,
        "migrated": prior.kind == "v1",
        "reset": prior.kind != "v2",
        "backup": str(backup) if backup else None,
        "state_file": str(path),
    }


USAGE = "usage: afkswitch_state.py afk [--context TEXT | --context-stdin] | back | read"


def parse(argv: list) -> tuple:
    if not argv or argv[0] not in ("afk", "back", "read"):
        raise HelperError("usage", USAGE)
    command, rest = argv[0], list(argv[1:])
    context = None
    if command != "afk":
        if rest:
            raise HelperError("usage", USAGE)
        return command, None
    if not rest:
        return command, None
    if rest[0] == "--context" and len(rest) == 2:
        context = rest[1]
    elif rest[0].startswith("--context=") and len(rest) == 1:
        context = rest[0][len("--context="):]
    elif rest == ["--context-stdin"]:
        data = sys.stdin.buffer.read()
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
        try:
            context = data.decode("utf-8")
        except UnicodeDecodeError:
            raise HelperError("invalid_context", "context is not valid UTF-8 text")
        # A heredoc or pipe adds one final newline; drop exactly that one.
        if context.endswith("\r\n"):
            context = context[:-2]
        elif context.endswith("\n"):
            context = context[:-1]
    else:
        raise HelperError("usage", USAGE)
    return command, context


def run(argv: list) -> dict:
    command, context = parse(argv)
    if command == "read":
        return read_command()
    return transition(command, context)


def main(argv: list | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        result = run(args)
        code = 0
    except HelperError as exc:
        result = {"ok": False, "command": args[0] if args else None, "error": exc.code, "message": exc.message}
        code = 2 if exc.code == "usage" else 1
    sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
