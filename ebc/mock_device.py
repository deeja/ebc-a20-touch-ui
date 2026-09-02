"""Synthetic EBC-A20 stand-in with the same interface as EbcDevice, so the
UI can be built and driven without real hardware attached (this is also
what runs when developing on Windows)."""
from __future__ import annotations

import math
import queue
import random
import threading
import time
from typing import Optional

from .protocol import STATUS_TEXT, Sample


class MockEbcDevice:
    def __init__(self) -> None:
        self.sample_queue: "queue.Queue[Sample]" = queue.Queue()
        self.connected = False
        self.last_error: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._discharging = threading.Event()
        self._current_ma = 0
        self._cutoff_mv = 3000
        self._capacity_mah = 0.0
        self._t0 = 0.0

    @staticmethod
    def list_ports() -> list[str]:
        return ["SIM (no hardware)"]

    def connect(self, port: str) -> None:
        if self.connected:
            return
        self._stop_flag.clear()
        self._t0 = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.connected = True

    def disconnect(self) -> None:
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.connected = False

    def start_discharge(self, current_ma: int, cutoff_mv: int, time_limit_min: int = 0) -> None:
        self._current_ma = current_ma
        self._cutoff_mv = cutoff_mv
        self._capacity_mah = 0.0
        self._discharge_t0 = time.monotonic()
        self._discharging.set()

    def stop_discharge(self) -> None:
        self._discharging.clear()

    def _run(self) -> None:
        last = time.monotonic()
        voltage_mv = 4200
        while not self._stop_flag.is_set():
            time.sleep(1.0)
            now = time.monotonic()
            dt_h = (now - last) / 3600.0
            last = now

            if self._discharging.is_set():
                status = 0x0A
                current_ma = self._current_ma + random.uniform(-15, 15)
                elapsed = now - self._discharge_t0
                # rough decaying discharge curve toward the cutoff voltage
                voltage_mv = self._cutoff_mv + (4200 - self._cutoff_mv) * math.exp(-elapsed / 900.0)
                voltage_mv += random.uniform(-5, 5)
                self._capacity_mah += current_ma * dt_h
                if voltage_mv <= self._cutoff_mv:
                    status = 0x14
                    self._discharging.clear()
            else:
                status = 0x00
                current_ma = 0
                voltage_mv = max(voltage_mv, 3700)

            sample = Sample(
                timestamp=now,
                status_code=status,
                voltage_mv=int(voltage_mv),
                current_ma=int(max(0, current_ma)),
                capacity_mah=int(self._capacity_mah),
                device_type=0x09,
            )
            self.sample_queue.put(sample)
