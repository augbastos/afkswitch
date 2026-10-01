# Antigravity CLI adapter

Experimental static layout for Antigravity CLI 1.2.13; not verified in a live host,
no default hook wiring and no installer. For a separately reviewed host experiment, copy these public
files into the global plugin directory `~/.gemini/config/plugins/afkswitch`:

```text
afkswitch/
  plugin.json                 # this directory's plugin.json
  hooks.json                  # this directory's hooks.json
  scripts/presence_hook.py     # from the plugin root
  skills/afk/scripts/afkswitch_state.py   # from the plugin root, unchanged
```

In `hooks.json`, replace `<plugin dir>` with the **absolute** installed plugin directory,
retaining the quotes around the script path. The command uses `python` (Python 3.9+ on
PATH); adapt the executable to the interpreter installed on your system.

Global skills live at `~/.gemini/config/skills/<name>/SKILL.md`. Copy the complete `afk`
and `back` directories from the plugin's `skills/` there, reusing each SKILL.md,
references and standalone helper as-is. Keep the plugin's own helper copy as well:
the lifecycle script imports it by path.

`PreInvocation` reads camelCase hook JSON from stdin but does not depend on its fields.
It reads `~/.afkswitch/state.json` once and, only while AFK, returns
`{"injectSteps":[{"ephemeralMessage":"<universal presence event>"}]}`. Ephemeral context
is not persisted, so each invocation receives current AFK state; available state produces
no output. It does not read a transcript, write state, poll, run in the background,
change permissions or use the network. Errors exit 0 with no output.

Only state is declared supported; sync=false until verified in a live host.
Peer messaging reach between independent CLI sessions is
unproven: notify and fanIn are not supported. The static layout and output contract are
tested locally; loading it in an installed Antigravity host remains a separate check.
