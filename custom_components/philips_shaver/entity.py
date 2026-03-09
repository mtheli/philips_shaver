# custom_components/philips_shaver/entity.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .coordinator import PhilipsShaverCoordinator
from .const import DOMAIN, CONF_ADDRESS, CONF_TRANSPORT_TYPE, TRANSPORT_ESP_BRIDGE, CONF_ESP_DEVICE_NAME

_LOGGER = logging.getLogger(__name__)


class PhilipsShaverEntity(CoordinatorEntity[PhilipsShaverCoordinator]):
    """Base class for all Philips Shaver entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PhilipsShaverCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entry = entry
        self._is_esp_bridge = (
            entry.data.get(CONF_TRANSPORT_TYPE) == TRANSPORT_ESP_BRIDGE
        )

        # Device identifier: MAC for BLE, esp_device_name for ESP bridge
        if self._is_esp_bridge:
            self._device_id = entry.data[CONF_ESP_DEVICE_NAME]
        else:
            self._device_id = entry.data["address"]

        # Set initial device info
        device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Philips",
            name="Philips Shaver",
        )
        if not self._is_esp_bridge:
            device_info["connections"] = {(dr.CONNECTION_BLUETOOTH, self._device_id)}
        else:
            # Add BLE connection if shaver MAC is known (auto-detected or migrated)
            shaver_mac = entry.data.get(CONF_ADDRESS)
            if shaver_mac:
                device_info["connections"] = {(dr.CONNECTION_BLUETOOTH, shaver_mac)}
        self._attr_device_info = device_info

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Only update device registry when relevant device data has changed
        data = self.coordinator.data

        model_changed = (
            self.device_info.get("model") != data.get("model_number")
            if self.device_info
            else True
        )
        fw_changed = (
            self.device_info.get("sw_version") != data.get("firmware")
            if self.device_info
            else True
        )

        if model_changed or fw_changed:
            device_registry = dr.async_get(self.hass)
            device = device_registry.async_get_device(
                    identifiers={(DOMAIN, self._device_id)}
                )

            if device:
                device_registry.async_update_device(
                    device.id,
                    model=data.get("model_number") or "i9000 / XP9201",
                    sw_version=data.get("firmware"),
                )

        # dynamically updating icon
        if hasattr(self, "icon"):
            try:
                new_icon = self.icon
                if getattr(self, "_attr_icon", None) != new_icon:
                    self._attr_icon = new_icon
            except Exception as err:
                _LOGGER.debug(
                    "Failed to update dynamic icon for %s: %s",
                    self.entity_id or self.__class__.__name__,
                    err,
                )

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True if the device is reachable (BLE range or ESP bridge data)."""

        if not self._is_esp_bridge:
            # Direct BLE: check if device is advertising
            service_info = async_last_service_info(self.hass, self._device_id)
            if service_info is not None:
                return True

        # ESP bridge / BLE fallback: check last_seen freshness (10 min timeout)
        last_seen = self.coordinator.data.get("last_seen") if self.coordinator.data else None
        if last_seen:
            return (datetime.now() - last_seen).total_seconds() < 600

        return False


class PhilipsBridgeEntity(PhilipsShaverEntity):
    """Base for entities on the ESP Bridge sub-device."""

    def __init__(
        self,
        coordinator: PhilipsShaverCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        # Override device_info to register on the bridge sub-device.
        # Linking to the ESPHome parent device is done in __init__.py.
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, f"{self._device_id}_bridge")},
            name="ESP Bridge",
            manufacturer="Espressif",
        )

    @property
    def available(self) -> bool:
        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
