# custom_components/philips_shaver/__init__.py
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    async_last_service_info,
    async_register_callback,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from . import bluetooth as shaver_bluetooth
from .const import (
    DOMAIN,
)
from .coordinator import PhilipsShaverCoordinator
from .utils import parse_color

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.LIGHT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Philips Shaver from a config entry."""
    address = entry.data["address"]

    # === NEU: Coordinator anlegen ===
    coordinator = PhilipsShaverCoordinator(hass, entry)
    # hass.async_create_task(coordinator._async_start_advertisement_logging())

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # WICHTIG: Bei Options-Änderung Integration neu laden
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    _LOGGER.info("Philips Shaver integration loaded – address: %s", address)
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Wird aufgerufen, wenn der User die Optionen ändert."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info("Start unloading philips shaver integration ...")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    coordinator = hass.data[DOMAIN].pop(entry.entry_id)["coordinator"]
    await coordinator.async_shutdown()

    _LOGGER.info("Unloading philips shaver integration finished")
    return True
