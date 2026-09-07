"""Touch-kiosk-friendly dual-line strip chart: voltage (left axis) and
current (right axis) against time, on a shared canvas. Redraws are
decimated to the canvas width and throttled by the caller (app.py) rather
than on every sample, since redrawing a long polyline every frame is the
kind of thing that makes a Pi Zero feel broken.

Double-tapping the chart opens a touch popup to pick how the time axis
behaves (a scrolling window of a chosen width, or "Fit All" to show the
whole run) - that choice is remembered across restarts via ui/prefs.py.
Double-tap rather than a single tap so a stray touch while watching a
live test doesn't accidentally pop up the menu. Dragging a finger/mouse
across the chart instead shows a value tooltip and crosshair for the
nearest sample - a single tap alone (no drag, no second tap) does
nothing."""
from __future__ import annotations

import csv
import math
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import deque
from datetime import datetime

from . import prefs as prefsmod
from .widgets import (
    ACCENT_RED,
    BORDER,
    BTN_ACTIVE_BG,
    BTN_BG,
    ConfirmDialog,
    FONT_LARGE,
    FONT_MED,
    FONT_SMALL,
    InfoDialog,
    NumpadDialog,
    PANEL_BG,
    SELECTED_BG,
    SELECTED_BORDER,
    TEXT,
    TEXT_MUTED,
    ToggleButton,
    big_button,
    center_on_parent,
)

VOLTAGE_COLOR = "#c62828"
CURRENT_COLOR = "#0288d1"
CAPACITY_COLOR = "#2e7d32"
VOLTAGE_GRID_COLOR = "#fadbdb"
CURRENT_GRID_COLOR = "#d6ecfa"
CAPACITY_GRID_COLOR = "#dcedc8"
GRID_COLOR = "#dddddd"
AXIS_TEXT_COLOR = "#666666"
HINT_TEXT_COLOR = "#aaaaaa"
CROSSHAIR_COLOR = "#999999"
BG_COLOR = "#ffffff"

