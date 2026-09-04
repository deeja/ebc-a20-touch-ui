"""Serial driver for the ZKETECH EBC-A20. See protocol.py for wire format
and the unverified-parity caveat.
"""
from __future__ import annotations

import queue
import sys
import threading
import time
from typing import Optional

import serial
import serial.tools.list_ports

from . import protocol
from .protocol import FrameReader, Sample, build_command, parse_status_frame


class DeviceError(Exception):
    pass


class EbcDevice:
    """Real EBC-A20 connected over USB-serial. All I/O happens on a
    background thread; samples are handed to the UI via a Queue."""

    def __init__(self) -> None:
        self.sample_queue: "queue.Queue[Sample]" = queue.Queue()
        self.raw_queue: "queue.Queue[protocol.RawFrame]" = queue.Queue()
        self.connected = False
        self.last_error: Optional[str] = None
        self._ser: Optional[serial.Serial] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()

    @staticmethod
    def list_ports() -> list[str]:
        """Serial ports likely to be a real USB-serial adapter, filtered
        per-OS since "junk" entries look different on each platform -
        Windows COM ports don't have this problem and need no filtering."""
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if sys.platform == "darwin":
            # Each USB-serial adapter shows up twice on macOS: a
            # /dev/cu.* (call-up, for initiating outgoing connections -
            # what this app wants) and a /dev/tty.* (call-in) device for
            # the same physical port. Keep only cu.* so one adapter isn't
            # shown as two identical-looking buttons.
            ports = [p for p in ports if not p.startswith("/dev/tty.")]
        elif sys.platform.startswith("linux"):
            # Built-in motherboard serial headers (ttyS0-ttyS31 etc.), not
            # real USB-serial adapters - a real EBC-A20 shows up as
            # ttyUSB*/ttyACM* instead.
            ports = [p for p in ports if not p.startswith("/dev/ttyS")]
        return ports

    def connect(self, port: str) -> None:
        if self.connected:
            return
        self._ser = serial.Serial(
            port=port,
            baudrate=protocol.BAUDRATE,
            bytesize=protocol.BYTESIZE,
            parity=protocol.PARITY,
            stopbits=protocol.STOPBITS,
            timeout=0.5,
        )
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ser.write(build_command(protocol.CMD_CONNECT))
        self.connected = True

    def disconnect(self) -> None:
        if not self.connected:
            return
        try:
            if self._ser and self._ser.is_open:
                self._ser.write(build_command(protocol.CMD_STOP))
                self._ser.write(build_command(protocol.CMD_DISCONNECT))
        except Exception:
            pass
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._ser and self._ser.is_open:
            self._ser.close()
        self.connected = False

    def start_discharge_cc(self, current_ma: int, cutoff_mv: int, time_limit_min: int = 0) -> None:
        self._send(protocol.CMD_DISCH_CC_START, current_ma // 10, cutoff_mv // 10, time_limit_min)

    def start_discharge_cp(self, power_w: int, cutoff_mv: int, time_limit_min: int = 0) -> None:
        self._send(protocol.CMD_DISCH_CP_START, power_w, cutoff_mv // 10, time_limit_min)

    def start_charge_cv(self, current_ma: int, voltage_mv: int, cutoff_current_ma: int) -> None:
        self._send(protocol.CMD_CHG_CV_START, current_ma // 10, voltage_mv // 10, cutoff_current_ma // 10)

    def stop(self) -> None:
        self._send(protocol.CMD_STOP)

    def _send(self, cmd: int, p1: int = 0, p2: int = 0, p3: int = 0) -> None:
        if not self.connected or not self._ser:
            raise DeviceError("not connected")
        self._ser.write(build_command(cmd, p1, p2, p3))

    def _run(self) -> None:
        reader = FrameReader()
        try:
            while not self._stop_flag.is_set():
                chunk = self._ser.read(64)
                if not chunk:
                    continue
                for payload, ok in reader.feed(chunk):
                    sample = parse_status_frame(payload) if ok else None
                    if sample is not None:
                        sample.timestamp = time.monotonic()
                        self.sample_queue.put(sample)
                    self.raw_queue.put(protocol.RawFrame(time.time(), payload, ok, sample))
        except Exception as exc:  # serial disconnects, permission errors, etc.
            self.last_error = str(exc)
            self.connected = False
