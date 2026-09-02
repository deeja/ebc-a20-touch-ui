"""Small touch-friendly widgets shared by the app screens. Finger-sized
targets (~44px), no hover/tooltip/right-click affordances."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

FONT_LARGE = ("TkDefaultFont", 18, "bold")
FONT_MED = ("TkDefaultFont", 13)
FONT_SMALL = ("TkDefaultFont", 10)


def big_button(master, text: str, command, bg: str = "#2c2c2c", fg: str = "white") -> tk.Button:
    return tk.Button(
        master,
        text=text,
        command=command,
        font=FONT_MED,
        bg=bg,
        fg=fg,
        activebackground="#444444",
        activeforeground="white",
        relief="flat",
        padx=18,
        pady=14,
        bd=0,
    )


class NumberStepper(tk.Frame):
    """Label + [-] value [+] control for touch input, with press-and-hold
    repeat so the user isn't stuck tapping hundreds of times."""

    def __init__(self, master, label: str, value: int, step: int, minimum: int, maximum: int, unit: str = "", **kw):
        super().__init__(master, bg=kw.pop("bg", "#1a1a1a"), **kw)
        self.value = value
        self.step = step
        self.minimum = minimum
        self.maximum = maximum
        self.unit = unit
        self._repeat_job = None

        tk.Label(self, text=label, font=FONT_SMALL, bg="#1a1a1a", fg="#aaaaaa").pack(anchor="w")

        row = tk.Frame(self, bg="#1a1a1a")
        row.pack(fill="x", pady=(2, 0))

        minus = big_button(row, "-", None, bg="#333333")
        minus.pack(side="left")
        minus.bind("<ButtonPress-1>", lambda e: self._start_repeat(-1))
        minus.bind("<ButtonRelease-1>", lambda e: self._stop_repeat())

        self.value_label = tk.Label(row, text=self._text(), font=FONT_LARGE, bg="#1a1a1a", fg="white", width=8)
        self.value_label.pack(side="left", padx=8)

        plus = big_button(row, "+", None, bg="#333333")
        plus.pack(side="left")
        plus.bind("<ButtonPress-1>", lambda e: self._start_repeat(1))
        plus.bind("<ButtonRelease-1>", lambda e: self._stop_repeat())

    def _text(self) -> str:
        return f"{self.value} {self.unit}".strip()

    def _apply(self, direction: int) -> None:
        self.value = max(self.minimum, min(self.maximum, self.value + direction * self.step))
        self.value_label.config(text=self._text())

    def _start_repeat(self, direction: int) -> None:
        self._apply(direction)
        self._repeat_job = self.after(350, lambda: self._repeat(direction))

    def _repeat(self, direction: int) -> None:
        self._apply(direction)
        self._repeat_job = self.after(120, lambda: self._repeat(direction))

    def _stop_repeat(self) -> None:
        if self._repeat_job is not None:
            self.after_cancel(self._repeat_job)
            self._repeat_job = None


class ReadoutTile(tk.Frame):
    def __init__(self, master, label: str, **kw):
        super().__init__(master, bg="#1a1a1a", **kw)
        tk.Label(self, text=label, font=FONT_SMALL, bg="#1a1a1a", fg="#aaaaaa").pack(anchor="w", padx=10, pady=(8, 0))
        self.value_label = tk.Label(self, text="--", font=FONT_LARGE, bg="#1a1a1a", fg="white")
        self.value_label.pack(anchor="w", padx=10, pady=(0, 8))

    def set(self, text: str) -> None:
        self.value_label.config(text=text)
