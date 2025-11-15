# custom_components/philips_shaver/__init__.py
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, CHAR_BATTERY_LEVEL, POLL_INTERVAL
from . import bluetooth as shaver_bluetooth

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    address = entry.data.get("address")

    hass.data[DOMAIN][entry.entry_id] = {
        "address": address,
        "data": {},
    }

    async def _update_now(now=None):
        _LOGGER.info("Updating Philips Shaver %s", address)

        results = await shaver_bluetooth.connect_and_read(
            hass, address, [CHAR_BATTERY_LEVEL]
        )

        battery = None
        if CHAR_BATTERY_LEVEL in results and results[CHAR_BATTERY_LEVEL]:
            battery = results[CHAR_BATTERY_LEVEL][0]
            _LOGGER.info("Battery level: %s%%", battery)
        else:
            _LOGGER.warning("No battery data – is device paired?")

        hass.data[DOMAIN][entry.entry_id]["data"]["battery"] = battery
        async_dispatcher_send(hass, f"{DOMAIN}_update_{entry.entry_id}")

    await _update_now()  # Sofortiger erster Aufruf

    unsub = async_track_time_interval(hass, _update_now, timedelta(seconds=POLL_INTERVAL))
    hass.data[DOMAIN][entry.entry_id]["unsub"] = unsub

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data[DOMAIN].pop(entry.entry_id)
    if unsub := data.get("unsub"):
        unsub()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)