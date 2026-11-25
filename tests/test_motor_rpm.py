"""Motor speed (0x0104) and target motor speed.

Models with shaving modes (0x0332, XP9201/XP9400) notify the live speed in
0x0104 and report the set value of the active mode in 0x0332. Models without
(S7885, QP4530) never notify 0x0104 and hold a fixed set value there. The
motor speed sensor therefore only reports on the former; the target motor
speed sensor reports the set value on both.
"""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.philips_shaver.const import (
    CHAR_MOTOR_RPM,
    CHAR_SHAVING_MODE_SETTINGS,
    LIVE_READ_CHARS,
    POLL_READ_CHARS,
)
from custom_components.philips_shaver.coordinator import (
    NOTIFICATION_CHARS,
    PhilipsShaverCoordinator,
)
from custom_components.philips_shaver.sensor import (
    PhilipsMotorSpeedSensor,
    PhilipsTargetMotorSpeedSensor,
)

from .conftest import chars_as_bytes

# S7885 0x0104 value from the #29 capture: e818 → 6376 raw.
S7885_RPM = bytes.fromhex("e818")


def process(results: dict[str, bytes], data: dict | None = None) -> dict:
    stub = SimpleNamespace(data=data or {}, _cleaning_sources={})
    return PhilipsShaverCoordinator._process_results(stub, results)


def make(cls, data: dict):
    sensor = cls.__new__(cls)
    sensor.coordinator = SimpleNamespace(data=data)
    return sensor


def speed(data: dict) -> int | None:
    return make(PhilipsMotorSpeedSensor, data).native_value


def target(data: dict) -> int | None:
    return make(PhilipsTargetMotorSpeedSensor, data).native_value


def test_motor_rpm_is_read_and_still_subscribed() -> None:
    assert CHAR_MOTOR_RPM in POLL_READ_CHARS
    assert CHAR_MOTOR_RPM in LIVE_READ_CHARS
    assert CHAR_MOTOR_RPM in NOTIFICATION_CHARS
    # A mode change updates the set value by notification.
    assert CHAR_SHAVING_MODE_SETTINGS in NOTIFICATION_CHARS


def test_xp9201_live_speed_and_mode_target(xp9201) -> None:
    data = process(chars_as_bytes(xp9201))
    # 0x8118 LE = 6273 raw → 2066 rpm live
    assert speed(data) == 2066
    # 0x0332 bd18 = 6333 raw → 2086 rpm
    assert target(data) == 2086


def test_xp9201_live_notifications_pass_through(xp9201) -> None:
    data = process(chars_as_bytes(xp9201))
    for raw, rpm in (("9718", 2073), ("141a", 2199), ("0000", 0)):
        data = process({CHAR_MOTOR_RPM: bytes.fromhex(raw)}, data)
        assert speed(data) == rpm
        assert target(data) == 2086


def test_mode_settings_notification_updates_target(xp9201) -> None:
    data = process(chars_as_bytes(xp9201))
    # 1900 rpm → 5768 raw, rest unchanged
    raw = (5768).to_bytes(2, "little") + bytes.fromhex("f401dc05a00f3c00")
    data = process({CHAR_SHAVING_MODE_SETTINGS: raw}, data)
    assert target(data) == 1900


def test_qp4530_set_value_is_target_not_speed(qp4530) -> None:
    data = process(chars_as_bytes(qp4530))
    # 0x6419 LE = 6500 raw → 2141 rpm, fixed
    assert data["motor_rpm"] == 2141
    assert target(data) == 2141
    assert speed(data) is None


def test_s7885_set_value_is_target_not_speed(s7885) -> None:
    data = process(chars_as_bytes(s7885))
    assert "shaving_settings" not in data
    assert target(data) == 2100
    assert speed(data) is None


def test_nothing_read_yet() -> None:
    data = {"motor_rpm": 0, "shaving_settings": None}
    assert target(data) is None
    assert speed(data) is None


def test_invalid_mode_settings_fall_back_to_0104() -> None:
    data = process(
        {CHAR_SHAVING_MODE_SETTINGS: b"\x01\x02", CHAR_MOTOR_RPM: S7885_RPM},
        {"motor_rpm": 0},
    )
    assert data["shaving_settings"] == {"error": "Invalid data length"}
    assert target(data) == 2100
    assert speed(data) is None
