"""
ZKETECH EBC-A20 serial protocol.

Reverse-engineered from two independent public sources, which agree on
framing/checksum/value-encoding but DISAGREE on serial parity:

  - https://gist.github.com/enkiusz/6408645efd622b8a638a14957cd37f47
    -> 9600 baud, 8 data bits, ODD parity, 1 stop bit
  - https://github.com/Kazhuu/ebc-battery-tester (FRAMES.md / REVERSE_ENGINEERING.md)
    -> 9600 baud, 8E1 (EVEN parity), CH340 adapter (VID 0x1A86 / PID 0x7523)

This has NOT been verified against real hardware. PARITY below defaults to
EVEN (the more thoroughly documented source). If connecting to a real unit
produces no valid frames / constant checksum failures, try ODD first.

Byte-level details (frame markers, base240 encoding, checksum algorithm,
command/status codes, CC-discharge frame layout) are cross-confirmed by both
sources including a worked example frame, so those are on firmer footing
than the parity setting.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass
from functools import reduce
from typing import Optional

import serial

SOF = 0xFA
EOF = 0xF8
BASE = 240  # == 0xf0

# --- serial line settings ----------------------------------------------
BAUDRATE = 9600
BYTESIZE = serial.EIGHTBITS
PARITY = serial.PARITY_EVEN  # UNVERIFIED - see module docstring; try PARITY_ODD if this fails
STOPBITS = serial.STOPBITS_ONE

# --- host -> device command codes ---------------------------------------
CMD_CONNECT = 0x05
CMD_DISCONNECT = 0x06
CMD_STOP = 0x02
CMD_DISCH_CC_START = 0x01
CMD_DISCH_CC_ADJUST = 0x07
CMD_DISCH_CC_CONTINUE = 0x08

# --- device -> host status byte (CC discharge mode) ----------------------
STATUS_TEXT = {
    0x00: "Idle",
    0x0A: "Discharging",
    0x14: "Finished",
    0x64: "Idle (last: CC discharge)",
    0x65: "Idle (last: CP discharge)",
    0x66: "Idle (last: CV charge)",
    0x6E: "Discharging (CC)",
    0x6F: "Discharging (CP)",
    0x70: "Charging (CV)",
}


def encode_base240(value: int) -> tuple[int, int]:
    value = max(0, int(round(value)))
    h, l = divmod(value, BASE)
    return h, l


def decode_base240(h: int, l: int) -> int:
    return h * BASE + l


def checksum(payload: bytes) -> int:
    return reduce(operator.xor, payload, 0)


def build_command(cmd: int, p1: int = 0, p2: int = 0, p3: int = 0) -> bytes:
    """Build a host->device frame. p1/p2/p3 are raw encoded units (already
    scaled per the field, e.g. mA/10) - see device.py for the scaling used
    by each command."""
    p1h, p1l = encode_base240(p1)
    p2h, p2l = encode_base240(p2)
    p3h, p3l = encode_base240(p3)
    payload = bytes([cmd, p1h, p1l, p2h, p2l, p3h, p3l])
    return bytes([SOF]) + payload + bytes([checksum(payload)]) + bytes([EOF])


@dataclass
class Sample:
    timestamp: float
    status_code: int
    voltage_mv: int
    current_ma: int
    capacity_mah: int
    device_type: int

    @property
    def status_text(self) -> str:
        return STATUS_TEXT.get(self.status_code, f"Unknown (0x{self.status_code:02x})")

    @property
    def voltage_v(self) -> float:
        return self.voltage_mv / 1000.0

    @property
    def current_a(self) -> float:
        return self.current_ma / 1000.0

    @property
    def capacity_ah(self) -> float:
        return self.capacity_mah / 1000.0


def parse_status_frame(payload: bytes) -> Optional[Sample]:
    """Decode a 16-byte device->host payload into a Sample. Returns None if
    the payload is too short to be a status frame."""
    if len(payload) < 16:
        return None

    status = payload[0]
    current_ma = decode_base240(payload[1], payload[2]) * 10
    voltage_mv = decode_base240(payload[3], payload[4]) * 10
    capacity_mah = decode_base240(payload[5], payload[6])
    device_type = payload[15]

    return Sample(
        timestamp=0.0,  # filled in by the reader
        status_code=status,
        voltage_mv=voltage_mv,
        current_ma=current_ma,
        capacity_mah=capacity_mah,
        device_type=device_type,
    )


class FrameReader:
    """Feed raw serial bytes in; get complete (payload, checksum_ok) frames out.

    Frames are scanned by SOF/EOF markers rather than fixed length, since
    that's robust to any lingering framing uncertainty.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self._in_frame = False

    def feed(self, data: bytes) -> list[tuple[bytes, bool]]:
        frames: list[tuple[bytes, bool]] = []
        for b in data:
            if not self._in_frame:
                if b == SOF:
                    self._in_frame = True
                    self._buf = bytearray()
                continue
            if b == EOF:
                self._in_frame = False
                if len(self._buf) >= 1:
                    payload, chk = bytes(self._buf[:-1]), self._buf[-1]
                    frames.append((payload, checksum(payload) == chk))
                self._buf = bytearray()
                continue
            self._buf.append(b)
        return frames
