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
from homeassistant.helpers import entity_registry as er
from homeassistant.const import UnitOfTime, PERCENTAGE
from homeassistant.components.bluetooth import async_last_service_info
from .coordinator import PhilipsShaverCoordinator

from .const import DOMAIN, CONF_ENABLE_LIVE_UPDATES, DEFAULT_ENABLE_LIVE_UPDATES
from .entity import PhilipsShaverEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    enable_live = entry.options.get(
        CONF_ENABLE_LIVE_UPDATES, DEFAULT_ENABLE_LIVE_UPDATES
    )

    entities: list[PhilipsShaverEntity] = [
        PhilipsBatterySensor(coordinator, entry),
        PhilipsAmountOfChargesSensor(coordinator, entry),
        PhilipsShaverAmountOfOperationalTurnsSensor(coordinator, entry),
        PhilipsFirmwareSensor(coordinator, entry),
        PhilipsHeadRemainingSensor(coordinator, entry),
        PhilipsDaysSinceLastUsedSensor(coordinator, entry),
        PhilipsShavingTimeSensor(coordinator, entry),
        PhilipsDeviceStateSensor(coordinator, entry),
        PhilipsDeviceActivitySensor(coordinator, entry),
        PhilipsLastSeenSensor(coordinator, entry),
        PhilipsRssiSensor(coordinator, entry),
        PhilipsMotorSpeedSensor(coordinator, entry),
        PhilipsMotorCurrentSensor(coordinator, entry),
        PhilipsMotorCurrentMaxSensor(coordinator, entry),
        PhilipsShavingModeSensor(coordinator, entry),
        PhilipsTotalAgeSensor(coordinator, entry),
    ]

    # check for pressure capability
    if coordinator.capabilities.pressure:
        entities.append(PhilipsShaverPressureSensor(coordinator, entry))
        entities.append(PhilipsShaverPressureStateSensor(coordinator, entry))
    else:
        _LOGGER.info(
            "Shaver does not support pressure feedback – skipping pressure sensors"
        )

    # check for cleaning mode capability
    if coordinator.capabilities.cleaning_mode:
        entities.append(PhilipsCleaningProgressSensor(coordinator, entry))
        entities.append(PhilipsCleaningCyclesSensor(coordinator, entry))
    else:
        _LOGGER.info(
            "Shaver does not support cleaning mode – skipping cleaning sensors"
        )

    async_add_entities(entities)

    # Immer am Ende: Live-Sensoren je nach Option (de)aktivieren
    await _update_live_entity_visibility(hass, coordinator.address, enable_live)


async def _update_live_entity_visibility(
    hass: HomeAssistant, address: str, enable_live: bool
) -> None:
    """Enable or disable live-only entities based on the live updates option."""
    ent_reg = er.async_get(hass)

    live_unique_ids = [
        f"{address}_cleaning_progress",
        f"{address}_motor_rpm",
        f"{address}_motor_current",
        f"{address}_pressure",
    ]

    for unique_id in live_unique_ids:
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
        if entity_id:
            if enable_live:
                # re-enable sensor
                ent_reg.async_update_entity(entity_id, disabled_by=None)
            else:
                # disabling sensors
                ent_reg.async_update_entity(
                    entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                )


# =============================================================================
# Batterie
# =============================================================================
class PhilipsBatterySensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "battery"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_battery"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        value = self.coordinator.data.get("battery")
        if value is None:
            return None

        try:
            return int(value)
        except (ValueError, TypeError):
            return None

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

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_amount_of_charges"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("amount_of_charges")

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Amount of Operational Turns
# =============================================================================
class PhilipsShaverAmountOfOperationalTurnsSensor(PhilipsShaverEntity, SensorEntity):
    """Sensor für die Anzahl der Einschaltvorgänge."""

    _attr_translation_key = "amount_of_operational_turns"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_amount_of_operational_turns"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("amount_of_operational_turns")


# =============================================================================
# Firmware
# =============================================================================
class PhilipsFirmwareSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_firmware"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("firmware")

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Restliche Sensoren
# =============================================================================
class PhilipsHeadRemainingSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "head_remaining"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:razor-double-edge"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_head_remaining"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("head_remaining")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        minutes = self.coordinator.data.get("head_remaining_minutes")
        if minutes is None:
            return None

        return {"remaining_minutes": minutes}

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

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_days_last_used"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("days_since_last_used")

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

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_shaving_time"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("shaving_time")

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

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_device_state"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("device_state")

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


class PhilipsDeviceActivitySensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "activity"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "shaving", "charging", "cleaning", "locked"]
    _attr_icon = "mdi:state-machine"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_activity"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data

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

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_last_seen"

    @property
    def native_value(self) -> int | None:
        last_seen = self.coordinator.data.get("last_seen")
        if not last_seen:
            return None
        return int((datetime.now() - last_seen).total_seconds() // 60)

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

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_rssi"

    @property
    def native_value(self) -> int | None:
        service_info = async_last_service_info(self.hass, self._address)
        return service_info.rssi if service_info else None

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Cleaning Progress
# =============================================================================
class PhilipsCleaningProgressSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "cleaning_progress"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:progress-clock"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_cleaning_progress"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("cleaning_progress")

    @property
    def icon(self) -> str:
        progress = self.native_value or 0
        if progress == 0:
            return "mdi:progress-clock"
        if progress >= 100:
            return "mdi:check-circle-outline"
        return "mdi:progress-wrench"

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


class PhilipsCleaningCyclesSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "cleaning_cycles"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_cleaning_cycles"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("cleaning_cycles")

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

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_motor_rpm"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("motor_rpm")

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

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_motor_current"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("motor_current_ma")

    @property
    def extra_state_attributes(self) -> dict | None:
        return {
            "max_limit": self.coordinator.data.get("motor_current_max_ma"),
            "load_percent": self._calculate_load(),
        }

    def _calculate_load(self) -> int | None:
        current = self.native_value
        maximum = self.coordinator.data.get("motor_current_max_ma")
        if current is not None and maximum and maximum > 0:
            return int((current / maximum) * 100)
        return None

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


class PhilipsMotorCurrentMaxSensor(PhilipsShaverEntity, SensorEntity):
    """Statische Schwelle für das Motor-Stromlimit."""

    _attr_translation_key = "motor_current_max"
    _attr_native_unit_of_measurement = "mA"
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:shield-check"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_motor_current_max"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("motor_current_max_ma")

    @hass_callback
    def _update_callback(self):
        self.async_write_ha_state()


# =============================================================================
# Shaving Mode
# =============================================================================
class PhilipsShavingModeSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "shaving_mode"
    _attr_icon = "mdi:shaver"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "sensitive",
        "regular",
        "intense",
        "custom",
        "foam",
        "battery_saving",
        "unknown",
    ]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_shaving_mode"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("shaving_mode")

    @property
    def extra_state_attributes(self) -> dict | None:
        # raw value of the mode
        mode_id = self.coordinator.data.get("shaving_mode_value")
        attrs = {"raw_value": mode_id}

        # determine the currently used mode
        if mode_id == 3:
            # if the mode is custom, use the values of the custom package (0330)
            settings = self.coordinator.data.get("custom_shaving_settings")
        else:
            # all other modes, use the standard settings (0332)
            settings = self.coordinator.data.get("shaving_settings")

        # add settings if available
        if settings:
            attrs.update(settings)

        return attrs

    @property
    def icon(self) -> str:
        # raw value of the mode
        mode_id = self.coordinator.data.get("shaving_mode_value")
        ICONS = {
            0: "mdi:feather",  # sensitive
            1: "mdi:face-man",  # regular
            2: "mdi:lightning-bolt",  # intense
            3: "mdi:tune",  # custom
            4: "mdi:spray",  # foam
            5: "mdi:battery-heart-outline",  # battery_saving
        }
        return ICONS.get(mode_id, "mdi:face-man")  # type: ignore


# =============================================================================
# Shaving Mode
# =============================================================================
class PhilipsShaverPressureSensor(PhilipsShaverEntity, SensorEntity):
    """Numerischer Drucksensor für Rohwerte."""

    _attr_translation_key = "pressure"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:gauge"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_pressure"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("pressure")


class PhilipsShaverPressureStateSensor(PhilipsShaverEntity, SensorEntity):
    """Status-Sensor für das Druck-Feedback (Enum)."""

    _attr_translation_key = "pressure_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["no_contact", "too_low", "optimal", "too_high"]
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_pressure_state"

    @property
    def native_value(self) -> str | None:
        pressure = self.coordinator.data.get("pressure")
        if pressure is None:
            return None

        # Dynamische Schwellenwerte aus dem Coordinator holen
        mode_id = self.coordinator.data.get("shaving_mode_value")
        settings = self.coordinator.data.get(
            "custom_shaving_settings" if mode_id == 3 else "shaving_settings"
        )

        if not settings:
            return "no_contact"

        low = settings.get("pressure_limit_low", 1500)
        high = settings.get("pressure_limit_high", 4000)
        base = settings.get("pressure_base", 500)

        if pressure < base:
            return "no_contact"
        if pressure < low:
            return "too_low"
        if pressure <= high:
            return "optimal"
        return "too_high"

    @property
    def icon(self) -> str:
        """Dynamisches Icon basierend auf dem Status."""
        state = self.native_value
        if state == "optimal":
            return "mdi:check-circle"
        if state == "too_high":
            return "mdi:alert-circle"
        if state == "too_low":
            return "mdi:arrow-down-circle"
        return "mdi:circle-outline"


# =============================================================================
# Total Age Sensor
# =============================================================================
class PhilipsTotalAgeSensor(PhilipsShaverEntity, SensorEntity):
    """Sensor für das Gesamtalter des Geräts (Betriebssekunden)."""

    _attr_translation_key = "total_age"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:history"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_total_age"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("total_age")

    @property
    def extra_state_attributes(self) -> dict | None:
        seconds = self.native_value
        if seconds is None:
            return None

        # Calculating readable date/time
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60

        return {"formatted_age": f"{days}d {hours}h {minutes}m", "raw_seconds": seconds}
