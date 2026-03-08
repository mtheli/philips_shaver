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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import UnitOfTime, PERCENTAGE
from homeassistant.components.bluetooth import async_last_service_info
from .coordinator import PhilipsShaverCoordinator

from .const import (
    DOMAIN, CONF_ENABLE_LIVE_UPDATES, DEFAULT_ENABLE_LIVE_UPDATES,
    CONF_TRANSPORT_TYPE, TRANSPORT_ESP_BRIDGE,
    CARTRIDGE_CAPACITY, EVAPORATION_RATE, CLEANING_CONSTANTS, CLEANING_CONSTANT_DEFAULT,
)
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
        PhilipsRemainingShavesSensor(coordinator, entry),
        PhilipsAmountOfChargesSensor(coordinator, entry),
        PhilipsShaverAmountOfOperationalTurnsSensor(coordinator, entry),
        PhilipsFirmwareSensor(coordinator, entry),
        PhilipsHeadRemainingSensor(coordinator, entry),
        PhilipsDaysSinceLastUsedSensor(coordinator, entry),
        PhilipsShavingTimeSensor(coordinator, entry),
        PhilipsDeviceStateSensor(coordinator, entry),
        PhilipsDeviceActivitySensor(coordinator, entry),
        PhilipsLastSeenSensor(coordinator, entry),
        PhilipsMotorSpeedSensor(coordinator, entry),
        PhilipsMotorCurrentSensor(coordinator, entry),
        PhilipsMotorCurrentMaxSensor(coordinator, entry),
        PhilipsMotorRpmMaxSensor(coordinator, entry),
        PhilipsMotorRpmMinSensor(coordinator, entry),
        PhilipsHandleLoadTypeSensor(coordinator, entry),
        PhilipsModelNumberSensor(coordinator, entry),
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

    # check for cleaning capability (cleaning_mode or unit_cleaning)
    if coordinator.capabilities.cleaning_mode or coordinator.capabilities.unit_cleaning:
        entities.append(PhilipsCleaningProgressSensor(coordinator, entry))
        entities.append(PhilipsCleaningCyclesSensor(coordinator, entry))
        remaining_sensor = PhilipsRemainingCleaningCyclesSensor(coordinator, entry)
        entities.append(remaining_sensor)
        hass.data[DOMAIN][entry.entry_id]["remaining_cycles_sensor"] = remaining_sensor
    else:
        _LOGGER.info(
            "Shaver does not support cleaning mode – skipping cleaning sensors"
        )

    # check for motion capability
    if coordinator.capabilities.motion:
        entities.append(PhilipsMotionTypeSensor(coordinator, entry))
    else:
        _LOGGER.info(
            "Shaver does not support motion sensing – skipping motion sensor"
        )

    # RSSI sensor only for direct BLE (not available via ESP bridge)
    if entry.data.get(CONF_TRANSPORT_TYPE) != TRANSPORT_ESP_BRIDGE:
        entities.append(PhilipsRssiSensor(coordinator, entry))

    async_add_entities(entities)

    # Enable/disable live-only entities based on option
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
class PhilipsBatterySensor(PhilipsShaverEntity, RestoreEntity, SensorEntity):
    _attr_translation_key = "battery"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_battery"

    async def async_added_to_hass(self) -> None:
        """Restore battery level from previous state on HA restart."""
        await super().async_added_to_hass()

        if self.coordinator.data.get("battery") is not None:
            return  # Already have fresh data

        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                self.coordinator.data["battery"] = int(last_state.state)
                _LOGGER.info("Restored battery level: %s%%", last_state.state)
            except (ValueError, TypeError):
                pass

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


# Max shaving minutes and avg shave duration from Philips companion app
BATTERY_MAX_SHAVING_MINUTES = 50
BATTERY_AVG_SHAVE_MINUTES = 3.3


