"""Control service detection over the ESP bridge (issue #29).

The ESP setup probes each service with one characteristic. The Control
service used to be probed via Handle Load Type (0x0322), which some models
(S7885) leave out, so the whole service was dropped: no pressure, motion or
light ring. It is now probed via Capabilities (0x0302). Existing ESP entries
without the service are flagged by the v1.4 migration and re-checked once on
the next connect; entries created with the new probe are never re-checked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.philips_shaver import config_flow as cf
from custom_components.philips_shaver import async_migrate_entry
from custom_components.philips_shaver.const import (
    CHAR_BATTERY_LEVEL,
    CHAR_CAPABILITIES,
    CHAR_DEVICE_STATE,
    CHAR_HANDLE_LOAD_TYPE,
    CHAR_MODEL_NUMBER,
    CHAR_MOTION_TYPE,
    CHAR_PRESSURE,
    CONF_CAPABILITIES,
    CONF_ESP_BRIDGE_ID,
    CONF_ESP_DEVICE_ID_LEGACY,
    CONF_RECHECK_CONTROL,
    CONF_SERVICES,
    CONF_TRANSPORT_TYPE,
    SVC_BATTERY,
    SVC_CONTROL,
    SVC_PLATFORM,
    TRANSPORT_ESP_BRIDGE,
)
from custom_components.philips_shaver.coordinator import PhilipsShaverCoordinator

# S7885: Control service present, Handle Load Type missing
S7885_CHARS = {
    CHAR_BATTERY_LEVEL: b"\x50",
    CHAR_MODEL_NUMBER: b"S7885",
    CHAR_DEVICE_STATE: b"\x01",
    CHAR_CAPABILITIES: b"\x69\x00\x00\x00",
}


class FakeEspTransport:
    """Behaves like EspBridgeTransport: a missing characteristic reads as
    None and leaves the bridge's error code for pop_read_error()."""

    def __init__(self, chars: dict[str, bytes], error: str | None = "not_found") -> None:
        self.chars = chars
        self.error = error
        self.errors: dict[str, str] = {}
        self.reads: list[str] = []
        self.detected_mac = "AA:BB:CC:DD:EE:FF"

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def read_char(self, char_uuid: str) -> bytes | None:
        self.reads.append(char_uuid)
        value = self.chars.get(char_uuid)
        if value is None and self.error:
            self.errors[char_uuid] = self.error
        return value

    def pop_read_error(self, char_uuid: str) -> str | None:
        return self.errors.pop(char_uuid, None)


def test_control_service_probed_via_capabilities() -> None:
    assert cf.PhilipsShaverConfigFlow.SERVICE_PROBE_CHARS[SVC_CONTROL] == CHAR_CAPABILITIES


async def test_esp_setup_finds_control_without_handle_load_type(monkeypatch) -> None:
    transport = FakeEspTransport(S7885_CHARS)
    monkeypatch.setattr(cf, "EspBridgeTransport", lambda *a, **k: transport)
    flow = cf.PhilipsShaverConfigFlow.__new__(cf.PhilipsShaverConfigFlow)
    flow.hass = MagicMock()
    flow._bump_progress = lambda *_: None

    result = await flow._async_fetch_capabilities_esp("addr", "esp", "shaver")

    assert SVC_CONTROL in result["services"]
    assert result["capabilities"] == 0x69
    assert CHAR_HANDLE_LOAD_TYPE not in transport.reads
    # The probe read is reused, not read a second time
    assert transport.reads.count(CHAR_CAPABILITIES) == 1


async def test_esp_setup_without_control_service(monkeypatch) -> None:
    chars = {k: v for k, v in S7885_CHARS.items() if k != CHAR_CAPABILITIES}
    transport = FakeEspTransport(chars)
    monkeypatch.setattr(cf, "EspBridgeTransport", lambda *a, **k: transport)
    flow = cf.PhilipsShaverConfigFlow.__new__(cf.PhilipsShaverConfigFlow)
    flow.hass = MagicMock()
    flow._bump_progress = lambda *_: None

    result = await flow._async_fetch_capabilities_esp("addr", "esp", "shaver")

    assert SVC_CONTROL not in result["services"]
    assert result["capabilities"] == 0


def make_coordinator(transport, *, esp: bool = True, services=None, flagged: bool = True):
    services = [SVC_BATTERY, SVC_PLATFORM] if services is None else services
    coordinator = PhilipsShaverCoordinator.__new__(PhilipsShaverCoordinator)
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.transport = transport
    coordinator._is_esp_bridge = esp
    coordinator._control_recheck_done = False
    coordinator.entry = SimpleNamespace(
        entry_id="entry1",
        data={
            CONF_SERVICES: list(services),
            CONF_CAPABILITIES: 0,
            **({CONF_RECHECK_CONTROL: True} if flagged else {}),
        },
    )

    def update_entry(entry, data):
        entry.data = data

    coordinator.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_update_entry=MagicMock(side_effect=update_entry),
            async_schedule_reload=MagicMock(),
        )
    )
    coordinator.available_services = {s.lower() for s in services}
    coordinator._apply_available_services()
    return coordinator


async def test_recheck_adds_missing_control_service() -> None:
    coordinator = make_coordinator(FakeEspTransport(S7885_CHARS))
    assert CHAR_PRESSURE not in coordinator._notify_chars

    assert await coordinator._async_recheck_control_service() is True

    assert SVC_CONTROL in coordinator.entry.data[CONF_SERVICES]
    assert coordinator.entry.data[CONF_CAPABILITIES] == 0x69
    assert CONF_RECHECK_CONTROL not in coordinator.entry.data
    assert CHAR_PRESSURE in coordinator._notify_chars
    assert CHAR_MOTION_TYPE in coordinator._notify_chars
    coordinator.hass.config_entries.async_schedule_reload.assert_called_once_with("entry1")


