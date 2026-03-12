# custom_components/philips_shaver/select.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SVC_CONTROL,
    CHAR_SHAVING_MODE,
    SHAVING_MODES,
    CHAR_LIGHTRING_COLOR_BRIGHTNESS,
    LIGHTRING_BRIGHTNESS_MODES,
)
from .entity import PhilipsShaverEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips Shaver select platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    has_control = SVC_CONTROL in coordinator.available_services
    entities = []

    if has_control:
        entities.append(PhilipsShavingModeSelect(coordinator, entry))

    if coordinator.capabilities.light_ring:
        entities.append(PhilipsLightRingBrightnessSelect(coordinator, entry))

    async_add_entities(entities)


class PhilipsShavingModeSelect(PhilipsShaverEntity, SelectEntity):
    """Select entity for the shaving mode (Sensitive, Regular, Intense, Custom, Foam)."""

    _attr_translation_key = "shaving_mode"
    _attr_options = ["sensitive", "regular", "intense", "custom", "foam", "battery_saving"]

    def __init__(self, coordinator: Any, entry: ConfigEntry) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_shaving_mode_select"

    @property
    def current_option(self) -> str | None:
        """Return the current shaving mode from coordinator data."""
        mode_id = self.coordinator.data.get("shaving_mode_value")

        # Map mode ID to option string
        return SHAVING_MODES.get(mode_id)

    async def async_select_option(self, option: str) -> None:
        """Send the selected mode to the shaver."""
        if not self.coordinator.transport.is_connected:
            _LOGGER.warning(
                "Shaver not connected – cannot set shaving mode to %s", option
            )
            return

        write_mapping = {
            "sensitive": 0x00,
            "regular": 0x01,
            "intense": 0x02,
            "custom": 0x03,
            "foam": 0x04,
            "battery_saving": 0x05,
        }

        val = write_mapping.get(option)
        if val is None:
            return

        try:
            await self.coordinator.transport.write_char(CHAR_SHAVING_MODE, bytes([val]))
            _LOGGER.info("Shaving mode set to %s (0x%02x)", option, val)
        except Exception as e:
            _LOGGER.error("Failed to write shaving mode %s: %s", option, e)
            return

        # Update coordinator data immediately
        new_data = self.coordinator.data.copy()
        new_data["shaving_mode_value"] = val
        new_data["shaving_mode"] = option
        new_data["last_seen"] = datetime.now()

        self.coordinator.async_set_updated_data(new_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose raw mode value and active shaving settings."""
        mode_id = self.coordinator.data.get("shaving_mode_value")
        attrs: dict[str, Any] = {"raw_value": mode_id}

        if mode_id == 3:
            settings = self.coordinator.data.get("custom_shaving_settings")
        else:
            settings = self.coordinator.data.get("shaving_settings")

        if settings:
            attrs.update(settings)

        return attrs

    @property
    def icon(self) -> str:
        """Return a dynamic icon based on the current shaving mode."""
        mode_id = self.coordinator.data.get("shaving_mode_value")
        ICONS = {
            0: "mdi:feather",  # sensitive
            1: "mdi:face-man",  # regular
            2: "mdi:lightning-bolt",  # intense
            3: "mdi:tune",  # custom
            4: "mdi:spray",  # foam
            5: "mdi:battery-heart-outline",  # battery_saving
        }
        return ICONS.get(mode_id, "mdi:face-man")


class PhilipsLightRingBrightnessSelect(PhilipsShaverEntity, SelectEntity):
    """Select entity for the light ring brightness (High, Medium, Low)."""

    _attr_translation_key = "lightring_brightness"
    _attr_options = ["high", "medium", "low"]
    _attr_icon = "mdi:brightness-6"

    @property
    def available(self) -> bool:
        """Unavailable when light ring is disabled via app handle settings."""
        if not self.coordinator.data.get("lightring_enabled", True):
            return False
        return super().available

    def __init__(self, coordinator: Any, entry: ConfigEntry) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_lightring_brightness_select"

    @property
    def current_option(self) -> str | None:
        """Return the current brightness from coordinator data."""
        return self.coordinator.data.get("lightring_brightness")

    async def async_select_option(self, option: str) -> None:
        """Send the selected brightness to the shaver."""
        if not self.coordinator.transport.is_connected:
            _LOGGER.warning(
                "Shaver not connected – cannot set brightness to %s", option
            )
            return

        write_mapping = {
            "high": 0xFF,
            "medium": 0xCD,
            "low": 0x9B,
        }

        val = write_mapping.get(option)
        if val is None:
            return

        try:
            await self.coordinator.transport.write_char(
                CHAR_LIGHTRING_COLOR_BRIGHTNESS, bytes([val])
            )
            _LOGGER.info("Light ring brightness set to %s (0x%02x)", option, val)
        except Exception as e:
            _LOGGER.error("Failed to write brightness %s: %s", option, e)
            return

        new_data = self.coordinator.data.copy()
        new_data["lightring_brightness_value"] = val
        new_data["lightring_brightness"] = option
        new_data["last_seen"] = datetime.now()

        self.coordinator.async_set_updated_data(new_data)
