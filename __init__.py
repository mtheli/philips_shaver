"""Philips Shaver integration."""
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up Philips Shaver from YAML (optional)."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the integration from a config entry."""
    address = entry.data["address"]
    _LOGGER.info("Starting Philips Shaver integration for device %s", address)

    # Bluetooth Listener registrieren
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"address": address}

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.info("Stopping Philips Shaver integration")
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True
