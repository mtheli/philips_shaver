"""Active shaving mode settings come from 0x0332 in every mode.

0x0330 is only the writable template for the custom mode; on an XP9400
whose custom mode was never set it reads 0000…3c00. The mode select's
attributes and the pressure thresholds must not pick it up.
"""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.philips_shaver.const import (
    CHAR_CUSTOM_SHAVING_MODE_SETTINGS,
    CHAR_SHAVING_MODE,
    CHAR_SHAVING_MODE_SETTINGS,
)
from custom_components.philips_shaver.coordinator import PhilipsShaverCoordinator
from custom_components.philips_shaver.select import PhilipsShavingModeSelect
from custom_components.philips_shaver.sensor import (
    PhilipsShaverPressureStateSensor,
    PhilipsTargetMotorSpeedSensor,
)

ACTIVE = bytes.fromhex("bd18f401dc05a00f3c00")  # 2086 rpm, 500/1500/4000, 60
UNSET_TEMPLATE = bytes.fromhex("00000000000000003c00")


def process(results: dict[str, bytes]) -> dict:
    stub = SimpleNamespace(data={}, _cleaning_sources={})
    return PhilipsShaverCoordinator._process_results(stub, results)


def make(cls, data: dict):
    entity = cls.__new__(cls)
    entity.coordinator = SimpleNamespace(data=data)
    return entity


def custom_mode_data() -> dict:
    return process(
        {
            CHAR_SHAVING_MODE: bytes([3]),
            CHAR_SHAVING_MODE_SETTINGS: ACTIVE,
            CHAR_CUSTOM_SHAVING_MODE_SETTINGS: UNSET_TEMPLATE,
        }
    )


def test_select_attributes_use_active_settings_in_custom_mode() -> None:
    attrs = make(PhilipsShavingModeSelect, custom_mode_data()).extra_state_attributes
    assert attrs["raw_value"] == 3
    assert attrs["custom_motor_rpm"] == 2086
    assert attrs["pressure_limit_low"] == 1500
    assert attrs["pressure_limit_high"] == 4000


def test_pressure_thresholds_use_active_settings_in_custom_mode() -> None:
    data = custom_mode_data()
    for pressure, state in ((300, "no_contact"), (1200, "too_low"),
                            (2900, "optimal"), (4600, "too_high")):
        data["pressure"] = pressure
        assert make(PhilipsShaverPressureStateSensor, data).native_value == state


def test_target_speed_matches_select_attribute() -> None:
    data = custom_mode_data()
    assert make(PhilipsTargetMotorSpeedSensor, data).native_value == 2086

