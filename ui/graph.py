"""Touch-kiosk-friendly dual-line strip chart: voltage (left axis) and
current (right axis) against time, on a shared canvas. Redraws are
decimated to the canvas width and throttled by the caller (app.py) rather
than on every sample, since redrawing a long polyline every frame is the
kind of thing that makes a Pi Zero feel broken.

Tapping the chart opens a touch popup to pick how the time axis behaves
(a scrolling window of a chosen width, or "Fit All" to show the whole
run) - that choice is remembered across restarts via ui/prefs.py."""
from __future__ import annotations

import tkinter as tk
from collections import deque

from . import prefs as prefsmod
from .widgets import (
    ACCENT_BLUEGREY,
    ACCENT_RED,
    BORDER,
    BTN_ACTIVE_BG,
    BTN_BG,
    FONT_LARGE,
    FONT_MED,
    FONT_SMALL,
    NumpadDialog,
    PANEL_BG,
    SELECTED_BG,
    SELECTED_BORDER,
    TEXT,
    TEXT_MUTED,
    ToggleButton,
    big_button,
)

VOLTAGE_COLOR = "#0288d1"
CURRENT_COLOR = "#ef6c00"
GRID_COLOR = "#dddddd"
AXIS_TEXT_COLOR = "#666666"
HINT_TEXT_COLOR = "#aaaaaa"
BG_COLOR = "#ffffff"

MARGIN_L = 60
MARGIN_R = 60
MARGIN_T = 16
MARGIN_B = 34

PREFS_KEY = "graph_view"

MIN_WINDOW_S = 5
MAX_WINDOW_S = 24 * 3600

# unit_options for the scroll-window NumpadDialog: raw base unit is seconds.
WINDOW_UNITS = [("Sec", 1), ("Min", 60)]


class DualLineGraph(tk.Canvas):
    def __init__(self, master, history_seconds: int = 300, **kw):
        kw.setdefault("bg", BG_COLOR)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self.default_window_seconds = history_seconds
        self.window_seconds = history_seconds
        self.fit_all = False
        self.y_zero_based = False
        self._load_view_settings()

        self._points: deque[tuple[float, float, float]] = deque(maxlen=2000)
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._on_tap)

    def add_sample(self, t: float, voltage_v: float, current_a: float) -> None:
        self._points.append((t, voltage_v, current_a))

    def clear(self) -> None:
        self._points.clear()
        self.redraw()

    # -- view mode (scrolling window vs. fit-all) --------------------------
    def _load_view_settings(self) -> None:
        saved = prefsmod.load_prefs().get(PREFS_KEY, {})
        self.fit_all = bool(saved.get("fit_all", False))
        self.window_seconds = int(saved.get("window_seconds", self.default_window_seconds))
        self.y_zero_based = bool(saved.get("y_zero_based", False))

    def _save_view_settings(self) -> None:
        all_prefs = prefsmod.load_prefs()
        all_prefs[PREFS_KEY] = {
            "fit_all": self.fit_all,
            "window_seconds": self.window_seconds,
            "y_zero_based": self.y_zero_based,
        }
        prefsmod.save_prefs(all_prefs)

    def set_window(self, seconds: int) -> None:
        self.fit_all = False
        self.window_seconds = seconds
        self._save_view_settings()
        self.redraw()

    def set_fit_all(self) -> None:
        self.fit_all = True
        self._save_view_settings()
        self.redraw()

    def set_y_zero_based(self, enabled: bool) -> None:
        self.y_zero_based = enabled
        self._save_view_settings()
        self.redraw()

    def clear_view_settings(self) -> None:
        """Reset to the graph's built-in default and forget the saved
        choice, so a future run starts fresh instead of reopening on
        whatever view was last picked."""
        all_prefs = prefsmod.load_prefs()
        all_prefs.pop(PREFS_KEY, None)
        prefsmod.save_prefs(all_prefs)
        self.fit_all = False
        self.window_seconds = self.default_window_seconds
        self.y_zero_based = False
        self.redraw()

    def _on_tap(self, _event=None) -> None:
        GraphViewDialog(self, self)

    def redraw(self) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10 or not self._points:
            return

        plot_w = max(1, w - MARGIN_L - MARGIN_R)
        plot_h = max(1, h - MARGIN_T - MARGIN_B)

        t_max = self._points[-1][0]
        t_min = self._points[0][0] if self.fit_all else t_max - self.window_seconds
        pts = [p for p in self._points if p[0] >= t_min]
        if len(pts) < 2:
            return

        # decimate to roughly one sample per pixel column
        if len(pts) > plot_w:
            step = len(pts) // plot_w
            pts = pts[::step]

        volts = [p[1] for p in pts]
        amps = [p[2] for p in pts]
        v_lo, v_hi = _padded_range(volts, zero_based=self.y_zero_based)
        a_lo, a_hi = _padded_range(amps, zero_based=self.y_zero_based)

        def x_of(t: float) -> float:
            span = max(1e-6, t_max - t_min)
            return MARGIN_L + (t - t_min) / span * plot_w

        def y_of(val: float, lo: float, hi: float) -> float:
            span = max(1e-6, hi - lo)
            return MARGIN_T + plot_h - (val - lo) / span * plot_h

        self._draw_grid(w, h, plot_w, plot_h, t_min, t_max, v_lo, v_hi, a_lo, a_hi)

        v_line = []
        a_line = []
        for t, v, a in pts:
            x = x_of(t)
            v_line += [x, y_of(v, v_lo, v_hi)]
            a_line += [x, y_of(a, a_lo, a_hi)]

        self.create_line(*v_line, fill=VOLTAGE_COLOR, width=2, smooth=True)
        self.create_line(*a_line, fill=CURRENT_COLOR, width=2, smooth=True)

        self.create_text(MARGIN_L, 8, text="Voltage (V)", fill=VOLTAGE_COLOR, anchor="w", font=("TkDefaultFont", 9, "bold"))
        self.create_text(w - MARGIN_R, 8, text="Current (A)", fill=CURRENT_COLOR, anchor="e", font=("TkDefaultFont", 9, "bold"))
        self.create_text(w / 2, 8, text="tap chart for view options", fill=HINT_TEXT_COLOR, anchor="n", font=("TkDefaultFont", 8))

    def _draw_grid(self, w, h, plot_w, plot_h, t_min, t_max, v_lo, v_hi, a_lo, a_hi):
        rows = 4
        for i in range(rows + 1):
            y = MARGIN_T + plot_h * i / rows
            self.create_line(MARGIN_L, y, MARGIN_L + plot_w, y, fill=GRID_COLOR)
            v_val = v_hi - (v_hi - v_lo) * i / rows
            a_val = a_hi - (a_hi - a_lo) * i / rows
            self.create_text(MARGIN_L - 6, y, text=f"{v_val:.2f}", fill=VOLTAGE_COLOR, anchor="e", font=("TkDefaultFont", 8))
            self.create_text(MARGIN_L + plot_w + 6, y, text=f"{a_val:.2f}", fill=CURRENT_COLOR, anchor="w", font=("TkDefaultFont", 8))

        cols = 4
        for i in range(cols + 1):
            x = MARGIN_L + plot_w * i / cols
            self.create_line(x, MARGIN_T, x, MARGIN_T + plot_h, fill=GRID_COLOR)
            t_val = t_min + (t_max - t_min) * i / cols
            self.create_text(x, MARGIN_T + plot_h + 4, text=_format_elapsed(t_val), fill=AXIS_TEXT_COLOR,
                              anchor="n", font=("TkDefaultFont", 8))

        self.create_rectangle(MARGIN_L, MARGIN_T, MARGIN_L + plot_w, MARGIN_T + plot_h, outline=GRID_COLOR)


