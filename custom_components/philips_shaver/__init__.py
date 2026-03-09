# custom_components/philips_shaver/__init__.py
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_TRANSPORT_TYPE,
    TRANSPORT_ESP_BRIDGE,
    CONF_ESP_DEVICE_NAME,
)
from .coordinator import PhilipsShaverCoordinator
from .transport import BleakTransport, EspBridgeTransport

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.LIGHT, Platform.SELECT, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SWITCH]

SERVICE_FETCH_HISTORY = "fetch_history"


def _async_link_via_esp_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Link the shaver device to its ESP32 bridge in the device registry."""
    esp_device_name = entry.data[CONF_ESP_DEVICE_NAME]
    dev_reg = dr.async_get(hass)

    # Find the ESPHome config entry matching our bridge device name
    # ESPHome uses hyphens (atom-lite), we store underscores (atom_lite)
    esp_mac: str | None = None
    normalized = esp_device_name.replace("_", "-")
    for esphome_entry in hass.config_entries.async_entries("esphome"):
        entry_name = esphome_entry.data.get("device_name", "")
        if entry_name == esp_device_name or entry_name == normalized:
            esp_mac = esphome_entry.unique_id
            break

    if not esp_mac:
        _LOGGER.debug("ESPHome config entry for '%s' not found", esp_device_name)
        return

    # ESPHome registers devices by network MAC connection
    esp_device = dev_reg.async_get_device(
        connections={(dr.CONNECTION_NETWORK_MAC, esp_mac)}
    )
    if not esp_device:
        _LOGGER.debug("ESPHome device for '%s' not in registry", esp_device_name)
        return

    # Find our shaver device and set via_device
    shaver_device = dev_reg.async_get_device(
        identifiers={(DOMAIN, esp_device_name)}
    )
    if shaver_device:
        dev_reg.async_update_device(shaver_device.id, via_device_id=esp_device.id)
        _LOGGER.info("Linked shaver device to ESP bridge '%s'", esp_device_name)

    # Also link the bridge sub-device to the ESPHome device
    bridge_device = dev_reg.async_get_device(
        identifiers={(DOMAIN, f"{esp_device_name}_bridge")}
    )
    if bridge_device:
        dev_reg.async_update_device(bridge_device.id, via_device_id=esp_device.id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Philips Shaver from a config entry."""
    # Create transport based on config
    transport_type = entry.data.get(CONF_TRANSPORT_TYPE)
    if transport_type == TRANSPORT_ESP_BRIDGE:
        esp_device_name = entry.data[CONF_ESP_DEVICE_NAME]
        transport = EspBridgeTransport(hass, esp_device_name, esp_device_name)
    else:
        address = entry.data["address"]
        transport = BleakTransport(hass, address)

    coordinator = PhilipsShaverCoordinator(hass, entry, transport)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Link shaver device to ESP bridge device via device registry
    if transport_type == TRANSPORT_ESP_BRIDGE:
        _async_link_via_esp_device(hass, entry)

    # Start polling/live monitoring after platforms are registered
    await coordinator.async_start()
    if transport_type != TRANSPORT_ESP_BRIDGE:
        hass.async_create_task(coordinator._async_start_advertisement_logging())

    # Register services (only once)
    if not hass.services.has_service(DOMAIN, SERVICE_FETCH_HISTORY):
        async def handle_fetch_history(call: ServiceCall) -> ServiceResponse:
            """Handle the fetch_history service call."""
            # Find the coordinator for the requested device (or use first one)
            entry_id = call.data.get("entry_id")
            if entry_id and entry_id in hass.data[DOMAIN]:
                coord = hass.data[DOMAIN][entry_id]["coordinator"]
            else:
                # Use first available coordinator
                first = next(iter(hass.data[DOMAIN].values()), None)
                if not first:
                    _LOGGER.error("No Philips Shaver devices configured")
                    return {"sessions": []}
                coord = first["coordinator"]

            sessions = await coord.async_fetch_history()
            return {"sessions": sessions}

        hass.services.async_register(
            DOMAIN,
            SERVICE_FETCH_HISTORY,
            handle_fetch_history,
            schema=vol.Schema({
                vol.Optional("entry_id"): str,
            }),
            supports_response=SupportsResponse.ONLY,
        )

    device_id = entry.data.get("address") or entry.data.get(CONF_ESP_DEVICE_NAME)
    _LOGGER.info("Philips Shaver integration loaded – device: %s", device_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info("Unloading philips shaver integration started")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    coordinator = hass.data[DOMAIN].pop(entry.entry_id)["coordinator"]
    await coordinator.async_shutdown()

    # Remove services if no more entries
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_FETCH_HISTORY)

    _LOGGER.info("Unloading philips shaver integration finished")
    return True
