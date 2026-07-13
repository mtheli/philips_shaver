"""Derivation tests for the charging status enum sensor.

``native_value`` only touches ``self.coordinator.data``, so the sensor is
instantiated without its HA-bound ``__init__`` and fed a coordinator stub.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.philips_shaver.sensor import PhilipsChargingStatusSensor


def status_for(data: dict) -> str | None:
    sensor = PhilipsChargingStatusSensor.__new__(PhilipsChargingStatusSensor)
    sensor.coordinator = SimpleNamespace(data=data)
    return sensor.native_value


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"device_state": "off", "battery": 90}, "not_charging"),
        ({"device_state": "shaving", "battery": 90}, "not_charging"),
        ({"device_state": "charging", "battery": 90}, "charging"),
        ({"device_state": "charging", "battery": 100}, "full_charge"),
        # 100% while off the plug is a full battery, not "full charge" state
        ({"device_state": "off", "battery": 100}, "not_charging"),
    ],
)
def test_states(data: dict, expected: str) -> None:
    assert status_for(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        {},  # no reads yet
        {"battery": 90},  # device_state char missing
        {"device_state": "unknown", "battery": 90},  # unmapped state byte
    ],
)
def test_unknown_when_state_unavailable(data: dict) -> None:
    assert status_for(data) is None


def test_charging_without_battery_reading_is_not_full() -> None:
    assert status_for({"device_state": "charging"}) == "charging"


def test_options_cover_all_derived_states() -> None:
    sensor = PhilipsChargingStatusSensor.__new__(PhilipsChargingStatusSensor)
    assert sensor.options == ["not_charging", "charging", "full_charge"]
