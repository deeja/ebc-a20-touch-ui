from __future__ import annotations

import os
import queue
import time
import tkinter as tk

from ebc import config as cfgmod
from ebc.device import EbcDevice
from ebc.mock_device import MockEbcDevice
from ebc.sequencer import AutoCycleController

from .graph import DualLineGraph
from .settings_screen import SettingsScreen
from .widgets import (
    ACCENT_BLUEGREY,
    ACCENT_GREEN,
    ACCENT_RED,
    BG,
    BTN_BG,
    TEXT,
    TEXT_MUTED,
    ReadoutTile,
    big_button,
    configure_ttk_style,
)

# JRP7006 is a 1024x600 landscape touchscreen; default to that but always
# read the real screen size at runtime so this also runs windowed on a dev
# machine.
DEFAULT_W, DEFAULT_H = 1024, 600


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("EBC-A20 Battery Tester")
        self.configure(bg=BG)
        self.geometry(f"{DEFAULT_W}x{DEFAULT_H}")

        configure_ttk_style(self)

        self.device = None
        self._connect_thread = None
        self.test_config = cfgmod.TestConfig()

        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

        self.connect_screen = ConnectScreen(self.container, self)
        self.main_screen = MainScreen(self.container, self)
        self.settings_screen = SettingsScreen(self.container, self)
        for screen in (self.connect_screen, self.main_screen, self.settings_screen):
            screen.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._fullscreen = False

        if os.environ.get("EBC_KIOSK"):
            self.config(cursor="none")
            self._toggle_fullscreen(True)
        else:
            # Only bound outside kiosk mode: with no window manager on the Pi,
            # un-fullscreening leaves a titlebar-less window with no way to
            # move or close it.
            self.bind("<Escape>", lambda e: self._toggle_fullscreen(False))
            self.bind("<F11>", lambda e: self._toggle_fullscreen())

        self.show_connect()

    def _toggle_fullscreen(self, force: bool | None = None) -> None:
        self._fullscreen = (not self._fullscreen) if force is None else force
        self.attributes("-fullscreen", self._fullscreen)

    def show_connect(self) -> None:
        self.connect_screen.lift()

    def show_main(self) -> None:
        self.main_screen.lift()
        self.main_screen.on_shown()

    def show_settings(self) -> None:
        self.settings_screen.on_shown()
        self.settings_screen.lift()

    def set_device(self, device) -> None:
        self.device = device


class ConnectScreen(tk.Frame):
    def __init__(self, master, app: App):
        super().__init__(master, bg=BG)
        self.app = app

        tk.Label(self, text="EBC-A20 Battery Tester", font=("TkDefaultFont", 22, "bold"),
                 bg=BG, fg=TEXT).pack(pady=(30, 6))
        tk.Label(self, text="Tap a port to connect", font=("TkDefaultFont", 12),
                 bg=BG, fg=TEXT_MUTED).pack(pady=(0, 20))

        body = tk.Frame(self, bg=BG)
        body.pack(expand=True)

        self.ports_container = tk.Frame(body, bg=BG, width=360)
        self.ports_container.pack(fill="x")

        big_button(body, "Refresh Ports", self.refresh_ports).pack(fill="x", pady=(8, 0))
        big_button(body, "Use Simulator (no hardware)", self.connect_simulator, bg=ACCENT_BLUEGREY, fg="white") \
            .pack(fill="x", pady=(16, 0))

        self.status_label = tk.Label(self, text="", font=("TkDefaultFont", 11), bg=BG, fg="#c62828")
        self.status_label.pack(pady=14)

        self.refresh_ports()

    def refresh_ports(self) -> None:
        for child in self.ports_container.winfo_children():
            child.destroy()
        ports = EbcDevice.list_ports()
        if not ports:
            tk.Label(self.ports_container, text="(no serial ports found)", font=("TkDefaultFont", 12),
                     bg=BG, fg=TEXT_MUTED).pack(pady=6)
            return
        for p in ports:
            big_button(self.ports_container, p, lambda port=p: self.connect_to(port), bg=BTN_BG, fg=TEXT) \
                .pack(fill="x", pady=4)

    def connect_to(self, port: str) -> None:
        self.status_label.config(text=f"Connecting to {port}...", fg=TEXT_MUTED)
        self.update_idletasks()
        device = EbcDevice()
        try:
            device.connect(port)
        except Exception as exc:
            self.status_label.config(text=f"Connection failed: {exc}", fg="#c62828")
            return
        self.app.set_device(device)
        self.status_label.config(text="")
        self.app.show_main()

    def connect_simulator(self) -> None:
        device = MockEbcDevice()
        device.connect("SIM")
        self.app.set_device(device)
        self.status_label.config(text="")
        self.app.show_main()


