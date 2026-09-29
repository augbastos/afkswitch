"""Reference checker for the notify and fan-in conformance levels.

Pure functions over a recorded transcript (what the host listed, what was sent, what came
back, and what the adapter reported). No model, host, or network is involved, so any
adapter can record a transcript in this shape and check it.

    python conformance/checker.py conformance/notify/scenarios.json conformance/fan-in/scenarios.json
    python conformance/checker.py my-recording.json

A file holds {"scenarios": [...]}. Each scenario has "kind" ("notify" or "fan-in") and a
"transcript"; see conformance/README.md for the fields. A scenario may declare
"expect": "pass" or "fail" (with the violation codes it must produce in "violations"); the
command exits 1 when any scenario's verdict differs from what it expects, or, when it
declares nothing, when it fails.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ALIVE = {"idle", "busy", "working", "waiting", "running", "active"}
SECTION_ORDER = ["needs_you_now", "completed", "running", "other_blockers", "no_reply", "late"]
_HEADER = re.compile(r"afkswitch-status g(\d+)\s*$")


# ------------------------------------------------------------------ shared rules

def is_target(row: dict, self_name: str) -> bool:
    """A live, local, interactive session other than the sender."""
    return (
        row.get("name") != self_name
        and not row.get("self", False)
        and row.get("kind") == "interactive"
        and row.get("location", "local") == "local"
        and row.get("state") in ALIVE
    )


def address(row: dict, rows: list) -> str:
    """The bare name, or "name [ref]" when another row shares the name."""
    shared = sum(1 for r in rows if r.get("name") == row.get("name")) > 1
    return f"{row['name']} [{row['ref']}]" if shared else row["name"]


def resolve(to: str, targets: dict, rows: list) -> str | None:
    """Map a send's "to" onto a target address; "?ambiguous" for a bare name several rows share."""
    if to in targets:
        return to
    for addr, row in targets.items():
        if to == f"{row['name']} [{row.get('ref')}]":
            return addr  # the ref was not needed, but it is unambiguous
    if sum(1 for r in rows if r.get("name") == to) > 1:
        return "?ambiguous"
    return None


def receiver_action(known: int | None, generation: int, reset: bool) -> str:
    """What a peer does with an incoming AFKSwitch message (spec: Peer messages and generations)."""
    if reset or known is None or generation > known:
        return "apply"
    if generation == known:
        return "repeat"
    return "ignore-stale"


# ------------------------------------------------------------------ notify

def check_notify(t: dict) -> list:
    v = []
    state = t.get("state", {})
    sends = t.get("sends", [])
    report = t.get("report", {})
    rows = t.get("listing", [])
    self_name = t.get("self")

    if not state.get("ok"):
        if sends:
            v.append("SENT_WITHOUT_STATE: a peer was messaged although the state was not saved")
        if not report.get("state_failed") or "state transition failed" not in report.get("message", ""):
            v.append("STATE_FAILURE_NOT_REPORTED: the report must say 'state transition failed'")
        return v + check_receivers(t)

    generation, reset = state.get("generation"), bool(state.get("reset"))
    targets = {address(r, rows): r for r in rows if is_target(r, self_name)}

    by_target = {}
    for s in sends:
        to = resolve(s.get("to"), targets, rows)
        if to == "?ambiguous":
            v.append(f"AMBIGUOUS_TARGET: '{s.get('to')}' is shared by several sessions; send to 'name [ref]'")
            continue
        if to is None:
            v.append(f"NON_TARGET_MESSAGED: '{s.get('to')}' is not a live local interactive peer")
            continue
        by_target.setdefault(to, []).append(s)
        if s.get("generation") != generation or bool(s.get("reset")) != reset:
            v.append(f"WRONG_GENERATION: message to '{to}' carries g{s.get('generation')}"
                     f"{' reset' if s.get('reset') else ''}, state is g{generation}{' reset' if reset else ''}")

    final = {}
    for to, attempts in by_target.items():
        ok_retry = len(attempts) == 2 and attempts[0].get("result") == "failed"
        if len(attempts) > 1 and not ok_retry:
            v.append(f"DUPLICATE_SEND: '{to}' got {len(attempts)} copies (only one retry after a confirmed failure)")
        final[to] = attempts[-1].get("result")

    missed = [a for a in targets if a not in by_target]
    for a in missed:
        v.append(f"TARGET_MISSED: '{a}' was never messaged")
    if missed and any(r == "failed" for r in final.values()):
        v.append("FAILURE_CANCELLED_OTHERS: a failed send stopped later targets")

    delivered = sorted(a for a, r in final.items() if r == "delivered")
    notified = report.get("notified", [])
    not_notified = [n.get("name") for n in report.get("not_notified", [])]
    for a in notified:
        if a not in delivered:
            v.append(f"OVERCLAIMED_DELIVERY: '{a}' reported as notified but the host result was {final.get(a, 'no send')}")
    for a in targets:
        if a not in delivered and a not in not_notified:
            v.append(f"UNREPORTED_FAILURE: '{a}' does not know and is not listed as not notified")
    if sorted(set(notified)) != sorted(notified):
        v.append("DUPLICATE_IN_REPORT: a session is listed twice as notified")
    if report.get("discovered") != len(targets):
        v.append(f"WRONG_COUNT: discovered {report.get('discovered')}, expected {len(targets)}")
    if report.get("generation") != generation:
        v.append(f"REPORT_GENERATION: report shows g{report.get('generation')}, state is g{generation}")
    return v + check_receivers(t)


