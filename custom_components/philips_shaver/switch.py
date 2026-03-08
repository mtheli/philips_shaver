# custom_components/philips_shaver/switch.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CHAR_APP_HANDLE_SETTINGS,
    APP_SETTINGS_FULL_COACHING,
    APP_SETTINGS_MAX_PRESSURE,
)
from .entity import PhilipsShaverEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities for the Philips Shaver."""
    from .const import DOMAIN

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[SwitchEntity] = []

    if coordinator.capabilities.light_ring:
        entities.append(PhilipsLightRingSwitch(coordinator, entry))

    if entities:
        async_add_entities(entities)


class PhilipsLightRingSwitch(PhilipsShaverEntity, SwitchEntity):
    """Switch entity to toggle the light ring on/off."""

    _attr_translation_key = "lightring_enabled"

    def __init__(self, coordinator: Any, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_lightring_enabled"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("lightring_enabled")

    @property
    def icon(self) -> str:
        if self.is_on:
            return "mdi:circle-slice-8"
        return "mdi:circle-outline"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_lightring(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_lightring(False)

    async def _set_lightring(self, enabled: bool) -> None:
        """Read-modify-write the app handle settings bitfield."""
        if not self.coordinator.transport.is_connected:
            _LOGGER.warning("Shaver not connected – cannot toggle light ring")
            return

        # Get current raw bytes (from last poll/notification)
        raw = self.coordinator.data.get("app_handle_settings_raw")
        if not raw:
            raw = await self.coordinator.transport.read_char(CHAR_APP_HANDLE_SETTINGS)
        if not raw:
            _LOGGER.error("Cannot read app handle settings – aborting")
            return

        val = int.from_bytes(raw, "little")

        # Modify bits (matching Philips companion app behavior)
        if enabled:
            val |= APP_SETTINGS_FULL_COACHING   # set bit 4
        else:
            val &= ~APP_SETTINGS_FULL_COACHING  # clear bit 4
        val &= ~APP_SETTINGS_MAX_PRESSURE       # always clear bit 5

        new_raw = val.to_bytes(len(raw), "little")

        try:
            await self.coordinator.transport.write_char(
                CHAR_APP_HANDLE_SETTINGS, new_raw
            )
            _LOGGER.info("Light ring %s", "enabled" if enabled else "disabled")
        except Exception as e:
            _LOGGER.error("Failed to write light ring setting: %s", e)
            return

        new_data = self.coordinator.data.copy()
        new_data["lightring_enabled"] = enabled
        new_data["app_handle_settings_raw"] = new_raw
        new_data["last_seen"] = datetime.now()
        self.coordinator.async_set_updated_data(new_data)