# Voltage and Current both live on the left, each its own auto-ranging scale,
# as two stacked label columns (Voltage innermost, Current outer) - so the
# left margin needs room for two of what used to be a single column.
LEFT_COL_W = 34
MARGIN_L = LEFT_COL_W * 2
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
        self.fit_all = True
        self.y_zero_based = False
        self._load_view_settings()

        # Resolved once rather than passing raw ("TkDefaultFont", N) tuples
        # into create_text() on every redraw - Tk re-parses a tuple spec
        # into a font object on every call otherwise, which adds up across
        # the many labels drawn per redraw on slow hardware.
        self._font_axis = tkfont.Font(family="TkDefaultFont", size=8)
        self._font_top_hint = tkfont.Font(family="TkDefaultFont", size=11)
        self._font_overlay = tkfont.Font(family="TkDefaultFont", size=27)

        # Current test mode/battery preset (e.g. "DSC_CC", "liion") - set by
        # the caller (app.py, which knows about TestConfig) via
        # set_test_info(), used only to label Export's filename.
        self.test_label = ""

        # (elapsed_s, voltage_v, current_a, capacity_mah, wall_clock_time.time())
        # - the wall-clock time is only for Export's start/end filename, not
        # for plotting (that uses elapsed_s against the shared t0 origin).
        self._points: deque[tuple[float, float, float, float, float]] = deque(maxlen=2000)

        self._press_xy: tuple[int, int] | None = None
        self._dragging = False
        self._drag_x: int | None = None
        self._overlay_items: list[int] = []

        # Geometry/domain from the most recent redraw() - lets a drag move
        # the crosshair/tooltip cheaply (no full recompute) between the
        # throttled full redraws the caller schedules.
        self._last_pts: list[tuple[float, float, float, float, float]] = []
        self._last_t_min = 0.0
        self._last_t_max = 0.0
        self._last_plot_w: int | None = None
        self._last_plot_h = 0

        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Double-Button-1>", self._on_double_tap)

    def add_sample(self, t: float, voltage_v: float, current_a: float, capacity_mah: float) -> None:
        self._points.append((t, voltage_v, current_a, capacity_mah, time.time()))

    def clear(self) -> None:
        self._points.clear()
        self.redraw()

    # -- view mode (scrolling window vs. fit-all) --------------------------
    def _load_view_settings(self) -> None:
        saved = prefsmod.load_prefs().get(PREFS_KEY, {})
        self.fit_all = bool(saved.get("fit_all", True))
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

    def set_test_info(self, mode: str, preset_key: str) -> None:
        self.test_label = f"{mode}_{preset_key}" if mode else ""

    # -- double-tap (open view options) vs. drag (tooltip) ------------------
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
        if self._press_xy is None:
            # A release with no matching press on this canvas - e.g. the tail
            # end of a click on the view-options popup that closed mid-click
            # (its grab let go, so this release leaked through to the chart)
            # - ignore it rather than treat it as a real tap/drag end.
            return
        was_dragging = self._dragging
        self._press_xy = None
        self._dragging = False
        self._drag_x = None
        if was_dragging:
            self.redraw()
        # A plain single tap (no drag) does nothing on its own - opening the
        # view options menu needs a second tap, see _on_double_tap, so an
        # accidental touch while watching a live test doesn't pop it up.

    def _on_double_tap(self, event) -> None:
        self._press_xy = None
        self._dragging = False
        self._drag_x = None
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
        if self.fit_all:
            t_min = self._points[0][0]
        else:
            # Don't let the window's left edge extend before any real data
            # exists - otherwise the line only fills the right portion of
            # the plot until enough time has passed to fill the whole
            # configured window, which reads as "the lines don't reach all
            # the way left". Fill the available width with what's there
            # instead; once there's more than window_seconds of data this
            # is equivalent to the fixed scrolling window as before.
            t_min = max(self._points[0][0], t_max - self.window_seconds)
        pts = [p for p in self._points if p[0] >= t_min]
        if len(pts) < 2:
            self._last_plot_w = None
            return

        v_min, v_max = min(p[1] for p in pts), max(p[1] for p in pts)
        a_min, a_max = min(p[2] for p in pts), max(p[2] for p in pts)
        cap_min, cap_max = min(p[3] for p in pts), max(p[3] for p in pts)

        # decimate to roughly one sample per pixel column for the polyline -
        # min/max/ticks above are computed from the full-resolution pts so a
        # narrow spike isn't lost to decimation.
        plot_pts = pts
        if len(plot_pts) > plot_w:
            step = len(plot_pts) // plot_w
            plot_pts = plot_pts[::step]

        v_ticks, v_decimals = _axis_ticks(v_min, v_max, self.y_zero_based, min_span=1.0, center_offset=-0.10)
        a_ticks, a_decimals = _axis_ticks(a_min, a_max, self.y_zero_based, min_span=1.0, center_offset=0.10)
        cap_ticks, cap_decimals = _axis_ticks(cap_min, cap_max, self.y_zero_based, whole_only=True, min_span=1.0)
        v_lo, v_hi = v_ticks[0], v_ticks[-1]
        a_lo, a_hi = a_ticks[0], a_ticks[-1]
        cap_lo, cap_hi = cap_ticks[0], cap_ticks[-1]

        def x_of(t: float) -> float:
            span = max(1e-6, t_max - t_min)
            return MARGIN_L + (t - t_min) / span * plot_w

        def y_of(val: float, lo: float, hi: float) -> float:
            span = max(1e-6, hi - lo)
            return MARGIN_T + plot_h - (val - lo) / span * plot_h

        self._draw_axis_grid(plot_w, plot_h, v_ticks, v_decimals, v_lo, v_hi,
                              VOLTAGE_GRID_COLOR, VOLTAGE_COLOR, "V", MARGIN_L - 6, "e")
        self._draw_axis_grid(plot_w, plot_h, a_ticks, a_decimals, a_lo, a_hi,
                              CURRENT_GRID_COLOR, CURRENT_COLOR, "A", MARGIN_L - 6 - LEFT_COL_W, "e")
        self._draw_axis_grid(plot_w, plot_h, cap_ticks, cap_decimals, cap_lo, cap_hi,
                              CAPACITY_GRID_COLOR, CAPACITY_COLOR, "mAh", MARGIN_L + plot_w + 6, "w")
        self._draw_time_grid(plot_w, plot_h, t_min, t_max)

        v_line = []
        a_line = []
        cap_line = []
        for t, v, a, cap, _wall in plot_pts:
            x = x_of(t)
            v_line += [x, y_of(v, v_lo, v_hi)]
            a_line += [x, y_of(a, a_lo, a_hi)]
            cap_line += [x, y_of(cap, cap_lo, cap_hi)]

        self.create_line(*v_line, fill=VOLTAGE_COLOR, width=4)
        self.create_line(*a_line, fill=CURRENT_COLOR, width=4)
        self.create_line(*cap_line, fill=CAPACITY_COLOR, width=4)

        self.create_text(w / 2, 8, text="double-tap chart for view options, drag for values", fill=HINT_TEXT_COLOR,
                          anchor="n", font=self._font_top_hint)

        self._last_pts = pts
        self._last_t_min, self._last_t_max = t_min, t_max
        self._last_plot_w, self._last_plot_h = plot_w, plot_h

        if self._dragging and self._drag_x is not None:
            self._update_overlay(self._drag_x)

    def _draw_axis_grid(self, plot_w, plot_h, ticks, decimals, lo, hi, line_color, text_color, unit_label,
                         label_x, anchor) -> None:
        span = max(1e-9, hi - lo)
        for val in ticks:
            y = MARGIN_T + plot_h - (val - lo) / span * plot_h
            self.create_line(MARGIN_L, y, MARGIN_L + plot_w, y, fill=line_color)
            label = f"{val:.{decimals}f}{unit_label}"
            self.create_text(label_x, y, text=label, fill=text_color, anchor=anchor, font=self._font_axis)

    def _draw_time_grid(self, plot_w, plot_h, t_min, t_max) -> None:
        cols = 4
        for i in range(cols + 1):
            x = MARGIN_L + plot_w * i / cols
            self.create_line(x, MARGIN_T, x, MARGIN_T + plot_h, fill=GRID_COLOR)
            t_val = t_min + (t_max - t_min) * i / cols
            self.create_text(x, MARGIN_T + plot_h + 4, text=_format_elapsed(t_val), fill=AXIS_TEXT_COLOR,
                              anchor="n", font=self._font_axis)
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
        a_text = f"{sample[2]:.1f}A"
        cap_text = f"{sample[3]:.0f}mAh"
        text = f"{_format_elapsed(sample[0])}\n{v_text}\n{a_text}\n{cap_text}"

        right_side = x > MARGIN_L + self._last_plot_w / 2
        anchor = "ne" if right_side else "nw"
        tx = x - 8 if right_side else x + 8
        ty = MARGIN_T + 6

        label = self.create_text(tx, ty, text=text, fill=TEXT, anchor=anchor, font=self._font_overlay, justify="left")
        bbox = self.bbox(label)
        if bbox:
            pad = 4
            rect = self.create_rectangle(bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad,
                                          fill=BG_COLOR, outline=GRID_COLOR)
            self.tag_lower(rect, label)
            self._overlay_items.append(rect)
        self._overlay_items.append(label)