class GraphViewDialog(tk.Toplevel):
    """Touch popup opened by tapping the chart: pick a scrolling time
    window, jump to Fit All, or clear the saved view choice.

    Follows the same show/center/grab_set ordering as NumpadDialog
    (widgets.py) - grabbing input before the window is viewable is what
    made the app appear to freeze there, so the same care applies here."""

    def __init__(self, master: tk.Misc, graph: DualLineGraph):
        super().__init__(master, bg=PANEL_BG)
        self.title("Chart View")
        self._graph = graph

        tk.Label(self, text="Chart View", font=FONT_MED, bg=PANEL_BG, fg=TEXT_MUTED).pack(pady=(14, 6))

        window_box = tk.Frame(self, bg=PANEL_BG)
        window_box.pack(fill="x", padx=14)
        tk.Label(window_box, text="SCROLL WINDOW", font=FONT_SMALL, bg=PANEL_BG, fg=TEXT_MUTED).pack(anchor="w")
        window_selected = not graph.fit_all
        self._window_btn = tk.Button(
            window_box, text=_format_elapsed(graph.window_seconds), command=self._open_window_numpad,
            font=FONT_LARGE, bg=SELECTED_BG if window_selected else PANEL_BG, fg=TEXT,
            activebackground=BTN_ACTIVE_BG, activeforeground=TEXT, relief="flat", bd=1,
            highlightthickness=2, highlightbackground=SELECTED_BORDER if window_selected else BORDER,
            padx=16, pady=10,
        )
        self._window_btn.pack(anchor="w", fill="x", pady=(2, 10))

        self.zero_toggle = ToggleButton(self, "Start Y at 0", active=graph.y_zero_based,
                                         on_change=self._pick_y_zero_based)
        self.zero_toggle.pack(fill="x", padx=14, pady=(0, 10))

        fit_bg = SELECTED_BG if graph.fit_all else ACCENT_BLUEGREY
        fit_fg = TEXT if graph.fit_all else "white"
        big_button(self, "Fit All", self._pick_fit_all, bg=fit_bg, fg=fit_fg).pack(fill="x", padx=14, pady=(10, 4))
        big_button(self, "Clear Settings", self._clear_settings, bg=ACCENT_RED, fg="white").pack(fill="x", padx=14, pady=4)
        big_button(self, "Close", self.destroy, bg=BTN_BG, fg=TEXT).pack(fill="x", padx=14, pady=(4, 14))

        self.transient(master.winfo_toplevel())
        self._center_on(master.winfo_toplevel())
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

    def _open_window_numpad(self) -> None:
        NumpadDialog(self, "SCROLL WINDOW", WINDOW_UNITS, self._on_window_numpad_accept)

    def _on_window_numpad_accept(self, value: float, scale: float) -> None:
        seconds = max(MIN_WINDOW_S, min(MAX_WINDOW_S, int(round(value * scale))))
        self._graph.set_window(seconds)
        self.destroy()

    def _pick_y_zero_based(self, enabled: bool) -> None:
        self._graph.set_y_zero_based(enabled)

    def _pick_fit_all(self) -> None:
        self._graph.set_fit_all()
        self.destroy()

    def _clear_settings(self) -> None:
        self._graph.clear_view_settings()
        self.destroy()


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _padded_range(values: list[float], zero_based: bool = False) -> tuple[float, float]:
    lo, hi = min(values), max(values)
    if zero_based:
        lo = min(0.0, lo)
    if hi - lo < 1e-6:
        hi += 0.5
        if not zero_based:
            lo -= 0.5
    pad = (hi - lo) * 0.1
    hi += pad
    if not zero_based or lo < 0:
        lo -= pad
    return lo, hi
