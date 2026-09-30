#!/usr/bin/env python3
"""Opt-in local host CLI evaluation. No model is started unless the user invokes this."""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

SCENARIOS = Path(__file__).with_name("scenarios.json")


def grade(text: str, checks: dict) -> dict:
    """Deterministic text checks; this is a smoke eval, not a semantic quality claim."""
    flags = re.IGNORECASE | re.MULTILINE
    missing = [pattern for pattern in checks.get("required", []) if not re.search(pattern, text, flags)]
    forbidden = [pattern for pattern in checks.get("forbidden", []) if re.search(pattern, text, flags)]
    return {"passed": not missing and not forbidden, "missing": missing, "forbidden": forbidden}


def command(template: str, prompt: str) -> list:
    """POSIX-style template quoting on every OS; run tokens directly, never a shell."""
    tokens = shlex.split(template)
    if not tokens:
        raise ValueError("host command must not be empty")
    if any("{prompt}" in token and token != "{prompt}" for token in tokens):
        raise ValueError("{prompt} must be a whole argument")
    if "{prompt}" in tokens:
        return [prompt if token == "{prompt}" else token for token in tokens]
    return tokens + [prompt]


def evaluate(template: str, scenarios: list, repeats: int, timeout: float) -> list:
    results = []
    for scenario in scenarios:
        for trial in range(1, repeats + 1):
            error, output, exit_code = None, "", None
            try:
                proc = subprocess.run(command(template, scenario["prompt"]), capture_output=True,
                                      text=True, encoding="utf-8", errors="replace", timeout=timeout,
                                      stdin=subprocess.DEVNULL, shell=False)
                output, exit_code = proc.stdout, proc.returncode
                if exit_code:
                    error = f"host exited {exit_code}"
            except subprocess.TimeoutExpired:
                error = "host timed out"
            except OSError as exc:
                error = f"host unavailable: {exc.strerror or type(exc).__name__}"
            verdict = grade(output, scenario["checks"])
            verdict["passed"] = verdict["passed"] and error is None
            results.append({"scenario": scenario["id"], "trial": trial, "exit_code": exit_code,
                            "error": error, "output": output, **verdict})
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Headless CLI template, e.g. 'claude -p {prompt}'")
    parser.add_argument("--host-version", default="unknown", help="Version supplied by the operator, never guessed")
    parser.add_argument("--model", default="unknown", help="Model supplied by the operator, never guessed")
    parser.add_argument("-n", "--repeats", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS)
    parser.add_argument("--output", type=Path, default=Path("evals/results.json"))
    args = parser.parse_args(argv)
    if args.repeats < 1 or args.timeout <= 0:
        parser.error("repeats and timeout must be positive")
    try:
        command(args.host, "validate template")
        scenarios = json.loads(args.scenarios.read_text(encoding="utf-8"))["scenarios"]
        if not scenarios:
            raise ValueError("scenarios must not be empty")
        for scenario in scenarios:
            if not scenario.get("checks", {}).get("required"):
                raise ValueError("every scenario must have required checks")
            for pattern in scenario["checks"].get("required", []) + scenario["checks"].get("forbidden", []):
                re.compile(pattern)
    except (OSError, ValueError, KeyError, re.error) as exc:
        parser.error(str(exc))
    results = evaluate(args.host, scenarios, args.repeats, args.timeout)
    passed = sum(result["passed"] for result in results)
    report = {"host": args.host, "version": args.host_version, "model": args.model,
              "repeats": args.repeats, "passed": passed, "total": len(results),
              "pass_rate": passed / len(results), "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "passed": passed, "total": len(results), "pass_rate": report["pass_rate"]}))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