class GraphViewDialog(tk.Toplevel):
    """Touch popup opened by double-tapping the chart: pick a scrolling
    time window, jump to Fit All, or clear the saved view choice.

    Follows the same show/center/grab_set ordering as NumpadDialog
    (widgets.py) - grabbing input before the window is viewable is what
    made the app appear to freeze there, so the same care applies here.
    Fully modal like the app's other dialogs (ConfirmDialog/InfoDialog/
    NumpadDialog): only the explicit "Close" button (or Export/Clear
    Graph, which also dismiss it) closes it - no tap-outside-to-dismiss,
    so an accidental touch elsewhere on screen can't lose the open menu."""

    def __init__(self, master: tk.Misc, graph: DualLineGraph):
        super().__init__(master, bg=PANEL_BG)
        self.overrideredirect(True)
        self.withdraw()
        self._graph = graph

        top_row = tk.Frame(self, bg=PANEL_BG)
        top_row.pack(fill="x", padx=14, pady=(14, 0))

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

        big_button(self, "Export", self._export_graph, bg=BTN_BG, fg=TEXT).pack(fill="x", padx=14, pady=(0, 10))

        big_button(self, "Clear Graph", self._clear_graph, bg=ACCENT_RED, fg="white").pack(fill="x", padx=14, pady=(0, 10))

        big_button(self, "Close", self.destroy, bg=BTN_BG, fg=TEXT).pack(fill="x", padx=14, pady=(0, 14))

        self.transient(master.winfo_toplevel())
        center_on_parent(self, master.winfo_toplevel())
        self.lift()
        self.focus_force()
        self.grab_set()

    def _open_window_numpad(self) -> None:
        NumpadDialog(self, "SCROLL WINDOW", WINDOW_UNITS, self._on_window_numpad_accept)

    def _on_window_numpad_accept(self, value: float, scale: float) -> None:
        seconds = max(MIN_WINDOW_S, min(MAX_WINDOW_S, int(round(value * scale))))
        self._graph.set_window(seconds)
        # Deferred, not self.destroy() directly - this runs from inside the
        # NumpadDialog's own _confirm(), which is a *child* of self (parented
        # here so it centers over this popup). Destroying self synchronously
        # would cascade-destroy that child mid-callback, before its own
        # cleanup runs. after_idle lets the child finish its own destroy()
        # first, on the next event-loop pass.
        self.after_idle(self.destroy)

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

    def _clear_graph(self) -> None:
        ConfirmDialog(self, "Clear all graph data?", self._do_clear_graph, confirm_label="Clear")

    def _do_clear_graph(self) -> None:
        self._graph.clear()
        # Deferred - same reasoning as _on_window_numpad_accept: this runs
        # from inside ConfirmDialog's own _confirm(), a child of self.
        self.after_idle(self.destroy)

    def _export_graph(self) -> None:
        # Parented to the graph (which outlives this popup) rather than
        # self, since the menu closes right after - a dialog parented to a
        # destroyed Toplevel would be destroyed along with it.
        graph = self._graph
        points = list(graph._points)
        if not points:
            InfoDialog(graph, "Nothing to export yet")
            self.destroy()
            return
        start_iso = datetime.fromtimestamp(points[0][4]).strftime("%Y-%m-%dT%H-%M-%S")
        end_iso = datetime.fromtimestamp(points[-1][4]).strftime("%Y-%m-%dT%H-%M-%S")
        label_part = f"{graph.test_label}_" if graph.test_label else ""
        path = prefsmod.APP_DATA_DIR / f"graph_export_{label_part}{start_iso}_to_{end_iso}.csv"
        try:
            prefsmod.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["elapsed_s", "timestamp", "voltage_v", "current_a", "capacity_mah"])
                for t, v, a, cap, wall in points:
                    writer.writerow([
                        f"{t:.3f}",
                        datetime.fromtimestamp(wall).isoformat(timespec="seconds"),
                        f"{v:.3f}", f"{a:.3f}", f"{cap:.0f}",
                    ])
            InfoDialog(graph, f"Exported to {path}")
        except OSError as exc:
            InfoDialog(graph, f"Export failed: {exc}")
        self.destroy()


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


