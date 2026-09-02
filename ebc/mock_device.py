"""Synthetic EBC-A20 stand-in with the same interface as EbcDevice, so the
UI can be built and driven without real hardware attached (this is also
what runs when developing on Windows). Simulates all three manual test
modes (CC discharge, CP discharge, CV charge) with plausible curves and the
matching status codes from protocol.STATUS_TEXT."""
from __future__ import annotations

import math
import queue
import random
import threading
import time
from typing import Optional

from . import config
from .protocol import Sample

_IDLE_STATUS = {
    config.MODE_DSC_CC: 0x00,
    config.MODE_DSC_CP: 0x01,
    config.MODE_CHG_CV: 0x02,
}
_ACTIVE_STATUS = {
    config.MODE_DSC_CC: 0x0A,
    config.MODE_DSC_CP: 0x0B,
    config.MODE_CHG_CV: 0x0C,
}
_FINISHED_STATUS = {
    config.MODE_DSC_CC: 0x14,
    config.MODE_DSC_CP: 0x15,
    config.MODE_CHG_CV: 0x16,
}


class MockEbcDevice:
    def __init__(self) -> None:
        self.sample_queue: "queue.Queue[Sample]" = queue.Queue()
        self.connected = False
        self.last_error: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._active = threading.Event()

        self._mode: str = config.MODE_DSC_CC
        self._params: dict = {}
        self._voltage_mv: float = 3700.0
        self._capacity_mah: float = 0.0
        self._leg_t0: float = 0.0

    @staticmethod
    def list_ports() -> list[str]:
        return ["SIM (no hardware)"]

    def connect(self, port: str) -> None:
        if self.connected:
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.connected = True

    def disconnect(self) -> None:
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.connected = False

    def start_discharge_cc(self, current_ma: int, cutoff_mv: int, time_limit_min: int = 0) -> None:
        self._start_leg(config.MODE_DSC_CC, current_ma=current_ma, cutoff_mv=cutoff_mv, time_limit_min=time_limit_min)

    def start_discharge_cp(self, power_w: int, cutoff_mv: int, time_limit_min: int = 0) -> None:
        self._start_leg(config.MODE_DSC_CP, power_w=power_w, cutoff_mv=cutoff_mv, time_limit_min=time_limit_min)

    def start_charge_cv(self, current_ma: int, voltage_mv: int, cutoff_current_ma: int) -> None:
        self._start_leg(config.MODE_CHG_CV, current_ma=current_ma, voltage_mv=voltage_mv, cutoff_current_ma=cutoff_current_ma)

    def stop(self) -> None:
        self._active.clear()

    def _start_leg(self, mode: str, **params) -> None:
        self._mode = mode
        self._params = params
        self._capacity_mah = 0.0
        self._leg_t0 = time.monotonic()
        self._active.set()

    def _run(self) -> None:
        last = time.monotonic()
        while not self._stop_flag.is_set():
            time.sleep(1.0)
            now = time.monotonic()
            dt_h = (now - last) / 3600.0
            last = now

            if self._active.is_set():
                current_ma, finished = self._step(now, dt_h)
                status = _FINISHED_STATUS[self._mode] if finished else _ACTIVE_STATUS[self._mode]
                if finished:
                    self._active.clear()
            else:
                current_ma = 0.0
                status = _IDLE_STATUS.get(self._mode, 0x00)

            sample = Sample(
                timestamp=now,
                status_code=status,
                voltage_mv=int(self._voltage_mv),
                current_ma=int(max(0, current_ma)),
                capacity_mah=int(self._capacity_mah),
                device_type=0x09,
            )
            self.sample_queue.put(sample)

    def _step(self, now: float, dt_h: float) -> tuple[float, bool]:
        """Advance the simulated battery by one tick. Returns (current_ma, finished)."""
        elapsed = now - self._leg_t0
        p = self._params
        time_limit_min = p.get("time_limit_min", 0)
        time_up = time_limit_min and elapsed / 60.0 >= time_limit_min

        if self._mode == config.MODE_DSC_CC:
            cutoff_mv = p["cutoff_mv"]
            current_ma = p["current_ma"] + random.uniform(-15, 15)
            self._voltage_mv = cutoff_mv + (self._voltage_mv - cutoff_mv) * math.exp(-1.0 / 900.0) \
                if self._voltage_mv > cutoff_mv else self._voltage_mv
            self._voltage_mv += random.uniform(-5, 5)
            self._capacity_mah += max(0, current_ma) * dt_h
            finished = self._voltage_mv <= cutoff_mv or time_up

        elif self._mode == config.MODE_DSC_CP:
            cutoff_mv = p["cutoff_mv"]
            self._voltage_mv = cutoff_mv + (self._voltage_mv - cutoff_mv) * math.exp(-1.0 / 900.0) \
                if self._voltage_mv > cutoff_mv else self._voltage_mv
            self._voltage_mv += random.uniform(-5, 5)
            voltage_v = max(0.1, self._voltage_mv / 1000.0)
            current_ma = (p["power_w"] * 1000.0) / voltage_v
            self._capacity_mah += max(0, current_ma) * dt_h
            finished = self._voltage_mv <= cutoff_mv or time_up

        elif self._mode == config.MODE_CHG_CV:
            target_mv = p["voltage_mv"]
            set_current_ma = p["current_ma"]
            cutoff_current_ma = p["cutoff_current_ma"]
            tau = 300.0
            if self._voltage_mv < target_mv:
                self._voltage_mv += (target_mv - self._voltage_mv) * (1 - math.exp(-1.0 / tau))
            self._voltage_mv += random.uniform(-3, 3)
            self._voltage_mv = min(self._voltage_mv, target_mv + 5)

            taper_band_mv = max(1.0, target_mv * 0.05)
            headroom = max(0.0, target_mv - self._voltage_mv)
            taper_frac = min(1.0, headroom / taper_band_mv)
            current_ma = set_current_ma * taper_frac + random.uniform(-5, 5)
            self._capacity_mah += max(0, current_ma) * dt_h
            finished = (current_ma <= cutoff_current_ma and headroom < taper_band_mv) or time_up

        else:
            current_ma, finished = 0.0, True

        return current_ma, finished