class PhilipsRemainingShavesSensor(PhilipsShaverEntity, SensorEntity):
    """Estimated remaining shaves based on battery level."""

    _attr_translation_key = "remaining_shaves"
    _attr_native_unit_of_measurement = "shaves"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:face-man-shimmer"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_remaining_shaves"

    @property
    def native_value(self) -> int | None:
        battery = self.coordinator.data.get("battery")
        if battery is None:
            return None
        minutes = (battery / 100.0) * BATTERY_MAX_SHAVING_MINUTES
        return int(minutes / BATTERY_AVG_SHAVE_MINUTES)


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
        self._attr_unique_id = f"{self._device_id}_amount_of_charges"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("amount_of_charges")



# =============================================================================
# Amount of Operational Turns
# =============================================================================
class PhilipsShaverAmountOfOperationalTurnsSensor(PhilipsShaverEntity, SensorEntity):
    """Sensor for the number of operational turns (power-on cycles)."""

    _attr_translation_key = "amount_of_operational_turns"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_amount_of_operational_turns"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("amount_of_operational_turns")


# =============================================================================
# Firmware
# =============================================================================
class PhilipsFirmwareSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:chip"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_firmware"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("firmware")



# =============================================================================
# Remaining Sensors
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
        self._attr_unique_id = f"{self._device_id}_head_remaining"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("head_remaining")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        minutes = self.coordinator.data.get("head_remaining_minutes")
        if minutes is None:
            return None

        return {"remaining_minutes": minutes}



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
        self._attr_unique_id = f"{self._device_id}_days_last_used"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("days_since_last_used")



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
        self._attr_unique_id = f"{self._device_id}_shaving_time"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("shaving_time")



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
        self._attr_unique_id = f"{self._device_id}_device_state"

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



class PhilipsDeviceActivitySensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "activity"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "shaving", "charging", "cleaning", "locked"]
    _attr_icon = "mdi:state-machine"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_activity"

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

        # 3. check for shaving
        if data.get("device_state") == "shaving":
            return "shaving"

        # 4. check for charging
        if data.get("device_state") == "charging":
            return "charging"

        # 5. Everything else
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



