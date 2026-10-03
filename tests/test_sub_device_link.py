"""Tests for hanging the Connection device under the shaver.

DeviceInfo(via_device=…) is deprecated since Home Assistant 2026.8 and is
removed in 2027.8; its replacement takes the parent's registry id, which the
entities do not know when they are built. The Connection device therefore
carries no parent in its DeviceInfo, and setup links it once the platforms
have registered every device.

The lookups go through ``async_get_own_device``: from 2026.9 on, every call to
``async_get_device`` logs a deprecation warning, and the scoped
``async_get_device_by_identifier`` that replaces it only exists from 2026.8.
The pinned test stack is the HA 2025.1 line, so the scoped branch is covered
through a registry double that refuses the deprecated call outright.
"""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.philips_shaver import _async_link_sub_devices
from custom_components.philips_shaver.const import (
    CONF_ADDRESS,
    CONF_ESP_DEVICE_NAME,
    CONF_TRANSPORT_TYPE,
    DOMAIN,
    TRANSPORT_ESP_BRIDGE,
)
from custom_components.philips_shaver.coordinator import PhilipsShaverCoordinator
from custom_components.philips_shaver.transport import EspBridgeTransport
from custom_components.philips_shaver.utils import async_get_own_device

ADDRESS = "AA:BB:CC:DD:EE:FF"


class BridgeStub(EspBridgeTransport):
    """A bridge transport that reports a firmware version and nothing else."""

    is_connected = False
    disconnect_count = 0
    bridge_version = "1.14.0"

    def __init__(self) -> None:
        pass


def add_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_TRANSPORT_TYPE: TRANSPORT_ESP_BRIDGE,
            CONF_ESP_DEVICE_NAME: "shaver-bridge",
        },
    )
    entry.add_to_hass(hass)
    return entry


def register_devices(hass, entry: MockConfigEntry):
    """The two devices as the platforms leave them: no parent anywhere."""
    reg = dr.async_get(hass)
    main = reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, ADDRESS)}
    )
    connection = reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{ADDRESS}_bridge")},
    )
    return main, connection


class ScopedRegistry:
    """A core from 2026.9 on: the scoped lookup exists, the old one warns.

    The old call raises here instead of warning, so a single leftover use
    fails the test rather than slipping through.
    """

    def __init__(self, hass) -> None:
        self._real = dr.async_get(hass)

    def __getattr__(self, name: str):
        return getattr(self._real, name)

    def async_get_device(self, identifiers=None, connections=None):
        raise AssertionError("deprecated async_get_device called")

    def async_get_device_by_identifier(self, identifier, config_entry_id):
        device = self._real.async_get_device(identifiers={identifier})
        if device is None or config_entry_id not in device.config_entries:
            return None
        return device


def test_link_keeps_the_connection_on_the_esp_node(hass) -> None:
    """The bridge path moves Connection under the ESPHome node; keep that."""
    entry = add_entry(hass)
    _, connection = register_devices(hass, entry)
    esp_entry = MockConfigEntry(domain="esphome", data={})
    esp_entry.add_to_hass(hass)
    reg = dr.async_get(hass)
    esp_device = reg.async_get_or_create(
        config_entry_id=esp_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "24:0a:c4:11:22:33")},
    )
    reg.async_update_device(connection.id, via_device_id=esp_device.id)

    _async_link_sub_devices(hass, entry)

    assert reg.async_get(connection.id).via_device_id == esp_device.id


def test_link_without_the_shaver_device_leaves_connection_alone(hass) -> None:
    entry = add_entry(hass)
    connection = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{ADDRESS}_bridge")},
    )

    _async_link_sub_devices(hass, entry)

    assert dr.async_get(hass).async_get(connection.id).via_device_id is None


def test_link_on_a_scoped_core_never_calls_the_deprecated_lookup(
    hass, monkeypatch
) -> None:
    entry = add_entry(hass)
    main, connection = register_devices(hass, entry)
    real = dr.async_get(hass)
    double = ScopedRegistry(hass)
    monkeypatch.setattr(dr, "async_get", lambda _hass: double)

    _async_link_sub_devices(hass, entry)

    assert real.async_get(connection.id).via_device_id == main.id


def test_own_device_lookup_is_scoped_to_the_entry(hass) -> None:
    """Another entry's device under the same identifier is not ours."""
    entry = add_entry(hass)
    main, _ = register_devices(hass, entry)
    other = MockConfigEntry(domain=DOMAIN, data={})
    other.add_to_hass(hass)
    double = ScopedRegistry(hass)

    assert async_get_own_device(double, ADDRESS, entry.entry_id) == main
    assert async_get_own_device(double, ADDRESS, other.entry_id) is None


def test_bridge_version_lands_on_the_connection_device(hass) -> None:
    """The Connection device is registered under the shaver's MAC.

    The lookup used to build its identifier from the ESP device name instead,
    found nothing once the MAC was known, and never wrote the version.
    """
    entry = add_entry(hass)
    _, connection = register_devices(hass, entry)
    coordinator = PhilipsShaverCoordinator(hass, entry, BridgeStub())

    coordinator._check_bridge_version()

    assert dr.async_get(hass).async_get(connection.id).sw_version == "1.14.0"
