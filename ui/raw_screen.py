"""Raw Values screen: every raw device frame (hex) alongside its decoded
fields, for low-level diagnostics of the serial link. Frames are captured
continuously by MainScreen's poll loop (via append_record()) regardless of
which screen is showing - nothing is lost while the user is elsewhere; this
screen only renders (virtual-scrolls) the ones that fit in view while it's
the active screen, mirroring ui/graph.py's DualLineGraph redraw-from-buffer
approach (the only precedent in this codebase for a large, continuously
updated canvas)."""
from __future__ import annotations

import csv
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime

from ebc.protocol import RawFrame

from . import prefs as prefsmod
from .widgets import (
    ACCENT_RED,
    BG,
    BORDER,
    BTN_BG,
    FONT_MED,
    FONT_SMALL,
    PANEL_BG,
    TEXT,
    TEXT_MUTED,
    big_button,
)

EXPORT_DIR = prefsmod.APP_DATA_DIR

ROW_H = 22
HEADER_H = 26
TIME_X = 8
HEX_X = 140
DECODED_X = 459  # HEX_X + (430 - 140) * 1.1 - hex column widened 10%
SCROLLBAR_W = 6

REDRAW_MS = 300
WHEEL_ROWS_PER_NOTCH = 3

HEADER_BG = "#e8e8e8"
GRID_COLOR = "#e0e0e0"
HEX_COLOR = "#546e7a"
DECODED_COLOR = "#1a1a1a"
ERROR_COLOR = "#c62828"
SCROLLBAR_COLOR = "#b0b0b0"


