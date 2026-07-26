"""Tests for the device-registry fields the coordinator maintains.

The shaver reports its model, firmware and serial number over the Device
Information Service. All three belong on the device page, but a read that
only answered part of them must never wipe what an earlier read had already
established — and a shaver without a serial answers with all zeros, which is
"unknown" rather than a serial worth showing.
"""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.philips_shaver.const import (
    CONF_ADDRESS,
    CONF_ESP_DEVICE_NAME,
    CONF_TRANSPORT_TYPE,
    DOMAIN,
    TRANSPORT_ESP_BRIDGE,
)
from custom_components.philips_shaver.coordinator import PhilipsShaverCoordinator

ADDRESS = "AA:BB:CC:DD:EE:FF"


class StubTransport:
    """Just enough transport for coordinator construction."""

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
    return PhilipsShaverCoordinator(hass, entry, StubTransport()), entry


def register_device(hass, entry: MockConfigEntry):
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, ADDRESS)},
    )


def test_model_firmware_and_serial_land_on_the_device(hass) -> None:
    coordinator, entry = make_coordinator(hass)
    device = register_device(hass, entry)

    coordinator._update_device_registry(
        {
            "model_number": "XP9201",
            "firmware": "1.2.3",
            "serial_number": "S9K12345678",
        }
    )

    device = dr.async_get(hass).async_get(device.id)
    assert device.model == "XP9201"
    assert device.sw_version == "1.2.3"
    assert device.serial_number == "S9K12345678"


def test_all_zero_serial_is_not_written(hass) -> None:
    """A shaver without a serial answers with zeros — that is not a serial."""
    coordinator, entry = make_coordinator(hass)
    device = register_device(hass, entry)

    coordinator._update_device_registry(
        {
            "model_number": "QP4530",
            "firmware": "2.0.0",
            "serial_number": "0000000000",
        }
    )

    device = dr.async_get(hass).async_get(device.id)
    assert device.model == "QP4530"
    assert device.serial_number is None


def test_partial_read_keeps_previously_known_fields(hass) -> None:
    """A read that only returns the model must not clear firmware/serial."""
    coordinator, entry = make_coordinator(hass)
    device = register_device(hass, entry)

    coordinator._update_device_registry(
        {
            "model_number": "XP9201",
            "firmware": "1.2.3",
            "serial_number": "S9K12345678",
        }
    )
    coordinator._update_device_registry({"model_number": "XP9201"})

    device = dr.async_get(hass).async_get(device.id)
    assert device.sw_version == "1.2.3"
    assert device.serial_number == "S9K12345678"


def test_serial_only_read_still_updates_the_device(hass) -> None:
    """The old guard returned early without a model — a serial counts too."""
    coordinator, entry = make_coordinator(hass)
    device = register_device(hass, entry)

    coordinator._update_device_registry({"serial_number": "S9K12345678"})

    device = dr.async_get(hass).async_get(device.id)
    assert device.serial_number == "S9K12345678"
    assert device.model is None


def test_nothing_read_is_a_no_op(hass) -> None:
    coordinator, entry = make_coordinator(hass)
    device = register_device(hass, entry)

    coordinator._update_device_registry({"battery": 80})

    device = dr.async_get(hass).async_get(device.id)
    assert device.model is None
    assert device.sw_version is None
    assert device.serial_number is None
