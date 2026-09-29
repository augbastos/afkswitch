#!/usr/bin/env python3
"""Shim: /back runs the one canonical AFKSwitch state helper, skills/afk/scripts/afkswitch_state.py."""
import os
import runpy
import sys

HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      os.pardir, os.pardir, "afk", "scripts", "afkswitch_state.py")

if not os.path.isfile(HELPER):
    sys.stdout.write('{"ok": false, "error": "helper_missing", '
                     '"message": "state helper unavailable (skills/afk/scripts/afkswitch_state.py not found)"}\n')
    sys.exit(1)

runpy.run_path(os.path.normpath(HELPER), run_name="__main__")
