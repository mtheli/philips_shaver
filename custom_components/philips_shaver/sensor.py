# custom_components/philips_shaver/sensor.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
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
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import UnitOfTime, PERCENTAGE
from homeassistant.components.bluetooth import async_last_service_info
from .coordinator import PhilipsShaverCoordinator

from .const import (
    DOMAIN,
    CONF_TRANSPORT_TYPE, TRANSPORT_ESP_BRIDGE, CONF_SERVICES,
    SVC_CONTROL, SVC_GROOMER,
    CARTRIDGE_CAPACITY, EVAPORATION_RATE, CLEANING_CONSTANTS, CLEANING_CONSTANT_DEFAULT,
)
from .entity import PhilipsConnectionEntity, PhilipsShaverEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

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
        # PhilipsMotorRpmMaxSensor(coordinator, entry),   # not present on all models, no known use
        # PhilipsMotorRpmMinSensor(coordinator, entry),  # not present on all models, no known use
        PhilipsModelNumberSensor(coordinator, entry),
        PhilipsTotalAgeSensor(coordinator, entry),
    ]

    # Handle Load Type requires Control Service (0x0300)
    has_control = SVC_CONTROL in coordinator.available_services
    if has_control:
        entities.append(PhilipsHandleLoadTypeSensor(coordinator, entry))

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

    # Speed sensors require Smart Groomer Service (0x0700) — OneBlade only
    has_groomer = SVC_GROOMER in coordinator.available_services
    if has_groomer:
        entities.append(PhilipsSpeedSensor(coordinator, entry))
        entities.append(PhilipsSpeedVerdictSensor(coordinator, entry))

    # check for motion capability
    if coordinator.capabilities.motion:
        entities.append(PhilipsMotionTypeSensor(coordinator, entry))
    else:
        _LOGGER.info(
            "Shaver does not support motion sensing – skipping motion sensor"
        )

    # Connection sub-device: adapter works for both transports
    entities.append(PhilipsAdapterSensor(coordinator, entry))

    is_esp = entry.data.get(CONF_TRANSPORT_TYPE) == TRANSPORT_ESP_BRIDGE
    # RSSI sensor only for direct BLE (not available via ESP bridge)
    if not is_esp:
        entities.append(PhilipsRssiSensor(coordinator, entry))

    # Bridge version sensor only on ESP
    if is_esp:
        entities.append(PhilipsBridgeVersionSensor(coordinator, entry))
        entities.append(PhilipsBridgeBootTimeSensor(coordinator, entry))

    async_add_entities(entities)


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


# Shaver battery constants (standard algorithm)
BATTERY_MAX_SHAVING_MINUTES = 50
BATTERY_AVG_SHAVE_MINUTES = 3.3

# OneBlade battery constants (from manufacturer app)
ONEBLADE_CURRENT_COEFF = -0.165
ONEBLADE_CURRENT_OFFSET = 265.8
ONEBLADE_EFFICIENCY = 0.9
# Fallback values when no history data is available
ONEBLADE_DEFAULT_AVG_CURRENT = 200.0  # mA
ONEBLADE_DEFAULT_AVG_DURATION = 180.0  # seconds (3 minutes)


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
        self._is_oneblade = SVC_GROOMER in {
            s.lower() for s in entry.data.get(CONF_SERVICES, [])
        }

    @property
    def native_value(self) -> int | None:
        battery = self.coordinator.data.get("battery")
        if battery is None:
            return None

        if self._is_oneblade:
            return self._calc_oneblade(battery)
        return self._calc_shaver(battery)

    @staticmethod
    def _calc_shaver(battery: int) -> int:
        """Standard shaver: linear estimate from battery percentage."""
        minutes = (battery / 100.0) * BATTERY_MAX_SHAVING_MINUTES
        return int(minutes / BATTERY_AVG_SHAVE_MINUTES)

    def _calc_oneblade(self, battery: int) -> int:
        """OneBlade: motor-current-based estimate from manufacturer app."""
        avg_current = ONEBLADE_DEFAULT_AVG_CURRENT
        avg_duration = ONEBLADE_DEFAULT_AVG_DURATION

        # Use history data if available
        sessions = self.coordinator.data.get("history_sessions")
        if sessions:
            currents = [s["avg_current_ma"] for s in sessions if s.get("avg_current_ma")]
            durations = [s["duration_seconds"] for s in sessions if s.get("duration_seconds")]
            if currents:
                avg_current = sum(currents) / len(currents)
            if durations:
                avg_duration = sum(durations) / len(durations)

        if avg_current <= 0:
            return 0

        minutes_remaining = (
            (ONEBLADE_CURRENT_COEFF * avg_current + ONEBLADE_CURRENT_OFFSET)
            * ONEBLADE_EFFICIENCY
            / avg_current
            * 60.0
            * battery
            / 100.0
        )
        shave_minutes = avg_duration / 60.0
        if shave_minutes <= 0:
            return 0
        return max(0, int(minutes_remaining / shave_minutes))


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
    _attr_options = ["initializing", "off", "shaving", "charging", "cleaning", "locked"]
    _attr_icon = "mdi:state-machine"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_activity"

    @property
    def available(self) -> bool:
        """Always available — shows 'initializing' when no data yet."""
        return True

    @property
    def native_value(self) -> str:
        data = self.coordinator.data
        if not data:
            return "off"

        # 0. Connecting — show initializing while reading data
        if data.get("_connecting"):
            return "initializing"

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
            "initializing": "mdi:loading",
            "off": "mdi:power-standby",
            "shaving": "mdi:face-man-shimmer",
            "charging": "mdi:battery-charging-outline",
            "cleaning": "mdi:shimmer",
            "locked": "mdi:lock",
        }.get(self.native_value, "mdi:help-circle")