def check_receivers(t: dict) -> list:
    v = []
    for r in t.get("receivers", []):
        msg = r.get("message", {})
        want = receiver_action(r.get("known_generation"), msg.get("generation"), bool(msg.get("reset")))
        if r.get("action") != want:
            v.append(f"RECEIVER_WRONG_ACTION: '{r.get('session')}' knew g{r.get('known_generation')}, got "
                     f"g{msg.get('generation')}{' reset' if msg.get('reset') else ''}: must {want}, did {r.get('action')}")
    return v


# ------------------------------------------------------------------ fan-in

def parse_reply(text: str) -> dict | None:
    lines = [line.strip() for line in text.strip().splitlines()]
    if not lines:
        return None
    m = _HEADER.fullmatch(lines[0])
    if not m:
        return None
    fields = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip().lower()] = value.strip()
    return {"generation": int(m.group(1)), "fields": fields}


def has_content(value: str | None) -> bool:
    return bool(value) and value.strip().lower().rstrip(".") not in {"none", "nothing", "n/a", "-"}


def check_fan_in(t: dict) -> list:
    v = []
    self_name, generation = t.get("self"), t.get("generation")
    requested = t.get("requested", [])
    report = t.get("report", {})

    counted, blockers, late = {}, set(), []
    for reply in t.get("replies", []):
        parsed = parse_reply(reply.get("text", ""))
        sender = reply.get("from")
        if reply.get("to") != self_name:
            continue  # answered another asker: not ours to count or show
        if sender not in requested or parsed is None or parsed["generation"] != generation:
            late.append(sender)
            continue
        counted.setdefault(sender, parsed)
    for sender, parsed in counted.items():
        if has_content(parsed["fields"].get("needs-human")):
            blockers.add(sender)

    replied = report.get("replied", [])
    if len(set(replied)) != len(replied):
        v.append("DUPLICATE_REPLY: a session is counted more than once")
    for s in replied:
        if s not in counted:
            v.append(f"PHANTOM_REPLY: '{s}' is counted but sent no matching reply for g{generation}")
    for s in counted:
        if s not in replied:
            v.append(f"MISSING_REPLY: '{s}' replied but is not in the report")
    expected_silent = [s for s in requested if s not in counted]
    if sorted(report.get("no_reply", [])) != sorted(expected_silent):
        v.append(f"NO_REPLY_MISMATCH: no reply yet should be {sorted(expected_silent)}, got {sorted(report.get('no_reply', []))}")
    for s in expected_silent:
        for section in ("completed", "needs_you_now", "running", "other_blockers"):
            if s in report.get(section, []):
                v.append(f"SILENCE_MISREAD: '{s}' has not replied but appears under {section}")
    for s in late:
        if s not in report.get("late", []):
            v.append(f"LATE_REPLY_UNREPORTED: '{s}' answered an earlier /back or without the header; show it as late")
    sections = report.get("sections", [])
    if [s for s in SECTION_ORDER if s in sections] != sections:
        v.append(f"SECTION_ORDER: sections {sections} are not in the order {SECTION_ORDER}")
    if blockers:
        if not sections or sections[0] != "needs_you_now":
            v.append("HUMAN_BLOCKER_NOT_FIRST: 'Needs you now' must come first")
        for s in blockers:
            if s not in report.get("needs_you_now", []):
                v.append(f"HUMAN_BLOCKER_MISSING: '{s}' needs the human but is not under Needs you now")
    if report.get("requested_count") != len(requested):
        v.append(f"WRONG_COUNT: status requested from {report.get('requested_count')}, expected {len(requested)}")
    return v


# ------------------------------------------------------------------ driver

CHECKS = {"notify": check_notify, "fan-in": check_fan_in}


def check(scenario: dict) -> list:
    return CHECKS[scenario["kind"]](scenario["transcript"])


def verdict_matches(scenario: dict, violations: list) -> bool:
    expect = scenario.get("expect", "pass")
    if expect == "pass":
        return not violations
    codes = {x.split(":", 1)[0] for x in violations}
    return bool(violations) and set(scenario.get("violations", [])) <= codes


def main(paths: list) -> int:
    bad = 0
    for path in paths:
        for scenario in json.loads(Path(path).read_text(encoding="utf-8"))["scenarios"]:
            violations = check(scenario)
            ok = verdict_matches(scenario, violations)
            bad += not ok
            label = "PASS" if not violations else "FAIL"
            expect = scenario.get("expect", "pass")
            print(f"{'ok ' if ok else 'BAD'} {label:4} (expected {expect}) {scenario['kind']}/{scenario['name']}")
            for x in violations:
                print(f"      {x}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
