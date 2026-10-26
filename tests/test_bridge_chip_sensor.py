"""Smoke tests for the ESP Chip diagnostic sensor and the build-change hook.

Bridge firmware >= 1.14.2 reports its chip and where it resolves rotating
addresses. Older firmware reports neither — the sensor must stay unknown.
A change of the reported build fields must re-run the IDF check and
refresh the entities, since the info event often arrives after setup.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.philips_shaver.coordinator import (
    PhilipsShaverCoordinator,
)
from custom_components.philips_shaver.sensor import (
    PhilipsBridgeBuildSensor,
    PhilipsBridgeChipSensor,
)


def _chip_sensor(**fields) -> PhilipsBridgeChipSensor:
    sensor = PhilipsBridgeChipSensor.__new__(PhilipsBridgeChipSensor)
    sensor.coordinator = SimpleNamespace(transport=SimpleNamespace(**fields))
    return sensor


def test_chip_sensor_shows_chip_and_resolution() -> None:
    sensor = _chip_sensor(chip="esp32s3", addr_res="ctrl")
    assert sensor.native_value == "ESP32-S3"
    assert sensor.extra_state_attributes == {"address_resolution": "controller"}
    sensor = _chip_sensor(chip="esp32", addr_res="host")
    assert sensor.native_value == "ESP32"
    assert sensor.extra_state_attributes == {"address_resolution": "host"}


def test_chip_sensor_unknown_on_old_firmware() -> None:
    sensor = _chip_sensor(chip=None, addr_res=None)
    assert sensor.native_value is None
    assert sensor.extra_state_attributes is None
    sensor = _chip_sensor()
    assert sensor.native_value is None
    assert sensor.extra_state_attributes is None


def test_build_sensor_leaves_chip_to_chip_sensor() -> None:
    sensor = PhilipsBridgeBuildSensor.__new__(PhilipsBridgeBuildSensor)
    sensor.coordinator = SimpleNamespace(transport=SimpleNamespace(
        esphome_version="2026.10.0", idf_version="v5.5.5",
        chip="esp32s3", addr_res="host",
    ))
    assert sensor.native_value == "ESPHome 2026.10.0 / IDF v5.5.5"
    assert sensor.extra_state_attributes == {
        "esphome_version": "2026.10.0",
        "idf_version": "v5.5.5",
    }


def test_build_change_reruns_idf_check_and_refreshes() -> None:
    coord = PhilipsShaverCoordinator.__new__(PhilipsShaverCoordinator)
    coord._check_bridge_idf = MagicMock()
    coord.async_update_listeners = MagicMock()
    coord._on_bridge_build_changed()
    coord._check_bridge_idf.assert_called_once()
    coord.async_update_listeners.assert_called_once()
