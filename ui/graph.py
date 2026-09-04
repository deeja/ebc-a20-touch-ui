"""Touch-kiosk-friendly dual-line strip chart: voltage (left axis) and
current (right axis) against time, on a shared canvas. Redraws are
decimated to the canvas width and throttled by the caller (app.py) rather
than on every sample, since redrawing a long polyline every frame is the
kind of thing that makes a Pi Zero feel broken.

Tapping the chart opens a touch popup to pick how the time axis behaves
(a scrolling window of a chosen width, or "Fit All" to show the whole
run) - that choice is remembered across restarts via ui/prefs.py.
Dragging a finger/mouse across the chart instead shows a value tooltip
and crosshair for the nearest sample - drag vs. tap is disambiguated by
a small movement threshold so a plain tap still opens the popup."""
from __future__ import annotations

import math
import tkinter as tk
from collections import deque

from . import prefs as prefsmod
from .widgets import (
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
VOLTAGE_GRID_COLOR = "#d6ecfa"
CURRENT_GRID_COLOR = "#fbe0c4"
GRID_COLOR = "#dddddd"
AXIS_TEXT_COLOR = "#666666"
HINT_TEXT_COLOR = "#aaaaaa"
CROSSHAIR_COLOR = "#999999"
BG_COLOR = "#ffffff"

MARGIN_L = 68
MARGIN_R = 68
MARGIN_T = 16
MARGIN_B = 34

PREFS_KEY = "graph_view"

MIN_WINDOW_S = 5
MAX_WINDOW_S = 24 * 3600

# unit_options for the scroll-window NumpadDialog: raw base unit is seconds.
WINDOW_UNITS = [("Sec", 1), ("Min", 60)]

# Axis tick sizing: below FINE_STEP_THRESHOLD_BASE (base units, V or A) an
# axis uses a fixed one-decimal step instead of losing all resolution to a
# whole number of volts/amps; at or above it, ticks fall back to a standard
# 1/2/5 x10**n "nice step" search, which is always a whole number.
FINE_STEP_THRESHOLD_BASE = 2.0
FINE_STEP = 0.1
NICE_STEP_TARGET_ROWS = 4

DRAG_THRESHOLD_PX = 10


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

        self._press_xy: tuple[int, int] | None = None
        self._dragging = False
        self._drag_x: int | None = None
        self._overlay_items: list[int] = []

        # Geometry/domain from the most recent redraw() - lets a drag move
        # the crosshair/tooltip cheaply (no full recompute) between the
        # throttled full redraws the caller schedules.
        self._last_pts: list[tuple[float, float, float]] = []
        self._last_t_min = 0.0
        self._last_t_max = 0.0
        self._last_plot_w: int | None = None
        self._last_plot_h = 0
        self._last_v_lo = self._last_v_hi = 0.0
        self._last_a_lo = self._last_a_hi = 0.0

        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

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

    # -- tap (open view options) vs. drag (tooltip) -------------------------
    def _on_press(self, event) -> None:
        self._press_xy = (event.x, event.y)
        self._dragging = False

    def _on_drag(self, event) -> None:
        if self._press_xy is None:
            return
        dx = event.x - self._press_xy[0]
        dy = event.y - self._press_xy[1]
        if not self._dragging and max(abs(dx), abs(dy)) > DRAG_THRESHOLD_PX:
            self._dragging = True
        if self._dragging:
            self._update_overlay(event.x)

    def _on_release(self, event) -> None:
        was_dragging = self._dragging
        self._press_xy = None
        self._dragging = False
        self._drag_x = None
        if was_dragging:
            self.redraw()
        else:
            self._on_tap(event)

    def _on_tap(self, _event=None) -> None:
        GraphViewDialog(self, self)

    def redraw(self) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10 or not self._points:
            self._last_plot_w = None
            return

        plot_w = max(1, w - MARGIN_L - MARGIN_R)
        plot_h = max(1, h - MARGIN_T - MARGIN_B)

        t_max = self._points[-1][0]
        t_min = self._points[0][0] if self.fit_all else t_max - self.window_seconds
        pts = [p for p in self._points if p[0] >= t_min]
        if len(pts) < 2:
            self._last_plot_w = None
            return

        v_min, v_max = min(p[1] for p in pts), max(p[1] for p in pts)
        a_min, a_max = min(p[2] for p in pts), max(p[2] for p in pts)

        # decimate to roughly one sample per pixel column for the polyline -
        # min/max/ticks above are computed from the full-resolution pts so a
        # narrow spike isn't lost to decimation.
        plot_pts = pts
        if len(plot_pts) > plot_w:
            step = len(plot_pts) // plot_w
            plot_pts = plot_pts[::step]

        v_ticks, v_decimals = _axis_ticks(v_min, v_max, self.y_zero_based)
        a_ticks, a_decimals = _axis_ticks(a_min, a_max, self.y_zero_based)
        v_lo, v_hi = v_ticks[0], v_ticks[-1]
        a_lo, a_hi = a_ticks[0], a_ticks[-1]

        def x_of(t: float) -> float:
            span = max(1e-6, t_max - t_min)
            return MARGIN_L + (t - t_min) / span * plot_w

        def y_of(val: float, lo: float, hi: float) -> float:
            span = max(1e-6, hi - lo)
            return MARGIN_T + plot_h - (val - lo) / span * plot_h

        self._draw_axis_grid(plot_w, plot_h, v_ticks, v_decimals, v_lo, v_hi,
                              VOLTAGE_GRID_COLOR, VOLTAGE_COLOR, "V", "left")
        self._draw_axis_grid(plot_w, plot_h, a_ticks, a_decimals, a_lo, a_hi,
                              CURRENT_GRID_COLOR, CURRENT_COLOR, "A", "right")
        self._draw_time_grid(plot_w, plot_h, t_min, t_max)

        v_line = []
        a_line = []
        for t, v, a in plot_pts:
            x = x_of(t)
            v_line += [x, y_of(v, v_lo, v_hi)]
            a_line += [x, y_of(a, a_lo, a_hi)]

        self.create_line(*v_line, fill=VOLTAGE_COLOR, width=2, smooth=True)
        self.create_line(*a_line, fill=CURRENT_COLOR, width=2, smooth=True)

        self.create_text(MARGIN_L, 8, text="Voltage (V)", fill=VOLTAGE_COLOR, anchor="w", font=("TkDefaultFont", 9, "bold"))
        self.create_text(w - MARGIN_R, 8, text="Current (A)", fill=CURRENT_COLOR, anchor="e", font=("TkDefaultFont", 9, "bold"))
        self.create_text(w / 2, 8, text="tap chart for view options, drag for values", fill=HINT_TEXT_COLOR,
                          anchor="n", font=("TkDefaultFont", 8))

        self._last_pts = pts
        self._last_t_min, self._last_t_max = t_min, t_max
        self._last_plot_w, self._last_plot_h = plot_w, plot_h
        self._last_v_lo, self._last_v_hi = v_lo, v_hi
        self._last_a_lo, self._last_a_hi = a_lo, a_hi

        if self._dragging and self._drag_x is not None:
            self._update_overlay(self._drag_x)

    def _draw_axis_grid(self, plot_w, plot_h, ticks, decimals, lo, hi, line_color, text_color, unit_label, side) -> None:
        span = max(1e-9, hi - lo)
        for val in ticks:
            y = MARGIN_T + plot_h - (val - lo) / span * plot_h
            self.create_line(MARGIN_L, y, MARGIN_L + plot_w, y, fill=line_color)
            label = f"{val:.{decimals}f}{unit_label}"
            x = (MARGIN_L - 6) if side == "left" else (MARGIN_L + plot_w + 6)
            anchor = "e" if side == "left" else "w"
            self.create_text(x, y, text=label, fill=text_color, anchor=anchor, font=("TkDefaultFont", 8))

    def _draw_time_grid(self, plot_w, plot_h, t_min, t_max) -> None:
        cols = 4
        for i in range(cols + 1):
            x = MARGIN_L + plot_w * i / cols
            self.create_line(x, MARGIN_T, x, MARGIN_T + plot_h, fill=GRID_COLOR)
            t_val = t_min + (t_max - t_min) * i / cols
            self.create_text(x, MARGIN_T + plot_h + 4, text=_format_elapsed(t_val), fill=AXIS_TEXT_COLOR,
                              anchor="n", font=("TkDefaultFont", 8))
        self.create_rectangle(MARGIN_L, MARGIN_T, MARGIN_L + plot_w, MARGIN_T + plot_h, outline=GRID_COLOR)

    def _update_overlay(self, x: int) -> None:
        if self._last_plot_w is None or not self._last_pts:
            return
        if self._overlay_items:
            self.delete(*self._overlay_items)
        self._overlay_items = []

        x = max(MARGIN_L, min(MARGIN_L + self._last_plot_w, x))
        self._drag_x = x

        span = max(1e-6, self._last_t_max - self._last_t_min)
        t = self._last_t_min + (x - MARGIN_L) / self._last_plot_w * span
        sample = min(self._last_pts, key=lambda p: abs(p[0] - t))

        crosshair = self.create_line(x, MARGIN_T, x, MARGIN_T + self._last_plot_h, fill=CROSSHAIR_COLOR, dash=(2, 2))
        self._overlay_items.append(crosshair)

        v_text = f"{sample[1]:.2f}V"
        a_text = f"{sample[2]:.2f}A"
        text = f"{_format_elapsed(sample[0])}\n{v_text}\n{a_text}"

        right_side = x > MARGIN_L + self._last_plot_w / 2
        anchor = "ne" if right_side else "nw"
        tx = x - 8 if right_side else x + 8
        ty = MARGIN_T + 6

        label = self.create_text(tx, ty, text=text, fill=TEXT, anchor=anchor, font=("TkDefaultFont", 9), justify="left")
        bbox = self.bbox(label)
        if bbox:
            pad = 4
            rect = self.create_rectangle(bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad,
                                          fill=BG_COLOR, outline=GRID_COLOR)
            self.tag_lower(rect, label)
            self._overlay_items.append(rect)
        self._overlay_items.append(label)


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

        top_row = tk.Frame(self, bg=PANEL_BG)
        top_row.pack(fill="x", padx=14)

        window_box = tk.Frame(top_row, bg=PANEL_BG)
        window_box.pack(side="left", fill="both", expand=True)
        tk.Label(window_box, text="SCROLL WINDOW", font=FONT_SMALL, bg=PANEL_BG, fg=TEXT_MUTED).pack(anchor="w")
        window_selected = not graph.fit_all
        self._window_btn = tk.Button(
            window_box, text=_format_elapsed(graph.window_seconds), command=self._open_window_numpad,
            font=FONT_LARGE, bg=SELECTED_BG if window_selected else PANEL_BG, fg=TEXT,
            activebackground=BTN_ACTIVE_BG, activeforeground=TEXT, relief="flat", bd=1,
            highlightthickness=2, highlightbackground=SELECTED_BORDER if window_selected else BORDER,
            padx=16, pady=10,
        )
        self._window_btn.pack(anchor="w", fill="x")

        self.fit_toggle = ToggleButton(top_row, "Fit All", active=graph.fit_all, on_change=self._pick_fit_all)
        self.fit_toggle.pack(side="left", padx=(10, 0), pady=(16, 0))

        self.zero_toggle = ToggleButton(self, "Start Y at 0", active=graph.y_zero_based,
                                         on_change=self._pick_y_zero_based)
        self.zero_toggle.pack(fill="x", padx=14, pady=(10, 10))

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

    def _pick_fit_all(self, enabled: bool) -> None:
        if enabled:
            self._graph.set_fit_all()
        else:
            self._graph.set_window(self._graph.window_seconds)
        window_selected = not self._graph.fit_all
        self._window_btn.config(
            bg=SELECTED_BG if window_selected else PANEL_BG,
            highlightbackground=SELECTED_BORDER if window_selected else BORDER,
        )


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _nice_step(raw_step: float) -> float:
    """Smallest value from {1, 2, 5} x 10**k (k >= 0) that is >= raw_step -
    always a whole number, since k never goes negative."""
    if raw_step <= 0:
        return 1.0
    k = 0
    while True:
        for candidate in (1, 2, 5):
            step = candidate * (10 ** k)
            if step >= raw_step:
                return float(step)
        k += 1


def _axis_ticks(lo: float, hi: float, zero_based: bool) -> tuple[list[float], int]:
    """Tick values (in V or A) for one axis, plus how many decimal places to
    display them with. Narrow spans (below FINE_STEP_THRESHOLD_BASE) use a
    fixed one-decimal step rather than collapsing to just 2-3 whole-volt/amp
    gridlines; wider spans use a standard 1/2/5 x10**n "nice step", always a
    whole number."""
    eff_lo = min(0.0, lo) if zero_based else lo
    span = max(hi - eff_lo, 1e-9)
    if span < FINE_STEP_THRESHOLD_BASE:
        step = FINE_STEP
    else:
        step = _nice_step(span / NICE_STEP_TARGET_ROWS)
    decimals = 1 if step < 1 else 0

    nice_lo = math.floor(eff_lo / step) * step
    nice_hi = math.ceil(hi / step) * step
    if nice_hi <= nice_lo:
        nice_hi = nice_lo + step
    rows = round((nice_hi - nice_lo) / step)
    ticks = [nice_lo + step * i for i in range(rows + 1)]
    return ticks, decimals