async def test_recheck_runs_once_when_service_absent() -> None:
    chars = {k: v for k, v in S7885_CHARS.items() if k != CHAR_CAPABILITIES}
    transport = FakeEspTransport(chars)
    coordinator = make_coordinator(transport)

    assert await coordinator._async_recheck_control_service() is False
    assert await coordinator._async_recheck_control_service() is False

    assert transport.reads == [CHAR_CAPABILITIES]
    # Definite "absent" answer: flag dropped, so later starts skip the read
    assert CONF_RECHECK_CONTROL not in coordinator.entry.data
    assert SVC_CONTROL not in coordinator.entry.data[CONF_SERVICES]
    coordinator.hass.config_entries.async_schedule_reload.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        None,  # ESP read timeout: None without any error code
        "read_timeout",
        "queue_full",
        "not_connected",
    ],
)
async def test_recheck_keeps_flag_without_definite_answer(error) -> None:
    chars = {k: v for k, v in S7885_CHARS.items() if k != CHAR_CAPABILITIES}
    transport = FakeEspTransport(chars, error=error)
    coordinator = make_coordinator(transport)

    assert await coordinator._async_recheck_control_service() is False
    assert coordinator.entry.data[CONF_RECHECK_CONTROL] is True
    coordinator.hass.config_entries.async_update_entry.assert_not_called()

    # The next connect tries again — and succeeds once the shaver answers
    transport.chars = S7885_CHARS
    assert await coordinator._async_recheck_control_service() is True
    assert SVC_CONTROL in coordinator.entry.data[CONF_SERVICES]
    assert CONF_RECHECK_CONTROL not in coordinator.entry.data


async def test_recheck_keeps_flag_when_read_raises() -> None:
    class FailingTransport(FakeEspTransport):
        async def read_char(self, char_uuid):
            raise TimeoutError

    coordinator = make_coordinator(FailingTransport(S7885_CHARS))

    assert await coordinator._async_recheck_control_service() is False
    assert coordinator.entry.data[CONF_RECHECK_CONTROL] is True
    coordinator.hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.parametrize(
    ("esp", "flagged"),
    [
        (True, False),  # not flagged: new-probe entry, XP9201, done OneBlade
        (False, True),  # direct BLE lists real services
    ],
)
async def test_recheck_skipped(esp, flagged) -> None:
    transport = FakeEspTransport(S7885_CHARS)
    coordinator = make_coordinator(transport, esp=esp, flagged=flagged)

    assert await coordinator._async_recheck_control_service() is False
    assert transport.reads == []


def make_entry(data, minor_version=3):
    entry = SimpleNamespace(version=1, minor_version=minor_version, data=data, entry_id="e")

    def update_entry(e, data=None, minor_version=None):
        if data is not None:
            e.data = data
        if minor_version is not None:
            e.minor_version = minor_version

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_update_entry=MagicMock(side_effect=update_entry))
    )
    return hass, entry


@pytest.mark.parametrize(
    ("data", "flagged"),
    [
        # ESP entry stored without Control (S7885 / OneBlade): flag
        ({CONF_TRANSPORT_TYPE: TRANSPORT_ESP_BRIDGE,
          CONF_SERVICES: [SVC_BATTERY, SVC_PLATFORM]}, True),
        # ESP entry with Control (XP9201): untouched
        ({CONF_TRANSPORT_TYPE: TRANSPORT_ESP_BRIDGE,
          CONF_SERVICES: [SVC_BATTERY, SVC_PLATFORM, SVC_CONTROL]}, False),
        # Direct BLE: service list comes from the real GATT table
        ({CONF_TRANSPORT_TYPE: "bleak", CONF_SERVICES: [SVC_BATTERY]}, False),
        # Legacy ESP entry without service list reads everything anyway
        ({CONF_TRANSPORT_TYPE: TRANSPORT_ESP_BRIDGE}, False),
    ],
)
async def test_migration_flags_esp_entries_without_control(data, flagged) -> None:
    hass, entry = make_entry(dict(data))

    assert await async_migrate_entry(hass, entry) is True

    assert entry.minor_version == 4
    assert entry.data.get(CONF_RECHECK_CONTROL, False) is flagged


async def test_migration_skips_current_entries() -> None:
    data = {CONF_TRANSPORT_TYPE: TRANSPORT_ESP_BRIDGE, CONF_SERVICES: [SVC_BATTERY]}
    hass, entry = make_entry(dict(data), minor_version=4)

    await async_migrate_entry(hass, entry)

    assert CONF_RECHECK_CONTROL not in entry.data


async def test_migration_from_1_2_runs_both_steps() -> None:
    data = {
        CONF_TRANSPORT_TYPE: TRANSPORT_ESP_BRIDGE,
        CONF_SERVICES: [SVC_BATTERY],
        CONF_ESP_DEVICE_ID_LEGACY: "shaver",
    }
    hass, entry = make_entry(dict(data), minor_version=2)

    await async_migrate_entry(hass, entry)

    assert entry.minor_version == 4
    assert entry.data[CONF_ESP_BRIDGE_ID] == "shaver"
    assert CONF_ESP_DEVICE_ID_LEGACY not in entry.data
    assert entry.data[CONF_RECHECK_CONTROL] is True
