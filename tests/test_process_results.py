"""Golden-decode tests: feed captured GATT bytes through the coordinator's
``_process_results`` and pin the parsed values.

``_process_results`` only touches ``self.data`` and the per-source cleaning
progress, so a tiny stub stands in for
the full coordinator — no Home Assistant instance needed beyond the imports.
"""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.philips_shaver.const import (
    LIGHTRING_DEFAULT_COLORS,
    CHAR_BATTERY_LEVEL,
    CHAR_CLEANING_PROGRESS,
    CHAR_CLEANING_PROGRESS_CONTROL,
    CHAR_DEVICE_STATE,
    CHAR_LIGHTRING_COLOR_MOTION,
    CHAR_LIGHTRING_COLOR_OK,
    CHAR_PRESSURE,
    CHAR_TOTAL_AGE,
    CHAR_TOTAL_RUNNING_MOTOR,
)
from custom_components.philips_shaver.coordinator import PhilipsShaverCoordinator

from .conftest import chars_as_bytes


def make_stub(data: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(data=data or {}, _cleaning_sources={})


def process(results: dict[str, bytes], data: dict | None = None) -> dict:
    return PhilipsShaverCoordinator._process_results(make_stub(data), results)


def test_xp9201_snapshot_decodes(xp9201) -> None:
    """Feed the full XP9201 capture through the parser and pin key values.

    Captured live while the motor was running; total_running_motor matched
    the HA sensor value at capture time (239 min)."""
    data = process(chars_as_bytes(xp9201))

    assert data["battery"] == 90
    assert data["model_number"] == "XP9201"
    assert data["hardware_revision"] == "300011042261"
    assert data["device_state"] == "shaving"
    assert data["travel_lock"] is False
    # 0x0112 = 0x00ef little-endian → 239 minutes of cumulative motor runtime
    assert data["total_running_motor"] == 239
    # 0x0106 device age — reset to 0 by a firmware event, useless as runtime
    assert data["total_age"] == 0
    assert data["cleaning_cycles"] == 52
    # 0x011A idle value; the XP9201 has no 0x0318
    assert data["cleaning_progress"] == 100
    assert data["cleaning_progress_reported"] is True
    assert data["shaving_mode"] == "custom"
    assert data["handle_load_type"] == "shaving_heads"


def test_qp4530_snapshot_decodes(qp4530) -> None:
    """OneBlade capture (taken while the motor was running)."""
    data = process(chars_as_bytes(qp4530))

    assert data["battery"] == 94
    assert data["model_number"] == "Philips QP4530"
    assert data["hardware_revision"] == "300006520671"
    assert data["device_state"] == "shaving"
    assert data["travel_lock"] is False
    assert data["shaving_time"] == 67
    assert data["head_remaining"] == 74
    assert data["head_remaining_minutes"] == 126
    # 0x0112 exists on the OneBlade too: 0x0050 → 80 minutes
    assert data["total_running_motor"] == 80
    # 0x0106 is 0 on the QP4530 — device age is not usable as a runtime
    assert data["total_age"] == 0
    # No Control Service on this model → no mode/pressure keys at all
    assert "shaving_mode" not in data
    assert "handle_load_type" not in data


def test_missing_chars_leave_no_keys() -> None:
    """A device without a characteristic must not produce a key at all —
    sensors then report unknown instead of a bogus value (e.g. the S7887
    without 0x0112)."""
    data = process({CHAR_BATTERY_LEVEL: bytes([80])})

    data.pop("last_seen", None)  # timestamp added on every successful batch
    assert data == {"battery": 80}
    assert "total_running_motor" not in data
    assert "total_age" not in data


def test_none_values_are_skipped() -> None:
    """ESP bridge reports absent chars as None — parser must skip them."""
    data = process(
        {
            CHAR_BATTERY_LEVEL: bytes([80]),
            CHAR_TOTAL_RUNNING_MOTOR: None,
            CHAR_DEVICE_STATE: None,
        }
    )

    assert data["battery"] == 80
    assert "total_running_motor" not in data
    assert "device_state" not in data


def test_all_none_returns_existing_data_unchanged() -> None:
    existing = {"battery": 42}
    data = process({CHAR_TOTAL_AGE: None}, data=existing)
    assert data == existing


def test_total_running_motor_parses_uint16_le() -> None:
    data = process({CHAR_TOTAL_RUNNING_MOTOR: bytes.fromhex("9700")})
    assert data["total_running_motor"] == 0x97
    data = process({CHAR_TOTAL_RUNNING_MOTOR: bytes.fromhex("ffff")})
    assert data["total_running_motor"] == 65535


def test_pressure_parses_signed_int16_le() -> None:
    """Below zero must stay below zero, not wrap to ~65 000 (too high)."""
    assert process({CHAR_PRESSURE: bytes.fromhex("fbff")})["pressure"] == -5
    assert process({CHAR_PRESSURE: bytes.fromhex("0000")})["pressure"] == 0
    assert process({CHAR_PRESSURE: bytes.fromhex("a00f")})["pressure"] == 4000


def test_default_ring_colors_ok_green_motion_pink() -> None:
    assert LIGHTRING_DEFAULT_COLORS[CHAR_LIGHTRING_COLOR_OK] == (0x37, 0xFF, 0x00)
    assert LIGHTRING_DEFAULT_COLORS[CHAR_LIGHTRING_COLOR_MOTION] == (0xFF, 0x49, 0xFF)


def test_cleaning_progress_from_either_source() -> None:
    # XP line: platform service only
    assert process({CHAR_CLEANING_PROGRESS: b"\x09"})["cleaning_progress"] == 9
    # Series 7000/8000/9000: control service only
    data = process({CHAR_CLEANING_PROGRESS_CONTROL: b"\x2a"})
    assert data["cleaning_progress"] == 42
    assert data["cleaning_progress_reported"] is True


def test_running_cleaning_wins_over_idle_source() -> None:
    stub = make_stub()
    run = PhilipsShaverCoordinator._process_results
    stub.data = run(stub, {CHAR_CLEANING_PROGRESS: b"\x64"})
    assert stub.data["cleaning_progress"] == 100

    # The other source starts a cleaning: its progress is shown ...
    stub.data = run(stub, {CHAR_CLEANING_PROGRESS_CONTROL: b"\x1e"})
    assert stub.data["cleaning_progress"] == 30

    # ... and once it is idle again (0), the idle 100 comes back.
    stub.data = run(stub, {CHAR_CLEANING_PROGRESS_CONTROL: b"\x00"})
    assert stub.data["cleaning_progress"] == 100


def test_no_cleaning_source_leaves_progress_untouched() -> None:
    data = process({CHAR_BATTERY_LEVEL: b"\x50"}, {"cleaning_progress": None})
    assert data["cleaning_progress"] is None
    assert "cleaning_progress_reported" not in data
