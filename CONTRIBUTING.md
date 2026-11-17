# Contributing to AFKSwitch

AFKSwitch should stay small.

## Design rule

**Reuse native host capabilities before building infrastructure.**

A new adapter should first ask:

1. Can the host persist small local state?
2. Can it discover peer sessions natively?
3. Can it message peers natively?
4. Can it request replies or receive lifecycle events natively?

Only add a fallback when a required capability truly does not exist.

## Product boundary

AFKSwitch owns:

- `/afk`;
- `/back`;
- the portable presence contract;
- host adapters for those semantics.

It does not own general fleet discovery, arbitrary broadcasting, scheduling, orchestration, remote-control infrastructure, authentication, or permission management.

## Pull requests

Keep changes focused. Update documentation and validation whenever behavior or a manifest changes.
Before opening a pull request, run `python scripts/validate.py` and `python -m pytest conformance`
(see [`conformance/README.md`](conformance/README.md)); a new adapter follows
[`adapters/README.md`](adapters/README.md). New host support must document its actual capability level: state-only, notify, or fan-in.

Do not claim host parity without a reproducible test.

## Compatibility

Preserve the portable contract in `spec/presence.md`. Host-specific behavior belongs in adapter documentation or narrowly scoped skill instructions.

### Live check

A host's hooks claim `sync` only after this check, recorded in
[`docs/compatibility.md`](docs/compatibility.md) with the host version, date and OS:

1. Run `python scripts/install.py --host <id>` and approve whatever the host asks
   (Codex `/hooks`, Hermes's first-run approval).
2. With the agent open, run `afkswitch afk` in a terminal. At the agent's next hook boundary
   (new session, prompt, tool call or model call, per the matrix) the model must be able to
   quote the `[AFKSwitch g<N>]` line.
3. For hosts told once per generation, a second prompt must not repeat it.
4. Run `afkswitch back`; the agent must stop treating you as away.
5. Run `python scripts/install.py --host <id> --uninstall` and check the config files are
   back to their previous content.