def _axis_ticks(lo: float, hi: float, zero_based: bool, whole_only: bool = False,
                 min_span: float = 0.0, center_offset: float = 0.0) -> tuple[list[float], int]:
    """Tick values for one axis, plus how many decimal places to display
    them with. Narrow spans (below FINE_STEP_THRESHOLD_BASE) use a fixed
    one-decimal step rather than collapsing to just 2-3 whole gridlines;
    wider spans use a standard 1/2/5 x10**n "nice step", always a whole
    number. whole_only skips the one-decimal case entirely - for capacity
    (mAh), which the device already reports as a whole number, so unlike
    V/A there's no real sub-unit precision a decimal step would add.

    min_span floors how tight the axis is allowed to zoom in on a nearly-flat
    signal (e.g. an idle battery's voltage barely moving) - below it, tiny
    sensor noise fills the whole plot height and reads as a wild swing. The
    window is widened symmetrically around the data's own midpoint, then
    shifted up to lo=0 if that would otherwise dip negative - voltage/
    current/capacity are never negative quantities, so neither should their
    axis floor be.

    center_offset, applied only while that floor is active, nudges the
    window's centre by this fraction of min_span (positive = data renders
    lower on screen, negative = higher) - so two independently-flat traces
    sharing the same plot area (voltage and current) land at visibly
    different heights instead of drawing directly on top of each other."""
    if min_span > 0 and (hi - lo) < min_span:
        mid = (lo + hi) / 2 + center_offset * min_span
        lo = mid - min_span / 2
        hi = mid + min_span / 2
        if lo < 0:
            hi -= lo
            lo = 0.0
    eff_lo = min(0.0, lo) if zero_based else lo
    span = max(hi - eff_lo, 1e-9)
    if span < FINE_STEP_THRESHOLD_BASE and not whole_only:
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
