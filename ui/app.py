from __future__ import annotations

import queue
import tkinter as tk
from tkinter import ttk

from ebc.device import EbcDevice
from ebc.mock_device import MockEbcDevice

from .graph import DualLineGraph
from .widgets import NumberStepper, ReadoutTile, big_button

BG = "#0d0d0d"
PANEL_BG = "#1a1a1a"

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

        self.device = None
        self._connect_thread = None

        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

        self.connect_screen = ConnectScreen(self.container, self)
        self.main_screen = MainScreen(self.container, self)
        for screen in (self.connect_screen, self.main_screen):
            screen.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.bind("<Escape>", lambda e: self._toggle_fullscreen(False))
        self.bind("<F11>", lambda e: self._toggle_fullscreen())
        self._fullscreen = False

        self.show_connect()

    def _toggle_fullscreen(self, force: bool | None = None) -> None:
        self._fullscreen = (not self._fullscreen) if force is None else force
        self.attributes("-fullscreen", self._fullscreen)

    def show_connect(self) -> None:
        self.connect_screen.lift()

    def show_main(self) -> None:
        self.main_screen.lift()
        self.main_screen.on_shown()

    def set_device(self, device) -> None:
        self.device = device


class ConnectScreen(tk.Frame):
    def __init__(self, master, app: App):
        super().__init__(master, bg=BG)
        self.app = app

        tk.Label(self, text="EBC-A20 Battery Tester", font=("TkDefaultFont", 22, "bold"),
                 bg=BG, fg="white").pack(pady=(30, 6))
        tk.Label(self, text="Select a serial port and connect", font=("TkDefaultFont", 12),
                 bg=BG, fg="#aaaaaa").pack(pady=(0, 20))

        body = tk.Frame(self, bg=BG)
        body.pack(expand=True)

        self.port_list = tk.Listbox(body, font=("TkDefaultFont", 13), height=8, width=36,
                                     bg=PANEL_BG, fg="white", selectbackground="#4fc3f7",
                                     activestyle="none", bd=0, highlightthickness=1,
                                     highlightbackground="#333333")
        self.port_list.grid(row=0, column=0, columnspan=2, pady=(0, 12))

        big_button(body, "Refresh Ports", self.refresh_ports).grid(row=1, column=0, padx=6, sticky="ew")
        big_button(body, "Connect", self.connect, bg="#2e7d32").grid(row=1, column=1, padx=6, sticky="ew")

        big_button(body, "Use Simulator (no hardware)", self.connect_simulator, bg="#455a64") \
            .grid(row=2, column=0, columnspan=2, pady=(16, 0), sticky="ew")

        self.status_label = tk.Label(self, text="", font=("TkDefaultFont", 11), bg=BG, fg="#ef5350")
        self.status_label.pack(pady=14)

        self.refresh_ports()

    def refresh_ports(self) -> None:
        self.port_list.delete(0, tk.END)
        for p in EbcDevice.list_ports():
            self.port_list.insert(tk.END, p)
        if self.port_list.size() == 0:
            self.port_list.insert(tk.END, "(no serial ports found)")

    def connect(self) -> None:
        sel = self.port_list.curselection()
        if not sel:
            self.status_label.config(text="Select a port first.")
            return
        port = self.port_list.get(sel[0])
        if port.startswith("("):
            return
        self.status_label.config(text=f"Connecting to {port}...", fg="#aaaaaa")
        self.update_idletasks()
        device = EbcDevice()
        try:
            device.connect(port)
        except Exception as exc:
            self.status_label.config(text=f"Connection failed: {exc}", fg="#ef5350")
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
        tk.Label(top, text="EBC-A20", font=("TkDefaultFont", 14, "bold"), bg=BG, fg="white").pack(side="left")
        self.status_dot = tk.Label(top, text="●", font=("TkDefaultFont", 14), bg=BG, fg="#66bb6a")
        self.status_dot.pack(side="left", padx=(8, 0))
        self.status_text = tk.Label(top, text="Connected", font=("TkDefaultFont", 12), bg=BG, fg="#aaaaaa")
        self.status_text.pack(side="left", padx=(4, 0))
        big_button(top, "Disconnect", self.disconnect, bg="#b71c1c").pack(side="right")

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

        self.current_stepper = NumberStepper(controls, "DISCHARGE CURRENT", 1000, 100, 50, 20000, "mA")
        self.current_stepper.pack(side="left", padx=(0, 20))
        self.cutoff_stepper = NumberStepper(controls, "CUTOFF VOLTAGE", 3000, 50, 1000, 30000, "mV")
        self.cutoff_stepper.pack(side="left", padx=(0, 20))

        btns = tk.Frame(controls, bg=BG)
        btns.pack(side="right")
        big_button(btns, "Start Discharge", self.start_discharge, bg="#2e7d32").pack(side="left", padx=6)
        big_button(btns, "Stop", self.stop_discharge, bg="#b71c1c").pack(side="left", padx=6)

    def on_shown(self) -> None:
        self._cancel_loops()
        self._t0 = None
        self.graph.clear()
        self._poll_job = self.after(self.POLL_MS, self._drain_queue)
        self._redraw_job = self.after(self.REDRAW_MS, self._redraw_loop)

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
            self.status_dot.config(fg="#ef5350")
            self.status_text.config(text=device.last_error or "Disconnected")

        self._poll_job = self.after(self.POLL_MS, self._drain_queue)

    def _apply_sample(self, sample) -> None:
        if self._t0 is None:
            self._t0 = sample.timestamp
        self.graph.add_sample(sample.timestamp - self._t0, sample.voltage_v, sample.current_a)
        self.tile_voltage.set(f"{sample.voltage_v:.3f} V")
        self.tile_current.set(f"{sample.current_a:.3f} A")
        self.tile_capacity.set(f"{sample.capacity_mah} mAh")
        self.tile_status.set(sample.status_text)

    def _redraw_loop(self) -> None:
        if self.app.device is None:
            self._redraw_job = None
            return
        self.graph.redraw()
        self._redraw_job = self.after(self.REDRAW_MS, self._redraw_loop)

    def start_discharge(self) -> None:
        device = self.app.device
        if device is None:
            return
        device.start_discharge(self.current_stepper.value, self.cutoff_stepper.value)

    def stop_discharge(self) -> None:
        device = self.app.device
        if device is None:
            return
        device.stop_discharge()

    def disconnect(self) -> None:
        device = self.app.device
        if device is not None:
            device.disconnect()
        self.app.set_device(None)
        self._cancel_loops()
        self.app.show_connect()
