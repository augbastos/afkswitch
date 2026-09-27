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

Keep changes focused. Update documentation and validation whenever behavior or a manifest changes. New host support must document its actual capability level: state-only, notify, or fan-in.

Do not claim host parity without a reproducible test.

## Compatibility

Preserve the portable contract in `spec/presence.md`. Host-specific behavior belongs in adapter documentation or narrowly scoped skill instructions.
