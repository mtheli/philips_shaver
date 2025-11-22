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
        PhilipsDeviceStateSensor(hass, entry),
        PhilipsTravelLockBinarySensor(hass, entry),
        PhilipsDeviceActivitySensor(hass, entry),
        PhilipsLastSeenSensor(hass, entry),
        PhilipsRssiSensor(hass, entry),
        PhilipsCleaningProgressSensor(hass, entry),
        PhilipsMotorSpeedSensor(hass, entry),
        PhilipsMotorCurrentSensor(hass, entry),
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

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_battery"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("battery")

    @property
    def icon(self) -> str | None:
        """Dynamisches Battery-Icon basierend auf Ladestatus und Akkustand."""
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
            return base  # mdi:battery bzw. mdi:battery-charging

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
    _attr_name = "Last Session Duration"
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
    _attr_name = "State"
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
            "off": "mdi:power-standby",  # power off
            "shaving": "mdi:face-man-shimmer",  # shaving in progress
            "charging": "mdi:battery-charging-100",  # charging
            "unknown": "mdi:help-circle-outline",  # unknown
        }.get(state, "mdi:help-circle-outline")

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


# sensor.py – ersetzt alle drei Binary-Sensoren
class PhilipsDeviceActivitySensor(PhilipsShaverEntity, SensorEntity):
    _attr_name = "Activity"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "shaving", "charging", "cleaning"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:state-machine"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_activity"

    @property
    def native_value(self) -> str:
        data = self.hass.data[DOMAIN][self.entry.entry_id]["data"]

        # 1. Reinigung hat höchste Priorität (weil selten + wichtig)
        progress = data.get("cleaning_progress")
        if progress is not None and 0 < progress < 100:
            return "cleaning"

        # 2. Rasieren
        if data.get("in_use", False):
            return "shaving"

        # 3. Nur Laden
        if data.get("device_state") == "charging":
            return "charging"

        # 4. Alles andere
        return "off"

    @property
    def icon(self) -> str:
        return {
            "off":       "mdi:power-standby",
            "shaving":   "mdi:face-man-shimmer",
            "charging":  "mdi:battery-charging-outline",
            "cleaning":  "mdi:shimmer"
        }.get(self.native_value, "mdi:help-circle")

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

# =============================================================================
# Cleaning Progress Sensor
# =============================================================================
class PhilipsCleaningProgressSensor(PhilipsShaverEntity, SensorEntity):
    _attr_name = "Cleaning Progress"
    _attr_native_unit_of_measurement = "%"
    _attr_device_class = SensorDeviceClass.BATTERY  # am besten passend für Prozente
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:progress-clock"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{self._address}_cleaning_progress"

    @property
    def native_value(self) -> int | None:
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("cleaning_progress")

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
        """Nur anzeigen, wenn Reinigung aktiv ist oder kürzlich war."""
        progress = self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("cleaning_progress")
        return progress is not None and progress > 0

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()

# =============================================================================
# Motor Speed (RPM)
# =============================================================================
class PhilipsMotorSpeedSensor(PhilipsShaverEntity, SensorEntity):
    _attr_name = "Motor Speed"
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
        """Dynamisches Icon je nach Betrieb."""
        rpm = self.native_value
        if rpm is None or rpm == 0:
            return "mdi:speedometer-slow"
        if rpm < 3000:
            return "mdi:speedometer-slow"
        if rpm < 6000:
            return "mdi:speedometer-medium"
        return "mdi:speedometer"  # Vollgas ~6300 RPM

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Motor Current
# =============================================================================
class PhilipsMotorCurrentSensor(PhilipsShaverEntity, SensorEntity):
    _attr_name = "Motor Current"
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
        return self.hass.data[DOMAIN][self.entry.entry_id]["data"].get("motor_current_ma")

    @property
    def available(self) -> bool:
        return self.native_value is not None 

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()