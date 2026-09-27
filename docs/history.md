# Project history

AFKSwitch began in September 2026 as **claude-session-presence**, a private Claude Code utility built to solve a real workflow problem: multiple agents could keep working while their human operator walked away, but they had no explicit shared signal for human physical presence.

The first implementation used Claude Code's native cross-session discovery and messaging rather than introducing a daemon, database, polling loop, or custom protocol.

The project was dogfooded in a real overnight multi-session run. During that run, sessions continued independent work, deferred physically-bound authentication steps, and reported those blockers when the operator returned.

On 27 September 2026 the project began its transition to **AFKSwitch**:

- `/afk` and `/back` became the product core;
- general session discovery and broadcast commands were removed from the product boundary;
- Claude Code became the first reference adapter rather than the identity of the project;
- state moved conceptually from a Claude-specific location to `~/.afkswitch/state.json`;
- the contract was documented independently of any model vendor.

The original Git history is intentionally preserved so the evolution from the working Claude utility to a model-agnostic presence contract remains visible.

The public repository `augbastos/afkswitch` carries that same history, with one change: commit author e-mails were normalized to the GitHub noreply address. Commit messages, dates, and contents are unchanged. The original `claude-session-presence` repository remains private as the archive.
