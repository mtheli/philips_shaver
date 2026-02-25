# custom_components/philips_shaver/__init__.py
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse

from .const import DOMAIN
from .coordinator import PhilipsShaverCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.LIGHT, Platform.SELECT, Platform.BINARY_SENSOR]

SERVICE_FETCH_HISTORY = "fetch_history"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Philips Shaver from a config entry."""
    address = entry.data["address"]

    coordinator = PhilipsShaverCoordinator(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start polling/live monitoring after platforms are registered
    await coordinator.async_start()
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

    _LOGGER.info("Philips Shaver integration loaded – address: %s", address)
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
