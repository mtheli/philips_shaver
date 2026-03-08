# custom_components/philips_shaver/button.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CHAR_BLADE_REPLACEMENT
from .entity import PhilipsShaverEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips Shaver button platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([PhilipsBladeReplacementButton(coordinator, entry)])


class PhilipsBladeReplacementButton(PhilipsShaverEntity, ButtonEntity):
    """Button to confirm blade/shaver head replacement."""

    _attr_translation_key = "blade_replacement"
    _attr_icon = "mdi:razor-double-edge"

    def __init__(self, coordinator: Any, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_blade_replacement"

    async def async_press(self) -> None:
        """Write to 0x010E to reset the head replacement counter."""
        if not self.coordinator.transport.is_connected:
            _LOGGER.warning("Shaver not connected – cannot confirm blade replacement")
            return

        try:
            await self.coordinator.transport.write_char(
                CHAR_BLADE_REPLACEMENT, bytes([0x01])
            )
            _LOGGER.info("Blade replacement confirmed – head counter reset")
        except Exception as e:
            _LOGGER.error("Failed to confirm blade replacement: %s", e)
            return

        new_data = self.coordinator.data.copy()
        new_data["head_remaining"] = 100
        new_data["last_seen"] = datetime.now()
        self.coordinator.async_set_updated_data(new_data)
