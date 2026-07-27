"""Tests for the YAML-area backfill in async_setup_entry.

The ESP YAML `area:` arrives as CONF_AREA in the entry data and is applied
to the registry devices after platform setup. Both registry devices must get
it — the main device and the Connection sub-device ({id}_bridge) — because
neither carries a suggested_area, so this backfill is the only thing that
prefills the post-setup "Name and assign" dialog. A manually assigned area
must never be overwritten.
"""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.philips_shaver import _async_apply_yaml_area
from custom_components.philips_shaver.const import (
    CONF_ADDRESS,
    CONF_AREA,
    CONF_ESP_DEVICE_NAME,
    CONF_TRANSPORT_TYPE,
    DOMAIN,
    TRANSPORT_ESP_BRIDGE,
)

ADDRESS = "AA:BB:CC:DD:EE:FF"


def make_entry(hass, area: str | None = "Bathroom") -> MockConfigEntry:
    data = {
        CONF_ADDRESS: ADDRESS,
        CONF_TRANSPORT_TYPE: TRANSPORT_ESP_BRIDGE,
        CONF_ESP_DEVICE_NAME: "shaver-bridge",
    }
    if area is not None:
        data[CONF_AREA] = area
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    return entry


def register_devices(hass, entry: MockConfigEntry):
    dev_reg = dr.async_get(hass)
    main = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, ADDRESS)},
    )
    sub = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{ADDRESS}_bridge")},
    )
    return main, sub


def test_area_lands_on_main_and_connection_sub_device(hass) -> None:
    entry = make_entry(hass)
    main, sub = register_devices(hass, entry)

    _async_apply_yaml_area(hass, entry)

    dev_reg = dr.async_get(hass)
    area = ar.async_get(hass).async_get_area_by_name("Bathroom")
    assert area is not None
    assert dev_reg.async_get(main.id).area_id == area.id
    assert dev_reg.async_get(sub.id).area_id == area.id


def test_manual_assignment_is_not_overwritten(hass) -> None:
    """A user-chosen area wins over the YAML value — on either device."""
    entry = make_entry(hass)
    main, sub = register_devices(hass, entry)
    bedroom = ar.async_get(hass).async_get_or_create("Bedroom")
    dr.async_get(hass).async_update_device(sub.id, area_id=bedroom.id)

    _async_apply_yaml_area(hass, entry)

    dev_reg = dr.async_get(hass)
    bathroom = ar.async_get(hass).async_get_area_by_name("Bathroom")
    assert dev_reg.async_get(main.id).area_id == bathroom.id
    assert dev_reg.async_get(sub.id).area_id == bedroom.id


def test_no_yaml_area_is_a_no_op(hass) -> None:
    entry = make_entry(hass, area=None)
    main, sub = register_devices(hass, entry)

    _async_apply_yaml_area(hass, entry)

    dev_reg = dr.async_get(hass)
    assert dev_reg.async_get(main.id).area_id is None
    assert dev_reg.async_get(sub.id).area_id is None
    # No unused area registered either
    assert ar.async_get(hass).async_get_area_by_name("Bathroom") is None


def test_missing_sub_device_does_not_break_the_backfill(hass) -> None:
    """Only the main device exists (e.g. Connection entities disabled)."""
    entry = make_entry(hass)
    dev_reg = dr.async_get(hass)
    main = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, ADDRESS)},
    )

    _async_apply_yaml_area(hass, entry)

    bathroom = ar.async_get(hass).async_get_area_by_name("Bathroom")
    assert dev_reg.async_get(main.id).area_id == bathroom.id
