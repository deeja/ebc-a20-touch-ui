"""Test configuration screen: battery preset, mode, and per-mode
parameters. Mirrors the real device's own Testing Interface / Setting
Interface split (manual §4.3) so the live graph screen doesn't have to
crowd in up to 6 fields per mode.

Modes that involve charging (CHG-CV, Repeat) are only offered in the Mode
dropdown when the selected battery preset actually supports charging on
this device - see presets.py for why NiMH/NiCd don't."""
from __future__ import annotations

import dataclasses
import tkinter as tk

from ebc import config as cfgmod
from ebc import presets

from .widgets import (
    ACCENT_GREEN,
    BG,
    BTN_BG,
    CHARGE_ACCENT,
    CHARGE_BG,
    DISCHARGE_ACCENT,
    DISCHARGE_BG,
    TEXT,
    TEXT_MUTED,
    PresetButton,
    SelectableButton,
    ToggleButton,
    TouchNumberField,
    big_button,
    current_field_kwargs,
    plain_field_kwargs,
    time_field_kwargs,
    voltage_field_kwargs,
)

DISCHARGE_ONLY_MODES = [cfgmod.MODE_DSC_CC, cfgmod.MODE_DSC_CP]
PRESET_GRID_COLS = 5


class SettingsScreen(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.cfg = cfgmod.TestConfig()
        self._bindings: list[tuple[TouchNumberField, str]] = []

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=10, pady=(8, 4))
        self.title_label = tk.Label(top, text="Configure", font=("TkDefaultFont", 16, "bold"), bg=BG, fg=TEXT)
        self.title_label.pack(side="left")
        big_button(top, "Cancel", self._cancel, bg=BTN_BG, fg=TEXT).pack(side="right")
        big_button(top, "OK", self._save, bg=ACCENT_GREEN, fg="white").pack(side="right", padx=(0, 8))

        battery_grid = tk.Frame(self, bg=BG)
        battery_grid.pack(fill="x", padx=10)
        self.preset_buttons: dict[str, PresetButton] = {}
        for i, key in enumerate(presets.PRESET_ORDER):
            preset = presets.PRESETS[key]
            btn = PresetButton(battery_grid, preset.label, preset.subtitle,
                                command=lambda k=key: self._on_preset_selected(k))
            btn.grid(row=i // PRESET_GRID_COLS, column=i % PRESET_GRID_COLS, padx=3, pady=3, sticky="nsew")
            self.preset_buttons[key] = btn
        for c in range(PRESET_GRID_COLS):
            battery_grid.grid_columnconfigure(c, weight=1)

        mode_button_row = tk.Frame(self, bg=BG)
        mode_button_row.pack(fill="x", padx=10, pady=(8, 4))
        self.cell_field = TouchNumberField(mode_button_row, "CELLS IN SERIES", 1, 1, 1,
                                            on_change=self._on_cells_changed, bg=BG,
                                            **plain_field_kwargs(""))
        self.mode_buttons: dict[str, SelectableButton] = {}
        for m in cfgmod.MODE_ORDER:
            btn = SelectableButton(mode_button_row, cfgmod.MODE_LABELS[m],
                                    command=lambda mm=m: self._on_mode_selected(mm))
            self.mode_buttons[m] = btn

        self.param_container = tk.Frame(self, bg=BG)
        self.param_container.pack(fill="both", expand=True, padx=10, pady=4)

        self.mode_frames = {
            cfgmod.MODE_DSC_CC: self._build_dsc_cc_frame(),
            cfgmod.MODE_DSC_CP: self._build_dsc_cp_frame(),
            cfgmod.MODE_CHG_CV: self._build_chg_cv_frame(),
            cfgmod.MODE_REPEAT: self._build_repeat_frame(),
        }
        for frame in self.mode_frames.values():
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

    # -- frame builders ---------------------------------------------------
    def _field(self, master, attr: str, label: str, lo: int, hi: int, kind_kwargs: dict,
               bg: str = BG, **pack_kw) -> TouchNumberField:
        f = TouchNumberField(master, label, getattr(self.cfg, attr), lo, hi,
                              on_change=lambda v, a=attr: setattr(self.cfg, a, v), bg=bg, **kind_kwargs)
        f.pack(side="left", padx=(0, 20), **pack_kw)
        self._bindings.append((f, attr))
        return f

    def _phase_header(self, master, text: str, bg: str, accent: str) -> None:
        tk.Label(master, text=text, font=("TkDefaultFont", 11, "bold"), bg=bg, fg=accent) \
            .pack(anchor="w", padx=10, pady=(8, 0))

    def _build_dsc_cc_frame(self) -> tk.Frame:
        f = tk.Frame(self.param_container, bg=DISCHARGE_BG)
        self._phase_header(f, "DISCHARGE", DISCHARGE_BG, DISCHARGE_ACCENT)
        row = tk.Frame(f, bg=DISCHARGE_BG)
        row.pack(anchor="nw", padx=10, pady=10)
        self._field(row, "dsc_cc_current_ma", "DISCHARGE CURRENT", 100, 20000, current_field_kwargs(), bg=DISCHARGE_BG)
        self._field(row, "dsc_cc_cutoff_mv", "CUTOFF VOLTAGE", 0, 30000, voltage_field_kwargs(), bg=DISCHARGE_BG)
        self._field(row, "dsc_cc_time_min", "TIME LIMIT (0=none)", 0, 999, time_field_kwargs(), bg=DISCHARGE_BG)
        return f

    def _build_dsc_cp_frame(self) -> tk.Frame:
        f = tk.Frame(self.param_container, bg=DISCHARGE_BG)
        self._phase_header(f, "DISCHARGE", DISCHARGE_BG, DISCHARGE_ACCENT)
        row = tk.Frame(f, bg=DISCHARGE_BG)
        row.pack(anchor="nw", padx=10, pady=10)
        self._field(row, "dsc_cp_power_w", "DISCHARGE POWER", 1, 85, plain_field_kwargs("W"), bg=DISCHARGE_BG)
        self._field(row, "dsc_cp_cutoff_mv", "CUTOFF VOLTAGE", 0, 30000, voltage_field_kwargs(), bg=DISCHARGE_BG)
        self._field(row, "dsc_cp_time_min", "TIME LIMIT (0=none)", 0, 999, time_field_kwargs(), bg=DISCHARGE_BG)
        return f

    def _build_chg_cv_frame(self) -> tk.Frame:
        f = tk.Frame(self.param_container, bg=CHARGE_BG)
        self._phase_header(f, "CHARGE", CHARGE_BG, CHARGE_ACCENT)
        row = tk.Frame(f, bg=CHARGE_BG)
        row.pack(anchor="nw", padx=10, pady=10)
        self._field(row, "chg_cv_current_ma", "CHARGE CURRENT", 100, 5000, current_field_kwargs(), bg=CHARGE_BG)
        self._field(row, "chg_cv_voltage_mv", "CHARGE VOLTAGE", 0, 18000, voltage_field_kwargs(), bg=CHARGE_BG)
        self._field(row, "chg_cv_cutoff_ma", "CUTOFF CURRENT", 100, 5000, current_field_kwargs(), bg=CHARGE_BG)
        return f

    def _build_repeat_frame(self) -> tk.Frame:
        f = tk.Frame(self.param_container, bg=BG)

        phases = tk.Frame(f, bg=BG)
        phases.pack(fill="x", anchor="nw")

        charge_section = tk.Frame(phases, bg=CHARGE_BG)
        charge_section.pack(side="left", anchor="n", padx=(0, 10))
        self._phase_header(charge_section, "CHARGE", CHARGE_BG, CHARGE_ACCENT)
        charge_row = tk.Frame(charge_section, bg=CHARGE_BG)
        charge_row.pack(anchor="nw", padx=10, pady=(2, 10))
        self._field(charge_row, "repeat_charge_current_ma", "CHARGE CURRENT", 100, 5000, current_field_kwargs(), bg=CHARGE_BG)
        self._field(charge_row, "repeat_charge_voltage_mv", "CHARGE VOLTAGE", 0, 18000, voltage_field_kwargs(), bg=CHARGE_BG)
        self._field(charge_row, "repeat_charge_cutoff_ma", "CUTOFF CURRENT", 100, 5000, current_field_kwargs(), bg=CHARGE_BG)

        discharge_section = tk.Frame(phases, bg=DISCHARGE_BG)
        discharge_section.pack(side="left", anchor="n")
        self._phase_header(discharge_section, "DISCHARGE", DISCHARGE_BG, DISCHARGE_ACCENT)
        discharge_row = tk.Frame(discharge_section, bg=DISCHARGE_BG)
        discharge_row.pack(anchor="nw", padx=10, pady=(2, 10))
        self._field(discharge_row, "repeat_discharge_current_ma", "DISCHARGE CURRENT", 100, 20000, current_field_kwargs(), bg=DISCHARGE_BG)
        self._field(discharge_row, "repeat_discharge_cutoff_mv", "CUTOFF VOLTAGE", 0, 30000, voltage_field_kwargs(), bg=DISCHARGE_BG)

        tk.Label(f, text="Cycling", font=("TkDefaultFont", 11, "bold"), bg=BG, fg=TEXT_MUTED).pack(anchor="w", pady=(10, 0))
        cycle_row = tk.Frame(f, bg=BG)
        cycle_row.pack(anchor="nw", pady=(2, 10))
        self._field(cycle_row, "repeat_rest_min", "REST BETWEEN LEGS", 0, 99, time_field_kwargs())
        self._field(cycle_row, "repeat_cycle_count", "CYCLES", 1, 999, plain_field_kwargs(""))
        self.continuous_toggle = ToggleButton(cycle_row, "Continuous", active=False,
                                               on_change=lambda v: setattr(self.cfg, "repeat_continuous", v))
        self.continuous_toggle.pack(side="left", padx=(0, 20), pady=(16, 0))
        return f

    # -- preset / mode handling --------------------------------------------
    def _on_preset_selected(self, key: str) -> None:
        self.cfg.preset_key = key
        for k, btn in self.preset_buttons.items():
            btn.set_selected(k == key)
        self._refresh_preset_ui()

    def _on_cells_changed(self, _value: int) -> None:
        self.cfg.cell_count = self.cell_field.raw_value
        self._apply_preset_values()

    def _refresh_preset_ui(self) -> None:
        preset = presets.PRESETS[self.cfg.preset_key]
        if preset.per_cell:
            self.cell_field.set_range(1, presets.max_cells(self.cfg.preset_key))
            self.cell_field.pack(side="left", padx=(16, 0))
        else:
            self.cell_field.pack_forget()
        self._apply_preset_values()

    def _apply_preset_values(self) -> None:
        preset = presets.PRESETS[self.cfg.preset_key]
        cells = self.cell_field.raw_value if preset.per_cell else 1
        charge_mv, cutoff_mv = presets.pack_voltages_mv(self.cfg.preset_key, cells)

        if self.cfg.preset_key != "custom":
            self.cfg.dsc_cc_cutoff_mv = cutoff_mv
            self.cfg.dsc_cp_cutoff_mv = cutoff_mv
            self.cfg.repeat_discharge_cutoff_mv = cutoff_mv
            if charge_mv is not None:
                self.cfg.chg_cv_voltage_mv = charge_mv
                self.cfg.chg_cv_cutoff_ma = preset.default_cutoff_current_ma
                self.cfg.repeat_charge_voltage_mv = charge_mv
                self.cfg.repeat_charge_cutoff_ma = preset.default_cutoff_current_ma

        self._sync_fields_from_cfg()
        self._update_mode_options()
        self._update_title()

    def _update_title(self) -> None:
        self.title_label.config(text=f"Configure - {presets.describe(self.cfg.preset_key, self.cfg.cell_count)}")

    def _on_mode_selected(self, mode: str) -> None:
        self.cfg.mode = mode
        for m, btn in self.mode_buttons.items():
            btn.set_selected(m == mode)
        self.mode_frames[mode].lift()

    def _update_mode_options(self) -> None:
        """Charging (CHG-CV, Repeat) is only offered as a mode when the
        selected battery preset actually supports it on this device - see
        presets.py. 'Custom' always allows every mode since it carries no
        chemistry claim."""
        preset = presets.PRESETS[self.cfg.preset_key]
        charge_supported = self.cfg.preset_key == "custom" or preset.cell_charge_mv is not None
        allowed = cfgmod.MODE_ORDER if charge_supported else DISCHARGE_ONLY_MODES

        for m in cfgmod.MODE_ORDER:
            self.mode_buttons[m].pack_forget()
        for m in allowed:
            self.mode_buttons[m].pack(side="left", padx=(0, 8))

        if self.cfg.mode not in allowed:
            self.cfg.mode = allowed[0]
        for m, btn in self.mode_buttons.items():
            btn.set_selected(m == self.cfg.mode)
        self.mode_frames[self.cfg.mode].lift()

    def _sync_fields_from_cfg(self) -> None:
        for field, attr in self._bindings:
            field.set_value(getattr(self.cfg, attr))

    # -- lifecycle ----------------------------------------------------------
    def on_shown(self) -> None:
        self.cfg = dataclasses.replace(self.app.test_config)
        for k, btn in self.preset_buttons.items():
            btn.set_selected(k == self.cfg.preset_key)
        self.continuous_toggle.active = self.cfg.repeat_continuous
        self.continuous_toggle._refresh()

        # Widen/narrow the cell-count range for the restored preset BEFORE
        # forcing its value back - otherwise a restored count could get
        # clamped by a stale range left over from whatever preset was shown
        # last. This also recomputes which modes this preset allows and
        # lifts the right mode frame.
        self._refresh_preset_ui()
        self.cell_field.set_value(self.cfg.cell_count)

    def _save(self) -> None:
        self.app.test_config = self.cfg
        self.app.is_configured = True
        self.app.show_main()

    def _cancel(self) -> None:
        self.app.show_main()
