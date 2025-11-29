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
        PhilipsAmountOfChargesSensor(hass, entry),
        PhilipsFirmwareSensor(hass, entry),
        PhilipsHeadRemainingSensor(hass, entry),
        PhilipsDaysSinceLastUsedSensor(hass, entry),
        PhilipsShavingTimeSensor(hass, entry),
        PhilipsDeviceStateSensor(hass, entry),
        PhilipsTravelLockBinarySensor(hass, entry),
        PhilipsDeviceActivitySensor(hass, entry),
        PhilipsLastSeenSensor(hass, entry),
        PhilipsRssiSensor(hass, entry),
        PhilipsCleaningProgressSensor(hass, entry),
        PhilipsCleaningCyclesSensor(hass, entry),
        PhilipsMotorSpeedSensor(hass, entry),
        PhilipsMotorCurrentSensor(hass, entry),
    ]
    async_add_entities(entities)


# =============================================================================
# Batterie
# =============================================================================
class PhilipsBatterySensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "battery"
    _attr_native_unit_of_measurement = "%"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-unknown"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_battery"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("battery")

    @property
    def icon(self) -> str | None:
        """Dynamic battery-icon based on state"""
        battery_level = self.native_value or 0
        state = self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("device_state")

        # if the battery level is unkown
        if battery_level is None:
            if state == "charging":
                return "mdi:battery-charging-unknown"
            return "mdi:battery-unknown"

        # shaving in progress
        if state == "shaving":
            return "mdi:battery-alert-bluetooth"

        # determine basic icon name
        if state == "charging":
            base = "mdi:battery-charging"
            outline = "-outline" if battery_level <= 10 else ""
        else:
            base = "mdi:battery"
            outline = "-outline" if battery_level <= 10 else ""

        # battery fully charged
        if battery_level >= 100:
            return base

        # battery >= 20 <= 90
        level = min(
            90, ((battery_level - 1) // 10) * 10 + 10 if battery_level > 10 else 10
        )
        suffix = f"-{level}" if battery_level > 10 or outline else ""

        return f"{base}{suffix}{outline}"

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Amount of Charges
# =============================================================================
class PhilipsAmountOfChargesSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "amount_of_charges"
    _attr_native_unit_of_measurement = "charges"
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_amount_of_charges"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get(
            "amount_of_charges"
        )

    @property
    def available(self) -> bool:
        return self.native_value is not None

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Firmware
# =============================================================================
class PhilipsFirmwareSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "firmware"
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
    _attr_translation_key = "head_remaining"
    _attr_native_unit_of_measurement = "%"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:razor-double-edge"

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
    _attr_translation_key = "days_last_used"
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
    _attr_translation_key = "shaving_time"
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
class PhilipsDeviceStateSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "device_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "shaving", "charging", "unknown"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_device_state"

    @property
    def native_value(self) -> str | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("device_state")

    @property
    def icon(self) -> str:
        state = self.native_value or "unknown"

        return {
            "off": "mdi:power-standby",
            "shaving": "mdi:face-man-shimmer",
            "charging": "mdi:battery-charging-100",
            "unknown": "mdi:help-circle-outline",
        }.get(state, "mdi:help-circle-outline")

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


class PhilipsTravelLockBinarySensor(PhilipsShaverEntity, BinarySensorEntity):
    _attr_translation_key = "travel_lock"
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


class PhilipsDeviceActivitySensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "activity"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "shaving", "charging", "cleaning", "locked"]
    _attr_icon = "mdi:state-machine"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_activity"

    @property
    def native_value(self) -> str:
        data = self.hass.data[DOMAIN][self.entry.entry_id]["data"]

        # 1. check for travel locking
        if data.get("travel_lock", False):
            return "locked"

        # 2. check for cleaning in progress
        progress = data.get("cleaning_progress")
        if progress is not None and 0 < progress < 100:
            return "cleaning"

        # 2. check for shaving
        if data.get("device_state") == "shaving":
            return "shaving"

        # 3. check for charging
        if data.get("device_state") == "charging":
            return "charging"

        # 4. Everything else
        return "off"

    @property
    def icon(self) -> str:
        return {
            "off": "mdi:power-standby",
            "shaving": "mdi:face-man-shimmer",
            "charging": "mdi:battery-charging-outline",
            "cleaning": "mdi:shimmer",
            "locked": "mdi:lock",
        }.get(self.native_value, "mdi:help-circle")

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Last Seen
# =============================================================================
class PhilipsLastSeenSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "last_seen"
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
# RSSI Sensor
# =============================================================================
class PhilipsRssiSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "rssi"
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
        service_info = async_last_service_info(self.hass, self._address)
        return service_info.rssi if service_info else None

    @property
    def available(self) -> bool:
        service_info = async_last_service_info(self.hass, self._address)
        return service_info is not None

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Cleaning Progress
# =============================================================================
class PhilipsCleaningProgressSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "cleaning_progress"
    _attr_native_unit_of_measurement = "%"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:progress-clock"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_cleaning_progress"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get(
            "cleaning_progress"
        )

    @property
    def icon(self) -> str:
        progress = self.native_value or 0
        if progress == 0:
            return "mdi:progress-clock"
        if progress >= 100:
            return "mdi:check-circle-outline"
        return "mdi:progress-wrench"

    @property
    def available(self) -> bool:
        progress = self.hass.data[DOMAIN][self.entry.entry_id]["data"].get(
            "cleaning_progress"
        )
        return progress is not None and progress > 0

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


class PhilipsCleaningCyclesSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "cleaning_cycles"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_cleaning_cycles"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get(
            "cleaning_cycles"
        )

    @property
    def available(self) -> bool:
        return self.native_value is not None

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Motor Speed
# =============================================================================
class PhilipsMotorSpeedSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "motor_rpm"
    _attr_native_unit_of_measurement = "RPM"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:speedometer"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_motor_rpm"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("motor_rpm")

    @property
    def available(self) -> bool:
        return self.native_value is not None

    @property
    def icon(self) -> str:
        rpm = self.native_value
        if rpm is None or rpm == 0:
            return "mdi:speedometer-slow"
        if rpm < 3000:
            return "mdi:speedometer-slow"
        if rpm < 6000:
            return "mdi:speedometer-medium"
        return "mdi:speedometer"

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Motor Current
# =============================================================================
class PhilipsMotorCurrentSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "motor_current"
    _attr_native_unit_of_measurement = "mA"
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:current-dc"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_motor_current"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get(
            "motor_current_ma"
        )

    @property
    def available(self) -> bool:
        return self.native_value is not None

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()
