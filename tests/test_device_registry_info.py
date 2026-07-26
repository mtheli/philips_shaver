"""Tests for the device-registry fields the coordinator maintains.

The shaver reports its model, firmware and serial number over the Device
Information Service. All three belong on the device page, but a read that
only answered part of them must never wipe what an earlier read had already
established — and a shaver without a serial answers with all zeros, which is
"unknown" rather than a serial worth showing.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.philips_shaver.const import (
    CONF_ADDRESS,
    CONF_ESP_DEVICE_NAME,
    CONF_TRANSPORT_TYPE,
    DOMAIN,
    TRANSPORT_BLEAK,
    TRANSPORT_ESP_BRIDGE,
)
from custom_components.philips_shaver.coordinator import PhilipsShaverCoordinator
from custom_components.philips_shaver.entity import PhilipsConnectionEntity

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


def test_hardware_revision_lands_on_the_device(hass) -> None:
    coordinator, entry = make_coordinator(hass)
    device = register_device(hass, entry)

    coordinator._update_device_registry(
        {
            "model_number": "XP9201",
            "hardware_revision": "300011042261",
        }
    )

    device = dr.async_get(hass).async_get(device.id)
    assert device.hw_version == "300011042261"


def test_not_reported_hardware_revision_is_not_written(hass) -> None:
    """Devices that don't populate 2A27 answer with "" or zeros."""
    coordinator, entry = make_coordinator(hass)
    device = register_device(hass, entry)

    coordinator._update_device_registry(
        {
            "model_number": "XP9201",
            "hardware_revision": "00",
        }
    )

    device = dr.async_get(hass).async_get(device.id)
    assert device.hw_version is None


def test_hardware_only_read_still_updates_the_device(hass) -> None:
    coordinator, entry = make_coordinator(hass)
    device = register_device(hass, entry)

    coordinator._update_device_registry({"hardware_revision": "300006520671"})

    device = dr.async_get(hass).async_get(device.id)
    assert device.hw_version == "300006520671"
    assert device.model is None


def test_nul_padded_serial_is_not_written(hass) -> None:
    """A QP4530 answers the serial characteristic with twenty NUL bytes.

    They decode to "\\x00\\x00…", which is neither empty nor made of
    ASCII zeros — the earlier check let it through and the device page
    ended up showing a "Serial number:" row with nothing after it.
    """
    coordinator, entry = make_coordinator(hass)
    device = register_device(hass, entry)

    coordinator._update_device_registry({"serial_number": "\x00" * 20})

    device = dr.async_get(hass).async_get(device.id)
    assert device.serial_number is None


def test_connection_sub_device_links_to_the_main_device(hass) -> None:
    """With direct BLE nothing rewires the Connection sub-device later.

    The ESP path re-parents it to the ESP host after setup, but on a local
    adapter the declared via_device is the only parent link — without it the
    sub-device floats around unattached in the device list.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_TRANSPORT_TYPE: TRANSPORT_BLEAK,
        },
    )
    entry.add_to_hass(hass)
    coordinator = PhilipsShaverCoordinator(hass, entry, StubTransport())

    entity = PhilipsConnectionEntity(coordinator, entry)

    assert entity._attr_device_info["via_device"] == (DOMAIN, ADDRESS)


def test_connection_sub_device_name_is_translatable(hass) -> None:
    """The sub-device is named via a translation key so the trailing word
    ("Connection") follows the interface language; the parent name rides
    along as a placeholder rather than being baked into a fixed string."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_TRANSPORT_TYPE: TRANSPORT_BLEAK,
            "device_name": "Bathroom Shaver",
        },
    )
    entry.add_to_hass(hass)
    coordinator = PhilipsShaverCoordinator(hass, entry, StubTransport())

    info = PhilipsConnectionEntity(coordinator, entry)._attr_device_info

    assert info["translation_key"] == "connection"
    assert info["translation_placeholders"] == {"device_name": "Bathroom Shaver"}
    assert "name" not in info


def test_connection_translation_key_resolves_to_the_localized_name(hass) -> None:
    """End-to-end through the registry: the key we set must actually resolve
    to "<parent> Connection". A wrong key path or placeholder name would make
    async_get_or_create fall back to the bare key ("connection", parent lost) —
    the dict-level test above cannot catch that. The template comes from the
    real strings.json so a renamed key or missing device section fails here.
    """
    strings = json.loads(
        (
            Path(__file__).parent.parent
            / "custom_components/philips_shaver/strings.json"
        ).read_text(encoding="utf-8")
    )
    name_template = strings["device"]["connection"]["name"]

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: ADDRESS})
    entry.add_to_hass(hass)

    cached = {f"component.{DOMAIN}.device.connection.name": name_template}
    with patch(
        "homeassistant.helpers.device_registry.translation."
        "async_get_cached_translations",
        return_value=cached,
    ):
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{ADDRESS}_bridge")},
            translation_key="connection",
            translation_placeholders={"device_name": "Bathroom Shaver"},
        )

    assert device.name == "Bathroom Shaver Connection"


def test_previously_written_padding_is_cleared(hass) -> None:
    """A value an older version wrote through must not linger.

    It would never be overwritten — the new read is correctly ignored, so
    without an explicit clear the blank row would stay forever.
    """
    coordinator, entry = make_coordinator(hass)
    device = register_device(hass, entry)
    dr.async_get(hass).async_update_device(device.id, serial_number="\x00" * 20)

    # A later read returns the same padding — the clear must still happen.
    coordinator._update_device_registry({"serial_number": "\x00" * 20})

    device = dr.async_get(hass).async_get(device.id)
    assert device.serial_number is None
