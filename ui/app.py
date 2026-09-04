from __future__ import annotations

import os
import queue
import time
import tkinter as tk

from ebc import config as cfgmod
from ebc import presets
from ebc import protocol
from ebc.device import EbcDevice
from ebc.mock_device import MockEbcDevice
from ebc.sequencer import (
    ST_DISCHARGING,
    ST_RESTING_BEFORE_CHARGE,
    AutoCycleController,
)

from .graph import DualLineGraph
from .raw_screen import RawScreen
from .settings_screen import SettingsScreen
from .warning_screen import WarningScreen, warning_acknowledged
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
        self.is_configured = False

        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

        self.connect_screen = ConnectScreen(self.container, self)
        self.main_screen = MainScreen(self.container, self)
        self.settings_screen = SettingsScreen(self.container, self)
        self.raw_screen = RawScreen(self.container, self)
        self.warning_screen = WarningScreen(self.container, self.show_connect)
        for screen in (self.connect_screen, self.main_screen, self.settings_screen, self.raw_screen, self.warning_screen):
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

        if warning_acknowledged():
            self.show_connect()
        else:
            self.warning_screen.lift()

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

    def show_raw(self) -> None:
        self.raw_screen.on_shown()
        self.raw_screen.lift()

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
        self._last_sample = None

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=10, pady=(8, 4))

        title_col = tk.Frame(top, bg=BG)
        title_col.pack(side="left")
        self.battery_label = tk.Label(title_col, text="", font=("TkDefaultFont", 12, "bold"), bg=BG, fg=TEXT)
        self.battery_label.pack(anchor="w")
        self.mode_label = tk.Label(title_col, text="", font=("TkDefaultFont", 12), bg=BG, fg=TEXT_MUTED)
        self.mode_label.pack(anchor="w")

        # side="right" packs each new button to the left of the previous
        # one, so pack in reverse of the desired left-to-right order to get
        # Raw / Configure / Start / Stop / Disconnect.
        big_button(top, "Disconnect", self.disconnect, bg=ACCENT_RED, fg="white").pack(side="right")
        self.stop_btn = big_button(top, "Stop", self.stop_test, bg=ACCENT_RED, fg="white")
        self.stop_btn.pack(side="right", padx=(0, 6))
        self.start_btn = big_button(top, "Start", self.start_test, bg=ACCENT_GREEN, fg="white")
        self.start_btn.pack(side="right", padx=(0, 6))
        self.configure_btn = big_button(top, "Configure", self.open_settings, bg=ACCENT_BLUEGREY, fg="white")
        self.configure_btn.pack(side="right", padx=(0, 6))
        # Not gated by _refresh_controls() like configure_btn - viewing raw
        # data while a test is actively running is the main use case.
        big_button(top, "Raw", self.open_raw, bg=BTN_BG, fg=TEXT).pack(side="right", padx=(0, 6))

        mode_info = tk.Frame(self, bg=BG)
        mode_info.pack(fill="x", padx=10, pady=(0, 4))
        # Not packed here: these only take up space (and are only packed)
        # while they actually have something to say, so an idle screen
        # doesn't reserve blank lines the graph could otherwise fill.
        self.sequencer_label = tk.Label(mode_info, text="", font=("TkDefaultFont", 11), bg=BG, fg="#0277bd")
        self.warning_label = tk.Label(mode_info, text="", font=("TkDefaultFont", 11, "bold"), bg=BG, fg=ACCENT_RED)

        # Readouts are pinned to the bottom (packed with side="bottom" before
        # the graph is packed) so the graph - packed last with expand=True -
        # fills whatever vertical space is left between the top info block
        # and the readouts, instead of the readouts trailing the graph.
        readouts = tk.Frame(self, bg=BG)
        readouts.pack(side="bottom", fill="x", padx=10, pady=(4, 10))
        self.tile_voltage = ReadoutTile(readouts, "VOLTAGE")
        self.tile_current = ReadoutTile(readouts, "CURRENT")
        self.tile_capacity = ReadoutTile(readouts, "CAPACITY")
        self.tile_status = ReadoutTile(readouts, "STATUS")
        for i, tile in enumerate((self.tile_voltage, self.tile_current, self.tile_capacity, self.tile_status)):
            tile.grid(row=0, column=i, sticky="ew", padx=4)
            readouts.grid_columnconfigure(i, weight=1)

        self.graph = DualLineGraph(self, history_seconds=300)
        self.graph.pack(fill="both", expand=True, padx=10, pady=4)

        self.sequencer: AutoCycleController | None = None

    @staticmethod
    def _set_label_text(label: tk.Label, text: str) -> None:
        """Show/hide a label based on whether it has anything to say, so an
        empty sequencer/warning line doesn't reserve blank vertical space
        the graph could otherwise fill."""
        label.config(text=text)
        if text:
            if not label.winfo_manager():
                label.pack(anchor="w")
        else:
            label.pack_forget()

    def _set_sequencer_text(self, text: str) -> None:
        self._set_label_text(self.sequencer_label, text)

    def _set_warning_text(self, text: str) -> None:
        self._set_label_text(self.warning_label, text)

    def on_shown(self) -> None:
        self._cancel_loops()
        self._t0 = None
        self._last_sample = None
        self.graph.clear()
        cfg = self.app.test_config
        if self.app.is_configured:
            self.battery_label.config(text=presets.describe(cfg.preset_key, cfg.cell_count))
            self.mode_label.config(text=cfg.summary())
        else:
            self.battery_label.config(text="Not configured")
            self.mode_label.config(text="Tap Configure to select a battery and test mode")
        self._set_sequencer_text("")
        self._set_warning_text("")
        self.tile_status.set("--")
        self.graph.set_targets(*self._current_targets())
        self._refresh_controls()
        self._poll_job = self.after(self.POLL_MS, self._drain_queue)
        self._redraw_job = self.after(self.REDRAW_MS, self._redraw_loop)

    def _current_targets(self) -> tuple[float | None, float | None]:
        """Configured cutoff/setpoint (voltage, current) for the graph's
        target line, in V/A - depends on mode, and for Repeat also on
        which leg (charge vs. discharge) the sequencer is currently in.
        No battery/mode has actually been chosen until Configure is saved
        at least once, so there's nothing to target yet."""
        if not self.app.is_configured:
            return None, None
        cfg = self.app.test_config
        if cfg.mode == cfgmod.MODE_DSC_CC:
            return cfg.dsc_cc_cutoff_mv / 1000.0, cfg.dsc_cc_current_ma / 1000.0
        if cfg.mode == cfgmod.MODE_DSC_CP:
            return cfg.dsc_cp_cutoff_mv / 1000.0, None
        if cfg.mode == cfgmod.MODE_CHG_CV:
            return cfg.chg_cv_voltage_mv / 1000.0, cfg.chg_cv_current_ma / 1000.0
        if cfg.mode == cfgmod.MODE_REPEAT:
            discharging = self.sequencer is not None and self.sequencer.state in (
                ST_DISCHARGING, ST_RESTING_BEFORE_CHARGE,
            )
            if discharging:
                return cfg.repeat_discharge_cutoff_mv / 1000.0, cfg.repeat_discharge_current_ma / 1000.0
            return cfg.repeat_charge_voltage_mv / 1000.0, cfg.repeat_charge_current_ma / 1000.0
        return None, None

    def _is_running(self) -> bool:
        if self.sequencer is not None and not self.sequencer.finished:
            return True
        return self._last_sample is not None and protocol.is_active_status(self._last_sample.status_code)

    def _refresh_controls(self) -> None:
        running = self._is_running()
        self.start_btn.config(state=tk.NORMAL if (self.app.is_configured and not running) else tk.DISABLED)
        self.configure_btn.config(state=tk.DISABLED if running else tk.NORMAL)

    def open_settings(self) -> None:
        self.app.show_settings()

    def open_raw(self) -> None:
        self.app.show_raw()

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

        try:
            while True:
                record = device.raw_queue.get_nowait()
                self.app.raw_screen.append_record(record)
        except queue.Empty:
            pass

        if not getattr(device, "connected", True):
            self.app.connect_screen.status_label.config(
                text=f"Disconnected: {device.last_error}" if device.last_error else "Device disconnected",
                fg="#c62828",
            )
            self.disconnect()
            return

        if self.sequencer is not None:
            self.sequencer.tick(time.monotonic())
            self._set_sequencer_text(self.sequencer.status_text(time.monotonic()))
            if self.sequencer.finished:
                self.sequencer = None
            self.graph.set_targets(*self._current_targets())

        self._refresh_controls()
        self._poll_job = self.after(self.POLL_MS, self._drain_queue)

    def _apply_sample(self, sample) -> None:
        self._last_sample = sample
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

    @staticmethod
    def _voltage_bounds_mv(cfg) -> tuple[int, int]:
        """Sane (lo, hi) voltage band for the currently configured mode's
        own parameters - discharge modes expect the pack above its cutoff
        (up to the device's hardware ceiling), charge modes expect it below
        the target charge voltage."""
        if cfg.mode == cfgmod.MODE_DSC_CC:
            return cfg.dsc_cc_cutoff_mv, presets.CHARGE_VOLTAGE_CEILING_MV
        if cfg.mode == cfgmod.MODE_DSC_CP:
            return cfg.dsc_cp_cutoff_mv, presets.CHARGE_VOLTAGE_CEILING_MV
        if cfg.mode == cfgmod.MODE_CHG_CV:
            return 0, cfg.chg_cv_voltage_mv
        if cfg.mode == cfgmod.MODE_REPEAT:
            return 0, cfg.repeat_charge_voltage_mv
        return 0, presets.CHARGE_VOLTAGE_CEILING_MV

    def start_test(self) -> None:
        device = self.app.device
        if device is None:
            return
        if not self.app.is_configured or self._is_running():
            return
        cfg = self.app.test_config

        sample = self._last_sample
        if sample is None or sample.voltage_mv <= 0:
            self._set_warning_text("Battery not connected")
            return
        lo_mv, hi_mv = self._voltage_bounds_mv(cfg)
        if not (lo_mv <= sample.voltage_mv <= hi_mv):
            self._set_warning_text("Battery voltage outside range for these settings")
            return
        self._set_warning_text("")

        self.mode_label.config(text=cfg.summary())
        if cfg.mode == cfgmod.MODE_DSC_CC:
            device.start_discharge_cc(cfg.dsc_cc_current_ma, cfg.dsc_cc_cutoff_mv, cfg.dsc_cc_time_min)
        elif cfg.mode == cfgmod.MODE_DSC_CP:
            device.start_discharge_cp(cfg.dsc_cp_power_w, cfg.dsc_cp_cutoff_mv, cfg.dsc_cp_time_min)
        elif cfg.mode == cfgmod.MODE_CHG_CV:
            device.start_charge_cv(cfg.chg_cv_current_ma, cfg.chg_cv_voltage_mv, cfg.chg_cv_cutoff_ma)
        elif cfg.mode == cfgmod.MODE_REPEAT:
            self.sequencer = AutoCycleController(device, cfg, time.monotonic())
            self._set_sequencer_text(self.sequencer.status_text(time.monotonic()))
        self._refresh_controls()

    def stop_test(self) -> None:
        device = self.app.device
        if device is None:
            return
        if self.sequencer is not None:
            self.sequencer.stop()
            self._set_sequencer_text(self.sequencer.status_text(time.monotonic()))
            self.sequencer = None
        else:
            device.stop()
        self._refresh_controls()

    def disconnect(self) -> None:
        device = self.app.device
        if device is not None:
            device.disconnect()
        self.app.set_device(None)
        self.sequencer = None
        self._cancel_loops()
        self.app.show_connect()
