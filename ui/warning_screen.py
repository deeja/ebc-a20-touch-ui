"""Safety disclaimer shown on startup - see README.md's "FOR EXPERTS ONLY"
section, which this mirrors. Acknowledgement is remembered across runs via
a small prefs file in the user's home directory, so this doesn't get in the
way once someone's actually read it."""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from typing import Callable

from .widgets import ACCENT_GREEN, ACCENT_RED, BG, PANEL_BG, TEXT, TEXT_MUTED, big_button

PREFS_PATH = Path.home() / ".battery_tester_ui" / "prefs.json"

WARNING_POINTS = [
    "This drives real charge/discharge hardware against real batteries.",
    "Using it outside a battery's safe parameters can cause fire, "
    "explosion, toxic gas release, or permanent damage to the battery, "
    "the EBC-A20, or its surroundings - lithium chemistries especially so.",
    "This tool does not know what's safe for the cell in front of you: "
    "it does not verify voltage cutoffs, C-rates, or charge-termination "
    "behavior against the specific battery you connect.",
    "It is provided with no warranty. Its authors accept no responsibility "
    "for any damage, injury, fire, or loss arising from its use.",
]


def _load_prefs() -> dict:
    try:
        return json.loads(PREFS_PATH.read_text())
    except (OSError, ValueError):
        return {}


def _save_prefs(prefs: dict) -> None:
    try:
        PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREFS_PATH.write_text(json.dumps(prefs))
    except OSError:
        pass  # best-effort - worst case, the warning shows again next run


def warning_acknowledged() -> bool:
    return bool(_load_prefs().get("warning_acknowledged"))


def set_warning_acknowledged() -> None:
    prefs = _load_prefs()
    prefs["warning_acknowledged"] = True
    _save_prefs(prefs)


class WarningScreen(tk.Frame):
    def __init__(self, master, on_continue: Callable[[], None]):
        super().__init__(master, bg=BG)
        self._on_continue = on_continue

        tk.Label(self, text="⚠ Read Before Use", font=("TkDefaultFont", 22, "bold"),
                 bg=BG, fg=ACCENT_RED).pack(pady=(24, 4))
        tk.Label(self, text="For experts only - not a toy", font=("TkDefaultFont", 13),
                 bg=BG, fg=TEXT_MUTED).pack(pady=(0, 16))

        body = tk.Frame(self, bg=PANEL_BG, highlightthickness=1, highlightbackground=ACCENT_RED)
        body.pack(padx=40, fill="x")
        for point in WARNING_POINTS:
            tk.Label(body, text=f"•  {point}", font=("TkDefaultFont", 12), bg=PANEL_BG, fg=TEXT,
                     wraplength=880, justify="left", anchor="w").pack(fill="x", padx=16, pady=8)

        self._understand_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self, text="I understand the risks", variable=self._understand_var,
            command=self._refresh_continue_state, font=("TkDefaultFont", 12, "bold"), bg=BG, fg=TEXT,
            activebackground=BG, activeforeground=TEXT, selectcolor=PANEL_BG,
            padx=10, pady=10,
        ).pack(pady=(20, 0))

        self._dont_remind_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self, text="Don't remind me again about the dangers",
            variable=self._dont_remind_var, font=("TkDefaultFont", 12), bg=BG, fg=TEXT,
            activebackground=BG, activeforeground=TEXT, selectcolor=PANEL_BG,
            padx=10, pady=10,
        ).pack(pady=(0, 4))

        self._continue_btn = big_button(self, "Continue", self._continue, bg=ACCENT_GREEN, fg="white")
        self._continue_btn.pack(padx=40, pady=(10, 24), fill="x")
        self._refresh_continue_state()

    def _refresh_continue_state(self) -> None:
        self._continue_btn.config(state=tk.NORMAL if self._understand_var.get() else tk.DISABLED)

    def _continue(self) -> None:
        if self._dont_remind_var.get():
            set_warning_acknowledged()
        self._on_continue()
