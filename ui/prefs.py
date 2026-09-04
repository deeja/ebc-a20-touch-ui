"""Shared JSON prefs file for small UI settings that should survive
restarts (warning acknowledgement, graph view mode, ...). One file, one
location, so anything wanting to remember a setting reads/writes a key in
the same dict rather than growing its own file."""
from __future__ import annotations

import json
from pathlib import Path

PREFS_PATH = Path.home() / ".battery_tester_ui" / "prefs.json"


def load_prefs() -> dict:
    try:
        return json.loads(PREFS_PATH.read_text())
    except (OSError, ValueError):
        return {}


def save_prefs(prefs: dict) -> None:
    try:
        PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREFS_PATH.write_text(json.dumps(prefs))
    except OSError:
        pass  # best-effort - worst case, the setting doesn't survive a restart
