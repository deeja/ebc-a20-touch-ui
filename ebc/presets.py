"""Battery chemistry presets.

Autofills the voltage-related fields (charge voltage, discharge cutoff
voltage, charge cutoff current) for a test config. Current/power setpoints
are NOT chemistry-derived (they depend on pack capacity / desired C-rate,
which this app doesn't ask for) and are left at their existing generic
defaults.

Values are standard published per-cell figures, not something specific to
the EBC-A20. See ebc/protocol.py and README.md for the "is CHG-CV the right
charge algorithm for this chemistry" analysis - short version: yes for every
chemistry below with a charge voltage (it's a real CC-CV algorithm despite
the "CV" name), and NiMH/NiCd are intentionally charge-unsupported because
they need peak-detection termination this device can't do.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

CHARGE_VOLTAGE_CEILING_MV = 18000  # device hardware limit in charge mode


@dataclass(frozen=True)
class BatteryPreset:
    label: str
    cell_nominal_mv: int
    cell_charge_mv: Optional[int]  # None => charging not supported (NiMH/NiCd)
    cell_cutoff_mv: int
    default_cutoff_current_ma: int
    per_cell: bool  # True: multiply by cell count; False: preset IS the full pack
    note: str = ""

    @property
    def dropdown_label(self) -> str:
        if not self.cell_nominal_mv:
            return self.label
        suffix = "/cell" if self.per_cell else ""
        return f"{self.label} ({self.cell_nominal_mv / 1000:.1f}V{suffix})"

    @property
    def subtitle(self) -> str:
        """Second line for the battery preset button: the operative
        voltages, not just nominal - what actually gets sent to the
        device."""
        if not self.cell_nominal_mv:
            return "Set manually"
        if self.cell_charge_mv is None:
            return f"{self.cell_cutoff_mv / 1000:.2f}V cutoff · discharge only"
        suffix = " /cell" if self.per_cell else ""
        return f"{self.cell_charge_mv / 1000:.2f}V chg · {self.cell_cutoff_mv / 1000:.2f}V cut{suffix}"


PRESETS: dict[str, BatteryPreset] = {
    "custom": BatteryPreset("Custom / Manual", 0, None, 0, 0, per_cell=False,
                             note="No autofill - set values manually."),
    "liion": BatteryPreset("Li-ion", 3700, 4200, 3000, 100, per_cell=True),
    "lipo": BatteryPreset("LiPo", 3700, 4200, 3300, 100, per_cell=True,
                           note="Higher cutoff than bare Li-ion cells, typical for protected packs."),
    "lifepo4": BatteryPreset("LiFePO4", 3200, 3650, 2500, 100, per_cell=True),
    "lifepo4_4s": BatteryPreset("LiFePO4 (4S pack)", 12800, 14600, 10000, 100, per_cell=False,
                                 note="4 cells in series - the common 12V-nominal LiFePO4 drop-in pack size."),
    "lto": BatteryPreset("LTO (Lithium Titanate)", 2400, 2700, 1500, 100, per_cell=True,
                          note="Li-based - CC-CV charge is correct. Low per-cell voltage allows more series cells."),
    "leadacid6v": BatteryPreset("Lead-Acid (6V pack)", 6000, 7200, 5250, 200, per_cell=False),
    "leadacid12v": BatteryPreset("Lead-Acid (12V pack)", 12000, 14400, 10500, 200, per_cell=False),
    "nimh": BatteryPreset("NiMH", 1200, None, 1000, 0, per_cell=True,
                           note="Charging not supported by this tester (needs -ΔV peak detection, "
                                "not current-taper-at-fixed-voltage). Discharge/capacity testing is fine."),
    "nicd": BatteryPreset("NiCd", 1200, None, 1000, 0, per_cell=True,
                           note="Charging not supported by this tester (needs -ΔV peak detection, "
                                "not current-taper-at-fixed-voltage). Discharge/capacity testing is fine."),
}

PRESET_ORDER = ["custom", "liion", "lipo", "lifepo4", "lifepo4_4s", "lto", "leadacid6v", "leadacid12v", "nimh", "nicd"]


def max_cells(preset_key: str) -> int:
    """Highest cell count that keeps charge voltage under the 18V hardware
    ceiling, for a per_cell preset. Always at least 1."""
    preset = PRESETS[preset_key]
    if not preset.per_cell or not preset.cell_charge_mv:
        return 1
    return max(1, math.floor(CHARGE_VOLTAGE_CEILING_MV / preset.cell_charge_mv))


def pack_voltages_mv(preset_key: str, cells: int) -> tuple[Optional[int], int]:
    """Returns (charge_mv or None, cutoff_mv) for the given preset and cell count."""
    preset = PRESETS[preset_key]
    if not preset.per_cell:
        return preset.cell_charge_mv, preset.cell_cutoff_mv
    cells = max(1, cells)
    charge_mv = preset.cell_charge_mv * cells if preset.cell_charge_mv else None
    cutoff_mv = preset.cell_cutoff_mv * cells
    return charge_mv, cutoff_mv


def describe(preset_key: str, cell_count: int) -> str:
    """Human-readable summary of a configured battery - preset, series-cell
    count (for per-cell chemistries), and the resulting charge/cutoff
    voltages. Shared by the Settings screen title and the main screen's
    battery-configuration summary."""
    preset = PRESETS[preset_key]
    if preset_key == "custom":
        return "Custom / Manual"
    cells = cell_count if preset.per_cell else 1
    charge_mv, cutoff_mv = pack_voltages_mv(preset_key, cells)
    cell_suffix = f" {cells}S" if preset.per_cell else ""
    if charge_mv is not None:
        return f"{preset.label}{cell_suffix} - {charge_mv / 1000:.2f}V chg -> {cutoff_mv / 1000:.2f}V cut"
    return f"{preset.label}{cell_suffix} - {cutoff_mv / 1000:.2f}V cutoff (discharge only)"
