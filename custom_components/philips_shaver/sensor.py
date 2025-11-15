from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback as hass_callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([PhilipsBatterySensor(hass, entry)])


class PhilipsBatterySensor(SensorEntity):
    _attr_native_unit_of_measurement = "%"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._attr_name = f"Philips Shaver Battery {entry.data.get('address')[-5:]}"
        self._state = None

        self._unsub = async_dispatcher_connect(
            hass,
            f"{DOMAIN}_update_{entry.entry_id}",
            self._update_callback,
        )

    async def async_will_remove_from_hass(self) -> None:
        self._unsub()

    @property
    def native_value(self) -> Any:
        return self._state

    @hass_callback # Import von hass_callback nicht vergessen!
    def _update_callback(self):
        data = self.hass.data[DOMAIN][self.entry.entry_id]["data"]
        self._state = data.get("battery")
        self.async_schedule_update_ha_state()