class RawLogView(tk.Canvas):
    def __init__(self, master, **kw):
        kw.setdefault("bg", PANEL_BG)
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", BORDER)
        super().__init__(master, **kw)
        self.records: list[RawFrame] = []
        self.autoscroll = True
        self._scroll_top = 0
        self._drag_start_y: int | None = None
        self._drag_start_top = 0
        self._last_redraw_sig: tuple | None = None

        # Resolved once rather than passing raw font tuples into
        # create_text() on every redraw - see ui/graph.py's DualLineGraph
        # for the same reasoning.
        self._font_header = tkfont.Font(family="TkFixedFont", size=9, weight="bold")
        self._font_row = tkfont.Font(family="TkFixedFont", size=9)

        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-4>", lambda e: self._scroll_by(-WHEEL_ROWS_PER_NOTCH))
        self.bind("<Button-5>", lambda e: self._scroll_by(WHEEL_ROWS_PER_NOTCH))
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)

    def append_record(self, record: RawFrame) -> None:
        self.records.append(record)

    def clear(self) -> None:
        self.records = []
        self._scroll_top = 0
        self.redraw()

    def _visible_rows(self) -> int:
        h = self.winfo_height()
        return max(1, (h - HEADER_H) // ROW_H)

    def _max_scroll_top(self) -> int:
        return max(0, len(self.records) - self._visible_rows())

    def _scroll_by(self, rows: int) -> None:
        self._scroll_top = max(0, min(self._max_scroll_top(), self._scroll_top + rows))
        self.redraw()

    def _on_mousewheel(self, event) -> None:
        # Windows/Mac deliver a signed delta (typically +-120); normalize to
        # a small row count in the opposite direction (wheel up -> scroll up).
        rows = -1 if event.delta > 0 else 1
        self._scroll_by(rows * WHEEL_ROWS_PER_NOTCH)

    def _on_press(self, event) -> None:
        self._drag_start_y = event.y
        self._drag_start_top = self._scroll_top

    def _on_drag(self, event) -> None:
        if self._drag_start_y is None:
            return
        rows_moved = (self._drag_start_y - event.y) // ROW_H
        self._scroll_top = max(0, min(self._max_scroll_top(), self._drag_start_top + rows_moved))
        self.redraw()

    @staticmethod
    def _decoded_text(record: RawFrame) -> tuple[str, str]:
        if record.sample is not None:
            s = record.sample
            text = (
                f"V={s.voltage_mv}mV I={s.current_ma}mA Cap={s.capacity_mah}mAh "
                f"Status=0x{s.status_code:02X} DevType=0x{s.device_type:02X}"
            )
            return text, DECODED_COLOR
        if not record.checksum_ok:
            return "checksum FAIL", ERROR_COLOR
        return f"short frame ({len(record.payload)}b)", ERROR_COLOR

    def redraw(self) -> None:
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return

        visible = self._visible_rows()
        if self.autoscroll:
            self._scroll_top = self._max_scroll_top()
        self._scroll_top = max(0, min(self._max_scroll_top(), self._scroll_top))

        # Nothing about what would be drawn has changed since last time (no
        # new records, no scroll/resize) - skip the delete+rebuild. Redraws
        # driven by RawScreen's periodic loop are the common case this
        # matters for, since most ticks land between new frames arriving.
        sig = (len(self.records), self._scroll_top, w, h)
        if sig == self._last_redraw_sig:
            return
        self._last_redraw_sig = sig

        self.delete("all")
        self.create_rectangle(0, 0, w, HEADER_H, fill=HEADER_BG, outline=GRID_COLOR)
        self.create_text(TIME_X, HEADER_H / 2, text="TIME", anchor="w", font=self._font_header, fill=TEXT_MUTED)
        self.create_text(HEX_X, HEADER_H / 2, text="HEX", anchor="w", font=self._font_header, fill=TEXT_MUTED)
        self.create_text(DECODED_X, HEADER_H / 2, text="DECODED", anchor="w", font=self._font_header, fill=TEXT_MUTED)

        for i in range(visible):
            idx = self._scroll_top + i
            if idx >= len(self.records):
                break
            record = self.records[idx]
            y = HEADER_H + i * ROW_H
            if i % 2 == 1:
                self.create_rectangle(0, y, w, y + ROW_H, fill="#f7f7f7", outline="")
            ts = datetime.fromtimestamp(record.timestamp).strftime("%H:%M:%S.%f")[:-3]
            self.create_text(TIME_X, y + ROW_H / 2, text=ts, anchor="w", font=self._font_row, fill=TEXT)
            hex_text = record.payload.hex(" ").upper()
            self.create_text(HEX_X, y + ROW_H / 2, text=hex_text, anchor="w", font=self._font_row, fill=HEX_COLOR)
            decoded_text, decoded_color = self._decoded_text(record)
            self.create_text(DECODED_X, y + ROW_H / 2, text=decoded_text, anchor="w",
                              font=self._font_row, fill=decoded_color)

        total = len(self.records)
        if total > visible:
            track_h = h - HEADER_H
            thumb_h = max(16, track_h * visible / total)
            thumb_y = HEADER_H + (track_h - thumb_h) * (self._scroll_top / max(1, total - visible))
            self.create_rectangle(w - SCROLLBAR_W, thumb_y, w, thumb_y + thumb_h, fill=SCROLLBAR_COLOR, outline="")


class RawScreen(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self._redraw_job = None

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(top, text="Raw Values", font=("TkDefaultFont", 16, "bold"), bg=BG, fg=TEXT).pack(side="left")
        big_button(top, "Close", self._close, bg=BTN_BG, fg=TEXT).pack(side="right")

        controls = tk.Frame(self, bg=BG)
        controls.pack(fill="x", padx=10, pady=(0, 4))
        big_button(controls, "Export", self._export, bg=BTN_BG, fg=TEXT).pack(side="left")
        big_button(controls, "Clear", self._clear, bg=ACCENT_RED, fg="white").pack(side="left", padx=(6, 0))

        self._autoscroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            controls, text="Autoscroll", variable=self._autoscroll_var, command=self._on_autoscroll_toggle,
            font=FONT_MED, bg=BG, fg=TEXT, activebackground=BG, activeforeground=TEXT, selectcolor=PANEL_BG,
            padx=10, pady=10,
        ).pack(side="left", padx=(12, 0))

        self.count_label = tk.Label(controls, text="", font=FONT_SMALL, bg=BG, fg=TEXT_MUTED)
        self.count_label.pack(side="right")
        self.export_label = tk.Label(controls, text="", font=FONT_SMALL, bg=BG, fg=TEXT_MUTED)
        self.export_label.pack(side="right", padx=(0, 12))

        self.view = RawLogView(self)
        self.view.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def on_shown(self) -> None:
        self.export_label.config(text="")
        self._update_count()
        self.view.redraw()
        self._redraw_loop()

    def append_record(self, record: RawFrame) -> None:
        self.view.append_record(record)

    def _redraw_loop(self) -> None:
        self.view.redraw()
        self._update_count()
        self._redraw_job = self.after(REDRAW_MS, self._redraw_loop)

    def _close(self) -> None:
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
            self._redraw_job = None
        self.app.show_main()

    def _on_autoscroll_toggle(self) -> None:
        self.view.autoscroll = self._autoscroll_var.get()

    def _clear(self) -> None:
        self.view.clear()
        self._update_count()

    def _update_count(self) -> None:
        self.count_label.config(text=f"{len(self.view.records)} frames")

    def _export(self) -> None:
        path = EXPORT_DIR / f"raw_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "hex", "checksum_ok", "voltage_mv", "current_ma",
                                  "capacity_mah", "status_hex", "device_type_hex"])
                for r in self.view.records:
                    ts = datetime.fromtimestamp(r.timestamp).strftime("%H:%M:%S.%f")[:-3]
                    hex_text = r.payload.hex(" ").upper()
                    if r.sample is not None:
                        s = r.sample
                        writer.writerow([ts, hex_text, r.checksum_ok, s.voltage_mv, s.current_ma,
                                          s.capacity_mah, f"0x{s.status_code:02X}", f"0x{s.device_type:02X}"])
                    else:
                        writer.writerow([ts, hex_text, r.checksum_ok, "", "", "", "", ""])
            self.export_label.config(text=f"Exported to {path}")
        except OSError as exc:
            self.export_label.config(text=f"Export failed: {exc}")