# =============================================================================
# Last Seen
# =============================================================================
class PhilipsLastSeenSensor(PhilipsShaverEntity, RestoreEntity, SensorEntity):
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
        self._attr_unique_id = f"{self._device_id}_last_seen"

    async def async_added_to_hass(self) -> None:
        """Restore last_seen timestamp from previous state on HA restart."""
        await super().async_added_to_hass()

        if self.coordinator.data.get("last_seen"):
            return  # Already have fresh data

        last_state = await self.async_get_last_state()
        if last_state and (iso := last_state.attributes.get("last_seen_iso")):
            try:
                restored = datetime.fromisoformat(iso)
                self.coordinator.data["last_seen"] = restored
                _LOGGER.info("Restored last_seen: %s", restored.isoformat())
            except (ValueError, TypeError):
                pass

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Persist the actual timestamp for restore on restart."""
        last_seen = self.coordinator.data.get("last_seen")
        if last_seen:
            return {"last_seen_iso": last_seen.isoformat()}
        return None

    @property
    def native_value(self) -> int | None:
        last_seen = self.coordinator.data.get("last_seen")
        if not last_seen:
            return None
        return int((datetime.now() - last_seen).total_seconds() // 60)



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
        self._attr_unique_id = f"{self._device_id}_rssi"

    @property
    def native_value(self) -> int | None:
        service_info = async_last_service_info(self.hass, self._device_id)
        return service_info.rssi if service_info else None



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
        self._attr_unique_id = f"{self._device_id}_cleaning_progress"

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



class PhilipsCleaningCyclesSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "cleaning_cycles"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_cleaning_cycles"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("cleaning_cycles")


class PhilipsRemainingCleaningCyclesSensor(
    PhilipsShaverEntity, RestoreEntity, SensorEntity
):
    """Remaining cleaning cycles with evaporation algorithm."""

    _attr_translation_key = "cleaning_cycles_remaining"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:spray-bottle"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_cleaning_cycles_remaining"
        self._stored_remaining: float = CARTRIDGE_CAPACITY
        self._sync_cleaning_count: int | None = None
        self._sync_timestamp: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Restore persisted state on HA restart."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                self._stored_remaining = float(last_state.state)
            except (ValueError, TypeError):
                pass
            attrs = last_state.attributes or {}
            if "sync_cleaning_count" in attrs:
                try:
                    self._sync_cleaning_count = int(attrs["sync_cleaning_count"])
                except (ValueError, TypeError):
                    pass
            if "sync_timestamp" in attrs:
                try:
                    self._sync_timestamp = datetime.fromisoformat(
                        attrs["sync_timestamp"]
                    )
                except (ValueError, TypeError):
                    pass

    @property
    def native_value(self) -> float | None:
        if self._sync_timestamp is None:
            return None
        # Apply real-time evaporation since last sync
        days_since = (
            (datetime.now() - self._sync_timestamp).total_seconds() / 86400
        )
        evaporation = days_since * EVAPORATION_RATE
        return max(0.0, min(CARTRIDGE_CAPACITY, self._stored_remaining - evaporation))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs: dict[str, Any] = {}
        if self._sync_cleaning_count is not None:
            attrs["sync_cleaning_count"] = self._sync_cleaning_count
        if self._sync_timestamp is not None:
            attrs["sync_timestamp"] = self._sync_timestamp.isoformat()
        attrs["stored_remaining"] = round(self._stored_remaining, 2)
        return attrs if attrs else None

    def _handle_coordinator_update(self) -> None:
        """Recalculate when cleaning_cycles changes."""
        current_cycles = self.coordinator.data.get("cleaning_cycles")
        if current_cycles is not None:
            if self._sync_cleaning_count is None:
                # First sync: initialize baseline
                self._sync_cleaning_count = current_cycles
                self._sync_timestamp = datetime.now()
            elif current_cycles != self._sync_cleaning_count:
                self._recalculate(current_cycles)
        super()._handle_coordinator_update()

    def _recalculate(self, current_cycles: int) -> None:
        """Apply the evaporation algorithm to compute remaining cycles."""
        now = datetime.now()
        days_since_sync = (
            (now - self._sync_timestamp).total_seconds() / 86400
            if self._sync_timestamp
            else 0.0
        )

        cycles_since_sync = current_cycles - self._sync_cleaning_count
        # Edge case: counter wrapped or reset
        if self._sync_cleaning_count > current_cycles and current_cycles > 0:
            cycles_since_sync = 1
        cycles_since_sync = max(0, cycles_since_sync)

        # Average days per cleaning cycle → cleaning constant lookup
        if cycles_since_sync > 0:
            avg_days = round(days_since_sync / cycles_since_sync)
        else:
            avg_days = 0

        cleaning_constant = CLEANING_CONSTANTS.get(
            min(avg_days, 6) if avg_days < 7 else 6, CLEANING_CONSTANT_DEFAULT
        )
        if avg_days >= 7:
            cleaning_constant = CLEANING_CONSTANT_DEFAULT

        evaporation_loss = days_since_sync * EVAPORATION_RATE
        cleaning_loss = cleaning_constant * cycles_since_sync

        remaining = max(
            0.0,
            min(CARTRIDGE_CAPACITY, self._stored_remaining - evaporation_loss - cleaning_loss),
        )

        # Advance sync point
        self._stored_remaining = remaining
        self._sync_cleaning_count = current_cycles
        self._sync_timestamp = now

    def reset_cartridge(self) -> None:
        """Reset remaining cycles to full cartridge capacity."""
        self._stored_remaining = CARTRIDGE_CAPACITY
        current = self.coordinator.data.get("cleaning_cycles")
        if current is not None:
            self._sync_cleaning_count = current
        self._sync_timestamp = datetime.now()
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
        self._attr_unique_id = f"{self._device_id}_motor_rpm"

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



# =============================================================================
# Motor Current
# =============================================================================
class PhilipsMotorCurrentSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "motor_current"
    _attr_native_unit_of_measurement = "mA"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:current-dc"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_motor_current"

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



class PhilipsMotorCurrentMaxSensor(PhilipsShaverEntity, SensorEntity):
    """Sensor for the static motor current limit threshold."""

    _attr_translation_key = "motor_current_max"
    _attr_native_unit_of_measurement = "mA"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:shield-check"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_motor_current_max"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("motor_current_max_ma")



# =============================================================================
# Motor RPM Max / Min
# =============================================================================
class PhilipsMotorRpmMaxSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "motor_rpm_max"
    _attr_native_unit_of_measurement = "RPM"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:speedometer"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_motor_rpm_max"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("motor_rpm_max")


class PhilipsMotorRpmMinSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "motor_rpm_min"
    _attr_native_unit_of_measurement = "RPM"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:speedometer-slow"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_motor_rpm_min"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("motor_rpm_min")


# =============================================================================
# Handle Load Type
# =============================================================================
class PhilipsHandleLoadTypeSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "handle_load_type"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "not_supported",
        "undefined",
        "detection_in_progress",
        "trimmer",
        "shaving_heads",
        "styler",
        "brush",
        "precision_trimmer",
        "beardstyler",
        "precision_trimmer_or_beardstyler",
        "no_load",
        "unknown",
    ]
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:puzzle"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_handle_load_type"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("handle_load_type")

    @property
    def extra_state_attributes(self) -> dict | None:
        raw = self.coordinator.data.get("handle_load_type_value")
        if raw is None:
            return None
        return {"raw_value": raw}

    @property
    def icon(self) -> str:
        load_type = self.native_value
        icons = {
            "trimmer": "mdi:content-cut",
            "shaving_heads": "mdi:razor-double-edge",
            "styler": "mdi:hair-dryer",
            "brush": "mdi:broom",
            "precision_trimmer": "mdi:content-cut",
            "beardstyler": "mdi:face-man-profile",
            "precision_trimmer_or_beardstyler": "mdi:content-cut",
            "no_load": "mdi:puzzle-outline",
        }
        return icons.get(load_type, "mdi:puzzle")


# =============================================================================
# Motion Type
# =============================================================================
class PhilipsMotionTypeSensor(PhilipsShaverEntity, SensorEntity):
    """Motion type sensor with threshold-based categorization.

    The BLE characteristic (0x0305) returns a uint8 motion quality score.
    APA-type shavers (i9000/XP9201) use threshold-based mapping:
      0     = no_motion
      1-49  = large_stroke  ("Try smaller circles")
      >= 50 = small_circle  ("Keep going!")
    """

    _attr_translation_key = "motion_type"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["no_motion", "small_circle", "large_stroke"]
    _attr_icon = "mdi:gesture-swipe"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_motion_type"

    @property
    def native_value(self) -> str | None:
        raw = self.coordinator.data.get("motion_type_value")
        if raw is None:
            return None
        if raw == 0:
            return "no_motion"
        if raw < 50:
            return "large_stroke"
        return "small_circle"

    @property
    def extra_state_attributes(self) -> dict | None:
        raw = self.coordinator.data.get("motion_type_value")
        if raw is None:
            return None
        return {"raw_value": raw}

    @property
    def icon(self) -> str:
        motion = self.native_value
        icons = {
            "no_motion": "mdi:hand-back-right-off",
            "small_circle": "mdi:circle-outline",
            "large_stroke": "mdi:gesture-swipe",
        }
        return icons.get(motion, "mdi:gesture-swipe")


# =============================================================================
# Model Number (Device Type)
# =============================================================================
class PhilipsModelNumberSensor(PhilipsShaverEntity, SensorEntity):
    _attr_translation_key = "model_number"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:information-outline"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_model_number"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("model_number")


# =============================================================================
# Pressure
# =============================================================================
class PhilipsShaverPressureSensor(PhilipsShaverEntity, SensorEntity):
    """Numeric pressure sensor for raw values."""

    _attr_translation_key = "pressure"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:gauge"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_pressure"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("pressure")


class PhilipsShaverPressureStateSensor(PhilipsShaverEntity, SensorEntity):
    """Pressure feedback state sensor (enum: too_low, optimal, too_high)."""

    _attr_translation_key = "pressure_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["no_contact", "too_low", "optimal", "too_high"]
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_pressure_state"

    @property
    def native_value(self) -> str | None:
        pressure = self.coordinator.data.get("pressure")
        if pressure is None:
            return None

        # Get dynamic thresholds from coordinator
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
        """Dynamic icon based on the current pressure state."""
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
    """Sensor for the total device age (operating seconds)."""

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
        self._attr_unique_id = f"{self._device_id}_total_age"

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
