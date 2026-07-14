"""Tests for the coordinator-level store that survives HA restarts.

The shaver is a sleepy device — after a restart it stays out of BLE reach
until the next shave, so the coordinator persists its last known data to
disk and reloads it during setup. Entities stay available on restored data;
live session state is deliberately not persisted. Ported from the Sonicare
integration (v0.19.0).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.philips_shaver.const import (
    CONF_ADDRESS,
    CONF_ESP_DEVICE_NAME,
    CONF_TRANSPORT_TYPE,
    DOMAIN,
    TRANSPORT_ESP_BRIDGE,
)
from custom_components.philips_shaver.coordinator import (
    STORAGE_VERSION,
    PhilipsShaverCoordinator,
    _storage_key,
    async_remove_stored_data,
)
from custom_components.philips_shaver.entity import PhilipsShaverEntity

ADDRESS = "AA:BB:CC:DD:EE:FF"
LAST_SEEN = datetime(2026, 7, 14, 6, 30, tzinfo=timezone.utc)


class StubTransport:
    """Just enough transport for coordinator/entity construction."""

    is_connected = False
    disconnect_count = 0


def make_coordinator(hass) -> tuple[PhilipsShaverCoordinator, MockConfigEntry]:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_TRANSPORT_TYPE: TRANSPORT_ESP_BRIDGE,
            CONF_ESP_DEVICE_NAME: "shaver-bridge",
        },
    )
    entry.add_to_hass(hass)
    coordinator = PhilipsShaverCoordinator(hass, entry, StubTransport())
    return coordinator, entry


def test_data_to_save_drops_live_and_private_keys(hass) -> None:
    coordinator, _ = make_coordinator(hass)
    coordinator.data.update(
        {
            "battery": 87,
            "device_state": "shaving",
            "motor_rpm": 7200,
            "pressure": 3,
            "app_handle_settings_raw": b"\x10\x00",
            "last_seen": LAST_SEEN,
            "_connecting": True,
        }
    )

    saved = coordinator._data_to_save()

    assert saved["battery"] == 87
    assert saved["last_seen"] == LAST_SEEN.isoformat()
    for key in (
        "device_state",
        "motor_rpm",
        "pressure",
        "app_handle_settings_raw",
        "_connecting",
    ):
        assert key not in saved


async def test_load_restores_values_and_parses_types(hass, hass_storage) -> None:
    coordinator, entry = make_coordinator(hass)
    hass_storage[_storage_key(entry.entry_id)] = {
        "version": STORAGE_VERSION,
        "data": {
            "battery": 42,
            "head_remaining": 63,
            "days_since_last_used": 2,
            "color_ok": [0, 255, 0],
            "last_seen": LAST_SEEN.isoformat(),
            # Live keys from an older store format must not be adopted
            "device_state": "shaving",
        },
    }

    await coordinator.async_load_stored_data()

    assert coordinator.data["battery"] == 42
    assert coordinator.data["head_remaining"] == 63
    assert coordinator.data["days_since_last_used"] == 2
    assert coordinator.data["color_ok"] == (0, 255, 0)
    assert isinstance(coordinator.data["color_ok"], tuple)
    assert coordinator.data["last_seen"] == LAST_SEEN
    assert coordinator.data["device_state"] == "off"


async def test_load_without_store_is_noop(hass, hass_storage) -> None:
    coordinator, _ = make_coordinator(hass)
    before = dict(coordinator.data)

    await coordinator.async_load_stored_data()

    assert coordinator.data == before


async def test_updated_data_is_saved_debounced(hass, hass_storage) -> None:
    coordinator, entry = make_coordinator(hass)
    new_data = dict(coordinator.data)
    new_data.update({"battery": 55, "last_seen": LAST_SEEN})

    coordinator.async_set_updated_data(new_data)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done()

    stored = hass_storage[_storage_key(entry.entry_id)]["data"]
    assert stored["battery"] == 55
    assert stored["last_seen"] == LAST_SEEN.isoformat()


async def test_remove_stored_data(hass, hass_storage) -> None:
    _, entry = make_coordinator(hass)
    key = _storage_key(entry.entry_id)
    hass_storage[key] = {"version": STORAGE_VERSION, "data": {"battery": 1}}

    await async_remove_stored_data(hass, entry.entry_id)

    assert key not in hass_storage


async def test_entity_available_on_restored_data(hass, hass_storage) -> None:
    """Sleepy device: once seen (restored counts), entities stay available."""
    coordinator, entry = make_coordinator(hass)
    hass_storage[_storage_key(entry.entry_id)] = {
        "version": STORAGE_VERSION,
        "data": {"battery": 42, "last_seen": LAST_SEEN.isoformat()},
    }
    await coordinator.async_load_stored_data()

    entity = PhilipsShaverEntity(coordinator, entry)

    assert coordinator.transport.is_connected is False
    assert entity.available is True


async def test_entity_unavailable_when_never_seen(hass) -> None:
    coordinator, entry = make_coordinator(hass)
    entity = PhilipsShaverEntity(coordinator, entry)

    assert entity.available is False

    coordinator.transport.is_connected = True
    assert entity.available is True
