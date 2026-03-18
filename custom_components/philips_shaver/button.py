# custom_components/philips_shaver/button.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CHAR_BLADE_REPLACEMENT, CHAR_SYSTEM_NOTIFICATIONS
from .entity import PhilipsShaverEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips Shaver button platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    has_cleaning = coordinator.capabilities.cleaning_mode or coordinator.capabilities.unit_cleaning

    entities: list[ButtonEntity] = [
        PhilipsBladeReplacementButton(coordinator, entry),
        PhilipsResetAllNotificationsButton(coordinator, entry),
    ]

    if has_cleaning:
        entities.append(PhilipsResetCleanReminderButton(coordinator, entry))
        entities.append(PhilipsCartridgeResetButton(coordinator, entry))

    async_add_entities(entities)


class PhilipsBladeReplacementButton(PhilipsShaverEntity, ButtonEntity):
    """Button to confirm blade/shaver head replacement."""

    _attr_translation_key = "blade_replacement"
    _attr_icon = "mdi:razor-double-edge"
    _attr_entity_category = EntityCategory.CONFIG

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
        new_data["last_seen"] = datetime.now(timezone.utc)
        self.coordinator.async_set_updated_data(new_data)


class PhilipsCartridgeResetButton(PhilipsShaverEntity, ButtonEntity):
    """Button to reset the cleaning cartridge counter to 30."""

    _attr_translation_key = "cartridge_reset"
    _attr_icon = "mdi:restart"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: Any, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_cartridge_reset"

    async def async_press(self) -> None:
        """Reset the remaining cleaning cycles to full."""
        sensor = self.hass.data[DOMAIN][self.entry.entry_id].get(
            "remaining_cycles_sensor"
        )
        if sensor is None:
            _LOGGER.warning("Remaining cycles sensor not found")
            return
        sensor.reset_cartridge()
        _LOGGER.info("Cleaning cartridge counter reset to 30")


class PhilipsResetCleanReminderButton(PhilipsShaverEntity, ButtonEntity):
    """Button to acknowledge the clean reminder notification."""

    _attr_translation_key = "reset_clean_reminder"
    _attr_icon = "mdi:spray-bottle"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: Any, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_reset_clean_reminder"

    async def async_press(self) -> None:
        """Clear bit 1 (clean reminder) in system notifications via read-modify-write."""
        if not self.coordinator.transport.is_connected:
            _LOGGER.warning("Shaver not connected – cannot reset clean reminder")
            return

        try:
            raw = await self.coordinator.transport.read_char(CHAR_SYSTEM_NOTIFICATIONS)
            if raw is None:
                _LOGGER.warning("Could not read system notifications")
                return
            current = int.from_bytes(raw, "little")
            updated = current & ~0x02  # clear bit 1
            await self.coordinator.transport.write_char(
                CHAR_SYSTEM_NOTIFICATIONS, updated.to_bytes(4, "little")
            )
            _LOGGER.info("Clean reminder cleared (0x%08X → 0x%08X)", current, updated)
        except Exception as e:
            _LOGGER.error("Failed to reset clean reminder: %s", e)
            return

        # Re-read to confirm
        try:
            raw = await self.coordinator.transport.read_char(CHAR_SYSTEM_NOTIFICATIONS)
            if raw is not None:
                updated = int.from_bytes(raw, "little")
        except Exception:
            pass

        new_data = self.coordinator.data.copy()
        new_data["system_notifications"] = updated
        self.coordinator.async_set_updated_data(new_data)


class PhilipsResetAllNotificationsButton(PhilipsShaverEntity, ButtonEntity):
    """Button to acknowledge all system notifications."""

    _attr_translation_key = "reset_all_notifications"
    _attr_icon = "mdi:bell-check"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: Any, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_reset_all_notifications"

    async def async_press(self) -> None:
        """Write 0x00000000 to 0x0110 to clear all notification bits."""
        if not self.coordinator.transport.is_connected:
            _LOGGER.warning("Shaver not connected – cannot reset notifications")
            return

        try:
            await self.coordinator.transport.write_char(
                CHAR_SYSTEM_NOTIFICATIONS, bytes(4)
            )
            _LOGGER.info("All system notifications acknowledged")
        except Exception as e:
            _LOGGER.error("Failed to reset notifications: %s", e)
            return

        # Re-read to confirm
        try:
            raw = await self.coordinator.transport.read_char(CHAR_SYSTEM_NOTIFICATIONS)
            if raw is not None:
                new_data = self.coordinator.data.copy()
                new_data["system_notifications"] = int.from_bytes(raw, "little")
                self.coordinator.async_set_updated_data(new_data)
                return
        except Exception as e:
            _LOGGER.debug("Failed to re-read notifications: %s", e)

        # Fallback: assume success
        new_data = self.coordinator.data.copy()
        new_data["system_notifications"] = 0
        self.coordinator.async_set_updated_data(new_data)