# =============================================================================
# Last Seen
# =============================================================================
class PhilipsLastSeenSensor(PhilipsConnectionEntity, RestoreEntity, SensorEntity):
    _attr_translation_key = "last_seen"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
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
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                restored = datetime.fromisoformat(last_state.state)
                if restored.tzinfo is None:
                    restored = restored.replace(tzinfo=timezone.utc)
                self.coordinator.data["last_seen"] = restored
                _LOGGER.info("Restored last_seen: %s", restored.isoformat())
            except (ValueError, TypeError):
                pass

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.get("last_seen")



# =============================================================================
# RSSI Sensor
# =============================================================================
class PhilipsRssiSensor(PhilipsConnectionEntity, SensorEntity):
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
        # When actively connected, prefer the RSSI from the scanner carrying
        # the link — the global advert cache may show a stronger signal on a
        # different scanner that isn't serving the connection.
        live_rssi = self.coordinator.transport.connection_rssi
        if live_rssi is not None:
            return live_rssi
        service_info = async_last_service_info(self.hass, self._device_id)
        if service_info is None or service_info.rssi is None:
            return None
        # -127 is habluetooth/BlueZ sentinel for "no fresh advertisement"
        if service_info.rssi <= -127:
            return None
        return service_info.rssi



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
                    restored = datetime.fromisoformat(attrs["sync_timestamp"])
                    if restored.tzinfo is None:
                        restored = restored.replace(tzinfo=timezone.utc)
                    self._sync_timestamp = restored
                except (ValueError, TypeError):
                    pass

    @property
    def native_value(self) -> float | None:
        if self._sync_timestamp is None:
            return None
        # Apply real-time evaporation since last sync
        days_since = (
            (datetime.now(timezone.utc) - self._sync_timestamp).total_seconds() / 86400
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
                self._sync_timestamp = datetime.now(timezone.utc)
            elif current_cycles != self._sync_cleaning_count:
                self._recalculate(current_cycles)
        super()._handle_coordinator_update()

    def _recalculate(self, current_cycles: int) -> None:
        """Apply the evaporation algorithm to compute remaining cycles."""
        now = datetime.now(timezone.utc)
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
        self.set_cartridge_value(CARTRIDGE_CAPACITY)

    def set_cartridge_value(self, value: float) -> None:
        """Set remaining cycles to a custom value (0–30)."""
        value = max(0.0, min(CARTRIDGE_CAPACITY, value))
        self._stored_remaining = value
        current = self.coordinator.data.get("cleaning_cycles")
        if current is not None:
            self._sync_cleaning_count = current
        self._sync_timestamp = datetime.now(timezone.utc)
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
        base = settings.get("pressure_base_value", 500)

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


# =============================================================================
# Speed (OneBlade — Smart Groomer Service)
# =============================================================================
class PhilipsSpeedSensor(PhilipsShaverEntity, SensorEntity):
    """OneBlade movement speed (uint16 LE from 0x0703)."""

    _attr_translation_key = "speed"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:speedometer"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_speed"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("speed")


class PhilipsSpeedVerdictSensor(PhilipsShaverEntity, SensorEntity):
    """OneBlade speed coaching verdict (computed from speed + thresholds)."""

    _attr_translation_key = "speed_verdict"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["optimal", "too_fast", "none"]
    _attr_icon = "mdi:speedometer"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_speed_verdict"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("speed_verdict")

    @property
    def icon(self) -> str:
        verdict = self.native_value
        if verdict == "optimal":
            return "mdi:check-circle"
        if verdict == "too_fast":
            return "mdi:alert-circle"
        return "mdi:speedometer"


class PhilipsBridgeVersionSensor(PhilipsConnectionEntity, SensorEntity):
    """Sensor showing the ESP bridge component version."""

    _attr_translation_key = "bridge_version"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_bridge_version"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.transport.bridge_version


class PhilipsBridgeBootTimeSensor(PhilipsConnectionEntity, SensorEntity):
    """Sensor showing when the ESP bridge was last booted."""

    _attr_translation_key = "bridge_boot_time"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:restart"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_bridge_boot_time"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.transport.bridge_boot_time


class PhilipsAdapterSensor(PhilipsConnectionEntity, SensorEntity):
    """Adapter currently carrying the BLE connection."""

    _attr_translation_key = "adapter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(
        self, coordinator: PhilipsShaverCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_adapter"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.transport.connection_path
