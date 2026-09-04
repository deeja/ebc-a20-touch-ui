"""Test configuration shared between the Settings screen and the Main
screen. Values are in the same base units used everywhere else in this
app: mA, mV, W, minutes."""
from __future__ import annotations

from dataclasses import dataclass

MODE_DSC_CC = "DSC_CC"
MODE_DSC_CP = "DSC_CP"
MODE_CHG_CV = "CHG_CV"
MODE_REPEAT = "REPEAT"

MODE_ORDER = [MODE_DSC_CC, MODE_DSC_CP, MODE_CHG_CV, MODE_REPEAT]

MODE_LABELS = {
    MODE_DSC_CC: "Discharge - CC",
    MODE_DSC_CP: "Discharge - CP",
    
    MODE_CHG_CV: "Charge - CV",
    MODE_REPEAT: "Cycle - C/D",
}


@dataclass
class TestConfig:
    mode: str = MODE_DSC_CC

    preset_key: str = "custom"
    cell_count: int = 1

    dsc_cc_current_ma: int = 1000
    dsc_cc_cutoff_mv: int = 3000
    dsc_cc_time_min: int = 0

    dsc_cp_power_w: int = 10
    dsc_cp_cutoff_mv: int = 3000
    dsc_cp_time_min: int = 0

    chg_cv_current_ma: int = 1000
    chg_cv_voltage_mv: int = 4200
    chg_cv_cutoff_ma: int = 100

    repeat_charge_current_ma: int = 1000
    repeat_charge_voltage_mv: int = 4200
    repeat_charge_cutoff_ma: int = 100
    repeat_discharge_current_ma: int = 1000
    repeat_discharge_cutoff_mv: int = 3000
    repeat_rest_min: int = 51
    repeat_cycle_count: int = 1
    repeat_continuous: bool = False

    def summary(self) -> str:
        if self.mode == MODE_DSC_CC:
            return f"DSC-CC {self.dsc_cc_current_ma/1000:.2f}A → {self.dsc_cc_cutoff_mv/1000:.2f}V"
        if self.mode == MODE_DSC_CP:
            return f"DSC-CP {self.dsc_cp_power_w}W → {self.dsc_cp_cutoff_mv/1000:.2f}V"
        if self.mode == MODE_CHG_CV:
            return f"CHG-CV {self.chg_cv_current_ma/1000:.2f}A → {self.chg_cv_voltage_mv/1000:.2f}V"
        if self.mode == MODE_REPEAT:
            cycles = "∞" if self.repeat_continuous else str(self.repeat_cycle_count)
            return f"REPEAT x{cycles} (rest {self.repeat_rest_min}min)"
        return self.mode
