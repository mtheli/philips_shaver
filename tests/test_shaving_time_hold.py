"""Behaviour tests for the last-session duration sensor.

The device counts the field up while the handle runs and clears it back to
0 on its own a while after the session, so the sensor holds the last
reported duration once the handle is idle. ``native_value`` and the update
callback only touch ``self.coordinator.data``, so the sensor is
instantiated without its HA-bound ``__init__`` and fed a coordinator stub.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.philips_shaver.sensor import PhilipsShavingTimeSensor


def make_sensor(data: dict) -> PhilipsShavingTimeSensor:
    sensor = PhilipsShavingTimeSensor.__new__(PhilipsShavingTimeSensor)
    sensor.coordinator = SimpleNamespace(data=data)
    sensor._last_duration = None
    # The update callback writes the state; without a hass behind the
    # sensor that call is the only part that cannot run here.
    sensor.async_write_ha_state = lambda: None
    return sensor


def feed(sensor: PhilipsShavingTimeSensor, **values) -> int | None:
    """Push a device update through the real callback, then read the state."""
    sensor.coordinator.data.update(values)
    sensor._handle_coordinator_update()
    return sensor.native_value


def test_counts_up_live_while_shaving() -> None:
    sensor = make_sensor({"device_state": "shaving", "shaving_time": 0})
    assert sensor.native_value == 0
    assert feed(sensor, shaving_time=9) == 9
    assert feed(sensor, shaving_time=29) == 29


def test_holds_last_duration_when_device_clears_it() -> None:
    sensor = make_sensor({"device_state": "shaving", "shaving_time": 0})
    feed(sensor, shaving_time=29)
    # Session over — the handle idles with the result still reported.
    assert feed(sensor, device_state="off") == 29
    # Half an hour later the device clears the field on its own.
    assert feed(sensor, shaving_time=0) == 29


def test_new_session_replaces_a_longer_previous_one() -> None:
    sensor = make_sensor({"device_state": "shaving", "shaving_time": 0})
    feed(sensor, shaving_time=459)
    feed(sensor, device_state="off", shaving_time=0)

    # Next session starts: the live 0 must reach consumers that seed a
    # timer from this sensor, instead of the previous result.
    assert feed(sensor, device_state="shaving") == 0
    assert feed(sensor, shaving_time=1) == 1


def test_unknown_until_the_device_reports_a_duration() -> None:
    sensor = make_sensor({})
    assert sensor.native_value is None
    # A device that answers the read with 0 and was never used stays unknown
    # rather than claiming a zero-second session.
    assert feed(sensor, device_state="off", shaving_time=0) is None


@pytest.mark.parametrize("value", ["nonsense", None])
def test_unusable_reading_does_not_disturb_the_held_value(value) -> None:
    sensor = make_sensor({"device_state": "off", "shaving_time": 29})
    sensor._last_duration = 29
    assert feed(sensor, shaving_time=value) == 29
