from __future__ import annotations

import logging
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback as hass_callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PhilipsShaverCoordinator
from .entity import PhilipsShaverEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Philips Shaver binary sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = [
        PhilipsChargingBinarySensor(coordinator, entry),
        PhilipsTravelLockBinarySensor(coordinator, entry),
    ]

    async_add_entities(entities)


class PhilipsChargingBinarySensor(PhilipsShaverEntity, BinarySensorEntity):
    """Binary sensor to show if the shaver is charging."""

    _attr_translation_key = "charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the charging sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_is_charging"

    @property
    def is_on(self) -> bool:
        """Return True if the shaver is currently charging."""
        if not self.coordinator.data:
            return False

        # checking for charging status
        return self.coordinator.data.get("device_state") == "charging"


class PhilipsTravelLockBinarySensor(PhilipsShaverEntity, BinarySensorEntity):
    _attr_translation_key = "travel_lock"
    _attr_device_class = BinarySensorDeviceClass.LOCK
    _attr_icon = "mdi:lock"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_travel_lock"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("travel_lock", False)
