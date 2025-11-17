# custom_components/philips_shaver/sensor.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback as hass_callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import UnitOfTime
from homeassistant.components.select import SelectEntity
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.components.bluetooth import async_last_service_info

from .const import DOMAIN
from .entity import PhilipsShaverEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities: list[PhilipsShaverEntity] = [
        PhilipsBatterySensor(hass, entry),
        PhilipsFirmwareSensor(hass, entry),
        PhilipsHeadRemainingSensor(hass, entry),
        PhilipsDaysSinceLastUsedSensor(hass, entry),
        PhilipsShavingTimeSensor(hass, entry),
        PhilipsDeviceStateSelect(hass, entry),
        PhilipsTravelLockBinarySensor(hass, entry),
        PhilipsInUseBinarySensor(hass, entry),
        PhilipsLastSeenSensor(hass, entry),
        PhilipsRssiSensor(hass, entry),
    ]
    async_add_entities(entities)


# =============================================================================
# Batterie
# =============================================================================
class PhilipsBatterySensor(PhilipsShaverEntity, SensorEntity):
    _attr_name = "Battery"
    _attr_native_unit_of_measurement = "%"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_battery"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("battery")

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Firmware (Diagnostic)
# =============================================================================
class PhilipsFirmwareSensor(PhilipsShaverEntity, SensorEntity):
    _attr_name = "Firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_firmware"

    @property
    def native_value(self) -> str | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("firmware")

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Restliche Sensoren
# =============================================================================
class PhilipsHeadRemainingSensor(PhilipsShaverEntity, SensorEntity):
    _attr_name = "Shaver Head Remaining"
    _attr_native_unit_of_measurement = "%"
    _attr_device_class = SensorDeviceClass.POWER_FACTOR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:saw-blade"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_head_remaining"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("head_remaining")

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


class PhilipsDaysSinceLastUsedSensor(PhilipsShaverEntity, SensorEntity):
    _attr_name = "Days Since Last Used"
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_days_last_used"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get(
            "days_since_last_used"
        )

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


class PhilipsShavingTimeSensor(PhilipsShaverEntity, SensorEntity):
    _attr_name = "Last Shaving Time"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-fast"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_shaving_time"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("shaving_time")

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Select & Binary Sensoren
# =============================================================================
class PhilipsDeviceStateSelect(PhilipsShaverEntity, SelectEntity):
    _attr_name = "State"
    _attr_icon = "mdi:state-machine"
    _attr_options = ["off", "shaving", "charging"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_device_state"

    @property
    def current_option(self) -> str | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("device_state")

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


class PhilipsTravelLockBinarySensor(PhilipsShaverEntity, BinarySensorEntity):
    _attr_name = "Travel Lock"
    _attr_device_class = BinarySensorDeviceClass.LOCK
    _attr_icon = "mdi:lock"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_travel_lock"

    @property
    def is_on(self) -> bool:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get(
            "travel_lock", False
        )

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


class PhilipsInUseBinarySensor(PhilipsShaverEntity, BinarySensorEntity):
    _attr_name = "In Use"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:play-circle"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_in_use"

    @property
    def is_on(self) -> bool:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("in_use", False)

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# NEU: Last Seen Sensor (wie gewünscht)
# =============================================================================
class PhilipsLastSeenSensor(PhilipsShaverEntity, SensorEntity):
    _attr_name = "Last Seen"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_last_seen"

    @property
    def native_value(self) -> int | None:
        last_seen = self.hass.data[DOMAIN][self.entry.entry_id].get("last_seen")
        if not last_seen:
            return None
        return int((datetime.now() - last_seen).total_seconds() // 60)

    @property
    def available(self) -> bool:
        return self.hass.data[DOMAIN][self.entry.entry_id].get("last_seen") is not None

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# NEU: RSSI Sensor (Signalstärke des Bluetooth-Signals)
# =============================================================================
class PhilipsRssiSensor(PhilipsShaverEntity, SensorEntity):
    _attr_name = "RSSI"
    _attr_native_unit_of_measurement = "dBm"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bluetooth"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_rssi"

    @property
    def native_value(self) -> int | None:
        """Aktueller RSSI-Wert aus der letzten Bluetooth-Advertisement."""
        service_info = async_last_service_info(self.hass, self._address)
        return service_info.rssi if service_info else None

    @property
    def available(self) -> bool:
        """Nur verfügbar, wenn das Gerät kürzlich gesehen wurde."""
        service_info = async_last_service_info(self.hass, self._address)
        return service_info is not None

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()
