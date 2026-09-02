"""Touch-kiosk-friendly dual-line strip chart: voltage (left axis) and
current (right axis) against time, on a shared canvas. Redraws are
decimated to the canvas width and throttled by the caller (app.py) rather
than on every sample, since redrawing a long polyline every frame is the
kind of thing that makes a Pi Zero feel broken."""
from __future__ import annotations

import tkinter as tk
from collections import deque

VOLTAGE_COLOR = "#4fc3f7"
CURRENT_COLOR = "#ffb74d"
GRID_COLOR = "#2a2a2a"
AXIS_TEXT_COLOR = "#aaaaaa"
BG_COLOR = "#111111"

MARGIN_L = 60
MARGIN_R = 60
MARGIN_T = 16
MARGIN_B = 24


class DualLineGraph(tk.Canvas):
    def __init__(self, master, history_seconds: int = 300, **kw):
        kw.setdefault("bg", BG_COLOR)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self.history_seconds = history_seconds
        self._points: deque[tuple[float, float, float]] = deque(maxlen=2000)
        self.bind("<Configure>", lambda e: self.redraw())

    def add_sample(self, t: float, voltage_v: float, current_a: float) -> None:
        self._points.append((t, voltage_v, current_a))

    def clear(self) -> None:
        self._points.clear()
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10 or not self._points:
            return

        plot_w = max(1, w - MARGIN_L - MARGIN_R)
        plot_h = max(1, h - MARGIN_T - MARGIN_B)

        t_max = self._points[-1][0]
        t_min = t_max - self.history_seconds
        pts = [p for p in self._points if p[0] >= t_min]
        if len(pts) < 2:
            return

        # decimate to roughly one sample per pixel column
        if len(pts) > plot_w:
            step = len(pts) // plot_w
            pts = pts[::step]

        volts = [p[1] for p in pts]
        amps = [p[2] for p in pts]
        v_lo, v_hi = _padded_range(volts)
        a_lo, a_hi = _padded_range(amps)

        def x_of(t: float) -> float:
            span = max(1e-6, t_max - t_min)
            return MARGIN_L + (t - t_min) / span * plot_w

        def y_of(val: float, lo: float, hi: float) -> float:
            span = max(1e-6, hi - lo)
            return MARGIN_T + plot_h - (val - lo) / span * plot_h

        self._draw_grid(w, h, plot_w, plot_h, v_lo, v_hi, a_lo, a_hi)

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

    def _draw_grid(self, w, h, plot_w, plot_h, v_lo, v_hi, a_lo, a_hi):
        rows = 4
        for i in range(rows + 1):
            y = MARGIN_T + plot_h * i / rows
            self.create_line(MARGIN_L, y, MARGIN_L + plot_w, y, fill=GRID_COLOR)
            v_val = v_hi - (v_hi - v_lo) * i / rows
            a_val = a_hi - (a_hi - a_lo) * i / rows
            self.create_text(MARGIN_L - 6, y, text=f"{v_val:.2f}", fill=VOLTAGE_COLOR, anchor="e", font=("TkDefaultFont", 8))
            self.create_text(MARGIN_L + plot_w + 6, y, text=f"{a_val:.2f}", fill=CURRENT_COLOR, anchor="w", font=("TkDefaultFont", 8))
        self.create_rectangle(MARGIN_L, MARGIN_T, MARGIN_L + plot_w, MARGIN_T + plot_h, outline=GRID_COLOR)


def _padded_range(values: list[float]) -> tuple[float, float]:
    lo, hi = min(values), max(values)
    if hi - lo < 1e-6:
        lo -= 0.5
        hi += 0.5
    pad = (hi - lo) * 0.1
    return lo - pad, hi + pad
