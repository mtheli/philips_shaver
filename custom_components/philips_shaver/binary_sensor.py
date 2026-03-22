from __future__ import annotations

import logging
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback as hass_callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PhilipsShaverCoordinator
from .entity import PhilipsBridgeEntity, PhilipsShaverEntity
from .const import DOMAIN, CONF_TRANSPORT_TYPE, TRANSPORT_ESP_BRIDGE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Philips Shaver binary sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    is_esp = entry.data.get(CONF_TRANSPORT_TYPE) == TRANSPORT_ESP_BRIDGE

    entities = [
        PhilipsChargingBinarySensor(coordinator, entry),
        PhilipsTravelLockBinarySensor(coordinator, entry),
    ]

    # System notification binary sensors (bit 0–4)
    has_cleaning = coordinator.capabilities.cleaning_mode or coordinator.capabilities.unit_cleaning
    for bit, key, icon_on, icon_off in NOTIFICATION_BITS:
        if key == "notification_clean_reminder" and not has_cleaning:
            continue
        entities.append(
            PhilipsNotificationBinarySensor(coordinator, entry, bit, key, icon_on, icon_off)
        )

    if is_esp:
        # Bridge sensors live on the ESP Bridge sub-device
        entities.append(PhilipsEspBridgeAliveSensor(coordinator, entry))
        entities.append(PhilipsBridgeBleConnectedSensor(coordinator, entry))
    else:
        entities.append(PhilipsShaverBleConnectedSensor(coordinator, entry))

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
        self._attr_unique_id = f"{self._device_id}_is_charging"

    @property
    def is_on(self) -> bool:
        """Return True if the shaver is currently charging."""
        if not self.coordinator.data:
            return False

        # checking for charging status
        return self.coordinator.data.get("device_state") == "charging"


class PhilipsTravelLockBinarySensor(PhilipsShaverEntity, BinarySensorEntity):
    _attr_translation_key = "travel_lock"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_travel_lock"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("travel_lock", False)

    @property
    def icon(self) -> str:
        return "mdi:lock" if self.is_on else "mdi:lock-open-variant"


NOTIFICATION_BITS = [
    # (bit_mask, translation_key, icon_on, icon_off)
    (0x01, "notification_motor_blocked", "mdi:engine-off", "mdi:engine"),
    (0x02, "notification_clean_reminder", "mdi:spray-bottle", "mdi:spray-bottle"),
    (0x04, "notification_head_replacement", "mdi:razor-double-edge", "mdi:razor-double-edge"),
    (0x08, "notification_battery_overheated", "mdi:thermometer-alert", "mdi:thermometer"),
    (0x10, "notification_unplug_required", "mdi:power-plug-off", "mdi:power-plug"),
]


class PhilipsNotificationBinarySensor(PhilipsShaverEntity, BinarySensorEntity):
    """Binary sensor for a single system notification bit."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: PhilipsShaverCoordinator,
        entry: ConfigEntry,
        bit_mask: int,
        translation_key: str,
        icon_on: str,
        icon_off: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._bit_mask = bit_mask
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{self._device_id}_{translation_key}"
        self._icon_on = icon_on
        self._icon_off = icon_off

    @property
    def is_on(self) -> bool:
        flags = self.coordinator.data.get("system_notifications", 0)
        return bool(flags & self._bit_mask)

    @property
    def icon(self) -> str:
        return self._icon_on if self.is_on else self._icon_off


class PhilipsShaverBleConnectedSensor(PhilipsShaverEntity, BinarySensorEntity):
    """Binary sensor showing whether the BLE link to the shaver is active."""

    _attr_translation_key = "shaver_ble_connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_shaver_ble_connected"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.transport.is_shaver_connected


class PhilipsBridgeBleConnectedSensor(PhilipsBridgeEntity, BinarySensorEntity):
    """BLE connection status on the ESP Bridge sub-device."""

    _attr_translation_key = "shaver_ble_connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_shaver_ble_connected"

    @property
    def is_on(self) -> bool:
        return self.coordinator.transport.is_shaver_connected


class PhilipsEspBridgeAliveSensor(PhilipsBridgeEntity, BinarySensorEntity):
    """Binary sensor showing whether the ESP32 bridge is reachable."""

    _attr_translation_key = "esp_bridge_alive"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_esp_bridge_alive"

    @property
    def is_on(self) -> bool:
        return self.coordinator.transport.is_bridge_alive
