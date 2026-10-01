# Opt-in local model evals

Five synthetic presence scenarios, repeated N times through a headless host CLI you
choose. This is a small stdlib smoke harness, not a platform or semantic proof. No real
models run in CI or by default. It installs nothing and requires no paid service; your
chosen host/model may have its own cost and authentication requirements.

```text
python evals/run.py --host 'claude -p {prompt}' --host-version <version> --model <model> -n 3
python evals/run.py --host 'codex exec {prompt}' --host-version <version> --model <model> -n 3
```

The host template uses POSIX-style quoting on every OS and is executed directly with
shell=false. `{prompt}` must be an entire argument; without it the prompt is appended,
so `--host 'claude -p'` also works. A local headless model CLI is equally suitable. Quoted
executable paths work; use forward slashes on Windows. No shell pipelines or expansion.

Prompts ask for synthetic reasoning only: no tools, actual presence transitions, peer
messages or production changes. Choose a host configuration that restricts tool execution;
the harness cannot enforce the host's permissions. Authenticate separately before opting in;
the harness uses closed stdin and a per-run timeout, never handles credentials. Do not put
secrets in the command template or prompts. Supply host version and model explicitly;
omitted metadata is unknown, never inferred. Set `--timeout`, `--output` or `--scenarios`
when needed. Each trial starts a fresh CLI invocation without resume arguments.

Results JSON records host/version/model, every trial's output, exit code, regex failures,
and aggregate pass_rate. Outputs stay local (default `evals/results.json`); review them
before sharing. Nonzero host exits, unavailable commands and timeouts fail their trial.
The harness exits 0 only when all trials pass, otherwise 1. Invalid input is a usage error.

Scenarios: physical blocker defers only its step, presence is not permission, stale push
ignored, return context preserved, and missing reply never becomes invented peer status.
Deterministic required/forbidden regex checks are deliberately limited: a pass establishes
only matching output on these prompts, not correctness on every conversation.
Conformance tests exercise the grader and harness using a fake CLI, never a real model.
