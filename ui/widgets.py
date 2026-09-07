"""Small touch-friendly widgets shared by the app screens. Finger-sized
targets (~44px), no hover/tooltip/right-click affordances.

Light theme only, by design - see app.py."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

FONT_LARGE = ("TkDefaultFont", 18, "bold")
FONT_MED = ("TkDefaultFont", 13)
FONT_SMALL = ("TkDefaultFont", 10)

# Shared light palette. Kept here (not duplicated per-file) so the whole
# app's theme lives in one place.
BG = "#f2f2f2"            # app/screen background
PANEL_BG = "#ffffff"      # cards, fields, list rows
BORDER = "#c9c9c9"
TEXT = "#1a1a1a"
TEXT_MUTED = "#5a5a5a"
BTN_BG = "#e2e2e2"
BTN_ACTIVE_BG = "#cfcfcf"
ACCENT_GREEN = "#2e7d32"
ACCENT_GREEN_ACTIVE = "#388e3c"
ACCENT_RED = "#c62828"
ACCENT_RED_ACTIVE = "#d32f2f"
ACCENT_BLUEGREY = "#546e7a"
ACCENT_BLUEGREY_ACTIVE = "#62828e"

# Charge vs. discharge background tints (Settings screen mode/phase sections).
CHARGE_BG = "#e8f5e9"
CHARGE_ACCENT = "#2e7d32"
DISCHARGE_BG = "#fff3e0"
DISCHARGE_ACCENT = "#ef6c00"


def configure_ttk_style(root: tk.Tk) -> None:
    """One-time ttk style setup for touch-sized, light-themed comboboxes.
    'clam' is used because it's the ttk theme that actually honors color
    overrides consistently across platforms."""
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Touch.TCombobox",
        fieldbackground=PANEL_BG,
        background=BTN_BG,
        foreground=TEXT,
        arrowsize=24,
        padding=10,
        font=FONT_MED,
    )
    root.option_add("*TCombobox*Listbox.font", FONT_MED)
    root.option_add("*TCombobox*Listbox.background", PANEL_BG)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", "#4fc3f7")


class Dropdown(ttk.Combobox):
    """Readonly touch-styled dropdown. `on_change(value)` fires on selection."""

    def __init__(self, master, values: list[str], value: str, on_change: Optional[Callable[[str], None]] = None, **kw):
        self._var = tk.StringVar(value=value)
        super().__init__(master, values=values, textvariable=self._var, state="readonly",
                          style="Touch.TCombobox", font=FONT_MED, **kw)
        self._on_change = on_change
        self.bind("<<ComboboxSelected>>", self._fire)

    def _fire(self, _event=None) -> None:
        if self._on_change is not None:
            self._on_change(self._var.get())

    def set_value(self, value: str) -> None:
        self._var.set(value)

    def set_values(self, values: list[str]) -> None:
        """Change the allowed options in place (e.g. hiding modes a battery
        preset doesn't support). Does not touch the current selection - the
        caller decides what to do if it's no longer in `values`."""
        self.configure(values=values)

    @property
    def value(self) -> str:
        return self._var.get()


class ToggleButton(tk.Button):
    """Two-state touch button (e.g. 'Continuous' on/off)."""

    def __init__(self, master, text: str, active: bool = False,
                 on_change: Optional[Callable[[bool], None]] = None, **kw):
        self.active = active
        self._on_change = on_change
        self._base_text = text
        super().__init__(master, text=text, command=self._toggle, font=FONT_MED,
                          relief="flat", padx=18, pady=14, bd=0, **kw)
        self._refresh()

    def _toggle(self) -> None:
        self.active = not self.active
        self._refresh()
        if self._on_change is not None:
            self._on_change(self.active)

    def _refresh(self) -> None:
        if self.active:
            self.config(bg=ACCENT_GREEN, fg="white", activebackground=ACCENT_GREEN_ACTIVE, activeforeground="white")
        else:
            self.config(bg=BTN_BG, fg=TEXT, activebackground=BTN_ACTIVE_BG, activeforeground=TEXT)


SELECTED_BG = "#e3f2fd"
SELECTED_BORDER = "#0288d1"


class SelectableButton(tk.Button):
    """Single-line button that's one of an exclusive-choice group (e.g.
    Mode). set_selected() shows/clears a highlighted border+tint instead of
    relying on focus, since a touchscreen has no visible focus ring."""

    def __init__(self, master, text: str, command: Callable[[], None], **kw):
        super().__init__(master, text=text, command=command, font=FONT_MED,
                          relief="flat", bd=1, padx=14, pady=14, highlightthickness=2, **kw)
        self.selected = False
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        if selected:
            self.config(bg=SELECTED_BG, fg=TEXT, activebackground=SELECTED_BG, activeforeground=TEXT,
                        highlightbackground=SELECTED_BORDER, highlightcolor=SELECTED_BORDER)
        else:
            self.config(bg=PANEL_BG, fg=TEXT, activebackground=BTN_ACTIVE_BG, activeforeground=TEXT,
                        highlightbackground=BORDER, highlightcolor=BORDER)


class PresetButton(tk.Frame):
    """Two-line touch button for battery preset selection: name on top,
    voltage info underneath. Frame-based (not tk.Button) so the two lines
    can use different font weights/sizes; the whole card is clickable."""

    def __init__(self, master, title: str, subtitle: str, command: Callable[[], None], **kw):
        super().__init__(master, bg=PANEL_BG, bd=1, relief="flat",
                          highlightthickness=2, highlightbackground=BORDER, **kw)
        self._command = command
        self.selected = False

        self.title_label = tk.Label(self, text=title, font=("TkDefaultFont", 12, "bold"), bg=PANEL_BG, fg=TEXT,
                                     anchor="w", justify="left")
        self.title_label.pack(fill="x", padx=10, pady=(8, 0))
        self.subtitle_label = tk.Label(self, text=subtitle, font=FONT_SMALL, bg=PANEL_BG, fg=TEXT_MUTED,
                                        anchor="w", justify="left")
        self.subtitle_label.pack(fill="x", padx=10, pady=(0, 8))

        for widget in (self, self.title_label, self.subtitle_label):
            widget.bind("<Button-1>", self._on_click)

    def _on_click(self, _event=None) -> None:
        self._command()

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.config(text=text)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        bg = SELECTED_BG if selected else PANEL_BG
        border = SELECTED_BORDER if selected else BORDER
        self.config(bg=bg, highlightbackground=border)
        self.title_label.config(bg=bg)
        self.subtitle_label.config(bg=bg)


def big_button(master, text: str, command, bg: str = BTN_BG, fg: str = TEXT) -> tk.Button:
    active_bg = BTN_ACTIVE_BG if bg == BTN_BG else bg
    active_fg = fg
    return tk.Button(
        master,
        text=text,
        command=command,
        font=FONT_MED,
        bg=bg,
        fg=fg,
        activebackground=active_bg,
        activeforeground=active_fg,
        relief="flat",
        padx=18,
        pady=14,
        bd=0,
    )


# Unit-option presets for TouchNumberField/NumpadDialog: each option is
# (button label, multiplier to convert a typed value into the field's raw
# base unit). The chosen button both picks the unit AND confirms entry -
# there's no separate "Accept" button when units are involved.
CURRENT_UNITS = [("mA", 1), ("A", 1000)]          # raw base unit: mA
VOLTAGE_UNITS = [("mV", 1), ("V", 1000)]          # raw base unit: mV
TIME_UNITS = [("Sec", 1 / 60), ("Min", 1)]        # raw base unit: minutes
PLAIN_UNITS = [("OK", 1)]                          # no unit conversion


def current_field_kwargs() -> dict:
    return dict(unit_options=CURRENT_UNITS, display_scale=1000, display_decimals=2, display_unit="A")


def voltage_field_kwargs() -> dict:
    return dict(unit_options=VOLTAGE_UNITS, display_scale=1000, display_decimals=2, display_unit="V")


def time_field_kwargs() -> dict:
    return dict(unit_options=TIME_UNITS, display_scale=1, display_decimals=0, display_unit="min")


def plain_field_kwargs(unit: str = "") -> dict:
    return dict(unit_options=PLAIN_UNITS, display_scale=1, display_decimals=0, display_unit=unit)


class NumpadDialog(tk.Toplevel):
    """Modal on-screen number pad. Digits/decimal/backspace/clear build up
    a typed value; the unit button(s) at the bottom both pick the unit and
    confirm/accept in one tap (or a single "OK" button when the field has
    no unit choice).

    Ordering here matters: withdraw() immediately, before any children are
    packed, so the window never gets a chance to auto-map at its default
    top-left-ish spot and visibly jump from there to centered; then the
    window is positioned and made visible (deiconify) BEFORE grab_set()/
    focus_force() are called. Grabbing input on a window that isn't
    viewable yet is what caused the whole app to appear to freeze (all
    input got captured by a dialog that wasn't actually showing/focused)
    - this is the standard safe sequence for a Tk modal dialog."""

    def __init__(self, master: tk.Misc, title: str, unit_options: list[tuple[str, float]],
                 on_accept: Callable[[float, float], None]):
        super().__init__(master, bg=PANEL_BG)
        # Borderless like the other touch popups (GraphViewDialog, ConfirmDialog
        # in ui/graph.py) - a decorated Toplevel opened as a transient child of
        # one of those override-redirect windows stacks/focuses inconsistently
        # across window managers, which showed up as an overlay glitch between
        # the chart menu and this numpad.
        self.overrideredirect(True)
        # Stay hidden until centered - an override-redirect Toplevel maps
        # itself at a default top-left-ish spot the instant its children are
        # packed, so without this it visibly jumps from there to centered.
        self.withdraw()
        self._on_accept = on_accept
        self._text = ""

        tk.Label(self, text=title, font=FONT_MED, bg=PANEL_BG, fg=TEXT_MUTED).pack(pady=(14, 4))
        self.display = tk.Label(self, text="0", font=("TkDefaultFont", 28, "bold"), bg=BG, fg=TEXT,
                                 width=10, anchor="e", padx=10)
        self.display.pack(padx=14, pady=(0, 10))

        grid = tk.Frame(self, bg=PANEL_BG)
        grid.pack(padx=14)
        layout = [
            [("7", 0, 0), ("8", 0, 1), ("9", 0, 2)],
            [("4", 1, 0), ("5", 1, 1), ("6", 1, 2)],
            [("1", 2, 0), ("2", 2, 1), ("3", 2, 2)],
            [("C", 3, 0), ("0", 3, 1), ("⌫", 3, 2), (".", 3, 3)],
        ]
        commands = {"C": self._clear, "⌫": self._backspace}
        for row in layout:
            for label, r, c in row:
                cmd = commands.get(label, lambda d=label: self._digit(d))
                tk.Button(grid, text=label, command=cmd, font=("TkDefaultFont", 18), bg=BTN_BG, fg=TEXT,
                          activebackground=BTN_ACTIVE_BG, activeforeground=TEXT, relief="flat", bd=0,
                          width=4, height=1).grid(row=r, column=c, padx=4, pady=4)

        unit_row = tk.Frame(self, bg=PANEL_BG)
        unit_row.pack(fill="x", padx=14, pady=(10, 4))
        for label, scale in unit_options:
            tk.Button(unit_row, text=label, command=lambda s=scale: self._confirm(s), font=FONT_MED,
                      bg=ACCENT_GREEN, fg="white", activebackground=ACCENT_GREEN_ACTIVE, activeforeground="white",
                      relief="flat", bd=0, padx=18, pady=14).pack(side="left", expand=True, fill="x", padx=4)

        tk.Button(self, text="Cancel", command=self.destroy, font=FONT_SMALL, bg=BTN_BG, fg=TEXT,
                  activebackground=BTN_ACTIVE_BG, activeforeground=TEXT, relief="flat", bd=0,
                  padx=12, pady=8).pack(pady=(4, 14))

        self.transient(master.winfo_toplevel())
        self._center_on(master.winfo_toplevel())
        self.deiconify()
        self.lift()
        self.focus_force()
        self.grab_set()

    def _center_on(self, root: tk.Misc) -> None:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        rx, ry = root.winfo_rootx(), root.winfo_rooty()
        rw, rh = root.winfo_width(), root.winfo_height()
        x = rx + max(0, (rw - w) // 2)
        y = ry + max(0, (rh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _refresh(self) -> None:
        self.display.config(text=self._text if self._text else "0")

    def _digit(self, d: str) -> None:
        if d == "." and "." in self._text:
            return
        self._text += d
        self._refresh()

    def _backspace(self) -> None:
        self._text = self._text[:-1]
        self._refresh()

    def _clear(self) -> None:
        self._text = ""
        self._refresh()

    def _confirm(self, scale: float) -> None:
        try:
            value = float(self._text) if self._text not in ("", ".") else 0.0
        except ValueError:
            value = 0.0
        self._on_accept(value, scale)
        self.destroy()


class ConfirmDialog(tk.Toplevel):
    """Small modal Yes/Cancel popup, styled like the other borderless touch
    dialogs in this app (see NumpadDialog above for the same show/center/
    grab_set ordering note) - used to confirm a destructive/consequential
    action before it happens."""

    def __init__(self, master: tk.Misc, message: str, on_confirm: Callable[[], None],
                 confirm_label: str = "Confirm"):
        super().__init__(master, bg=PANEL_BG)
        self.overrideredirect(True)
        self.withdraw()
        self._on_confirm = on_confirm

        tk.Label(self, text=message, font=FONT_MED, bg=PANEL_BG, fg=TEXT,
                 wraplength=260, justify="center").pack(padx=20, pady=(20, 14))

        row = tk.Frame(self, bg=PANEL_BG)
        row.pack(fill="x", padx=14, pady=(0, 14))
        big_button(row, "Cancel", self.destroy, bg=BTN_BG, fg=TEXT).pack(side="left", expand=True, fill="x", padx=(0, 4))
        big_button(row, confirm_label, self._confirm, bg=ACCENT_RED, fg="white").pack(side="left", expand=True, fill="x", padx=(4, 0))

        self.transient(master.winfo_toplevel())
        center_on_parent(self, master.winfo_toplevel())
        self.lift()
        self.focus_force()
        self.grab_set()

    def _confirm(self) -> None:
        self._on_confirm()
        self.destroy()


class InfoDialog(tk.Toplevel):
    """Small modal message popup with a single OK button, styled like the
    other borderless touch dialogs in this app - used for one-shot result
    messages so they show as their own overlay rather than getting lost
    inline in whatever triggered them."""

    def __init__(self, master: tk.Misc, message: str):
        super().__init__(master, bg=PANEL_BG)
        self.overrideredirect(True)
        self.withdraw()

        tk.Label(self, text=message, font=FONT_MED, bg=PANEL_BG, fg=TEXT,
                 wraplength=260, justify="center").pack(padx=20, pady=(20, 14))
        big_button(self, "OK", self.destroy, bg=BTN_BG, fg=TEXT).pack(fill="x", padx=14, pady=(0, 14))

        self.transient(master.winfo_toplevel())
        center_on_parent(self, master.winfo_toplevel())
        self.lift()
        self.focus_force()
        self.grab_set()


def center_on_parent(win: tk.Toplevel, root: tk.Misc) -> None:
    """Position win over root, then reveal it. Callers must withdraw() win
    right after construction (before packing any children) - otherwise it
    auto-maps at a default top-left-ish spot the moment its children are
    packed, and visibly jumps from there to here when this repositions it."""
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    rx, ry = root.winfo_rootx(), root.winfo_rooty()
    rw, rh = root.winfo_width(), root.winfo_height()
    x = rx + max(0, (rw - w) // 2)
    y = ry + max(0, (rh - h) // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.deiconify()


class TouchNumberField(tk.Frame):
    """Label + tap-to-edit value (opens NumpadDialog). Stores/reports its
    value in a fixed raw base unit (e.g. mA, mV, minutes); displays it in a
    friendlier unit (A, V, min) but lets numpad entry happen in either the
    base or friendly unit via the dialog's unit buttons."""

    def __init__(self, master, label: str, raw_value: int, minimum: int, maximum: int,
                 unit_options: list[tuple[str, float]], display_scale: float = 1, display_decimals: int = 0,
                 display_unit: str = "", on_change: Optional[Callable[[int], None]] = None, **kw):
        super().__init__(master, bg=kw.pop("bg", BG), **kw)
        self.raw_value = raw_value
        self.minimum = minimum
        self.maximum = maximum
        self.unit_options = unit_options
        self.display_scale = display_scale
        self.display_decimals = display_decimals
        self.display_unit = display_unit
        self.on_change = on_change
        self.label_text = label

        tk.Label(self, text=label, font=FONT_SMALL, bg=BG, fg=TEXT_MUTED).pack(anchor="w")
        self.value_button = tk.Button(self, text=self._display(), command=self._open_numpad, font=FONT_LARGE,
                                       bg=PANEL_BG, fg=TEXT, activebackground=BTN_ACTIVE_BG, activeforeground=TEXT,
                                       relief="flat", bd=1, highlightthickness=1, highlightbackground=BORDER,
                                       padx=16, pady=10)
        self.value_button.pack(anchor="w", pady=(2, 0))

    def _display(self) -> str:
        val = self.raw_value / self.display_scale
        return f"{val:.{self.display_decimals}f} {self.display_unit}".strip()

    def _open_numpad(self) -> None:
        NumpadDialog(self, self.label_text, self.unit_options, self._on_numpad_accept)

    def _on_numpad_accept(self, value: float, scale: float) -> None:
        self.set_value(int(round(value * scale)))

    def set_value(self, raw_value: int) -> None:
        self.raw_value = max(self.minimum, min(self.maximum, raw_value))
        self.value_button.config(text=self._display())
        if self.on_change is not None:
            self.on_change(self.raw_value)

    def set_range(self, minimum: int, maximum: int) -> None:
        self.minimum, self.maximum = minimum, maximum
        self.set_value(self.raw_value)


class ReadoutTile(tk.Frame):
    def __init__(self, master, label: str, **kw):
        super().__init__(master, bg=PANEL_BG, **kw)
        tk.Label(self, text=label, font=FONT_SMALL, bg=PANEL_BG, fg=TEXT_MUTED).pack(anchor="w", padx=10, pady=(8, 0))
        self.value_label = tk.Label(self, text="--", font=FONT_LARGE, bg=PANEL_BG, fg=TEXT)
        self.value_label.pack(anchor="w", padx=10, pady=(0, 8))

    def set(self, text: str) -> None:
        self.value_label.config(text=text)