class MainScreen(tk.Frame):
    POLL_MS = 150
    REDRAW_MS = 400

    def __init__(self, master, app: App):
        super().__init__(master, bg=BG)
        self.app = app
        self._t0 = None

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(top, text="EBC-A20", font=("TkDefaultFont", 14, "bold"), bg=BG, fg=TEXT).pack(side="left")
        self.status_dot = tk.Label(top, text="●", font=("TkDefaultFont", 14), bg=BG, fg="#2e7d32")
        self.status_dot.pack(side="left", padx=(8, 0))
        self.status_text = tk.Label(top, text="Connected", font=("TkDefaultFont", 12), bg=BG, fg=TEXT_MUTED)
        self.status_text.pack(side="left", padx=(4, 0))
        big_button(top, "Disconnect", self.disconnect, bg=ACCENT_RED, fg="white").pack(side="right")

        self.graph = DualLineGraph(self, history_seconds=300)
        self.graph.pack(fill="both", expand=True, padx=10, pady=4)

        readouts = tk.Frame(self, bg=BG)
        readouts.pack(fill="x", padx=10, pady=4)
        self.tile_voltage = ReadoutTile(readouts, "VOLTAGE")
        self.tile_current = ReadoutTile(readouts, "CURRENT")
        self.tile_capacity = ReadoutTile(readouts, "CAPACITY")
        self.tile_status = ReadoutTile(readouts, "STATUS")
        for i, tile in enumerate((self.tile_voltage, self.tile_current, self.tile_capacity, self.tile_status)):
            tile.grid(row=0, column=i, sticky="ew", padx=4)
            readouts.grid_columnconfigure(i, weight=1)

        controls = tk.Frame(self, bg=BG)
        controls.pack(fill="x", padx=10, pady=(4, 10))

        mode_info = tk.Frame(controls, bg=BG)
        mode_info.pack(side="left", fill="x", expand=True)
        self.mode_label = tk.Label(mode_info, text="", font=("TkDefaultFont", 13, "bold"), bg=BG, fg=TEXT)
        self.mode_label.pack(anchor="w")
        self.sequencer_label = tk.Label(mode_info, text="", font=("TkDefaultFont", 11), bg=BG, fg="#0277bd")
        self.sequencer_label.pack(anchor="w")

        btns = tk.Frame(controls, bg=BG)
        btns.pack(side="right")
        big_button(btns, "Configure", self.open_settings, bg=ACCENT_BLUEGREY, fg="white").pack(side="left", padx=6)
        big_button(btns, "Start", self.start_test, bg=ACCENT_GREEN, fg="white").pack(side="left", padx=6)
        big_button(btns, "Stop", self.stop_test, bg=ACCENT_RED, fg="white").pack(side="left", padx=6)

        self.sequencer: AutoCycleController | None = None

    def on_shown(self) -> None:
        self._cancel_loops()
        self._t0 = None
        self.graph.clear()
        self.mode_label.config(text=self.app.test_config.summary())
        self.sequencer_label.config(text="")
        self._poll_job = self.after(self.POLL_MS, self._drain_queue)
        self._redraw_job = self.after(self.REDRAW_MS, self._redraw_loop)

    def open_settings(self) -> None:
        self.app.show_settings()

    def _cancel_loops(self) -> None:
        for attr in ("_poll_job", "_redraw_job"):
            job = getattr(self, attr, None)
            if job is not None:
                self.after_cancel(job)
            setattr(self, attr, None)

    def _drain_queue(self) -> None:
        device = self.app.device
        if device is None:
            self._poll_job = None
            return
        try:
            while True:
                sample = device.sample_queue.get_nowait()
                self._apply_sample(sample)
        except queue.Empty:
            pass

        if not getattr(device, "connected", True):
            self.status_dot.config(fg="#c62828")
            self.status_text.config(text=device.last_error or "Disconnected")

        if self.sequencer is not None:
            self.sequencer.tick(time.monotonic())
            self.sequencer_label.config(text=self.sequencer.status_text(time.monotonic()))
            if self.sequencer.finished:
                self.sequencer = None

        self._poll_job = self.after(self.POLL_MS, self._drain_queue)

    def _apply_sample(self, sample) -> None:
        if self._t0 is None:
            self._t0 = sample.timestamp
        self.graph.add_sample(sample.timestamp - self._t0, sample.voltage_v, sample.current_a)
        self.tile_voltage.set(f"{sample.voltage_v:.2f} V")
        self.tile_current.set(f"{sample.current_a:.3f} A")
        self.tile_capacity.set(f"{sample.capacity_mah} mAh")
        self.tile_status.set(sample.status_text)
        if self.sequencer is not None:
            self.sequencer.on_sample(sample)

    def _redraw_loop(self) -> None:
        if self.app.device is None:
            self._redraw_job = None
            return
        self.graph.redraw()
        self._redraw_job = self.after(self.REDRAW_MS, self._redraw_loop)

    def start_test(self) -> None:
        device = self.app.device
        if device is None:
            return
        cfg = self.app.test_config
        self.mode_label.config(text=cfg.summary())
        if cfg.mode == cfgmod.MODE_DSC_CC:
            device.start_discharge_cc(cfg.dsc_cc_current_ma, cfg.dsc_cc_cutoff_mv, cfg.dsc_cc_time_min)
        elif cfg.mode == cfgmod.MODE_DSC_CP:
            device.start_discharge_cp(cfg.dsc_cp_power_w, cfg.dsc_cp_cutoff_mv, cfg.dsc_cp_time_min)
        elif cfg.mode == cfgmod.MODE_CHG_CV:
            device.start_charge_cv(cfg.chg_cv_current_ma, cfg.chg_cv_voltage_mv, cfg.chg_cv_cutoff_ma)
        elif cfg.mode == cfgmod.MODE_REPEAT:
            self.sequencer = AutoCycleController(device, cfg, time.monotonic())
            self.sequencer_label.config(text=self.sequencer.status_text(time.monotonic()))

    def stop_test(self) -> None:
        device = self.app.device
        if device is None:
            return
        if self.sequencer is not None:
            self.sequencer.stop()
            self.sequencer_label.config(text=self.sequencer.status_text(time.monotonic()))
            self.sequencer = None
        else:
            device.stop()

    def disconnect(self) -> None:
        device = self.app.device
        if device is not None:
            device.disconnect()
        self.app.set_device(None)
        self.sequencer = None
        self._cancel_loops()
        self.app.show_connect()
