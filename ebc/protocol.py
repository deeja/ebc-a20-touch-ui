"""
ZKETECH EBC-A20 serial protocol.

Reverse-engineered from two independent public sources, which agree on
framing/checksum/value-encoding but DISAGREE on serial parity:

  - https://gist.github.com/enkiusz/6408645efd622b8a638a14957cd37f47
    -> 9600 baud, 8 data bits, ODD parity, 1 stop bit
  - https://github.com/Kazhuu/ebc-battery-tester (FRAMES.md / REVERSE_ENGINEERING.md)
    -> 9600 baud, 8E1 (EVEN parity), CH340 adapter (VID 0x1A86 / PID 0x7523)

Verified against real hardware: EVEN parity, framing, checksum, and base240
decoding all check out - the device connects and produces valid frames.

One correction found against real hardware: the live status frame's voltage
field (payload[3:4]) is NOT x10 like the docs' scaling table implied - it's
just decode_base240() directly in mV. The docs' "Voltage: mV / 10" scaling
table entry describes the SET-command encoding (host -> device), not this
live-readback field; conflating the two was the bug. current_ma
(payload[1:2]) still uses the x10 decode and hasn't been independently
re-checked against a multimeter/known load - if displayed current also
looks off by a clean factor (10x, or missing entirely), check that decode
next using the same method that caught the voltage bug.
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
CMD_DISCH_CP_START = 0x11
CMD_DISCH_CP_CONTINUE = 0x18
CMD_CHG_CV_START = 0x21
CMD_CHG_CV_CONTINUE = 0x28
# CONTINUE variants resume an in-progress test (e.g. after a parameter
# tweak) without resetting accumulated capacity. Not used by this UI - it
# only ever sends START, matching the current no-live-adjustment scope.

# --- device -> host status byte -------------------------------------------
STATUS_TEXT = {
    # CC discharge
    0x00: "Idle",
    0x0A: "Discharging",
    0x14: "Finished",
    # CP discharge
    0x01: "Idle",
    0x0B: "Discharging (CP)",
    0x15: "Finished",
    # CV charge
    0x02: "Idle",
    0x0C: "Charging",
    0x16: "Finished",
    # firmware report, first ~15s after CONNECT
    0x64: "Idle (last: CC discharge)",
    0x65: "Idle (last: CP discharge)",
    0x66: "Idle (last: CV charge)",
    0x6E: "Discharging (CC)",
    0x6F: "Discharging (CP)",
    0x70: "Charging (CV)",
}

# Status code that means "this leg is done", per mode - used by the repeat
# sequencer to know when to advance to the next leg.
FINISHED_STATUS = {
    "DSC_CC": 0x14,
    "DSC_CP": 0x15,
    "CHG_CV": 0x16,
}

# Status codes that mean the device is actively discharging/charging right
# now - used by the UI to know a test is running, including one that was
# already in progress on the device before this app connected (see the
# 0x6E-0x70 codes above).
ACTIVE_STATUS_CODES = {0x0A, 0x0B, 0x0C, 0x6E, 0x6F, 0x70}


def is_active_status(code: int) -> bool:
    return code in ACTIVE_STATUS_CODES


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
    voltage_mv = decode_base240(payload[3], payload[4])  # confirmed against real hardware: no x10 here
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
