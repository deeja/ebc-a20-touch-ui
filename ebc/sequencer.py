"""Repeat-mode orchestration: Charge -> rest -> Discharge -> rest, looped.

Not its own thread - driven by calls from the UI's existing poll loop
(on_sample() for status transitions, tick() for rest-timer countdowns), so
it shares the Tk main thread and needs no locking. This exists because the
device has no confirmed wire command for its native "Auto" cycle - see
ebc/protocol.py's module docstring for the parity/verification caveat that
also applies to the CP/CV commands this sequencer sends.
"""
from __future__ import annotations

from typing import Optional

from . import config, protocol

ST_CHARGING = "charging"
ST_RESTING_BEFORE_DISCHARGE = "resting_before_discharge"
ST_DISCHARGING = "discharging"
ST_RESTING_BEFORE_CHARGE = "resting_before_charge"
ST_DONE = "done"
ST_STOPPED = "stopped"


class AutoCycleController:
    def __init__(self, device, cfg: config.TestConfig, now: float) -> None:
        self.device = device
        self.cfg = cfg
        self.state = ST_CHARGING
        self.cycles_done = 0
        self.cycle_count = None if cfg.repeat_continuous else max(1, cfg.repeat_cycle_count)
        self._rest_deadline: Optional[float] = None
        self._start_charge(now)

    # -- leg transitions -----------------------------------------------
    def _start_charge(self, now: float) -> None:
        self.device.start_charge_cv(
            self.cfg.repeat_charge_current_ma,
            self.cfg.repeat_charge_voltage_mv,
            self.cfg.repeat_charge_cutoff_ma,
        )
        self.state = ST_CHARGING

    def _start_discharge(self, now: float) -> None:
        self.device.start_discharge_cc(
            self.cfg.repeat_discharge_current_ma,
            self.cfg.repeat_discharge_cutoff_mv,
        )
        self.state = ST_DISCHARGING

    def _begin_rest(self, next_state: str, now: float) -> None:
        self.state = next_state
        self._rest_deadline = now + self.cfg.repeat_rest_min * 60.0

    # -- driven by the UI -----------------------------------------------
    def on_sample(self, sample: protocol.Sample) -> None:
        if self.state == ST_CHARGING and sample.status_code == protocol.FINISHED_STATUS[config.MODE_CHG_CV]:
            self._begin_rest(ST_RESTING_BEFORE_DISCHARGE, sample.timestamp)
        elif self.state == ST_DISCHARGING and sample.status_code == protocol.FINISHED_STATUS[config.MODE_DSC_CC]:
            self.cycles_done += 1
            if self.cycle_count is not None and self.cycles_done >= self.cycle_count:
                self.state = ST_DONE
            else:
                self._begin_rest(ST_RESTING_BEFORE_CHARGE, sample.timestamp)

    def tick(self, now: float) -> None:
        if self._rest_deadline is None or now < self._rest_deadline:
            return
        self._rest_deadline = None
        if self.state == ST_RESTING_BEFORE_DISCHARGE:
            self._start_discharge(now)
        elif self.state == ST_RESTING_BEFORE_CHARGE:
            self._start_charge(now)

    def stop(self) -> None:
        if self.state not in (ST_DONE, ST_STOPPED):
            self.device.stop()
        self.state = ST_STOPPED
        self._rest_deadline = None

    @property
    def finished(self) -> bool:
        return self.state in (ST_DONE, ST_STOPPED)

    def status_text(self, now: float) -> str:
        total = "∞" if self.cycle_count is None else str(self.cycle_count)
        cycle_label = f"Cycle {self.cycles_done + 1}/{total}"
        if self.state == ST_CHARGING:
            return f"{cycle_label} — charging"
        if self.state == ST_DISCHARGING:
            return f"{cycle_label} — discharging"
        if self.state in (ST_RESTING_BEFORE_DISCHARGE, ST_RESTING_BEFORE_CHARGE):
            remaining = max(0, int((self._rest_deadline or now) - now))
            next_leg = "discharge" if self.state == ST_RESTING_BEFORE_DISCHARGE else "charge"
            return f"{cycle_label} — resting, {next_leg} in {remaining // 60:02d}:{remaining % 60:02d}"
        if self.state == ST_DONE:
            return f"Done — {self.cycles_done} cycle(s)"
        if self.state == ST_STOPPED:
            return f"Stopped — {self.cycles_done} cycle(s) completed"
        return self.state
